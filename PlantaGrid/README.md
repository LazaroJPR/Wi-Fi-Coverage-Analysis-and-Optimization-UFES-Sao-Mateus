<details open>
  <summary><strong>🇧🇷 Português</strong></summary>

<h1>🧠 Conversão de Planta Baixa em Grafo Ponderado para Simulações de Navegação Wi-Fi</h1>

Este software converte uma imagem de planta arquitetônica em um **grafo ponderado**, onde os nós representam pontos navegáveis e as arestas representam conexões ponderadas com base nos obstáculos detectados na imagem (paredes, portas, janelas, etc).

## 📌 Exemplo Visual

### Planta de entrada

![Planta de Exemplo](https://github.com/LazaroJPR/TCC/blob/main/Dados/Plantas%20Padronizadas/Salas%20Professores.jpg)

### Grafo gerado

![Grafo Gerado](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

## 🧱 Parâmetros de Atenuação por Material

| Material  | Cor Referência | Nível de Atenuação |
|-----------|----------------|--------------------|
| Concreto  | Azul           | 16.67              |
| Janela    | Vermelho       | 7.00               |
| Porta     | Verde          | 6.81               |
| MDF       | Amarelo        | 4.00               |

## 🛠️ Tecnologias utilizadas

- Python 3.8+
- OpenCV (`opencv-python`)
- NumPy
- NetworkX
- Matplotlib
- Tkinter (interface gráfica para seleção de arquivos)
- concurrent.futures (paralelização, biblioteca padrão)
- logging (registro de logs, biblioteca padrão)
- json, os (bibliotecas padrão)

## 🚧 Funcionalidades

- Identificação automática de:
  - Paredes de concreto (azul)
  - Janelas (vermelho)
  - Portas (verde)
  - MDF/parede leve (amarelo)
- Construção de um grafo baseado na planta, com:
  - Nós posicionados em um grid
  - Arestas ponderadas conforme o tipo de obstáculo
- Visualização final do grafo com legenda de pesos

### Requisitos

Certifique-se de ter instalado:
- Python 3.8+  
- As seguintes dependências (instale com o comando abaixo):

```bash
pip install opencv-python numpy networkx matplotlib
```

> Tkinter, concurrent.futures, logging, json e os já vêm com o Python padrão.

## 📦 Como usar

1. Suba uma imagem da planta com as cores padronizadas.
2. Execute o script `PlantaGrid.py` para processar a imagem, detectar os obstáculos e criar o grafo:
   ```bash
   python PlantaGrid.py
   ```
   O caminho da imagem será solicitado por uma janela de seleção de arquivos.
3. O grafo será renderizado sobre a imagem original com as arestas coloridas conforme o peso.

### Configuração

O arquivo `config.json` permite ajustar parâmetros do processamento, como o tamanho das células do grid, os pesos de atenuação para cada cor/material e o caminho para salvar as imagens geradas. Exemplo:
```json
{
    "cell_size": 5,
    "weight_mapping": {
        "azul": 16.67,
        "vermelho": 7,
        "verde": 6.81,
        "amarelo": 4,
        "default": 1
    },
    "plot_save_path": "C:\\Caminho\\para\\salvar"
}
```
- `cell_size`: tamanho do grid para discretização da planta.
- `weight_mapping`: pesos de atenuação para cada cor/material.
- `plot_save_path`: pasta onde as imagens do grafo e o grafo serão salvos.

## 🎯 Aplicações

- Simulações de navegação autônoma
- Planejamento de posicionamento de roteadores Wi-Fi
- Robótica e mapeamento indoor
- Análise de acessibilidade de ambientes

</details>

<details>
  <summary><strong>🇺🇸 English</strong></summary>

<h1>🧠 Floor Plan to Weighted Graph for Wi-Fi Navigation Simulations</h1>

This software converts a **floor plan image** into a **weighted graph**, where nodes represent navigable points and edges represent weighted paths based on detected obstacles (walls, doors, windows, etc.).

## 📌 Visual Example

### Input Floor Plan

![Example Floor Plan](https://github.com/LazaroJPR/TCC/blob/main/Dados/Plantas%20Padronizadas/Salas%20Professores.jpg)

### Generated Graph

![Generated Graph](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

## 🧱 Attenuation Parameters by Material

| Material  | Reference Color | Attenuation Level |
|-----------|------------------|--------------------|
| Concrete  | Blue             | 16.67              |
| Window    | Red              | 7.00               |
| Door      | Green            | 6.81               |
| MDF       | Yellow           | 4.00               |

## 🛠️ Technologies Used

- Python 3.8+
- OpenCV (`opencv-python`)
- NumPy
- NetworkX
- Matplotlib
- Tkinter (GUI for file selection)
- concurrent.futures (parallelization, standard library)
- logging (logging, standard library)
- json, os (standard libraries)

## 🚧 Features

- Automatic detection of:
  - Concrete walls (blue)
  - Windows (red)
  - Doors (green)
  - MDF/light walls (yellow)
- Graph construction with:
  - Nodes placed on a grid
  - Edges weighted by obstacle type
- Final visualization with color-coded weights and legend

### Requirements

Make sure you have installed:
- Python 3.8+  
- The following dependencies (install with the command below):

```bash
pip install opencv-python numpy networkx matplotlib
```

> Tkinter, concurrent.futures, logging, json and os are included in standard Python.

## 📦 How to Use

1. Upload a standardized color-coded floor plan image.
2. Run the `PlantaGrid.py` script to process the image, detect obstacles, and build the graph:
   ```bash
   python PlantaGrid.py
   ```
   The image path will be requested via a file selection dialog.
3. The graph is rendered over the original image with color-coded weighted edges.

### Configuration

The `config.json` file allows you to adjust processing parameters, such as grid cell size, attenuation weights for each color/material, and the path to save generated images. Example:
```json
{
    "cell_size": 5,
    "weight_mapping": {
        "azul": 16.67,
        "vermelho": 7,
        "verde": 6.81,
        "amarelo": 4,
        "default": 1
    },
    "plot_save_path": "C:\\Path\\to\\save"
}
```
- `cell_size`: grid size for discretizing the floor plan.
- `weight_mapping`: attenuation weights for each color/material.
- `plot_save_path`: folder where graph images and graph will be saved.

## 🎯 Applications

- Autonomous navigation simulations
- Wi-Fi router placement planning
- Indoor robotics and mapping
- Accessibility analysis in architecture

</details>
