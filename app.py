import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import calendar
from datetime import date, datetime

# Configuração da página
st.set_page_config(page_title="Gestão de Mesas CME", layout="wide", page_icon="📈")

# --- FUNÇÕES DE FORMATAÇÃO E CONVERSÃO ---
def fmt_moeda(valor):
    """Formata no padrão $ 50.000,00"""
    if valor is None or pd.isna(valor):
        return "$ 0,00"
    sinal = "-" if valor < 0 else ""
    val_abs = abs(valor)
    formatado = f"{val_abs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}$ {formatado}"

def fmt_data(data_str):
    """Formata no padrão DD/MM/AAAA"""
    if not data_str or pd.isna(data_str):
        return "-"
    try:
        return pd.to_datetime(data_str).strftime("%d/%m/%Y")
    except:
        return str(data_str)

def converter_br_para_float(texto):
    """Converte '50.000,00' ou '-250,50' para float padrão"""
    if not texto:
        return 0.0
    limpo = str(texto).replace("R$", "").replace("$", "").strip()
    if "." in limpo and "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    return float(limpo)

def formatar_duracao(h, m, s):
    """Gera texto legível: '45s', '3m 12s', '1h 20m 15s'"""
    partes = []
    if h > 0:
        partes.append(f"{h}h")
    if m > 0 or h > 0:
        partes.append(f"{m}m")
    partes.append(f"{s}s")
    return " ".join(partes)

def parse_display_duracao(val):
    """Formata tanto trades antigos (só minutos) quanto os novos (h, m, s)"""
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

# --- BANCO DE DADOS ---
conn = sqlite3.connect("mesas_v4.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    trader TEXT,
    mesa TEXT,
    tamanho_conta TEXT,
    tipo TEXT,
    saldo_inicial REAL,
    max_dd REAL,
    limite_diario REAL,
    meta REAL,
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
    lotes REAL,
    resultado REAL,
    duracao_min TEXT,
    estrategia TEXT,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")

cursor.execute("CREATE TABLE IF NOT EXISTS ativos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS estrategias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")

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
ativos_df = pd.read_sql("SELECT nome FROM ativos ORDER BY nome ASC", conn)
estrategias_df = pd.read_sql("SELECT nome FROM estrategias ORDER BY nome ASC", conn)

# Menu Lateral
st.sidebar.title("Navegação")
menu = st.sidebar.radio(
    "Ir para:",
    ["📊 Painel Geral", "📁 Minhas Contas", "🛡️ Regras e Compliance", "➕ Cadastrar"]
)

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
        c1.metric("Resultado Líquido Global", fmt_moeda(total_lucro_global), delta=fmt_moeda(total_lucro_global))
        c2.metric("Saldo Total sob Gestão", fmt_moeda(saldo_global_atual))
        c3.metric("Total de Saques Realizados", fmt_moeda(total_saques_global))
        c4.metric("Total de Contas Ativas", len(contas_df))

        st.markdown("---")

        # RADAR TOP 3 CONTAS
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
                st.info(f"**{row['identificador']}**\n\n👤 Trader: `{row['trader']}` | Tam: `{row['tamanho']}`")
                
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
            df_tabela[["identificador", "trader", "mesa", "tamanho", "tipo", "Saldo Inicial", "Saldo Atual", "P&L Total", "Falta p/ Meta", "MAM/Dia"]].rename(
                columns={"identificador": "Conta", "trader": "Trader", "mesa": "Mesa", "tamanho": "Tamanho", "tipo": "Tipo"}
            ),
            use_container_width=True
        )

# =========================================================
# 2. MINHAS CONTAS (PAINEL, TRADES, ATIVOS E ESTRATÉGIAS)
# =========================================================
elif menu == "📁 Minhas Contas":
    if contas_df.empty:
        st.title("📁 Minhas Contas")
        st.warning("Cadastre suas contas na aba '➕ Cadastrar' primeiro.")
    else:
        lista_opcoes = [
            f"{c['id']} - {c['nome']} — {c['mesa']} ({c['tamanho_conta']}) | Trader: {c['trader']}"
            for _, c in contas_df.iterrows()
        ]
        
        conta_sel = st.selectbox("📂 Selecione a Conta para Acessar:", lista_opcoes)
        c_id = int(conta_sel.split(" - ")[0])
        c = contas_df[contas_df["id"] == c_id].iloc[0]

        st.title(f"📈 {c['nome']} — {c['mesa']}")
        st.markdown(f"👤 **Trader:** `{c['trader']}` | **Tamanho:** `{c['tamanho_conta']}` | **Tipo:** `{c['tipo']}` | **Saques Totais:** `{fmt_moeda(c['total_saques'])}`")

        tab_painel, tab_lancar, tab_gerenciar = st.tabs(["📊 Desempenho da Conta", "➕ Lançar Trade Nesta Conta", "⚙️ Opções da Conta"])

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
                t_view["Duração"] = t_view["duracao_min"].apply(parse_display_duracao)

                st.dataframe(
                    t_view[["Data", "ativo", "lotes", "Resultado", "Duração", "estrategia", "notas"]].rename(
                        columns={"ativo": "Ativo", "lotes": "Lotes", "estrategia": "Estratégia", "notas": "Notas"}
                    ).sort_values(by="Data", ascending=False),
                    use_container_width=True
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
                lotes = st.number_input("Qtd. de Contratos (Lotes)", min_value=0.1, value=1.0, step=0.5)

            with c2:
                ativo = st.selectbox("Ativo Operado", ativos_df["nome"].tolist())
                resultado_str = st.text_input("Resultado Líquido ($) (ex: 250,00 ou -150,00)", value="0,00")

            with c3:
                estrategia = st.selectbox("Estratégia Utilizada", estrategias_df["nome"].tolist())
                st.markdown("**Duração da Operação**")
                cd1, cd2, cd3 = st.columns(3)
                with cd1:
                    dur_h = st.number_input("Horas", min_value=0, max_value=72, value=0, step=1)
                with cd2:
                    dur_m = st.number_input("Min", min_value=0, max_value=59, value=5, step=1)
                with cd3:
                    dur_s = st.number_input("Seg", min_value=0, max_value=59, value=0, step=5)

            notas = st.text_area("Observações Técnicas / Psicológicas do Trade")

            st.write("") # Espaçamento visual

            # BOTÕES LADO A LADO: SALVAR | NOVO ATIVO | NOVA ESTRATÉGIA
            col_salvar, col_add_ativo, col_add_est = st.columns([1, 1.2, 1.2])

            with col_salvar:
                btn_salvar = st.button("💾 Salvar", type="primary", use_container_width=True)

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

            # Processamento do Salvar Trade
            if btn_salvar:
                try:
                    res_float = converter_br_para_float(resultado_str)
                    duracao_formatada = formatar_duracao(dur_h, dur_m, dur_s)
                    
                    cursor.execute("""
                    INSERT INTO trades (conta_id, data, ativo, lotes, resultado, duracao_min, estrategia, notas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (c_id, str(data_trade), ativo, lotes, res_float, duracao_formatada, estrategia, notas))
                    conn.commit()
                    st.toast("Atualizado", icon="✅")
                    st.success("Trade registrado com sucesso!")
                    st.rerun()
                except Exception:
                    st.toast("Erro, e tente novamente", icon="❌")
                    st.error("Erro, e tente novamente. Verifique os valores inseridos.")

        # --- ABA 3: EXCLUIR CONTA SELECIONADA ---
        with tab_gerenciar:
            st.subheader("Gerenciamento Desta Conta")
            st.warning(f"Você está na conta: **{c['nome']} ({c['mesa']})**")
            
            confirmar_del = st.checkbox(f"⚠️ Confirmo que desejo apagar definitivamente a conta '{c['nome']}' e todos os seus trades.")
            if st.button("🗑️ Excluir Esta Conta Definitivamente"):
                if confirmar_del:
                    try:
                        cursor.execute("DELETE FROM trades WHERE conta_id = ?", (c_id,))
                        cursor.execute("DELETE FROM contas WHERE id = ?", (c_id,))
                        conn.commit()
                        st.toast("Atualizado", icon="✅")
                        st.success("Conta removida com sucesso!")
                        st.rerun()
                    except Exception:
                        st.toast("Erro, e tente novamente", icon="❌")
                        st.error("Erro, e tente novamente ao excluir.")
                else:
                    st.warning("Marque a caixa de confirmação para prosseguir.")

# =========================================================
# 3. REGRAS E COMPLIANCE DA MESA
# =========================================================
elif menu == "🛡️ Regras e Compliance":
    st.title("🛡️ Auditoria de Regras da Mesa")
    if contas_df.empty:
        st.warning("Nenhuma conta encontrada.")
    else:
        lista_contas = [f"{c['id']} - {c['nome']} ({c['mesa']}) | Trader: {c['trader']}" for _, c in contas_df.iterrows()]
        conta_sel = st.selectbox("Selecione a Conta para Auditoria:", lista_contas)
        c_id = int(conta_sel.split(" - ")[0])
        c_info = contas_df[contas_df["id"] == c_id].iloc[0]

        t_all = trades_df[trades_df["conta_id"] == c_id].copy()
        if not t_all.empty and c_info["data_inicio_janela"]:
            t_janela = t_all[t_all["data"] >= c_info["data_inicio_janela"]].copy()
        else:
            t_janela = t_all.copy()

        st.markdown(f"### Conta: `{c_info['nome']}` | Trader: `{c_info['trader']}` | Mesa: `{c_info['mesa']}` | Tipo: `{c_info['tipo']}`")
        st.write(f"**Total Histórico em Saques:** `{fmt_moeda(c_info['total_saques'])}` | **Início da Janela:** `{fmt_data(c_info['data_inicio_janela'])}`")

        # REGRA 1: CONSISTÊNCIA DE SALDO
        st.subheader("1. Regra de Consistência de Saldo (Concentração Diária)")
        if c_info["tipo"] == "Challenge (Avaliação)":
            st.info("ℹ️ A regra de consistência de saldo NÃO se aplica a contas em avaliação (Challenge).")
        else:
            payouts = c_info["total_saques"]
            if c_info["tipo"] in ["Standard / Master", "No Activation"]:
                regra_pct = 0.40 if payouts <= 30000 else (0.30 if payouts <= 50000 else 0.20)
            else:
                regra_pct = 0.30 if payouts <= 50000 else 0.20

            if t_janela.empty:
                st.info("Nenhuma operação registrada na janela atual.")
            else:
                pnl_diario = t_janela.groupby("data")["resultado"].sum().reset_index()
                lucro_total = pnl_diario["resultado"].sum()
                maior_dia = pnl_diario["resultado"].max()

                c1, c2, c3 = st.columns(3)
                c1.metric("Lucro Líquido na Janela", fmt_moeda(lucro_total))
                c2.metric("Maior Ganho em 1 Dia", fmt_moeda(maior_dia))
                c3.metric("Teto Permitido", f"{int(regra_pct*100)}%")

                if lucro_total > 0 and maior_dia > 0:
                    rep = (maior_dia / lucro_total) * 100
                    if rep > (regra_pct * 100):
                        lucro_necessario = maior_dia / regra_pct
                        falta_diluir = lucro_necessario - lucro_total
                        st.error(f"❌ **VIOLAÇÃO DE CONSISTÊNCIA:** O maior dia representou {rep:.1f}% do lucro total (Teto: {int(regra_pct*100)}%).")
                        st.warning(f"💡 **Diluição Necessária:** Você precisa lucrar mais **{fmt_moeda(falta_diluir)}** em outros pregões para diluir a concentração.")
                    else:
                        st.success(f"✅ **REGRA APROVADA:** Maior dia representou {rep:.1f}% do lucro líquido.")

        # REGRA 2: MEDIANA (5x)
        st.markdown("---")
        st.subheader("2. Regra da Mediana das Operações Ganhadoras (Risco x Retorno)")
        trades_gain = t_janela[t_janela["resultado"] > 0]["resultado"]
        trades_loss = t_janela[t_janela["resultado"] < 0]["resultado"]

        if trades_gain.empty:
            st.info("Sem operações vencedoras para calcular a mediana.")
        else:
            mediana = float(np.median(trades_gain))
            teto_stop = 5.0 * mediana
            maior_loss = abs(trades_loss.min()) if not trades_loss.empty else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Mediana dos Ganhos", fmt_moeda(mediana))
            m2.metric("Stop Máximo Permitido (5x)", fmt_moeda(teto_stop))
            m3.metric("Maior Stop Realizado", fmt_moeda(maior_loss))

            if maior_loss > teto_stop:
                st.error(f"❌ **VIOLAÇÃO DA MEDIANA:** O stop de {fmt_moeda(maior_loss)} ultrapassou o teto de 5x a mediana ({fmt_moeda(teto_stop)}).")
            else:
                st.success("✅ **REGRA APROVADA:** Nenhuma perda excedeu 5x a mediana dos ganhos.")

        # REGRA 3: LOTES
        st.markdown("---")
        st.subheader("3. Consistência de Volume de Contratos")
        if not t_janela.empty:
            media_l = t_janela["lotes"].mean()
            l1, l2 = st.columns(2)
            l1.metric("Média de Lotes Operados", f"{media_l:.2f}")
            l2.metric("Lote Máximo Registrado", f"{t_janela['lotes'].max():.2f}")
            
            discrepantes = t_janela[t_janela["lotes"] > (media_l * 2.5)]
            if not discrepantes.empty:
                st.warning(f"⚠️ **Atenção:** {len(discrepantes)} operações com lotes superiores a 2.5x a sua média.")
            else:
                st.success("✅ **REGRA APROVADA:** Volume de contratos homogêneo.")

# =========================================================
# 4. CADASTRAR (APENAS NOVAS CONTAS)
# =========================================================
elif menu == "➕ Cadastrar":
    st.title("➕ Cadastrar Nova Conta")
    st.caption("Cadastre aqui apenas novas contas de mesas proprietárias que ainda não constam no sistema.")

    with st.form("form_cadastrar_conta"):
        c1, c2 = st.columns(2)
        with c1:
            nome = st.text_input("Identificação da Conta (ex: Apex 50k #1)")
            trader = st.text_input("Nome do Trader Responsável", value="Trader Principal")
            mesa = st.text_input("Nome da Mesa (ex: Ylos Trading, Mide Global, Apex)")
            tamanho_conta = st.selectbox("Tamanho da Conta", ["25k", "50k", "100k", "150k", "250k", "300k", "Outro"])
            tipo = st.selectbox("Tipo de Conta", [
                "Challenge (Avaliação)",
                "No Activation",
                "Standard / Master",
                "Instant Funding / Freedom"
            ])
        with c2:
            saldo_str = st.text_input("Saldo Inicial ($)", value="50.000,00")
            max_dd_str = st.text_input("Drawdown Máximo Permitido ($)", value="2.500,00")
            limite_diario_str = st.text_input("Limite Diário de Perda ($)", value="1.000,00")
            meta_str = st.text_input("Meta de Lucro ($)", value="3.000,00")
            total_saques_str = st.text_input("Total em Saques Já Aprovados ($)", value="0,00")
            data_inicio = st.date_input("Início da Janela de Saque", value=date.today(), format="DD/MM/YYYY")

        salvar = st.form_submit_button("Cadastrar Nova Conta")
        if salvar:
            try:
                if not nome or not mesa:
                    raise ValueError("Preencha nome e mesa.")
                
                s_ini = converter_br_para_float(saldo_str)
                m_dd = converter_br_para_float(max_dd_str)
                l_dia = converter_br_para_float(limite_diario_str)
                meta_val = converter_br_para_float(meta_str)
                saques_val = converter_br_para_float(total_saques_str)

                cursor.execute("""
                INSERT INTO contas (nome, trader, mesa, tamanho_conta, tipo, saldo_inicial, max_dd, limite_diario, meta, total_saques, data_inicio_janela)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nome, trader, mesa, tamanho_conta, tipo, s_ini, m_dd, l_dia, meta_val, saques_val, str(data_inicio)))
                conn.commit()
                
                st.toast("Atualizado", icon="✅")
                st.success("Conta cadastrada com sucesso!")
                st.rerun()
            except Exception:
                st.toast("Erro, e tente novamente", icon="❌")
                st.error("Erro, e tente novamente. Verifique se digitou os dados corretamente.")
