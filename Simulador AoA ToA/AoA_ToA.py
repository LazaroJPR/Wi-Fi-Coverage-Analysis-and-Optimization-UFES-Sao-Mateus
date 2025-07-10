import os
import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np
from itertools import combinations
from sklearn.cluster import KMeans
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import tkinter as tk
from tkinter import filedialog
import logging
import json
from precompute_aoa_toa import PrecomputeAoAToA
import threading

SPEED_OF_LIGHT = 3e8  # m/s

# Configuração básica do logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

def calc_fspl(distance_m, freq_mhz):
    """Calcula a perda de percurso no espaço livre (FSPL)."""
    min_dist = 1e-3
    distance_km = max(distance_m, min_dist) / 1000.0
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

def calc_aoa_influence(aoa, expected_angle, obstacle_loss=0):
    """Calcula o impacto do AoA no RSSI para antenas omnidirecionais."""
    # Diferença angular (indica reflexão)
    angle_diff = min(abs(aoa - expected_angle), abs(360 - abs(aoa - expected_angle)))
    
    # Quanto maior a diferença angular, maior a probabilidade do sinal ter sido refletido
    reflection_indicator = min(1.0, angle_diff / 180.0)
    
    # Atenuação baseada na diferença angular e obstáculos
    # Reflexões fortes em ambientes com muitos obstáculos causam maior atenuação
    attenuation = -1.5 * reflection_indicator * (1 + obstacle_loss/30)
    
    return attenuation

def iteration_task(
    iteration,
    candidate_nodes_snapshot,
    nodes,
    num_roteadores,
    G_data,
    rssi_threshold,
    tx_power,
    freq_mhz,
    distance_conversion,
    toa_hdf5_file,
    elite_positions=None,
    no_improve_count=None,
    adapt_threshold=10,
    avg_rssi_weight=0.3,
    coverage_weight=0.7
):
    """Executa uma iteração de busca de roteadores em paralelo."""
    import numpy as np
    import networkx as nx
    import logging
    import random
    import h5py
    import ast

    # Reconstrói o grafo a partir dos dados serializados
    G = nx.node_link_graph(G_data, edges="links")
    np.random.seed()
    local_candidate_nodes = candidate_nodes_snapshot.copy()
    nodes_local = nodes.copy()
    
     # Estratégia adaptativa baseada em progresso da busca
    # Se não houve melhora por adapt_threshold iterações, força exploração
    if no_improve_count is not None and no_improve_count >= adapt_threshold:
        exploration_phase = True
        phase_str = "Exploração (forçada por estagnação)"
    else:
        block_size = 30
        exploration_block = int(block_size / 3)
        block_pos = iteration % block_size
        if block_pos < exploration_block:
            exploration_phase = True
            phase_str = "exploração"
        else:
            exploration_phase = False
            phase_str = "intensificação"

    if len(local_candidate_nodes) < num_roteadores:
        local_candidate_nodes = nodes_local

    # Estratégia de perturbação baseada na fase da busca
    block_start = (iteration // block_size) * block_size
    if exploration_phase:
        block_end = block_start + exploration_block
    else:
        block_end = block_start + block_size
        block_start = block_start + exploration_block

    if iteration == block_start:
        logging.info(
            f"Iteração {iteration}/{block_end - 1}: Fase de {phase_str}."
        )
        if exploration_phase:
            # Fase de exploração: mais diversidade
            mutation_size = min(40, len(nodes_local))
            mutation_nodes = [nodes_local[i] for i in np.random.choice(
                len(nodes_local), mutation_size, replace=False)]
            local_candidate_nodes = list(set(local_candidate_nodes[:len(local_candidate_nodes)//2] + mutation_nodes))
        else:
            # Fase de intensificação: aproveitar as melhores posições encontradas
            if elite_positions and len(elite_positions) > 0:
                elite_selection = random.sample(elite_positions, min(num_roteadores//2 + 1, len(elite_positions))
                )
                neighborhood_nodes = []
                for pos in elite_selection:
                    # Encontra nós próximos no grafo (vizinhança)
                    neighbors = []
                    for node in nodes_local:
                        dist = np.hypot(node[0] - pos[0], node[1] - pos[1])
                        if 0 < dist < 10:
                            neighbors.append(node)
                    if neighbors:
                        neighborhood_nodes.extend(random.sample(neighbors, min(3, len(neighbors))))
                
                # Adiciona alguns nós aleatórios para manter diversidade
                random_nodes = [nodes_local[i] for i in np.random.choice(
                    len(nodes_local), min(20, len(nodes_local)), replace=False)]
                
                # Combina as diferentes fontes de nós
                local_candidate_nodes = list(set(elite_selection + neighborhood_nodes + random_nodes))
            else:
                # Se não tiver elite, usa estratégia padrão
                mutation_nodes = [nodes_local[i] for i in np.random.choice(
                    len(nodes_local), min(40, len(nodes_local)), replace=False)]
                local_candidate_nodes = list(set(local_candidate_nodes[:len(local_candidate_nodes)//2] + mutation_nodes))

    selected_indices = np.random.choice(
        len(local_candidate_nodes), size=num_roteadores, replace=False)
    combo = [local_candidate_nodes[i] for i in selected_indices]

    # Se temos soluções elite e não estamos na fase de exploração, às vezes usamos uma combinação de posições elite
    if elite_positions and not exploration_phase and random.random() < 0.3 and len(elite_positions) > 0:
        available_elite = elite_positions.copy()
        if len(available_elite) >= num_roteadores:
            combo = random.sample(available_elite, num_roteadores)
        else:
            combo = available_elite + [local_candidate_nodes[i] for i in np.random.choice(
                len(local_candidate_nodes), size=num_roteadores-len(available_elite), replace=False)]

    # Função para ler ToA/AoA de arquivo HDF5 sob demanda
    def get_toa_aoa_from_hdf5(hdf5_file, pairs):
        toa_data = {}
        aoa_data = {}
        import pickle
        import threading
        if not hasattr(get_toa_aoa_from_hdf5, "_index_cache"):
            get_toa_aoa_from_hdf5._index_cache = {}
            get_toa_aoa_from_hdf5._lock = threading.Lock()
        idx_path = hdf5_file + ".pkl"
        with get_toa_aoa_from_hdf5._lock:
            if idx_path not in get_toa_aoa_from_hdf5._index_cache:
                with open(idx_path, "rb") as f:
                    get_toa_aoa_from_hdf5._index_cache[idx_path] = pickle.load(f)
        idx_dict = get_toa_aoa_from_hdf5._index_cache[idx_path]
        toa_index = idx_dict["toa"]
        aoa_index = idx_dict["aoa"]
        import h5py
        with h5py.File(hdf5_file, "r") as f:
            toa_grp = f["toa"]
            aoa_grp = f["aoa"]
            for src, tgt in pairs:
                key = str((src, tgt))
                idx = toa_index.get(key)
                if idx is not None:
                    toa_data[(src, tgt)] = toa_grp['values'][idx]
                idx = aoa_index.get(key)
                if idx is not None:
                    aoa_data[(src, tgt)] = aoa_grp['values'][idx]
        return toa_data, aoa_data

    # Lista de pares necessários para esta iteração
    node_list = list(G.nodes())
    pairs = []
    for node in node_list:
        for router in combo:
            if node != router:
                pairs.append((node, router))
    toa_data, aoa_data = get_toa_aoa_from_hdf5(toa_hdf5_file, pairs)

    rssi_values = RouterOptimizerAoAToA.compute_rssi_for_nodes_static(
        G, combo, tx_power, freq_mhz, distance_conversion, toa_data, aoa_data,
        rssi_func=RouterOptimizerAoAToA.compute_rssi_for_node_static
    )
    
    rssi_values = np.array(rssi_values)
    coverage = np.sum(rssi_values >= rssi_threshold) / len(rssi_values) * 100
    valid_rssi = rssi_values[rssi_values > -100]
    avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100

    penalty = RouterOptimizerAoAToA.router_distance_penalty_static(combo)

    # Normaliza cobertura e RSSI médio para [0,1]
    coverage_norm = coverage / 100.0
    avg_rssi_norm = (avg_rssi + 90) / 60

    score = avg_rssi_weight * avg_rssi_norm + coverage_weight * coverage_norm - 0.1 * penalty

    return {
        'routers': combo,
        'coverage': coverage,
        'avg_rssi': avg_rssi,
        'score': score,
        'rssi_values': rssi_values.tolist()
    }

class SolutionMemory:
    """Armazena e gerencia as melhores soluções encontradas durante o processo de otimização."""
    def __init__(self, max_size=10):
        self.solutions = []
        self.max_size = max_size
        self._lock = threading.RLock()

    def add_solution(self, solution):
        """Adiciona uma solução à memória, mantendo apenas as melhores."""
        with self._lock:
            self.solutions.append(solution)
            self.solutions = sorted(self.solutions, key=lambda x: x['score'], reverse=True)[:self.max_size]

    def get_best_solutions(self, n=None):
        """Retorna as n melhores soluções da memória."""
        with self._lock:
            n = n or self.max_size
            return self.solutions[:min(n, len(self.solutions))]
    
    def get_best_router_positions(self, n=None):
        """Retorna as posições dos roteadores das n melhores soluções."""
        with self._lock:
            solutions = self.get_best_solutions(n)
            return [sol['routers'] for sol in solutions]
    
    def get_elite_positions(self):
        """Retorna um conjunto de posições combinadas das melhores soluções."""
        with self._lock:
            if not self.solutions:
                return []
            all_positions = []
            for sol in self.solutions[:min(3, len(self.solutions))]:
                all_positions.extend(sol['routers'])
            return list(set(all_positions))

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
        self.max_workers = config.get("max_workers", os.cpu_count() or 2)
        self.avg_rssi_weight = config.get("avg_rssi_weight", 0.3)
        self.coverage_weight = config.get("coverage_weight", 0.7)

        weight_colors_cfg = config.get("weight_colors", {
            "16.67": "blue",    # Parede (concreto)
            "7": "red",         # Janela
            "6.81": "green",    # Porta
            "4": "yellow",      # MDF
            "1": "gray"         # Passagem livre
        })
        self.weight_colors = {float(k): v for k, v in weight_colors_cfg.items()}

        self.plot_save_path = config.get("plot_save_path", ".")
        self.precomputation_save_path = self.plot_save_path
        
        os.makedirs(self.plot_save_path, exist_ok=True)
        os.makedirs(self.precomputation_save_path, exist_ok=True)

        logging.info("RouterOptimizerAoAToA inicializado com config.json.")
        self.toa_cache = {}
        self.toa_data = {}
        self.precompute_helper = PrecomputeAoAToA(self)
        self.solution_memory = SolutionMemory(max_size=20)

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
    
    @staticmethod
    def compute_rssi_for_nodes_static(G, routers, tx_power, freq_mhz, distance_conversion, toa_data, aoa_data=None, rssi_func=None):
        """Calcula o melhor RSSI para todos os nós do grafo usando ToA e AoA."""
        if rssi_func is None:
            rssi_func = RouterOptimizerAoAToA.compute_rssi_for_node_static
        node_list = list(G.nodes())
        return [
            rssi_func(G, node, routers, tx_power, freq_mhz, distance_conversion, toa_data, aoa_data)
            for node in node_list
        ]

    @staticmethod
    def compute_rssi_for_node_static(G, node, routers, tx_power, freq_mhz, distance_conversion, toa_data, aoa_data=None):
        """Calcula o melhor RSSI para um nó em relação aos roteadores usando ToA e AoA."""
        best_rssi = -100.0

        for router in routers:
            if node == router:
                continue
            path, obstacle_loss = get_path_and_loss(G, node, router)
            if path is None:
                continue

            toa = toa_data.get((node, router), None)
            if toa is None:
                continue

            # Calcula o ângulo esperado (linha reta entre nós)
            dx = node[0] - router[0]
            dy = node[1] - router[1]
            expected_angle = (np.degrees(np.arctan2(dy, dx)) + 180) % 360

            # Aplica o impacto do AoA se disponível
            aoa_factor = 0
            if aoa_data:
                aoa = aoa_data.get((router, node), None)
                if aoa is not None:
                    aoa_factor = calc_aoa_influence(aoa, expected_angle, obstacle_loss)

            distance = max(calc_distance_toa(toa), distance_conversion)
            fspl = calc_fspl(distance, freq_mhz)
            
            # Adicionar o fator de AoA ao cálculo do RSSI
            rssi = tx_power - fspl - obstacle_loss + aoa_factor
            
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    def compute_rssi_for_node(self, G, node, routers, toa_data, aoa_data=None):
        """Calcula o melhor RSSI para um nó em relação aos roteadores."""
        return RouterOptimizerAoAToA.compute_rssi_for_node_static(
            G, node, routers, self.tx_power, self.freq_mhz, self.distance_conversion, toa_data, aoa_data
        )

    def evaluate_coverage(self, G, routers, toa_data=None, aoa_data=None):
        """Avalia a cobertura e RSSI médio para uma configuração de roteadores."""
        logging.debug("Calculando cobertura e RSSI médio usando ToA e AoA.")
        node_list = list(G.nodes())

        if toa_data is None and not self.toa_data:
            self.toa_data, self.aoa_data = self.generate_toa_aoa_data(G, node_list)

        toa_data = toa_data or self.toa_data
        aoa_data = aoa_data or getattr(self, 'aoa_data', {})

        with ThreadPoolExecutor() as executor:
            rssi_values = list(executor.map(
                lambda node: self.compute_rssi_for_node(G, node, routers, toa_data, aoa_data),
                node_list
            ))
        rssi_values = np.array(rssi_values)
        coverage = np.sum(rssi_values >= self.rssi_threshold) / len(rssi_values) * 100
        valid_rssi = rssi_values[rssi_values > -100]
        avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100
        return coverage, avg_rssi, rssi_values
    
    def precompute_toa_aoa_data(self, G, nodes, filename=None, chunks=None):
        return self.precompute_helper.precompute_toa_aoa_data(G, nodes, filename, chunks)

    def generate_toa_aoa_data(self, G, nodes, noise_factor=None, use_precomputed=True, precomputed_file=None, force_precompute=False):
        """Gera dados de ToA e AoA com opção de usar/gerar dados pré-computados."""
        return self.precompute_helper.generate_toa_aoa_data(
            G, nodes, noise_factor, use_precomputed, precomputed_file, force_precompute, prefer_hdf5=True
        )
    
    @staticmethod
    def router_distance_penalty_static(routers):
        """Calcula penalização por roteadores muito próximos (static, para uso externo)."""
        total = 0
        for a, b in combinations(routers, 2):
            d = np.hypot(a[0] - b[0], a[1] - b[1])
            total += 1 / (d + 1e-3)
        return total

    def router_distance_penalty(self, routers):
        """Calcula penalização por roteadores muito próximos."""
        return RouterOptimizerAoAToA.router_distance_penalty_static(routers)

    def find_best_routers(self, G, num_roteadores, cancel_event=None):
        """Encontra as melhores posições para os roteadores usando paralelismo."""
        logging.info(f"Iniciando busca pelas melhores posições para {num_roteadores} roteadores.")
        nodes = list(G.nodes())
        best_solutions = []

        if cancel_event and cancel_event.is_set():
            logging.info("Busca cancelada pelo usuário.")
            return best_solutions

        if not self.toa_data or not hasattr(self, 'aoa_data') or not self.aoa_data:
            logging.info("Gerando dados ToA/AoA para a otimização.")
            self.toa_data, self.aoa_data, self.toa_hdf5_file = self.generate_toa_aoa_data(G, nodes, use_precomputed=True)
        else:
            logging.info("Usando dados ToA/AoA pré-existentes/pré-calculados.")
            self.toa_hdf5_file = getattr(self.precompute_helper, 'last_hdf5_file', None)

        if cancel_event and cancel_event.is_set():
            logging.info("Busca cancelada pelo usuário.")
            return best_solutions

        # Seleção de nós candidatos
        centralidade = nx.degree_centrality(G)
        top_central_nodes = sorted(centralidade, key=centralidade.get, reverse=True)[:len(nodes)//2]
        _, _, initial_rssi_values = self.evaluate_coverage(G, [])
        weak_nodes = [node for node, rssi in zip(nodes, initial_rssi_values)
                     if rssi < self.rssi_threshold]
        candidate_nodes = list(set(top_central_nodes) | set(weak_nodes))

        # Clusterização para posições iniciais
        positions = np.array([[x, y] for (x, y) in nodes])
        kmeans = KMeans(n_clusters=num_roteadores, n_init='auto', random_state=42)
        kmeans.fit(positions)
        centroids = [tuple(map(float, c)) for c in kmeans.cluster_centers_]
        centroid_nearest_nodes = [min(nodes, key=lambda n: np.linalg.norm(np.array(n) - np.array(c)))
                                for c in centroids]
        candidate_nodes = list(set(candidate_nodes + centroid_nearest_nodes))

        total_iterations = self.max_iter

        # Snapshot dos candidatos para evitar problemas de concorrência
        candidate_nodes_snapshot = candidate_nodes.copy()

        # Serializa o grafo para passar entre processos
        G_data = nx.node_link_data(G, edges="links")

        logging.info(f"Executando {total_iterations} iterações em paralelo com {self.max_workers} processos.")
        no_improve_count = 0
        best_score = float('-inf')

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for iteration in range(total_iterations):
                if cancel_event and cancel_event.is_set():
                    logging.info("Busca cancelada pelo usuário durante as iterações.")
                    break
                    
                futures.append(
                    executor.submit(
                        iteration_task,
                        iteration,
                        candidate_nodes_snapshot,
                        nodes,
                        num_roteadores,
                        G_data,
                        self.rssi_threshold,
                        self.tx_power,
                        self.freq_mhz,
                        self.distance_conversion,
                        self.toa_hdf5_file,
                        elite_positions=self.solution_memory.get_elite_positions(),
                        no_improve_count=no_improve_count,
                        avg_rssi_weight=self.avg_rssi_weight,
                        coverage_weight=self.coverage_weight
                    )
                )
            for idx, future in enumerate(as_completed(futures), 1):
                if cancel_event and cancel_event.is_set():
                    logging.info("Busca cancelada pelo usuário durante processamento dos resultados.")
                    break
                    
                try:
                    solution = future.result()
                    self.solution_memory.add_solution(solution)
                    best_solutions.append(solution)
                    # Mantém apenas as top_n melhores
                    best_solutions = sorted(best_solutions, key=lambda x: x['score'], reverse=True)[:self.top_n]
                    if solution['score'] > best_score:
                        best_score = solution['score']
                        no_improve_count = 0
                    else:
                        no_improve_count += 1
                    if idx % 20 == 0 or idx == total_iterations:
                        logging.info(f"Iterações concluídas: {idx}/{total_iterations}")
                except Exception as e:
                    logging.error(f"Erro durante a execução paralela na iteração {idx}: {e}", exc_info=True)

        logging.info("Busca por melhores posições finalizada.")
        return best_solutions

    def _create_base_plot(self, G, routers, rssi_values=None):
        """Cria o plot base comum."""
        scale_factor = self.scale_factor
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        
        fig = plt.figure(figsize=(16, 12))
        ax = fig.add_subplot(111) if hasattr(self, 'save_solution') else plt.gca()
        
        # Desenhar arestas
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black') for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6, ax=ax)
        
        # Desenhar nós com cores de RSSI
        if rssi_values is None:
            _, _, rssi_values = self.evaluate_coverage(G, routers)
        nodes = nx.draw_networkx_nodes(
            G, pos, node_color=rssi_values,
            cmap='RdYlGn', vmin=-90, vmax=-30,
            node_size=80, ax=ax
        )
        
        # Destacar roteadores
        nx.draw_networkx_nodes(
            G, pos, nodelist=routers,
            node_color='black', node_size=300,
            edgecolors='yellow', linewidths=2, ax=ax
        )
        
        return fig, ax

    def save_solution(self, solution, index, G):
        """Salva uma solução com plotagem e dados."""
        folder_name = f"solucao_{index}"
        os.makedirs(folder_name, exist_ok=True)
        logging.info(f"Salvando solução #{index} em {folder_name}")

        # Usa os valores de RSSI já calculados
        rssi_values = np.array(solution.get('rssi_values'))
        fig, ax = self._create_base_plot(G, solution['routers'], rssi_values)
        plt.colorbar(ax.collections[1], label='RSSI (dBm)', ax=ax)
        ax.set_title(f"Solução #{index} - Cobertura: {solution['coverage']:.1f}%, RSSI Médio: {solution['avg_rssi']:.1f} dBm")
        ax.axis('equal')
        ax.axis('off')

        image_path = os.path.join(folder_name, f"cobertura_{index}.png")
        fig.savefig(image_path, bbox_inches='tight', facecolor='w', dpi=100)
        plt.close(fig)

        txt_path = os.path.join(folder_name, f"dados_{index}.txt")
        with open(txt_path, 'w') as f:
            f.write(f"=== Solução #{index} ===\n")
            f.write(f"Posições: {solution['routers']}\n")
            f.write(f"Cobertura: {solution['coverage']:.1f}%\n")
            f.write(f"RSSI médio: {solution['avg_rssi']:.1f} dBm\n")
    
        return folder_name

    def interactive_router_placement(self, G, num_roteadores_default, master=None, controls_callback=None):
        """Permite movimentar roteadores interativamente e calcula cobertura/RSSI ao clicar em Calcular."""
        is_standalone = master is None
        if is_standalone:
            matplotlib.use('TkAgg')
            root = tk.Tk()
            root.title("Simulador Interativo - AoA/ToA")
            master = root
        
        nodes = list(G.nodes())
        min_routers = 1
        max_routers = min(10, len(nodes))
        
        routers = [nodes[i] for i in np.linspace(0, len(nodes)-1, num_roteadores_default, dtype=int)]
        
        fig = plt.figure(figsize=(12, 9))
        canvas = FigureCanvasTkAgg(fig, master=master)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(master)
        toolbar_frame.pack(side=tk.TOP, fill=tk.X)
        toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
        toolbar.update()

        ax = fig.add_subplot(111)
        fig.subplots_adjust(top=0.85, bottom=0.1)
        ax.set_aspect('equal')
        
        router_count_var = tk.IntVar(value=num_roteadores_default)
        calc_button_ref = [None]

        title_text = "Simulador Interativo - AoA/ToA"
        subtitle_text = "Arraste os roteadores, ajuste a quantidade e clique em Calcular para ver a cobertura"

        def get_node_radius_px():
            trans = ax.transData.transform
            node_pos_px = {n: trans((n[0]*self.scale_factor, n[1]*self.scale_factor)) for n in G.nodes()}
            edge_lengths = [
                np.linalg.norm(np.array(node_pos_px[u]) - np.array(node_pos_px[v]))
                for u, v in G.edges()
            ]
            return 0.8 * min(edge_lengths) if edge_lengths else 10

        def update_fonts(event=None):
            w, h = fig.get_size_inches()*fig.dpi
            base = min(w, h)
            title_fontsize = max(16, base // 40)
            subtitle_fontsize = max(12, base // 70)
            label_fontsize = max(10, base // 90)

            if hasattr(fig, '_main_title'):
                fig._main_title.set_fontsize(title_fontsize)
            if hasattr(fig, '_subtitle'):
                fig._subtitle.set_fontsize(subtitle_fontsize)
            if hasattr(fig, '_coverage_title') and fig._coverage_title is not None:
                fig._coverage_title.set_fontsize(label_fontsize)
            ax.title.set_fontsize(label_fontsize)

            node_radius_px = get_node_radius_px()
            node_size = np.pi * (node_radius_px ** 2)
            nodes_plot.set_sizes([node_size] * len(G.nodes()))

            if hasattr(fig, '_colorbar') and hasattr(fig._colorbar, 'set_label'):
                fig._colorbar.set_label('RSSI (dBm)', fontsize=label_fontsize)
            fig.canvas.draw_idle()

        fig._main_title = fig.suptitle(title_text, fontsize=22, y=0.98, ha='center', fontweight='bold')
        fig._subtitle = fig.text(0.5, 0.94, subtitle_text, fontsize=14, ha='center', va='top')
        fig._coverage_title = None

        ax.set_title("")

        scale_factor = self.scale_factor
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black') for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6, ax=ax)
        
        node_radius_px = 10
        node_size = np.pi * (node_radius_px ** 2)
        nodes_plot = nx.draw_networkx_nodes(
            G, pos, node_color='lightgray',
            node_size=node_size, ax=ax, alpha=0
        )
        nodes_plot.set_zorder(1)
        
        router_scat = ax.scatter(
            [r[0]*scale_factor for r in routers],
            [r[1]*scale_factor for r in routers],
            s=300, c='black', edgecolors='yellow', linewidths=2, picker=True
        )
        router_scat.set_zorder(2)
        
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

        def calculate_coverage():
            """Inicia o cálculo da cobertura em uma thread separada para não bloquear a GUI."""
            if not calc_button_ref[0]:
                return
                
            # Atualiza o botão para estado de loading
            calc_button = calc_button_ref[0]
            original_text = calc_button.cget('text')
            calc_button.config(text="Calculando...", state='disabled')
            if master.winfo_exists():
                master.update_idletasks()

            def calculation_thread():
                try:
                    # Usa os dados ToA/AoA já carregados
                    coverage, avg_rssi, rssi_values = self.evaluate_coverage(G, current_routers, self.toa_data, getattr(self, 'aoa_data', {}))
                    
                    def update_gui():
                        nodes_plot.set_array(rssi_values)
                        nodes_plot.set_cmap('RdYlGn')
                        nodes_plot.set_clim(-90, -30)
                        nodes_plot.set_alpha(1.0)
                        router_positions = ', '.join([str(tuple(int(x) for x in r)) for r in current_routers])
                        
                        if fig._coverage_title is not None:
                            fig._coverage_title.remove()

                        fig._coverage_title = fig.text(
                            0.5, 0.89,
                            f"Cobertura: {coverage:.1f}% | RSSI médio: {avg_rssi:.1f} dBm\n"
                            f"Posições dos roteadores: {router_positions}",
                            fontsize=max(10, min(fig.get_size_inches()*fig.dpi)//90),
                            ha='center', va='top'
                        )
                        ax.set_title("")

                        if not hasattr(fig, '_colorbar') or fig._colorbar is None:
                            cax = fig.add_axes([0.92, 0.1, 0.015, 0.75])
                            fig._colorbar = plt.colorbar(nodes_plot, cax=cax, label='RSSI (dBm)')
                            fig._colorbar.set_label('RSSI (dBm)', fontsize=max(10, min(fig.get_size_inches()*fig.dpi)//90))
                        else:
                            fig._colorbar.update_normal(nodes_plot)
                        
                        if calc_button_ref[0]:
                            calc_button_ref[0].config(text=original_text, state='normal')
                        fig.canvas.draw_idle()

                    if master.winfo_exists():
                        master.after(0, update_gui)
                        
                except Exception as e:
                    def show_error():
                        if calc_button_ref[0]:
                            calc_button_ref[0].config(text=original_text, state='normal')
                        print(f"Erro no cálculo: {e}")
                    
                    if master.winfo_exists():
                        master.after(0, show_error)

            threading.Thread(target=calculation_thread, daemon=True).start()

        def on_slider_change(val):
            nonlocal current_routers
            n = int(router_count_var.get())

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
            nodes_plot.set_alpha(0)
            ax.set_title("")
            if fig._coverage_title is not None:
                fig._coverage_title.remove()
                fig._coverage_title = None
            fig.canvas.draw_idle()

        # Conecta os eventos do matplotlib
        fig.canvas.mpl_connect('pick_event', on_pick)
        fig.canvas.mpl_connect('motion_notify_event', on_motion)
        fig.canvas.mpl_connect('button_release_event', on_release)
        fig.canvas.mpl_connect('resize_event', update_fonts)
        
        # Callback para criar os controles na interface principal
        if controls_callback:
            controls_callback(
                router_count_var, 
                min_routers, 
                max_routers, 
                on_slider_change, 
                calculate_coverage, 
                calc_button_ref
            )

        update_fonts()

        if is_standalone:
            controls_frame = tk.Frame(master)
            controls_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
            
            slider_frame = tk.Frame(controls_frame)
            slider_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            tk.Label(slider_frame, text="Qtd. Roteadores:", font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=(0, 5))
            router_slider = tk.Scale(slider_frame, from_=min_routers, to=max_routers, 
                                    orient=tk.HORIZONTAL, variable=router_count_var, 
                                    length=200, font=('Segoe UI', 9))
            router_slider.pack(side=tk.LEFT, padx=(0, 20))
            
            calc_button = tk.Button(controls_frame, text="Calcular Cobertura", 
                                   font=('Segoe UI', 10, 'bold'), 
                                   bg='#007acc', fg='white', 
                                   activebackground='#005a9e', 
                                   relief='flat', padx=20, pady=5,
                                   cursor='hand2')
            calc_button.pack(side=tk.RIGHT, padx=(10, 0))
            
            calc_button_ref[0] = calc_button
            calc_button.config(command=calculate_coverage)
            router_slider.config(command=on_slider_change)
            
            master.mainloop()

    def run_optimization(self, cancel_event=None):
        """Executa o processo de otimização para a quantidade de roteadores definida no config."""
        matplotlib.use('Agg')
        logging.info("Iniciando processo de otimização de roteadores.")
        logging.info("=== OTIMIZAÇÃO DE ROTEADORES ===")
        
        if hasattr(self, 'precompute_helper') and self.precompute_helper:
            self.precompute_helper.cancel_event = cancel_event
        
        if cancel_event and cancel_event.is_set():
            logging.info("Otimização cancelada pelo usuário.")
            return
            
        try:
            G = self.load_graph()
        except RuntimeError:
            logging.error("Otimização cancelada: nenhum grafo selecionado.")
            return

        if not G:
            logging.error("Nenhum grafo foi carregado.")
            return

        if cancel_event and cancel_event.is_set():
            logging.info("Otimização cancelada pelo usuário.")
            return

        nodes = list(G.nodes())
        logging.info(f"Grafo carregado: {len(nodes)} nós, {len(G.edges())} arestas")

        self.toa_data, self.aoa_data, _ = self.generate_toa_aoa_data(G, nodes)

        if cancel_event and cancel_event.is_set():
            logging.info("Otimização cancelada pelo usuário.")
            return

        if not self.toa_data:
            logging.error("Erro ao gerar/carregar dados ToA/AoA")
            return

        logging.info(f"Dados ToA/AoA carregados: {len(self.toa_data)} pares")

        best_solutions = self.find_best_routers(G, self.num_roteadores, cancel_event)

        if cancel_event and cancel_event.is_set():
            logging.info("Otimização cancelada pelo usuário.")
            return

        if not best_solutions:
            logging.warning("Nenhuma solução encontrada")
            return

        logging.info(f"Encontradas {len(best_solutions)} soluções")

        for i, solution in enumerate(best_solutions[:self.top_n], 1):
            if cancel_event and cancel_event.is_set():
                logging.info("Otimização cancelada pelo usuário.")
                return
            self.save_solution(solution, i, G)

        logging.info("=== OTIMIZAÇÃO CONCLUÍDA ===")