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

import multiprocessing
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import logging
import threading
import queue
import os
import sys
import json
import cv2
import re
from PIL import Image, ImageTk

sys.path.append(os.path.join(os.path.dirname(__file__), 'Simulador Distancia Euclidiana'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'Simulador AoA ToA'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'PlantaGrid'))

from euclideanDistance import RouterOptimizer as EuclideanOptimizer
from AoA_ToA import RouterOptimizerAoAToA as AoAOptimizer
from PlantaGrid import JpegToGraph

class QueueHandler(logging.Handler):
    def __init__(self, log_queue, status_update_callback=None):
        super().__init__()
        self.log_queue = log_queue
        self.status_update_callback = status_update_callback

    def emit(self, record):
        formatted_record = self.format(record)
        self.log_queue.put(formatted_record)
        
        if self.status_update_callback:
            message = record.getMessage()
            self.status_update_callback(message)

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador de Otimização de Roteadores")
        
        # Configurar ícones da aplicação
        self.setup_icons()
        
        self.state('zoomed')
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
        
        # Variáveis do PlantaGrid
        self.plantagrid_cell_size_var = tk.StringVar()
        self.plantagrid_concrete_weight_var = tk.StringVar()
        self.plantagrid_window_weight_var = tk.StringVar()
        self.plantagrid_door_weight_var = tk.StringVar()
        self.plantagrid_mdf_weight_var = tk.StringVar()
        self.plantagrid_save_path_var = tk.StringVar()
        self.plantagrid_canvas_container = None
        
        # Carrega configurações iniciais
        self.load_config_from_file(self.sim_type.get())
        
        # Configura estilos para as seções expansíveis
        self.setup_collapsible_styles()

    def setup_icons(self):
        """Configura os ícones da aplicação (janela e barra de tarefas)"""
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "Logo.png")
            
            if os.path.exists(logo_path):
                logo_image = Image.open(logo_path)
                
                window_icon = logo_image.resize((32, 32), Image.Resampling.LANCZOS)
                self.window_icon_photo = ImageTk.PhotoImage(window_icon)
                
                taskbar_icon = logo_image.resize((16, 16), Image.Resampling.LANCZOS)
                self.taskbar_icon_photo = ImageTk.PhotoImage(taskbar_icon)
                
                self.iconphoto(True, self.window_icon_photo, self.taskbar_icon_photo)
                
                logging.info("Ícones da aplicação carregados com sucesso")
            else:
                logging.warning(f"Arquivo de logo não encontrado: {logo_path}")
                
        except Exception as e:
            logging.error(f"Erro ao carregar ícones da aplicação: {e}")
            # Continua sem ícones se houver erro

    def create_main_tab_widgets(self):
        main_frame = ttk.Frame(self.main_tab, padding="10")
        main_frame.pack(expand=True, fill="both")

        # Frame de controle à esquerda com largura fixa
        control_frame = ttk.LabelFrame(main_frame, text="Configurações da Simulação", padding="10")
        control_frame.pack(side="left", fill="y", padx=10, pady=10)
        control_frame.pack_propagate(False)
        control_frame.configure(width=450)

        # Configuração do Canvas com Scrollbar
        canvas = tk.Canvas(control_frame, width=400, highlightthickness=0)
        scrollbar = ttk.Scrollbar(control_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas_height = canvas.winfo_height()
            content_height = canvas.bbox("all")[3] if canvas.bbox("all") else 0
            if content_height <= canvas_height:
                canvas.yview_moveto(0)

        scrollable_frame.bind("<Configure>", configure_scroll_region)

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width) if canvas.find_all() else None)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        # PlantaGrid
        ttk.Label(scrollable_frame, text="PlantaGrid:", font=("Helvetica", 12, "bold")).pack(pady=(5, 10), anchor="w")
        
        self.plantagrid_button = ttk.Button(scrollable_frame, text="Converter Planta Arquitetônica", command=self.show_plantagrid_interface)
        self.plantagrid_button.pack(pady=(0, 10), fill="x")

        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', pady=15)

        # Tipo de simulação
        ttk.Label(scrollable_frame, text="Tipo de Simulação:", font=("Helvetica", 12, "bold")).pack(pady=(5, 10), anchor="w")
        
        self.sim_type = tk.StringVar(value="euclidean")
        ttk.Radiobutton(scrollable_frame, text="Distância Euclidiana", variable=self.sim_type, value="euclidean", command=self.update_config_visibility).pack(anchor="w", padx=10)
        ttk.Radiobutton(scrollable_frame, text="AoA / ToA", variable=self.sim_type, value="aoa_toa", command=self.update_config_visibility).pack(anchor="w", padx=10)

        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', pady=15)

        # Configurações Gerais
        general_section = self.create_collapsible_section(scrollable_frame, "Configurações Gerais", True)
        
        ttk.Label(general_section, text="Potência do Roteador (dBm):").pack(pady=(5, 2), anchor="w")
        self.tx_power_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.tx_power_var, "23", width=20).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(general_section, text="Frequência do Sinal (MHz):").pack(pady=(5, 2), anchor="w")
        self.freq_mhz_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.freq_mhz_var, "2400", width=20).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(general_section, text="Modelo do Roteador:").pack(pady=(5, 2), anchor="w")
        self.router_name_var = tk.StringVar()
        self.create_placeholder_entry(general_section, self.router_name_var, "Cisco AIR-AP-2802I-Z-K9-BR", width=35).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(general_section, text="Local para salvar arquivo:").pack(pady=(5, 2), anchor="w")
        path_frame = ttk.Frame(general_section)
        path_frame.pack(fill="x", pady=(0, 5), padx=10)
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
        self.plot_save_path_var = tk.StringVar(value=desktop_path)
        ttk.Entry(path_frame, textvariable=self.plot_save_path_var, width=25).pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="Procurar", command=self.browse_save_path, width=10).pack(side="right", padx=(5, 0))

        # Peso dos Materiais
        materials_section = self.create_collapsible_section(scrollable_frame, "Peso dos Materiais", False)

        ttk.Label(materials_section, text="Concreto (Azul):").pack(pady=(5, 2), anchor="w")
        self.concrete_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.concrete_weight_var, "16.67", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(materials_section, text="Janela (Vermelho):").pack(pady=(5, 2), anchor="w")
        self.window_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.window_weight_var, "7", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(materials_section, text="Porta (Verde):").pack(pady=(5, 2), anchor="w")
        self.door_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.door_weight_var, "6.81", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(materials_section, text="MDF (Amarelo):").pack(pady=(5, 2), anchor="w")
        self.mdf_weight_var = tk.StringVar()
        self.create_placeholder_entry(materials_section, self.mdf_weight_var, "4", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        # Configurações da Otimização
        optimization_section = self.create_collapsible_section(scrollable_frame, "Configurações da Otimização", False)

        ttk.Label(optimization_section, text="Número de Roteadores:").pack(pady=(5, 2), anchor="w")
        self.num_roteadores_var = tk.StringVar()
        self.create_placeholder_entry(optimization_section, self.num_roteadores_var, "2", width=15).pack(pady=(0, 5), anchor="w", padx=10)

        ttk.Label(optimization_section, text="Número de Processos:").pack(pady=(5, 2), anchor="w")
        self.max_workers_var = tk.StringVar()
        self.create_placeholder_entry(optimization_section, self.max_workers_var, "16", width=15).pack(pady=(0, 5), anchor="w", padx=10)

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

        # Controles da simulação interativa
        self.interactive_controls_frame = ttk.LabelFrame(scrollable_frame, text="Controles Interativos", padding="10")
        self.interactive_controls_frame.pack(pady=(10, 0), fill="x")
        self.interactive_controls_frame.pack_forget()
        
        router_slider_frame = ttk.Frame(self.interactive_controls_frame)
        router_slider_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(router_slider_frame, text="Qtd. Roteadores:").pack(side="left", padx=(0, 10))
        self.router_count_var = tk.IntVar(value=2)
        self.router_slider = tk.Scale(router_slider_frame, from_=1, to=10, 
                                     orient=tk.HORIZONTAL, variable=self.router_count_var, 
                                     length=200)
        self.router_slider.pack(side="left", padx=(0, 20))
        
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

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def create_log_tab_widgets(self):
        log_frame = ttk.Frame(self.log_tab, padding="10")
        log_frame.pack(expand=True, fill="both")

        self.log_widget = scrolledtext.ScrolledText(log_frame, state='disabled', wrap=tk.WORD, height=15)
        self.log_widget.pack(expand=True, fill="both", pady=5)

        self.log_queue = queue.Queue()
        self.status_update_callback = None
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

    def clear_interactive_view(self):
        """Limpa a área de visualização interativa, removendo qualquer conteúdo anterior"""
        if self.interactive_canvas_container:
            self.interactive_canvas_container.destroy()
            self.interactive_canvas_container = None
        
        # Também limpa o container do PlantaGrid se existir
        if self.plantagrid_canvas_container:
            self.plantagrid_canvas_container.destroy()
            self.plantagrid_canvas_container = None
        
        # Esconde os controles interativos
        self.interactive_controls_frame.pack_forget()
        self.calc_coverage_button.config(state="disabled")

    def run_simulation(self, target_func, on_finish=None):
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
        self.plantagrid_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self.simulation_thread = None
        logging.info("Simulação concluída ou cancelada.")

    def run_batch_simulation(self):
        try:
            # Limpa a área de visualização antes de iniciar
            self.clear_interactive_view()
            
            config_dict = self.get_config_dict()
            self.save_config_to_file(config_dict, self.sim_type.get())
            
            # Cria a interface de loading para a simulação em lote
            self.interactive_canvas_container = ttk.Frame(self.view_frame)
            self.interactive_canvas_container.pack(expand=True, fill="both")
            
            self.batch_button.config(state="disabled")
            self.interactive_button.config(state="disabled")
            self.plantagrid_button.config(state="disabled")
            self.cancel_button.config(state="normal")
            self.cancel_event.clear()

            loading_frame = ttk.Frame(self.interactive_canvas_container)
            loading_frame.pack(expand=True, fill="both")
            
            loading_label = ttk.Label(loading_frame, text="Executando Otimização de Roteadores...", font=("Helvetica", 16, "bold"))
            loading_label.pack(pady=(100, 20))
            
            status_label = ttk.Label(loading_frame, text="Preparando simulação...", font=("Helvetica", 12))
            status_label.pack(pady=10)
            
            progress_bar = ttk.Progressbar(loading_frame, mode='indeterminate')
            progress_bar.pack(pady=20)
            progress_bar.start()
            
            self.update_idletasks()

            def update_batch_status(message):
                """Atualiza o status da simulação em lote na thread principal"""
                def update():
                    if status_label.winfo_exists():
                        status_label.config(text=message)
                        self.update_idletasks()
                self.after(0, update)

            self.status_update_callback = update_batch_status

            def on_batch_finish():
                """Finaliza a interface de loading da simulação em lote"""
                try:
                    progress_bar.stop()
                    loading_frame.destroy()
                    
                    self.status_update_callback = None

                    success_label = ttk.Label(self.interactive_canvas_container, 
                                            text="✓ Otimização concluída com sucesso!", 
                                            font=("Helvetica", 14, "bold"), foreground="green")
                    success_label.pack(pady=50)

                    view_logs_button = ttk.Button(self.interactive_canvas_container, 
                                                text="Visualizar Logs Completos", 
                                                command=lambda: self.notebook.select(self.log_tab))
                    view_logs_button.pack(pady=10)
                    
                except:
                    pass

                self.on_simulation_finish()

            sim_type = self.sim_type.get()
            if sim_type == "euclidean":
                optimizer = EuclideanOptimizer()
                optimizer.num_roteadores = config_dict["num_roteadores"]
                optimizer.max_iter = config_dict["max_iter"]
                optimizer.max_workers = config_dict["max_workers"]
                optimizer.tx_power = config_dict["tx_power"]
                optimizer.freq_mhz = config_dict["freq_mhz"]
                optimizer.router_name = config_dict["router_name"]
                optimizer.plot_save_path = config_dict["plot_save_path"]
                optimizer.weight_colors = {float(k): v for k, v in config_dict["weight_colors"].items()}
                self.run_simulation(lambda: optimizer.run_optimization(cancel_event=self.cancel_event), on_finish=on_batch_finish)
            elif sim_type == "aoa_toa":
                optimizer = AoAOptimizer()
                optimizer.num_roteadores = config_dict["num_roteadores"]
                optimizer.max_iter = config_dict["max_iter"]
                optimizer.max_workers = config_dict["max_workers"]
                optimizer.tx_power = config_dict["tx_power"]
                optimizer.freq_mhz = config_dict["freq_mhz"]
                optimizer.router_name = config_dict["router_name"]
                optimizer.plot_save_path = config_dict["plot_save_path"]
                optimizer.precomputation_save_path = config_dict["precomputation_save_path"]
                optimizer.weight_colors = {float(k): v for k, v in config_dict["weight_colors"].items()}
                self.run_simulation(lambda: optimizer.run_optimization(cancel_event=self.cancel_event), on_finish=on_batch_finish)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
            self.batch_button.config(state="normal")

    def cancel_simulation(self):
        self.cancel_event.set()
        logging.warning("Sinal de cancelamento enviado. Aguardando a simulação terminar...")
        self.cancel_button.config(state="disabled")
        
        self.status_update_callback = None
        
        # Se houver uma thread de simulação em lote ativa, aguarda ela terminar
        if self.simulation_thread and self.simulation_thread.is_alive():
            if self.interactive_canvas_container:
                for widget in self.interactive_canvas_container.winfo_children():
                    widget.destroy()
                
                cancel_label = ttk.Label(self.interactive_canvas_container, 
                                       text="⚠ Simulação cancelada pelo usuário", 
                                       font=("Helvetica", 14, "bold"), foreground="orange")
                cancel_label.pack(pady=50)
        else:
            pass

    def run_interactive_simulation(self):
        try:
            # Limpa a área de visualização antes de iniciar
            self.clear_interactive_view()
            
            config_dict = self.get_config_dict()
            self.save_config_to_file(config_dict, self.sim_type.get())
            
            self.interactive_canvas_container = ttk.Frame(self.view_frame)
            self.interactive_canvas_container.pack(expand=True, fill="both")

            sim_type = self.sim_type.get()
            optimizer = EuclideanOptimizer() if sim_type == "euclidean" else AoAOptimizer()
            
            # Aplica os valores da interface diretamente no otimizador
            optimizer.num_roteadores = config_dict["num_roteadores"]
            optimizer.max_iter = config_dict["max_iter"]
            optimizer.max_workers = config_dict["max_workers"]
            optimizer.tx_power = config_dict["tx_power"]
            optimizer.freq_mhz = config_dict["freq_mhz"]
            optimizer.router_name = config_dict["router_name"]
            optimizer.plot_save_path = config_dict["plot_save_path"]
            optimizer.weight_colors = {float(k): v for k, v in config_dict["weight_colors"].items()}
            
            # Para AoA_ToA, aplica também o caminho de pré-computação
            if sim_type == "aoa_toa":
                optimizer.precomputation_save_path = config_dict["precomputation_save_path"]

            try:
                G = optimizer.load_graph()
                if not G:
                    self.on_interactive_finish()
                    return
            except RuntimeError:
                self.on_interactive_finish()
                return
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {str(e)}")
            return

        # Desabilitar botões e habilitar cancelar durante pré-computação
        self.batch_button.config(state="disabled")
        self.interactive_button.config(state="disabled")
        self.plantagrid_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.cancel_event.clear()
        
        loading_frame = ttk.Frame(self.interactive_canvas_container)
        loading_frame.pack(expand=True, fill="both")
        
        loading_label = ttk.Label(loading_frame, text="Preparando simulador...", font=("Helvetica", 16))
        loading_label.pack(pady=(100, 20))
        
        status_label = ttk.Label(loading_frame, text="Verificando dados disponíveis...", font=("Helvetica", 12))
        status_label.pack(pady=10)
        
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

        self.status_update_callback = update_loading_status

        def setup_simulation_thread():
            """Thread para fazer o trabalho pesado (pré-computação) e depois criar a UI."""
            
            try:
                if self.cancel_event.is_set():
                    logging.info("Simulação cancelada antes de iniciar.")
                    self.after(0, create_interactive_gui)
                    return
                
                # Se for AoA-ToA, faz a pré-computação dos dados ToA/AoA
                if sim_type == "aoa_toa":
                    update_loading_status("Verificando dados ToA/AoA...")
                    nodes = list(G.nodes())
                    
                    # Configura callback para atualizar status durante pré-computação
                    original_callback = getattr(optimizer.precompute_helper, 'status_callback', None)
                    original_cancel_event = getattr(optimizer.precompute_helper, 'cancel_event', None)
                    
                    optimizer.precompute_helper.status_callback = update_loading_status
                    optimizer.precompute_helper.cancel_event = self.cancel_event
                    
                    try:
                        # Chama a geração/carregamento de dados ToA/AoA
                        logging.info("Iniciando geração/carregamento de dados ToA/AoA...")
                        optimizer.toa_data, optimizer.aoa_data, _ = optimizer.generate_toa_aoa_data(
                            G, nodes, 
                            use_precomputed=True, 
                            force_precompute=False
                        )
                        
                        if not optimizer.toa_data:
                            raise RuntimeError("Erro ao gerar/carregar dados ToA/AoA")
                        
                        logging.info(f"Dados ToA/AoA carregados: {len(optimizer.toa_data)} pares")
                        
                    except Exception as e:
                        # Restaura callback e cancel_event originais
                        optimizer.precompute_helper.status_callback = original_callback
                        optimizer.precompute_helper.cancel_event = original_cancel_event
                        if "cancelada" in str(e).lower() or self.cancel_event.is_set():
                            raise RuntimeError("Pré-computação cancelada pelo usuário")
                        else:
                            raise e
                    finally:
                        # Restaura callback e cancel_event originais
                        optimizer.precompute_helper.status_callback = original_callback
                        optimizer.precompute_helper.cancel_event = original_cancel_event
                
                if self.cancel_event.is_set():
                    logging.info("Simulação cancelada antes de criar interface.")
                    self.after(0, create_interactive_gui)
                    return
                
                update_loading_status("Criando interface interativa...")
                
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
                        self.plantagrid_button.config(state="normal")
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
                    self.plantagrid_button.config(state="normal")
                    self.cancel_button.config(state="disabled")
                    logging.error(f"Erro na preparação da simulação interativa: {e}")
                
                self.after(0, show_error)

        def create_interactive_gui():
            """Cria a GUI interativa após os dados estarem prontos."""
            try:
                progress_bar.stop()
                loading_frame.destroy()
                
                self.status_update_callback = None
                
                if self.cancel_event.is_set():
                    logging.info("Criação da GUI cancelada.")
                    self.on_interactive_finish()
                    return
                
                def setup_interactive_controls(router_count_var, min_routers, max_routers, 
                                             on_slider_change, calculate_coverage, calc_button_ref):
                    self.router_slider.config(from_=min_routers, to=max_routers, 
                                            command=on_slider_change)
                    self.router_count_var.set(router_count_var.get())
                    
                    def sync_vars(*args):
                        router_count_var.set(self.router_count_var.get())
                    self.router_count_var.trace('w', sync_vars)
                    
                    self.calc_coverage_button.config(command=calculate_coverage, state="normal")
                    calc_button_ref[0] = self.calc_coverage_button
                    
                    self.interactive_controls_frame.pack(pady=(10, 0), fill="x")
                
                optimizer.interactive_router_placement(G, optimizer.num_roteadores, 
                                                     master=self.interactive_canvas_container, 
                                                     controls_callback=setup_interactive_controls)
                
                self.batch_button.config(state="normal")
                self.interactive_button.config(state="normal")
                self.plantagrid_button.config(state="normal")
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
                self.plantagrid_button.config(state="normal")
                self.cancel_button.config(state="disabled")

        threading.Thread(target=setup_simulation_thread, daemon=True).start()

    def on_interactive_finish(self):
        """Chamado para limpar a UI após a simulação interativa ser fechada ou falhar ao carregar."""
        self.status_update_callback = None
        
        # Usa o método centralizado de limpeza
        self.clear_interactive_view()
        
        self.batch_button.config(state="normal")
        self.interactive_button.config(state="normal")
        self.plantagrid_button.config(state="normal")

    def on_closing(self):
        if messagebox.askokcancel("Sair", "Deseja sair do simulador?"):
            try:
                self.cancel_event.set()
                
                if self.simulation_thread and self.simulation_thread.is_alive():
                    self.simulation_thread.join(timeout=2)
                
                self.quit()
                self.destroy()
                
            except Exception as e:
                logging.error(f"Erro ao fechar aplicação: {e}")
            finally:
                os._exit(0)

    def handle_status_update(self, log_message):
        """Intercepta mensagens de log para atualizar o status de loading durante simulações."""
        if not self.status_update_callback:
            return
        
        # Para simulação interativa, usa as mensagens específicas traduzidas
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
        
        # Verifica se é uma mensagem traduzida para simulação interativa
        translated_message = None
        for pattern, status in status_messages.items():
            if pattern in log_message:
                if callable(status):
                    translated_message = status(log_message)
                else:
                    translated_message = status
                break
        
        # Se encontrou uma tradução, usa ela; senão, usa a mensagem original do log
        if translated_message:
            self.status_update_callback(translated_message)
        else:
            # Para simulação em lote, mostra diretamente a última linha do log
            # Remove o timestamp e nível do log para ficar mais limpo
            clean_message = re.sub(r'^\[.*?\]\s*\w+\s*-\s*', '', log_message)
            if clean_message.strip():
                self.status_update_callback(clean_message.strip())
    
    def _extract_progress_status(self, log_message):
        """Extrai informação de progresso dos logs de pré-computação."""
        match = re.search(r'Progresso:\s*(\d+)%.*?(\d+(?:,\d+)*)/(\d+(?:,\d+)*)\s*pares', log_message)
        if match:
            percent = match.group(1)
            current = match.group(2).replace(',', '')
            total = match.group(3).replace(',', '')
            return f"Processando: {percent}% ({current}/{total} pares)"
        return None

    def update_config_visibility(self):
        """Atualiza a visibilidade das configurações baseada no tipo de simulação"""
        self.load_config_from_file(self.sim_type.get())

    def browse_save_path(self):
        """Abre diálogo para selecionar pasta de salvamento"""
        folder = filedialog.askdirectory(title="Selecione a pasta para salvar os arquivos")
        if folder:
            self.plot_save_path_var.set(folder + "\\")

    def get_config_dict(self):
        """Retorna um dicionário com as configurações atuais"""
        def get_value_or_placeholder(var, placeholder):
            value = var.get()
            return placeholder if value == placeholder else value
        
        save_path = self.plot_save_path_var.get()
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
            "plot_save_path": save_path,
            "precomputation_save_path": save_path
        }

    def save_config_to_file(self, config_dict, sim_type):
        """Salva as configurações no arquivo config.json apropriado"""
        if sim_type == "euclidean":
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador Distancia Euclidiana', 'config.json')
        else:
            config_path = os.path.join(os.path.dirname(__file__), 'Simulador AoA ToA', 'config.json')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_config = {}
        except Exception as e:
            logging.warning(f"Erro inesperado ao carregar config: {e}")
            existing_config = {}
        
        existing_config.update(config_dict)
        
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
                
            def set_value_with_placeholder(var, value, placeholder):
                if value != placeholder:
                    var.set(value)
                else:
                    var.set(placeholder)
                
            set_value_with_placeholder(self.tx_power_var, str(config.get("tx_power", 23)), "23")
            set_value_with_placeholder(self.freq_mhz_var, str(config.get("freq_mhz", 2400)), "2400")
            set_value_with_placeholder(self.router_name_var, config.get("router_name", "Cisco AIR-AP-2802I-Z-K9-BR"), "Cisco AIR-AP-2802I-Z-K9-BR")
            set_value_with_placeholder(self.num_roteadores_var, str(config.get("num_roteadores", 2)), "2")
            set_value_with_placeholder(self.max_workers_var, str(config.get("max_workers", 16)), "16")
            set_value_with_placeholder(self.max_iter_var, str(config.get("max_iter", 500)), "500")
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
            self.plot_save_path_var.set(config.get("plot_save_path", desktop_path))
            
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
            self._set_default_values()
        except json.JSONDecodeError:
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
        
        def on_focus_in(event):
            if textvariable.get() == placeholder_text:
                textvariable.set("")
                entry.configure(foreground='black')
        
        def on_focus_out(event):
            if textvariable.get() == "":
                textvariable.set(placeholder_text)
                entry.configure(foreground='gray')
        
        entry.bind('<FocusIn>', on_focus_in)
        entry.bind('<FocusOut>', on_focus_out)
        
        textvariable.set(placeholder_text)
        entry.configure(foreground='gray')
        
        return entry

    def get_actual_value(self, textvariable, placeholder_text):
        """Retorna o valor real do campo, considerando o placeholder"""
        value = textvariable.get()
        return "" if value == placeholder_text else value

    def create_collapsible_section(self, parent, title, is_open=False):
        """Cria uma seção expansível/recolhível similar ao <details> do HTML"""
        
        section_frame = ttk.Frame(parent)
        section_frame.pack(fill="x", pady=(8, 0))
        
        header_frame = ttk.Frame(section_frame, style='CollapsibleHeader.TFrame')
        header_frame.pack(fill="x", pady=(0, 2))
        
        expanded = tk.BooleanVar(value=is_open)
        
        content_frame = ttk.Frame(section_frame)
        content_frame.configure(padding=(15, 0, 10, 10))
        
        def toggle_section():
            """Alterna entre abrir/fechar a seção"""
            is_expanded = expanded.get()
            expanded.set(not is_expanded)
            
            if expanded.get():
                content_frame.pack(fill="x", pady=(0, 8))
                arrow_label.config(text="▼")
            else:
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
        
        content_header = ttk.Frame(header_frame, style='CollapsibleHeader.TFrame')
        content_header.pack(fill="x", padx=8, pady=8)
        
        arrow_label = ttk.Label(content_header, text="▼" if is_open else "▶", 
                               style='CollapsibleArrow.TLabel')
        arrow_label.pack(side="left", padx=(0, 10))
        arrow_label.bind("<Button-1>", lambda e: toggle_section())
        
        title_label = ttk.Label(content_header, text=title, 
                               style='CollapsibleTitle.TLabel')
        title_label.pack(side="left")
        title_label.bind("<Button-1>", lambda e: toggle_section())
        
        for widget in [header_frame, content_header, arrow_label, title_label]:
            widget.bind("<Enter>", on_header_enter)
            widget.bind("<Leave>", on_header_leave)
            widget.bind("<Button-1>", lambda e: toggle_section())
        
        separator = ttk.Frame(section_frame, height=1, style='CollapsibleHeader.TFrame')
        separator.pack(fill="x", pady=(0, 5))
        
        if is_open:
            content_frame.pack(fill="x", pady=(0, 8))
        
        return content_frame

    def setup_collapsible_styles(self):
        """Configura estilos visuais para as seções expansíveis e remove bordas de foco"""
        style = ttk.Style()
        
        style.configure('CollapsibleHeader.TFrame', 
                       relief='flat', 
                       borderwidth=0)
        
        style.configure('CollapsibleTitle.TLabel', 
                       font=('Segoe UI', 11, 'bold'),
                       foreground='#2c3e50')
        
        style.configure('CollapsibleArrow.TLabel', 
                       font=('Segoe UI', 12),
                       foreground='#6c757d')

    def show_plantagrid_interface(self):
        """Mostra a interface do PlantaGrid na área de visualização"""
        try:
            # Limpa a área de visualização antes de iniciar
            self.clear_interactive_view()
            
            self.plantagrid_canvas_container = ttk.Frame(self.view_frame)
            self.plantagrid_canvas_container.pack(expand=True, fill="both")
            
            # Título
            title_label = ttk.Label(self.plantagrid_canvas_container, 
                                  text="Conversão de Planta Arquitetônica(Padronizada) em Grafo", 
                                  font=("Helvetica", 16, "bold"))
            title_label.pack(pady=(20, 30))
            
            # Frame principal para o formulário
            form_frame = ttk.Frame(self.plantagrid_canvas_container)
            form_frame.pack(pady=20)
            
            # Configurações do Grid
            grid_section = ttk.LabelFrame(form_frame, text="Configurações do Grid", padding="15")
            grid_section.pack(fill="x", pady=(0, 15))
            
            ttk.Label(grid_section, text="Tamanho da Célula (Distância entre nós):").pack(pady=(5, 2), anchor="w")
            cell_size_frame = ttk.Frame(grid_section)
            cell_size_frame.pack(fill="x", pady=(0, 5))
            
            self.plantagrid_cell_size_var = tk.StringVar()
            self.create_placeholder_entry(cell_size_frame, self.plantagrid_cell_size_var, "5", width=10).pack(side="left", padx=(10, 5))
            ttk.Label(cell_size_frame, text="(5 = 50cm, 10 = 1m)", foreground="gray").pack(side="left")
            
            # Peso das Atenuações
            weights_section = ttk.LabelFrame(form_frame, text="Peso das Atenuações (dB/m)", padding="15")
            weights_section.pack(fill="x", pady=(0, 15))
            
            # Frame para organizar os campos em 2 colunas
            weights_grid = ttk.Frame(weights_section)
            weights_grid.pack(fill="x")
            
            # Coluna esquerda
            left_col = ttk.Frame(weights_grid)
            left_col.pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            ttk.Label(left_col, text="Concreto (Azul):").pack(pady=(5, 2), anchor="w")
            self.plantagrid_concrete_weight_var = tk.StringVar()
            self.create_placeholder_entry(left_col, self.plantagrid_concrete_weight_var, "16.67", width=15).pack(pady=(0, 5), anchor="w", padx=10)
            
            ttk.Label(left_col, text="Janela (Vermelho):").pack(pady=(5, 2), anchor="w")
            self.plantagrid_window_weight_var = tk.StringVar()
            self.create_placeholder_entry(left_col, self.plantagrid_window_weight_var, "7", width=15).pack(pady=(0, 5), anchor="w", padx=10)
            
            # Coluna direita
            right_col = ttk.Frame(weights_grid)
            right_col.pack(side="right", fill="x", expand=True)
            
            ttk.Label(right_col, text="Porta (Verde):").pack(pady=(5, 2), anchor="w")
            self.plantagrid_door_weight_var = tk.StringVar()
            self.create_placeholder_entry(right_col, self.plantagrid_door_weight_var, "6.81", width=15).pack(pady=(0, 5), anchor="w", padx=10)
            
            ttk.Label(right_col, text="MDF (Amarelo):").pack(pady=(5, 2), anchor="w")
            self.plantagrid_mdf_weight_var = tk.StringVar()
            self.create_placeholder_entry(right_col, self.plantagrid_mdf_weight_var, "4", width=15).pack(pady=(0, 5), anchor="w", padx=10)
            
            # Local para salvar
            save_section = ttk.LabelFrame(form_frame, text="Local para Salvar", padding="15")
            save_section.pack(fill="x", pady=(0, 15))
            
            ttk.Label(save_section, text="Pasta de destino:").pack(pady=(5, 2), anchor="w")
            path_frame = ttk.Frame(save_section)
            path_frame.pack(fill="x", pady=(0, 5), padx=10)
            
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
            self.plantagrid_save_path_var = tk.StringVar(value=desktop_path)
            ttk.Entry(path_frame, textvariable=self.plantagrid_save_path_var, width=40).pack(side="left", fill="x", expand=True)
            ttk.Button(path_frame, text="Procurar", command=self.browse_plantagrid_save_path, width=10).pack(side="right", padx=(5, 0))
            
            # Botão de conversão
            convert_button = ttk.Button(form_frame, text="Iniciar Conversão", command=self.run_plantagrid_conversion)
            convert_button.pack(pady=20)
            
            # Inicializa valores padrão
            self.plantagrid_cell_size_var.set("5")
            self.plantagrid_concrete_weight_var.set("16.67")
            self.plantagrid_window_weight_var.set("7")
            self.plantagrid_door_weight_var.set("6.81")
            self.plantagrid_mdf_weight_var.set("4")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao criar interface do PlantaGrid: {str(e)}")
            logging.error(f"Erro ao criar interface do PlantaGrid: {e}")

    def browse_plantagrid_save_path(self):
        """Abre diálogo para selecionar pasta de salvamento do PlantaGrid"""
        folder = filedialog.askdirectory(title="Selecione a pasta para salvar os arquivos")
        if folder:
            self.plantagrid_save_path_var.set(folder + os.sep)

    def run_plantagrid_conversion(self):
        """Executa a conversão do PlantaGrid"""
        try:
            image_path = filedialog.askopenfilename(
                title="Selecione a imagem da planta arquitetônica",
                filetypes=[("JPEG files", "*.jpg;*.jpeg"), ("PNG files", "*.png"), ("All files", "*.*")]
            )
            
            if not image_path or not os.path.isfile(image_path):
                return
            
            # Limpa apenas o conteúdo atual do PlantaGrid, não toda a visualização
            if self.plantagrid_canvas_container:
                for widget in self.plantagrid_canvas_container.winfo_children():
                    widget.destroy()
            
            loading_frame = ttk.Frame(self.plantagrid_canvas_container)
            loading_frame.pack(expand=True, fill="both")
            
            loading_label = ttk.Label(loading_frame, text="Convertendo Planta Arquitetônica...", 
                                    font=("Helvetica", 16, "bold"))
            loading_label.pack(pady=(100, 20))
            
            status_label = ttk.Label(loading_frame, text="Iniciando conversão...", 
                                   font=("Helvetica", 12))
            status_label.pack(pady=10)
            
            progress_bar = ttk.Progressbar(loading_frame, mode='indeterminate')
            progress_bar.pack(pady=20)
            progress_bar.start()
            
            self.update_idletasks()
            
            def update_plantagrid_status(message):
                """Atualiza o status do loading na thread principal"""
                def update():
                    if status_label.winfo_exists():
                        status_label.config(text=message)
                self.after(0, update)
            
            previous_callback = self.status_update_callback
            self.status_update_callback = update_plantagrid_status
            
            def conversion_thread():
                """Thread para executar a conversão"""
                try:
                    config = {
                        "cell_size": int(self.get_actual_value(self.plantagrid_cell_size_var, "5") or "5"),
                        "weight_mapping": {
                            "azul": float(self.get_actual_value(self.plantagrid_concrete_weight_var, "16.67") or "16.67"),
                            "vermelho": float(self.get_actual_value(self.plantagrid_window_weight_var, "7") or "7"),
                            "verde": float(self.get_actual_value(self.plantagrid_door_weight_var, "6.81") or "6.81"),
                            "amarelo": float(self.get_actual_value(self.plantagrid_mdf_weight_var, "4") or "4"),
                            "default": 1
                        },
                        "plot_save_path": self.plantagrid_save_path_var.get() or os.path.join(os.path.expanduser("~"), "Desktop") + os.sep
                    }
                    
                    temp_config_path = os.path.join(os.path.dirname(__file__), "PlantaGrid", "temp_config.json")
                    with open(temp_config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=4)
                    
                    processor = JpegToGraph(temp_config_path)
                    
                    img_rgb = processor.load_image(image_path)
                    hsv_img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
                    color_masks = processor.create_color_masks(hsv_img)
                    blockage_mask = processor.create_blockage_mask(img_rgb)
                    
                    nodes = processor.generate_graph_nodes(img_rgb.shape, blockage_mask)
                    G = processor.build_graph(nodes, hsv_img, blockage_mask)
                    
                    processor.visualize_graph(G)
                    processor.export_graph(G)
                    
                    if os.path.exists(temp_config_path):
                        os.remove(temp_config_path)
                    
                    def show_success():
                        progress_bar.stop()
                        loading_frame.destroy()
                        success_label = ttk.Label(self.plantagrid_canvas_container, 
                                                text="Conversão concluída com sucesso!", 
                                                font=("Helvetica", 14, "bold"), 
                                                foreground="green")
                        success_label.pack(pady=(100, 20))
                        
                        info_label = ttk.Label(self.plantagrid_canvas_container, 
                                             text=f"Arquivos salvos em: {processor.plot_save_path}", 
                                             font=("Helvetica", 10))
                        info_label.pack(pady=10)
                        
                        back_button = ttk.Button(self.plantagrid_canvas_container, 
                                               text="Voltar", 
                                               command=self.show_plantagrid_interface)
                        back_button.pack(pady=20)
                    
                    self.after(0, show_success)
                    
                except Exception as e:
                    def show_error():
                        progress_bar.stop()
                        loading_frame.destroy()
                        error_label = ttk.Label(self.plantagrid_canvas_container, 
                                              text=f"Erro na conversão: {str(e)}", 
                                              font=("Helvetica", 12), 
                                              foreground="red")
                        error_label.pack(pady=(100, 20))
                        
                        back_button = ttk.Button(self.plantagrid_canvas_container, 
                                               text="Voltar", 
                                               command=self.show_plantagrid_interface)
                        back_button.pack(pady=20)
                        
                        logging.error(f"Erro na conversão do PlantaGrid: {e}")
                    
                    self.after(0, show_error)
                finally:
                    self.status_update_callback = previous_callback
            
            threading.Thread(target=conversion_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao iniciar conversão: {str(e)}")
            logging.error(f"Erro ao iniciar conversão do PlantaGrid: {e}")

    def setup_collapsible_styles(self):
        """Configura estilos visuais para as seções expansíveis e remove bordas de foco"""
        style = ttk.Style()
        
        style.configure('CollapsibleHeader.TFrame', 
                       relief='flat', 
                       borderwidth=0)
        
        style.configure('CollapsibleTitle.TLabel', 
                       font=('Segoe UI', 11, 'bold'),
                       foreground='#2c3e50')
        
        style.configure('CollapsibleArrow.TLabel', 
                       font=('Segoe UI', 12),
                       foreground='#6c757d')

if __name__ == "__main__":
    # Proteção crítica para multiprocessing em executáveis PyInstaller
    multiprocessing.freeze_support()
    
    app = MainApp()
    app.mainloop()