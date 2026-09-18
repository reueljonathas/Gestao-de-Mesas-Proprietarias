import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import date

# Configuração da Página
st.set_page_config(page_title="Gestão de Mesas Proprietárias", layout="wide", page_icon="📈")

# Conectar/Criar Banco de Dados SQLite
conn = sqlite3.connect("mesas.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    saldo_inicial REAL,
    max_dd REAL,
    limite_diario REAL,
    meta REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta_id INTEGER,
    data TEXT,
    resultado REAL,
    notas TEXT,
    FOREIGN KEY(conta_id) REFERENCES contas(id)
)
""")
conn.commit()

# Menu Lateral
st.sidebar.title("Configurações")
aba = st.sidebar.radio("Navegar:", ["📊 Painel Geral", "➕ Lançar Resultado", "⚙️ Cadastrar Conta"])

# 1. CADASTRAR CONTA
if aba == "⚙️ Cadastrar Conta":
    st.title("Cadastrar Nova Conta de Mesa")
    with st.form("form_conta"):
        nome = st.text_input("Nome da Conta / Mesa (ex: Apex 50k, FTMO 100k)")
        saldo_inicial = st.number_input("Saldo Inicial ($)", min_value=1000.0, value=50000.0, step=1000.0)
        max_dd = st.number_input("Drawdown Máximo Permitido ($)", min_value=100.0, value=2500.0, step=100.0)
        limite_diario = st.number_input("Limite de Perda Diária ($)", min_value=50.0, value=1000.0, step=100.0)
        meta = st.number_input("Meta de Lucro / Profit Target ($)", min_value=100.0, value=3000.0, step=100.0)
        
        salvar = st.form_submit_button("Salvar Conta")
        if salvar and nome:
            cursor.execute("INSERT INTO contas (nome, saldo_inicial, max_dd, limite_diario, meta) VALUES (?, ?, ?, ?, ?)",
                           (nome, saldo_inicial, max_dd, limite_diario, meta))
            conn.commit()
            st.success("Conta cadastrada com sucesso!")

# Puxar contas cadastradas
contas_df = pd.read_sql("SELECT * FROM contas", conn)

if contas_df.empty and aba != "⚙️ Cadastrar Conta":
    st.warning("Cadastre uma conta primeiro na aba '⚙️ Cadastrar Conta'.")

# 2. LANÇAR RESULTADO
elif aba == "➕ Lançar Resultado" and not contas_df.empty:
    st.title("Lançar Resultado do Dia")
    
    conta_escolhida = st.selectbox("Selecione a Conta", contas_df["nome"].tolist())
    conta_id = int(contas_df[contas_df["nome"] == conta_escolhida]["id"].values[0])
    
    with st.form("form_resultado"):
        data_op = st.date_input("Data do Trade", value=date.today())
        resultado = st.number_input("Resultado Líquido do Dia ($) (use sinal de - para perda)", value=0.0, step=10.0)
        notas = st.text_area("Observações (ativos operados, erros, acertos)")
        
        enviar = st.form_submit_button("Registrar Resultado")
        if enviar:
            cursor.execute("INSERT INTO lancamentos (conta_id, data, resultado, notas) VALUES (?, ?, ?, ?)",
                           (conta_id, str(data_op), resultado, notas))
            conn.commit()
            st.success("Resultado lançado com sucesso!")

# 3. PAINEL GERAL
elif aba == "📊 Painel Geral" and not contas_df.empty:
    conta_escolhida = st.selectbox("Visualizar Conta:", contas_df["nome"].tolist())
    conta_dados = contas_df[contas_df["nome"] == conta_escolhida].iloc[0]
    conta_id = int(conta_dados["id"])

    # Carregar histórico
    df_trades = pd.read_sql(f"SELECT * FROM lancamentos WHERE conta_id = {conta_id} ORDER BY data ASC", conn)
    
    total_lucro = df_trades["resultado"].sum() if not df_trades.empty else 0.0
    saldo_atual = conta_dados["saldo_inicial"] + total_lucro
    
    saldo_minimo = conta_dados["saldo_inicial"] - conta_dados["max_dd"]
    margem_dd = saldo_atual - saldo_minimo
    falta_meta = max(0.0, (conta_dados["saldo_inicial"] + conta_dados["meta"]) - saldo_atual)
    
    # Métricas no topo
    st.title(f"Dashboard: {conta_dados['nome']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo Atual", f"${saldo_atual:,.2f}", delta=f"${total_lucro:,.2f}")
    c2.metric("Margem de Drawdown Restante", f"${margem_dd:,.2f}")
    c3.metric("Falta p/ Meta", f"${falta_meta:,.2f}")
    c4.metric("Limite Diário Configurado", f"${conta_dados['limite_diario']:,.2f}")
    
    st.markdown("---")

    if not df_trades.empty:
        # Gráfico de Evolução do Saldo
        df_trades["Saldo Acumulado"] = conta_dados["saldo_inicial"] + df_trades["resultado"].cumsum()
        fig = px.line(df_trades, x="data", y="Saldo Acumulado", title="Evolução do Saldo ($)", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        # Estatísticas
        dias_positivos = len(df_trades[df_trades["resultado"] > 0])
        dias_negativos = len(df_trades[df_trades["resultado"] < 0])
        total_dias = len(df_trades)
        win_rate = (dias_positivos / total_dias * 100) if total_dias > 0 else 0
        
        st.subheader("Métricas de Desempenho")
        m1, m2, m3 = st.columns(3)
        m1.metric("Dias Operados", total_dias)
        m2.metric("Taxa de Acerto (Dias Win)", f"{win_rate:.1f}%")
        m3.metric("Dias Gain / Loss", f"{dias_positivos}G / {dias_negativos}L")

        st.subheader("Histórico de Lançamentos")
        st.dataframe(df_trades[["data", "resultado", "notas"]].sort_values(by="data", ascending=False), use_container_width=True)
    else:
        st.info("Nenhum lançamento feito para esta conta ainda.")
