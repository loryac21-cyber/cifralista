"""El servidor MCP expone el mismo motor: se prueba en memoria con el cliente de FastMCP."""
import asyncio

import pytest

fastmcp = pytest.importorskip("fastmcp")
from fastmcp import Client  # noqa: E402

from mcp_server import mcp  # noqa: E402


def llamar(nombre, args):
    async def _():
        async with Client(mcp) as c:
            return await c.call_tool(nombre, args)
    return asyncio.run(_())


def test_lista_las_herramientas_y_el_catalogo():
    async def _():
        async with Client(mcp) as c:
            return [t.name for t in await c.list_tools()]
    assert {"listar_indicadores", "calcular", "graficar", "parrafo_base"} <= set(asyncio.run(_()))
    ids = [i["id"] for i in llamar("listar_indicadores", {}).structured_content["result"]]
    assert "edad_promedio" in ids and "pobreza_monetaria" in ids


def test_calcular_devuelve_la_cifra_del_inei_con_su_precision():
    r = llamar("calcular", {"indicadores": ["edad_promedio"]}).structured_content
    fila = r["resultados"][0]["tabla"][0]
    assert round(fila["valor"], 1) == 54.5 and fila["cv"] < 5
    assert "FACTOR_PRODUCTOR" in r["resultados"][0]["ficha"]["Método"]


def test_errores_claros():
    with pytest.raises(Exception, match="listar_indicadores"):
        llamar("calcular", {"indicadores": ["ingreso_inventado"]})
