import os
import zipfile
import shutil
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import random
from itertools import combinations
import tkinter as tk
from tkinter import filedialog, messagebox
import logging
import json
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
from io import StringIO

log_capture_string = StringIO()
log_capture_handler = logging.StreamHandler(log_capture_string)
log_capture_handler.setLevel(logging.INFO)
log_capture_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S'))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        log_capture_handler
    ]
)

def calc_fspl(distance_m, freq_mhz):
    """Calcula a perda de percurso no espaço livre (FSPL)."""
    # Garante distância mínima para evitar log(0)
    min_dist = 1e-3
    distance_km = max(distance_m, min_dist) / 1000.0
    return 20 * np.log10(distance_km) + 20 * np.log10(freq_mhz) + 32.44

def get_path_and_loss(G, source, target):
    """Calcula o caminho e a perda por obstáculos entre dois nós."""
    try:
        # Busca o caminho mais curto considerando o peso das arestas (obstáculos)
        path = nx.shortest_path(G, source=source, target=target, weight='weight')
        obstacle_loss = sum(G[p][q].get('weight', 0) for p, q in zip(path[:-1], path[1:]))
        return path, obstacle_loss
    except (nx.NetworkXNoPath, KeyError):
        return None, float('inf')

def calculate_fitness_worker(args):
    """
    Função de trabalho para calcular o fitness de um único indivíduo.
    Projetada para ser executada em um processo separado.
    """
    individual, G, config = args
    
    rssi_values = []
    for node in G.nodes():
        best_rssi = -100.0
        for router in individual:
            if node == router:
                best_rssi = config['tx_power']
                break
            
            path, obstacle_loss = get_path_and_loss(G, node, router)
            if path is None:
                continue

            # Calcula a distância euclidiana entre nó e roteador
            euclidean_dist = np.hypot(node[0] - router[0], node[1] - router[1])
            fspl = calc_fspl(euclidean_dist * config['distance_conversion'], config['freq_mhz'])
            
            rssi = config['tx_power'] - fspl - obstacle_loss
            if rssi > best_rssi:
                best_rssi = rssi
        rssi_values.append(best_rssi)

    rssi_values = np.array(rssi_values)
    # Calcula a cobertura percentual de nós acima do limiar de RSSI
    coverage = np.sum(rssi_values >= config['rssi_threshold']) / len(rssi_values) * 100
    valid_rssi = rssi_values[rssi_values >= config['rssi_threshold']]
    avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100
    
    penalty = 0
    # Penaliza soluções com roteadores muito próximos
    if len(individual) > 1:
        for r1, r2 in combinations(individual, 2):
            dist = np.hypot(r1[0] - r2[0], r1[1] - r2[1])
            if dist < 5:
                penalty += (1 / (dist + 1e-6))
    
    # Normalização dos critérios para cálculo do fitness
    coverage_norm = coverage / 100.0
    avg_rssi_norm = (avg_rssi - config['rssi_threshold']) / 30.0
    
    score = (config['coverage_weight'] * coverage_norm + 
             config['avg_rssi_weight'] * avg_rssi_norm -
             penalty * 0.1)
             
    return score


class RouterOptimizerConfig:
    """Classe para carregar configurações e conter funções de plotagem."""
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}

        self.rssi_threshold = config.get("rssi_threshold", -70)
        self.tx_power = config.get("tx_power", 23)
        self.freq_mhz = config.get("freq_mhz", 2400)
        self.distance_conversion = config.get("distance_conversion", 0.5)
        self.num_roteadores = config.get("num_roteadores", 1)
        self.avg_rssi_weight = config.get("avg_rssi_weight", 0.3)
        self.coverage_weight = config.get("coverage_weight", 0.7)
        self.scale_factor = config.get("scale_factor", 2)
        weight_colors_cfg = config.get("weight_colors", {"16.67": "blue", "7": "red"})
        self.weight_colors = {float(k): v for k, v in weight_colors_cfg.items()}
        self.plot_save_path = config.get("plot_save_path", ".")
        
        ga_config = config.get("genetic_algorithm", {})
        self.population_size = ga_config.get("population_size", 100)
        self.generations = ga_config.get("generations", 50)
        self.mutation_rate = ga_config.get("mutation_rate", 0.1)
        self.crossover_rate = ga_config.get("crossover_rate", 0.8)
        self.tournament_size = ga_config.get("tournament_size", 3)
        self.elitism_count = ga_config.get("elitism_count", 2)
        
        opt_config = config.get("optimization", {})
        self.penalty_weight = opt_config.get("penalty_weight", 0.1)
        self.min_router_distance = opt_config.get("min_router_distance", 5)
        self.rssi_normalization_range = opt_config.get("rssi_normalization_range", 30)
        
        parallel_config = config.get("parallel_processing", {})
        self.max_workers = parallel_config.get("max_workers", None)
        self.chunk_size = parallel_config.get("chunk_size", None)
        
        log_config = config.get("logging", {})
        self.log_level = log_config.get("level", "INFO")
        self.save_log = log_config.get("save_log", True)
        self.console_output = log_config.get("console_output", True)
        
        viz_config = config.get("visualization", {})
        self.figure_size = viz_config.get("figure_size", [16, 12])
        self.node_size = viz_config.get("node_size", 80)
        self.router_node_size = viz_config.get("router_node_size", 300)
        self.edge_width = viz_config.get("edge_width", 1.2)
        self.edge_alpha = viz_config.get("edge_alpha", 0.6)
        self.dpi = viz_config.get("dpi", 100)
        self.colormap = viz_config.get("colormap", "RdYlGn")
        self.rssi_vmin = viz_config.get("rssi_vmin", -90)
        self.rssi_vmax = viz_config.get("rssi_vmax", -30)
        
        logging.info("Configurações do otimizador carregadas.")

    def to_dict(self):
        """Retorna os parâmetros de configuração como um dicionário para paralelização."""
        return {
            'rssi_threshold': self.rssi_threshold,
            'tx_power': self.tx_power,
            'freq_mhz': self.freq_mhz,
            'distance_conversion': self.distance_conversion,
            'num_roteadores': self.num_roteadores,
            'avg_rssi_weight': self.avg_rssi_weight,
            'coverage_weight': self.coverage_weight,
            'penalty_weight': self.penalty_weight,
            'min_router_distance': self.min_router_distance,
            'rssi_normalization_range': self.rssi_normalization_range,
        }

    def load_graph(self):
        """Carrega o grafo do usuário via diálogo Tkinter."""
        logging.info("Solicitando arquivo do grafo ao usuário...")
        root = tk.Tk()
        root.withdraw()
        try:
            graph_file = filedialog.askopenfilename(
                title="Selecione o arquivo do grafo",
                filetypes=[("Arquivos GraphML", "*.graphml")]
            )
        finally:
            root.destroy()

        if not graph_file:
            raise RuntimeError("Nenhum arquivo selecionado.")
        
        G = nx.read_graphml(graph_file)
        return nx.relabel_nodes(G, {n: eval(n) for n in G.nodes()})

    def evaluate_final_solution(self, G, routers):
        """Avalia uma solução final para obter todos os detalhes (não usado no loop do AG)."""
        rssi_values = []
        for node in G.nodes():
            best_rssi = -100.0
            for router in routers:
                if node == router:
                    best_rssi = self.tx_power
                    break
                path, obstacle_loss = get_path_and_loss(G, node, router)
                if path is None:
                    continue
                euclidean_dist = np.hypot(node[0] - router[0], node[1] - router[1])
                fspl = calc_fspl(euclidean_dist * self.distance_conversion, self.freq_mhz)
                rssi = self.tx_power - fspl - obstacle_loss
                if rssi > best_rssi:
                    best_rssi = rssi
            rssi_values.append(best_rssi)
        
        rssi_values = np.array(rssi_values)
        coverage = np.sum(rssi_values >= self.rssi_threshold) / len(rssi_values) * 100
        valid_rssi = rssi_values[rssi_values >= self.rssi_threshold]
        avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100
        
        return coverage, avg_rssi, rssi_values

    def save_solution_zip(self, solution, G):
        """Salva a melhor solução encontrada em um arquivo .zip."""

        os.makedirs(self.plot_save_path, exist_ok=True)
        folder_name = "melhor_solucao_genetico_paralelo"
        os.makedirs(folder_name, exist_ok=True)
        
        routers = solution['routers']
        
        pos = {n: (n[0] * self.scale_factor, n[1] * self.scale_factor) for n in G.nodes()}
        fig, ax = plt.subplots(figsize=self.figure_size)
        edge_colors = [self.weight_colors.get(G[u][v].get('weight', 1), 'black') for u, v in G.edges()]
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=self.edge_width, alpha=self.edge_alpha, ax=ax)
        
        nodes = nx.draw_networkx_nodes(G, pos, node_color=solution['rssi_values'],
                                       cmap=self.colormap, vmin=self.rssi_vmin, vmax=self.rssi_vmax, 
                                       node_size=self.node_size, ax=ax)
        
        nx.draw_networkx_nodes(G, pos, nodelist=routers, node_color='black',
                               node_size=self.router_node_size, edgecolors='yellow', linewidths=2, ax=ax)

        plt.colorbar(nodes, label='RSSI (dBm)', ax=ax)
        ax.set_title(f"Melhor Solução - Cobertura: {solution['coverage']:.1f}%, RSSI Médio: {solution['avg_rssi']:.1f} dBm")
        ax.axis('equal')
        ax.axis('off')

        image_path = os.path.join(folder_name, "cobertura_genetico.png")
        fig.savefig(image_path, bbox_inches='tight', dpi=self.dpi)
        plt.close(fig)

        txt_path = os.path.join(folder_name, "dados_genetico.txt")
        with open(txt_path, 'w') as f:
            f.write("=== Melhor Solução (Algoritmo Genético) ===\n")
            f.write(f"Posições dos Roteadores: {routers}\n")
            f.write(f"Cobertura (> {self.rssi_threshold} dBm): {solution['coverage']:.1f}%\n")
            f.write(f"RSSI médio (em áreas cobertas): {solution['avg_rssi']:.1f} dBm\n")
            f.write(f"Pontuação de Fitness: {solution['fitness']:.4f}\n")

        log_path = os.path.join(folder_name, "log_execucao.txt")
        with open(log_path, 'w', encoding='utf-8') as f:
            log_contents = log_capture_string.getvalue()
            f.write("=== Log de Execução do Algoritmo Genético ===\n\n")
            f.write(log_contents)

        zip_filename = os.path.join(self.plot_save_path, f"solucao_genetico_paralelo_{self.num_roteadores}_roteadores.zip")    
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for file in os.listdir(folder_name):
                zipf.write(os.path.join(folder_name, file), file)
        
        shutil.rmtree(folder_name)
        logging.info(f"Solução salva e compactada em: {zip_filename}")


class GeneticOptimizer:
    """Implementa o Algoritmo Genético Paralelo."""
    def __init__(self, config_helper, G, population_size=None, generations=None, mutation_rate=None, crossover_rate=None, tournament_size=None, elitism_count=None):
        # Inicializa parâmetros do AG e configurações
        self.config = config_helper
        self.config_dict = config_helper.to_dict()
        self.G = G
        self.nodes = list(G.nodes())
        self.num_roteadores = self.config.num_roteadores
        self.population_size = population_size or self.config.population_size
        self.generations = generations or self.config.generations
        self.mutation_rate = mutation_rate or self.config.mutation_rate
        self.crossover_rate = crossover_rate or self.config.crossover_rate
        self.tournament_size = tournament_size or self.config.tournament_size
        self.elitism_count = elitism_count or self.config.elitism_count

    def _initialize_population(self):
        # Gera população inicial aleatória de indivíduos (soluções)
        population = []
        for _ in range(self.population_size):
            individual = random.sample(self.nodes, self.num_roteadores)
            population.append(individual)
        return population

    def _selection(self, population_with_fitness):
        # Seleção por torneio: escolhe o melhor entre um grupo aleatório
        tournament = random.sample(population_with_fitness, self.tournament_size)
        tournament.sort(key=lambda x: x[1], reverse=True)
        return tournament[0][0]

    def _crossover(self, parent1, parent2):
        # Realiza crossover entre dois pais para gerar dois filhos
        if random.random() > self.crossover_rate:
            return parent1, parent2
        child1, child2 = list(parent1), list(parent2)
        crossover_point = random.randint(1, self.num_roteadores - 1)
        temp1 = child1[:crossover_point] + child2[crossover_point:]
        temp2 = child2[:crossover_point] + child1[crossover_point:]
        child1 = list(dict.fromkeys(temp1))
        child2 = list(dict.fromkeys(temp2))
        # Garante que os filhos tenham o número correto de roteadores e sem repetição
        for p in parent2:
            if len(child1) < self.num_roteadores and p not in child1:
                child1.append(p)
        for p in parent1:
            if len(child2) < self.num_roteadores and p not in child2:
                child2.append(p)
        while len(child1) < self.num_roteadores:
            node = random.choice(self.nodes)
            if node not in child1:
                child1.append(node)
        while len(child2) < self.num_roteadores:
            node = random.choice(self.nodes)
            if node not in child2:
                child2.append(node)
        return child1, child2

    def _mutate(self, individual):
        # Aplica mutação: troca aleatoriamente a posição de um roteador
        mutated_individual = list(individual)
        for i in range(self.num_roteadores):
            if random.random() < self.mutation_rate:
                while True:
                    new_node = random.choice(self.nodes)
                    if new_node not in mutated_individual:
                        mutated_individual[i] = new_node
                        break
        return mutated_individual

    def run(self):
        """Executa o algoritmo genético usando ProcessPoolExecutor para paralelizar."""
        logging.info("Iniciando o Algoritmo Genético...")
        population = self._initialize_population()
        best_overall_solution = None
        best_overall_fitness = float('-inf')

        # Paraleliza o cálculo do fitness da população
        with ProcessPoolExecutor(max_workers=self.config.max_workers) as executor:
            for gen in range(self.generations):
                tasks = [(ind, self.G, self.config_dict) for ind in population]         
                logging.info(f"Geração {gen+1}/{self.generations}: Avaliando fitness da população...")
                
                # Calcula o fitness de cada indivíduo em paralelo
                fitness_scores = list(tqdm(executor.map(calculate_fitness_worker, tasks), total=len(population), desc=f"Geração {gen+1}"))
                
                population_with_fitness = list(zip(population, fitness_scores))
                population_with_fitness.sort(key=lambda x: x[1], reverse=True)

                # Atualiza a melhor solução global se necessário
                if population_with_fitness[0][1] > best_overall_fitness:
                    best_overall_fitness = population_with_fitness[0][1]
                    best_overall_solution = population_with_fitness[0][0]
                    logging.info(f"-> Nova melhor solução encontrada! Fitness: {best_overall_fitness:.4f}")

                next_population = []
                # Elitismo: mantém os melhores indivíduos
                if self.elitism_count > 0:
                    elites = [ind[0] for ind in population_with_fitness[:self.elitism_count]]
                    next_population.extend(elites)
                
                # Gera nova população por seleção, crossover e mutação
                while len(next_population) < self.population_size:
                    parent1 = self._selection(population_with_fitness)
                    parent2 = self._selection(population_with_fitness)
                    child1, child2 = self._crossover(parent1, parent2)
                    next_population.append(self._mutate(child1))
                    if len(next_population) < self.population_size:
                        next_population.append(self._mutate(child2))
                
                population = next_population

        logging.info("Otimização com Algoritmo Genético Paralelo concluída.")
        # Avalia a melhor solução encontrada
        coverage, avg_rssi, rssi_values = self.config.evaluate_final_solution(self.G, best_overall_solution)
        
        return {
            'routers': best_overall_solution,
            'fitness': best_overall_fitness,
            'coverage': coverage,
            'avg_rssi': avg_rssi,
            'rssi_values': rssi_values
        }

if __name__ == "__main__":
    try:
        config_helper = RouterOptimizerConfig()
        G = config_helper.load_graph()
        logging.info(f"Grafo carregado com {len(G.nodes())} nós e {len(G.edges())} arestas.")
        logging.info(f"Buscando a melhor posição para {config_helper.num_roteadores} roteador(es).")
        
        ga_optimizer = GeneticOptimizer(
            config_helper=config_helper,
            G=G
        )
        best_solution = ga_optimizer.run()
        
        logging.info("--- Melhor Solução Final Encontrada ---")
        logging.info(f"Posições: {best_solution['routers']}")
        logging.info(f"Cobertura: {best_solution['coverage']:.1f}%")
        logging.info(f"RSSI médio: {best_solution['avg_rssi']:.1f} dBm")
        logging.info(f"Fitness Score: {best_solution['fitness']:.4f}")
        
        config_helper.save_solution_zip(best_solution, G)

    except Exception as e:
        logging.error(f"Ocorreu um erro fatal: {e}", exc_info=True)
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("Erro", f"Ocorreu um erro:\n{e}")
        error_root.destroy()