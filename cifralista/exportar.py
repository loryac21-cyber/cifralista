"""Exporta el resultado a un Word listo para pegar en la nota técnica: título, párrafo, gráfico, cuadro y ficha."""
import io
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from .motor import codigo_reproducible
from .redactor import fmt

GRIS = RGBColor(0x52, 0x51, 0x4E)


def tabla_para_mostrar(r):
    """Cuadro con los nombres que usa una nota técnica (sirve para la app, el CSV y el Word)."""
    t = r.tabla
    u = r.unidad
    cols = {"grupo": "Año" if r.es_serie else "Grupo"}
    if "categoria" in t:
        cols["categoria"] = "Categoría"
    df = t.rename(columns=cols)
    salida = df[list(cols.values())].copy()
    salida[f"Valor ({u})"] = t.valor.round(1)
    salida["IC 95 % inferior"] = t.ic_inf.round(1)
    salida["IC 95 % superior"] = t.ic_sup.round(1)
    salida["CV (%)"] = t.cv.round(1)
    salida["Casos en la muestra"] = t.n
    salida["Población expandida"] = t.N.round(0).astype("int64")
    salida["Referencial"] = t.referencial.map({True: "Sí", False: ""})
    if len(r.tabla.indicador.unique()) == 1 and "categoria" not in t:
        return salida
    salida.insert(0, "Indicador", t.indicador)
    return salida


def documento(resultados, redaccion, png, pregunta):
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)

    doc.add_heading(redaccion.titulo or resultados[0].indicador.nombre, level=1)
    p = doc.add_paragraph(redaccion.parrafo)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fuentes = sorted({r.fuente for r in resultados})
    cita = doc.add_paragraph(f"Fuente: {'; '.join(fuentes)}. Elaboración propia con CifraLista.")
    cita.runs[0].font.size = Pt(9)
    cita.runs[0].font.color.rgb = GRIS

    if png:
        doc.add_picture(io.BytesIO(png), width=Cm(16))

    for r in resultados:
        doc.add_heading(f"Cuadro: {r.indicador.nombre}, {r.encuesta_txt} ({r.unidad})", level=2)
        t = tabla_para_mostrar(r)
        columnas = [c for c in t.columns if c not in ("Población expandida",)]
        tabla = doc.add_table(rows=1, cols=len(columnas))
        tabla.style = "Light Grid Accent 1"
        for j, c in enumerate(columnas):
            tabla.rows[0].cells[j].text = c
        for _, fila in t.iterrows():
            celdas = tabla.add_row().cells
            for j, c in enumerate(columnas):
                v = fila[c]
                celdas[j].text = fmt(v, 0 if c == "Casos en la muestra" else 1) if isinstance(v, (int, float)) \
                    and not isinstance(v, bool) else str(v)
        nota = doc.add_paragraph("IC 95 %: intervalo de confianza; CV: coeficiente de variación. «Referencial»: CV "
                                 "mayor a 15 % o menos de 30 casos.")
        nota.runs[0].font.size = Pt(8.5)
        nota.runs[0].font.color.rgb = GRIS

    doc.add_heading("Ficha técnica", level=2)
    for r in resultados:
        for k, v in r.ficha().items():
            par = doc.add_paragraph(style="List Bullet")
            par.add_run(f"{k}: ").bold = True
            par.add_run(str(v))
        for aviso in r.avisos:
            doc.add_paragraph(aviso, style="List Bullet")
    doc.add_paragraph(f"Pregunta original: «{pregunta}». Texto redactado por "
                      f"{'Claude (Anthropic) con verificación automática de cifras' if redaccion.origen == 'claude' else 'plantilla, sin IA'}"
                      f"; cifras calculadas en Python el {date.today():%d/%m/%Y}.")

    doc.add_heading("Anexo: código para reproducir la cifra", level=2)
    codigo = doc.add_paragraph(codigo_reproducible(resultados[0]))
    for run in codigo.runs:
        run.font.name = "Consolas"
        run.font.size = Pt(8.5)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
