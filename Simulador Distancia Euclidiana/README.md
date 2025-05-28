<details open>
  <summary><strong>🇧🇷 Português</strong></summary>

<h1>📡 Simulador de Cobertura Wi-Fi com Otimização de Roteadores</h1>

Este módulo realiza simulações de cobertura Wi-Fi em ambientes internos, utilizando um **grafo ponderado** (gerado a partir de uma planta baixa) para calcular a propagação do sinal, considerando obstáculos (paredes, portas, janelas, etc) e a distância euclidiana. O sistema busca automaticamente as melhores posições para roteadores, maximizando a cobertura e o nível de sinal (RSSI).

## 📌 Exemplo Visual

### Grafo de entrada

O grafo ponderado deve ser gerado previamente pelo módulo "Criador de Grafos" e salvo em formato `.graphml`.

![Grafo](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Resultado da simulação

![Simulação Gerada](https://github.com/LazaroJPR/Wi-Fi-Coverage-Analysis-and-Optimization-UFES-Sao-Mateus/blob/main/Dados/Simula%C3%A7%C3%B5es/Dist%C3%A2ncia%20Euclidiana/Salas%20Professores/2%20roteadores/solucao_1/cobertura_1.png)

O simulador gera imagens de cobertura, destacando a intensidade do sinal em cada ponto e as posições ideais dos roteadores.

## ⚙️ Parâmetros Principais

| Parâmetro           | Descrição                                              |
|---------------------|--------------------------------------------------------|
| rssi_threshold      | Limite mínimo de RSSI para considerar cobertura        |
| tx_power            | Potência de transmissão do roteador (dBm)              |
| freq_mhz            | Frequência do Wi-Fi (MHz)                              |
| scale_factor        | Fator de escala para visualização                      |
| distance_conversion | Fator de conversão de unidade do grafo para metros     |
| max_iter            | Número de iterações de busca por melhores posições     |
| top_n               | Quantidade de melhores soluções salvas                 |
| weight_colors       | Cores para pesos das arestas                           |
| plot_save_path      | Pasta para salvar resultados e imagens                 |
| num_roteadores      | Quantidade de roteadores a posicionar                  |
| router_name         | Nome/modelo do roteador                                |
| max_workers         | Número máximo de threads/processos paralelos           |
| avg_rssi_weight     | Peso do RSSI médio na função objetivo                  |
| coverage_weight     | Peso da cobertura na função objetivo                   |

Todos os parâmetros podem ser ajustados no arquivo `config.json`.

## 🛠️ Tecnologias Utilizadas

- Python 3.8+
- NumPy
- NetworkX
- Matplotlib
- scikit-learn (KMeans)
- Tkinter (seleção de arquivos)
- concurrent.futures (paralelização)
- logging, json, os, shutil, zipfile (bibliotecas padrão)

### Requisitos

Certifique-se de ter instalado:
```bash
pip install numpy networkx matplotlib scikit-learn
```
> Tkinter, concurrent.futures, logging, json, os e shutil já vêm com o Python padrão.

## 🚀 Funcionalidades

- Carregamento de grafos ponderados em `.graphml`
- Simulação da propagação do sinal Wi-Fi considerando obstáculos
- Otimização automática das posições dos roteadores (paralelizada)
- Geração de imagens de cobertura e exportação dos melhores resultados em `.zip`
- Parâmetros totalmente configuráveis via `config.json`
- **Modo interativo:** Posicionamento manual e visualização dinâmica dos roteadores com cálculo instantâneo de cobertura e RSSI médio (`euclideanDistance_interactive.py`)

## 📦 Como Usar

1. Gere o grafo ponderado da planta baixa usando o módulo "Criador de Grafos".
2. Ajuste os parâmetros desejados no `config.json`.
3. Para simulação automática, execute:
   ```bash
   python euclideanDistance.py
   ```
   Para simulação interativa, execute:
   ```bash
   python euclideanDistance_interactive.py
   ```
4. Selecione o arquivo `.graphml` do grafo quando solicitado.
5. Os melhores resultados serão salvos na pasta definida em `plot_save_path` (imagens e dados em `.zip`).  
   No modo interativo, visualize e ajuste os roteadores diretamente na interface gráfica.

## 📝 Exemplo de config.json

```json
{
    "rssi_threshold": -70,
    "tx_power": 23,
    "freq_mhz": 2400,
    "scale_factor": 2,
    "distance_conversion": 0.5,
    "max_iter": 500,
    "top_n": 5,
    "weight_colors": {
        "16.67": "blue",
        "7": "red",
        "6.81": "green",
        "4": "yellow",
        "1": "gray"
    },
    "plot_save_path": "C:\\Caminho\\para\\salvar",
    "num_roteadores": 5,
    "router_name": "Cisco AIR-AP-2802I-Z-K9-BR",
    "max_workers": 16,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7
}
```

## 🎯 Aplicações

- Planejamento de cobertura Wi-Fi em ambientes internos
- Simulações para projetos de redes sem fio
- Ensino e pesquisa em propagação de sinais e otimização

</details>

<details>
  <summary><strong>🇺🇸 English</strong></summary>

<h1>📡 Wi-Fi Coverage Simulator with Router Optimization</h1>

This module simulates indoor Wi-Fi coverage using a **weighted graph** (generated from a floor plan) to calculate signal propagation, considering obstacles (walls, doors, windows, etc.) and Euclidean distance. The system automatically searches for the best router positions to maximize coverage and signal strength (RSSI).

## 📌 Visual Example

### Input Graph

The weighted graph must be previously generated by the "Graph Creator" module and saved as `.graphml`.

![Graph](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Simulation Result

![Generated Simulation](https://github.com/LazaroJPR/Wi-Fi-Coverage-Analysis-and-Optimization-UFES-Sao-Mateus/blob/main/Dados/Simula%C3%A7%C3%B5es/Dist%C3%A2ncia%20Euclidiana/Salas%20Professores/2%20roteadores/solucao_1/cobertura_1.png)

The simulator generates coverage images, highlighting signal intensity at each point and the optimal router positions.

## ⚙️ Main Parameters

| Parameter           | Description                                         |
|---------------------|-----------------------------------------------------|
| rssi_threshold      | Minimum RSSI to consider coverage                   |
| tx_power            | Router transmit power (dBm)                         |
| freq_mhz            | Wi-Fi frequency (MHz)                               |
| scale_factor        | Scale factor for visualization                      |
| distance_conversion | Conversion factor from graph unit to meters         |
| max_iter            | Number of optimization iterations                   |
| top_n               | Number of best solutions saved                      |
| weight_colors       | Edge weight colors                                  |
| plot_save_path      | Folder to save results and images                   |
| num_roteadores      | Number of routers to place                          |
| router_name         | Router name/model                                   |
| max_workers         | Maximum number of parallel threads/processes        |
| avg_rssi_weight     | Weight of average RSSI in objective function        |
| coverage_weight     | Weight of coverage in objective function            |

All parameters can be adjusted in `config.json`.

## 🛠️ Technologies Used

- Python 3.8+
- NumPy
- NetworkX
- Matplotlib
- scikit-learn (KMeans)
- Tkinter (file selection)
- concurrent.futures (parallelization)
- logging, json, os, shutil, zipfile (standard libraries)

### Requirements

Make sure you have installed:
```bash
pip install numpy networkx matplotlib scikit-learn
```
> Tkinter, concurrent.futures, logging, json, os and shutil are included in standard Python.

## 🚀 Features

- Load weighted graphs in `.graphml`
- Simulate Wi-Fi signal propagation considering obstacles
- Automatic router position optimization (parallelized)
- Generate coverage images and export best results in `.zip`
- Fully configurable via `config.json`
- **Interactive mode:** Manually place and move routers with instant coverage and RSSI feedback (`euclideanDistance_interactive.py`)

## 📦 How to Use

1. Generate the weighted graph from the floor plan using the "Graph Creator" module.
2. Adjust desired parameters in `config.json`.
3. For automatic simulation, run:
   ```bash
   python euclideanDistance.py
   ```
   For interactive simulation, run:
   ```bash
   python euclideanDistance_interactive.py
   ```
4. Select the `.graphml` graph file when prompted.
5. The best results will be saved in the folder defined in `plot_save_path` (images and data in `.zip`).  
   In interactive mode, visualize and adjust routers directly in the graphical interface.

## 📝 Example config.json

```json
{
    "rssi_threshold": -70,
    "tx_power": 23,
    "freq_mhz": 2400,
    "scale_factor": 2,
    "distance_conversion": 0.5,
    "max_iter": 500,
    "top_n": 5,
    "weight_colors": {
        "16.67": "blue",
        "7": "red",
        "6.81": "green",
        "4": "yellow",
        "1": "gray"
    },
    "plot_save_path": "C:\\Path\\to\\save",
    "num_roteadores": 5,
    "router_name": "Cisco AIR-AP-2802I-Z-K9-BR",
    "max_workers": 16,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7
}
```

## 🎯 Applications

- Wi-Fi coverage planning for indoor environments
- Simulations for wireless network projects
- Teaching and research in signal propagation and optimization

</details>
