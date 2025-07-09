"""
Simulador de Otimização de Roteadores - Interface Gráfica Principal

Este módulo implementa a interface gráfica principal para simulações de otimização
de posicionamento de roteadores usando diferentes algoritmos:
- Distância Euclidiana
- Ângulo de Chegada (AoA) e Tempo de Chegada (ToA)

Características principais:
- Interface com abas para simulação e logs
- Simulação em lote e interativa
- Sistema dinâmico de status de loading baseado em logs
- Processamento em threads separadas para não bloquear a UI
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import logging
import threading
import queue
import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), 'Simulador Distancia Euclidiana'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'Simulador AoA ToA'))

from euclideanDistance import RouterOptimizer as EuclideanOptimizer
from AoA_ToA import RouterOptimizerAoAToA as AoAOptimizer

class QueueHandler(logging.Handler):
    def __init__(self, log_queue, status_update_callback=None):
        super().__init__()
        self.log_queue = log_queue
        self.status_update_callback = status_update_callback

    def emit(self, record):
        formatted_record = self.format(record)
        self.log_queue.put(formatted_record)
        
        # Intercepta logs específicos para atualizar o status de loading
        if self.status_update_callback:
            message = record.getMessage()
            self.status_update_callback(message)

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador de Otimização de Roteadores")
        
        # Maximiza a janela para ocupar toda a tela
        self.state('zoomed')  # Para Windows
        # Alternativa para outros sistemas: self.attributes('-zoomed', True)
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        # --- Aba Principal ---
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text='Início')
        self.create_main_tab_widgets()

        # --- Aba de Log ---
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text='Log da Simulação')
        self.create_log_tab_widgets()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.simulation_thread = None
        self.cancel_event = threading.Event()
        
        # Carrega configurações iniciais
        self.load_config_from_file(self.sim_type.get())
        
        # Configura estilos para as seções expansíveis
        self.setup_collapsible_styles()

    def create_main_tab_widgets(self):
        main_frame = ttk.Frame(self.main_tab, padding="10")
        main_frame.pack(expand=True, fill="both")

        # Frame de controle à esquerda com largura fixa
        control_frame = ttk.LabelFrame(main_frame, text="Configurações da Simulação", padding="10")
        control_frame.pack(side="left", fill="y", padx=10, pady=10)
        control_frame.pack_propagate(False)  # Impede que o frame se expanda
        control_frame.configure(width=450)   # Define largura fixa

        # Configuração do Canvas com Scrollbar
        canvas = tk.Canvas(control_frame, width=400, highlightthickness=0)
        scrollbar = ttk.Scrollbar(control_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        def configure_scroll_region(event):
            # Configura a região de scroll
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Reseta a visualização para o topo se não houver necessidade de scroll
            canvas_height = canvas.winfo_height()
            content_height = canvas.bbox("all")[3] if canvas.bbox("all") else 0
            if content_height <= canvas_height:
                canvas.yview_moveto(0)

        scrollable_frame.bind("<Configure>", configure_scroll_region)

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Garante que o scrollable_frame mantenha a largura fixa
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width) if canvas.find_all() else None)

        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Tipo de simulação
        ttk.Label(scrollable_frame, text="Tipo de Simulação:", font=("Helvetica", 12, "bold")).pack(pady=(5, 10), anchor="w")
        
        self.sim_type = tk.StringVar(value="euclidean")
        ttk.Radiobutton(scrollable_frame, text="Distância Euclidiana", variable=self.sim_type, value="euclidean", command=self.update_config_visibility).pack(anchor="w", padx=10)
        ttk.Radiobutton(scrollable_frame, text="AoA / ToA", variable=self.sim_type, value="aoa_toa", command=self.update_config_visibility).pack(anchor="w", padx=10)

        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', pady=15)

        # Configurações Gerais (Expansível - Aberta por padrão)
        general_section = self.create_collapsible_section(scrollable_frame, "Configurações Gerais", True)
        
        # Potência do Roteador
        ttk.Label(general_section, text="Potência do Roteador (dBm):").pack(pady=(5, 2), anchor="w")
        self.tx_power_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.tx_power_var, "23", width=20).pack(pady=(0, 5), anchor="w", padx=10)

        # Frequência do Sinal
        ttk.Label(general_section, text="Frequência do Sinal (MHz):").pack(pady=(5, 2), anchor="w")
        self.freq_mhz_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.freq_mhz_var, "2400", width=20).pack(pady=(0, 5), anchor="w", padx=10)

        # Modelo do Roteador
        ttk.Label(general_section, text="Modelo do Roteador:").pack(pady=(5, 2), anchor="w")
        self.router_name_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.router_name_var, "Cisco AIR-AP-2802I-Z-K9-BR", width=35).pack(pady=(0, 5), anchor="w", padx=10)

        # Local para salvar arquivo
        ttk.Label(general_section, text="Local para salvar arquivo:").pack(pady=(5, 2), anchor="w")
        path_frame = ttk.Frame(general_section)
        path_frame.pack(fill="x", pady=(0, 5), padx=10)
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
        self.plot_save_path_var = tk.StringVar(value=desktop_path)
        ttk.Entry(path_frame, textvariable=self.plot_save_path_var, width=25).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="Procurar", command=self.browse_save_path, width=10).pack(side="right", padx=(5, 0))

        # Peso dos Materiais (Expansível - Fechada por padrão)
        materials_section = self.create_collapsible_section(scrollable_frame, "Peso dos Materiais", False)

        # Concreto (Azul)
        ttk.Label(materials_section, text="Concreto (Azul):").pack(pady=(5, 2), anchor="w")
        self.concrete_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.concrete_weight_var, "16.67", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Janela (Vermelho)
        ttk.Label(materials_section, text="Janela (Vermelho):").pack(pady=(5, 2), anchor="w")
        self.window_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.window_weight_var, "7", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Porta (Verde)
        ttk.Label(materials_section, text="Porta (Verde):").pack(pady=(5, 2), anchor="w")
        self.door_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.door_weight_var, "6.81", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # MDF (Amarelo)
        ttk.Label(materials_section, text="MDF (Amarelo):").pack(pady=(5, 2), anchor="w")
        self.mdf_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.mdf_weight_var, "4", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Configurações da Otimização (Expansível - Fechada por padrão)
        optimization_section = self.create_collapsible_section(scrollable_frame, "Configurações da Otimização", False)

        # Número de Roteadores
        ttk.Label(optimization_section, text="Número de Roteadores:").pack(pady=(5, 2), anchor="w")
        self.num_roteadores_var = tk.StringVar()
        self.create_placeholder_entry(optimization_section, self.num_roteadores_var, "2", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Número de Processos
        ttk.Label(optimization_section, text="Número de Processos:").pack(pady=(5, 2), anchor="w")
        self.max_workers_var = tk.StringVar()
        self.create_placeholder_entry(optimization_section, self.max_workers_var, "16", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Número Máximo de Iterações
        ttk.Label(optimization_section, text="Número Máximo de Iterações:").pack(pady=(5, 2), anchor="w")
        self.max_iter_var = tk.StringVar()
        self.create_placeholder_entry(optimization_section, self.max_iter_var, "500", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', pady=15)

        # Botões
        self.batch_button = ttk.Button(scrollable_frame, text="Iniciar Otimização de Roteadores", command=self.run_batch_simulation)
        self.batch_button.pack(pady=10, fill="x")
        
        self.interactive_button = ttk.Button(scrollable_frame, text="Iniciar Simulação Interativa", command=self.run_interactive_simulation)
        self.interactive_button.pack(pady=10, fill="x")

        self.cancel_button = ttk.Button(scrollable_frame, text="Cancelar Simulação", command=self.cancel_simulation, state="disabled")
        self.cancel_button.pack(pady=10, fill="x")

        # Controles da simulação interativa (inicialmente ocultos)
        self.interactive_controls_frame = ttk.LabelFrame(scrollable_frame, text="Controles Interativos", padding="10")
        self.interactive_controls_frame.pack(pady=(10, 0), fill="x")
        self.interactive_controls_frame.pack_forget()  # Oculta inicialmente
        
        # Slider para quantidade de roteadores
        router_slider_frame = ttk.Frame(self.interactive_controls_frame)
        router_slider_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(router_slider_frame, text="Qtd. Roteadores:").pack(side="left", padx=(0, 10))
        self.router_count_var = tk.IntVar(value=2)
        self.router_slider = tk.Scale(router_slider_frame, from_=1, to=10, 
                                     orient=tk.HORIZONTAL, variable=self.router_count_var, 
                                     length=200)
        self.router_slider.pack(side="left", padx=(0, 20))
        
        # Botão calcular cobertura
        self.calc_coverage_button = ttk.Button(self.interactive_controls_frame, 
                                              text="Calcular Cobertura", 
                                              state="disabled")
        self.calc_coverage_button.pack(pady=(0, 5), fill="x")

        # Frame de visualização à direita   
        self.view_frame = ttk.LabelFrame(main_frame, text="Visualização Interativa", padding="10")
        self.view_frame.pack(side="right", expand=True, fill="both", padx=10, pady=10)
        
        self.interactive_canvas_container = None

        # Configura a visibilidade inicial
        self.update_config_visibility()

        # Bind do scroll do mouse
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def create_log_tab_widgets(self):
        log_frame = ttk.Frame(self.log_tab, padding="10")
        log_frame.pack(expand=True, fill="both")

        self.log_widget = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, height=15)
        self.log_widget.pack(expand=True, fill="both", pady=5)

        self.log_queue = queue.Queue()
        self.status_update_callback = None  # Será definido durante a simulação interativa
        self.queue_handler = QueueHandler(self.log_queue, self.handle_status_update)
        
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        self.queue_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(self.queue_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.after(100, self.poll_log_queue)

    def poll_log_queue(self):
        while True:
            try:
                record = self.log_queue.get(block=False)
            except queue.Empty:
                break
            else:
                self.log_widget.configure(state='normal')
                self.log_widget.insert(tk.END, record + '\n')
                self.log_widget.configure(state='disabled')
                self.log_widget.see(tk.END)
        self.after(100, self.poll_log_queue)

    def run_simulation(self, target_func, on_finish=None):
        self.notebook.select(self.log_tab)
        
        def wrapped_target():
            target_func()
            if on_finish:
                self.after(0, on_finish)

        self.simulation_thread = threading.Thread(target=wrapped_target)
        self.simulation_thread.daemon = True
        self.simulation_thread.start()

    def on_simulation_finish(self):
        self.batch_button.config(state="normal")
        self.interactive_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self.simulation_thread = None
        logging.info("Simulação concluída ou cancelada.")

    def run_batch_simulation(self):
        try:
            # Salva as configurações antes de executar
            config_dict = self.get_config_dict()
            self.save_config_to_file(config_dict, self.sim_type.get())
            
            self.batch_button.config(state="disabled")
            self.interactive_button.config(state="disabled")
            self.cancel_button.config(state="normal")
            self.cancel_event.clear()

            sim_type = self.sim_type.get()
            if sim_type == "euclidean":
                optimizer = EuclideanOptimizer()
                self.run_simulation(lambda: optimizer.run_optimization(cancel_event=self.cancel_event), on_finish=self.on_simulation_finish)
            elif sim_type == "aoa_toa":
                optimizer = AoAOptimizer()
                self.run_simulation(lambda: optimizer.run_optimization(cancel_event=self.cancel_event), on_finish=self.on_simulation_finish)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
            self.batch_button.config(state="normal")

    def cancel_simulation(self):
        # Define o sinal de cancelamento
        self.cancel_event.set()
        logging.warning("Sinal de cancelamento enviado. Aguardando a simulação terminar...")
        self.cancel_button.config(state="disabled")
        
        # Se houver uma thread de simulação em lote ativa, aguarda ela terminar
        if self.simulation_thread and self.simulation_thread.is_alive():
            # Para simulação em lote, apenas aguarda a thread terminar
            pass
        else:
            # Para simulação interativa, força atualização imediata da UI
            # A thread de setup verificará o cancel_event e encerrará adequadamente
            pass

    def run_interactive_simulation(self):
        try:
            # Salva as configurações antes de executar
            config_dict = self.get_config_dict()
            self.save_config_to_file(config_dict, self.sim_type.get())
            
            if self.interactive_canvas_container:
                self.interactive_canvas_container.destroy()
            self.interactive_canvas_container = ttk.Frame(self.view_frame)
            self.interactive_canvas_container.pack(expand=True, fill="both")

            sim_type = self.sim_type.get()
            optimizer = EuclideanOptimizer() if sim_type == "euclidean" else AoAOptimizer()

            try:
                # 1. Carregar o grafo na thread principal (necessário para o diálogo de arquivo)
                G = optimizer.load_graph()
                if not G:
                    self.on_interactive_finish()
                    return
            except RuntimeError:
                # Usuário cancelou a seleção de arquivo
                self.on_interactive_finish()
                return
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
            return

        # 2. Desabilitar botões e habilitar cancelar durante pré-computação
        self.batch_button.config(state="disabled")
        self.interactive_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.cancel_event.clear()
        
        # Frame de loading com componentes visuais
        loading_frame = ttk.Frame(self.interactive_canvas_container)
        loading_frame.pack(expand=True, fill="both")
        
        # Label principal de loading
        loading_label = ttk.Label(loading_frame, text="Preparando simulador...", font=("Helvetica", 16))
        loading_label.pack(pady=(100, 20))
        
        # Label de status específico
        status_label = ttk.Label(loading_frame, text="Verificando dados disponíveis...", font=("Helvetica", 12))
        status_label.pack(pady=10)
        
        # Barra de progresso
        progress_bar = ttk.Progressbar(loading_frame, mode='indeterminate')
        progress_bar.pack(pady=20)
        progress_bar.start()
        
        self.update_idletasks()

        def update_loading_status(message):
            """Atualiza o status do loading na thread principal"""
            def update():
                if status_label.winfo_exists():
                    status_label.config(text=message)
                    self.update_idletasks()
            self.after(0, update)

        # Define o callback de status para esta simulação
        self.status_update_callback = update_loading_status

        def setup_simulation_thread():
            """Thread para fazer o trabalho pesado (pré-computação) e depois criar a UI."""
            
            try:
                # Verifica cancelamento antes de iniciar
                if self.cancel_event.is_set():
                    logging.info("Simulação cancelada antes de iniciar.")
                    self.after(0, create_interactive_gui)
                    return
                
                # 3. Para AoA/ToA, executa a pré-computação com feedback
                if sim_type == "aoa_toa":
                    nodes = list(G.nodes())
                    
                    # Verifica se já tem dados ToA/AoA carregados (em memória ou HDF5)
                    has_data_in_memory = optimizer.toa_data and hasattr(optimizer, 'aoa_data') and optimizer.aoa_data
                    has_hdf5_file = hasattr(optimizer, 'toa_hdf5_file') and optimizer.toa_hdf5_file
                    
                    if not has_data_in_memory and not has_hdf5_file:
                        # Verifica cancelamento antes da pré-computação
                        if self.cancel_event.is_set():
                            logging.info("Simulação cancelada antes da pré-computação.")
                            self.after(0, create_interactive_gui)
                            return
                            
                        # O status será atualizado automaticamente pelos logs
                        
                        # Chama a função que pode solicitar pré-computação com cancel_event
                        result = optimizer.generate_toa_aoa_data(G, nodes, use_precomputed=True, cancel_event=self.cancel_event)
                        
                        # Verifica cancelamento após pré-computação
                        if self.cancel_event.is_set():
                            logging.info("Simulação cancelada após pré-computação.")
                            self.after(0, create_interactive_gui)
                            return
                        
                        if isinstance(result, tuple) and len(result) == 3 and isinstance(result[2], str) and result[2].endswith(".h5"):
                            optimizer.toa_hdf5_file = result[2]
                            optimizer.aoa_data = None
                            update_loading_status("Dados HDF5 carregados com sucesso!")
                        else:
                            optimizer.toa_data, optimizer.aoa_data = result
                            update_loading_status("Dados ToA/AoA gerados com sucesso!")
                    else:
                        update_loading_status("Usando dados já carregados em memória...")
                
                # Verifica cancelamento final antes de criar GUI
                if self.cancel_event.is_set():
                    logging.info("Simulação cancelada antes de criar interface.")
                    self.after(0, create_interactive_gui)
                    return
                
                update_loading_status("Criando interface interativa...")
                
                # 4. Agenda a criação da GUI na thread principal
                self.after(0, create_interactive_gui)
                
            except RuntimeError as e:
                if "cancelada" in str(e).lower():
                    logging.info("Pré-computação cancelada pelo usuário.")
                    self.after(0, create_interactive_gui)
                else:
                    def show_error():
                        progress_bar.stop()
                        loading_frame.destroy()
                        # Limpa o callback de status ao finalizar com erro
                        self.status_update_callback = None
                        error_label = ttk.Label(self.interactive_canvas_container, 
                                              text=f"Erro ao preparar simulação: {str(e)}", 
                                              font=("Helvetica", 12), foreground="red")
                        error_label.pack(pady=50)
                        self.batch_button.config(state="normal")
                        self.interactive_button.config(state="normal")
                        self.cancel_button.config(state="disabled")
                        logging.error(f"Erro na preparação da simulação interativa: {e}")
                    
                    self.after(0, show_error)
            except Exception as e:
                def show_error():
                    progress_bar.stop()
                    loading_frame.destroy()
                    # Limpa o callback de status ao finalizar com erro
                    self.status_update_callback = None
                    error_label = ttk.Label(self.interactive_canvas_container, 
                                          text=f"Erro ao preparar simulação: {str(e)}", 
                                          font=("Helvetica", 12), foreground="red")
                    error_label.pack(pady=50)
                    self.batch_button.config(state="normal")
                    self.interactive_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    logging.error(f"Erro na preparação da simulação interativa: {e}")
                
                self.after(0, show_error)

        def create_interactive_gui():
            """Cria a GUI interativa após os dados estarem prontos."""
            try:
                # Para a barra de progresso e remove o loading
                progress_bar.stop()
                loading_frame.destroy()
                
                # Limpa o callback de status
                self.status_update_callback = None
                
                # Verifica se foi cancelado
                if self.cancel_event.is_set():
                    logging.info("Criação da GUI cancelada.")
                    self.on_interactive_finish()
                    return
                
                # Função callback para configurar os controles da interface
                def setup_interactive_controls(router_count_var, min_routers, max_routers, 
                                             on_slider_change, calculate_coverage, calc_button_ref):
                    # Configura o slider
                    self.router_slider.config(from_=min_routers, to=max_routers, 
                                            command=on_slider_change)
                    self.router_count_var.set(router_count_var.get())
                    
                    # Sincroniza as variáveis
                    def sync_vars(*args):
                        router_count_var.set(self.router_count_var.get())
                    self.router_count_var.trace('w', sync_vars)
                    
                    # Configura o botão de calcular
                    self.calc_coverage_button.config(command=calculate_coverage, state="normal")
                    calc_button_ref[0] = self.calc_coverage_button
                    
                    # Mostra os controles
                    self.interactive_controls_frame.pack(pady=(10, 0), fill="x")
                
                # Cria a interface interativa com callback
                optimizer.interactive_router_placement(G, optimizer.num_roteadores, 
                                                     master=self.interactive_canvas_container, 
                                                     controls_callback=setup_interactive_controls)
                
                # Reabilita os botões
                self.batch_button.config(state="normal")
                self.interactive_button.config(state="normal")
                self.cancel_button.config(state="disabled")
                
            except Exception as e:
                logging.error(f"Erro ao criar interface interativa: {e}")
                # Mostra mensagem de erro
                error_label = ttk.Label(self.interactive_canvas_container, 
                                      text=f"Erro ao criar interface: {str(e)}", 
                                      font=("Helvetica", 12), foreground="red")
                error_label.pack(pady=50)
                self.batch_button.config(state="normal")
                self.interactive_button.config(state="normal")
                self.cancel_button.config(state="disabled")

        # Inicia a thread para setup
        threading.Thread(target=setup_simulation_thread, daemon=True).start()

    def on_interactive_finish(self):
        """Chamado para limpar a UI após a simulação interativa ser fechada ou falhar ao carregar."""
        # Limpa o callback de status
        self.status_update_callback = None
        
        # Oculta os controles interativos
        self.interactive_controls_frame.pack_forget()
        self.calc_coverage_button.config(state="disabled")
        
        if self.interactive_canvas_container:
            self.interactive_canvas_container.destroy()
            self.interactive_canvas_container = None
        self.batch_button.config(state="normal")
        self.interactive_button.config(state="normal")

    def on_closing(self):
        if messagebox.askokcancel("Sair", "Deseja sair do simulador?"):
            self.quit()
            self.destroy()
            os._exit(0)

    def handle_status_update(self, log_message):
        """Intercepta mensagens de log para atualizar o status de loading durante simulações."""
        if not self.status_update_callback:
            return
            
        status_messages = {
            "Solicitando arquivo de dados pré-computados": "Procurando dados pré-computados...",
            "Carregando dados pré-computados de": "Carregando dados pré-computados...",
            "Carregando dados HDF5": "Carregando arquivo de dados...",
            "Lendo dados ToA": "Lendo dados de tempo de chegada (ToA)...",
            "Lendo dados AoA": "Lendo dados de ângulo de chegada (AoA)...",
            "Dados HDF5 carregados em": "Dados carregados com sucesso!",
            "Total de": "Dados carregados com sucesso!",
            "Dados pré-computados carregados com sucesso": "Dados carregados com sucesso!",
            "Nenhum arquivo de pré-computação selecionado": "Iniciando cálculo de novos dados...",
            "Iniciando pré-computação ToA/AoA para": "Iniciando pré-computação de dados...",
            "Este processo pode levar alguns minutos": "Processamento pode demorar alguns minutos...",
            "Iniciando pré-computação paralela para": "Executando pré-computação paralela...",
            "Utilizando": "Configurando processamento paralelo...",
            "Os resultados serão salvos em": "Preparando arquivo de saída...",
            "Dividindo processamento em": "Organizando processamento em grupos...",
            "Progresso:": self._extract_progress_status,
            "Salvando dados pré-computados": "Salvando dados calculados...",
            "Pré-computação HDF5 concluída": "Pré-computação concluída!",
            "Carregando dados recém-computados": "Carregando dados recém-calculados...",
            "Pré-computação e carregamento concluídos": "Dados prontos para uso!"
        }
        
        # Procura por padrões no log e atualiza o status
        for pattern, status in status_messages.items():
            if pattern in log_message:
                if callable(status):
                    status_text = status(log_message)
                else:
                    status_text = status
                    
                if status_text:
                    self.status_update_callback(status_text)
                break
    
    def _extract_progress_status(self, log_message):
        """Extrai informação de progresso dos logs de pré-computação."""
        import re
        # Busca por padrão: "Progresso: XX% | ..."
        match = re.search(r'Progresso:\s*(\d+)%.*?(\d+(?:,\d+)*)/(\d+(?:,\d+)*)\s*pares', log_message)
        if match:
            percent = match.group(1)
            current = match.group(2).replace(',', '')
            total = match.group(3).replace(',', '')
            return f"Processando: {percent}% ({current}/{total} pares)"
        return None

    def update_config_visibility(self):
        """Atualiza a visibilidade das configurações baseada no tipo de simulação"""
        # Carrega as configurações do tipo selecionado
        self.load_config_from_file(self.sim_type.get())

    def browse_save_path(self):
        """Abre diálogo para selecionar pasta de salvamento"""
        folder = filedialog.askdirectory(title="Selecione a pasta para salvar os arquivos")
        if folder:
            self.plot_save_path_var.set(folder + "\\")

    def get_config_dict(self):
        """Retorna um dicionário com as configurações atuais"""
        # Função auxiliar para obter valores com fallback para placeholder
        def get_value_or_placeholder(var, placeholder):
            value = var.get()
            return placeholder if value == placeholder else value
        
        return {
            "tx_power": int(get_value_or_placeholder(self.tx_power_var, "23")),
            "freq_mhz": int(get_value_or_placeholder(self.freq_mhz_var, "2400")),
            "router_name": get_value_or_placeholder(self.router_name_var, "Cisco AIR-AP-2802I-Z-K9-BR"),
            "weight_colors": {
                get_value_or_placeholder(self.concrete_weight_var, "16.67"): "blue",
                get_value_or_placeholder(self.window_weight_var, "7"): "red", 
                get_value_or_placeholder(self.door_weight_var, "6.81"): "green",
                get_value_or_placeholder(self.mdf_weight_var, "4"): "yellow",
                "1": "gray"
            },
            "num_roteadores": int(get_value_or_placeholder(self.num_roteadores_var, "2")),
            "max_workers": int(get_value_or_placeholder(self.max_workers_var, "16")),
            "max_iter": int(get_value_or_placeholder(self.max_iter_var, "500")),
            "plot_save_path": self.plot_save_path_var.get()
        }

    def save_config_to_file(self, config_dict, sim_type):
        """Salva as configurações no arquivo config.json apropriado"""
        if sim_type == "euclidean":
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador Distancia Euclidiana', 'config.json')
        else:
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador AoA ToA', 'config.json')
        
        # Carrega o config existente
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Arquivo não existe ou está vazio/corrompido - cria um novo
            existing_config = {}
        except Exception as e:
            logging.warning(f"Erro inesperado ao carregar config: {e}")
            existing_config = {}
        
        # Atualiza apenas os campos modificáveis
        existing_config.update(config_dict)
        
        # Salva o config atualizado
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(existing_config, f, indent=4)

    def load_config_from_file(self, sim_type):
        """Carrega as configurações do arquivo config.json apropriado"""
        if sim_type == "euclidean":
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador Distancia Euclidiana', 'config.json')
        else:
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador AoA ToA', 'config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Função auxiliar para definir valores com placeholder
            def set_value_with_placeholder(var, value, placeholder):
                if value != placeholder:
                    var.set(value)
                else:
                    var.set(placeholder)
                
            # Atualiza os campos na interface
            set_value_with_placeholder(self.tx_power_var, str(config.get("tx_power", 23)), "23")
            set_value_with_placeholder(self.freq_mhz_var, str(config.get("freq_mhz", 2400)), "2400")
            set_value_with_placeholder(self.router_name_var, config.get("router_name", "Cisco AIR-AP-2802I-Z-K9-BR"), "Cisco AIR-AP-2802I-Z-K9-BR")
            set_value_with_placeholder(self.num_roteadores_var, str(config.get("num_roteadores", 2)), "2")
            set_value_with_placeholder(self.max_workers_var, str(config.get("max_workers", 16)), "16")
            set_value_with_placeholder(self.max_iter_var, str(config.get("max_iter", 500)), "500")
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
            self.plot_save_path_var.set(config.get("plot_save_path", desktop_path))
            
            # Atualiza os pesos dos materiais
            weight_colors = config.get("weight_colors", {})
            for weight, color in weight_colors.items():
                if color == "blue":
                    set_value_with_placeholder(self.concrete_weight_var, weight, "16.67")
                elif color == "red":
                    set_value_with_placeholder(self.window_weight_var, weight, "7")
                elif color == "green":
                    set_value_with_placeholder(self.door_weight_var, weight, "6.81")
                elif color == "yellow":
                    set_value_with_placeholder(self.mdf_weight_var, weight, "4")
                    
        except FileNotFoundError:
            # Arquivo não existe - usa valores padrão silenciosamente
            self._set_default_values()
        except json.JSONDecodeError:
            # Arquivo existe mas está corrompido - usa valores padrão e avisa
            logging.warning("Arquivo config.json corrompido. Usando valores padrão.")
            self._set_default_values()
        except Exception as e:
            logging.warning(f"Erro inesperado ao carregar configurações: {e}")
            self._set_default_values()

    def _set_default_values(self):
        """Define os valores padrão para todos os campos"""
        self.tx_power_var.set("23")
        self.freq_mhz_var.set("2400")
        self.router_name_var.set("Cisco AIR-AP-2802I-Z-K9-BR")
        self.num_roteadores_var.set("2")
        self.max_workers_var.set("16")
        self.max_iter_var.set("500")
        self.concrete_weight_var.set("16.67")
        self.window_weight_var.set("7")
        self.door_weight_var.set("6.81")
        self.mdf_weight_var.set("4")
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
        self.plot_save_path_var.set(desktop_path)

    def create_placeholder_entry(self, parent, textvariable, placeholder_text, width=None, **kwargs):
        """Cria um Entry com placeholder text em cor mais fraca"""
        entry = ttk.Entry(parent, textvariable=textvariable, width=width, **kwargs)
        
        # Configura o placeholder
        def on_focus_in(event):
            if textvariable.get() == placeholder_text:
                textvariable.set("")
                entry.configure(foreground='black')
        
        def on_focus_out(event):
            if textvariable.get() == "":
                textvariable.set(placeholder_text)
                entry.configure(foreground='gray')
        
        # Configura eventos
        entry.bind('<FocusIn>', on_focus_in)
        entry.bind('<FocusOut>', on_focus_out)
        
        # Define o estado inicial
        textvariable.set(placeholder_text)
        entry.configure(foreground='gray')
        
        return entry

    def get_actual_value(self, textvariable, placeholder_text):
        """Retorna o valor real do campo, considerando o placeholder"""
        value = textvariable.get()
        return "" if value == placeholder_text else value

    def create_collapsible_section(self, parent, title, is_open=False):
        """Cria uma seção expansível/recolhível similar ao <details> do HTML"""
        
        # Frame principal da seção
        section_frame = ttk.Frame(parent)
        section_frame.pack(fill="x", pady=(8, 0))
        
        # Frame do cabeçalho (clicável) - design mais limpo
        header_frame = ttk.Frame(section_frame, style='CollapsibleHeader.TFrame')
        header_frame.pack(fill="x", pady=(0, 2))
        
        # Variável para controlar se está aberto/fechado
        expanded = tk.BooleanVar(value=is_open)
        
        # Frame para o conteúdo com padding reduzido
        content_frame = ttk.Frame(section_frame)
        content_frame.configure(padding=(15, 0, 10, 10))
        
        def toggle_section():
            """Alterna entre abrir/fechar a seção"""
            is_expanded = expanded.get()
            expanded.set(not is_expanded)
            
            if expanded.get():
                # Abrir seção
                content_frame.pack(fill="x", pady=(0, 8))
                arrow_label.config(text="▼")
            else:
                # Fechar seção
                content_frame.pack_forget()
                arrow_label.config(text="▶")
        
        def on_header_enter(event):
            """Efeito hover no cabeçalho - mais sutil"""
            title_label.configure(foreground='#495057')
            arrow_label.configure(foreground='#495057')
        
        def on_header_leave(event):
            """Remove efeito hover do cabeçalho"""
            title_label.configure(foreground='#2c3e50')
            arrow_label.configure(foreground='#6c757d')
        
        # Container para a seta e título alinhados
        content_header = ttk.Frame(header_frame, style='CollapsibleHeader.TFrame')
        content_header.pack(fill="x", padx=8, pady=8)
        
        # Seta indicadora (clicável) - ícones mais modernos
        arrow_label = ttk.Label(content_header, text="▼" if is_open else "▶", 
                               style='CollapsibleArrow.TLabel')
        arrow_label.pack(side="left", padx=(0, 10))
        arrow_label.bind("<Button-1>", lambda e: toggle_section())
        
        # Título da seção (clicável) - sem cursor especial
        title_label = ttk.Label(content_header, text=title, 
                               style='CollapsibleTitle.TLabel')
        title_label.pack(side="left")
        title_label.bind("<Button-1>", lambda e: toggle_section())
        
        # Adiciona efeitos hover a todos os elementos
        for widget in [header_frame, content_header, arrow_label, title_label]:
            widget.bind("<Enter>", on_header_enter)
            widget.bind("<Leave>", on_header_leave)
            widget.bind("<Button-1>", lambda e: toggle_section())
        
        # Linha sutil separadora
        separator = ttk.Frame(section_frame, height=1, style='CollapsibleHeader.TFrame')
        separator.pack(fill="x", pady=(0, 5))
        
        # Configura o estado inicial
        if is_open:
            content_frame.pack(fill="x", pady=(0, 8))
        
        return content_frame

    def setup_collapsible_styles(self):
        """Configura estilos visuais para as seções expansíveis e remove bordas de foco"""
        style = ttk.Style()
        
        # Estilo para o frame do cabeçalho - design mais limpo
        style.configure('CollapsibleHeader.TFrame', 
                       relief='flat', 
                       borderwidth=0)
        
        # Estilo para labels do cabeçalho - tipografia moderna
        style.configure('CollapsibleTitle.TLabel', 
                       font=('Segoe UI', 11, 'bold'),
                       foreground='#2c3e50')
        
        style.configure('CollapsibleArrow.TLabel', 
                       font=('Segoe UI', 12),
                       foreground='#6c757d')

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
