"""El motor debe reproducir las cifras que publica el INEI. Si una falla, la app no se despliega."""
import pytest

from cifralista.catalogo import INDICADORES, POR_ID
from cifralista.motor import Filtros, calcular

# (indicador, desagregación, filtros, grupo, cifra publicada por el INEI, fuente)
PUBLICADAS = [
    ("edad_promedio", "nacional", {}, "Perú", 54.5, "ENA 2025, nota de prensa del INEI"),
    ("productores_60_mas", "nacional", {}, "Perú", 37.9, "ENA 2025"),
    ("productores_15_24", "nacional", {}, "Perú", 0.9, "ENA 2025"),
    ("edad_promedio", "sexo", {}, "Mujer", 55.2, "ENA 2025"),
    ("hasta_primaria", "nacional", {}, "Perú", 57.7, "ENA 2025"),
    ("capacitacion", "nacional", {}, "Perú", 7.4, "ENA 2025"),
    ("pobreza_monetaria", "nacional", {}, "Perú", 27.6, "ENAHO 2024, informe técnico de pobreza"),
    ("pobreza_monetaria", "area", {}, "Rural", 39.3, "ENAHO 2024"),
    ("pobreza_monetaria", "area", {}, "Urbana", 24.8, "ENAHO 2024"),
    ("pobreza_extrema", "nacional", {}, "Perú", 5.5, "ENAHO 2024"),
]


@pytest.mark.parametrize("ind, desag, filtros, grupo, publicada, fuente", PUBLICADAS)
def test_reproduce_cifra_publicada(ind, desag, filtros, grupo, publicada, fuente):
    res = calcular(ind, desag, Filtros(**filtros))
    valor = res.tabla.set_index("grupo").loc[grupo, "valor"]
    assert round(valor, 1) == pytest.approx(publicada, abs=0.05), f"{ind} {grupo}: {valor:.2f} vs {publicada} ({fuente})"


def test_estructura_de_edad_suma_100_y_coincide_con_el_inei():
    t = calcular("estructura_edad").tabla.set_index("categoria")
    assert t.valor.sum() == pytest.approx(100, abs=0.01)
    assert round(t.loc["60 y más", "valor"], 1) == 37.9
    assert round(t.loc["45-59", "valor"], 1) == 35.8
    assert round(t.loc["25-44", "valor"], 1) == 25.3


def test_error_estandar_y_cv_razonables():
    res = calcular("productores_60_mas")
    fila = res.tabla.iloc[0]
    assert 0 < fila.ee < 1.5            # una muestra de 38 mil productores da décimas de punto, no puntos
    assert fila.cv < 5 and not fila.referencial
    assert fila.ic_inf < fila.valor < fila.ic_sup


def test_por_departamento_marca_referenciales_y_trae_promedio_nacional():
    res = calcular("asistencia_tecnica", "departamento")
    assert len(res.tabla) >= 24
    assert res.nacional is not None and res.nacional["valor"] == pytest.approx(
        calcular("asistencia_tecnica").tabla.valor.iloc[0])


def test_desagregacion_no_valida_da_error_claro():
    with pytest.raises(ValueError, match="no se puede desagregar"):
        calcular("productoras_mujeres", "sexo")


def test_filtros_reducen_el_universo():
    sierra = calcular("edad_promedio", filtros=Filtros(region_natural="Sierra")).tabla.iloc[0]
    total = calcular("edad_promedio").tabla.iloc[0]
    assert sierra.n < total.n


@pytest.mark.parametrize("ind", [i.id for i in INDICADORES])
def test_todos_los_indicadores_calculan_en_todas_sus_desagregaciones(ind):
    for d in POR_ID[ind].desagregaciones:
        res = calcular(ind, d)
        assert not res.tabla.empty and res.tabla.valor.notna().all(), (ind, d)
