"""Servidor MCP de CifraLista: el mismo motor de la app, como herramientas para Claude Desktop o Claude Code.

    uv sync --group mcp
    uv run --group mcp mcp_server.py                                  # el servidor, por stdio
    claude mcp add --scope project cifralista -- uv run --group mcp mcp_server.py

Así un analista escribe su nota en Claude y cada cifra sale de una llamada que se puede repetir: el modelo elige el
indicador y CifraLista calcula (factor de expansión, error estándar, CV) desde los microdatos del INEI.
"""
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cifralista.catalogo import DESAGREGACIONES, INDICADORES, POR_ID
from cifralista.graficos import a_png, figura
from cifralista.motor import Filtros, calcular_varios, codigo_reproducible
from cifralista.redactor import hechos, redactar_con_plantilla

SALIDAS = Path(__file__).parent / "salidas"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": False}

mcp = FastMCP("cifralista", instructions=(
    "Indicadores oficiales del Perú calculados desde los microdatos del INEI (ENA 2025 y ENAHO 2024). Primero mira "
    "el catálogo con listar_indicadores; luego usa calcular para obtener las cifras con su intervalo de confianza y "
    "coeficiente de variación, y graficar para el PNG. No calcules a mano ni escribas cifras que no vengan de estas "
    "herramientas; marca como referencial toda cifra con referencial=true y cita la fuente que devuelven."))


def _resultados(indicadores, desagregacion, region_natural, area, departamento, sexo):
    desconocidos = [i for i in indicadores if i not in POR_ID]
    if desconocidos:
        raise ToolError(f"No existen {desconocidos}. Usa listar_indicadores para ver los ids.")
    if not 1 <= len(indicadores) <= 3:
        raise ToolError("Pide entre 1 y 3 indicadores.")
    try:
        return calcular_varios(indicadores, desagregacion, Filtros(region_natural or None, area or None,
                                                                   departamento or None, sexo or None))
    except ValueError as e:
        raise ToolError(str(e)) from e


@mcp.tool(annotations=SOLO_LECTURA)
def listar_indicadores() -> list[dict]:
    """Catálogo de indicadores validados: id, nombre, encuesta, universo, unidad y desagregaciones válidas."""
    return [{"id": i.id, "nombre": i.nombre, "encuesta": i.encuesta, "universo": i.universo, "unidad": i.unidad,
             "tipo": i.tipo, "variable": i.variable, "desagregaciones": list(i.desagregaciones), "nota": i.nota}
            for i in INDICADORES]


@mcp.tool(annotations=SOLO_LECTURA)
def calcular(indicadores: list[str], desagregacion: str = "nacional", region_natural: str = "", area: str = "",
             departamento: str = "", sexo: str = "") -> dict:
    """Calcula 1 a 3 indicadores con factor de expansión, error estándar, IC 95 % y CV.

    desagregacion: nacional, region_natural, departamento, area, sexo, grupo_edad, nivel_educativo o lengua_materna.
    Filtros opcionales: region_natural (Costa/Sierra/Selva), area (Urbana/Rural, solo ENAHO), departamento, sexo.
    """
    res = _resultados(indicadores, desagregacion, region_natural, area, departamento, sexo)
    salida = {"desagregacion": DESAGREGACIONES[desagregacion], "resultados": []}
    for r in res:
        tabla = r.tabla.round({"valor": 2, "ee": 3, "cv": 1, "ic_inf": 2, "ic_sup": 2, "N": 0})
        salida["resultados"].append({
            "ficha": r.ficha(), "avisos": r.avisos,
            "total": None if r.nacional is None else round(r.nacional["valor"], 2),
            "tabla": tabla.to_dict(orient="records"),
            "codigo_reproducible": codigo_reproducible(r),
        })
    return salida


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def graficar(indicadores: list[str], desagregacion: str = "departamento", titulo: str = "", region_natural: str = "",
             area: str = "", departamento: str = "", sexo: str = "") -> dict:
    """Guarda el gráfico estilo nota técnica en salidas/ y devuelve la ruta. El título debe decir el hallazgo."""
    res = _resultados(indicadores, desagregacion, region_natural, area, departamento, sexo)
    fig = figura(res, titulo or redactar_con_plantilla(res).titulo)
    if fig is None:
        raise ToolError("Una sola cifra no necesita gráfico: usa calcular y repórtala en el texto.")
    SALIDAS.mkdir(exist_ok=True)
    ruta = SALIDAS / f"{'_'.join(indicadores)}_{desagregacion}.png"
    ruta.write_bytes(a_png(fig))
    return {"ruta": str(ruta.resolve()), "fuente": res[0].indicador.fuente}


@mcp.tool(annotations=SOLO_LECTURA)
def parrafo_base(indicadores: list[str], desagregacion: str = "nacional", region_natural: str = "",
                 area: str = "", departamento: str = "", sexo: str = "") -> dict:
    """Párrafo descriptivo sin IA (plantilla) y los hechos ya redondeados que se pueden citar."""
    res = _resultados(indicadores, desagregacion, region_natural, area, departamento, sexo)
    red = redactar_con_plantilla(res)
    return {"titulo": red.titulo, "parrafo": red.parrafo, "hechos": hechos(res)}


@mcp.prompt
def nota_tecnica(tema: str) -> str:
    """Arma una nota técnica corta con cifras de CifraLista."""
    return (f"Escribe una nota técnica de una página sobre «{tema}» para un ministerio del Perú. Usa "
            "listar_indicadores para elegir de 2 a 4 indicadores pertinentes; calcula cada uno con calcular "
            "(nacional y la desagregación más informativa); haz un gráfico con graficar. Estructura: mensaje clave "
            "(3 viñetas), evidencia (con las cifras y su fuente), limitaciones (cifras referenciales, universo, "
            "asociación no es causa) y anexo con el código reproducible. Ninguna cifra que no venga de las "
            "herramientas.")


if __name__ == "__main__":
    mcp.run()
