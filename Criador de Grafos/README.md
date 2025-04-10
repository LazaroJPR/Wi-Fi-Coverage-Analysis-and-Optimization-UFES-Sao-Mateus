<details open>
  <summary><strong>🇧🇷 Português</strong></summary>

<h1>🧠 Conversão de Planta Baixa em Grafo Ponderado para Simulações de Navegação Wi-Fi</h1>

Este módulo converte uma imagem de planta arquitetônica em um **grafo ponderado**, onde os nós representam pontos navegáveis e as arestas representam conexões ponderadas com base nos obstáculos detectados na imagem (paredes, portas, janelas, etc).

## 📌 Exemplo Visual

### Planta de entrada

![Planta de Exemplo](https://github.com/LazaroJPR/TCC/blob/main/Imagens/Plantas%20Padronizadas/Salas%20Pequenas.jpg)

### Grafo gerado

![Grafo Gerado](https://github.com/LazaroJPR/TCC/blob/main/Imagens/Grafos/Grafo%20-%20Salas%20Pequenas.png)

## 🧱 Parâmetros de Atenuação por Material

| Material  | Cor Referência | Nível de Atenuação |
|-----------|----------------|--------------------|
| Concreto  | Azul           | 16.67              |
| Janela    | Vermelho       | 7.00               |
| Porta     | Verde          | 6.81               |
| MDF       | Amarelo        | 4.00               |

## 🛠️ Tecnologias utilizadas

- Python
- OpenCV
- NumPy
- NetworkX
- Matplotlib

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

## 📦 Como usar

1. Suba uma imagem da planta com as cores padronizadas.
2. O script processará a imagem, detectará os obstáculos e criará o grafo.
3. O grafo será renderizado sobre a imagem original com as arestas coloridas conforme o peso.

## 🎯 Aplicações

- Simulações de navegação autônoma
- Planejamento de posicionamento de roteadores Wi-Fi
- Robótica e mapeamento indoor
- Análise de acessibilidade de ambientes

</details>

<details>
  <summary><strong>🇺🇸 English</strong></summary>

<h1>🧠 Floor Plan to Weighted Graph for Wi-Fi Navigation Simulations</h1>

This module converts a **floor plan image** into a **weighted graph**, where nodes represent navigable points and edges represent weighted paths based on detected obstacles (walls, doors, windows, etc.).

## 📌 Visual Example

### Input Floor Plan

![Example Floor Plan](https://github.com/LazaroJPR/TCC/blob/main/Imagens/Plantas%20Padronizadas/Salas%20Pequenas.jpg)

### Generated Graph

![Generated Graph](https://github.com/LazaroJPR/TCC/blob/main/Imagens/Grafos/Grafo%20-%20Salas%20Pequenas.png)

## 🧱 Attenuation Parameters by Material

| Material  | Reference Color | Attenuation Level |
|-----------|------------------|--------------------|
| Concrete  | Blue             | 16.67              |
| Window    | Red              | 7.00               |
| Door      | Green            | 6.81               |
| MDF       | Yellow           | 4.00               |

## 🛠️ Technologies Used

- Python
- OpenCV
- NumPy
- NetworkX
- Matplotlib

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

## 📦 How to Use

1. Upload a standardized color-coded floor plan image.
2. The script processes the image, detects the obstacles, and builds the graph.
3. The graph is rendered over the original image with color-coded weighted edges.

## 🎯 Applications

- Autonomous navigation simulations
- Wi-Fi router placement planning
- Indoor robotics and mapping
- Accessibility analysis in architecture

</details>
