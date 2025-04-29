import cv2
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from networkx import write_graphml
import os
import tkinter as tk
from tkinter import filedialog
import json
import logging

# Configuração básica do logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

class JpegToGraph:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
        logging.info("Inicializando JpegToGraph com config: %s", config_path)
        # Carregar configurações do arquivo JSON
        self.config = self.load_config(config_path)
        self.cell_size = self.config.get("cell_size", 5)
        self.weight_mapping = self.config.get("weight_mapping", {
            'azul': 16.67,  # Parede (concreto)
            'vermelho': 7,  # Janela
            'verde': 6.81,  # Porta
            'amarelo': 4,   # MDF
            'default': 1    # Passagem livre
        })
        self.plot_save_dir = self.config.get("plot_save_path", ".")
        self.plot_save_path = None
        self.image_filename = None
        self.hsv_color_ranges = {
            'azul': (np.array([100, 150, 50]), np.array([140, 255, 255])),
            'vermelho1': (np.array([0, 100, 100]), np.array([10, 255, 255])),
            'vermelho2': (np.array([160, 100, 100]), np.array([180, 255, 255])),
            'verde': (np.array([36, 50, 50]), np.array([86, 255, 255])),
            'amarelo': (np.array([20, 100, 100]), np.array([40, 255, 255]))
        }

    def load_config(self, config_path):
        if os.path.isfile(config_path):
            logging.info("Carregando configurações de %s", config_path)
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logging.warning("Arquivo de configuração não encontrado. Usando valores padrão.")
        return {}

    def load_image(self, image_path):
        """Carrega a imagem do caminho fornecido"""
        logging.info("Carregando imagem: %s", image_path)
        img = cv2.imread(image_path)
        if img is None:
            logging.error("Imagem não encontrada: %s", image_path)
            raise FileNotFoundError(f"Imagem não encontrada: {image_path}")

        self.image_filename = os.path.splitext(os.path.basename(image_path))[0]

        self.plot_save_path = os.path.join(
            self.plot_save_dir,
            f"{self.image_filename}.png"
        )
        logging.info("Imagem carregada com sucesso: %s", self.image_filename)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def show_image(self, img, title="Imagem"):
        """Exibe a imagem com matplotlib"""
        logging.info("Exibindo imagem: %s", title)
        plt.figure(figsize=(10, 8))
        plt.imshow(img)
        plt.title(title)
        plt.axis('off')

    def _create_color_mask(self, hsv_img, color_name):
        """Cria máscara para uma cor específica, tratando casos especiais como vermelho"""
        if color_name == 'vermelho':
            mask1 = cv2.inRange(hsv_img, *self.hsv_color_ranges['vermelho1'])
            mask2 = cv2.inRange(hsv_img, *self.hsv_color_ranges['vermelho2'])
            return cv2.bitwise_or(mask1, mask2)
        else:
            return cv2.inRange(hsv_img, *self.hsv_color_ranges[color_name])

    def create_color_masks(self, hsv_img):
        """Cria máscaras para cada intervalo de cores definido"""
        logging.info("Criando máscaras de cor")
        masks = {
            color: self._create_color_mask(hsv_img, color)
            for color in ['azul', 'vermelho', 'verde', 'amarelo']
        }
        # Aplicar operações morfológicas
        kernel_size = max(3, self.cell_size // 3)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        for key in masks:
            masks[key] = cv2.morphologyEx(masks[key], cv2.MORPH_CLOSE, kernel, iterations=2)
            masks[key] = cv2.morphologyEx(masks[key], cv2.MORPH_OPEN, kernel, iterations=1)
        logging.info("Máscaras de cor criadas")
        return masks

    def create_blockage_mask(self, img):
        """Cria máscara para áreas bloqueadas"""
        logging.info("Criando máscara de bloqueio")
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, mask = cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY_INV)
        logging.info("Máscara de bloqueio criada")
        return mask

    def generate_graph_nodes(self, img_shape, blockage_mask):
        """Gera os nós do grafo baseado no grid e nas áreas não bloqueadas"""
        logging.info("Gerando nós do grafo")
        h, w = img_shape[:2]
        nodes = []
        for y in range(0, h, self.cell_size):
            for x in range(0, w, self.cell_size):
                center_y = min(y + self.cell_size//2, h-1)
                center_x = min(x + self.cell_size//2, w-1)
                if blockage_mask[center_y, center_x] == 0:  # Área não bloqueada
                    node = (x // self.cell_size, y // self.cell_size)
                    nodes.append(node)
        logging.info("Total de nós gerados: %d", len(nodes))
        return nodes

    def check_edge_weights(self, point1, point2, hsv_img, blockage_mask):
        """Determina o peso da aresta baseado nas cores ao longo da linha"""
        mask = np.zeros((hsv_img.shape[0], hsv_img.shape[1]), dtype=np.uint8)
        cv2.line(mask, point1, point2, 255, thickness=3)
        if np.any(cv2.bitwise_and(blockage_mask, mask)):
            return None  # Aresta bloqueada
        line_pixels = cv2.bitwise_and(hsv_img, hsv_img, mask=mask)
        total_pixels = np.count_nonzero(mask) + 1e-5
        color_proportions = {
            color: self._create_color_mask(line_pixels, color)
            for color in ['azul', 'vermelho', 'verde', 'amarelo']
        }
        for color, prop in color_proportions.items():
            if np.count_nonzero(prop) / total_pixels > 0.15:
                return self.weight_mapping[color]
        return self.weight_mapping['default']

    def build_graph(self, nodes, hsv_img, blockage_mask):
        """Constrói o grafo com nós e arestas"""
        logging.info("Construindo o grafo")
        G = nx.Graph()
        G.add_nodes_from(nodes)
        # Direções para conexões (incluindo diagonais)
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1),
                     (1, 1), (1, -1), (-1, 1), (-1, -1)]
        for node in nodes:
            x, y = node
            for dx, dy in directions:
                neighbor = (x + dx, y + dy)
                if neighbor in G:
                    # Converter coordenadas do nó para pixels na imagem
                    point1 = (x * self.cell_size + self.cell_size // 2,
                             y * self.cell_size + self.cell_size // 2)
                    point2 = (neighbor[0] * self.cell_size + self.cell_size // 2,
                              neighbor[1] * self.cell_size + self.cell_size // 2)
                    weight = self.check_edge_weights(point1, point2, hsv_img, blockage_mask)
                    if weight is not None:
                        G.add_edge(node, neighbor, weight=weight)
        logging.info("Total de nós no grafo: %d", G.number_of_nodes())
        logging.info("Total de arestas no grafo: %d", G.number_of_edges())
        return G

    def visualize_graph(self, G):
        """Visualiza o grafo com cores representando os pesos das arestas"""
        logging.info("Visualizando o grafo")
        scale_factor = 2
        pos = {n: (n[0] * scale_factor, n[1] * scale_factor) for n in G.nodes()}
        plt.figure(figsize=(16, 12))

        # Mapeamento de pesos para cores
        weight_colors = {
            self.weight_mapping['default']: 'gray',
            self.weight_mapping['amarelo']: 'yellow',
            self.weight_mapping['verde']: 'green',
            self.weight_mapping['vermelho']: 'red',
            self.weight_mapping['azul']: 'blue'
        }
        edge_colors = [weight_colors.get(G[u][v].get('weight', 1), 'black')
                      for u, v in G.edges()]
        
        # Desenhar arestas
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2, alpha=0.6)

        # Desenhar nós
        nx.draw_networkx_nodes(
            G, pos, node_color='black',
            node_size=20, edgecolors='white', linewidths=0.5
        )
        plt.title("Grafo de navegação")
        plt.axis('equal')
        plt.axis('off')

        # Criar legenda
        legend_elements = [
            plt.Line2D([0], [0], color='gray', lw=2, label=f'Passagem livre ({self.weight_mapping["default"]})'),
            plt.Line2D([0], [0], color='yellow', lw=2, label=f'MDF ({self.weight_mapping["amarelo"]})'),
            plt.Line2D([0], [0], color='green', lw=2, label=f'Porta ({self.weight_mapping["verde"]})'),
            plt.Line2D([0], [0], color='red', lw=2, label=f'Janela ({self.weight_mapping["vermelho"]})'),
            plt.Line2D([0], [0], color='blue', lw=2, label=f'Concreto ({self.weight_mapping["azul"]})')
        ]
        plt.legend(handles=legend_elements,
                 loc='center left',
                 bbox_to_anchor=(1.02, 0.5),
                 frameon=False,
                 title='Atenuação (dB/m)')
        
        if self.plot_save_path:
            plt.savefig(self.plot_save_path, bbox_inches='tight')
            logging.info("Plot salvo em: %s", self.plot_save_path)
        else:
            logging.warning("Caminho para salvar o plot não definido.")

    def export_graph(self, G, filename=None):
        """Exporta o grafo no formato GraphML"""
        if filename is None:
            if self.plot_save_path:
                filename = os.path.splitext(self.plot_save_path)[0] + ".graphml"
            else:
                filename = "grafo_navegacao.graphml"
        write_graphml(G, filename)
        logging.info("Grafo exportado como '%s'", filename)

def main():
    logging.info("Iniciando aplicação")
    root = tk.Tk()
    root.withdraw()
    image_path = filedialog.askopenfilename(
        title="Selecione a imagem JPEG",
        filetypes=[("JPEG files", "*.jpg;*.jpeg"), ("All files", "*.*")]
    )
    if not image_path or not os.path.isfile(image_path):
        logging.error("Arquivo não encontrado ou seleção cancelada: %s", image_path)
        return
    processor = JpegToGraph()

    # 1. Carregar e exibir imagem
    img_rgb = processor.load_image(image_path)
    processor.show_image(img_rgb, "Planta padronizada")

    # 2. Processar imagem
    hsv_img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)  # Conversão direta de RGB para HSV
    color_masks = processor.create_color_masks(hsv_img)
    blockage_mask = processor.create_blockage_mask(img_rgb)

    # 3. Gerar grafo
    nodes = processor.generate_graph_nodes(img_rgb.shape, blockage_mask)
    G = processor.build_graph(nodes, hsv_img, blockage_mask)

    # 4. Visualizar e exportar
    processor.visualize_graph(G)
    processor.export_graph(G)

    # Exibir todos os plots
    plt.show()
    logging.info("Processamento finalizado")

if __name__ == "__main__":
    main()
