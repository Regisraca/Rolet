import os
import csv
import json
import time
import logging
import urllib.request
import urllib.parse
import threading
import warnings
import subprocess
import math
from datetime import datetime
from typing import Any
import tkinter as tk
from tkinter import messagebox, ttk
from playwright.sync_api import sync_playwright
import sqlite3
from datetime import date, datetime
def inicializar_banco():
    conn = sqlite3.connect('gestao_banca.db')
    cursor = conn.cursor()
    # Cria a tabela para guardar o histórico dos dias, garantindo que a data seja única
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_registro DATE UNIQUE,
            mes_ano TEXT,
            lucro REAL
        )
    ''')
    conn.commit()
    conn.close()

# Executa a função imediatamente ao abrir o script
inicializar_banco()
try:
    import winsound
except ImportError:
    winsound = None

logging.basicConfig(
    filename='bot_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

warnings.filterwarnings("ignore")

APP_NOME = "RÉGIS CUNHA ROLETA"
APP_VERSAO = "v19.0"

CONFIG_FILE = "config.json"
FAVORITOS_FILE = "favoritos.json"
AUDIT_FILE = "sessao_historico.json"
RELATORIOS_DIR = "relatorios"

# Blindagem de conexão: tempo máximo (s) sem novos números antes de reciclar a mesa
TIMEOUT_SEM_LEITURA = 180
# Limites de memória para sessões longas (evita crescimento infinito de widgets/séries)
MAX_ENTRADAS_HISTORICO = 300
MAX_PONTOS_GRAFICO = 60

TAGS_VALIDAS = {
    "R", "B", "D1", "D2", "D3", "C1", "C2", "C3", 
    "P", "O", "L", "H", "N", "P1", "P2", "P3", 
    "T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"
}.union({str(i) for i in range(37)})

VERMELHOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

SETORES_FISICOS = {
    "P1": {0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27},
    "P2": {13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1},
    "P3": {20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26}
}

TERMINAIS_MAP = {
    "T0": ["0", "10", "20", "30"],
    "T1": ["1", "11", "21", "31"],
    "T2": ["2", "12", "22", "32"],
    "T3": ["3", "13", "23", "33"],
    "T4": ["4", "14", "24", "34"],
    "T5": ["5", "15", "25", "35"],
    "T6": ["6", "16", "26", "36"],
    "T7": ["7", "17", "27"],
    "T8": ["8", "18", "28"],
    "T9": ["9", "19", "29"]
}

# Quantos números cada tag cobre na mesa (usado para medir risco/cobertura real)
NUMEROS_POR_TAG = {}

# ORDEM FÍSICA DA ROLETA EUROPEIA
RODA_EUROPEIA = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

class RoletaAoVivo:
    def __init__(self, master, app_ref):
        self.app = app_ref
        self.top = tk.Toplevel(master)
        self.top.title(f"{APP_NOME} {APP_VERSAO} • ROLETA AO VIVO")
        self.top.geometry("1180x900")
        self.top.minsize(1080, 700)
        self.top.configure(bg="#070A10")
        self.top.protocol("WM_DELETE_WINDOW", self.esconder)

   # 🎨 PALETA PREMIUM COM CORES VIVAS
        self.bg = "#070A10"
        self.panel = "#0D111B"
        self.panel3 = "#0A0F17"
        self.panel2 = "#111827"
        self.border = "#1E293B"
        self.text = "#E5E7EB"
        self.muted = "#718096"
        self.cyan = "#22D3EE"
        self.green = "#34D399"
        self.amber = "#FBBF24"
        self.red = "#FB7185"
        self.purple = "#A78BFA"
        self.neon_green = "#00FF88"
        self.neon_red = "#FF1744"
        self.glow_cyan = "#00FFFF"

        # ── SISTEMA DE SCROLL (ROLETA) ──
        self.main_canvas = tk.Canvas(self.top, bg=self.bg, highlightthickness=0)
        self.main_scrollbar = ttk.Scrollbar(self.top, orient="vertical", command=self.main_canvas.yview)
        
        shell = tk.Frame(self.main_canvas, bg=self.bg)
        self.shell_window = self.main_canvas.create_window((0, 0), window=shell, anchor="nw")
        
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)
        self.main_canvas.pack(side="left", fill="both", expand=True)
        self.main_scrollbar.pack(side="right", fill="y")
        
        def configure_shell(event):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        def configure_canvas(event):
            self.main_canvas.itemconfig(self.shell_window, width=event.width)
            
        shell.bind("<Configure>", configure_shell)
        self.main_canvas.bind("<Configure>", configure_canvas)

        def _on_mousewheel_roleta(event):
            widget = event.widget
            if isinstance(widget, (tk.Listbox, tk.Text)):
                return
            if widget.winfo_toplevel() == self.top:
                self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                
        self.top.bind_all("<MouseWheel>", _on_mousewheel_roleta, add="+")

        # Container Principal
        pad_frame = tk.Frame(shell, bg=self.bg)
        pad_frame.pack(fill="both", expand=True, padx=16, pady=16)

# --- HEADER COM CORES E GLOW ---
        header = tk.Frame(pad_frame, bg=self.bg)
        header.pack(fill="x", pady=(0, 12))

# Header com borda glow
        header_bg = tk.Frame(header, bg=self.panel, highlightbackground=self.glow_cyan, highlightthickness=2)
        header_bg.pack(fill="x", padx=2, pady=2)

        title_box = tk.Frame(header_bg, bg=self.panel)
        title_box.pack(fill="x", padx=16, pady=(12, 8))

# Título com neon
        tk.Label(title_box, text="🎰 PAINEL DA ROLETA AO VIVO", bg=self.panel, 
         fg=self.glow_cyan, font=("Segoe UI", 18, "bold")).pack(anchor="w")

# Subtítulo colorido
        sub_frame = tk.Frame(title_box, bg=self.panel)
        sub_frame.pack(anchor="w", pady=(2, 0))

        tk.Label(sub_frame, text="⚡ TERMINAL DE OPERAÇÕES", bg=self.panel, fg=self.neon_green, 
         font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(sub_frame, text=" & ", bg=self.panel, fg=self.muted, 
         font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(sub_frame, text="INTELIGÊNCIA", bg=self.panel, fg=self.glow_cyan, 
         font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(sub_frame, text="LABORATÓRIO", bg=self.panel, fg=self.amber, 
         font=("Segoe UI", 9, "bold")).pack(side="left")

# Status com indicador animado
        status_frame = tk.Frame(title_box, bg="#0A2224", highlightbackground=self.glow_cyan, 
                       highlightthickness=1)
        status_frame.pack(side="right", padx=(10, 0))

        self.status_dot = tk.Label(status_frame, text="●", bg="#0A2224", 
                           fg=self.neon_green, font=("Segoe UI", 14, "bold"))
        self.status_dot.pack(side="left", padx=(8, 2))

        tk.Label(status_frame, text=" SYSTEM ONLINE ", bg="#0A2224", 
         fg=self.text, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))

# Botão de Gestão de Banca (Onde você desenhou o quadrado vermelho)
        self.btn_abrir_gestao = tk.Button(title_box, text="📈 GESTÃO DE BANCA", 
                                          command=lambda: GestaoBancaDashboard(self.top, self.app), 
                                          bg="#D97706", fg="#FFFFFF", activebackground="#F59E0B", 
                                          activeforeground="#FFFFFF", relief="flat", bd=0, 
                                          font=("Segoe UI", 8, "bold"), cursor="hand2", padx=12, pady=6)
        self.btn_abrir_gestao.pack(side="right", padx=(0, 10))
        btn_close = tk.Button(title_box, text="✖ FECHAR PAINEL", command=self.esconder, 
                      bg=self.panel2, fg=self.neon_red, activebackground="#240810", 
                      activeforeground="#FDA4AF", relief="flat", bd=0, 
                      font=("Segoe UI", 8, "bold"), cursor="hand2", padx=12, pady=6)
        btn_close.pack(side="right")

        tk.Frame(pad_frame, bg=self.border, height=1).pack(fill="x", pady=(0, 14))

        content = tk.Frame(pad_frame, bg=self.bg)
        content.pack(fill="both", expand=True)

        # --- LADO ESQUERDO: CILINDRO & HISTÓRICO ---
        left = tk.Frame(content, bg=self.bg)
        left.pack(side="left", fill="y", padx=(0, 12))
        tk.Frame(left, width=480, height=1, bg=self.bg).pack() 

        wheel_card = tk.Frame(left, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        wheel_card.pack(fill="x", pady=(0, 10))
        
        wheel_header = tk.Frame(wheel_card, bg=self.panel)
        wheel_header.pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(wheel_header, text="CILINDRO FÍSICO", bg=self.panel, fg=self.cyan, font=("Segoe UI", 10, "bold")).pack(side="left")

        self.canvas = tk.Canvas(wheel_card, width=470, height=470, bg=self.panel, highlightthickness=0, bd=0)
        self.canvas.pack(pady=(10, 10))

        # Esteira de Histórico (Últimos 14)
        history_card = tk.Frame(left, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        history_card.pack(fill="x")
        tk.Label(history_card, text="ÚLTIMOS RESULTADOS", bg=self.panel, fg=self.muted, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
        
        self.canvas_history = tk.Canvas(history_card, width=470, height=50, bg=self.panel, highlightthickness=0, bd=0)
        self.canvas_history.pack(pady=(4, 10))

        # --- LADO DIREITO: DASHBOARD ESTATÍSTICO ---
        right = tk.Frame(content, bg=self.bg)
        right.pack(side="left", fill="both", expand=True)

        # 1. 4 KPI Cards 
        kpi_grid = tk.Frame(right, bg=self.bg)
        kpi_grid.pack(fill="x", pady=(0, 10))
        for c in range(4): kpi_grid.columnconfigure(c, weight=1)

        def _kpi_box(parent, col, title, color):
            box = tk.Frame(parent, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
            box.grid(row=0, column=col, sticky="nsew", padx=(0 if col==0 else 4, 0 if col==3 else 4))
            tk.Label(box, text=title, bg=self.panel, fg=self.muted, font=("Segoe UI", 7, "bold")).pack(anchor="center", pady=(8, 2))
            lbl = tk.Label(box, text="0", bg=self.panel, fg=color, font=("Segoe UI", 16, "bold"))
            lbl.pack(anchor="center", pady=(0, 8))
            return lbl

        self.lbl_v_greens = _kpi_box(kpi_grid, 0, "GREENS", self.green)
        self.lbl_v_reds   = _kpi_box(kpi_grid, 1, "REDS", self.red)
        self.lbl_v_assert = _kpi_box(kpi_grid, 2, "ASSERTIVIDADE", self.cyan)
        self.lbl_v_lucro  = _kpi_box(kpi_grid, 3, "LUCRO VIRTUAL", self.amber)

        # 2. CAIXA DE OPERAÇÃO UNIFICADA (Sinal + Gale)
        self.op_card = tk.Frame(right, bg=self.panel2, highlightbackground=self.border, highlightthickness=1)
        self.op_card.pack(fill="x", pady=(0, 10), ipadx=10, ipady=15)
        
        self.lbl_op_title = tk.Label(self.op_card, text="STATUS DA OPERAÇÃO", bg=self.panel2, fg=self.muted, font=("Segoe UI", 9, "bold"))
        self.lbl_op_title.pack(pady=(0, 5))
        
        self.lbl_op_alvo = tk.Label(self.op_card, text="📡 Escaneando Cilindro...", bg=self.panel2, fg=self.text, font=("Segoe UI", 14, "bold"))
        self.lbl_op_alvo.pack(pady=(0, 5))

        self.lbl_op_desc = tk.Label(self.op_card, text="Aguardando quebra de assimetria institucional.", bg=self.panel2, fg=self.muted, font=("Segoe UI", 10))
        self.lbl_op_desc.pack()

        # 3. GRID DO RAIO-X (3x2) — caixas compactas e simétricas
        stats_card = tk.Frame(right, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        stats_card.pack(fill="x", pady=(0, 10))
        tk.Label(stats_card, text="RAIO-X DA MESA", bg=self.panel, fg=self.cyan, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(12, 8))

        stats_grid = tk.Frame(stats_card, bg=self.panel)
        stats_grid.pack(fill="x", padx=14, pady=(0, 12))
        for c in range(3): stats_grid.columnconfigure(c, weight=1, uniform="raiox")
        for r in range(2): stats_grid.rowconfigure(r, uniform="raiox")

        def _stat_box(parent, row, col, title, attr, color):
            box = tk.Frame(parent, bg=self.panel2, highlightbackground=self.border, highlightthickness=1)
            box.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            tk.Label(box, text=title, bg=self.panel2, fg=self.muted, font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
            lbl = tk.Label(box, text="--", bg=self.panel2, fg=color, font=("Segoe UI", 9, "bold"),
                           justify="left", anchor="nw", height=4)
            lbl.pack(fill="x", padx=8, pady=(0, 6))
            setattr(self, attr, lbl)

        _stat_box(stats_grid, 0, 0, "🔥 PLENOS", "lbl_hot_nums", self.amber)
        _stat_box(stats_grid, 0, 1, "🌀 TERMINAIS", "lbl_terminals", self.cyan)
        _stat_box(stats_grid, 0, 2, "🎨 CORES", "lbl_cores", self.text)
        
        _stat_box(stats_grid, 1, 0, "⚖️ PARIDADE", "lbl_paridade", self.text)
        _stat_box(stats_grid, 1, 1, "📏 DÚZIAS", "lbl_duzias", self.text)
        _stat_box(stats_grid, 1, 2, "📊 COLUNAS", "lbl_colunas", self.text)

        # 4. GRÁFICO DE LUCRO REAL-TIME (Colocado na ordem correta, acima do lab)
        profit_card = tk.Frame(right, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        profit_card.pack(fill="x", pady=(0, 10))
        tk.Label(profit_card, text="📈 CURVA DE LUCRO ", bg=self.panel, fg=self.cyan, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 6))
        
        self.canvas_profit = tk.Canvas(profit_card, width=470, height=100, bg="#0A0F17", highlightthickness=0, bd=0)
        self.canvas_profit.pack(pady=(0, 10))

        # 5. HISTÓRICO DE ENTRADAS DA SESSÃO (auditoria ao vivo)
        entradas_card = tk.Frame(right, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        entradas_card.pack(fill="x", pady=(0, 10))

        entradas_header = tk.Frame(entradas_card, bg=self.panel)
        entradas_header.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(entradas_header, text="HISTÓRICO DE ENTRADAS DA SESSÃO", bg=self.panel, fg=self.cyan,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.lbl_winrate_gale = tk.Label(entradas_header, text="DIRETA 0 • G1 0 • G2 0", bg=self.panel,
                                         fg=self.muted, font=("Consolas", 8, "bold"))
        self.lbl_winrate_gale.pack(side="right")

        entradas_body = tk.Frame(entradas_card, bg=self.panel3, highlightbackground=self.border, highlightthickness=1)
        entradas_body.pack(fill="x", padx=14, pady=(0, 12))

        scroll_entradas = tk.Scrollbar(entradas_body, orient="vertical", bg=self.panel3, troughcolor=self.panel3,
                                       activebackground=self.cyan, bd=0, highlightthickness=0)
        scroll_entradas.pack(side="right", fill="y")

        self.listbox_entradas_sessao = tk.Listbox(
            entradas_body, bg=self.panel3, fg=self.text, font=("Consolas", 8, "bold"),
            bd=0, highlightthickness=0, activestyle="none", selectbackground="#123E42",
            selectforeground=self.text, yscrollcommand=scroll_entradas.set, height=6
        )
        self.listbox_entradas_sessao.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll_entradas.config(command=self.listbox_entradas_sessao.yview)

        # 6. LABORATÓRIO QUANT (AUTÔNOMO)
        quant_card = tk.Frame(right, bg=self.panel, highlightbackground=self.border, highlightthickness=1)
        quant_card.pack(fill="both", expand=True) # Este sim fica com expand=True para ocupar o restinho do rodapé
        tk.Label(quant_card, text="06 • LABORATÓRIO QUANT (AUTÔNOMO)", bg=self.panel, fg=self.purple, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 6))
        
        quant_body = tk.Frame(quant_card, bg=self.panel)
        quant_body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        
        # Listbox de padrões
        list_frame = tk.Frame(quant_body, bg=self.panel3, highlightbackground=self.border, highlightthickness=1)
        list_frame.pack(fill="both", expand=True)
        
        scroll_quant = tk.Scrollbar(list_frame, orient="vertical", bg=self.panel3, troughcolor=self.panel3,
                                   activebackground=self.cyan, bd=0, highlightthickness=0)
        scroll_quant.pack(side="right", fill="y")
        
        self.listbox_quant = tk.Listbox(
            list_frame, bg=self.panel3, fg=self.green, font=("Consolas", 8, "bold"),
            bd=0, highlightthickness=0, activestyle="none", selectbackground="#2D1B4E",
            selectforeground=self.text, yscrollcommand=scroll_quant.set, height=6
        )
        self.listbox_quant.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll_quant.config(command=self.listbox_quant.yview)
        
        # Botão de aplicação
        self.btn_aplicar_quant = tk.Button(quant_body, text="⚡ APLICAR AO ROBÔ", command=self.aplicar_padrao_selecionado,
                                           bg=self.cyan, fg="#041015", activebackground="#67E8F9",
                                           activeforeground="#041015", relief="flat", bd=0, cursor="hand2",
                                           font=("Segoe UI", 9, "bold"), padx=15, pady=6)
        self.btn_aplicar_quant.pack(fill="x", pady=(8, 0))

        # Estado para o gráfico de lucro
        self.historico_lucro_chart = [0.0]

        # Armazenamento temporário para backtest
        self.mesa_info_temp = {}

        # Armazenamento para padrões minerados
        self.padroes_minerados = []

        # Assinaturas de estado para evitar redesenhos redundantes (gerenciador de memória do canvas)
        self._assinatura_cilindro = None
        self._assinatura_grafico = None
        self._assinatura_quant = None

        self.visivel = True
        self.top.update_idletasks()
        self._desenhar_cilindro([], [])
        self._desenhar_historico([])
        self._desenhar_grafico_lucro()
        self._animar_dot_status()

    def esconder(self):
        self.visivel = False
        self.top.withdraw()

    def mostrar(self):
        self.visivel = True
        self.top.deiconify()

    def _animar_dot_status(self):
        """Anima o indicador de status piscando"""
        cores = [self.neon_green, self.glow_cyan, self.amber, self.neon_red]
        idx = 0
        
        def _trocar_dot():
            nonlocal idx
            if not self.visivel:
                return
            try:
                if not self.top.winfo_exists():
                    return
                self.status_dot.config(fg=cores[idx % len(cores)])
                idx += 1
                self.top.after(800, _trocar_dot)
            except (tk.TclError, AttributeError):
                return
        
        _trocar_dot()

    def adicionar_entrada_historico(self, estrategia, numero, resultado, gale, valor):
        """Insere uma entrada liquidada (GREEN/RED) no topo do histórico da sessão."""
        try:
            hora = datetime.now().strftime('%H:%M:%S')
            nivel = "DIRETA" if not gale else f"G{gale}"
            resultado_fmt = str(resultado).upper()
            valor_fmt = f"{float(valor):+.2f}".replace("+", "+R$ ").replace("-", "-R$ ")
            linha = f"[{hora}] {estrategia} | Num: {numero} | {nivel} | {resultado_fmt} ({valor_fmt})"

            self.listbox_entradas_sessao.insert(0, linha)
            cor = self.green if resultado_fmt == "GREEN" else self.red
            self.listbox_entradas_sessao.itemconfig(0, foreground=cor)

            excedente = self.listbox_entradas_sessao.size() - MAX_ENTRADAS_HISTORICO
            if excedente > 0:
                self.listbox_entradas_sessao.delete(MAX_ENTRADAS_HISTORICO, tk.END)
        except Exception as e:
            logging.error(f"Erro ao inserir entrada no histórico da sessão: {e}")

    def atualizar_metricas_gale(self, greens_por_gale):
        """Exibe a eficácia de cada nível de gale (entrada direta, G1, G2...)."""
        try:
            niveis = sorted(greens_por_gale.keys())
            partes = []
            for nivel in niveis:
                rotulo = "DIRETA" if nivel == 0 else f"G{nivel}"
                partes.append(f"{rotulo} {greens_por_gale[nivel]}")
            self.lbl_winrate_gale.config(text=" • ".join(partes) if partes else "SEM GREENS")
        except Exception as e:
            logging.error(f"Erro ao atualizar métricas por gale: {e}")

    def limpar_historico_entradas(self):
        try:
            self.listbox_entradas_sessao.delete(0, tk.END)
            self.historico_lucro_chart = [0.0]
            self._assinatura_grafico = None
            self._desenhar_grafico_lucro()
        except Exception as e:
            logging.error(f"Erro ao limpar histórico de entradas: {e}")

    def _desenhar_historico(self, historico):
        self.canvas_history.delete("all")
        if not historico:
            self.canvas_history.create_text(235, 25, text="📭 SEM DADOS AINDA", 
                                           fill=self.muted, font=("Segoe UI", 8, "bold"))
            return
            
        ultimos = historico[-14:] 
        raio = 14
        espaco = 32
        inicio_x = 235 - ((len(ultimos) * espaco) / 2) + 16
        
        for i, num in enumerate(ultimos):
            cx = inicio_x + (i * espaco)
            cy = 25
            
            if num == 0: 
                cor_bg, cor_fg = self.neon_green, "#000000"
            elif num in VERMELHOS: 
                cor_bg, cor_fg = self.neon_red, "#FFFFFF"
            else: 
                cor_bg, cor_fg = "#1F293B", "#FFFFFF"
            
            borda = self.glow_cyan if i == len(ultimos)-1 else self.border
            espessura = 3 if i == len(ultimos)-1 else 1
            
            if espessura > 2:
                self.canvas_history.create_oval(cx-raio-4, cy-raio-4, cx+raio+4, cy+raio+4, 
                                               outline=borda, width=2, stipple="gray50")
            
            self.canvas_history.create_oval(cx-raio, cy-raio, cx+raio, cy+raio, 
                                           fill=cor_bg, outline=borda, width=espessura)
            self.canvas_history.create_text(cx, cy, text=str(num), fill=cor_fg, 
                                           font=("Segoe UI", 10, "bold"))

    def _desenhar_grafico_lucro(self):
        assinatura = (len(self.historico_lucro_chart),
                      round(self.historico_lucro_chart[-1], 2) if self.historico_lucro_chart else None)
        if assinatura == self._assinatura_grafico:
            return
        self._assinatura_grafico = assinatura

        self.canvas_profit.delete("all")
        
        if not self.historico_lucro_chart or len(self.historico_lucro_chart) < 2:
            self.canvas_profit.create_text(235, 50, text="📊 AGUARDANDO DADOS DE LUCRO", 
                                          fill=self.muted, font=("Segoe UI", 8, "bold"))
            return
        
        canvas_width = 470
        canvas_height = 100
        padding = 10
        
        lucro_atual = self.historico_lucro_chart[-1]
        cor_linha = self.neon_green if lucro_atual >= 0 else self.neon_red
        
        min_val = min(self.historico_lucro_chart)
        max_val = max(self.historico_lucro_chart)
        
        if max_val == min_val:
            max_val += 1
            min_val -= 1
        
        range_val = max_val - min_val
        
        if min_val <= 0 <= max_val:
            zero_y = canvas_height - padding - ((0 - min_val) / range_val) * (canvas_height - 2 * padding)
            self.canvas_profit.create_line(padding, zero_y, canvas_width - padding, zero_y, 
                                          fill=self.border, width=1, dash=(2, 2))
        
        pontos = []
        num_pontos = len(self.historico_lucro_chart)
        
        for i, valor in enumerate(self.historico_lucro_chart):
            x = padding + (i / (num_pontos - 1)) * (canvas_width - 2 * padding)
            y = canvas_height - padding - ((valor - min_val) / range_val) * (canvas_height - 2 * padding)
            pontos.append((x, y))
        
        if len(pontos) >= 2:
            # Sombra da linha
            shadow_points = [(x, y+2) for x, y in pontos]
            self.canvas_profit.create_line(shadow_points, fill="#000000", width=4, smooth=True)
            
            self.canvas_profit.create_line(pontos, fill=cor_linha, width=3, smooth=True)
            self.canvas_profit.create_line(pontos, fill=cor_linha, width=1, smooth=True, stipple="gray25")
            
            ultimo_x, ultimo_y = pontos[-1]
            for r in range(3):
                self.canvas_profit.create_oval(ultimo_x-r*3, ultimo_y-r*3, 
                                              ultimo_x+r*3, ultimo_y+r*3, 
                                              fill="", outline=cor_linha, width=1, stipple="gray50")
            self.canvas_profit.create_oval(ultimo_x-4, ultimo_y-4, ultimo_x+4, ultimo_y+4, 
                                          fill=cor_linha, outline="")
            
            self.canvas_profit.create_text(ultimo_x + 10, ultimo_y, text=f"{lucro_atual:+.2f}", 
                                          fill=cor_linha, font=("Segoe UI", 8, "bold"), anchor="w")
        # Determinar cor baseada no lucro atual
        lucro_atual = self.historico_lucro_chart[-1]
        cor_linha = self.green if lucro_atual >= 0 else self.red
        
        # Calcular escala
        min_val = min(self.historico_lucro_chart)
        max_val = max(self.historico_lucro_chart)
        
        if max_val == min_val:
            max_val += 1
            min_val -= 1
        
        range_val = max_val - min_val
        
        # Desenhar linha zero se estiver no range
        if min_val <= 0 <= max_val:
            zero_y = canvas_height - padding - ((0 - min_val) / range_val) * (canvas_height - 2 * padding)
            self.canvas_profit.create_line(padding, zero_y, canvas_width - padding, zero_y, fill=self.border, width=1, dash=(2, 2))
        
        # Calcular pontos
        pontos = []
        num_pontos = len(self.historico_lucro_chart)
        
        for i, valor in enumerate(self.historico_lucro_chart):
            x = padding + (i / (num_pontos - 1)) * (canvas_width - 2 * padding)
            y = canvas_height - padding - ((valor - min_val) / range_val) * (canvas_height - 2 * padding)
            pontos.append((x, y))
        
        # Desenhar linha
        if len(pontos) >= 2:
            self.canvas_profit.create_line(pontos, fill=cor_linha, width=2, smooth=True)
            
            # Desenhar ponto final
            ultimo_x, ultimo_y = pontos[-1]
            self.canvas_profit.create_oval(ultimo_x-3, ultimo_y-3, ultimo_x+3, ultimo_y+3, fill=cor_linha, outline="")
            
            # Desenhar valor atual
            self.canvas_profit.create_text(ultimo_x + 10, ultimo_y, text=f"{lucro_atual:+.2f}", fill=cor_linha, font=("Segoe UI", 8, "bold"), anchor="w")

    def _desenhar_cilindro(self, historico, alvos_expandidos):
        try: janela = int(self.app.ent_amostra.get().strip())
        except Exception: janela = 60

        assinatura = (janela, len(historico), historico[-1] if historico else None,
                      tuple(sorted(alvos_expandidos or [])))
        if assinatura == self._assinatura_cilindro:
            return
        self._assinatura_cilindro = assinatura

        self.canvas.delete("all")
        cx, cy = 235, 235
        r_out, r_in, r_heat = 205, 158, 98
        passo = 360 / 37
        
        ultimos_amostra = historico[-janela:] if historico else []
        contagem = {n: ultimos_amostra.count(n) for n in range(37)}

        offset_topo = 90 + (passo / 2)

        for i, numero in enumerate(RODA_EUROPEIA):
            angulo_inicio = offset_topo - (i * passo)
            
            if numero == 0: 
                cor_bg = self.neon_green
            elif numero in VERMELHOS: 
                cor_bg = self.neon_red
            else: 
                cor_bg = "#1a1a1a"

            is_alvo = alvos_expandidos and str(numero) in alvos_expandidos
            cor_borda = self.glow_cyan if is_alvo else "#1a1a1a"
            largura_borda = 3 if is_alvo else 1

            self.canvas.create_arc(cx-r_out, cy-r_out, cx+r_out, cy+r_out, 
                                  start=angulo_inicio, extent=-passo, 
                                  fill=cor_bg, outline=cor_borda, width=largura_borda)
            
            hits = contagem.get(numero, 0)
            cor_heat = self.panel2 if hits == 0 else "#0055ff" if hits == 1 else self.amber if hits == 2 else self.neon_red
            self.canvas.create_arc(cx-r_in, cy-r_in, cx+r_in, cy+r_in, 
                                  start=angulo_inicio, extent=-passo, 
                                  fill=cor_heat, outline=self.panel, width=1)
            
            mid_angle = 90 - (i * passo)
            rad = math.radians(mid_angle)
            tx = cx + 181 * math.cos(rad)
            ty = cy - 181 * math.sin(rad)
            
# Força o texto de todos os números a ficarem sempre visíveis e em destaque
            if is_alvo:
                cor_texto = self.glow_cyan
                fonte = ("Segoe UI", 10, "bold")
            elif hits >= 3:
                cor_texto = self.amber
                fonte = ("Segoe UI", 10, "bold")
            else:
                cor_texto = "#ffffff"  # Branco puro para nunca sumir
                fonte = ("Segoe UI", 8, "bold")
            
            self.canvas.create_text(tx, ty, text=str(numero), fill=cor_texto, font=fonte)

        self.canvas.create_oval(cx-r_heat, cy-r_heat, cx+r_heat, cy+r_heat, 
                               fill=self.panel, outline=self.glow_cyan, width=2)
        
        if historico:
            ult = historico[-1]
            if ult in RODA_EUROPEIA:
                idx_ult = RODA_EUROPEIA.index(ult)
                mid_angle_bola = 90 - (idx_ult * passo)
                rad_bola = math.radians(mid_angle_bola)
                bx = cx + 137 * math.cos(rad_bola)
                by = cy - 137 * math.sin(rad_bola)
                
                # Efeito de GLOW na bola
                for r in range(3):
                    self.canvas.create_oval(bx-r*6, by-r*6, bx+r*6, by+r*6, 
                                           fill="", outline=self.glow_cyan, width=1, stipple="gray50")
                
                self.canvas.create_oval(bx-6, by-6, bx+6, by+6, fill="#000000", outline="")
                self.canvas.create_oval(bx-5, by-5, bx+5, by+5, fill=self.glow_cyan, outline="#FFFFFF", width=2)
                self.canvas.create_oval(bx-2, by-4, bx+1, by-1, fill="#FFFFFF", outline="", stipple="gray25")

            self.canvas.create_text(cx, cy-15, text="⚡ ÚLTIMO", fill=self.glow_cyan, 
                                   font=("Segoe UI", 8, "bold"))
            
            if ult == 0:
                cor_ult = self.neon_green
            elif ult in VERMELHOS:
                cor_ult = self.neon_red
            else:
                cor_ult = "#ffffff"
                
            self.canvas.create_text(cx, cy+10, text=str(ult), fill=cor_ult, 
                                   font=("Segoe UI", 28, "bold"))
        else:
            self.canvas.create_text(cx, cy, text="🎰 AGUARDANDO\n GIROS", 
                                   fill=self.muted, font=("Segoe UI", 10, "bold"), justify="center")

    @staticmethod
    def expandir_alvos(alvos):
        """Converte tags de setor/terminal em números plenos, preservando tags externas."""
        expandidos = []
        for alvo in alvos:
            alvo = str(alvo)
            if alvo in SETORES_FISICOS:
                expandidos.extend(str(n) for n in sorted(SETORES_FISICOS[alvo]))
 