import os
import zipfile
import shutil
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from itertools import combinations
from sklearn.cluster import KMeans
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import tkinter as tk
from tkinter import filedialog
import logging

# Configuração básica do logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

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
    weight_colors
):
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

    # Funções auxiliares para cálculo
    def calc_fspl(distance_m):
        if distance_m == 0:
            return 0
        distance_km = distance_m / 1000.0
        return 20 * np.log10(distance_km) + 20 * np.log10(freq_mhz) + 32.44

    def get_path_and_loss(G, source, target):
        try:
            path = nx.shortest_path(G, source=source, target=target, weight='weight')
            obstacle_loss = sum(G[p][q]['weight'] for p, q in zip(path[:-1], path[1:]))
            return path, obstacle_loss
        except (nx.NetworkXNoPath, KeyError):
            return None, float('inf')

    def compute_rssi_for_node(G, node, routers):
        best_rssi = -100.0
        for router in routers:
            if node == router:
                continue
            path, obstacle_loss = get_path_and_loss(G, node, router)
            if path is None:
                continue
            euclidean_dist = np.hypot(node[0] - router[0], node[1] - router[1])
            fspl = calc_fspl(euclidean_dist * distance_conversion)
            rssi = tx_power - fspl - obstacle_loss
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    node_list = list(G.nodes())
    rssi_values = [compute_rssi_for_node(G, node, combo) for node in node_list]
    rssi_values = np.array(rssi_values)
    coverage = np.sum(rssi_values >= rssi_threshold) / len(rssi_values) * 100
    valid_rssi = rssi_values[rssi_values > -100]
    avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100

    # Penalidade por roteadores próximos
    from itertools import combinations
    total = 0
    for a, b in combinations(combo, 2):
        d = np.hypot(a[0] - b[0], a[1] - b[1])
        total += 1 / (d + 1e-3)
    penalty = total

    score = avg_rssi - 0.1 * penalty

    return {
        'routers': combo,
        'coverage': coverage,
        'avg_rssi': avg_rssi,
        'score': score
    }

class RouterOptimizer:
    def __init__(self):
        self.rssi_threshold = -70       #RSSI mínimo a ser considerado como cobertura
        self.tx_power = 23              # dBm || Potência do roteador
        self.freq_mhz = 2400            # MHz || Frequência do WiFI
        self.scale_factor = 2           # Escala de visualização do gráfico
        self.distance_conversion = 0.5  # Fator de conversão de unidades para metros (0.5m por unidade)
        self.max_iter = 20             # Número máximo de iterações para otimização
        self.top_n = 10                 # Número de melhores soluções a serem mantidas

        self.weight_colors = {
            16.67: 'blue',    # Parede (concreto)
            7: 'red',         # Janela
            6.81: 'green',    # Porta
            4: 'yellow',      # MDF
            1: 'gray'         # Passagem livre (corrigido de 'default' para 'gray')
        }
        logging.info("RouterOptimizer inicializado.")

    def load_graph(self):
        """Carrega o grafo do usuário via diálogo Tkinter"""
        logging.info("Solicitando arquivo do grafo ao usuário...")
        root = tk.Tk()
        root.withdraw()
        graph_file = filedialog.askopenfilename(
            title="Selecione o arquivo do grafo",
            filetypes=[("GraphML files", "*.graphml"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()  # <- Adicione esta linha para destruir o root imediatamente
        plt.close('all')  # <- Garante que o contexto gráfico do Tkinter seja fechado antes de usar matplotlib
        if not graph_file:
            logging.error("Nenhum arquivo selecionado.")
            raise RuntimeError("Nenhum arquivo selecionado.")
        logging.info(f"Arquivo selecionado: {graph_file}")
        G = nx.read_graphml(graph_file)
        logging.info(f"Grafo carregado com {len(G.nodes())} nós e {len(G.edges())} arestas.")
        return nx.relabel_nodes(G, {n: eval(n) for n in G.nodes()})

    def show_graph(self, G, title="Grafo de Navegação"):
        """Exibe o grafo com matplotlib"""
        logging.info(f"Exibindo grafo: {title}")
        scale_factor = self.scale_factor
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        plt.figure(figsize=(16, 12))

        # Desenhar arestas
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black')
                      for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6)

        # Desenhar nós
        nx.draw_networkx_nodes(
            G, pos, node_color='black',
            node_size=20, edgecolors='white', linewidths=0.5
        )

        plt.title(title)
        plt.axis('equal')
        plt.axis('off')
        plt.show()

    def calc_fspl(self, distance_m):
        """Calcula a perda de percurso no espaço livre"""
        if distance_m == 0:
            return 0
        distance_km = distance_m / 1000.0
        return 20 * np.log10(distance_km) + 20 * np.log10(self.freq_mhz) + 32.44

    @lru_cache(maxsize=None)
    def get_path_and_loss(self, G, source, target):
        """Calcula o caminho e a perda por obstáculos entre dois nós"""
        try:
            path = nx.shortest_path(G, source=source, target=target, weight='weight')
            obstacle_loss = sum(G[p][q]['weight'] for p, q in zip(path[:-1], path[1:]))
            return path, obstacle_loss
        except (nx.NetworkXNoPath, KeyError):
            return None, float('inf')

    def compute_rssi_for_node(self, G, node, routers):
        """Calcula o melhor RSSI para um nó em relação aos roteadores"""
        best_rssi = -100.0
        for router in routers:
            if node == router:
                continue  # Ignora o próprio roteador
            path, obstacle_loss = self.get_path_and_loss(G, node, router)
            if path is None:
                continue
            euclidean_dist = np.hypot(node[0] - router[0], node[1] - router[1])
            fspl = self.calc_fspl(euclidean_dist * self.distance_conversion)
            rssi = self.tx_power - fspl - obstacle_loss
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    def evaluate_coverage(self, G, routers):
        """Avalia a cobertura e RSSI médio para uma configuração de roteadores"""
        logging.debug("Calculando cobertura e RSSI médio.")
        node_list = list(G.nodes())
        with ThreadPoolExecutor() as executor:
            rssi_values = list(executor.map(
                lambda node: self.compute_rssi_for_node(G, node, routers),
                node_list
            ))
        rssi_values = np.array(rssi_values)
        coverage = np.sum(rssi_values >= self.rssi_threshold) / len(rssi_values) * 100
        valid_rssi = rssi_values[rssi_values > -100]
        avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100
        return coverage, avg_rssi, rssi_values

    def router_distance_penalty(self, routers):
        """Calcula penalização por roteadores muito próximos"""
        total = 0
        for a, b in combinations(routers, 2):
            d = np.hypot(a[0] - b[0], a[1] - b[1])
            total += 1 / (d + 1e-3)
        return total

    def find_best_routers(self, G, num_roteadores):
        """Encontra as melhores posições para os roteadores usando paralelismo"""
        logging.info(f"Iniciando busca pelas melhores posições para {num_roteadores} roteadores.")
        nodes = list(G.nodes())
        best_solutions = []

        # Seleção de nós candidatos
        centrality = nx.degree_centrality(G)
        top_central_nodes = sorted(centrality, key=centrality.get, reverse=True)[:len(nodes)//2]
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
                    self.weight_colors
                )
                for iteration in range(total_iterations)
            ]
            for idx, future in enumerate(as_completed(futures), 1):
                solution = future.result()
                best_solutions.append(solution)
                # Mantém apenas as top_n melhores
                best_solutions = sorted(best_solutions, key=lambda x: x['score'], reverse=True)[:self.top_n]
                if idx % 20 == 0 or idx == total_iterations:
                    logging.info(f"Iterações concluídas: {idx}/{total_iterations}")

        logging.info("Busca por melhores posições finalizada.")
        return best_solutions

    def _create_base_plot(self, G, routers):
        """Cria o plot base comum"""
        scale_factor = self.scale_factor
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        
        fig = plt.figure(figsize=(16, 12))
        ax = fig.add_subplot(111) if hasattr(self, 'save_solution') else plt.gca()
        
        # Desenhar arestas
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black') for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6, ax=ax)
        
        # Desenhar nós com cores de RSSI
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

    def plot_simulation(self, G, routers, coverage, avg_rssi, title=None):
        """Visualiza a simulação com cobertura RSSI"""
        if title is None:
            title = f"Cobertura: {coverage:.1f}% | RSSI Médio: {avg_rssi:.1f} dBm"
        logging.info(f"Plotando simulação: {title}")
        fig, ax = self._create_base_plot(G, routers)
        plt.colorbar(ax.collections[1], label='RSSI (dBm)')
        plt.title(title)
        plt.axis('equal')
        plt.axis('off')
        # plt.show()  # Removido para não exibir o gráfico

    def save_solution(self, solution, index, G):
        """Salva uma solução com plotagem e dados"""
        folder_name = f"solucao_{index}"
        os.makedirs(folder_name, exist_ok=True)
        logging.info(f"Salvando solução #{index} em {folder_name}")

        fig, ax = self._create_base_plot(G, solution['routers'])
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
            f.write(f"Score: {solution['score']:.2f}\n")
    
        return folder_name

    def run_optimization(self):
        """Executa o processo de otimização para múltiplas quantidades de roteadores"""
        logging.info("Iniciando processo de otimização de roteadores.")
        print("\n=== OTIMIZAÇÃO DE ROTEADORES ===")
        G = self.load_graph()
        print(f"Grafo carregado com {len(G.nodes())} nós")
        self.show_graph(G, "Grafo de Navegação Original")

        for num_roteadores in range(2, 6):  # 2 até 5 roteadores
            print(f"\n=== Testando com {num_roteadores} roteadores ===")
            print(f"Roteador: Cisco AIR-AP-2802I-Z-K9-BR")
            print(f"TX Power: {self.tx_power} dBm, Frequência: {self.freq_mhz/1000} GHz\n")

            logging.info(f"Otimização para {num_roteadores} roteadores iniciada.")
            best_solutions = self.find_best_routers(G, num_roteadores)

            zip_filename = f"melhores_solucoes_{num_roteadores}_roteadores.zip"
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for idx, solution in enumerate(best_solutions, 1):
                    print(f"\n--- Solução #{idx} ---")
                    print(f"Posições: {solution['routers']}")
                    print(f"Cobertura: {solution['coverage']:.1f}%")
                    print(f"RSSI médio: {solution['avg_rssi']:.1f} dBm")
                    print(f"Score: {solution['score']:.2f}")

                    self.plot_simulation(
                        G,
                        solution['routers'],
                        solution['coverage'],
                        solution['avg_rssi'],
                        title=f"Solução #{idx} - Cobertura: {solution['coverage']:.1f}%, RSSI Médio: {solution['avg_rssi']:.1f} dBm"
                    )
                    # plt.show()  # Removido para não exibir o gráfico

                    folder_name = self.save_solution(solution, idx, G)
                    
                    for file in os.listdir(folder_name):
                        zipf.write(
                            os.path.join(folder_name, file),
                            os.path.join(f'solucao_{idx}', file)
                        )
                    
                    shutil.rmtree(folder_name)

            logging.info(f"Resultados compactados em {zip_filename} para {num_roteadores} roteadores.")

if __name__ == "__main__":
    optimizer = RouterOptimizer()
    optimizer.run_optimization()
