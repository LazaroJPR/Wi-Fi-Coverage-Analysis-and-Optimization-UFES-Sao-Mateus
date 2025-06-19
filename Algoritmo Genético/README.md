<details open>
  <summary><strong>🇧🇷 Português</strong></summary>

<h1>📡 Otimizador Genético de Cobertura Wi-Fi</h1>

Este módulo utiliza um **Algoritmo Genético Paralelo** para otimizar a posição de roteadores Wi-Fi em ambientes internos, maximizando a cobertura e o nível de sinal (RSSI) em um grafo ponderado (gerado a partir de uma planta baixa). O sistema considera obstáculos (paredes, portas, janelas, etc.) e a distância euclidiana para calcular a propagação do sinal.

## 📌 Exemplo Visual

### Grafo de entrada

O grafo ponderado deve ser gerado previamente pelo módulo "Criador de Grafos" e salvo em formato `.graphml`.

![Grafo](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Resultado da simulação

![Simulação Gerada](https://github.com/LazaroJPR/Wi-Fi-Coverage-Analysis-and-Optimization-UFES-Sao-Mateus/blob/main/Dados/Simula%C3%A7%C3%B5es/Dist%C3%A2ncia%20Euclidiana/Salas%20Professores/2%20roteadores/solucao_1/cobertura_1.png)

O simulador gera imagens de cobertura, destacando a intensidade do sinal em cada ponto e as posições ideais dos roteadores.

## ⚙️ Parâmetros Principais

| Parâmetro               | Descrição                                                        |
|-------------------------|------------------------------------------------------------------|
| rssi_threshold          | Limite mínimo de RSSI para considerar cobertura                  |
| tx_power                | Potência de transmissão do roteador (dBm)                        |
| freq_mhz                | Frequência do Wi-Fi (MHz)                                        |
| scale_factor            | Fator de escala para visualização                                |
| distance_conversion     | Fator de conversão de unidade do grafo para metros               |
| num_roteadores          | Quantidade de roteadores a posicionar                            |
| avg_rssi_weight         | Peso do RSSI médio na função objetivo                            |
| coverage_weight         | Peso da cobertura na função objetivo                             |
| weight_colors           | Cores para pesos das arestas                                     |
| plot_save_path          | Pasta para salvar resultados e imagens                           |
| genetic_algorithm       | Parâmetros do algoritmo genético (população, gerações, etc.)     |
| optimization            | Parâmetros de penalização e normalização do algoritmo            |
| parallel_processing     | Parâmetros de paralelização (max_workers, chunk_size)            |
| logging                 | Configurações de log (nível, salvar log, saída no console)       |
| visualization           | Parâmetros de visualização (tamanho da figura, cores, etc.)      |
| max_workers             | Número máximo de processos paralelos                             |
| chunk_size              | Tamanho dos lotes para processamento paralelo                    |
| penalty_weight          | Peso da penalização para roteadores próximos                     |
| min_router_distance     | Distância mínima entre roteadores para penalização               |
| rssi_normalization_range| Intervalo de normalização do RSSI médio                          |
| figure_size             | Tamanho da figura gerada                                         |
| node_size               | Tamanho dos nós no grafo                                         |
| router_node_size        | Tamanho dos nós dos roteadores                                   |
| edge_width              | Espessura das arestas                                            |
| edge_alpha              | Transparência das arestas                                        |
| dpi                     | DPI das imagens geradas                                          |
| colormap                | Mapa de cores para RSSI                                          |
| rssi_vmin               | Valor mínimo de RSSI para colormap                               |
| rssi_vmax               | Valor máximo de RSSI para colormap                               |

Todos os parâmetros podem ser ajustados no arquivo `config.json`.

## 🛠️ Tecnologias Utilizadas

- Python 3.8+
- NumPy
- NetworkX
- Matplotlib
- Tkinter (seleção de arquivos)
- concurrent.futures (paralelização)
- tqdm (barra de progresso)
- logging, json, os, shutil, zipfile (bibliotecas padrão)

### Requisitos

Certifique-se de ter instalado:
```bash
pip install numpy networkx matplotlib tqdm
```
> Tkinter, concurrent.futures, logging, json, os e shutil já vêm com o Python padrão.

## 🚀 Funcionalidades

- Carregamento de grafos ponderados em `.graphml`
- Simulação da propagação do sinal Wi-Fi considerando obstáculos
- Otimização automática das posições dos roteadores via Algoritmo Genético Paralelo
- Geração de imagens de cobertura e exportação dos melhores resultados em `.zip`
- Parâmetros totalmente configuráveis via `config.json`

## 📦 Como Usar

1. Gere o grafo ponderado da planta baixa usando o módulo "Criador de Grafos".
2. Ajuste os parâmetros desejados no `config.json`.
3. Execute:
   ```bash
   python genetic_optimizer.py
   ```
4. Selecione o arquivo `.graphml` do grafo quando solicitado.
5. O melhor resultado será salvo na pasta definida em `plot_save_path` (imagens e dados em `.zip`).

## 📝 Exemplo de config.json

```json
{
    "rssi_threshold": -70,
    "tx_power": 23,
    "freq_mhz": 2400,
    "scale_factor": 2,
    "distance_conversion": 0.5,
    "num_roteadores": 4,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7,
    "weight_colors": {
        "16.67": "blue",
        "7": "red",
        "6.81": "green",
        "4": "yellow",
        "1": "gray"
    },
    "plot_save_path": "C:\\Caminho\\para\\salvar",
    "genetic_algorithm": {
        "population_size": 100,
        "generations": 50,
        "mutation_rate": 0.1,
        "crossover_rate": 0.8,
        "tournament_size": 3,
        "elitism_count": 2
    },
    "parallel_processing": {
        "max_workers": 16
    }
}
```

## 🎯 Aplicações

- Planejamento de cobertura Wi-Fi em ambientes internos
- Simulações para projetos de redes sem fio
- Ensino e pesquisa em propagação de sinais e otimização

</details>

<details>
  <summary><strong>🇺🇸 English</strong></summary>

<h1>📡 Wi-Fi Coverage Genetic Optimizer</h1>

This module uses a **Parallel Genetic Algorithm** to optimize Wi-Fi router placement in indoor environments, maximizing coverage and signal strength (RSSI) on a weighted graph (generated from a floor plan). The system considers obstacles (walls, doors, windows, etc.) and Euclidean distance to calculate signal propagation.

## 📌 Visual Example

### Input Graph

The weighted graph must be previously generated by the "Graph Creator" module and saved as `.graphml`.

![Graph](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Simulation Result

![Generated Simulation](https://github.com/LazaroJPR/Wi-Fi-Coverage-Analysis-and-Optimization-UFES-Sao-Mateus/blob/main/Dados/Simula%C3%A7%C3%B5es/Dist%C3%A2ncia%20Euclidiana/Salas%20Professores/2%20roteadores/solucao_1/cobertura_1.png)

The simulator generates coverage images, highlighting signal intensity at each point and the optimal router positions.

## ⚙️ Main Parameters

| Parameter                | Description                                                        |
|--------------------------|--------------------------------------------------------------------|
| rssi_threshold           | Minimum RSSI to consider coverage                                  |
| tx_power                 | Router transmit power (dBm)                                        |
| freq_mhz                 | Wi-Fi frequency (MHz)                                              |
| scale_factor             | Scale factor for visualization                                     |
| distance_conversion      | Conversion factor from graph unit to meters                        |
| num_roteadores           | Number of routers to place                                         |
| avg_rssi_weight          | Weight of average RSSI in objective function                       |
| coverage_weight          | Weight of coverage in objective function                           |
| weight_colors            | Edge weight colors                                                 |
| plot_save_path           | Folder to save results and images                                  |
| genetic_algorithm        | Genetic algorithm parameters (population, generations, etc.)       |
| optimization             | Penalty and normalization parameters for the algorithm             |
| parallel_processing      | Parallelization parameters (max_workers, chunk_size)               |
| logging                  | Logging settings (level, save_log, console_output)                 |
| visualization            | Visualization parameters (figure size, colors, etc.)               |
| max_workers              | Maximum number of parallel processes                               |
| chunk_size               | Chunk size for parallel processing                                 |
| penalty_weight           | Penalty weight for close routers                                   |
| min_router_distance      | Minimum distance between routers for penalty                       |
| rssi_normalization_range | Normalization range for average RSSI                               |
| figure_size              | Generated figure size                                              |
| node_size                | Node size in the graph                                             |
| router_node_size         | Router node size in the graph                                      |
| edge_width               | Edge width                                                         |
| edge_alpha               | Edge transparency                                                  |
| dpi                      | DPI of generated images                                            |
| colormap                 | Colormap for RSSI                                                  |
| rssi_vmin                | Minimum RSSI value for colormap                                    |
| rssi_vmax                | Maximum RSSI value for colormap                                    |

All parameters can be adjusted in `config.json`.

## 🛠️ Technologies Used

- Python 3.8+
- NumPy
- NetworkX
- Matplotlib
- Tkinter (file selection)
- concurrent.futures (parallelization)
- tqdm (progress bar)
- logging, json, os, shutil, zipfile (standard libraries)

### Requirements

Make sure you have installed:
```bash
pip install numpy networkx matplotlib tqdm
```
> Tkinter, concurrent.futures, logging, json, os and shutil are included in standard Python.

## 🚀 Features

- Load weighted graphs in `.graphml`
- Simulate Wi-Fi signal propagation considering obstacles
- Automatic router position optimization via Parallel Genetic Algorithm
- Generate coverage images and export best results in `.zip`
- Fully configurable via `config.json`

## 📦 How to Use

1. Generate the weighted graph from the floor plan using the "Graph Creator" module.
2. Adjust desired parameters in `config.json`.
3. Run:
   ```bash
   python genetic_optimizer.py
   ```
4. Select the `.graphml` graph file when prompted.
5. The best result will be saved in the folder defined in `plot_save_path` (images and data in `.zip`).

## 📝 Example config.json

```json
{
    "rssi_threshold": -70,
    "tx_power": 23,
    "freq_mhz": 2400,
    "scale_factor": 2,
    "distance_conversion": 0.5,
    "num_roteadores": 4,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7,
    "weight_colors": {
        "16.67": "blue",
        "7": "red",
        "6.81": "green",
        "4": "yellow",
        "1": "gray"
    },
    "plot_save_path": "C:\\Path\\to\\save",
    "genetic_algorithm": {
        "population_size": 100,
        "generations": 50,
        "mutation_rate": 0.1,
        "crossover_rate": 0.8,
        "tournament_size": 3,
        "elitism_count": 2
    },
    "parallel_processing": {
        "max_workers": 16
    }
}
```

## 🎯 Applications

- Wi-Fi coverage planning for indoor environments
- Simulations for wireless network projects
- Teaching and research in signal propagation and optimization

</details>
