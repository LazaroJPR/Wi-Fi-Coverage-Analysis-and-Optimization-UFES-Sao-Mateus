import os
import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
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
import zipfile
import shutil

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
    weight_colors,
    toa_data,
    aoa_data=None
):
    """Executa uma iteração de busca de roteadores em paralelo."""
    import numpy as np
    import networkx as nx
    import logging

    # Reconstrói o grafo a partir dos dados serializados
    G = nx.node_link_graph(G_data, edges="links")
    np.random.seed()  # Garante aleatoriedade em cada processo
    local_candidate_nodes = candidate_nodes_snapshot.copy()
    nodes_local = nodes.copy()
    if len(local_candidate_nodes) < num_roteadores:
        local_candidate_nodes = nodes_local

    if iteration % 10 == 0:
        logging.debug(f"Iteração {iteration}: realizando mutação nos candidatos.")
        mutation_nodes = [nodes_local[i] for i in np.random.choice(
            len(nodes_local), min(40, len(nodes_local)), replace=False)]
        local_candidate_nodes = list(set(local_candidate_nodes[:len(local_candidate_nodes)//2] + mutation_nodes))

    selected_indices = np.random.choice(
        len(local_candidate_nodes), size=num_roteadores, replace=False)
    combo = [local_candidate_nodes[i] for i in selected_indices]

    # Centraliza o cálculo de RSSI e penalidade usando métodos estáticos
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

    score = 0.6 * avg_rssi_norm + 0.4 * coverage_norm - 0.1 * penalty

    return {
        'routers': combo,
        'coverage': coverage,
        'avg_rssi': avg_rssi,
        'score': score,
        'rssi_values': rssi_values.tolist()
    }

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
        self.toa_data = {}
        self.precompute_helper = PrecomputeAoAToA(self)

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
            G, nodes, noise_factor, use_precomputed, precomputed_file, force_precompute
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

    def find_best_routers(self, G, num_roteadores):
        """Encontra as melhores posições para os roteadores usando paralelismo."""
        logging.info(f"Iniciando busca pelas melhores posições para {num_roteadores} roteadores.")
        nodes = list(G.nodes())
        best_solutions = []

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

        max_workers = os.cpu_count() or 4
        total_iterations = self.max_iter

        # Snapshot dos candidatos para evitar problemas de concorrência
        candidate_nodes_snapshot = candidate_nodes.copy()

        # Serializa o grafo para passar entre processos
        G_data = nx.node_link_data(G, edges="links")

        logging.info(f"Executando {total_iterations} iterações em paralelo com {max_workers} processos.")
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
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
                    self.weight_colors,
                    self.toa_data
                )
                for iteration in range(total_iterations)
            ]
            for idx, future in enumerate(as_completed(futures), 1):
                try:
                    solution = future.result()
                    best_solutions.append(solution)
                    # Mantém apenas as top_n melhores
                    best_solutions = sorted(best_solutions, key=lambda x: x['score'], reverse=True)[:self.top_n]
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

    def run_optimization(self):
        """Executa o processo de otimização para a quantidade de roteadores definida no config."""
        logging.info("Iniciando processo de otimização de roteadores.")
        logging.info("=== OTIMIZAÇÃO DE ROTEADORES ===")
        G = self.load_graph()
        logging.info(f"Grafo carregado com {len(G.nodes())} nós")

        nodes = list(G.nodes())
        if not self.toa_data:
            self.toa_data, self.aoa_data = self.generate_toa_aoa_data(G, nodes, use_precomputed=True)

        num_roteadores = getattr(self, "num_roteadores", None)
        if num_roteadores is None:
            # Para compatibilidade, tenta ler do config.json se não estiver como atributo
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                num_roteadores = config.get("num_roteadores", 1)
            else:
                num_roteadores = 1

        logging.info(f"=== Testando com {num_roteadores} roteadores ===")
        logging.info(f"Roteador: {self.router_name}")
        logging.info(f"Potência TX: {self.tx_power} dBm, Frequência: {self.freq_mhz/1000} GHz")

        logging.info(f"Otimização para {num_roteadores} roteadores iniciada.")
        best_solutions = self.find_best_routers(G, num_roteadores)

        # Salva o zip na pasta definida em plot_save_path
        zip_filename = os.path.join(self.plot_save_path, f"melhores_solucoes_{num_roteadores}_roteadores.zip")
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for idx, solution in enumerate(best_solutions, 1):
                logging.info(f"--- Solução #{idx} ---")
                logging.info(f"Posições: {solution['routers']}")
                logging.info(f"Cobertura: {solution['coverage']:.1f}%")
                logging.info(f"RSSI médio: {solution['avg_rssi']:.1f} dBm")

                folder_name = self.save_solution(solution, idx, G)
                
                for file in os.listdir(folder_name):
                    zipf.write(
                        os.path.join(folder_name, file),
                        os.path.join(f'solucao_{idx}', file)
                    )
                
                shutil.rmtree(folder_name)

        logging.info(f"Resultados compactados em {zip_filename} para {num_roteadores} roteadores.")
    

if __name__ == "__main__":
    optimizer = RouterOptimizerAoAToA()
    optimizer.run_optimization()
