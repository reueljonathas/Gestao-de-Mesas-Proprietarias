import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import calendar
import json
import os
from datetime import date, datetime

# Configuração da página
st.set_page_config(page_title="Gestão de Mesas CME", layout="wide", page_icon="📈")

# --- ESTILIZAÇÃO PARA MENU LATERAL EM QUADRADOS ---
st.markdown("""
<style>
    [data-testid="stSidebar"] .stButton > button {
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 10px 16px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        margin-bottom: 4px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE FORMATAÇÃO E CONVERSÃO ---
def fmt_moeda(valor):
    if valor is None or pd.isna(valor):
        return "$ 0,00"
    sinal = "-" if valor < 0 else ""
    val_abs = abs(valor)
    formatado = f"{val_abs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}$ {formatado}"

def fmt_br_input(valor):
    if valor is None or pd.isna(valor):
        return "0,00"
    sinal = "-" if valor < 0 else ""
    val_abs = abs(float(valor))
    formatado = f"{val_abs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}{formatado}"

def fmt_data(data_str):
    if not data_str or pd.isna(data_str):
        return "-"
    try:
        return pd.to_datetime(data_str).strftime("%d/%m/%Y")
    except:
        return str(data_str)

def converter_br_para_float(texto):
    if not texto:
        return 0.0
    limpo = str(texto).replace("R$", "").replace("$", "").strip()
    if "." in limpo and "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except:
        return 0.0

def formatar_duracao(h, m, s):
    partes = []
    if h > 0:
        partes.append(f"{h}h")
    if m > 0 or h > 0:
        partes.append(f"{m}m")
    partes.append(f"{s}s")
    return " ".join(partes)

def descompactar_duracao(dur_str):
    h, m, s = 0, 0, 0
    if not dur_str or pd.isna(dur_str):
        return 0, 0, 0
    dur_str = str(dur_str)
    partes = dur_str.split()
    for p in partes:
        if p.endswith("h"):
            try: h = int(p.replace("h", ""))
            except: pass
        elif p.endswith("m"):
            try: m = int(p.replace("m", ""))
            except: pass
        elif p.endswith("s"):
            try: s = int(p.replace("s", ""))
            except: pass
    if not any(c in dur_str for c in ["h", "m", "s"]):
        try: m = int(dur_str)
        except: pass
    return h, m, s

def duracao_em_segundos(dur_str):
    h, m, s = descompactar_duracao(dur_str)
    return h * 3600 + m * 60 + s

def parse_display_duracao(val):
    if val is None or pd.isna(val):
        return "-"
    s_val = str(val)
    if any(c in s_val for c in ["s", "m", "h"]):
        return s_val
    try:
        num = int(val)
        return f"{num}m"
    except:
        return s_val

# --- BANCO DE DADOS FIXO COM AUTO-MIGRAÇÃO ---
DB_NAME = "mesas_pro.db"

if not os.path.exists(DB_NAME):
    for legado in ["mesas_v5.db", "mesas_v4.db", "mesas.db"]:
        if os.path.exists(legado):
            try:
                import shutil
                shutil.copyfile(legado, DB_NAME)
                break
            except:
                pass

conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    trader TEXT,
    mesa TEXT,
    tamanho_conta TEXT,
    tipo TEXT,
    status TEXT DEFAULT 'Challenge (avaliação)',
    saldo_inicial REAL,
    max_dd REAL,
    limite_diario REAL,
    meta REAL,
    custo_mesa REAL DEFAULT 0.0,
    custo_ativacao REAL DEFAULT 0.0,
    custo_reset REAL DEFAULT 0.0,
    outros_custos REAL DEFAULT 0.0,
    total_saques REAL DEFAULT 0.0,
    data_inicio_janela TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id INTEGER,
    data TEXT,
    ativo TEXT,
    direcao TEXT DEFAULT 'Compra (Long)',
    lotes REAL,
    pontos REAL DEFAULT 0.0,
    custos REAL DEFAULT 0.0,
    resultado REAL,
    duracao_min TEXT,
    estrategia TEXT,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS saques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id INTEGER,
    data_solicitacao TEXT,
    valor REAL,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")

cursor.execute("CREATE TABLE IF NOT EXISTS ativos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS estrategias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")

cursor.execute("PRAGMA table_info(trades)")
t_cols = [r[1] for r in cursor.fetchall()]
if "direcao" not in t_cols:
    cursor.execute("ALTER TABLE trades ADD COLUMN direcao TEXT DEFAULT 'Compra (Long)'")
if "pontos" not in t_cols:
    cursor.execute("ALTER TABLE trades ADD COLUMN pontos REAL DEFAULT 0.0")
if "custos" not in t_cols:
    cursor.execute("ALTER TABLE trades ADD COLUMN custos REAL DEFAULT 0.0")

cursor.execute("SELECT COUNT(*) FROM ativos")
if cursor.fetchone()[0] == 0:
    for a in ["NQ (Nasdaq)", "ES (S&P 500)", "YM (Dow)", "CL (Petróleo)", "GC (Ouro)", "RTY (Russell)"]:
        cursor.execute("INSERT OR IGNORE INTO ativos (nome) VALUES (?)", (a,))

cursor.execute("SELECT COUNT(*) FROM estrategias")
if cursor.fetchone()[0] == 0:
    for e in ["Rompimento", "Pullback / Tendência", "Reversão / VWAP", "Scalping", "Abertura / Notícia"]:
        cursor.execute("INSERT OR IGNORE INTO estrategias (nome) VALUES (?)", (e,))

conn.commit()

# --- CÁLCULO PREGÕES CME RESTANTES ---
def dias_uteis_cme_restantes():
    hoje = date.today()
    _, ultimo_dia = calendar.monthrange(hoje.year, hoje.month)
    uteis = 0
    for d in range(hoje.day, ultimo_dia + 1):
        if date(hoje.year, hoje.month, d).weekday() < 5:
            uteis += 1
    return max(1, uteis)

contas_df = pd.read_sql("SELECT * FROM contas", conn)
trades_df = pd.read_sql("SELECT * FROM trades", conn)
saques_df = pd.read_sql("SELECT * FROM saques", conn)
ativos_df = pd.read_sql("SELECT nome FROM ativos ORDER BY nome ASC", conn)
estrategias_df = pd.read_sql("SELECT nome FROM estrategias ORDER BY nome ASC", conn)

# --- NAVEGAÇÃO LATERAL EM QUADRADOS ---
if "menu" not in st.session_state:
    st.session_state.menu = "📊 Painel Geral"

st.sidebar.markdown("### ⚡ Menu Principal")
opcoes_menu = [
    "📊 Painel Geral",
    "📁 Minhas Contas",
    "💰 Relatório Financeiro",
    "🛡️ Regras e Compliance",
    "💾 Backup",
    "➕ Cadastrar"
]

for op in opcoes_menu:
    is_ativo = (st.session_state.menu == op)
    if st.sidebar.button(
        op,
        key=f"nav_btn_{op}",
        use_container_width=True,
        type="primary" if is_ativo else "secondary"
    ):
        st.session_state.menu = op
        st.rerun()

menu = st.session_state.menu

# =========================================================
# 1. PAINEL GERAL (CONSOLIDADO GLOBAL & RADAR DO DIA)
# =========================================================
if menu == "📊 Painel Geral":
    st.title("📊 Painel Geral Consolidado")
    
    if contas_df.empty:
        st.info("👋 Nenhuma conta cadastrada ainda. Acesse **'➕ Cadastrar'** para começar!")
    else:
        total_saldo_inicial = contas_df["saldo_inicial"].sum()
        total_lucro_global = trades_df["resultado"].sum() if not trades_df.empty else 0.0
        saldo_global_atual = total_saldo_inicial + total_lucro_global
        total_saques_global = contas_df["total_saques"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Resultado Líquido Operacional", fmt_moeda(total_lucro_global), delta=fmt_moeda(total_lucro_global))
        c2.metric("Saldo Total sob Gestão", fmt_moeda(saldo_global_atual))
        c3.metric("Total de Saques Realizados", fmt_moeda(total_saques_global))
        c4.metric("Total de Contas Ativas", len(contas_df))

        st.markdown("---")

        st.subheader("🎯 Radar Diário: Contas Recomendadas para Hoje (Máx 3)")
        st.caption("Foco disciplinado: Evite inatividade de 7 dias e priorize contas que exigem performance.")

        hoje = date.today()
        dias_uteis = dias_uteis_cme_restantes()
        status_contas = []

        for _, c in contas_df.iterrows():
            t_conta = trades_df[trades_df["conta_id"] == c["id"]]
            if not t_conta.empty:
                ult_data = datetime.strptime(t_conta["data"].max(), "%Y-%m-%d").date()
                dias_sem_operar = (hoje - ult_data).days
                operou_hoje = (ult_data == hoje)
            else:
                dias_sem_operar = 99
                operou_hoje = False

            lucro_conta = t_conta["resultado"].sum() if not t_conta.empty else 0.0
            saldo_conta = c["saldo_inicial"] + lucro_conta
            falta_meta = max(0.0, (c["saldo_inicial"] + c["meta"]) - saldo_conta)
            mam = falta_meta / dias_uteis

            score = 0
            if dias_sem_operar >= 5:
                score += 1500 + dias_sem_operar * 50
            elif dias_sem_operar >= 3:
                score += 400 + dias_sem_operar * 20
            if not operou_hoje:
                score += 100
            if falta_meta > 0 and c["meta"] > 0:
                score += min(100, (lucro_conta / c["meta"]) * 100)

            status_contas.append({
                "id": c["id"],
                "identificador": f"{c['nome']} ({c['mesa']})",
                "trader": c["trader"],
                "mesa": c["mesa"],
                "tamanho": c["tamanho_conta"],
                "tipo": c["tipo"],
                "status": c.get("status", "Challenge (avaliação)"),
                "saldo_inicial": c["saldo_inicial"],
                "saldo_atual": saldo_conta,
                "pnl": lucro_conta,
                "falta_meta": falta_meta,
                "mam": mam,
                "dias_sem_operar": dias_sem_operar,
                "operou_hoje": operou_hoje,
                "score": score
            })

        df_radar = pd.DataFrame(status_contas).sort_values(by="score", ascending=False)

        criticas = df_radar[df_radar["dias_sem_operar"] >= 5]
        if not criticas.empty:
            for _, cr in criticas.iterrows():
                dias_txt = "Nunca operada" if cr["dias_sem_operar"] == 99 else f"{cr['dias_sem_operar']} dias sem trade"
                st.error(f"⚠️ **ALERTA CRÍTICO (Regra dos 7 Dias):** A conta **{cr['identificador']}** (Trader: {cr['trader']}) está a **{dias_txt}**! Opere hoje para evitar desclassificação.")

        top3 = df_radar.head(3)
        cols = st.columns(3)
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols[i]:
                titulo = "⭐ MÁXIMA ATENÇÃO: FOCO EM PERFORMANCE" if i == 0 else f"Opção #{i+1} do Dia"
                st.markdown(f"#### {titulo}")
                st.info(f"**{row['identificador']}**\n\n👤 Trader: `{row['trader']}` | Tam: `{row['tamanho']}`\n\n📌 Fase: `{row['status']}`")
                
                d_txt = "Nunca" if row['dias_sem_operar'] == 99 else f"{row['dias_sem_operar']} dias atrás"
                st.write(f"🕒 **Última Operação:** {d_txt}")
                st.metric("Saldo Atual", fmt_moeda(row['saldo_atual']), delta=fmt_moeda(row['pnl']))
                st.metric(f"MAM ({dias_uteis} pregões CME)", f"{fmt_moeda(row['mam'])}/dia")

        st.markdown("---")
        st.subheader("📋 Resumo Consolidado de Todas as Contas")
        
        df_tabela = df_radar.copy()
        df_tabela["Saldo Inicial"] = df_tabela["saldo_inicial"].apply(fmt_moeda)
        df_tabela["Saldo Atual"] = df_tabela["saldo_atual"].apply(fmt_moeda)
        df_tabela["P&L Total"] = df_tabela["pnl"].apply(fmt_moeda)
        df_tabela["Falta p/ Meta"] = df_tabela["falta_meta"].apply(fmt_moeda)
        df_tabela["MAM/Dia"] = df_tabela["mam"].apply(fmt_moeda)

        st.dataframe(
            df_tabela[["identificador", "trader", "mesa", "tamanho", "tipo", "status", "Saldo Inicial", "Saldo Atual", "P&L Total", "Falta p/ Meta", "MAM/Dia"]].rename(
                columns={"identificador": "Conta", "trader": "Trader", "mesa": "Mesa", "tamanho": "Tamanho", "tipo": "Tipo", "status": "Fase"}
            ),
            use_container_width=True
        )

# =========================================================
# 2. MINHAS CONTAS (PAINEL, TRADES, SAQUES E CONFIGURAÇÕES)
# =========================================================
elif menu == "📁 Minhas Contas":
    if contas_df.empty:
        st.title("📁 Minhas Contas")
        st.warning("Cadastre suas contas na aba '➕ Cadastrar' primeiro.")
    else:
        lista_opcoes = [
            f"{c['id']} - {c['nome']} — {c['mesa']} ({c['tamanho_conta']}) | {c['tipo']} [{c['status']}]"
            for _, c in contas_df.iterrows()
        ]
        
        conta_sel = st.selectbox("📂 Selecione a Conta para Acessar:", lista_opcoes)
        c_id = int(conta_sel.split(" - ")[0])
        c = contas_df[contas_df["id"] == c_id].iloc[0]

        status_atual = c.get("status", "Challenge (avaliação)")
        is_financiada = status_atual in ["Funded (Financiada)", "Live (Real)"]

        st.title(f"📈 {c['nome']} — {c['mesa']}")
        st.markdown(f"👤 **Trader:** `{c['trader']}` | **Tamanho:** `{c['tamanho_conta']}` | **Modelo:** `{c['tipo']}` | **Fase:** `{status_atual}` | **Saques:** `{fmt_moeda(c['total_saques'])}`")

        if is_financiada:
            tab_painel, tab_lancar, tab_saques, tab_gerenciar = st.tabs([
                "📊 Desempenho da Conta", "➕ Lançar Trade", "💸 Saques da Conta", "⚙️ Opções da Conta"
            ])
        else:
            tab_painel, tab_lancar, tab_gerenciar = st.tabs([
                "📊 Desempenho da Conta", "➕ Lançar Trade", "⚙️ Opções da Conta"
            ])

        # --- ABA 1: DESEMPENHO E HISTÓRICO ---
        with tab_painel:
            t_conta = trades_df[trades_df["conta_id"] == c_id].copy()
            total_pnl = t_conta["resultado"].sum() if not t_conta.empty else 0.0
            saldo_atual = c["saldo_inicial"] + total_pnl
            drawdown_restante = saldo_atual - (c["saldo_inicial"] - c["max_dd"])
            falta_meta = max(0.0, (c["saldo_inicial"] + c["meta"]) - saldo_atual)
            dias_uteis = dias_uteis_cme_restantes()
            mam_individual = falta_meta / dias_uteis

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Saldo Atual", fmt_moeda(saldo_atual), delta=fmt_moeda(total_pnl))
            m2.metric("Margem até Stop da Mesa", fmt_moeda(drawdown_restante))
            m3.metric("Falta para o Alvo", fmt_moeda(falta_meta))
            m4.metric(f"MAM ({dias_uteis} pregões CME)", f"{fmt_moeda(mam_individual)}/dia")

            st.markdown("---")

            if not t_conta.empty:
                t_conta = t_conta.sort_values(by="id")
                t_conta["Saldo_Acum"] = c["saldo_inicial"] + t_conta["resultado"].cumsum()
                t_conta["data_formatada"] = t_conta["data"].apply(fmt_data)

                fig = px.line(t_conta, x="data_formatada", y="Saldo_Acum", title="Curva de Patrimônio ($)", markers=True)
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Histórico de Trades Desta Conta")
                t_view = t_conta.copy()
                t_view["Data"] = t_view["data"].apply(fmt_data)
                t_view["Resultado"] = t_view["resultado"].apply(fmt_moeda)
                t_view["Custos"] = t_view["custos"].apply(fmt_moeda)
                t_view["Duração"] = t_view["duracao_min"].apply(parse_display_duracao)

                st.dataframe(
                    t_view[["id", "Data", "ativo", "direcao", "lotes", "pontos", "Custos", "Resultado", "Duração", "estrategia", "notas"]].rename(
                        columns={"id": "ID", "ativo": "Ativo", "direcao": "Direção", "lotes": "Lotes", "pontos": "Pontos", "Custos": "Custos ($)", "Resultado": "Resultado Líquido", "estrategia": "Estratégia", "notas": "Notas"}
                    ).sort_values(by="ID", ascending=False),
                    use_container_width=True
                )
                csv = t_conta.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Baixar Histórico de Trades (CSV)", csv, f"trades_{c['nome']}.csv", "text/csv")
            else:
                st.info("Nenhuma operação registrada para esta conta ainda.")

        # --- ABA 2: LANÇAR TRADE COM PONTOS, CUSTOS E DIREÇÃO ---
        with tab_lancar:
            st.subheader(f"Registrar Operação: {c['nome']} ({c['mesa']})")

            c1, c2, c3 = st.columns(3)
            with c1:
                data_trade = st.date_input("Data do Pregão (DD/MM/AAAA)", value=date.today(), format="DD/MM/YYYY")
                ativo = st.selectbox("Ativo Operado", ativos_df["nome"].tolist(), index=None, placeholder="Selecione o Ativo...")
                direcao = st.selectbox("Direção da Operação", ["Compra (Long)", "Venda (Short)"], index=None, placeholder="Selecione a Direção...")

            with c2:
                lotes = st.number_input("Qtd. de Contratos (Lotes)", min_value=0.1, value=None, step=0.5, placeholder="ex: 1.0")
                pontos_str = st.text_input("Pontos na Operação", value="", placeholder="ex: 15,50 ou -8,25")
                custos_str = st.text_input("Custos / Taxas ($)", value="", placeholder="ex: 4,50")

            with c3:
                resultado_str = st.text_input("Resultado Líquido ($)", value="", placeholder="ex: 250,00 ou -150,00")
                estrategia = st.selectbox("Estratégia Utilizada", estrategias_df["nome"].tolist(), index=None, placeholder="Selecione a Estratégia...")
                st.markdown("**Duração da Operação**")
                cd1, cd2, cd3 = st.columns(3)
                with cd1:
                    dur_h = st.number_input("Horas", min_value=0, max_value=72, value=0, step=1)
                with cd2:
                    dur_m = st.number_input("Min", min_value=0, max_value=59, value=0, step=1)
                with cd3:
                    dur_s = st.number_input("Seg", min_value=0, max_value=59, value=0, step=1)

            notas = st.text_area("Observações Técnicas / Psicológicas do Trade", placeholder="Descreva os motivos da entrada, gatilho, disciplina ou erros...")

            st.write("")

            col_salvar, col_edit, col_add_ativo, col_add_est = st.columns([1, 1.2, 1.2, 1.2])

            with col_salvar:
                btn_salvar = st.button("💾 Salvar", type="primary", use_container_width=True)

            with col_edit:
                with st.popover("✏️ Editar Trade", use_container_width=True):
                    st.markdown("### ✏️ Alterar Trade Já Lançado")
                    t_conta_edit = trades_df[trades_df["conta_id"] == c_id]
                    if t_conta_edit.empty:
                        st.info("Nenhum trade lançado nesta conta para editar.")
                    else:
                        lista_trades_edit = [
                            f"ID {t['id']} | {fmt_data(t['data'])} - {t['ativo']} ({fmt_moeda(t['resultado'])})"
                            for _, t in t_conta_edit.sort_values(by="id", ascending=False).iterrows()
                        ]
                        trade_selecionado = st.selectbox("Selecione a Operação:", lista_trades_edit, key="sel_trade_edit")
                        t_id = int(trade_selecionado.split(" | ")[0].replace("ID ", ""))
                        t_dados = t_conta_edit[t_conta_edit["id"] == t_id].iloc[0]

                        ed_data = st.date_input("Data", value=datetime.strptime(t_dados["data"], "%Y-%m-%d").date(), format="DD/MM/YYYY", key=f"ed_d_{t_id}")
                        
                        idx_ativo = ativos_df["nome"].tolist().index(t_dados["ativo"]) if t_dados["ativo"] in ativos_df["nome"].tolist() else 0
                        ed_ativo = st.selectbox("Ativo", ativos_df["nome"].tolist(), index=idx_ativo, key=f"ed_atv_{t_id}")

                        dir_opcoes = ["Compra (Long)", "Venda (Short)"]
                        idx_dir = dir_opcoes.index(t_dados["direcao"]) if t_dados["direcao"] in dir_opcoes else 0
                        ed_dir = st.selectbox("Direção", dir_opcoes, index=idx_dir, key=f"ed_dir_{t_id}")

                        ed_lotes = st.number_input("Lotes", min_value=0.1, value=float(t_dados["lotes"]), step=0.5, key=f"ed_lot_{t_id}")
                        ed_pontos = st.text_input("Pontos", value=fmt_br_input(t_dados["pontos"]), key=f"ed_pts_{t_id}")
                        ed_custos = st.text_input("Custos ($)", value=fmt_br_input(t_dados["custos"]), key=f"ed_cst_{t_id}")
                        ed_res_str = st.text_input("Resultado ($)", value=fmt_br_input(t_dados["resultado"]), key=f"ed_res_{t_id}")

                        h_ant, m_ant, s_ant = descompactar_duracao(t_dados["duracao_min"])
                        st.caption("Duração:")
                        ed_c1, ed_c2, ed_c3 = st.columns(3)
                        with ed_c1:
                            ed_h = st.number_input("Horas", min_value=0, max_value=72, value=h_ant, step=1, key=f"ed_h_{t_id}")
                        with ed_c2:
                            ed_m = st.number_input("Min", min_value=0, max_value=59, value=m_ant, step=1, key=f"ed_m_{t_id}")
                        with ed_c3:
                            ed_s = st.number_input("Seg", min_value=0, max_value=59, value=s_ant, step=1, key=f"ed_s_{t_id}")

                        idx_est = estrategias_df["nome"].tolist().index(t_dados["estrategia"]) if t_dados["estrategia"] in estrategias_df["nome"].tolist() else 0
                        ed_est = st.selectbox("Estratégia", estrategias_df["nome"].tolist(), index=idx_est, key=f"ed_est_{t_id}")
                        ed_notas = st.text_area("Observações", value=str(t_dados["notas"] or ""), key=f"ed_not_{t_id}")

                        col_btn_upd, col_btn_del = st.columns(2)
                        with col_btn_upd:
                            if st.button("💾 Atualizar Trade", key=f"btn_save_tr_{t_id}"):
                                try:
                                    res_f = converter_br_para_float(ed_res_str)
                                    pts_f = converter_br_para_float(ed_pontos)
                                    cst_f = converter_br_para_float(ed_custos)
                                    dur_str = formatar_duracao(ed_h, ed_m, ed_s)
                                    cursor.execute("""
                                    UPDATE trades SET data=?, ativo=?, direcao=?, lotes=?, pontos=?, custos=?, resultado=?, duracao_min=?, estrategia=?, notas=?
                                    WHERE id=?
                                    """, (str(ed_data), ed_ativo, ed_dir, ed_lotes, pts_f, cst_f, res_f, dur_str, ed_est, ed_notas, t_id))
                                    conn.commit()
                                    st.toast("Atualizado", icon="✅")
                                    st.success("Trade atualizado!")
                                    st.rerun()
                                except Exception:
                                    st.toast("Erro, e tente novamente", icon="❌")
                        with col_btn_del:
                            if st.button("🗑️ Excluir Este Trade", key=f"btn_del_tr_{t_id}"):
                                try:
                                    cursor.execute("DELETE FROM trades WHERE id=?", (t_id,))
                                    conn.commit()
                                    st.toast("Atualizado", icon="✅")
                                    st.success("Trade excluído!")
                                    st.rerun()
                                except Exception:
                                    st.toast("Erro, e tente novamente", icon="❌")

            with col_add_ativo:
                with st.popover("➕ Novo Ativo", use_container_width=True):
                    st.markdown("**Cadastrar Novo Ativo**")
                    nome_novo_ativo = st.text_input("Símbolo (ex: MNQ, 6E, ZB)", key="pop_ativo")
                    if st.button("Confirmar Ativo", key="btn_conf_ativo"):
                        if nome_novo_ativo:
                            try:
                                cursor.execute("INSERT INTO ativos (nome) VALUES (?)", (nome_novo_ativo.strip(),))
                                conn.commit()
                                st.toast("Atualizado", icon="✅")
                                st.success(f"Ativo '{nome_novo_ativo}' adicionado!")
                                st.rerun()
                            except Exception:
                                st.toast("Erro, e tente novamente", icon="❌")
                                st.error("Este ativo já existe.")

            with col_add_est:
                with st.popover("➕ Nova Estratégia", use_container_width=True):
                    st.markdown("**Cadastrar Nova Estratégia**")
                    nome_nova_est = st.text_input("Nome da Técnica (ex: FVG, Rompimento)", key="pop_est")
                    if st.button("Confirmar Estratégia", key="btn_conf_est"):
                        if nome_nova_est:
                            try:
                                cursor.execute("INSERT INTO estrategias (nome) VALUES (?)", (nome_nova_est.strip(),))
                                conn.commit()
                                st.toast("Atualizado", icon="✅")
                                st.success(f"Estratégia '{nome_nova_est}' adicionada!")
                                st.rerun()
                            except Exception:
                                st.toast("Erro, e tente novamente", icon="❌")
                                st.error("Esta estratégia já existe.")

            if btn_salvar:
                try:
                    if not ativo:
                        raise ValueError("Por favor, selecione o Ativo Operado.")
                    if not direcao:
                        raise ValueError("Por favor, selecione a Direção (Compra/Venda).")
                    if not estrategia:
                        raise ValueError("Por favor, selecione a Estratégia Utilizada.")
                    if lotes is None or lotes <= 0:
                        raise ValueError("Informe a Quantidade de Contratos (Lotes).")
                    if not resultado_str.strip():
                        raise ValueError("Informe o Resultado Líquido do trade.")

                    res_float = converter_br_para_float(resultado_str)
                    pts_float = converter_br_para_float(pontos_str)
                    cst_float = converter_br_para_float(custos_str)
                    duracao_formatada = formatar_duracao(dur_h, dur_m, dur_s)

                    cursor.execute("""
                    SELECT id FROM trades 
                    WHERE conta_id = ? AND data = ? AND ativo = ? AND lotes = ? AND resultado = ? AND direcao = ?
                    """, (c_id, str(data_trade), ativo, lotes, res_float, direcao))
                    trade_duplicado = cursor.fetchone()

                    if trade_duplicado:
                        st.toast("Operação repetida prevenida!", icon="⚠️")
                        st.warning("⚠️ **Prevenção de Duplicação:** Uma operação idêntica com este ativo e resultado já foi salva nesta conta hoje. O duplo clique foi prevenido.")
                    else:
                        cursor.execute("""
                        INSERT INTO trades (conta_id, data, ativo, direcao, lotes, pontos, custos, resultado, duracao_min, estrategia, notas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (c_id, str(data_trade), ativo, direcao, lotes, pts_float, cst_float, res_float, duracao_formatada, estrategia, notas))
                        conn.commit()
                        st.toast("Atualizado", icon="✅")
                        st.success("Trade registrado com sucesso!")
                        st.rerun()
                except ValueError as ve:
                    st.toast("Erro, e tente novamente", icon="❌")
                    st.error(f"Atenção: {str(ve)}")
                except Exception as e:
                    st.toast("Erro, e tente novamente", icon="❌")
                    st.error(f"Erro ao salvar: {str(e)}")

        # --- ABA EXCLUSIVA DE SAQUES (APENAS CONTAS FUNDED OU LIVE) ---
        if is_financiada:
            with tab_saques:
                st.subheader(f"💸 Gestão de Saques: {c['nome']} ({c['mesa']})")
                st.caption("Registre suas retiradas para controle de histórico e reinício automático da janela de consistência.")

                saques_conta = saques_df[saques_df["conta_id"] == c_id].copy()
                qtd_saques = len(saques_conta)
                total_sacado_conta = saques_conta["valor"].sum() if not saques_conta.empty else 0.0

                s1, s2, s3 = st.columns(3)
                s1.metric("Quantidade de Saques", f"{qtd_saques} saque(s)")
                s2.metric("Total Retirado Desta Conta", fmt_moeda(total_sacado_conta))
                s3.metric("Início da Janela Atual", fmt_data(c["data_inicio_janela"]))

                st.markdown("---")

                with st.form("form_lancar_saque"):
                    st.markdown(f"#### Lançar {qtd_saques + 1}º Saque")
                    col_sq1, col_sq2 = st.columns(2)
                    with col_sq1:
                        data_saque = st.date_input("Data da Solicitação do Saque", value=date.today(), format="DD/MM/YYYY")
                        valor_saque_str = st.text_input("Valor Solicitado ($)", placeholder="ex: 1.500,00")
                    with col_sq2:
                        notas_saque = st.text_input("Identificação / Protocolo / Método", placeholder="ex: 1º Saque via Deel / Cripto")

                    btn_confirmar_saque = st.form_submit_button("💸 Confirmar Registro de Saque")
                    if btn_confirmar_saque:
                        try:
                            val_saque_f = converter_br_para_float(valor_saque_str)
                            if val_saque_f <= 0:
                                raise ValueError("O valor do saque deve ser maior que zero.")

                            cursor.execute("""
                            INSERT INTO saques (conta_id, data_solicitacao, valor, notas)
                            VALUES (?, ?, ?, ?)
                            """, (c_id, str(data_saque), val_saque_f, notas_saque))

                            novo_total_saques = float(c["total_saques"]) + val_saque_f
                            cursor.execute("""
                            UPDATE contas SET total_saques=?, data_inicio_janela=?
                            WHERE id=?
                            """, (novo_total_saques, str(data_saque), c_id))

                            conn.commit()
                            st.toast("Atualizado", icon="✅")
                            st.success(f"Saque de {fmt_moeda(val_saque_f)} registrado com sucesso! A nova janela de consistência começou em {fmt_data(str(data_saque))}.")
                            st.rerun()
                        except Exception as e:
                            st.toast("Erro, e tente novamente", icon="❌")
                            st.error(f"Erro ao registrar saque: {str(e)}")

                if not saques_conta.empty:
                    st.markdown("---")
                    st.subheader("📋 Histórico de Saques Realizados")
                    saques_view = saques_conta.copy().sort_values(by="id", ascending=False)
                    saques_view["Data Solicitação"] = saques_view["data_solicitacao"].apply(fmt_data)
                    saques_view["Valor ($)"] = saques_view["valor"].apply(fmt_moeda)

                    st.dataframe(
                        saques_view[["id", "Data Solicitação", "Valor ($)", "notas"]].rename(
                            columns={"id": "Nº", "notas": "Observações / Protocolo"}
                        ),
                        use_container_width=True
                    )

        # --- ABA DE OPÇÕES DA CONTA (EDITAR CUSTOS & DADOS) ---
        with tab_gerenciar:
            st.subheader(f"⚙️ Configurações da Conta: {c['nome']} ({c['mesa']})")
            
            with st.expander("✏️ Editar Dados e Custos Desta Conta", expanded=True):
                with st.form("form_editar_conta_atual"):
                    c1_ed, c2_ed = st.columns(2)
                    with c1_ed:
                        ed_nome = st.text_input("Identificação da Conta", value=str(c['nome']))
                        ed_trader = st.text_input("Nome do Trader", value=str(c['trader']))
                        ed_mesa = st.text_input("Nome da Mesa", value=str(c['mesa']))
                        
                        tam_opcoes = ["25k", "50k", "100k", "150k", "250k", "300k", "Outro"]
                        idx_tam = tam_opcoes.index(c['tamanho_conta']) if c['tamanho_conta'] in tam_opcoes else 0
                        ed_tamanho = st.selectbox("Tamanho da Conta", tam_opcoes, index=idx_tam)

                        tipo_opcoes = ["Freedom", "Freedom 2.0", "Standard", "No Activation", "Instant Funded"]
                        idx_tipo = tipo_opcoes.index(c['tipo']) if c['tipo'] in tipo_opcoes else 0
                        ed_tipo = st.selectbox("Tipo / Modelo de Conta", tipo_opcoes, index=idx_tipo)

                        status_opcoes = ["Challenge (avaliação)", "Funded (Financiada)", "Live (Real)"]
                        status_salvo = c.get('status', 'Challenge (avaliação)')
                        idx_status = status_opcoes.index(status_salvo) if status_salvo in status_opcoes else 0
                        ed_status = st.selectbox("Fase / Status da Conta", status_opcoes, index=idx_status)

                    with c2_ed:
                        ed_saldo = st.text_input("Saldo Inicial ($)", value=fmt_br_input(c['saldo_inicial']))
                        ed_dd = st.text_input("Drawdown Máximo ($)", value=fmt_br_input(c['max_dd']))
                        ed_limite = st.text_input("Limite Diário ($)", value=fmt_br_input(c['limite_diario']))
                        ed_meta = st.text_input("Meta de Lucro ($)", value=fmt_br_input(c['meta']))
                        
                        st.markdown("**Custos e Investimento Realizado:**")
                        ed_c_mesa = st.text_input("Valor Pago pela Mesa / Prova ($)", value=fmt_br_input(c.get('custo_mesa', 0.0)))
                        ed_c_ativ = st.text_input("Taxa de Ativação ($)", value=fmt_br_input(c.get('custo_ativacao', 0.0)))
                        ed_c_reset = st.text_input("Custo com Resets ($)", value=fmt_br_input(c.get('custo_reset', 0.0)))
                        ed_c_outros = st.text_input("Outros Custos ($)", value=fmt_br_input(c.get('outros_custos', 0.0)))

                        dt_janela_val = datetime.strptime(c['data_inicio_janela'], "%Y-%m-%d").date() if c['data_inicio_janela'] else date.today()
                        ed_dt_janela = st.date_input("Início da Janela de Saque", value=dt_janela_val, format="DD/MM/YYYY")

                    salvar_ed_conta = st.form_submit_button("💾 Salvar Alterações da Conta")
                    if salvar_ed_conta:
                        try:
                            cursor.execute("""
                            UPDATE contas SET nome=?, trader=?, mesa=?, tamanho_conta=?, tipo=?, status=?, saldo_inicial=?, max_dd=?, limite_diario=?, meta=?, custo_mesa=?, custo_ativacao=?, custo_reset=?, outros_custos=?, data_inicio_janela=?
                            WHERE id=?
                            """, (
                                ed_nome, ed_trader, ed_mesa, ed_tamanho, ed_tipo, ed_status,
                                converter_br_para_float(ed_saldo),
                                converter_br_para_float(ed_dd),
                                converter_br_para_float(ed_limite),
                                converter_br_para_float(ed_meta),
                                converter_br_para_float(ed_c_mesa),
                                converter_br_para_float(ed_c_ativ),
                                converter_br_para_float(ed_c_reset),
                                converter_br_para_float(ed_c_outros),
                                str(ed_dt_janela),
                                c_id
                            ))
                            conn.commit()
                            st.toast("Atualizado", icon="✅")
                            st.success("Dados e status da conta atualizados com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.toast("Erro, e tente novamente", icon="❌")
                            st.error(f"Erro ao atualizar a conta: {str(e)}")

            st.markdown("---")
            st.subheader("Zona de Perigo")
            confirmar_del = st.checkbox(f"⚠️ Confirmo que desejo apagar definitivamente a conta '{c['nome']}' e todos os seus registros.")
            if st.button("🗑️ Excluir Esta Conta Definitivamente"):
                if confirmar_del:
                    try:
                        cursor.execute("DELETE FROM saques WHERE conta_id = ?", (c_id,))
                        cursor.execute("DELETE FROM trades WHERE conta_id = ?", (c_id,))
                        cursor.execute("DELETE FROM contas WHERE id = ?", (c_id,))
                        conn.commit()
                        st.toast("Atualizado", icon="✅")
                        st.success("Conta removida com sucesso!")
                        st.rerun()
                    except Exception:
                        st.toast("Erro, e tente novamente", icon="❌")
                        st.error("Erro ao excluir.")
                else:
                    st.warning("Marque a confirmação para prosseguir.")

# =========================================================
# 3. RELATÓRIO FINANCEIRO (ESTUDO DE PAYBACK & CUSTOS)
# =========================================================
elif menu == "💰 Relatório Financeiro":
    st.title("💰 Relatório Financeiro")
    st.caption("Acompanhamento profissional de Payback: Saiba com precisão se seu investimento nas mesas já foi pago.")

    if contas_df.empty:
        st.warning("Nenhuma conta cadastrada para gerar relatório financeiro.")
    else:
        contas_df["custo_mesa"] = contas_df["custo_mesa"].fillna(0.0)
        contas_df["custo_ativacao"] = contas_df["custo_ativacao"].fillna(0.0)
        contas_df["custo_reset"] = contas_df["custo_reset"].fillna(0.0)
        contas_df["outros_custos"] = contas_df["outros_custos"].fillna(0.0)
        
        contas_df["custo_total"] = (
            contas_df["custo_mesa"] + contas_df["custo_ativacao"] + contas_df["custo_reset"] + contas_df["outros_custos"]
        )
        contas_df["lucro_real_liquido"] = contas_df["total_saques"] - contas_df["custo_total"]

        total_investido = contas_df["custo_total"].sum()
        total_sacado_global = contas_df["total_saques"].sum()
        lucro_liquido_bolso = total_sacado_global - total_investido
        
        roi_global = ((lucro_liquido_bolso / total_investido) * 100) if total_investido > 0 else 0.0

        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        col_f1.metric("Total Investido (Custos)", fmt_moeda(total_investido))
        col_f2.metric("Total Resgatado em Saques", fmt_moeda(total_sacado_global))
        col_f3.metric("Lucro Líquido Real no Bolso", fmt_moeda(lucro_liquido_bolso), delta=fmt_moeda(lucro_liquido_bolso))
        col_f4.metric("ROI Geral (%)", f"{roi_global:.1f}%")

        st.markdown("---")

        if lucro_liquido_bolso > 0:
            st.success(f"🎉 **PAYBACK CONCLUÍDO COM LUCRO:** Você já recuperou todo o capital investido em provas, resets e ativações, e está com **{fmt_moeda(lucro_liquido_bolso)}** de lucro líquido limpo no bolso!")
        elif lucro_liquido_bolso == 0 and total_investido > 0:
            st.info("⚖️ **BREAK-EVEN ATINGIDO:** O valor dos saques cobriu exatamente 100% dos seus custos. O próximo saque será 100% lucro.")
        else:
            falta_payback = abs(lucro_liquido_bolso)
            st.warning(f"⏳ **EM PROCESSO DE PAYBACK:** Faltam **{fmt_moeda(falta_payback)}** em saques para quitar o total investido nas contas.")

        st.markdown("---")
        st.subheader("📊 Estudo Detalhado de Payback por Conta")

        relatorio_linhas = []
        for _, r in contas_df.iterrows():
            c_tot = r["custo_total"]
            s_tot = r["total_saques"]
            l_real = s_tot - c_tot
            roi_ind = ((l_real / c_tot) * 100) if c_tot > 0 else 0.0

            if s_tot > c_tot:
                situacao = "✅ Pago (+ Lucro)"
            elif s_tot == c_tot and c_tot > 0:
                situacao = "⚖️ Break-even"
            else:
                dif = c_tot - s_tot
                situacao = f"⏳ Faltam {fmt_moeda(dif)}"

            relatorio_linhas.append({
                "Conta": f"{r['nome']} ({r['mesa']})",
                "Fase": r.get("status", "Challenge (avaliação)"),
                "Tipo": r["tipo"],
                "Compra ($)": fmt_moeda(r["custo_mesa"]),
                "Ativação ($)": fmt_moeda(r["custo_ativacao"]),
                "Resets ($)": fmt_moeda(r["custo_reset"]),
                "Outros ($)": fmt_moeda(r["outros_custos"]),
                "Custo Total": fmt_moeda(c_tot),
                "Total Sacado": fmt_moeda(s_tot),
                "Lucro Real": fmt_moeda(l_real),
                "ROI": f"{roi_ind:.1f}%",
                "Situação do Investimento": situacao
            })

        df_relatorio_view = pd.DataFrame(relatorio_linhas)
        st.dataframe(df_relatorio_view, use_container_width=True)

        st.subheader("📈 Comparativo: Capital Investido vs. Retorno por Conta")
        graf_df = contas_df[["nome", "custo_total", "total_saques"]].copy()
        graf_df = graf_df.rename(columns={"custo_total": "Total Investido ($)", "total_saques": "Total Sacado ($)"})
        graf_melt = graf_df.melt(id_vars=["nome"], value_vars=["Total Investido ($)", "Total Sacado ($)"], var_name="Métrica", value_name="Valor ($)")
        
        fig_bar = px.bar(graf_melt, x="nome", y="Valor ($)", color="Métrica", barmode="group", title="Investido vs. Retorno Sacado por Conta")
        st.plotly_chart(fig_bar, use_container_width=True)

# =========================================================
# 4. REGRAS E COMPLIANCE DA MESA (MOTOR OFICIAL YLOS TRADING)
# =========================================================
elif menu == "🛡️ Regras e Compliance":
    st.title("🛡️ Auditoria de Regras & Compliance")
    st.caption("Diagnóstico matemático oficial: status em tempo real e cálculo da solução caso alguma regra seja violada.")

    if contas_df.empty:
        st.warning("Nenhuma conta encontrada.")
    else:
        lista_contas = [f"{c['id']} - {c['nome']} ({c['mesa']}) | {c['tipo']} [{c['status']}]" for _, c in contas_df.iterrows()]
        conta_sel = st.selectbox("Selecione a Conta para Auditoria:", lista_contas)
        c_id = int(conta_sel.split(" - ")[0])
        c_info = contas_df[contas_df["id"] == c_id].iloc[0]

        mesa_nome = str(c_info["mesa"]).strip().lower()
        is_ylos = "ylos" in mesa_nome
        tipo_conta = str(c_info["tipo"]).strip()
        status_conta = str(c_info["status"]).strip()

        t_all = trades_df[trades_df["conta_id"] == c_id].copy()
        if not t_all.empty and c_info["data_inicio_janela"]:
            t_janela = t_all[t_all["data"] >= c_info["data_inicio_janela"]].copy()
        else:
            t_janela = t_all.copy()

        st.markdown(f"### Conta: `{c_info['nome']}` | Mesa: `{c_info['mesa']}` | Modelo: `{tipo_conta}` | Fase: `{status_conta}`")
        st.write(f"**Total em Saques:** `{fmt_moeda(c_info['total_saques'])}` | **Janela Atual Iniciada em:** `{fmt_data(c_info['data_inicio_janela'])}`")
        st.markdown("---")

        # 1. CONSISTÊNCIA DE SALDO
        st.subheader("1. Consistência de Saldo (Limite de Lucro Diário)")
        
        if is_ylos and status_conta == "Challenge (avaliação)":
            st.info("ℹ️ **Fase Challenge:** A regra de consistência de saldo não barra seu teste. No entanto, o cálculo abaixo mostra como diluir caso tenha concentrado o lucro.")

        if is_ylos:
            payouts = c_info["total_saques"]
            if tipo_conta in ["Freedom", "Freedom 2.0"]:
                regra_pct = 0.30 if payouts <= 50000 else 0.20
            elif tipo_conta in ["Standard", "No Activation"]:
                regra_pct = 0.40 if payouts <= 30000 else (0.30 if payouts <= 50000 else 0.20)
            else:
                regra_pct = 0.30 if payouts <= 50000 else 0.20
        else:
            regra_pct = 0.40

        if t_janela.empty:
            st.info("Nenhuma operação registrada na janela atual para cálculo de consistência.")
        else:
            pnl_diario = t_janela.groupby("data")["resultado"].sum().reset_index()
            lucro_total_janela = pnl_diario["resultado"].sum()
            maior_dia_lucro = pnl_diario["resultado"].max()

            c_c1, c_c2, c_c3 = st.columns(3)
            c_c1.metric("Lucro Líquido na Janela", fmt_moeda(lucro_total_janela))
            c_c2.metric("Maior Ganho em 1 Único Dia", fmt_moeda(maior_dia_lucro))
            c_c3.metric("Teto Permitido p/ 1 Dia", f"{int(regra_pct*100)}%")

            if lucro_total_janela > 0 and maior_dia_lucro > 0:
                representatividade = (maior_dia_lucro / lucro_total_janela) * 100
                
                if representatividade > (regra_pct * 100):
                    lucro_alvo_necessario = maior_dia_lucro / regra_pct
                    falta_lucrar_diluicao = lucro_alvo_necessario - lucro_total_janela

                    st.error(f"❌ **FORA DA REGRA:** O seu maior dia lucrou **{representatividade:.1f}%** do total acumulado (o teto permitido é de **{int(regra_pct*100)}%**).")
                    
                    st.warning(f"""
                    💡 **SOLUÇÃO EXATA PARA REGULARIZAR SUA CONTA:**
                    * Para que o ganho do seu melhor dia fique exatamente em **{int(regra_pct*100)}%**, seu lucro total na janela precisa alcançar **{fmt_moeda(lucro_alvo_necessario)}**.
                    * **O que você deve fazer agora:** Você precisa lucrar mais **{fmt_moeda(falta_lucrar_diluicao)}** distribuídos em novos pregões. Ao bater esse valor extra, seu saque ou aprovação estará 100% liberado!
                    """)
                else:
                    st.success(f"✅ **DENTRO DA REGRA:** Seu melhor dia representou **{representatividade:.1f}%** do lucro acumulado, respeitando com folga o limite de {int(regra_pct*100)}%.")
            else:
                st.info("A conta ainda não atingiu lucro líquido positivo acumulado nesta janela.")

        st.markdown("---")

        # 2. CRITÉRIOS DE DIAS OPERADOS E DIAS VENCEDORES (>= $50)
        st.subheader("2. Critérios de Dias Operados e Dias Vencedores (Mínimo $50)")
        
        if t_janela.empty:
            st.info("Sem dias operados nesta janela.")
        else:
            pnl_d = t_janela.groupby("data")["resultado"].sum().reset_index()
            total_dias_operados = len(pnl_d)
            dias_vencedores_50 = len(pnl_d[pnl_d["resultado"] >= 50.0])

            if is_ylos:
                if tipo_conta in ["Freedom", "Freedom 2.0"]:
                    meta_dias_op = 10
                    meta_dias_win = 10
                else:
                    meta_dias_op = 10
                    meta_dias_win = 7
            else:
                meta_dias_op = 5
                meta_dias_win = 5

            cd_1, cd_2, cd_3 = st.columns(3)
            cd_1.metric("Dias Operados", f"{total_dias_operados} de {meta_dias_op}")
            cd_2.metric("Dias c/ Ganho ≥ $50", f"{dias_vencedores_50} de {meta_dias_win}")
            
            faltam_dias_op = max(0, meta_dias_op - total_dias_operados)
            faltam_dias_win = max(0, meta_dias_win - dias_vencedores_50)

            if total_dias_operados >= meta_dias_op and dias_vencedores_50 >= meta_dias_win:
                st.success("✅ **DENTRO DA REGRA:** Você já completou todos os dias mínimos operados e os dias vencedores de $50 necessários!")
            else:
                st.warning(f"""
                ⏳ **CRITÉRIO PENDENTE PARA SAQUE / AVALIAÇÃO:**
                * Faltam **{faltam_dias_op} dia(s)** operados para cumprir a meta mínima.
                * Faltam **{faltam_dias_win} dia(s)** com ganho líquido de pelo menos **$ 50,00** para liberar a solicitação.
                """)

        st.markdown("---")

        # 3. REGRA DA MEDIANA 5x
        st.subheader("3. Risco x Retorno (Regra da Mediana 5x)")
        
        trades_gain = t_janela[t_janela["resultado"] > 0]["resultado"]
        trades_loss = t_janela[t_janela["resultado"] < 0]["resultado"]

        if trades_gain.empty:
            st.info("Sem operações vencedoras lançadas para calcular a mediana.")
        else:
            mediana_win = float(np.median(trades_gain))
            teto_stop_max = 5.0 * mediana_win
            maior_loss_unico = abs(trades_loss.min()) if not trades_loss.empty else 0.0

            cm_1, cm_2, cm_3 = st.columns(3)
            cm_1.metric("Mediana dos Trades Ganhadores", fmt_moeda(mediana_win))
            cm_2.metric("Prejuízo Máximo Permitido (5x)", fmt_moeda(teto_stop_max))
            cm_3.metric("Maior Loss Realizado", fmt_moeda(maior_loss_unico))

            if maior_loss_unico > teto_stop_max:
                st.error(f"❌ **FORA DA REGRA:** Você teve uma perda individual de **{fmt_moeda(maior_loss_unico)}**, ultrapassando o limite de 5x a mediana (**{fmt_moeda(teto_stop_max)}**).")
                mediana_necessaria = maior_loss_unico / 5.0
                st.warning(f"""
                💡 **SOLUÇÃO PARA REEQUILIBRAR A MEDIANA:**
                * Para que essa perda se torne aceitável dentro do limite de 5x, a mediana dos seus trades vencedores precisa subir para pelo menos **{fmt_moeda(mediana_necessaria)}**.
                * **O que fazer:** Foque em operações vencedoras maiores ou com alvos mais longos para puxar a sua mediana para cima.
                """)
            else:
                st.success(f"✅ **DENTRO DA REGRA:** Nenhuma perda única ultrapassou o teto permitido de 5x a mediana ({fmt_moeda(teto_stop_max)}).")

        st.markdown("---")

        # 4. MICROSCALPING (< 30 SEGUNDOS)
        st.subheader("4. Estilo Operacional e Tempo de Operação (Regra Anti-Microscalping)")
        
        if not t_janela.empty:
            trades_rapidos = []
            for _, tr in t_janela.iterrows():
                seg = duracao_em_segundos(tr["duracao_min"])
                if seg < 30 and seg > 0:
                    trades_rapidos.append(tr)

            if trades_rapidos:
                st.error(f"❌ **ALERTA DE REGRA PROIBIDA (Microscalp):** Foram detectadas **{len(trades_rapidos)}** operações com menos de 30 segundos de duração. A Ylos proíbe operações com menos de 30s na maioria dos trades.")
                st.caption("💡 **Solução:** Alongue o tempo de permanência nas operações para evitar desclassificação.")
            else:
                st.success("✅ **DENTRO DA REGRA:** Todas as suas operações duraram pelo menos 30 segundos.")

        st.markdown("---")

        # 5. DRAWDOWN TRAILING vs EOD
        st.subheader("5. Monitoramento de Drawdown")
        
        if is_ylos and tipo_conta in ["Standard", "No Activation"] and status_conta in ["Funded (Financiada)", "Live (Real)"]:
            trava_estatica = c_info["saldo_inicial"] + c_info["max_dd"] + 100.0
            saldo_atual_conta = c_info["saldo_inicial"] + t_all["resultado"].sum() if not t_all.empty else c_info["saldo_inicial"]
            
            st.info(f"📌 **Tipo de Drawdown:** Trailing tick-a-tick. Trava definitivamente e vira estático ao atingir **{fmt_moeda(trava_estatica)}**.")
            if saldo_atual_conta >= trava_estatica:
                st.success(f"🔒 **DRAWDOWN TRAVADO:** Parabéns! Seu saldo atingiu a marca e seu limite de perda agora é estático.")
            else:
                falta_trava = trava_estatica - saldo_atual_conta
                st.write(f"Faltam **{fmt_moeda(falta_trava)}** de lucro para travar o drawdown e torná-lo estático.")
        else:
            st.info("📌 **Tipo de Drawdown:** Ajustado ao final do dia (EOD). Seu saldo oficial é considerado no término do pregão.")

# =========================================================
# 5. BACKUP GERAL DE TODAS AS INFORMAÇÕES
# =========================================================
elif menu == "💾 Backup":
    st.title("💾 Backup Geral & Segurança dos Dados")
    st.caption("Faça o download do backup consolidado de TODAS as suas contas, trades, saques e custos em um único arquivo.")

    col_bkg1, col_bkg2 = st.columns(2)

    with col_bkg1:
        st.subheader("📥 Exportar Backup Completo")
        st.write("Gera uma cópia de segurança de todo o sistema (todas as contas juntas).")
        
        dados_backup = {
            "contas": pd.read_sql("SELECT * FROM contas", conn).to_dict(orient="records"),
            "trades": pd.read_sql("SELECT * FROM trades", conn).to_dict(orient="records"),
            "saques": pd.read_sql("SELECT * FROM saques", conn).to_dict(orient="records"),
            "ativos": pd.read_sql("SELECT * FROM ativos", conn).to_dict(orient="records"),
            "estrategias": pd.read_sql("SELECT * FROM estrategias", conn).to_dict(orient="records")
        }
        backup_json = json.dumps(dados_backup, ensure_ascii=False, indent=2)

        st.download_button(
            "📥 Baixar Arquivo de Backup Geral (.json)",
            data=backup_json,
            file_name=f"backup_geral_mesas_{date.today().strftime('%d_%m_%Y')}.json",
            mime="application/json",
            use_container_width=True,
            type="primary"
        )
        
        st.info(f"📊 **Dados inclusos no backup atual:**\n- **{len(dados_backup['contas'])}** conta(s)\n- **{len(dados_backup['trades'])}** trade(s)\n- **{len(dados_backup['saques'])}** saque(s)")

    with col_bkg2:
        st.subheader("📤 Restaurar Backup Completo")
        st.write("Envie o arquivo `.json` gerado anteriormente para recuperar tudo instantaneamente.")

        arquivo_upload = st.file_uploader("Selecione o arquivo de backup (.json)", type=["json"])
        if arquivo_upload is not None:
            if st.button("Restaurar Todos os Dados Agora", use_container_width=True):
                try:
                    conteudo = json.load(arquivo_upload)

                    if "contas" in conteudo and conteudo["contas"]:
                        cursor.execute("DELETE FROM contas")
                        for r in conteudo["contas"]:
                            cols = ", ".join(r.keys())
                            places = ", ".join(["?"] * len(r))
                            cursor.execute(f"INSERT INTO contas ({cols}) VALUES ({places})", list(r.values()))

                    if "trades" in conteudo and conteudo["trades"]:
                        cursor.execute("DELETE FROM trades")
                        for r in conteudo["trades"]:
                            cols = ", ".join(r.keys())
                            places = ", ".join(["?"] * len(r))
                            cursor.execute(f"INSERT INTO trades ({cols}) VALUES ({places})", list(r.values()))

                    if "saques" in conteudo and conteudo["saques"]:
                        cursor.execute("DELETE FROM saques")
                        for r in conteudo["saques"]:
                            cols = ", ".join(r.keys())
                            places = ", ".join(["?"] * len(r))
                            cursor.execute(f"INSERT INTO saques ({cols}) VALUES ({places})", list(r.values()))

                    conn.commit()
                    st.toast("Backup Geral Restaurado com Sucesso!", icon="✅")
                    st.success("Todos os dados do arquivo foram restaurados perfeitamente!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro ao processar arquivo de restauração: {str(ex)}")

# =========================================================
# 6. CADASTRAR NOVA CONTA (COM AUTO-PREENCHIMENTO DE SALDO)
# =========================================================
elif menu == "➕ Cadastrar":
    st.title("➕ Cadastrar Nova Conta")
    st.caption("Cadastre novas contas. O saldo inicial é preenchido proporcionalmente de forma automática conforme o tamanho da conta escolhido.")

    # MAPEAMENTO INTELIGENTE DE TAMANHO PARA SALDO INICIAL
    MAPA_TAMANHO_SALDO = {
        "25k": "25.000,00",
        "50k": "50.000,00",
        "100k": "100.000,00",
        "150k": "150.000,00",
        "250k": "250.000,00",
        "300k": "300.000,00"
    }

    def on_change_tamanho():
        tam = st.session_state.get("cad_tamanho_sel")
        if tam in MAPA_TAMANHO_SALDO:
            st.session_state["cad_saldo_input"] = MAPA_TAMANHO_SALDO[tam]
        elif tam == "Outro":
            st.session_state["cad_saldo_input"] = ""

    def on_change_tam_custom():
        cust = st.session_state.get("cad_tam_custom_val", "")
        if cust:
            txt_clean = cust.strip().lower().replace("k", "000").replace(".", "").replace(",", "")
            try:
                val = float(txt_clean)
                st.session_state["cad_saldo_input"] = fmt_br_input(val)
            except:
                pass

    if "cad_saldo_input" not in st.session_state:
        st.session_state["cad_saldo_input"] = ""

    c1, c2 = st.columns(2)
    with c1:
        nome = st.text_input("Identificação da Conta", value="", placeholder="ex: Apex 50k #1")
        trader = st.text_input("Nome do Trader Responsável", value="", placeholder="Nome do Trader")
        mesa = st.text_input("Nome da Mesa", value="", placeholder="ex: Ylos Trading, Mide Global, Apex")
        
        tamanho_conta = st.selectbox(
            "Tamanho da Conta",
            ["25k", "50k", "100k", "150k", "250k", "300k", "Outro"],
            index=None,
            placeholder="Selecione o Tamanho...",
            key="cad_tamanho_sel",
            on_change=on_change_tamanho
        )

        tam_final = tamanho_conta
        if tamanho_conta == "Outro":
            tam_custom = st.text_input(
                "Especifique o Tamanho Personalizado (ex: 75k, 200k)",
                key="cad_tam_custom_val",
                placeholder="ex: 75k",
                on_change=on_change_tam_custom
            )
            if tam_custom:
                tam_final = tam_custom
        
        tipo = st.selectbox(
            "Tipo / Modelo de Conta",
            ["Freedom", "Freedom 2.0", "Standard", "No Activation", "Instant Funded"],
            index=None,
            placeholder="Selecione o Modelo..."
        )

        status = st.selectbox(
            "Fase / Status da Conta",
            ["Challenge (avaliação)", "Funded (Financiada)", "Live (Real)"],
            index=None,
            placeholder="Selecione a Fase..."
        )

    with c2:
        saldo_str = st.text_input(
            "Saldo Inicial ($)",
            key="cad_saldo_input",
            placeholder="0,00 (Preenchido automaticamente ao selecionar o tamanho)"
        )
        max_dd_str = st.text_input("Drawdown Máximo Permitido ($)", value="", placeholder="0,00 (ex: 2.500,00)")
        limite_diario_str = st.text_input("Limite Diário de Perda ($)", value="", placeholder="0,00 (ex: 1.000,00)")
        meta_str = st.text_input("Meta de Lucro ($)", value="", placeholder="0,00 (ex: 3.000,00)")

        st.markdown("**Custos e Investimento na Conta:**")
        col_cust1, col_cust2 = st.columns(2)
        with col_cust1:
            custo_mesa_str = st.text_input("Valor Pago pela Mesa / Prova ($)", value="", placeholder="0,00")
            custo_ativ_str = st.text_input("Taxa de Ativação ($)", value="", placeholder="0,00")
        with col_cust2:
            custo_reset_str = st.text_input("Custo com Resets ($)", value="", placeholder="0,00")
            outros_custos_str = st.text_input("Outros Custos ($)", value="", placeholder="0,00")

        data_inicio = st.date_input("Início das Operações / Janela", value=date.today(), format="DD/MM/YYYY")

    st.write("")
    btn_salvar_conta = st.button("💾 Cadastrar Nova Conta", type="primary", use_container_width=True)

    if btn_salvar_conta:
        try:
            if not nome.strip():
                raise ValueError("Preencha a Identificação da Conta.")
            if not trader.strip():
                raise ValueError("Preencha o Nome do Trader Responsável.")
            if not mesa.strip():
                raise ValueError("Preencha o Nome da Mesa.")
            if not tam_final:
                raise ValueError("Selecione ou informe o Tamanho da Conta.")
            if not tipo:
                raise ValueError("Selecione o Tipo / Modelo de Conta.")
            if not status:
                raise ValueError("Selecione a Fase / Status da Conta.")
            if not saldo_str.strip():
                raise ValueError("Informe o Saldo Inicial ($).")
            if not max_dd_str.strip():
                raise ValueError("Informe o Drawdown Máximo Permitido ($).")
            if not limite_diario_str.strip():
                raise ValueError("Informe o Limite Diário de Perda ($).")
            if not meta_str.strip():
                raise ValueError("Informe a Meta de Lucro ($).")

            # SISTEMA ANTI-DUPLICAÇÃO DE CONTAS
            cursor.execute("""
            SELECT id FROM contas 
            WHERE LOWER(TRIM(nome)) = ? AND LOWER(TRIM(mesa)) = ?
            """, (nome.strip().lower(), mesa.strip().lower()))
            conta_duplicada = cursor.fetchone()

            if conta_duplicada:
                st.toast("Prevenção anti-duplicação ativada!", icon="⚠️")
                st.warning(f"⚠️ **Conta Duplicada Prevenida:** A conta **'{nome}'** na mesa **'{mesa}'** já está cadastrada no sistema! Cliques múltiplos foram bloqueados.")
            else:
                s_ini = converter_br_para_float(saldo_str)
                m_dd = converter_br_para_float(max_dd_str)
                l_dia = converter_br_para_float(limite_diario_str)
                meta_val = converter_br_para_float(meta_str)
                
                c_mesa = converter_br_para_float(custo_mesa_str) if custo_mesa_str.strip() else 0.0
                c_ativ = converter_br_para_float(custo_ativ_str) if custo_ativ_str.strip() else 0.0
                c_reset = converter_br_para_float(custo_reset_str) if custo_reset_str.strip() else 0.0
                c_outros = converter_br_para_float(outros_custos_str) if outros_custos_str.strip() else 0.0

                cursor.execute("""
                INSERT INTO contas (nome, trader, mesa, tamanho_conta, tipo, status, saldo_inicial, max_dd, limite_diario, meta, custo_mesa, custo_ativacao, custo_reset, outros_custos, total_saques, data_inicio_janela)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?)
                """, (nome, trader, mesa, tam_final, tipo, status, s_ini, m_dd, l_dia, meta_val, c_mesa, c_ativ, c_reset, c_outros, str(data_inicio)))
                conn.commit()
                
                st.toast("Atualizado", icon="✅")
                st.success("Conta cadastrada com sucesso!")
                st.rerun()
        except ValueError as ve:
            st.toast("Erro, e tente novamente", icon="❌")
            st.error(f"Atenção: {str(ve)}")
        except Exception as e:
            st.toast("Erro, e tente novamente", icon="❌")
            st.error(f"Erro ao cadastrar: {str(e)}")
