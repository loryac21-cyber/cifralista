"""El motor debe reproducir las cifras que publica el INEI. Si una falla, la app no se despliega."""
import pytest

from cifralista.catalogo import ANIOS_ENA, ANIOS_ENAHO, INDICADORES, POR_ID
from cifralista.motor import Filtros, anios_de, base, calcular
from cifralista.validacion import PUBLICADAS, contrastar


@pytest.mark.parametrize("ind, desag, grupo, anio, publicada, fuente", PUBLICADAS)
def test_reproduce_cifra_publicada(ind, desag, grupo, anio, publicada, fuente):
    res = calcular(ind, desag, anio=anio)
    valor = res.tabla.set_index("grupo").loc[grupo, "valor"]
    assert round(valor, 1) == pytest.approx(publicada, abs=0.05), f"{ind} {grupo} {anio}: {valor:.2f} vs {publicada}"


def test_contraste_de_la_app_coincide_en_todo():
    assert all(f["Coincide"] for f in contrastar())


def test_los_anios_del_catalogo_son_los_de_los_datos():
    assert tuple(sorted(base("ena").anio.unique())) == ANIOS_ENA
    assert tuple(sorted(base("hogares").anio.unique())) == ANIOS_ENAHO
    assert tuple(sorted(base("personas").anio.unique())) == ANIOS_ENAHO


def test_sin_anio_usa_el_ultimo_con_dato():
    assert calcular("edad_promedio").anios == (2025,)
    assert calcular("pobreza_monetaria").anios == (2024,)


def test_la_ena_2021_no_tuvo_credito_ni_lengua():
    assert 2021 not in anios_de("obtuvo_credito") and 2021 not in anios_de("lengua_originaria")
    assert anios_de("edad_promedio") == ANIOS_ENA
    with pytest.raises(ValueError, match="no tiene dato en 2021"):
        calcular("obtuvo_credito", anio=2021)


def test_serie_un_calculo_por_anio_con_aviso_de_diseno():
    res = calcular("productores_60_mas", "anio")
    t = res.tabla.set_index("grupo")
    assert list(t.index) == [str(a) for a in ANIOS_ENA]
    assert round(t.loc["2022", "valor"], 1) == 40.2 and round(t.loc["2025", "valor"], 1) == 37.9
    assert any("nuevo diseño muestral" in a for a in res.avisos)
    assert any("2020 no se realizó" in a for a in res.avisos)
    assert res.encuesta_txt == "ENA 2014-2025" and "2014-2025" in res.fuente


def test_serie_con_filtro_y_hueco_avisado():
    res = calcular("obtuvo_credito", "anio", Filtros(region_natural="Sierra"))
    assert "2021" not in set(res.tabla.grupo)
    assert any("Sin dato en 2021" in a for a in res.avisos)


def test_serie_de_pobreza_coincide_con_el_inei_cada_anio():
    t = calcular("pobreza_monetaria", "anio").tabla.set_index("grupo").valor.round(1)
    assert t.to_dict() == {"2014": 22.7, "2015": 21.8, "2016": 20.7, "2017": 21.7, "2018": 20.5, "2019": 20.2,
                           "2020": 30.1, "2021": 25.9, "2022": 27.5, "2023": 29.0, "2024": 27.6}


def test_estructura_de_edad_suma_100_y_coincide_con_el_inei():
    t = calcular("estructura_edad").tabla.set_index("categoria")
    assert t.valor.sum() == pytest.approx(100, abs=0.01)
    assert round(t.loc["60 y más", "valor"], 1) == 37.9
    assert round(t.loc["45-59", "valor"], 1) == 35.8
    assert round(t.loc["25-44", "valor"], 1) == 25.3


def test_error_estandar_y_cv_razonables():
    for anio in (2014, 2019, 2025):
        fila = calcular("productores_60_mas", anio=anio).tabla.iloc[0]
        assert 0 < fila.ee < 1.5            # muestras de 26 a 38 mil productores dan décimas de punto, no puntos
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


@pytest.mark.parametrize("ind", [i.id for i in INDICADORES])
def test_todos_los_indicadores_calculan_en_su_primer_anio(ind):
    res = calcular(ind, POR_ID[ind].desagregaciones[2], anio=anios_de(ind)[0])
    assert not res.tabla.empty and res.tabla.valor.notna().all()
