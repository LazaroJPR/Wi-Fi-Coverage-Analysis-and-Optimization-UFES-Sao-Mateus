import os
import zipfile
import shutil
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
    rssi_values = RouterOptimizer.compute_rssi_for_nodes_static(
        G, combo, tx_power, freq_mhz, distance_conversion, rssi_func=RouterOptimizer.compute_rssi_for_node_static
    )
    rssi_values = np.array(rssi_values)
    coverage = np.sum(rssi_values >= rssi_threshold) / len(rssi_values) * 100
    valid_rssi = rssi_values[rssi_values > -100]
    avg_rssi = np.mean(valid_rssi) if len(valid_rssi) > 0 else -100

    penalty = RouterOptimizer.router_distance_penalty_static(combo)

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

class RouterOptimizer:
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

        weight_colors_cfg = config.get("weight_colors", {
            "16.67": "blue",    # Parede (concreto)
            "7": "red",         # Janela
            "6.81": "green",    # Porta
            "4": "yellow",      # MDF
            "1": "gray"         # Passagem livre
        })
        self.weight_colors = {float(k): v for k, v in weight_colors_cfg.items()}

        self.plot_save_path = config.get("plot_save_path", ".")

        logging.info("RouterOptimizer inicializado com config.json.")

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
    def compute_rssi_for_node_static(G, node, routers, tx_power, freq_mhz, distance_conversion):
        """Calcula o melhor RSSI para um nó em relação aos roteadores (static, para uso externo)."""
        best_rssi = -100.0
        for router in routers:
            if node == router:
                continue
            path, obstacle_loss = get_path_and_loss(G, node, router)
            if path is None:
                continue
            euclidean_dist = np.hypot(node[0] - router[0], node[1] - router[1])
            fspl = calc_fspl(euclidean_dist * distance_conversion, freq_mhz)
            rssi = tx_power - fspl - obstacle_loss
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    @staticmethod
    def compute_rssi_for_nodes_static(G, routers, tx_power, freq_mhz, distance_conversion, rssi_func=None):
        """Calcula RSSI para todos os nós do grafo usando função fornecida."""
        if rssi_func is None:
            rssi_func = RouterOptimizer.compute_rssi_for_node_static
        node_list = list(G.nodes())
        return [rssi_func(G, node, routers, tx_power, freq_mhz, distance_conversion) for node in node_list]

    @staticmethod
    def router_distance_penalty_static(routers):
        """Calcula penalização por roteadores muito próximos (static, para uso externo)."""
        total = 0
        for a, b in combinations(routers, 2):
            d = np.hypot(a[0] - b[0], a[1] - b[1])
            total += 1 / (d + 1e-3)
        return total

    def compute_rssi_for_node(self, G, node, routers):
        """Calcula o melhor RSSI para um nó em relação aos roteadores."""
        return RouterOptimizer.compute_rssi_for_node_static(
            G, node, routers, self.tx_power, self.freq_mhz, self.distance_conversion
        )

    def evaluate_coverage(self, G, routers):
        """Avalia a cobertura e RSSI médio para uma configuração de roteadores."""
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
        """Calcula penalização por roteadores muito próximos."""
        return RouterOptimizer.router_distance_penalty_static(routers)

    def interactive_router_placement(self, G, num_roteadores_default):
        """Permite movimentar roteadores interativamente e calcula cobertura/RSSI ao clicar em Calcular."""

        nodes = list(G.nodes())
        min_routers = 1
        max_routers = min(20, len(nodes))
        num_roteadores = num_roteadores_default

        routers = [nodes[i] for i in np.linspace(0, len(nodes)-1, num_roteadores, dtype=int)]
        
        fig = plt.figure(figsize=(16, 12))
        ax = fig.add_subplot(111)
        ax.set_aspect('equal')
        fig.subplots_adjust(top=0.85, bottom=0.25)

        title_text = "Simulador Interativo - Distância Euclidiana"
        subtitle_text = "Arraste os roteadores, ajuste a quantidade e clique em Calcular para ver a cobertura"

        # Função para calcular o raio dos nós baseado no tamanho da menor aresta em pixels
        def get_node_radius_px():
            trans = ax.transData.transform
            node_pos_px = {n: trans((n[0]*scale_factor, n[1]*scale_factor)) for n in G.nodes()}
            edge_lengths = [
                np.linalg.norm(np.array(node_pos_px[u]) - np.array(node_pos_px[v]))
                for u, v in G.edges()
            ]
            if edge_lengths:
                min_edge_px = min(edge_lengths)
                return 0.8 * min_edge_px
            else:
                return 10

        # Função para atualizar tamanhos de fonte e dos nós dinamicamente
        def update_fonts(event=None):
            w, h = fig.get_size_inches()*fig.dpi
            base = min(w, h)
            title_fontsize = max(18, base // 40)
            subtitle_fontsize = max(12, base // 70)
            label_fontsize = max(10, base // 90)
            button_fontsize = max(10, base // 90)
            slider_fontsize = max(10, base // 90)

            if hasattr(fig, '_main_title'):
                fig._main_title.set_fontsize(title_fontsize)
            if hasattr(fig, '_subtitle'):
                fig._subtitle.set_fontsize(subtitle_fontsize)
            slider_routers.label.set_fontsize(label_fontsize)
            slider_routers.valtext.set_fontsize(slider_fontsize)
            btn_calculate.label.set_fontsize(button_fontsize)

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

        def calculate_coverage(event):
            """Calcula e mostra a cobertura quando o botão é clicado"""
            coverage, avg_rssi, rssi_values = self.evaluate_coverage(G, current_routers)
            nodes_plot.set_array(rssi_values)
            nodes_plot.set_cmap('RdYlGn')
            nodes_plot.set_clim(-90, -30)
            nodes_plot.set_alpha(1.0)
            router_positions = ', '.join([str(tuple(int(x) for x in r)) for r in current_routers])
            fig._coverage_title = ax.set_title(
                f"Cobertura: {coverage:.1f}% | RSSI médio: {avg_rssi:.1f} dBm\n"
                f"Posições dos roteadores: {router_positions}",
                fontsize=max(10, min(fig.get_size_inches()*fig.dpi)//90)
            )

            if not hasattr(fig, '_colorbar') or fig._colorbar is None:
                cax = fig.add_axes([0.92, 0.25, 0.015, 0.6])
                fig._colorbar = plt.colorbar(nodes_plot, cax=cax, label='RSSI (dBm)')
                fig._colorbar.set_label('RSSI (dBm)', fontsize=max(10, min(fig.get_size_inches()*fig.dpi)//90))
            else:
                fig._colorbar.update_normal(nodes_plot)
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
            nodes_plot.set_alpha(0)
            ax.set_title("")
            fig.canvas.draw_idle()

        # Criação dos widgets após definição das funções de fonte
        ax_button = plt.axes([0.45, 0.13, 0.1, 0.06])
        btn_calculate = Button(ax_button, 'Calcular')

        ax_slider = plt.axes([0.25, 0.05, 0.5, 0.04])
        slider_routers = Slider(
            ax_slider, 'Qtd. Roteadores', min_routers, max_routers, 
            valinit=num_roteadores, valstep=1, valfmt='%0.0f'
        )

        # Conecta eventos
        fig.canvas.mpl_connect('pick_event', on_pick)
        fig.canvas.mpl_connect('motion_notify_event', on_motion)
        fig.canvas.mpl_connect('button_release_event', on_release)
        btn_calculate.on_clicked(calculate_coverage)
        slider_routers.on_changed(on_slider_change)
        fig.canvas.mpl_connect('resize_event', update_fonts)

        # Inicializa fontes
        update_fonts()

        plt.show()

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

if __name__ == "__main__":
    optimizer = RouterOptimizer()
    G = optimizer.load_graph()
    num_roteadores = getattr(optimizer, "num_roteadores", 1)
    optimizer.interactive_router_placement(G, num_roteadores)