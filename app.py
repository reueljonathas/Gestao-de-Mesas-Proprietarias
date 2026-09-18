import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import calendar
from datetime import date, datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Gestão Profissional de Mesas CME", layout="wide", page_icon="🎯")

# --- BANCO DE DADOS ---
conn = sqlite3.connect("mesas_v2.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
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
    duracao_min INTEGER,
    estrategia TEXT,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")
conn.commit()

# --- FUNÇÃO: DIAS ÚTEIS RESTANTES NA CME NO MÊS ---
def dias_uteis_cme_restantes():
    hoje = date.today()
    _, ultimo_dia = calendar.monthrange(hoje.year, hoje.month)
    uteis = 0
    # Pregões regulares CME (Segunda a Sexta)
    for d in range(hoje.day, ultimo_dia + 1):
        dia_semana = date(hoje.year, hoje.month, d).weekday()
        if dia_semana < 5:  # 0=Segunda, 4=Sexta
            uteis += 1
    return max(1, uteis)

# --- CARREGAR DADOS ---
contas_df = pd.read_sql("SELECT * FROM contas", conn)
trades_df = pd.read_sql("SELECT * FROM trades", conn)

# Menu Superior / Lateral
st.sidebar.title("Navegação")
menu = st.sidebar.radio(
    "Ir para:",
    ["🎯 Radar Diário (Top 3)", "📈 Painel da Conta", "➕ Lançar Trade", "🛡️ Regras e Compliance", "⚙️ Gerenciar Contas"]
)

# ==========================================
# 1. RADAR DIÁRIO INTELIGENTE (TOP 3 CONTAS)
# ==========================================
if menu == "🎯 Radar Diário (Top 3)":
    st.title("🎯 Radar de Operação Diária")
    st.caption("Foco disciplinado: Opere no máximo 3 contas por dia respeitando a inatividade e performance.")

    if contas_df.empty:
        st.info("Nenhuma conta cadastrada. Acesse '⚙️ Gerenciar Contas' para começar.")
    else:
        hoje = date.today()
        dias_uteis = dias_uteis_cme_restantes()
        
        status_contas = []
        for _, c in contas_df.iterrows():
            t_conta = trades_df[trades_df["conta_id"] == c["id"]]
            
            # Último dia operado
            if not t_conta.empty:
                ult_data_str = t_conta["data"].max()
                ult_data = datetime.strptime(ult_data_str, "%Y-%m-%d").date()
                dias_sem_operar = (hoje - ult_data).days
                operou_hoje = (ult_data == hoje)
            else:
                dias_sem_operar = 99
                operou_hoje = False
            
            lucro_total = t_conta["resultado"].sum() if not t_conta.empty else 0.0
            saldo_atual = c["saldo_inicial"] + lucro_total
            alvo = c["saldo_inicial"] + c["meta"]
            falta_meta = max(0.0, alvo - saldo_atual)
            meta_diaria_cme = falta_meta / dias_uteis
            
            # Score de prioridade: Inatividade alta (peso maior) + urgência de performance
            score = 0
            if dias_sem_operar >= 5:
                score += 1000 + dias_sem_operar * 50  # Prioridade crítica
            elif dias_sem_operar >= 3:
                score += 300 + dias_sem_operar * 20
            
            if not operou_hoje:
                score += 100  # Rotatividade inteligente
            
            # Mais perto da meta ganha relevância de foco
            if falta_meta > 0:
                progresso = (lucro_total / c["meta"]) if c["meta"] > 0 else 0
                score += max(0, min(100, progresso * 100))

            status_contas.append({
                "id": c["id"],
                "nome": c["nome"],
                "tipo": c["tipo"],
                "dias_sem_operar": dias_sem_operar,
                "operou_hoje": operou_hoje,
                "saldo_atual": saldo_atual,
                "falta_meta": falta_meta,
                "meta_diaria_cme": meta_diaria_cme,
                "score": score
            })

        df_radar = pd.DataFrame(status_contas).sort_values(by="score", ascending=False)
        
        # Alerta de inatividade
        criticas = df_radar[df_radar["dias_sem_operar"] >= 5]
        if not criticas.empty:
            for _, cr in criticas.iterrows():
                dias = "Nunca operada" if cr["dias_sem_operar"] == 99 else f"{cr['dias_sem_operar']} dias sem operar"
                st.error(f"⚠️ **ALERTA DE RISCO DE INATIVIDADE (Regra dos 7 Dias):** A conta **{cr['nome']}** está a **{dias}**! Opere-a imediatamente para evitar cancelamento pela mesa.")

        st.subheader("📋 As 3 Contas Recomendadas para Hoje:")
        top3 = df_radar.head(3)

        cols = st.columns(3)
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols[i]:
                destaque = "⭐ CONTA COM FOCO EM PERFORMANCE" if i == 0 else f"Opção #{i+1} de Hoje"
                st.markdown(f"### {destaque}")
                st.markdown(f"**Conta:** `{row['nome']}` ({row['tipo']})")
                
                dias_txt = "Nunca" if row['dias_sem_operar'] == 99 else f"{row['dias_sem_operar']} dias atrás"
                st.write(f"🕒 **Última Operação:** {dias_txt}")
                st.metric("Saldo Atual", f"${row['saldo_atual']:,.2f}")
                st.metric("Falta p/ Alvo", f"${row['falta_meta']:,.2f}")
                st.metric(f"Meta Diária ({dias_uteis} pregões CME)", f"${row['meta_diaria_cme']:,.2f}/dia")
                
                if row["operou_hoje"]:
                    st.success("✅ Já operou hoje!")
                else:
                    st.info("⏳ Aguardando operação hoje")

# ==========================================
# 2. LANÇAMENTO DETALHADO DE TRADE
# ==========================================
elif menu == "➕ Lançar Trade":
    st.title("➕ Registro de Trade por Trade")
    if contas_df.empty:
        st.warning("Cadastre uma conta antes de lançar.")
    else:
        conta_sel = st.selectbox("Selecione a Conta", contas_df["nome"].tolist())
        c_id = int(contas_df[contas_df["nome"] == conta_sel]["id"].values[0])

        with st.form("form_trade"):
            col1, col2, col3 = st.columns(3)
            with col1:
                data_trade = st.date_input("Data da Operação", value=date.today())
                ativo = st.selectbox("Ativo Operado", ["NQ (Nasdaq)", "ES (S&P 500)", "YM (Dow)", "CL (Petróleo)", "GC (Ouro)", "RTY (Russell)", "Outro"])
            with col2:
                lotes = st.number_input("Qtd. de Contratos / Lotes", min_value=0.1, value=1.0, step=0.5)
                resultado = st.number_input("Resultado Líquido do Trade ($)", value=0.0, step=25.0, help="Use valor negativo se foi loss.")
            with col3:
                duracao = st.number_input("Tempo de Operação (Minutos)", min_value=1, value=15, step=1)
                estrategia = st.selectbox("Estratégia Utilizada", ["Rompimento", "Pullback / Tendência", "Reversão / VWAP", "Scalping Rápido", "Notícia / Abertura", "Outra"])

            notas = st.text_area("Observações do Trade (Gatilho de entrada, disciplina, erros cometidos)")
            
            salvar = st.form_submit_button("Registrar Trade")
            if salvar:
                cursor.execute("""
                INSERT INTO trades (conta_id, data, ativo, lotes, resultado, duracao_min, estrategia, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (c_id, str(data_trade), ativo, lotes, resultado, duracao, estrategia, notas))
                conn.commit()
                st.success("Trade registrado com sucesso! Atualize a página para refletir no compliance.")

# ==========================================
# 3. REGRAS E COMPLIANCE DA MESA
# ==========================================
elif menu == "🛡️ Regras e Compliance":
    st.title("🛡️ Auditoria de Conformidade e Regras da Mesa")

    if contas_df.empty:
        st.warning("Nenhuma conta encontrada.")
    else:
        conta_sel = st.selectbox("Selecione a Conta para Auditoria:", contas_df["nome"].tolist())
        c_info = contas_df[contas_df["nome"] == conta_sel].iloc[0]
        c_id = int(c_info["id"])

        # Filtrar trades da janela atual de saque
        t_all = trades_df[trades_df["conta_id"] == c_id].copy()
        if not t_all.empty and c_info["data_inicio_janela"]:
            t_janela = t_all[t_all["data"] >= c_info["data_inicio_janela"]].copy()
        else:
            t_janela = t_all.copy()

        st.markdown(f"### Conta: `{c_info['nome']}` | Modalidade: `{c_info['tipo']}`")
        st.write(f"**Total Histórico em Saques Aprovados:** `${c_info['total_saques']:,.2f}`")

        # -----------------------------------------------------------------
        # REGRA 1: CONSISTÊNCIA DE SALDO (40% / 30% / 20%)
        # -----------------------------------------------------------------
        st.subheader("1. Regra de Consistência de Saldo")
        
        if c_info["tipo"] == "Challenge (Avaliação)":
            st.info("ℹ️ A regra de consistência de saldo **NÃO** se aplica a contas em fase de Challenge (apenas contas Funded / Instant).")
        else:
            # Determinar porcentagem limite baseada nos saques totais
            payouts = c_info["total_saques"]
            if c_info["tipo"] == "Standard / Master / No Activation":
                if payouts <= 30000:
                    regra_pct = 0.40
                elif payouts <= 50000:
                    regra_pct = 0.30
                else:
                    regra_pct = 0.20
            else: # Instant Funding / Freedom
                if payouts <= 50000:
                    regra_pct = 0.30
                else:
                    regra_pct = 0.20

            if t_janela.empty:
                st.info("Nenhuma operação registrada na janela atual para calcular consistência.")
            else:
                # Agrupar por dia
                pnl_diario = t_janela.groupby("data")["resultado"].sum().reset_index()
                lucro_liquido_janela = pnl_diario["resultado"].sum()
                maior_dia_lucro = pnl_diario["resultado"].max()

                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Lucro Líquido na Janela", f"${lucro_liquido_janela:,.2f}")
                col_b.metric("Maior Lucro em 1 Único Dia", f"${maior_dia_lucro:,.2f}")
                col_c.metric("Limite de Concentração Permitido", f"{int(regra_pct*100)}%")

                if lucro_liquido_janela > 0 and maior_dia_lucro > 0:
                    representatividade = (maior_dia_lucro / lucro_liquido_janela) * 100
                    
                    if representatividade > (regra_pct * 100):
                        # Cálculo da diluição necessária:
                        # Lucro Total Necessário = Maior Dia / regra_pct
                        lucro_necessario_total = maior_dia_lucro / regra_pct
                        falta_lucrar_diluicao = lucro_necessario_total - lucro_liquido_janela

                        st.error(f"❌ **VIOLAÇÃO DE CONSISTÊNCIA:** O seu melhor dia representou **{representatividade:.1f}%** do lucro (Máximo: {int(regra_pct*100)}%).")
                        st.warning(f"💡 **Como corrigir (Diluição):** Para que seu saque seja aprovado sem ferir a regra, você precisa fazer mais **${falta_lucrar_diluicao:,.2f}** de lucro em outros dias para diluir o ganho daquele dia.")
                    else:
                        st.success(f"✅ **REGRA APROVADA:** Seu melhor dia representou **{representatividade:.1f}%** do lucro (abaixo do teto de {int(regra_pct*100)}%).")
                else:
                    st.write("A conta ainda não atingiu lucro positivo acumulado na janela.")

        # -----------------------------------------------------------------
        # REGRA 2: RISCO X RETORNO (REGRA DA MEDIANA - 5x)
        # -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("2. Regra da Mediana das Operações Ganhadoras (Risco x Retorno)")
        st.caption("Regra: O seu prejuízo financeiro máximo em uma única operação não pode ser superior a 5x a mediana das suas operações ganhadoras.")

        trades_gain = t_janela[t_janela["resultado"] > 0]["resultado"]
        trades_loss = t_janela[t_janela["resultado"] < 0]["resultado"]

        if trades_gain.empty:
            st.info("Nenhum trade com lucro registrado para calcular a mediana.")
        else:
            mediana_gain = float(np.median(trades_gain))
            limite_max_stop = 5.0 * mediana_gain
            maior_loss_unico = abs(trades_loss.min()) if not trades_loss.empty else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Mediana dos Trades Ganhadores", f"${mediana_gain:,.2f}")
            m2.metric("Prejuízo Máximo Permitido (5x)", f"${limite_max_stop:,.2f}")
            m3.metric("Maior Loss Realizado", f"${maior_loss_unico:,.2f}")

            if maior_loss_unico > limite_max_stop:
                st.error(f"❌ **VIOLAÇÃO DA REGRA DA MEDIANA:** Você teve uma operação com perda de **${maior_loss_unico:,.2f}**, que ultrapassou o teto permitido de **${limite_max_stop:,.2f}** (5x a mediana).")
            else:
                st.success("✅ **REGRA APROVADA:** Nenhuma perda individual ultrapassou o limite de 5x a mediana dos ganhos.")

        # -----------------------------------------------------------------
        # REGRA 3: CONSISTÊNCIA DE CONTRATOS (LOTES)
        # -----------------------------------------------------------------
        st.markdown("---")
        st.subheader("3. Consistência de Contratos e Lotes")
        
        if t_janela.empty:
            st.info("Sem histórico de lotes.")
        else:
            media_lotes = t_janela["lotes"].mean()
            max_lotes = t_janela["lotes"].max()
            min_lotes = t_janela["lotes"].min()

            l1, l2, l3 = st.columns(3)
            l1.metric("Média de Lotes Operados", f"{media_lotes:.2f}")
            l2.metric("Lote Máximo Utilizado", f"{max_lotes:.2f}")
            l3.metric("Lote Mínimo Utilizado", f"{min_lotes:.2f}")

            # Alerta se houver operações com mais que 2.5x a média ou micro trades (< 0.25x)
            anomalias_alta = t_janela[t_janela["lotes"] > (media_lotes * 2.5)]
            if not anomalias_alta.empty:
                st.warning(f"⚠️ **Atenção para Variação Excessiva:** Foram detectadas {len(anomalias_alta)} operações com mais de 2.5x a sua mão média habitual. Evite alavancagens repentinas para não caracterizar violação de consistência de volume.")
            else:
                st.success("✅ **REGRA APROVADA:** Dimensionamento de lotes consistente com o seu histórico.")

# ==========================================
# 4. PAINEL GERAL E PERFORMANCE
# ==========================================
elif menu == "📈 Painel da Conta":
    st.title("📈 Painel da Conta & Desempenho")
    if contas_df.empty:
        st.warning("Nenhuma conta cadastrada.")
    else:
        conta_sel = st.selectbox("Conta:", contas_df["nome"].tolist())
        c = contas_df[contas_df["nome"] == conta_sel].iloc[0]
        c_id = int(c["id"])

        t_conta = trades_df[trades_df["conta_id"] == c_id].copy()
        
        total_pnl = t_conta["resultado"].sum() if not t_conta.empty else 0.0
        saldo_atual = c["saldo_inicial"] + total_pnl
        drawdown_restante = saldo_atual - (c["saldo_inicial"] - c["max_dd"])
        falta_meta = max(0.0, (c["saldo_inicial"] + c["meta"]) - saldo_atual)
        dias_uteis = dias_uteis_cme_restantes()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Saldo Atual", f"${saldo_atual:,.2f}", delta=f"${total_pnl:,.2f}")
        c2.metric("Margem até Stop da Mesa", f"${drawdown_restante:,.2f}")
        c3.metric("Falta para o Alvo", f"${falta_meta:,.2f}")
        c4.metric(f"Alvo/Dia ({dias_uteis} dias CME)", f"${(falta_meta/dias_uteis):,.2f}")

        if not t_conta.empty:
            t_conta["data_dt"] = pd.to_datetime(t_conta["data"])
            t_conta = t_conta.sort_values(by="id")
            t_conta["Saldo_Acum"] = c["saldo_inicial"] + t_conta["resultado"].cumsum()

            fig = px.line(t_conta, x="data", y="Saldo_Acum", title="Curva de Patrimônio ($)", markers=True)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Histórico Completo de Trades")
            st.dataframe(t_conta[["data", "ativo", "lotes", "resultado", "duracao_min", "estrategia", "notas"]].sort_values(by="data", ascending=False), use_container_width=True)
            
            # Botão de Backup
            csv = t_conta.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Histórico de Trades em CSV", csv, f"trades_{c['nome']}.csv", "text/csv")
        else:
            st.info("Nenhum trade lançado nesta conta.")

# ==========================================
# 5. GERENCIAR CONTAS
# ==========================================
elif menu == "⚙️ Gerenciar Contas":
    st.title("⚙️ Gerenciamento de Contas")

    with st.expander("➕ Cadastrar Nova Conta de Mesa", expanded=False):
        with st.form("nova_conta"):
            nome = st.text_input("Identificação da Conta (ex: MyFundedFutures 50K Pro)")
            tipo = st.selectbox("Tipo de Conta", [
                "Standard / Master / No Activation",
                "Instant Funding / Freedom",
                "Challenge (Avaliação)"
            ])
            saldo_inicial = st.number_input("Saldo Inicial ($)", value=50000.0, step=5000.0)
            max_dd = st.number_input("Drawdown Máximo Permitido ($)", value=2500.0, step=100.0)
            limite_diario = st.number_input("Limite de Perda Diária ($)", value=1000.0, step=100.0)
            meta = st.number_input("Meta de Lucro ($)", value=3000.0, step=100.0)
            total_saques = st.number_input("Total já sacado em todas as contas ($)", value=0.0, step=1000.0)
            data_inicio = st.date_input("Início da janela atual (Data da ativação ou último saque)", value=date.today())

            salvar = st.form_submit_button("Cadastrar Conta")
            if salvar and nome:
                cursor.execute("""
                INSERT INTO contas (nome, tipo, saldo_inicial, max_dd, limite_diario, meta, total_saques, data_inicio_janela)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (nome, tipo, saldo_inicial, max_dd, limite_diario, meta, total_saques, str(data_inicio)))
                conn.commit()
                st.success("Conta cadastrada!")
                st.rerun()

    if not contas_df.empty:
        st.subheader("Contas Existentes")
        st.dataframe(contas_df[["id", "nome", "tipo", "saldo_inicial", "meta", "total_saques", "data_inicio_janela"]], use_container_width=True)
