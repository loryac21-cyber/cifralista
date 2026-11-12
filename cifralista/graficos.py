"""Gráficos estilo nota técnica (matplotlib): el mismo PNG va a la app y al Word.

Formas: un valor nacional no es un gráfico (la app lo muestra como cifra grande); un indicador por grupos va en
barras horizontales ordenadas con la línea del total; 2-3 indicadores, en barras agrupadas; una distribución, en
barras 100 % apiladas; una serie por años, en líneas cortadas donde cambia el diseño de la encuesta. Paleta categórica por orden fijo (azul, naranja, aqua, amarillo) validada para daltonismo.
"""
import io
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .motor import CAMBIO_DISENO_ENA  # noqa: E402
from .redactor import fmt  # noqa: E402

SUPERFICIE = "#ffffff"          # mismo fondo que la app y el Word
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TENUE = "#898781"
GRILLA = "#e1e0d9"
EJE = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
AZUL_CLARO = "#86b6ef"          # paso 250 de la rampa azul: cifras referenciales
ANCHO = 8.0

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 10,
    "axes.edgecolor": EJE,
    "axes.labelcolor": TINTA_2,
    "xtick.color": TENUE,
    "ytick.color": TINTA_2,
    "figure.facecolor": SUPERFICIE,
    "axes.facecolor": SUPERFICIE,
    "savefig.facecolor": SUPERFICIE,
})


def _lienzo(alto):
    fig = plt.figure(figsize=(ANCHO, alto), layout="constrained")
    fig.get_layout_engine().set(h_pad=0.08, w_pad=0.08)
    return fig, fig.add_subplot()


def _marco(ax, horizontal=True):
    for lado in ("top", "right", "left" if horizontal else "bottom"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom" if horizontal else "left"].set_color(EJE)
    ax.tick_params(length=0)
    ax.grid(True, axis="x" if horizontal else "y", color=GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    (ax.xaxis if horizontal else ax.yaxis).set_major_formatter(
        FuncFormatter(lambda v, _: fmt(v, 0 if float(v).is_integer() else 1)))


def _encabezado_y_pie(fig, ax, resultados, titulo, nota="", con_leyenda=False):
    r = resultados[0]
    i = r.indicador
    filtros = r.filtros.texto()
    nombres = ", ".join(x.indicador.nombre for x in resultados) if len(resultados) > 1 else i.nombre
    sub = f"{nombres} ({i.unidad}) · {i.universo}" + (f", {filtros}" if filtros else "") + f" · {r.encuesta_txt}"
    fig.suptitle("\n".join(textwrap.wrap(titulo or i.nombre, 70)), x=0.01, ha="left", fontsize=13,
                 fontweight="bold", color=TINTA)
    ax.set_title("\n".join(textwrap.wrap(sub, 100)), loc="left", fontsize=9, color=TINTA_2,
                 pad=26 if con_leyenda else 8)
    pie = f"Fuente: {'; '.join(sorted({x.fuente for x in resultados}))}. Elaboración: CifraLista."
    fig.supxlabel((nota + "\n" if nota else "") + pie, x=0.01, ha="left", fontsize=8, color=TENUE)


def _leyenda(ax, handles=None, ncol=4):
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol, frameon=False, fontsize=8.5,
              handlelength=1, handleheight=1, borderaxespad=0.3, labelcolor=TINTA_2)


def barras(resultado, titulo):
    """Un indicador por grupos: barras horizontales de mayor a menor, con la línea del total."""
    t = resultado.tabla.sort_values("valor")
    n = len(t)
    fig, ax = _lienzo(max(3.4, 0.3 * n + 2.2))
    colores = [AZUL_CLARO if r else SERIES[0] for r in t.referencial]
    barras_ = ax.barh(t.grupo.astype(str), t.valor, color=colores, height=0.62, edgecolor=SUPERFICIE,
                      linewidth=1.5)
    for b, r in zip(barras_, t.referencial):
        if r:
            b.set_hatch("///")
    maximo = t.valor.max()
    for k, (v, r) in enumerate(zip(t.valor, t.referencial)):
        ax.text(v + maximo * 0.012, k, fmt(v) + (" *" if r else ""), va="center", ha="left", fontsize=8.5,
                color=TINTA_2)
    if resultado.nacional:
        nv = resultado.nacional["valor"]
        ax.axvline(nv, color=TINTA_2, linewidth=1)
        ax.text(nv, n - 0.4, f" Total: {fmt(nv)}", va="bottom", ha="left", fontsize=8.5, color=TINTA)
    ax.set_xlim(0, maximo * 1.15)
    ax.set_ylim(-0.6, n - 0.1 + (0.5 if resultado.nacional else 0))
    _marco(ax)
    ax.set_xlabel("años" if resultado.unidad == "años" else "%", fontsize=9, color=TENUE, loc="right")
    nota = "* Cifra referencial: coeficiente de variación mayor a 15 % o menos de 30 casos." \
        if t.referencial.any() else ""
    _encabezado_y_pie(fig, ax, [resultado], titulo, nota)
    return fig


def agrupadas(resultados, titulo):
    """2-3 indicadores con la misma desagregación: barras agrupadas, una serie por indicador (orden fijo)."""
    grupos = resultados[0].tabla.grupo.astype(str).tolist()
    k = len(resultados)
    ancho = min(0.8 / k, 0.3)
    horizontal = len(grupos) > 6
    fig, ax = _lienzo(max(3.8, 0.25 * len(grupos) * k + 2.4) if horizontal else 4.4)
    maximo = max(r.tabla.valor.max() for r in resultados)
    for j, r in enumerate(resultados):
        vals = r.tabla.set_index(r.tabla.grupo.astype(str)).valor.reindex(grupos)
        pos = [g + (j - (k - 1) / 2) * ancho for g in range(len(grupos))]
        dibujar = ax.barh if horizontal else ax.bar
        dibujar(pos, vals, ancho * 0.92, color=SERIES[j], edgecolor=SUPERFICIE, linewidth=1.5,
                label=r.indicador.nombre)
        if len(grupos) <= 8:
            for p, v in zip(pos, vals):
                if horizontal:
                    ax.text(v + maximo * 0.01, p, fmt(v), va="center", fontsize=8, color=TINTA_2)
                else:
                    ax.text(p, v + maximo * 0.015, fmt(v), ha="center", va="bottom", fontsize=8, color=TINTA_2)
    if horizontal:
        ax.set_yticks(range(len(grupos)), grupos)
        ax.invert_yaxis()
        ax.set_xlim(0, maximo * 1.15)
    else:
        ax.set_xticks(range(len(grupos)), grupos)
        ax.set_ylim(0, maximo * 1.18)
    _marco(ax, horizontal=horizontal)
    _leyenda(ax, ncol=min(k, 2))
    _encabezado_y_pie(fig, ax, resultados, titulo, con_leyenda=True)
    return fig


def apiladas(resultado, titulo):
    """Distribución (suma 100 %): una barra apilada por grupo, segmentos separados por una línea de superficie."""
    t = resultado.tabla
    grupos = list(dict.fromkeys(t.grupo.astype(str)))
    cats = list(resultado.indicador.categorias)
    fig, ax = _lienzo(max(2.9, 0.5 * len(grupos) + 2.3))
    for gi, g in enumerate(grupos):
        izquierda = 0.0
        sub = t[t.grupo.astype(str) == g].set_index("categoria").valor
        for ci, c in enumerate(cats):
            v = float(sub.get(c, 0))
            ax.barh(gi, v, left=izquierda, color=SERIES[ci], height=0.6, edgecolor=SUPERFICIE, linewidth=2)
            if v >= 6:
                ax.text(izquierda + v / 2, gi, fmt(v), ha="center", va="center", fontsize=8.5,
                        color=TINTA if SERIES[ci] == "#eda100" else "#ffffff")
            izquierda += v
    ax.set_yticks(range(len(grupos)), grupos)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    _marco(ax)
    _leyenda(ax, handles=[Patch(color=SERIES[i], label=c) for i, c in enumerate(cats)], ncol=len(cats))
    _encabezado_y_pie(fig, ax, [resultado], titulo, "Los segmentos de menos de 6 % no llevan rótulo (ver el cuadro).",
                      con_leyenda=True)
    return fig


def serie(resultados, titulo):
    """Evolución por años: una línea por indicador (misma unidad), cortada donde cambia el diseño de la ENA; punteada
    sobre los años sin encuesta; puntos huecos = cifras referenciales; rótulos solo al inicio y fin de cada tramo."""
    r0 = resultados[0]
    usar = [r for r in resultados if r.unidad == r0.unidad]          # un solo eje: nunca dos escalas
    fig, ax = _lienzo(4.4)
    corte = CAMBIO_DISENO_ENA if r0.indicador.base == "ena" else None
    todos, valores = set(), []
    for j, r in enumerate(usar):
        color = SERIES[j]
        t = r.tabla.assign(anio=r.tabla.grupo.astype(int)).set_index("anio").sort_index()
        todos |= set(t.index)
        valores += t.valor.tolist()
        partes = [t] if not corte else [t[t.index < corte], t[t.index >= corte]]
        for k, p in enumerate(x for x in partes if len(x)):
            anios = list(p.index)
            for a, b in zip(anios, anios[1:]):
                ax.plot([a, b], [p.valor[a], p.valor[b]], color=color, linewidth=2,
                        linestyle="-" if b - a == 1 else ":", solid_capstyle="round")
            for a in (anios[0], anios[-1]) if len(anios) > 1 else (anios[0],):
                ax.annotate(fmt(p.valor[a]), (a, p.valor[a]), textcoords="offset points", xytext=(0, 8),
                            ha="center", fontsize=8.5, color=TINTA_2)
        ax.scatter(t.index, t.valor, s=36, zorder=3, color=[SUPERFICIE if x else color for x in t.referencial],
                   edgecolors=color, linewidths=1.6, label=r.indicador.nombre)
    lo, hi = min(valores), max(valores)
    margen = max(hi - lo, abs(hi) * 0.05, 0.5)
    ax.set_ylim(max(0, lo - margen * 0.45), hi + margen * 0.45)
    if corte and min(todos) < corte <= max(todos):
        ax.axvline(corte - 0.5, color=TENUE, linestyle="--", linewidth=1)
        ax.text(corte - 0.45, ax.get_ylim()[1], "Nuevo diseño\nmuestral", va="top", ha="left", fontsize=8,
                color=TENUE)
    xs = list(range(min(todos), max(todos) + 1))
    ax.set_xticks(xs, [str(x) for x in xs])
    ax.set_xlim(min(todos) - 0.5, max(todos) + 0.5)
    _marco(ax, horizontal=False)
    ax.set_ylabel("años" if r0.unidad == "años" else "%", fontsize=9, color=TENUE, loc="top")
    notas = []
    if len(xs) > len(todos) or any(len(r.tabla) < len(todos) for r in usar):
        notas.append("Línea punteada: años sin dato" + (" (en 2020 no hubo ENA)." if corte and 2020 in xs else "."))
    if any(r.tabla.referencial.any() for r in usar):
        notas.append("Punto hueco: cifra referencial (coeficiente de variación mayor a 15 % o menos de 30 casos).")
    if len(usar) < len(resultados):
        notas.append("Solo se grafican los indicadores con la misma unidad (ver el cuadro).")
    if len(usar) > 1:
        _leyenda(ax, ncol=min(len(usar), 2))
    _encabezado_y_pie(fig, ax, usar, titulo, " ".join(notas), con_leyenda=len(usar) > 1)
    return fig


def figura(resultados, titulo):
    """Elige la forma según los datos. Devuelve None cuando la respuesta es una sola cifra (no es un gráfico)."""
    r = resultados[0]
    if r.indicador.tipo == "distribucion":
        return apiladas(r, titulo)
    if r.es_serie:
        return serie(resultados, titulo) if len(r.tabla) > 1 else None
    if len(resultados) > 1:
        return None if r.desagregacion == "nacional" else agrupadas(resultados, titulo)
    return None if len(r.tabla) == 1 else barras(r, titulo)


def a_png(fig, dpi=200):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()
