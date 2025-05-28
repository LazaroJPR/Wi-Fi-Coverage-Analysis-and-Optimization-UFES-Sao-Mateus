<details open>
  <summary><strong>🇧🇷 Português</strong></summary>

<h1>📡 Simulador de Cobertura Wi-Fi com Otimização de Roteadores (AoA/ToA)</h1>

Este módulo realiza simulações de cobertura Wi-Fi em ambientes internos utilizando técnicas de **Ângulo de Chegada (AoA)** e **Tempo de Chegada (ToA)**, baseando-se em um **grafo ponderado** (gerado a partir de uma planta baixa). O sistema calcula a propagação do sinal considerando obstáculos (paredes, portas, janelas, etc.), distância e efeitos de AoA/ToA, buscando automaticamente as melhores posições para roteadores para maximizar a cobertura e o nível de sinal (RSSI).

## 📌 Exemplo Visual

### Grafo de entrada

O grafo ponderado deve ser gerado previamente pelo módulo "Criador de Grafos" e salvo em formato `.graphml`.

![Grafo](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Resultado da simulação

O simulador gera imagens de cobertura, destacando a intensidade do sinal em cada ponto e as posições ideais dos roteadores.

![Simulação Gerada](https://github.com/LazaroJPR/TCC/blob/main/Dados/Simula%C3%A7%C3%B5es/Salas%20Professores/5%20roteadores/solucao_1/cobertura_1.png)

## ⚙️ Parâmetros Principais

| Parâmetro                | Descrição                                              |
|--------------------------|--------------------------------------------------------|
| rssi_threshold           | Limite mínimo de RSSI para considerar cobertura        |
| tx_power                 | Potência de transmissão do roteador (dBm)              |
| freq_mhz                 | Frequência do Wi-Fi (MHz)                              |
| scale_factor             | Fator de escala para visualização                      |
| distance_conversion      | Fator de conversão de unidade do grafo para metros     |
| max_iter                 | Número de iterações de busca por melhores posições     |
| top_n                    | Quantidade de melhores soluções salvas                 |
| weight_colors            | Cores para pesos das arestas                           |
| plot_save_path           | Pasta para salvar resultados e imagens                 |
| precomputation_save_path | Pasta para salvar dados pré-computados                 |
| num_roteadores           | Quantidade de roteadores a posicionar                  |
| router_name              | Nome/modelo do roteador                                |
| max_workers              | Número máximo de threads/processos paralelos           |
| noise_factor             | Fator de ruído para simulação de ToA                   |
| avg_rssi_weight          | Peso do RSSI médio na função objetivo                  |
| coverage_weight          | Peso da cobertura na função objetivo                   |

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

### Pré-computação de ToA/AoA

Para acelerar simulações em grandes grafos, é possível pré-computar todos os pares de dados de **Tempo de Chegada (ToA)** e **Ângulo de Chegada (AoA)** usando o script `precompute_aoa_toa.py`. Isso gera um arquivo compactado com os resultados, que pode ser reutilizado em execuções futuras.

**Como usar:**
1. Execute o script:
   ```bash
   python precompute_aoa_toa.py
   ```
2. Selecione o arquivo `.graphml` do grafo quando solicitado.
3. O script irá calcular e salvar um arquivo `.pkl.gz` com os dados ToA/AoA.
4. Ao rodar o simulador, selecione esse arquivo quando solicitado para carregar os dados pré-computados.

> Recomenda-se usar a pré-computação para ambientes grandes ou simulações repetidas, pois reduz significativamente o tempo de execução.

## 🚀 Funcionalidades

- Carregamento de grafos ponderados em `.graphml`
- Simulação da propagação do sinal Wi-Fi considerando obstáculos, AoA e ToA
- Otimização automática das posições dos roteadores (paralelizada)
- Geração de imagens de cobertura e exportação dos melhores resultados em `.zip`
- Parâmetros totalmente configuráveis via `config.json`
- **Modo interativo:** Posicionamento manual e visualização dinâmica dos roteadores com cálculo instantâneo de cobertura e RSSI médio (`AoA_ToA_interactive.py`)

## 📦 Como Usar

1. Gere o grafo ponderado da planta baixa usando o módulo "Criador de Grafos".
2. Ajuste os parâmetros desejados no `config.json`.
3. Para simulação automática, execute:
   ```bash
   python AoA_ToA.py
   ```
   Para simulação interativa, execute:
   ```bash
   python AoA_ToA_interactive.py
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
    "precomputation_save_path": "C:\\Caminho\\para\\salvar",
    "num_roteadores": 2,
    "router_name": "Cisco AIR-AP-2802I-Z-K9-BR",
    "max_workers": 2,
    "noise_factor": 0.05,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7
}
```

## 🎯 Aplicações

- Planejamento de cobertura Wi-Fi em ambientes internos com técnicas de AoA/ToA
- Simulações para projetos de redes sem fio
- Ensino e pesquisa em propagação de sinais, localização e otimização

</details>

<details>
  <summary><strong>🇺🇸 English</strong></summary>

<h1>📡 Wi-Fi Coverage Simulator with Router Optimization (AoA/ToA)</h1>

This module simulates indoor Wi-Fi coverage using **Angle of Arrival (AoA)** and **Time of Arrival (ToA)** techniques, based on a **weighted graph** (generated from a floor plan). The system calculates signal propagation considering obstacles (walls, doors, windows, etc.), distance, and AoA/ToA effects, automatically searching for the best router positions to maximize coverage and signal strength (RSSI).

## 📌 Visual Example

### Input Graph

The weighted graph must be previously generated by the "Graph Creator" module and saved as `.graphml`.

![Graph](https://github.com/LazaroJPR/TCC/blob/main/Dados/Grafos/Salas%20Professores.png)

### Simulation Result

The simulator generates coverage images, highlighting signal intensity at each point and the optimal router positions.

![Generated Simulation](https://github.com/LazaroJPR/TCC/blob/main/Dados/Simula%C3%A7%C3%B5es/Salas%20Professores/5%20roteadores/solucao_1/cobertura_1.png)

## ⚙️ Main Parameters

| Parameter                | Description                                         |
|--------------------------|-----------------------------------------------------|
| rssi_threshold           | Minimum RSSI to consider coverage                   |
| tx_power                 | Router transmit power (dBm)                         |
| freq_mhz                 | Wi-Fi frequency (MHz)                               |
| scale_factor             | Scale factor for visualization                      |
| distance_conversion      | Conversion factor from graph unit to meters         |
| max_iter                 | Number of optimization iterations                   |
| top_n                    | Number of best solutions saved                      |
| weight_colors            | Edge weight colors                                  |
| plot_save_path           | Folder to save results and images                   |
| precomputation_save_path | Folder to save precomputed data                     |
| num_roteadores           | Number of routers to place                          |
| router_name              | Router name/model                                   |
| max_workers              | Maximum number of parallel threads/processes        |
| noise_factor             | Noise factor for ToA simulation                     |
| avg_rssi_weight          | Weight of average RSSI in objective function        |
| coverage_weight          | Weight of coverage in objective function            |

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

### ToA/AoA Precomputation

To speed up simulations on large graphs, you can precompute all pairs of **Time of Arrival (ToA)** and **Angle of Arrival (AoA)** data using the `precompute_aoa_toa.py` script. This generates a compressed file with the results, which can be reused in future runs.

**How to use:**
1. Run the script:
   ```bash
   python precompute_aoa_toa.py
   ```
2. Select the `.graphml` graph file when prompted.
3. The script will compute and save a `.pkl.gz` file with ToA/AoA data.
4. When running the simulator, select this file when prompted to load precomputed data.

> Precomputation is recommended for large environments or repeated simulations, as it significantly reduces execution time.

## 🚀 Features

- Load weighted graphs in `.graphml`
- Simulate Wi-Fi signal propagation considering obstacles, AoA and ToA
- Automatic router position optimization (parallelized)
- Generate coverage images and export best results in `.zip`
- Fully configurable via `config.json`
- **Interactive mode:** Manually place and move routers with instant coverage and RSSI feedback (`AoA_ToA_interactive.py`)

## 📦 How to Use

1. Generate the weighted graph from the floor plan using the "Graph Creator" module.
2. Adjust desired parameters in `config.json`.
3. For automatic simulation, run:
   ```bash
   python AoA_ToA.py
   ```
   For interactive simulation, run:
   ```bash
   python AoA_ToA_interactive.py
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
    "precomputation_save_path": "C:\\Path\\to\\save",
    "num_roteadores": 2,
    "router_name": "Cisco AIR-AP-2802I-Z-K9-BR",
    "max_workers": 2,
    "noise_factor": 0.05,
    "avg_rssi_weight": 0.3,
    "coverage_weight": 0.7
}
```

## 🎯 Applications

- Wi-Fi coverage planning for indoor environments using AoA/ToA techniques
- Simulations for wireless network projects
- Teaching and research in signal propagation, localization, and optimization

</details>
