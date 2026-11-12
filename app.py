"""CifraLista · app Streamlit.

    uv run streamlit run app.py

Flujo: pregunta → Claude la traduce a una consulta del catálogo (salida estructurada) → Python calcula con factores
de expansión y error estándar → gráfico + párrafo redactado por Claude con verificación de cifras → Word / CSV.
"""
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from cifralista import llm
from cifralista.catalogo import (ANIOS, ANIOS_ENA, ANIOS_ENAHO, AREAS, DEPARTAMENTOS, DESAGREGACIONES, INDICADORES,
                                 POR_ID, REGIONES, periodo)
from cifralista.exportar import documento, tabla_para_mostrar
from cifralista.graficos import a_png, figura
from cifralista.interprete import MODELO, Consulta, interpretar
from cifralista.motor import base, calcular_varios, codigo_reproducible
from cifralista.redactor import fmt, fmt_valor, redactar, redactar_con_plantilla
from cifralista.validacion import contrastar

load_dotenv()
st.set_page_config(page_title="CifraLista", page_icon=":material/query_stats:", layout="centered")

MAX_IA = int(os.getenv("CIFRALISTA_MAX_CONSULTAS_IA", "25"))
EJEMPLOS = [
    "¿Qué porcentaje de productores tiene 60 años o más, por departamento?",
    "¿Cómo evolucionó el porcentaje de productores de 60 años a más desde 2014?",
    "Evolución de la pobreza monetaria desde 2014",
    "Capacitación y asistencia técnica por región natural",
    "Estructura por edad de los productores, hombres y mujeres",
    "¿Cuántas productoras de la sierra obtuvieron crédito en 2019?",
]
PERIODO_ENA, PERIODO_ENAHO = periodo(ANIOS_ENA), periodo(ANIOS_ENAHO)


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
    r = interpretar(pregunta, api_key=clave_api(), usar_ia=usar_ia)
    return r.consulta.model_dump(), r.origen, r.aviso, r.via, r.costo_usd


@st.cache_data(max_entries=500, show_spinner=False)
def redactar_cacheado(pregunta, consulta_json, usar_ia):
    c = Consulta.model_validate_json(consulta_json)
    resultados = calcular_varios(c.indicadores, c.desagregacion, c.filtros(), anio=c.anio_int())
    return redactar(resultados, pregunta, api_key=clave_api(), usar_ia=usar_ia)


@st.cache_data(show_spinner=False)
def contraste_inei():
    return pd.DataFrame(contrastar())


st.session_state.setdefault("consultas_ia", 0)
st.session_state.setdefault("resultado", None)

# Encabezado -----------------------------------------------------------------------------------------------------------
st.caption(f":blue[**DATOS OFICIALES DEL INEI · ENA {PERIODO_ENA} · ENAHO {PERIODO_ENAHO}**]")
st.title("CifraLista", anchor=False)
st.markdown("Escribe tu pregunta y recibe **el gráfico, el párrafo y el cuadro de tu nota técnica**, con cifras "
            "calculadas desde los microdatos del INEI con factores de expansión y verificadas una por una.")
contraste = contraste_inei()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Indicadores", len(INDICADORES), border=True, icon=":material/checklist:",
          help="Indicadores validados en el catálogo.")
k2.metric("Iguales al INEI", f"{int(contraste.Coincide.sum())}/{len(contraste)}", border=True,
          icon=":material/verified:", help="Cifras publicadas por el INEI que CifraLista reproduce exactas.")
k3.metric("Años", f"{min(ANIOS)}-{str(max(ANIOS))[2:]}", border=True, icon=":material/timeline:",
          help=f"ENA {', '.join(map(str, ANIOS_ENA))} (en 2020 no hubo ENA) y ENAHO {PERIODO_ENAHO}. Cada año se "
               "calcula con su propia muestra.")
k4.metric("Registros", fmt((len(base("ena")) + len(base("personas"))) / 1e6, 1) + " M", border=True,
          icon=":material/groups:", help=f"{fmt(len(base('ena')), 0)} unidades agropecuarias (ENA) y "
                                         f"{fmt(len(base('personas')), 0)} residentes habituales (ENAHO), todos los años.")

with st.sidebar:
    st.header("Cómo funciona")
    st.markdown(
        "1. **Claude** traduce tu pregunta a una consulta de un catálogo de indicadores validados.\n"
        "2. **Python** calcula con el factor de expansión y el error estándar del diseño muestral.\n"
        "3. **Claude** redacta el párrafo y un verificador revisa que **cada cifra** salga del cálculo.\n\n"
        "La IA nunca calcula ni inventa números.")
    via_ia = llm.camino(clave_api())
    ia_disponible = via_ia is not None
    st.badge({"api": "Claude · API", "claude-code": "Claude · Claude Code local"}.get(
        via_ia, "Intérprete por reglas (sin IA)"),
        icon=":material/smart_toy:" if ia_disponible else ":material/rule:",
        color="green" if ia_disponible else "gray")
    if not ia_disponible:
        st.caption("Esta versión pública responde con reglas y plantillas; las cifras son las mismas. Con Claude, la "
                   "app entiende preguntas libres y redacta el párrafo.")
    st.subheader("Validación contra el INEI")
    st.caption(f"{int(contraste.Coincide.sum())} de {len(contraste)} cifras publicadas por el INEI se reproducen "
               "exactamente desde los microdatos.")
    with st.expander(f"Ver las {len(contraste)} cifras", icon=":material/table_view:"):
        st.table(contraste.assign(INEI=contraste.INEI.map(fmt), CifraLista=contraste.CifraLista.map(fmt))
                 .set_index("Indicador")[["INEI", "CifraLista"]])
    st.caption(f"Fuentes: INEI, microdatos de la ENA {PERIODO_ENA} y la ENAHO {PERIODO_ENAHO}. Proyecto de la "
               "Diplomatura Q-Lab PUCP.")

# Entrada --------------------------------------------------------------------------------------------------------------
modo = st.segmented_control("Cómo consultar", ["Escribir una pregunta", "Elegir el indicador"],
                            default="Escribir una pregunta", required=True, key="modo")

consulta, origen, aviso_ia, via, costo_ia = None, "manual", "", "", 0.0
pregunta = ""
if modo == "Escribir una pregunta":
    # Enlace para compartir una consulta: ?q=<pregunta> la resuelve al abrir la página (una vez por sesión).
    q = st.query_params.get("q", "")
    auto = bool(q) and st.session_state.get("q_resuelta") != q
    ejemplo = st.pills("Ejemplos", EJEMPLOS, key="ejemplo")
    with st.form("form_pregunta", border=False):
        pregunta = st.text_area("Tu pregunta", value=ejemplo or q or "", height=80,
                                placeholder="Por ejemplo: ¿qué porcentaje de productores recibió asistencia técnica "
                                            "en cada departamento?")
        enviar = st.form_submit_button("Calcular", type="primary", icon=":material/calculate:", key="calcular")
    if auto and not enviar:
        pregunta, enviar = q, True
        st.session_state.q_resuelta = q
    if enviar and pregunta.strip():
        usar_ia = ia_disponible and st.session_state.consultas_ia < MAX_IA
        if ia_disponible and not usar_ia:
            st.info("Llegaste al tope de consultas con IA de esta sesión; sigo con el intérprete por reglas.")
        with st.spinner("Claude está interpretando la pregunta…" if usar_ia else "Interpretando la pregunta…"):
            datos, origen, aviso_ia, via, costo_ia = interpretar_cacheado(pregunta.strip(), usar_ia)
        consulta = Consulta(**datos)
        if origen == "claude":
            st.session_state.consultas_ia += 1
else:
    with st.form("form_manual", border=False):
        ids = st.multiselect("Indicadores (hasta 3, con la misma desagregación)", [i.id for i in INDICADORES],
                             default=["productores_60_mas"], max_selections=3,
                             format_func=lambda i: f"{POR_ID[i].nombre} · {POR_ID[i].encuesta}")
        c1, c2 = st.columns(2)
        desag = c1.selectbox("Desagregación", list(DESAGREGACIONES), index=3, format_func=DESAGREGACIONES.get,
                             help="«Año (serie)» calcula el indicador en cada año con dato.")
        anio = c2.selectbox("Año", ("ultimo",) + tuple(str(a) for a in reversed(ANIOS)),
                            format_func=lambda x: "Último con dato" if x == "ultimo" else x,
                            help=f"ENA {PERIODO_ENA} (sin 2020) y ENAHO {PERIODO_ENAHO}. No se usa en la serie.")
        c3, c4, c5, c6 = st.columns(4)
        region = c3.selectbox("Región natural", ("ninguno",) + REGIONES, format_func=lambda x: "Todas" if x == "ninguno" else x)
        depto = c4.selectbox("Departamento", ("ninguno",) + DEPARTAMENTOS, format_func=lambda x: "Todos" if x == "ninguno" else x)
        area = c5.selectbox("Área (ENAHO)", ("ninguno",) + AREAS, format_func=lambda x: "Todas" if x == "ninguno" else x)
        sexo = c6.selectbox("Sexo", ("ninguno", "Hombre", "Mujer"), format_func=lambda x: "Todos" if x == "ninguno" else x)
        cacao = st.checkbox("Solo productores u hogares de cacao",
                            help="ENA: cosechó cacao en los últimos 12 meses. ENAHO: el hogar produjo cacao.")
        enviar = st.form_submit_button("Calcular", type="primary", icon=":material/calculate:")
    if enviar and ids:
        consulta = Consulta(en_alcance=True, indicadores=ids, desagregacion=desag, anio=anio,
                            filtro_region_natural=region, filtro_area=area, filtro_departamento=depto,
                            filtro_sexo=sexo, solo_cacao=cacao, explicacion="Consulta armada a mano.")
        pregunta = (", ".join(POR_ID[i].nombre for i in ids) + f" por {DESAGREGACIONES[desag].lower()}"
                    + (f" en {anio}" if anio != "ultimo" and desag != "anio" else ""))

# Cálculo --------------------------------------------------------------------------------------------------------------
if consulta is not None:
    if not consulta.en_alcance or not consulta.indicadores:
        st.session_state.resultado = None
        st.warning(consulta.explicacion, title="Esa pregunta está fuera del catálogo", icon=":material/info:")
    else:
        try:
            with st.spinner("Calculando con los microdatos…"):
                resultados = calcular_varios(consulta.indicadores, consulta.desagregacion, consulta.filtros(),
                                             anio=consulta.anio_int())
            usar_ia_texto = origen == "claude" and st.session_state.consultas_ia <= MAX_IA
            with st.spinner("Claude está redactando el párrafo…" if usar_ia_texto else "Redactando el párrafo…"):
                red = redactar_cacheado(pregunta, consulta.model_dump_json(), True) if usar_ia_texto \
                    else redactar_con_plantilla(resultados)
            fig = figura(resultados, red.titulo)
            png = a_png(fig) if fig else None
            st.session_state.resultado = {
                "pregunta": pregunta, "consulta": consulta, "origen": origen, "aviso_ia": aviso_ia, "via": via,
                "resultados": resultados, "red": red, "png": png, "costo": costo_ia + red.costo_usd,
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
            st.badge(resultados[0].encuesta_txt, icon=":material/calendar_month:", color="green")
            for k, v in consulta.filtros().activos().items():
                st.badge("Solo cacao" if k == "cacao" else f"{DESAGREGACIONES[k]}: {v}", icon=":material/filter_alt:",
                         color="orange")
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
                                   f"{fmt(f.n, 0)} casos · {r.encuesta_txt}")
    else:
        st.image(R["png"], alt=red.titulo or resultados[0].indicador.nombre)

    with st.container(border=True):
        st.subheader(red.titulo or resultados[0].indicador.nombre)
        st.write(red.parrafo)
        st.caption(f"Fuente: {'; '.join(sorted({r.fuente for r in resultados}))}. Elaboración propia con "
                   "CifraLista.")
        if red.no_verificadas:
            st.warning(f"Estas cifras del texto no salen del cálculo: {', '.join(red.no_verificadas)}. Usa el texto "
                       "por plantilla de abajo.", title="Cifras no verificadas", icon=":material/error:")
            st.write(redactar_con_plantilla(resultados).parrafo)
        else:
            st.badge("Todas las cifras del texto salen del cálculo", icon=":material/verified:", color="green")
        if red.aviso:
            st.caption(red.aviso)

    for a in dict.fromkeys(a for r in resultados for a in r.avisos):      # sin repetir avisos iguales
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
    if R["costo"]:
        via_txt = "vía Claude Code, costo equivalente en la API" if R["via"] == "claude-code" else "vía API"
        st.caption(f"Costo de IA de esta consulta: ≈ US$ {fmt(R['costo'], 4)} ({MODELO}, {via_txt}). Las preguntas "
                   "repetidas salen de la caché y no se vuelven a pagar.")
