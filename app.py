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

    # Caso esteja dentro de [supabase]
    if not raw_url and "supabase" in st.secrets:
        raw_url = str(st.secrets["supabase"].get("url", "")).strip().strip('"').strip("'")
        raw_key = str(st.secrets["supabase"].get("key", "")).strip().strip('"').strip("'")

    # Fallback seguro para o ID confirmado do seu projeto
    if "smvgfhdulefoyzmwvugp" in raw_url or not raw_url:
        sb_url = "https://smvgfhdulefoyzmwvugp.supabase.co"
    else:
        # Limpeza automática de URL
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

                        prazo_opcoes = [
                            "Sem prazo máximo (Indeterminado / Ylos)",
                            "30 dias corridos",
                            "60 dias corridos"
                        ]
                        prazo_salvo = c.get('prazo_avaliacao', 'Sem prazo máximo (Indeterminado / Ylos)')
                        idx_prazo = prazo_opcoes.index(prazo_salvo) if prazo_salvo in prazo_opcoes else 0
                        ed_prazo = st.selectbox("Regra de Prazo de Aprovação", prazo_opcoes, index=idx_prazo)

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
                        ed_dt_janela = st.date_input("Início da Janela / Operações", value=dt_janela_val, format="DD/MM/YYYY")

                    salvar_ed_conta = st.form_submit_button("💾 Salvar Alterações no Supabase")
                    if salvar_ed_conta:
                        try:
                            supabase.table("contas").update({
                                "nome": ed_nome, "trader": ed_trader, "mesa": ed_mesa,
                                "tamanho_conta": ed_tamanho, "tipo": ed_tipo, "status": ed_status,
                                "saldo_inicial": converter_br_para_float(ed_saldo),
                                "max_dd": converter_br_para_float(ed_dd),
                                "limite_diario": converter_br_para_float(ed_limite),
                                "meta": converter_br_para_float(ed_meta),
                                "custo_mesa": converter_br_para_float(ed_c_mesa),
                                "custo_ativacao": converter_br_para_float(ed_c_ativ),
                                "custo_reset": converter_br_para_float(ed_c_reset),
                                "outros_custos": converter_br_para_float(ed_c_outros),
                                "data_inicio_janela": str(ed_dt_janela),
                                "prazo_avaliacao": ed_prazo
                            }).eq("id", c_id).execute()
                            st.toast("Conta atualizada no Supabase!", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.toast(f"Erro: {str(e)}", icon="❌")

            st.markdown("---")
            st.subheader("Zona de Perigo")
            confirmar_del = st.checkbox(f"⚠️ Confirmo que desejo apagar definitivamente a conta '{c['nome']}' do Supabase.")
            if st.button("🗑️ Excluir Esta Conta Definitivamente"):
                if confirmar_del:
                    try:
                        supabase.table("contas").delete().eq("id", c_id).execute()
                        st.toast("Conta removida do banco na nuvem!", icon="✅")
                        st.rerun()
                    except Exception as e:
                        st.toast(f"Erro ao excluir: {str(e)}", icon="❌")
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
        for idx_rel, (_, r) in enumerate(contas_df.iterrows(), start=1):
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
                "Nº": idx_rel,
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
        st.dataframe(df_relatorio_view, use_container_width=True, hide_index=True)

        st.subheader("📈 Comparativo: Capital Investido vs. Retorno por Conta")
        graf_df = contas_df[["nome", "custo_total", "total_saques"]].copy()
        graf_df = graf_df.rename(columns={"custo_total": "Total Investido ($)", "total_saques": "Total Sacado ($)"})
        graf_melt = graf_df.melt(id_vars=["nome"], value_vars=["Total Investido ($)", "Total Sacado ($)"], var_name="Métrica", value_name="Valor ($)")
        
        fig_bar = px.bar(graf_melt, x="nome", y="Valor ($)", color="Métrica", barmode="group", title="Investido vs. Retorno Sacado por Conta")
        st.plotly_chart(fig_bar, use_container_width=True)

# =========================================================
# 4. REGRAS E COMPLIANCE DA MESA
# =========================================================
elif menu == "🛡️ Regras e Compliance":
    st.title("🛡️ Auditoria de Regras & Compliance")
    st.caption("Diagnóstico matemático oficial: status em tempo real e cálculo da solução caso alguma regra seja violada.")

    if contas_df.empty:
        st.warning("Nenhuma conta encontrada.")
    else:
        mapa_contas_audit = {}
        lista_contas_audit = []
        for idx_a, (_, c_aud) in enumerate(contas_df.iterrows(), start=1):
            rotulo_aud = f"Conta #{idx_a}: {c_aud['nome']} ({c_aud['mesa']}) | {c_aud['tipo']} [{c_aud['status']}]"
            lista_contas_audit.append(rotulo_aud)
            mapa_contas_audit[rotulo_aud] = int(c_aud['id'])

        conta_sel = st.selectbox("Selecione a Conta para Auditoria:", lista_contas_audit)
        c_id = mapa_contas_audit[conta_sel]
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
        st.write(f"**Total em Saques:** `{fmt_moeda(c_info['total_saques'])}` | **Janela Atual Iniciada em:** `{fmt_data(c_info['data_inicio_janela'])}` | **Regra de Prazo:** `{c_info.get('prazo_avaliacao', 'Sem prazo')}`")
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
    st.caption("Faça o download de cópias locais ou gerencie os dados salvos com segurança no Supabase.")

    col_bkg1, col_bkg2 = st.columns(2)

    with col_bkg1:
        st.subheader("📥 Exportar Backup Completo")
        st.write("Gera uma cópia JSON de segurança de todo o banco do Supabase.")
        
        dados_backup = {
            "contas": contas_df.to_dict(orient="records"),
            "trades": trades_df.to_dict(orient="records"),
            "saques": saques_df.to_dict(orient="records"),
            "ativos": ativos_df.to_dict(orient="records"),
            "estrategias": estrategias_df.to_dict(orient="records")
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
        st.info(f"📊 **Dados salvos no Supabase:**\n- **{len(contas_df)}** conta(s)\n- **{len(trades_df)}** trade(s)\n- **{len(saques_df)}** saque(s)")

    with col_bkg2:
        st.subheader("📤 Restaurar Backup (.json)")
        st.write("Envie um arquivo `.json` gerado anteriormente para preencher o Supabase.")

        arquivo_upload = st.file_uploader("Selecione o arquivo de backup (.json)", type=["json"])
        if arquivo_upload is not None:
            if st.button("Restaurar Dados no Supabase Agora", use_container_width=True):
                try:
                    conteudo = json.load(arquivo_upload)

                    if "contas" in conteudo and conteudo["contas"]:
                        for r in conteudo["contas"]:
                            r_clean = {k: v for k, v in r.items() if k != "id"}
                            supabase.table("contas").insert(r_clean).execute()

                    if "trades" in conteudo and conteudo["trades"]:
                        for r in conteudo["trades"]:
                            r_clean = {k: v for k, v in r.items() if k != "id"}
                            supabase.table("trades").insert(r_clean).execute()

                    if "saques" in conteudo and conteudo["saques"]:
                        for r in conteudo["saques"]:
                            r_clean = {k: v for k, v in r.items() if k != "id"}
                            supabase.table("saques").insert(r_clean).execute()

                    st.toast("Backup Restaurado no Supabase!", icon="✅")
                    st.success("Todos os dados do arquivo foram gravados na nuvem!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro ao processar arquivo de restauração: {str(ex)}")

    st.markdown("---")
    st.subheader("🧹 Zerar Banco de Dados no Supabase")
    st.caption("Use esta opção se quiser apagar todos os testes feitos até agora para começar o cadastro oficial com a primeira conta sendo a Conta #1.")
    
    chk_reset_total = st.checkbox("⚠️ Confirmo que desejo apagar todas as contas, trades e saques no Supabase.")
    if st.button("Zerar Sistema no Supabase"):
        if chk_reset_total:
            try:
                supabase.table("trades").delete().neq("id", 0).execute()
                supabase.table("saques").delete().neq("id", 0).execute()
                supabase.table("contas").delete().neq("id", 0).execute()
                st.toast("Supabase zerado com sucesso!", icon="✅")
                st.success("Tudo limpo! Agora você pode ir em '➕ Cadastrar' e criar sua Conta #1 oficial.")
                st.rerun()
            except Exception as e_reset:
                st.error(f"Erro ao zerar banco: {str(e_reset)}")
        else:
            st.warning("Marque a caixa de confirmação acima para prosseguir.")

# =========================================================
# 6. CADASTRAR NOVA CONTA (NO SUPABASE)
# =========================================================
elif menu == "➕ Cadastrar":
    st.title("➕ Cadastrar Nova Conta")
    st.caption("Cadastre novas contas diretamente no Supabase. O saldo inicial é preenchido proporcionalmente ao tamanho escolhido.")

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
        nome = st.text_input("Identificação da Conta", value="", placeholder="ex: Apex 50k #1 ou Ylos Freedom")
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
