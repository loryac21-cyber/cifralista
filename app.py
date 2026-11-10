"""CifraLista · app Streamlit.

    uv run streamlit run app.py

Flujo: pregunta → Claude la traduce a una consulta del catálogo (salida estructurada) → Python calcula con factores
de expansión y error estándar → gráfico + párrafo redactado por Claude con verificación de cifras → Word / CSV.
"""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from cifralista.catalogo import AREAS, DEPARTAMENTOS, DESAGREGACIONES, INDICADORES, POR_ID, REGIONES
from cifralista.exportar import documento, tabla_para_mostrar
from cifralista.graficos import a_png, figura
from cifralista.interprete import MODELO, Consulta, interpretar
from cifralista.motor import Filtros, calcular_varios, codigo_reproducible
from cifralista.redactor import fmt, fmt_valor, redactar, redactar_con_plantilla
from cifralista.validacion import contrastar

load_dotenv()
st.set_page_config(page_title="CifraLista", page_icon=":material/query_stats:", layout="centered")

# Precio de Claude Haiku 5.5 (US$ por millón de tokens, prompts de hasta 100 mil tokens).
PRECIO_ENTRADA, PRECIO_SALIDA = 0.10, 0.50
MAX_IA = int(os.getenv("CIFRALISTA_MAX_CONSULTAS_IA", "25"))
EJEMPLOS = [
    "¿Qué porcentaje de productores tiene 60 años o más, por departamento?",
    "Capacitación y asistencia técnica por región natural",
    "Estructura por edad de los productores, hombres y mujeres",
    "Pobreza monetaria urbana y rural",
    "¿Cuántas productoras de la sierra obtuvieron crédito?",
]


def clave_api():
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except FileNotFoundError:
        pass
    return os.getenv("ANTHROPIC_API_KEY")


@st.cache_data(max_entries=500, show_spinner=False)
def interpretar_cacheado(pregunta, usar_ia):
    """Una misma pregunta no se paga dos veces."""
    r = interpretar(pregunta, api_key=clave_api() if usar_ia else None)
    return r.consulta.model_dump(), r.origen, r.aviso, r.tokens_entrada, r.tokens_salida


@st.cache_data(show_spinner=False)
def contraste_inei():
    return pd.DataFrame(contrastar())


def costo(tokens_in, tokens_out):
    return (tokens_in * PRECIO_ENTRADA + tokens_out * PRECIO_SALIDA) / 1e6


st.session_state.setdefault("consultas_ia", 0)
st.session_state.setdefault("resultado", None)

# Encabezado -----------------------------------------------------------------------------------------------------------
st.title("CifraLista")
st.markdown("Cifras oficiales de la **ENA 2025** y la **ENAHO 2024**, calculadas desde los microdatos del INEI con "
            "factores de expansión, y listas para tu nota técnica: gráfico, párrafo, cuadro y ficha técnica.")

with st.sidebar:
    st.header("Cómo funciona")
    st.markdown(
        "1. **Claude** traduce tu pregunta a una consulta de un catálogo de indicadores validados.\n"
        "2. **Python** calcula con el factor de expansión y el error estándar del diseño muestral.\n"
        "3. **Claude** redacta el párrafo y un verificador revisa que **cada cifra** salga del cálculo.\n\n"
        "La IA nunca calcula ni inventa números.")
    ia_disponible = bool(clave_api())
    st.badge("Claude conectado" if ia_disponible else "Sin clave de API: modo reglas",
             icon=":material/smart_toy:" if ia_disponible else ":material/rule:",
             color="green" if ia_disponible else "gray")
    st.subheader("Validación contra el INEI")
    contraste = contraste_inei()
    st.caption(f"{int(contraste.Coincide.sum())} de {len(contraste)} cifras publicadas por el INEI se reproducen "
               "exactamente desde los microdatos.")
    st.dataframe(contraste[["Indicador", "INEI", "CifraLista"]], hide_index=True,
                 column_config={"INEI": st.column_config.NumberColumn(format="%.1f"),
                                "CifraLista": st.column_config.NumberColumn(format="%.1f")})
    st.caption("Fuentes: INEI, microdatos de la ENA 2025 y la ENAHO 2024. Proyecto de la Diplomatura Q-Lab PUCP.")

# Entrada --------------------------------------------------------------------------------------------------------------
modo = st.segmented_control("Cómo consultar", ["Escribir una pregunta", "Elegir el indicador"],
                            default="Escribir una pregunta", required=True, key="modo")

consulta, origen, aviso_ia, tokens = None, "manual", "", (0, 0)
pregunta = ""
if modo == "Escribir una pregunta":
    ejemplo = st.pills("Ejemplos", EJEMPLOS, key="ejemplo")
    with st.form("form_pregunta", border=False):
        pregunta = st.text_area("Tu pregunta", value=ejemplo or "", height=80,
                                placeholder="Por ejemplo: ¿qué porcentaje de productores recibió asistencia técnica "
                                            "en cada departamento?")
        enviar = st.form_submit_button("Calcular", type="primary", icon=":material/calculate:")
    if enviar and pregunta.strip():
        usar_ia = ia_disponible and st.session_state.consultas_ia < MAX_IA
        if ia_disponible and not usar_ia:
            st.info("Llegaste al tope de consultas con IA de esta sesión; sigo con el intérprete por reglas.")
        with st.spinner("Interpretando la pregunta…"):
            datos, origen, aviso_ia, t_in, t_out = interpretar_cacheado(pregunta.strip(), usar_ia)
        consulta, tokens = Consulta(**datos), (t_in, t_out)
        if origen == "claude":
            st.session_state.consultas_ia += 1
else:
    with st.form("form_manual", border=False):
        ids = st.multiselect("Indicadores (hasta 3, con la misma desagregación)", [i.id for i in INDICADORES],
                             default=["productores_60_mas"], max_selections=3,
                             format_func=lambda i: f"{POR_ID[i].nombre} · {POR_ID[i].encuesta}")
        c1, c2 = st.columns(2)
        desag = c1.selectbox("Desagregación", list(DESAGREGACIONES), index=2, format_func=DESAGREGACIONES.get)
        region = c2.selectbox("Región natural", ("ninguno",) + REGIONES, format_func=lambda x: "Todas" if x == "ninguno" else x)
        c3, c4, c5 = st.columns(3)
        depto = c3.selectbox("Departamento", ("ninguno",) + DEPARTAMENTOS, format_func=lambda x: "Todos" if x == "ninguno" else x)
        area = c4.selectbox("Área (ENAHO)", ("ninguno",) + AREAS, format_func=lambda x: "Todas" if x == "ninguno" else x)
        sexo = c5.selectbox("Sexo", ("ninguno", "Hombre", "Mujer"), format_func=lambda x: "Todos" if x == "ninguno" else x)
        enviar = st.form_submit_button("Calcular", type="primary", icon=":material/calculate:")
    if enviar and ids:
        consulta = Consulta(en_alcance=True, indicadores=ids, desagregacion=desag, filtro_region_natural=region,
                            filtro_area=area, filtro_departamento=depto, filtro_sexo=sexo,
                            explicacion="Consulta armada a mano.")
        pregunta = ", ".join(POR_ID[i].nombre for i in ids) + f" por {DESAGREGACIONES[desag].lower()}"

# Cálculo --------------------------------------------------------------------------------------------------------------
if consulta is not None:
    if not consulta.en_alcance or not consulta.indicadores:
        st.session_state.resultado = None
        st.warning(consulta.explicacion, title="Esa pregunta está fuera del catálogo", icon=":material/info:")
    else:
        try:
            with st.spinner("Calculando con los microdatos…"):
                resultados = calcular_varios(consulta.indicadores, consulta.desagregacion, consulta.filtros())
            usar_ia_texto = origen == "claude" and st.session_state.consultas_ia <= MAX_IA
            with st.spinner("Redactando el párrafo…"):
                red = redactar(resultados, pregunta, api_key=clave_api()) if usar_ia_texto \
                    else redactar_con_plantilla(resultados)
            fig = figura(resultados, red.titulo)
            png = a_png(fig) if fig else None
            st.session_state.resultado = {
                "pregunta": pregunta, "consulta": consulta, "origen": origen, "aviso_ia": aviso_ia,
                "resultados": resultados, "red": red, "png": png,
                "tokens": (tokens[0] + red.tokens_entrada, tokens[1] + red.tokens_salida),
            }
        except ValueError as e:
            st.session_state.resultado = None
            st.warning(str(e), title="No se puede calcular así", icon=":material/info:")

# Resultado ------------------------------------------------------------------------------------------------------------
R = st.session_state.resultado
if R:
    consulta, resultados, red = R["consulta"], R["resultados"], R["red"]
    with st.container(border=True):
        st.markdown("**Así entendí tu pregunta**")
        with st.container(horizontal=True, gap="small"):
            for i in consulta.indicadores:
                st.badge(POR_ID[i].nombre, icon=":material/analytics:", color="blue")
            st.badge(DESAGREGACIONES[consulta.desagregacion], icon=":material/splitscreen:", color="violet")
            for k, v in consulta.filtros().activos().items():
                st.badge(f"{DESAGREGACIONES[k]}: {v}", icon=":material/filter_alt:", color="orange")
            st.badge("Interpretado por Claude" if R["origen"] == "claude" else
                     ("Consulta manual" if R["origen"] == "manual" else "Interpretado por reglas"),
                     icon=":material/smart_toy:", color="gray")
        if R["aviso_ia"]:
            st.caption(R["aviso_ia"])

    # Una sola cifra no necesita gráfico: va como número grande con su intervalo.
    if R["png"] is None:
        with st.container(horizontal=True):
            for r in resultados:
                for _, f in r.tabla.iterrows():
                    etiqueta = r.indicador.nombre if f.grupo in ("Perú", "Total") else f"{r.indicador.nombre} · {f.grupo}"
                    st.metric(etiqueta, fmt_valor(f.valor, r.unidad), border=True,
                              help=f"IC 95 %: {fmt(f.ic_inf)}–{fmt(f.ic_sup)} · CV {fmt(f.cv)} % · "
                                   f"{fmt(f.n, 0)} casos · {r.indicador.encuesta}")
    else:
        st.image(R["png"], alt=red.titulo or resultados[0].indicador.nombre)

    with st.container(border=True):
        st.subheader(red.titulo or resultados[0].indicador.nombre)
        st.write(red.parrafo)
        st.caption(f"Fuente: {'; '.join(sorted({r.indicador.fuente for r in resultados}))}. Elaboración propia con "
                   "CifraLista.")
        if red.no_verificadas:
            st.warning(f"Estas cifras del texto no salen del cálculo: {', '.join(red.no_verificadas)}. Usa el texto "
                       "por plantilla de abajo.", title="Cifras no verificadas", icon=":material/error:")
            st.write(redactar_con_plantilla(resultados).parrafo)
        else:
            st.badge("Todas las cifras del texto salen del cálculo", icon=":material/verified:", color="green")
        if red.aviso:
            st.caption(red.aviso)

    for r in resultados:
        for a in r.avisos:
            st.info(a, icon=":material/info:")

    st.markdown("**Cuadro**")
    tabla = pd.concat([tabla_para_mostrar(r) for r in resultados], ignore_index=True)
    st.dataframe(tabla, hide_index=True)

    with st.container(horizontal=True):
        word = documento(resultados, red, R["png"], R["pregunta"])
        st.download_button("Descargar Word", word, "cifralista.docx", icon=":material/description:", type="primary",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        st.download_button("Descargar CSV", tabla.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "cifralista.csv", mime="text/csv", icon=":material/table:")
        if R["png"]:
            st.download_button("Descargar gráfico", R["png"], "cifralista.png", mime="image/png",
                               icon=":material/image:")

    with st.expander("Ficha técnica y método", icon=":material/fact_check:"):
        for r in resultados:
            st.table(pd.Series(r.ficha(), name=r.indicador.nombre))
    with st.expander("Código para reproducir la cifra", icon=":material/code:"):
        st.caption("Pégalo en el anexo metodológico: reproduce la estimación puntual con pandas.")
        st.code(codigo_reproducible(resultados[0]), language="python")
    t_in, t_out = R["tokens"]
    if t_in:
        st.caption(f"Esta consulta usó {fmt(t_in, 0)} tokens de entrada y {fmt(t_out, 0)} de salida con {MODELO}: "
                   f"≈ US$ {costo(t_in, t_out):.4f}.")
