import os
import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider
import numpy as np
from itertools import combinations
from sklearn.cluster import KMeans
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import tkinter as tk
from tkinter import filedialog
import logging
import json
import pickle
import gzip
import time
import ast
from datetime import datetime

# Constantes
SPEED_OF_LIGHT = 3e8  # m/s

# Configuração básica do logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

def calc_fspl(distance_m, freq_mhz):
    """Calcula a perda de percurso no espaço livre (FSPL)."""
    if distance_m == 0:
        return 0
    distance_km = distance_m / 1000.0
    return 20 * np.log10(distance_km) + 20 * np.log10(freq_mhz) + 32.44

def get_path_and_loss(G, source, target):
    """Calcula o caminho e a perda por obstáculos entre dois nós."""
    try:
        path = nx.shortest_path(G, source=source, target=target, weight='weight')
        obstacle_loss = sum(G[p][q]['weight'] for p, q in zip(path[:-1], path[1:]))
        return path, obstacle_loss
    except (nx.NetworkXNoPath, KeyError):
        return None, float('inf')

def calc_distance_toa(toa, c=SPEED_OF_LIGHT):
    """Calcula a distância a partir do tempo de chegada (ToA)."""
    return toa * c

def calc_aoa(source, target):
    """Calcula o ângulo de chegada (AoA) entre dois nós."""
    dx = target[0] - source[0]
    dy = target[1] - source[1]
    angle_rad = np.arctan2(dy, dx)
    angle_deg = np.degrees(angle_rad)
    return angle_deg

def process_toa_aoa_chunk(
    chunk_id,
    src_nodes,
    target_nodes,
    G_data,
    distance_conversion,
    noise_factor
):
    """Processa um chunk de nós para calcular dados ToA e AoA."""
    import networkx as nx
    import numpy as np
    import logging
    from datetime import datetime
    
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
    
    total_pairs = len(src_nodes) * len(target_nodes)
    processed = 0
    last_percent = -1
    start_time = time.time()
    
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
            
            processed += 1
            percent = int((processed / total_pairs) * 100)
            
            if percent > last_percent and percent % 5 == 0:
                elapsed = time.time() - start_time
                estimated_total = elapsed / (processed / total_pairs)
                remaining = estimated_total - elapsed
                
                now = datetime.now().strftime("%H:%M:%S")
                logging.info(f"[{now}] Chunk {chunk_id}: {percent}% concluído - Tempo restante estimado: {remaining/60:.1f} min")
                last_percent = percent
    
    return toa_results, aoa_results

class RouterOptimizerAoAToA:
    def __init__(self):
        """Inicializa o otimizador de roteadores e carrega configurações."""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}

        self.rssi_threshold = config.get("rssi_threshold", -70)
        self.tx_power = config.get("tx_power", 23)
        self.freq_mhz = config.get("freq_mhz", 2400)
        self.scale_factor = config.get("scale_factor", 2)
        self.distance_conversion = config.get("distance_conversion", 0.5)
        self.max_iter = config.get("max_iter", 20)
        self.top_n = config.get("top_n", 10)
        self.num_roteadores = config.get("num_roteadores", 1)
        self.router_name = config.get("router_name", "Roteador")
        self.noise_factor = config.get("noise_factor", 0.05)

        weight_colors_cfg = config.get("weight_colors", {
            "16.67": "blue",    # Parede (concreto)
            "7": "red",         # Janela
            "6.81": "green",    # Porta
            "4": "yellow",      # MDF
            "1": "gray"         # Passagem livre
        })
        self.weight_colors = {float(k): v for k, v in weight_colors_cfg.items()}

        self.plot_save_path = config.get("plot_save_path", ".")
        self.precomputation_save_path = config.get("precomputation_save_path", self.plot_save_path)
        
        os.makedirs(self.plot_save_path, exist_ok=True)
        os.makedirs(self.precomputation_save_path, exist_ok=True)

        logging.info("RouterOptimizerAoAToA inicializado com config.json.")
        self.toa_cache = {}

    @staticmethod
    def save_precomputed_data(toa_data, aoa_data, filename):
        """Salva dados ToA e AoA pré-computados em um arquivo."""
        logging.info(f"Salvando {len(toa_data)} pares de dados em {filename}")
        
        toa_serializable = {str(k): v for k, v in toa_data.items()}
        aoa_serializable = {str(k): v for k, v in aoa_data.items()}
        
        data = {
            'toa': toa_serializable,
            'aoa': aoa_serializable,
            'timestamp': datetime.now().isoformat()
        }
        
        with gzip.open(filename, 'wb') as f:
            pickle.dump(data, f)
        
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        logging.info(f"Dados salvos. Tamanho do arquivo: {file_size_mb:.2f} MB")
        return filename

    @staticmethod
    def load_precomputed_data(filename):
        """Carrega dados ToA e AoA pré-computados de um arquivo."""
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        logging.info(f"Carregando dados pré-computados de {filename} ({file_size_mb:.2f} MB)")
        start_time = time.time()
        
        with gzip.open(filename, 'rb') as f:
            data = pickle.load(f)
        
        toa_data = {ast.literal_eval(k): v for k, v in data['toa'].items()}
        aoa_data = {ast.literal_eval(k): v for k, v in data['aoa'].items()}
        
        elapsed = time.time() - start_time
        timestamp = data.get('timestamp', 'desconhecido')
        
        logging.info(f"Dados carregados em {elapsed:.2f}s ({file_size_mb/elapsed:.2f} MB/s). "
                    f"Total de {len(toa_data):,} pares. Data de criação: {timestamp}")
        
        return toa_data, aoa_data

    def load_graph(self):
        """Carrega o grafo do usuário via diálogo Tkinter."""
        logging.info("Solicitando arquivo do grafo ao usuário...")
        root = tk.Tk()
        root.call('tk', 'scaling', 1.0)
        root.withdraw()
        try:
            graph_file = filedialog.askopenfilename(
                title="Selecione o arquivo do grafo",
                filetypes=[("Arquivos GraphML", "*.graphml"), ("Todos os arquivos", "*.*")]
            )
        finally:
            root.destroy()

        if not graph_file:
            logging.error("Nenhum arquivo selecionado.")
            raise RuntimeError("Nenhum arquivo selecionado.")
        logging.info(f"Arquivo selecionado: {graph_file}")
        G = nx.read_graphml(graph_file)
        logging.info(f"Grafo carregado com {len(G.nodes())} nós e {len(G.edges())} arestas.")
        return nx.relabel_nodes(G, {n: eval(n) for n in G.nodes()})

    def calc_fspl(self, distance_m):
        """Calcula a perda de percurso no espaço livre."""
        return calc_fspl(distance_m, self.freq_mhz)

    @lru_cache(maxsize=None)
    def get_path_and_loss(self, G, source, target):
        """Calcula o caminho e a perda por obstáculos entre dois nós."""
        return get_path_and_loss(G, source, target)
    
    def compute_rssi_for_node(self, G, node, routers, toa_data=None):
        """Calcula o melhor RSSI para um nó em relação aos roteadores."""
        best_rssi = -100.0

        if toa_data is None and not self.toa_cache:
            nodes = list(G.nodes())
            self.toa_cache, _ = self.generate_toa_aoa_data(G, nodes)

        toa_data = toa_data or self.toa_cache

        for router in routers:
            if node == router:
                continue
            path, obstacle_loss = self.get_path_and_loss(G, node, router)
            if path is None:
                continue

            toa = toa_data.get((node, router), None)
            if toa is None:
                continue

            distance = calc_distance_toa(toa)
            fspl = self.calc_fspl(distance)
            rssi = self.tx_power - fspl - obstacle_loss
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    def evaluate_coverage(self, G, routers, toa_data=None):
        """Avalia a cobertura e RSSI médio para uma configuração de roteadores."""
        logging.debug("Calculando cobertura e RSSI médio usando ToA.")
        node_list = list(G.nodes())

        if toa_data is None and not self.toa_cache:
            self.toa_cache, _ = self.generate_toa_aoa_data(G, node_list)

        toa_data = toa_data or self.toa_cache

        with ThreadPoolExecutor() as executor:
            rssi_values = list(executor.map(
                lambda node: self.compute_rssi_for_node(G, node, routers, toa_data),
                node_list
            ))
        rssi_values = np.array(rssi_values)
        coverage = np.sum(rssi_values >= self.rssi_threshold) / len(rssi_values) * 100
        valid_rssi = rssi_values[rssi_values > -100]
        avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100
        return coverage, avg_rssi, rssi_values
    
    def precompute_toa_aoa_data(self, G, nodes, filename=None, chunks=None):
        if chunks is None:
            chunks = min(os.cpu_count() or 4, 16)
        
        if filename is None:
            graph_file = getattr(G, 'graph', {}).get('filename', '')
            if graph_file:
                graph_name = os.path.splitext(os.path.basename(graph_file))[0]
            else:
                graph_name = f"grafo_{len(G.nodes())}nodes"
            
            filename = os.path.join(self.precomputation_save_path, f"{graph_name}_aoa_toa_pre-computacao.pkl.gz")
        
        total_nodes = len(nodes)
        total_pairs = total_nodes * (total_nodes - 1)
        
        logging.info(f"Iniciando pré-computação paralela para {total_pairs} pares com {chunks} workers")
        logging.info(f"Os resultados serão salvos em: {filename}")
        
        chunk_size = max(1, len(nodes) // chunks)
        node_chunks = [nodes[i:i+chunk_size] for i in range(0, len(nodes), chunk_size)]
        
        chunks = len(node_chunks)
        
        G_data = nx.node_link_data(G, edges="links")
        
        toa_data = {}
        aoa_data = {}
        
        start_time = time.time()
        with ProcessPoolExecutor(max_workers=chunks) as executor:
            futures = []
            
            for i, src_chunk in enumerate(node_chunks):
                futures.append(
                    executor.submit(
                        process_toa_aoa_chunk,
                        i+1,
                        src_chunk,
                        nodes,
                        G_data,
                        self.distance_conversion,
                        self.noise_factor
                    )
                )
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    chunk_toa, chunk_aoa = future.result()
                    toa_data.update(chunk_toa)
                    aoa_data.update(chunk_aoa)
                    
                    elapsed = time.time() - start_time
                    estimated_total = elapsed * len(futures) / i
                    remaining = estimated_total - elapsed
                    
                    logging.info(f"Processado chunk {i}/{len(futures)} - Tempo restante estimado: {remaining/60:.1f} min")
                except Exception as e:
                    logging.error(f"Erro no processamento do chunk {i}: {e}", exc_info=True)
        
        total_time = time.time() - start_time
        logging.info(f"Pré-computação concluída em {total_time/60:.2f} minutos. Total de {len(toa_data)} pares.")
        
        saved_file = self.save_precomputed_data(toa_data, aoa_data, filename)
        
        return toa_data, aoa_data, saved_file
    
    def generate_toa_aoa_data(self, G, nodes, noise_factor=None, use_precomputed=True, precomputed_file=None, force_precompute=False):
        """Gera dados de ToA e AoA com opção de usar/gerar dados pré-computados."""
        if noise_factor is None:
            noise_factor = self.noise_factor
        
        if use_precomputed and not precomputed_file:
            root = tk.Tk()
            root.call('tk', 'scaling', 1.0)
            root.withdraw()
            try:
                precomputed_file = filedialog.askopenfilename(
                    title="Selecione o arquivo de dados pré-computados",
                    filetypes=[("Dados ToA/AoA", "*.pkl.gz"), ("Todos os arquivos", "*.*")],
                    initialdir=self.precomputation_save_path
                )
            finally:
                root.destroy()
        
        if use_precomputed and precomputed_file and os.path.exists(precomputed_file) and not force_precompute:
            try:
                toa_data, aoa_data = self.load_precomputed_data(precomputed_file)
                logging.info(f"Usando dados pré-computados: {len(toa_data)} pares")
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
    
    def interactive_router_placement(self, G, num_roteadores_default):
        """Permite movimentar roteadores interativamente e calcula cobertura/RSSI ao clicar em Calcular."""

        nodes = list(G.nodes())
        min_routers = 1
        max_routers = min(20, len(nodes))
        num_roteadores = num_roteadores_default

        routers = [nodes[i] for i in np.linspace(0, len(nodes)-1, num_roteadores, dtype=int)]

        if not self.toa_cache:
            self.toa_cache, _ = self.generate_toa_aoa_data(G, nodes, use_precomputed=True)

        fig = plt.figure(figsize=(16, 12))
        fig.subplots_adjust(top=0.85, bottom=0.25)
        ax = fig.add_subplot(111)
        
        ax_button = plt.axes([0.45, 0.13, 0.1, 0.06])
        btn_calculate = Button(ax_button, 'Calcular')

        ax_slider = plt.axes([0.25, 0.05, 0.5, 0.04])
        slider_routers = Slider(
            ax_slider, 'Qtd. Roteadores', min_routers, max_routers, 
            valinit=num_roteadores, valstep=1, valfmt='%0.0f'
        )
        
        fig.suptitle("Arraste os roteadores, ajuste a quantidade e clique em Calcular para ver a cobertura", fontsize=16, y=0.96, ha='center')
        ax.set_title("")
        
        scale_factor = self.scale_factor
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black') for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6, ax=ax)
        
        nodes_plot = nx.draw_networkx_nodes(
            G, pos, node_color='lightgray',
            node_size=80, ax=ax
        )
        
        router_scat = ax.scatter(
            [r[0]*scale_factor for r in routers],
            [r[1]*scale_factor for r in routers],
            s=300, c='black', edgecolors='yellow', linewidths=2, picker=True
        )
        
        dragged_idx = [None]
        current_routers = routers.copy()

        def update_router_scatter():
            router_scat.set_offsets([[r[0]*scale_factor, r[1]*scale_factor] for r in current_routers])
            fig.canvas.draw_idle()

        def on_pick(event):
            if event.artist == router_scat:
                dragged_idx[0] = event.ind[0]
        
        def on_motion(event):
            if dragged_idx[0] is not None and event.inaxes == ax and event.xdata and event.ydata:
                x, y = event.xdata/scale_factor, event.ydata/scale_factor
                current_routers[dragged_idx[0]] = min(nodes, key=lambda n: (n[0]-x)**2 + (n[1]-y)**2)
                update_router_scatter()
        
        def on_release(event):
            dragged_idx[0] = None

        def calculate_coverage(event):
            coverage, avg_rssi, rssi_values = self.evaluate_coverage(G, current_routers, toa_data=self.toa_cache)
            nodes_plot.set_array(rssi_values)
            nodes_plot.set_cmap('RdYlGn')
            nodes_plot.set_clim(-90, -30)
            router_positions = ', '.join([str(tuple(int(x) for x in r)) for r in current_routers])
            ax.set_title(
                f"Cobertura: {coverage:.1f}% | RSSI médio: {avg_rssi:.1f} dBm\n"
                f"Posições dos roteadores: {router_positions}"
            )
            fig.canvas.draw_idle()

        def on_slider_change(val):
            nonlocal current_routers
            n = int(slider_routers.val)

            if n == len(current_routers):
                return
            if n < len(current_routers):
                current_routers = current_routers[:n]
            else:
                already = set(current_routers)
                candidates = [nodes[i] for i in np.linspace(0, len(nodes)-1, n, dtype=int)]

                for c in candidates:
                    if c not in already and len(current_routers) < n:
                        current_routers.append(c)

                if len(current_routers) < n:
                    for node in nodes:
                        if node not in current_routers:
                            current_routers.append(node)
                        if len(current_routers) == n:
                            break
            update_router_scatter()

            nodes_plot.set_array(np.full(len(nodes), np.nan))
            ax.set_title("")
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('pick_event', on_pick)
        fig.canvas.mpl_connect('motion_notify_event', on_motion)
        fig.canvas.mpl_connect('button_release_event', on_release)
        btn_calculate.on_clicked(calculate_coverage)
        slider_routers.on_changed(on_slider_change)
        
        plt.show()

if __name__ == "__main__":
    optimizer = RouterOptimizerAoAToA()
    G = optimizer.load_graph()
    num_roteadores = getattr(optimizer, "num_roteadores", 1)
    optimizer.interactive_router_placement(G, num_roteadores)