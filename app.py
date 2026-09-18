import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import calendar
from datetime import date, datetime

# Configuração da página
st.set_page_config(page_title="Gestão Profissional de Mesas CME", layout="wide", page_icon="🎯")

# --- CONEXÃO COM O BANCO DE DADOS ---
conn = sqlite3.connect("mesas_v3.db", check_same_thread=False)
cursor = conn.cursor()

# Tabela de Contas
cursor.execute("""
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
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

# Tabela de Trades
cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id INTEGER,
    data TEXT,
    ativo TEXT,
    lotes REAL,
    resultado REAL,
    duracao_min INTEGER,
    estrategia TEXT,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")
conn.commit()

# --- FUNÇÃO: PREGÕES ÚTEIS CME RESTANTES NO MÊS ---
def dias_uteis_cme_restantes():
    hoje = date.today()
    _, ultimo_dia = calendar.monthrange(hoje.year, hoje.month)
    uteis = 0
    for d in range(hoje.day, ultimo_dia + 1):
        if date(hoje.year, hoje.month, d).weekday() < 5:  # Segunda a Sexta
            uteis += 1
    return max(1, uteis)

# Carregar dados
contas_df = pd.read_sql("SELECT * FROM contas", conn)
trades_df = pd.read_sql("SELECT * FROM trades", conn)

# Menu Lateral
st.sidebar.title("Navegação")
menu = st.sidebar.radio(
    "Ir para:",
    ["📊 Painel Principal (Global & Individual)", "➕ Lançar Trade", "🛡️ Regras e Compliance", "⚙️ Gerenciar Contas"]
)

# =========================================================
# 1. PAINEL PRINCIPAL (VISÃO GLOBAL OU INDIVIDUAL)
# =========================================================
if menu == "📊 Painel Principal (Global & Individual)":
    if contas_df.empty:
        st.title("📊 Painel Geral")
        st.info("👋 Nenhuma conta cadastrada ainda. Acesse a aba **'⚙️ Gerenciar Contas'** para começar!")
    else:
        # Opção de alternar entre visão global ou individual
        opcoes_seletor = ["🌐 Visão Global (Todas as Contas)"] + [
            f"{c['nome']} — {c['mesa']} ({c['tamanho_conta']})" for _, c in contas_df.iterrows()
        ]
        
        selecao = st.selectbox("Selecione o Modo de Visualização:", opcoes_seletor)

        # -------------------------------------------------
        # MODO 1: VISÃO GLOBAL (CONSOLIDADO DE TODAS AS MESAS)
        # -------------------------------------------------
        if selecao == "🌐 Visão Global (Todas as Contas)":
            st.title("🌐 Visão Consolidada de Todas as Contas")
            
            # Cálculos Globais
            total_saldo_inicial = contas_df["saldo_inicial"].sum()
            total_lucro_global = trades_df["resultado"].sum() if not trades_df.empty else 0.0
            saldo_global_atual = total_saldo_inicial + total_lucro_global
            total_saques_global = contas_df["total_saques"].sum()

            # Métricas Globais no Topo
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Resultado Líquido Global", f"${total_lucro_global:,.2f}", delta=f"{total_lucro_global:,.2f}")
            col2.metric("Saldo Total sob Gestão", f"${saldo_global_atual:,.2f}")
            col3.metric("Total em Saques Realizados", f"${total_saques_global:,.2f}")
            col4.metric("Total de Contas Ativas", len(contas_df))

            st.markdown("---")

            # RADAR DAS 3 CONTAS PRIORITÁRIAS PARA HOJE
            st.subheader("🎯 Radar Diário: Contas Recomendadas para Hoje (Máx 3)")
            st.caption("Foco disciplinado: Evite inatividade de 7 dias e priorize contas com meta em aberto.")

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
                meta_diaria = falta_meta / dias_uteis

                # Pontuação de prioridade (Score)
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
                    "mesa": c["mesa"],
                    "tamanho": c["tamanho_conta"],
                    "tipo": c["tipo"],
                    "saldo_inicial": c["saldo_inicial"],
                    "saldo_atual": saldo_conta,
                    "pnl": lucro_conta,
                    "falta_meta": falta_meta,
                    "meta_diaria": meta_diaria,
                    "dias_sem_operar": dias_sem_operar,
                    "operou_hoje": operou_hoje,
                    "score": score
                })

            df_radar = pd.DataFrame(status_contas).sort_values(by="score", ascending=False)

            # Alerta de inatividade
            criticas = df_radar[df_radar["dias_sem_operar"] >= 5]
            if not criticas.empty:
                for _, cr in criticas.iterrows():
                    dias_txt = "Nunca operada" if cr["dias_sem_operar"] == 99 else f"{cr['dias_sem_operar']} dias sem trade"
                    st.error(f"⚠️ **ALERTA CRÍTICO (Regra dos 7 Dias):** A conta **{cr['identificador']}** está a **{dias_txt}**! Opere-a hoje para não ser cancelada.")

            # Exibir as 3 contas recomendadas
            top3 = df_radar.head(3)
            cols = st.columns(3)
            for i, (_, row) in enumerate(top3.iterrows()):
                with cols[i]:
                    titulo = "⭐ MÁXIMA ATENÇÃO: FOCO EM PERFORMANCE" if i == 0 else f"Opção #{i+1} do Dia"
                    st.markdown(f"#### {titulo}")
                    st.info(f"**{row['identificador']}**\nTamanho: `{row['tamanho']}` | Tipo: `{row['tipo']}`")
                    
                    d_txt = "Nunca" if row['dias_sem_operar'] == 99 else f"{row['dias_sem_operar']} dias atrás"
                    st.write(f"🕒 **Última Operação:** {d_txt}")
                    st.metric("Saldo Atual", f"${row['saldo_atual']:,.2f}", delta=f"${row['pnl']:,.2f}")
                    st.metric(f"Meta Diária CME ({dias_uteis} pregões)", f"${row['meta_diaria']:,.2f}/dia")

            st.markdown("---")
            st.subheader("📋 Tabela Consolidada de Contas")
            st.dataframe(
                df_radar[["identificador", "mesa", "tamanho", "tipo", "saldo_inicial", "saldo_atual", "pnl", "falta_meta"]].rename(
                    columns={
                        "identificador": "Conta", "mesa": "Mesa", "tamanho": "Tamanho", "tipo": "Tipo",
                        "saldo_inicial": "Saldo Inicial ($)", "saldo_atual": "Saldo Atual ($)",
                        "pnl": "P&L Total ($)", "falta_meta": "Falta p/ Meta ($)"
                    }
                ),
                use_container_width=True
            )

        # -------------------------------------------------
        # MODO 2: VISÃO INDIVIDUAL DA CONTA SELECIONADA
        # -------------------------------------------------
        else:
            idx_selecionado = opcoes_seletor.index(selecao) - 1
            c = contas_df.iloc[idx_selecionado]
            c_id = int(c["id"])

            st.title(f"📈 {c['nome']} — {c['mesa']}")
            st.caption(f"Tamanho: {c['tamanho_conta']} | Tipo: {c['tipo']} | Total Saques: ${c['total_saques']:,.2f}")

            t_conta = trades_df[trades_df["conta_id"] == c_id].copy()
            total_pnl = t_conta["resultado"].sum() if not t_conta.empty else 0.0
            saldo_atual = c["saldo_inicial"] + total_pnl
            drawdown_restante = saldo_atual - (c["saldo_inicial"] - c["max_dd"])
            falta_meta = max(0.0, (c["saldo_inicial"] + c["meta"]) - saldo_atual)
            dias_uteis = dias_uteis_cme_restantes()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Saldo Atual", f"${saldo_atual:,.2f}", delta=f"${total_pnl:,.2f}")
            m2.metric("Margem até Stop da Mesa", f"${drawdown_restante:,.2f}")
            m3.metric("Falta para o Alvo", f"${falta_meta:,.2f}")
            m4.metric(f"Alvo/Dia ({dias_uteis} pregões CME)", f"${(falta_meta / dias_uteis):,.2f}")

            st.markdown("---")

            if not t_conta.empty:
                t_conta = t_conta.sort_values(by="id")
                t_conta["Saldo_Acum"] = c["saldo_inicial"] + t_conta["resultado"].cumsum()

                fig = px.line(t_conta, x="data", y="Saldo_Acum", title="Curva de Patrimônio da Conta ($)", markers=True)
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Histórico de Trades Desta Conta")
                st.dataframe(
                    t_conta[["data", "ativo", "lotes", "resultado", "duracao_min", "estrategia", "notas"]].sort_values(by="data", ascending=False),
                    use_container_width=True
                )
                csv = t_conta.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Baixar Trades Desta Conta (CSV)", csv, f"trades_{c['nome']}.csv", "text/csv")
            else:
                st.info("Nenhuma operação cadastrada para esta conta ainda.")

# =========================================================
# 2. LANÇAMENTO DE TRADES
# =========================================================
elif menu == "➕ Lançar Trade":
    st.title("➕ Registro de Operação")
    if contas_df.empty:
        st.warning("Cadastre uma conta antes de lançar operações.")
    else:
        lista_contas = [f"{c['id']} - {c['nome']} ({c['mesa']} | {c['tamanho_conta']})" for _, c in contas_df.iterrows()]
        conta_sel = st.selectbox("Selecione a Conta", lista_contas)
        c_id = int(conta_sel.split(" - ")[0])

        with st.form("form_trade"):
            c1, c2, c3 = st.columns(3)
            with c1:
                data_trade = st.date_input("Data do Pregão", value=date.today())
                ativo = st.selectbox("Ativo Operado (CME)", ["NQ (Nasdaq)", "ES (S&P 500)", "YM (Dow)", "CL (Petróleo)", "GC (Ouro)", "RTY (Russell)", "Outro"])
            with c2:
                lotes = st.number_input("Qtd. de Contratos (Lotes)", min_value=0.1, value=1.0, step=0.5)
                resultado = st.number_input("Resultado Líquido ($)", value=0.0, step=25.0, help="Coloque sinal de menos (-) para perdas.")
            with c3:
                duracao = st.number_input("Duração da Operação (Minutos)", min_value=1, value=15, step=1)
                estrategia = st.selectbox("Estratégia", ["Rompimento", "Pullback / Tendência", "Reversão / VWAP", "Scalping", "Abertura / Notícia", "Outra"])

            notas = st.text_area("Observações (Gatilho, disciplina emocional, erros ou acertos)")
            salvar = st.form_submit_button("Salvar Trade")
            if salvar:
                cursor.execute("""
                INSERT INTO trades (conta_id, data, ativo, lotes, resultado, duracao_min, estrategia, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (c_id, str(data_trade), ativo, lotes, resultado, duracao, estrategia, notas))
                conn.commit()
                st.success("Trade registrado com sucesso!")

# =========================================================
# 3. REGRAS E COMPLIANCE DA MESA
# =========================================================
elif menu == "🛡️ Regras e Compliance":
    st.title("🛡️ Auditoria de Regras da Mesa")
    if contas_df.empty:
        st.warning("Nenhuma conta encontrada.")
    else:
        lista_contas = [f"{c['id']} - {c['nome']} ({c['mesa']})" for _, c in contas_df.iterrows()]
        conta_sel = st.selectbox("Selecione a Conta para Auditoria:", lista_contas)
        c_id = int(conta_sel.split(" - ")[0])
        c_info = contas_df[contas_df["id"] == c_id].iloc[0]

        t_all = trades_df[trades_df["conta_id"] == c_id].copy()
        if not t_all.empty and c_info["data_inicio_janela"]:
            t_janela = t_all[t_all["data"] >= c_info["data_inicio_janela"]].copy()
        else:
            t_janela = t_all.copy()

        st.markdown(f"### Conta: `{c_info['nome']}` | Mesa: `{c_info['mesa']}` | Tipo: `{c_info['tipo']}`")
        st.write(f"**Saques Totais Aprovados:** `${c_info['total_saques']:,.2f}`")

        # REGRA 1: CONSISTÊNCIA DE SALDO
        st.subheader("1. Regra de Consistência de Saldo (Concentração Diária)")
        if c_info["tipo"] == "Challenge (Avaliação)":
            st.info("ℹ️ A regra de consistência de saldo **NÃO** se aplica a contas em fase de Challenge.")
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
                c1.metric("Lucro Líquido na Janela", f"${lucro_total:,.2f}")
                c2.metric("Maior Ganho em 1 Dia", f"${maior_dia:,.2f}")
                c3.metric("Teto Permitido", f"{int(regra_pct*100)}%")

                if lucro_total > 0 and maior_dia > 0:
                    rep = (maior_dia / lucro_total) * 100
                    if rep > (regra_pct * 100):
                        lucro_necessario = maior_dia / regra_pct
                        falta_diluir = lucro_necessario - lucro_total
                        st.error(f"❌ **VIOLAÇÃO DE CONSISTÊNCIA:** O maior dia foi {rep:.1f}% do total (Máx: {int(regra_pct*100)}%).")
                        st.warning(f"💡 **Diluição Necessária:** Lucre mais **${falta_diluir:,.2f}** em outros dias para liberar seu saque dentro da regra.")
                    else:
                        st.success(f"✅ **REGRA APROVADA:** Melhor dia representou {rep:.1f}% do lucro total.")

        # REGRA 2: MEDIANA (5x)
        st.markdown("---")
        st.subheader("2. Regra da Mediana das Operações Ganhadoras (Risco x Retorno)")
        trades_gain = t_janela[t_janela["resultado"] > 0]["resultado"]
        trades_loss = t_janela[t_janela["resultado"] < 0]["resultado"]

        if trades_gain.empty:
            st.info("Sem trades vencedores para calcular a mediana.")
        else:
            mediana = float(np.median(trades_gain))
            teto_stop = 5.0 * mediana
            maior_loss = abs(trades_loss.min()) if not trades_loss.empty else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Mediana dos Ganhos", f"${mediana:,.2f}")
            m2.metric("Stop Máximo Permitido (5x)", f"${teto_stop:,.2f}")
            m3.metric("Maior Stop Realizado", f"${maior_loss:,.2f}")

            if maior_loss > teto_stop:
                st.error(f"❌ **VIOLAÇÃO DA MEDIANA:** Perda de ${maior_loss:,.2f} ultrapassou o teto permitido de ${teto_stop:,.2f}.")
            else:
                st.success("✅ **REGRA APROVADA:** Nenhuma perda ultrapassou 5x a mediana dos ganhos.")

        # REGRA 3: CONSISTÊNCIA DE LOTES
        st.markdown("---")
        st.subheader("3. Consistência de Contratos Operados")
        if not t_janela.empty:
            media_l = t_janela["lotes"].mean()
            l1, l2 = st.columns(2)
            l1.metric("Média de Lotes", f"{media_l:.2f}")
            l2.metric("Lote Máximo", f"{t_janela['lotes'].max():.2f}")
            
            discrepantes = t_janela[t_janela["lotes"] > (media_l * 2.5)]
            if not discrepantes.empty:
                st.warning(f"⚠️ **Atenção:** {len(discrepantes)} operações com lotes superiores a 2.5x a sua média.")
            else:
                st.success("✅ **REGRA APROVADA:** Volume de contratos homogêneo.")

# =========================================================
# 4. GERENCIAR E EXCLUIR CONTAS
# =========================================================
elif menu == "⚙️ Gerenciar Contas":
    st.title("⚙️ Gerenciamento de Contas")

    # Formulário de Cadastro
    with st.expander("➕ Cadastrar Nova Conta de Mesa", expanded=True):
        with st.form("nova_conta"):
            c1, c2 = st.columns(2)
            with c1:
                nome = st.text_input("Identificação da Conta (ex: Conta Principal, Apex 1)")
                mesa = st.text_input("Nome da Mesa (ex: Ylos Trading, Mide Global, Apex, TradeDay)")
                tamanho_conta = st.selectbox("Tamanho da Conta", ["25k", "50k", "100k", "150k", "250k", "300k", "Outro"])
                tipo = st.selectbox("Tipo de Conta", [
                    "Challenge (Avaliação)",
                    "No Activation",
                    "Standard / Master",
                    "Instant Funding / Freedom"
                ])
            with c2:
                saldo_inicial = st.number_input("Saldo Inicial ($)", value=50000.0, step=5000.0)
                max_dd = st.number_input("Drawdown Máximo Permitido ($)", value=2500.0, step=100.0)
                limite_diario = st.number_input("Limite Diário ($)", value=1000.0, step=100.0)
                meta = st.number_input("Meta de Lucro ($)", value=3000.0, step=100.0)
                total_saques = st.number_input("Total já sacado em todas as contas ($)", value=0.0, step=1000.0)
                data_inicio = st.date_input("Início da Janela (Data de ativação ou último saque)", value=date.today())

            salvar = st.form_submit_button("Cadastrar Conta")
            if salvar and nome and mesa:
                cursor.execute("""
                INSERT INTO contas (nome, mesa, tamanho_conta, tipo, saldo_inicial, max_dd, limite_diario, meta, total_saques, data_inicio_janela)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nome, mesa, tamanho_conta, tipo, saldo_inicial, max_dd, limite_diario, meta, total_saques, str(data_inicio)))
                conn.commit()
                st.success(f"Conta '{nome}' da mesa '{mesa}' cadastrada com sucesso!")
                st.rerun()

    # Seção de Exclusão de Contas
    if not contas_df.empty:
        st.markdown("---")
        st.subheader("🗑️ Excluir Conta")
        
        lista_para_excluir = [f"{c['id']} - {c['nome']} ({c['mesa']} | {c['tamanho_conta']})" for _, c in contas_df.iterrows()]
        conta_a_apagar = st.selectbox("Selecione a conta que deseja remover definitivamente:", lista_para_excluir)
        id_apagar = int(conta_a_apagar.split(" - ")[0])

        confirmar = st.checkbox("⚠️ Confirmo que desejo apagar esta conta e TODOS os seus trades registrados.")
        if st.button("Excluir Conta Definitivamente"):
            if confirmar:
                cursor.execute("DELETE FROM trades WHERE conta_id = ?", (id_apagar,))
                cursor.execute("DELETE FROM contas WHERE id = ?", (id_apagar,))
                conn.commit()
                st.success("Conta e histórico removidos com sucesso!")
                st.rerun()
            else:
                st.warning("Por favor, marque a caixinha de confirmação para poder excluir.")

        st.markdown("---")
        st.subheader("Contas Ativas")
        st.dataframe(contas_df[["id", "nome", "mesa", "tamanho_conta", "tipo", "saldo_inicial", "meta", "total_saques"]], use_container_width=True)
