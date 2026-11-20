from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_qrcode_scanner import qrcode_scanner
from api_produtos import buscar_dados_mestres

def renderizar_aba_coleta():
    # 1. Escolha do método de entrada
    modo_entrada = st.radio(
        "Como deseja informar o código do produto?",
        options=["Computador (Digitar SKU / EAN)", "Celular (Câmera)"],
        horizontal=True,
    )

    codigo_lido = None

    # 2. Captura do código conforme a escolha
    if modo_entrada == "Celular (Câmera)":
        st.caption("Aponte a câmera para o código de barras ou QR Code.")
        codigo_lido = qrcode_scanner(key="scanner_mvp")
    else:
        with st.form("form_busca_manual", clear_on_submit=True):
            c_input, c_btn = st.columns([3, 1])
            sku_digitado = c_input.text_input(
                "Digite o SKU ou Código de Barras (EAN)",
                placeholder="Ex: 7894900011517",
                label_visibility="collapsed",
            )
            buscar = c_btn.form_submit_button("Buscar Código", use_container_width=True)
            
            if buscar and sku_digitado.strip():
                codigo_lido = sku_digitado.strip()

    # 3. Processamento unificado do código
    if codigo_lido:
        ean_bipado = "".join(filter(str.isdigit, str(codigo_lido))) or str(codigo_lido)
        
        if ean_bipado in st.session_state.itens_coletados:
            item_ex = st.session_state.itens_coletados[ean_bipado]
            st.session_state.aviso_duplicado = (
                f"Código **{ean_bipado}** ({item_ex['Descrição']}) já foi cadastrado"
                f" com saldo **{item_ex['Qtd Física']}**!"
            )
            st.session_state.codigo_atual = None
            
        elif ean_bipado != st.session_state.codigo_atual:
            st.session_state.aviso_duplicado = None
            st.session_state.codigo_atual = ean_bipado
            with st.spinner("Buscando dados mestres..."):
                st.session_state.dados_api = buscar_dados_mestres(ean_bipado)

    # 4. Alerta caso o código já exista na lista
    if st.session_state.aviso_duplicado:
        st.error(st.session_state.aviso_duplicado)

    # 5. Formulário de confirmação do novo item
    if st.session_state.codigo_atual:
        st.info(f"**Novo Código Selecionado:** {st.session_state.codigo_atual}")
        info = st.session_state.dados_api

        with st.form("form_estoque", clear_on_submit=True):
            descricao = st.text_input("Descrição", value=info.get("descricao", ""))
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoria / Setor", value="Geral")
            marca = c2.text_input("Marca", value=info.get("marca", ""))
            quantidade = c3.number_input(
                "Qtd Atual na Prateleira", min_value=0.0, value=1.0, step=1.0
            )

            b1, b2 = st.columns(2)
            if b1.form_submit_button("Salvar Item", use_container_width=True):
                st.session_state.itens_coletados[st.session_state.codigo_atual] = {
                    "EAN": st.session_state.codigo_atual,
                    "Descrição": descricao if descricao else "Item sem descrição",
                    "Categoria": categoria,
                    "Marca": marca,
                    "Qtd Física": quantidade,
                }
                st.session_state.codigo_atual = None
                st.rerun()
                
            if b2.form_submit_button("Cancelar", use_container_width=True):
                st.session_state.codigo_atual = None
                st.rerun()

    # 6. Tabela dos itens já salvos + Exportação CSV
    if st.session_state.itens_coletados:
        st.subheader(f"Itens Monitorados ({len(st.session_state.itens_coletados)})")
        df_coletados = pd.DataFrame(list(st.session_state.itens_coletados.values()))
        st.dataframe(df_coletados, use_container_width=True)

        # Prepara o CSV com separador ';' e codificação UTF-8-SIG (abre perfeito no Excel)
        csv_bytes = df_coletados.to_csv(index=False, sep=";").encode("utf-8-sig")
        data_hoje = datetime.now().strftime("%Y-%m-%d_%H-%M")
        nome_arquivo = f"inventario_coleta_{data_hoje}.csv"

        st.download_button(
            label="📥 Baixar Planilha da Coleta (.CSV)",
            data=csv_bytes,
            file_name=nome_arquivo,
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )
