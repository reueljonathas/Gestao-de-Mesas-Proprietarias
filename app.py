import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import calendar
import json
import os
import re
from datetime import date, datetime, timedelta
from supabase import create_client, Client

# Configuração da página
st.set_page_config(page_title="Gestão de Mesas CME", layout="wide", page_icon="📈")

# --- CONEXÃO INTELIGENTE E SANITIZADA COM SUPABASE ---
try:
    raw_url = str(st.secrets.get("SUPABASE_URL", "")).strip().strip('"').strip("'")
    raw_key = str(st.secrets.get("SUPABASE_KEY", "")).strip().strip('"').strip("'")

    if not raw_url and "supabase" in st.secrets:
        raw_url = str(st.secrets["supabase"].get("url", "")).strip().strip('"').strip("'")
        raw_key = str(st.secrets["supabase"].get("key", "")).strip().strip('"').strip("'")

    if "smvgfhdulefoyzmwvugp" in raw_url or not raw_url:
        sb_url = "https://smvgfhdulefoyzmwvugp.supabase.co"
    else:
        if "dashboard/project/" in raw_url:
            ref = raw_url.split("dashboard/project/")[1].split("/")[0]
            sb_url = f"https://{ref}.supabase.co"
        else:
            sb_url = raw_url.split("/rest/v1")[0].rstrip("/")
            if sb_url.endswith(".supabase.com"):
                sb_url = sb_url.replace(".supabase.com", ".supabase.co")
            if not sb_url.startswith("http"):
                sb_url = f"https://{sb_url}"

    sb_key = raw_key

    if not sb_key or len(sb_key) < 20:
        st.error("🚨 A chave SUPABASE_KEY não foi encontrada ou está incompleta no Secrets!")
        st.info("Cole a chave anon (que começa com eyJ...) nas configurações de Secrets do Streamlit.")
        st.stop()

    supabase: Client = create_client(sb_url, sb_key)
except Exception as err_setup:
    st.error(f"🚨 Erro ao configurar conexão: {str(err_setup)}")
    st.stop()

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
    sinal = "-" if float(valor) < 0 else ""
    val_abs = abs(float(valor))
    formatado = f"{val_abs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}$ {formatado}"

def fmt_br_input(valor):
    if valor is None or pd.isna(valor):
        return "0,00"
    sinal = "-" if float(valor) < 0 else ""
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

def extrair_ultimos_digitos(texto):
    if not texto:
        return "----"
    nums = re.findall(r'\d+', str(texto))
    if nums:
        bloco = nums[-1]
        return bloco[-4:] if len(bloco) >= 4 else bloco
    s = str(texto).strip()
    return s[-4:] if len(s) >= 4 else s

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

# --- CARREGAR DADOS DO SUPABASE COM TRATAMENTO BLINDADO ---
def carregar_dados():
    try:
        contas_res = supabase.table("contas").select("*").order("id", desc=False).execute()
        trades_res = supabase.table("trades").select("*").order("id", desc=False).execute()
        saques_res = supabase.table("saques").select("*").order("id", desc=False).execute()
        ativos_res = supabase.table("ativos").select("nome").order("nome", desc=False).execute()
        estrategias_res = supabase.table("estrategias").select("nome").order("nome", desc=False).execute()
    except Exception as err_api:
        st.error("🚨 **Aviso de Conexão com o Supabase**")
        st.warning(f"Não foi possível buscar os dados na nuvem no momento. Detalhe técnico: `{str(err_api)}`")
        st.info(f"Endereço conectado: `{sb_url}`. Verifique sua conexão e se a chave copiada no Secrets é a chave anon completa.")
        st.stop()

    df_c = pd.DataFrame(contas_res.data) if contas_res.data else pd.DataFrame(columns=[
        "id", "nome", "trader", "mesa", "tamanho_conta", "tipo", "status",
        "saldo_inicial", "max_dd", "limite_diario", "meta", "custo_mesa",
        "custo_ativacao", "custo_reset", "outros_custos", "total_saques",
        "data_inicio_janela", "prazo_avaliacao"
    ])
    df_t = pd.DataFrame(trades_res.data) if trades_res.data else pd.DataFrame(columns=[
        "id", "conta_id", "data", "ativo", "direcao", "lotes", "pontos",
        "custos", "resultado", "duracao_min", "estrategia", "notas"
    ])
    df_s = pd.DataFrame(saques_res.data) if saques_res.data else pd.DataFrame(columns=[
        "id", "conta_id", "data_solicitacao", "valor", "notas"
    ])
    df_a = pd.DataFrame(ativos_res.data) if ativos_res.data else pd.DataFrame(columns=["nome"])
    df_e = pd.DataFrame(estrategias_res.data) if estrategias_res.data else pd.DataFrame(columns=["nome"])

    for col in ["saldo_inicial", "max_dd", "limite_diario", "meta", "custo_mesa", "custo_ativacao", "custo_reset", "outros_custos", "total_saques"]:
        if col in df_c.columns:
            df_c[col] = pd.to_numeric(df_c[col], errors="coerce").fillna(0.0)
            
    for col in ["lotes", "pontos", "custos", "resultado"]:
        if col in df_t.columns:
            df_t[col] = pd.to_numeric(df_t[col], errors="coerce").fillna(0.0)

    if "valor" in df_s.columns:
        df_s["valor"] = pd.to_numeric(df_s["valor"], errors="coerce").fillna(0.0)

    return df_c, df_t, df_s, df_a, df_e

contas_df, trades_df, saques_df, ativos_df, estrategias_df = carregar_dados()

# --- CÁLCULO PREGÕES CME RESTANTES ---
def dias_uteis_mes_atual():
    hoje = date.today()
    _, ultimo_dia = calendar.monthrange(hoje.year, hoje.month)
    uteis = 0
    for d in range(hoje.day, ultimo_dia + 1):
        if date(hoje.year, hoje.month, d).weekday() < 5:
            uteis += 1
    return max(1, uteis)

def dias_uteis_ate_limite(data_limite):
    hoje = date.today()
    if data_limite < hoje:
        return 0
    uteis = 0
    cur = hoje
    while cur <= data_limite:
        if cur.weekday() < 5:
            uteis += 1
        cur += timedelta(days=1)
    return max(1, uteis)

def calcular_mam_conta(c, saldo_atual):
    alvo = c["saldo_inicial"] + c["meta"]
    falta_meta = max(0.0, alvo - saldo_atual)
    prazo = c.get("prazo_avaliacao", "Sem prazo máximo (Indeterminado / Ylos)")
    mesa_low = str(c.get("mesa", "")).strip().lower()

    if "ylos" in mesa_low or "sem prazo" in str(prazo).lower():
        dias_uteis = dias_uteis_mes_atual()
        mam = falta_meta / dias_uteis
        info_txt = f"{dias_uteis} pregões neste mês (Mês renovável)"
        dias_expira = None
    elif "30 dias" in str(prazo):
        dt_ini = datetime.strptime(c["data_inicio_janela"], "%Y-%m-%d").date() if c["data_inicio_janela"] else date.today()
        dt_lim = dt_ini + timedelta(days=30)
        dias_expira = (dt_lim - date.today()).days
        dias_uteis = dias_uteis_ate_limite(dt_lim)
        mam = falta_meta / max(1, dias_uteis)
        info_txt = f"{dias_uteis} pregões até o prazo de 30 dias"
    elif "60 dias" in str(prazo):
        dt_ini = datetime.strptime(c["data_inicio_janela"], "%Y-%m-%d").date() if c["data_inicio_janela"] else date.today()
        dt_lim = dt_ini + timedelta(days=60)
        dias_expira = (dt_lim - date.today()).days
        dias_uteis = dias_uteis_ate_limite(dt_lim)
        mam = falta_meta / max(1, dias_uteis)
        info_txt = f"{dias_uteis} pregões até o prazo de 60 dias"
    else:
        try:
            dt_lim = datetime.strptime(str(prazo), "%Y-%m-%d").date()
            dias_expira = (dt_lim - date.today()).days
            dias_uteis = dias_uteis_ate_limite(dt_lim)
            mam = falta_meta / max(1, dias_uteis)
            info_txt = f"{dias_uteis} pregões até {fmt_data(str(prazo))}"
        except:
            dias_uteis = dias_uteis_mes_atual()
            mam = falta_meta / dias_uteis
            info_txt = f"{dias_uteis} pregões no mês"
            dias_expira = None

    return mam, falta_meta, info_txt, dias_expira

# --- MENU LATERAL ---
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
        st.info("👋 Nenhuma conta cadastrada ainda no Supabase. Acesse **'➕ Cadastrar'** para começar!")
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
        st.caption("Fila Inteligente: Contas operadas hoje saem automaticamente do radar para você focar nas que ainda precisam de negociação.")

        hoje = date.today()
        status_contas = []

        for _, c in contas_df.iterrows():
            t_conta = trades_df[trades_df["conta_id"] == c["id"]]
            
            if not t_conta.empty:
                ult_data = datetime.strptime(t_conta["data"].max(), "%Y-%m-%d").date()
                dias_sem_operar = (hoje - ult_data).days
                t_hoje = t_conta[t_conta["data"] == str(hoje)]
                operou_hoje = not t_hoje.empty
                pnl_hoje = t_hoje["resultado"].sum() if operou_hoje else 0.0
            else:
                dias_sem_operar = 99
                operou_hoje = False
                pnl_hoje = 0.0

            lucro_conta = t_conta["resultado"].sum() if not t_conta.empty else 0.0
            saldo_conta = c["saldo_inicial"] + lucro_conta
            
            mam, falta_meta, info_mam, dias_expira = calcular_mam_conta(c, saldo_conta)

            score = 0
            if dias_sem_operar >= 5:
                score += 1500 + dias_sem_operar * 50
            elif dias_sem_operar >= 3:
                score += 400 + dias_sem_operar * 20
            
            if dias_expira is not None and dias_expira <= 7:
                score += 2000

            if falta_meta > 0 and c["meta"] > 0:
                score += min(100, (lucro_conta / c["meta"]) * 100)

            status_contas.append({
                "id": c["id"],
                "nome_original": c["nome"],
                "identificador": f"{c['nome']} ({c['mesa']})",
                "trader": c["trader"],
                "mesa": c["mesa"],
                "tamanho": c["tamanho_conta"],
                "tipo": c["tipo"],
                "status": c.get("status", "Challenge (avaliação)"),
                "prazo": c.get("prazo_avaliacao", "Sem prazo"),
                "saldo_inicial": c["saldo_inicial"],
                "saldo_atual": saldo_conta,
                "pnl": lucro_conta,
                "falta_meta": falta_meta,
                "mam": mam,
                "info_mam": info_mam,
                "dias_expira": dias_expira,
                "dias_sem_operar": dias_sem_operar,
                "operou_hoje": operou_hoje,
                "pnl_hoje": pnl_hoje,
                "score": score
            })

        df_radar = pd.DataFrame(status_contas).sort_values(by="score", ascending=False)

        criticas = df_radar[(df_radar["dias_sem_operar"] >= 5) & (df_radar["operou_hoje"] == False)]
        if not criticas.empty:
            for _, cr in criticas.iterrows():
                dias_txt = "Nunca operada" if cr["dias_sem_operar"] == 99 else f"{cr['dias_sem_operar']} dias sem trade"
                st.error(f"⚠️ **ALERTA CRÍTICO (Regra dos 7 Dias):** A conta **{cr['identificador']}** está a **{dias_txt}**! Opere hoje para evitar desclassificação.")

        expirando = df_radar[(df_radar["dias_expira"].notnull()) & (df_radar["dias_expira"] <= 7)]
        if not expirando.empty:
            for _, ex in expirando.iterrows():
                if ex["dias_expira"] < 0:
                    st.error(f"🚨 **PRAZO ESGOTADO:** A conta **{ex['identificador']}** ultrapassou o prazo ({abs(ex['dias_expira'])} dias expirada)!")
                else:
                    st.warning(f"⏳ **PRAZO DE APROVAÇÃO ACABANDO:** Faltam **{ex['dias_expira']} dias corridos** para expirar a conta **{ex['identificador']}**!")

        df_pendentes = df_radar[df_radar["operou_hoje"] == False]

        if df_pendentes.empty:
            st.success("🎉 **Excelente! Todas as contas já foram operadas hoje e cumpriram a regra de atividade!** Não há contas pendentes para negociação no momento. Bom descanso!")
        else:
            top_pendentes = df_pendentes.head(3)
            cols = st.columns(len(top_pendentes))
            
            for i, (_, row) in enumerate(top_pendentes.iterrows()):
                with cols[i]:
                    ultimos_digitos = extrair_ultimos_digitos(row['nome_original'])
                    st.markdown(f"### Conta #{i+1} do dia ({ultimos_digitos})")
                    st.markdown(f"👤 **Trader:** `{row['trader']}` &nbsp;|&nbsp; ⏳ **Prazo:** `{row['prazo']}`")
                    st.info(f"**Identificação:** `{row['identificador']}`\n\n📌 **Modelo:** `{row['tipo']}` ({row['tamanho']}) | **Fase:** `{row['status']}`")
                    
                    d_txt = "Nunca operada" if row['dias_sem_operar'] == 99 else f"{row['dias_sem_operar']} dias atrás"
                    st.write(f"🕒 **Última Operação:** {d_txt}")
                    st.metric("Saldo Atual", fmt_moeda(row['saldo_atual']), delta=fmt_moeda(row['pnl']))
                    st.metric("MAM Diária", f"{fmt_moeda(row['mam'])}/dia")
                    st.caption(f"ℹ️ {row['info_mam']}")

        st.markdown("---")
        st.subheader("📋 Resumo Consolidado de Todas as Contas")
        
        df_tabela = df_radar.copy()
        df_tabela["Nº"] = range(1, len(df_tabela) + 1)
        df_tabela["Status Hoje"] = df_tabela["operou_hoje"].apply(lambda x: "✅ Operada Hoje" if x else "⏳ Pendente")
        df_tabela["Saldo Inicial"] = df_tabela["saldo_inicial"].apply(fmt_moeda)
        df_tabela["Saldo Atual"] = df_tabela["saldo_atual"].apply(fmt_moeda)
        df_tabela["P&L Total"] = df_tabela["pnl"].apply(fmt_moeda)
        df_tabela["Falta p/ Meta"] = df_tabela["falta_meta"].apply(fmt_moeda)
        df_tabela["MAM/Dia"] = df_tabela["mam"].apply(fmt_moeda)

        cols_exibir = [
            "Nº", "Status Hoje", "identificador", "trader", "mesa",
            "tamanho", "tipo", "status", "prazo", "Saldo Inicial", "Saldo Atual",
            "P&L Total", "Falta p/ Meta", "MAM/Dia"
        ]

        st.dataframe(
            df_tabela[cols_exibir].rename(
                columns={
                    "identificador": "Conta",
                    "trader": "Trader",
                    "mesa": "Mesa",
                    "tamanho": "Tamanho",
                    "tipo": "Tipo",
                    "status": "Fase",
                    "prazo": "Regra de Prazo"
                }
            ),
            use_container_width=True,
            hide_index=True
        )

# =========================================================
# 2. MINHAS CONTAS (PAINEL, TRADES, SAQUES E CONFIGURAÇÕES)
# =========================================================
elif menu == "📁 Minhas Contas":
    if contas_df.empty:
        st.title("📁 Minhas Contas")
        st.warning("Cadastre suas contas na aba '➕ Cadastrar' primeiro.")
    else:
        mapa_contas = {}
        lista_opcoes = []
        for idx_c, (_, c_row) in enumerate(contas_df.iterrows(), start=1):
            rotulo = f"Conta #{idx_c}: {c_row['nome']} — {c_row['mesa']} ({c_row['tamanho_conta']}) | {c_row['tipo']} [{c_row['status']}]"
            lista_opcoes.append(rotulo)
            mapa_contas[rotulo] = int(c_row['id'])
        
        conta_sel = st.selectbox("📂 Selecione a Conta para Acessar:", lista_opcoes)
        c_id = mapa_contas[conta_sel]
        c = contas_df[contas_df["id"] == c_id].iloc[0]

        status_atual = c.get("status", "Challenge (avaliação)")
        is_financiada = status_atual in ["Funded (Financiada)", "Live (Real)"]

        st.title(f"📈 {c['nome']} — {c['mesa']}")
        st.markdown(f"👤 **Trader:** `{c['trader']}` | **Tamanho:** `{c['tamanho_conta']}` | **Modelo:** `{c['tipo']}` | **Fase:** `{status_atual}`")

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
            
            mam_individual, falta_meta, info_mam_ind, dias_expira_ind = calcular_mam_conta(c, saldo_atual)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Saldo Atual", fmt_moeda(saldo_atual), delta=fmt_moeda(total_pnl))
            m2.metric("Margem até Stop da Mesa", fmt_moeda(drawdown_restante))
            m3.metric("Falta para o Alvo", fmt_moeda(falta_meta))
            m4.metric("MAM Diária", f"{fmt_moeda(mam_individual)}/dia")
            
            st.caption(f"ℹ️ **Cálculo da MAM:** {info_mam_ind}")

            if dias_expira_ind is not None:
                if dias_expira_ind < 0:
                    st.error(f"🚨 **Atenção:** O prazo de aprovação desta conta expirou há {abs(dias_expira_ind)} dias.")
                elif dias_expira_ind <= 7:
                    st.warning(f"⏳ **Prazo Apertado:** Restam apenas {dias_expira_ind} dias corridos para bater a meta antes do prazo da mesa.")

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
                    use_container_width=True,
                    hide_index=True
                )
                csv = t_conta.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Baixar Histórico de Trades (CSV)", csv, f"trades_{c['nome']}.csv", "text/csv")
            else:
                st.info("Nenhuma operação registrada para esta conta ainda.")

        # --- ABA 2: LANÇAR TRADE ---
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
                                    
                                    supabase.table("trades").update({
                                        "data": str(ed_data),
                                        "ativo": ed_ativo,
                                        "direcao": ed_dir,
                                        "lotes": ed_lotes,
                                        "pontos": pts_f,
                                        "custos": cst_f,
                                        "resultado": res_f,
                                        "duracao_min": dur_str,
                                        "estrategia": ed_est,
                                        "notas": ed_notas
                                    }).eq("id", t_id).execute()
                                    
                                    st.toast("Atualizado no Supabase!", icon="✅")
                                    st.success("Trade atualizado!")
                                    st.rerun()
                                except Exception as e:
                                    st.toast(f"Erro: {str(e)}", icon="❌")
                        with col_btn_del:
                            if st.button("🗑️ Excluir Este Trade", key=f"btn_del_tr_{t_id}"):
                                try:
                                    supabase.table("trades").delete().eq("id", t_id).execute()
                                    st.toast("Trade excluído!", icon="✅")
                                    st.rerun()
                                except Exception as e:
                                    st.toast(f"Erro: {str(e)}", icon="❌")

            with col_add_ativo:
                with st.popover("➕ Novo Ativo", use_container_width=True):
                    st.markdown("**Cadastrar Novo Ativo**")
                    nome_novo_ativo = st.text_input("Símbolo (ex: MNQ, 6E, ZB)", key="pop_ativo")
                    if st.button("Confirmar Ativo", key="btn_conf_ativo"):
                        if nome_novo_ativo:
                            try:
                                supabase.table("ativos").insert({"nome": nome_novo_ativo.strip()}).execute()
                                st.toast("Ativo salvo no Supabase!", icon="✅")
                                st.rerun()
                            except Exception:
                                st.toast("Este ativo já existe.", icon="❌")

            with col_add_est:
                with st.popover("➕ Nova Estratégia", use_container_width=True):
                    st.markdown("**Cadastrar Nova Estratégia**")
                    nome_nova_est = st.text_input("Nome da Técnica (ex: FVG, Rompimento)", key="pop_est")
                    if st.button("Confirmar Estratégia", key="btn_conf_est"):
                        if nome_nova_est:
                            try:
                                supabase.table("estrategias").insert({"nome": nome_nova_est.strip()}).execute()
                                st.toast("Estratégia salva no Supabase!", icon="✅")
                                st.rerun()
                            except Exception:
                                st.toast("Esta estratégia já existe.", icon="❌")

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

                    t_dup = supabase.table("trades").select("id").match({
                        "conta_id": c_id, "data": str(data_trade), "ativo": ativo,
                        "lotes": lotes, "resultado": res_float, "direcao": direcao
                    }).execute()

                    if t_dup.data:
                        st.toast("Operação repetida prevenida!", icon="⚠️")
                        st.warning("⚠️ **Prevenção de Duplicação:** Uma operação idêntica com este ativo e resultado já foi salva hoje.")
                    else:
                        supabase.table("trades").insert({
                            "conta_id": c_id, "data": str(data_trade), "ativo": ativo,
                            "direcao": direcao, "lotes": lotes, "pontos": pts_float,
                            "custos": cst_float, "resultado": res_float,
                            "duracao_min": duracao_formatada, "estrategia": estrategia,
                            "notas": notas
                        }).execute()
                        st.toast("Salvo no Supabase!", icon="✅")
                        st.success("Trade registrado com sucesso!")
                        st.rerun()
                except ValueError as ve:
                    st.toast(f"Atenção: {str(ve)}", icon="❌")
                except Exception as e:
                    st.toast(f"Erro: {str(e)}", icon="❌")

        # --- ABA EXCLUSIVA DE SAQUES (FUNDED OU LIVE) ---
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

                            supabase.table("saques").insert({
                                "conta_id": c_id, "data_solicitacao": str(data_saque),
                                "valor": val_saque_f, "notas": notas_saque
                            }).execute()

                            novo_total_saques = float(c["total_saques"]) + val_saque_f
                            supabase.table("contas").update({
                                "total_saques": novo_total_saques,
                                "data_inicio_janela": str(data_saque)
                            }).eq("id", c_id).execute()

                            st.toast("Saque salvo no Supabase!", icon="✅")
                            st.success("Saque registrado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.toast(f"Erro: {str(e)}", icon="❌")

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
                        use_container_width=True,
                        hide_index=True
                    )

        # --- ABA DE OPÇÕES DA CONTA ---
        with tab_gerenciar:
            st.subheader(f"⚙️ Configurações da Conta: {c['nome']} ({c['mesa']})")
            
            with st.expander("✏️ Editar Dados, Prazo e Custos Desta Conta", expanded=True):
                with st.form("form_editar_conta_atual"):
                    c1_ed, c2_ed = st.columns(2)
                    with c1_ed:
                        ed_nome = st.text_input("Identificação da Conta"
