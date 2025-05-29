import ast
import gzip
import logging
import os
import pickle
import time
import tkinter as tk
from concurrent.futures import ProcessPoolExecutor, as_completed
from tkinter import filedialog
import networkx as nx
import h5py
import numpy as np

def process_toa_aoa_chunk(
    src_nodes,
    target_nodes,
    G_data,
    distance_conversion,
    noise_factor,
    hdf5_path=None
):
    """Processa um chunk de nós para calcular dados ToA (Time of Arrival) e AoA (Angle of Arrival).
    Se hdf5_path for fornecido, salva diretamente no arquivo HDF5."""
    import networkx as nx
    import numpy as np

    SPEED_OF_LIGHT = 3e8

    def calc_aoa(source, target):
        dx = target[0] - source[0]
        dy = target[1] - source[1]
        angle_rad = np.arctan2(dy, dx)
        angle_deg = np.degrees(angle_rad)
        return angle_deg

    def get_path_and_loss(G, source, target):
        try:
            path = nx.shortest_path(G, source=source, target=target, weight='weight')
            obstacle_loss = sum(G[p][q]['weight'] for p, q in zip(path[:-1], path[1:]))
            return path, obstacle_loss
        except (nx.NetworkXNoPath, KeyError):
            return None, float('inf')

    G = nx.node_link_graph(G_data, edges="links")

    toa_results = {}
    aoa_results = {}

    for src in src_nodes:
        for tgt in target_nodes:
            if src == tgt:
                continue

            d_euclidean = np.hypot(src[0] - tgt[0], src[1] - tgt[1]) * distance_conversion

            path, obstacle_loss = get_path_and_loss(G, src, tgt)

            if path and len(path) > 2:
                path_length = 0
                for i in range(len(path)-1):
                    p1, p2 = path[i], path[i+1]
                    seg_length = np.hypot(p1[0]-p2[0], p1[1]-p2[1]) * distance_conversion
                    path_length += seg_length

                if obstacle_loss > 10:
                    primary_toa = (d_euclidean / SPEED_OF_LIGHT) * (1 + 0.1 * obstacle_loss/20)
                    reflected_toa = (path_length / SPEED_OF_LIGHT) * 1.3

                    detection_prob = 0.7 - (obstacle_loss / 100)
                    if np.random.random() > detection_prob:
                        toa = reflected_toa
                    else:
                        toa = primary_toa
                else:
                    toa = (d_euclidean / SPEED_OF_LIGHT) * (1 + 0.05 * obstacle_loss/20)
            else:
                toa = d_euclidean / SPEED_OF_LIGHT

            toa_error_factor = 1 + np.random.normal(0, noise_factor * (1 + 0.1 * (obstacle_loss if path else 0)))
            toa *= toa_error_factor
            toa_results[(src, tgt)] = toa

            base_aoa = calc_aoa(src, tgt)

            if path and len(path) > 2:
                last_obstacle = path[-2]
                reflected_aoa = calc_aoa(last_obstacle, tgt)

                reflection_prob = min(0.6, obstacle_loss / 40)

                if np.random.random() < reflection_prob:
                    aoa = reflected_aoa
                    aoa_noise = np.random.normal(0, noise_factor * 3 * 180)
                else:
                    aoa = base_aoa
                    aoa_noise = np.random.normal(0, noise_factor * (1 + obstacle_loss/30) * 180)
            else:
                aoa = base_aoa
                aoa_noise = np.random.normal(0, noise_factor * 180)

            aoa = (aoa + aoa_noise) % 360
            aoa_results[(src, tgt)] = aoa

    if hdf5_path is not None:
        with h5py.File(hdf5_path, "a", libver="latest") as f:
            f.swmr_mode = True
            toa_grp = f.require_group("toa")
            aoa_grp = f.require_group("aoa")
            for k, v in toa_results.items():
                key = f"{k[0]}|{k[1]}"
                toa_grp.attrs[key] = v
            for k, v in aoa_results.items():
                key = f"{k[0]}|{k[1]}"
                aoa_grp.attrs[key] = v
        return None, None
    return toa_results, aoa_results

class PrecomputeAoAToA:
    def __init__(self, optimizer):
        """Inicializa a classe de pré-computação ToA/AoA."""
        self.optimizer = optimizer

    @staticmethod
    def save_precomputed_data_hdf5(toa_data, aoa_data, filename):
        """Salva os dados ToA/AoA em formato HDF5."""
        logging.info(f"Salvando {len(toa_data)} pares de dados em {filename} (HDF5)")
        with h5py.File(filename, "w") as f:
            toa_grp = f.create_group("toa")
            aoa_grp = f.create_group("aoa")
            for k, v in toa_data.items():
                key = f"{k[0]}|{k[1]}"
                toa_grp.attrs[key] = v
            for k, v in aoa_data.items():
                key = f"{k[0]}|{k[1]}"
                aoa_grp.attrs[key] = v
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        logging.info(f"Dados HDF5 salvos. Tamanho do arquivo: {file_size_mb:.2f} MB")
        return filename

    @staticmethod
    def load_precomputed_data_hdf5(filename, pairs=None):
        """Carrega dados ToA/AoA de arquivo HDF5. Se pairs for fornecido, carrega apenas esses pares."""
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        logging.info(f"Carregando dados HDF5 de {filename} ({file_size_mb:.2f} MB)")
        start_time = time.time()
        toa_data = {}
        aoa_data = {}
        with h5py.File(filename, "r") as f:
            toa_grp = f["toa"]
            aoa_grp = f["aoa"]
            if pairs is None:
                for key in toa_grp.attrs:
                    src_str, tgt_str = key.split("|")
                    src = ast.literal_eval(src_str)
                    tgt = ast.literal_eval(tgt_str)
                    toa_data[(src, tgt)] = toa_grp.attrs[key]
                for key in aoa_grp.attrs:
                    src_str, tgt_str = key.split("|")
                    src = ast.literal_eval(src_str)
                    tgt = ast.literal_eval(tgt_str)
                    aoa_data[(src, tgt)] = aoa_grp.attrs[key]
            else:
                for src, tgt in pairs:
                    key = f"{src}|{tgt}"
                    if key in toa_grp.attrs:
                        toa_data[(src, tgt)] = toa_grp.attrs[key]
                    if key in aoa_grp.attrs:
                        aoa_data[(src, tgt)] = aoa_grp.attrs[key]
        elapsed = time.time() - start_time
        logging.info(f"Dados HDF5 carregados em {elapsed:.2f}s ({file_size_mb/elapsed:.2f} MB/s). Total de {len(toa_data):,} pares.")
        return toa_data, aoa_data

    def precompute_toa_aoa_data(self, G, nodes, filename=None, chunks=None, use_hdf5=True):
        """Realiza a pré-computação paralela dos dados ToA e AoA para todos os pares de nós.
        Se use_hdf5=True, salva em HDF5."""
        if chunks is None:
            chunks = min(os.cpu_count() or 4, 16)
        if filename is None:
            graph_file = getattr(G, 'graph', {}).get('filename', '')
            if graph_file:
                graph_name = os.path.splitext(os.path.basename(graph_file))[0]
            else:
                graph_name = f"grafo_{len(G.nodes())}nodes"
            filename = os.path.join(self.optimizer.precomputation_save_path, f"{graph_name}_aoa_toa_pre-computacao.h5")
        total_nodes = len(nodes)
        total_pairs = total_nodes * (total_nodes - 1)
        logging.info(f"Iniciando pré-computação paralela para {total_pairs} pares com {chunks} workers")
        logging.info(f"Os resultados serão salvos em: {filename}")
        chunk_size = max(1, len(nodes) // chunks)
        node_chunks = [nodes[i:i+chunk_size] for i in range(0, len(nodes), chunk_size)]
        chunks = len(node_chunks)
        G_data = nx.node_link_data(G, edges="links")
        start_time = time.time()
        total_processed = 0
        last_percent = -1

        with h5py.File(filename, "w") as f:
            f.create_group("toa")
            f.create_group("aoa")
        with ProcessPoolExecutor(max_workers=chunks) as executor:
            futures = []
            for i, src_chunk in enumerate(node_chunks):
                futures.append(
                    executor.submit(
                        process_toa_aoa_chunk,
                        src_chunk,
                        nodes,
                        G_data,
                        self.optimizer.distance_conversion,
                        self.optimizer.noise_factor,
                        filename
                    )
                )
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    total_processed += len(node_chunks[i-1]) * len(nodes)
                    percent = int((total_processed / total_pairs) * 100)
                    if percent > last_percent and percent % 5 == 0:
                        logging.info(f"Progresso total: {percent}% concluído")
                        last_percent = percent
                except Exception as e:
                    logging.error(f"Erro no processamento do chunk {i}: {e}", exc_info=True)
        total_time = time.time() - start_time
        logging.info(f"Pré-computação HDF5 concluída em {total_time/60:.2f} minutos.")
        return None, None, filename

    def generate_toa_aoa_data(self, G, nodes, noise_factor=None, use_precomputed=True, precomputed_file=None, force_precompute=False, prefer_hdf5=True):
        """Gera ou carrega dados ToA/AoA, utilizando pré-computação se disponível.
        Se prefer_hdf5=True, usa HDF5 se possível."""
        if noise_factor is None:
            noise_factor = self.optimizer.noise_factor
        if use_precomputed and not precomputed_file:
            root = tk.Tk()
            root.call('tk', 'scaling', 1.0)
            root.withdraw()
            try:
                precomputed_file = filedialog.askopenfilename(
                    title="Selecione o arquivo de dados pré-computados",
                    filetypes=[("Dados ToA/AoA", "*.h5"), ("Todos os arquivos", "*.*")],
                    initialdir=self.optimizer.precomputation_save_path
                )
            finally:
                root.destroy()
        if use_precomputed and precomputed_file and os.path.exists(precomputed_file) and not force_precompute:
            try:
                toa_data, aoa_data = self.load_precomputed_data_hdf5(precomputed_file)
                logging.info(f"Usando dados pré-computados: {len(toa_data) if toa_data else 'HDF5'} pares")
                return toa_data, aoa_data
            except Exception as e:
                logging.warning(f"Erro ao carregar dados pré-computados: {e}")
                logging.info("Prosseguindo para pré-computação...")
        else:
            if force_precompute:
                logging.info("Recomputação forçada iniciada...")
            elif not precomputed_file:
                logging.info("Nenhum arquivo de pré-computação selecionado. Iniciando cálculo...")
            else:
                logging.info(f"Arquivo selecionado '{precomputed_file}' não encontrado. Iniciando cálculo...")
        logging.info(f"Iniciando pré-computação para {len(nodes)*(len(nodes)-1)} pares...")
        return self.precompute_toa_aoa_data(G, nodes)[0:2]
