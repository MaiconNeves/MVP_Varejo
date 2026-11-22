from datetime import datetime
from google import genai
from PIL import Image
import pandas as pd
import streamlit as st
from streamlit_qrcode_scanner import qrcode_scanner
from api_produtos import buscar_dados_mestres


def contar_itens_nas_fotos(lista_fotos, nome_produto):
    """Envia cada foto para o Gemini 2.5 Flash e soma as unidades encontradas."""
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("Chave GEMINI_API_KEY não encontrada nos Secrets do Streamlit.")
        return 0

    client = genai.Client(api_key=api_key)
    total_contado = 0

    prompt = (
        f"Você é um auditor de inventário de estoque. Analise esta imagem e conte "
        f"exatamente quantas unidades do produto '{nome_produto}' estão visíveis. "
        f"Conte apenas itens inteiros e claramente identificáveis deste produto. "
        f"Responda ESTRITAMENTE com o número inteiro (exemplo: 14). "
        f"Se não houver nenhuma unidade, responda 0."
    )

    for foto_bytes in lista_fotos:
        imagem = Image.open(foto_bytes)
        resposta = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[imagem, prompt],
        )
        # Limpa qualquer texto extra e pega apenas os números
        digitos = "".join(filter(str.isdigit, resposta.text))
        total_contado += int(digitos) if digitos else 0

    return total_contado


def inicializar_estados():
    """Garante que todas as variáveis de sessão existam antes de rodar a tela."""
    estados_padrao = {
        "itens_coletados": {},
        "codigo_atual": None,
        "aviso_duplicado": None,
        "dados_api": {},
        "modo_foto_inventario": False,
        "fotos_inventario": [],
        "qtd_calculada_ia": 1.0,
    }
    for chave, valor in estados_padrao.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def renderizar_aba_coleta():
    inicializar_estados()

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
            # Reseta estados de foto ao bipar um produto novo
            st.session_state.modo_foto_inventario = False
            st.session_state.fotos_inventario = []
            st.session_state.qtd_calculada_ia = 1.0
            with st.spinner("Buscando dados mestres..."):
                st.session_state.dados_api = buscar_dados_mestres(ean_bipado)

    # 4. Alerta caso o código já exista na lista
    if st.session_state.aviso_duplicado:
        st.error(st.session_state.aviso_duplicado)

    # 5. Formulário de confirmação do novo item
    if st.session_state.codigo_atual:
        st.info(f"**Novo Código Selecionado:** {st.session_state.codigo_atual}")
        info = st.session_state.dados_api
        desc_padrao = info.get("descricao", "")

        # Botão para ativar a contagem por fotos
        if st.button("📸 Gerar Inventário do Item (Contar por Fotos)", use_container_width=True):
            st.session_state.modo_foto_inventario = not st.session_state.modo_foto_inventario

        # Painel de captura de múltiplas fotos no celular
        if st.session_state.modo_foto_inventario:
            with st.container(border=True):
                st.markdown("#### Contagem Visual do Estoque")
                st.caption(
                    "Tire a foto de uma prateleira/caixa, clique em Adicionar e repita até cobrir todo o estoque deste item."
                )

                foto_atual = st.camera_input(
                    "Câmera do Estoque",
                    key=f"cam_item_{len(st.session_state.fotos_inventario)}",
                )

                c_add, c_limpar = st.columns(2)
                if foto_atual and c_add.button("➕ Adicionar Foto", use_container_width=True):
                    st.session_state.fotos_inventario.append(foto_atual)
                    st.rerun()

                if st.session_state.fotos_inventario and c_limpar.button("🗑️ Limpar Fotos", use_container_width=True):
                    st.session_state.fotos_inventario = []
                    st.rerun()

                qtd_fotos = len(st.session_state.fotos_inventario)
                st.write(f"**Fotos prontas para contagem:** {qtd_fotos}")

                if qtd_fotos > 0:
                    if st.button("✅ Finalizar e Gerar Quantidade", type="primary", use_container_width=True):
                        with st.spinner(f"Analisando {qtd_fotos} foto(s) com Gemini..."):
                            nome_busca = desc_padrao if desc_padrao else st.session_state.codigo_atual
                            total = contar_itens_nas_fotos(st.session_state.fotos_inventario, nome_busca)
                            st.session_state.qtd_calculada_ia = float(total)
                            st.session_state.fotos_inventario = []
                            st.session_state.modo_foto_inventario = False
                            st.success(f"Contagem concluída: **{total}** unidades!")
                            st.rerun()

        # Formulário principal (preenchido com o resultado da IA, mas editável manualmente)
        with st.form("form_estoque", clear_on_submit=True):
            descricao = st.text_input("Descrição", value=desc_padrao)
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoria / Setor", value="Geral")
            marca = c2.text_input("Marca", value=info.get("marca", ""))
            quantidade = c3.number_input(
                "Qtd Atual na Prateleira",
                min_value=0.0,
                value=st.session_state.qtd_calculada_ia,
                step=1.0,
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
                st.session_state.qtd_calculada_ia = 1.0
                st.rerun()

            if b2.form_submit_button("Cancelar", use_container_width=True):
                st.session_state.codigo_atual = None
                st.session_state.qtd_calculada_ia = 1.0
                st.session_state.fotos_inventario = []
                st.session_state.modo_foto_inventario = False
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
