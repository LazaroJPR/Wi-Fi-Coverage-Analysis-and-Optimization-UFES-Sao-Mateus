import os
import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider
import numpy as np
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog
import logging
import json
from precompute_aoa_toa import PrecomputeAoAToA

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
        self.aoa_data = {}
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
    
    def compute_rssi_for_node(self, G, node, routers, toa_data, aoa_data=None):
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

            distance = max(calc_distance_toa(toa), self.distance_conversion)
            fspl = calc_fspl(distance, self.freq_mhz)
            
            # Adicionar o fator de AoA ao cálculo do RSSI
            rssi = self.tx_power - fspl - obstacle_loss + aoa_factor
            
            if rssi > best_rssi:
                best_rssi = rssi
        return best_rssi

    def evaluate_coverage(self, G, routers, toa_data=None, aoa_data=None):
        """Avalia a cobertura e RSSI médio para uma configuração de roteadores."""
        logging.debug("Calculando cobertura e RSSI médio usando ToA e AoA.")
        node_list = list(G.nodes())

        if isinstance(toa_data, str) and toa_data.endswith(".h5"):
            pairs = []
            for node in node_list:
                for router in routers:
                    if node != router:
                        pairs.append((node, router))
            toa_data, aoa_data = get_toa_aoa_from_hdf5(toa_data, pairs)

        toa_data = toa_data or getattr(self, 'toa_cache', {})
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
    
    def interactive_router_placement(self, G, num_roteadores_default):
        """Permite movimentar roteadores interativamente e calcula cobertura/RSSI ao clicar em Calcular."""

        nodes = list(G.nodes())
        min_routers = 1
        max_routers = min(20, len(nodes))
        num_roteadores = num_roteadores_default

        routers = [nodes[i] for i in np.linspace(0, len(nodes)-1, num_roteadores, dtype=int)]

        if not self.toa_cache:
            result = self.generate_toa_aoa_data(G, nodes, use_precomputed=True)
            if isinstance(result, tuple) and len(result) == 3 and isinstance(result[2], str) and result[2].endswith(".h5"):
                self.toa_cache = result[2]
                self.aoa_data = None
            else:
                self.toa_cache, self.aoa_data = result

        fig = plt.figure(figsize=(16, 12))
        fig.subplots_adjust(top=0.85, bottom=0.25)
        ax = fig.add_subplot(111)
        ax.set_aspect('equal')
        cax = fig.add_axes([0.92, 0.25, 0.015, 0.6])
        fig._cax = cax

        title_text = "Simulador Interativo - AoA/ToA"
        subtitle_text = "Arraste os roteadores, ajuste a quantidade e clique em Calcular para ver a cobertura"

        # Função para calcular o raio dos nós baseado no tamanho da menor aresta em pixels
        def get_node_radius_px():
            trans = ax.transData.transform
            node_pos_px = {n: trans((n[0]*self.scale_factor, n[1]*self.scale_factor)) for n in G.nodes()}
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

        # Inicialize a colorbar (vazia) já no início
        fig._colorbar = plt.colorbar(nodes_plot, cax=cax, label='RSSI (dBm)')
        fig._colorbar.set_label('RSSI (dBm)', fontsize=max(10, min(fig.get_size_inches()*fig.dpi)//90))

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
            coverage, avg_rssi, rssi_values = self.evaluate_coverage(
                G, current_routers, toa_data=self.toa_cache, aoa_data=self.aoa_data
            )
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

            # Atualize a colorbar existente, não crie outra
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

if __name__ == "__main__":
    optimizer = RouterOptimizerAoAToA()
    G = optimizer.load_graph()
    num_roteadores = getattr(optimizer, "num_roteadores", 1)
    optimizer.interactive_router_placement(G, num_roteadores)