"""El intérprete por reglas (respaldo sin IA) y el verificador de cifras."""
import pytest

from cifralista.interprete import interpretar_con_reglas
from cifralista.motor import calcular
from cifralista.redactor import redactar_con_plantilla, verificar_cifras

CASOS = [
    ("¿Cuál es la edad promedio del productor agropecuario?", "edad_promedio", "nacional", {}),
    ("Porcentaje de productores de 60 años a más por región natural", "productores_60_mas", "region_natural", {}),
    ("¿Cuántos productores recibieron asistencia técnica por departamento?", "asistencia_tecnica", "departamento", {}),
    ("Pobreza monetaria urbano y rural", "pobreza_monetaria", "area", {}),
    ("pobreza extrema por departamento", "pobreza_extrema", "departamento", {}),
    ("¿Qué porcentaje de productores obtuvo crédito en la sierra?", "obtuvo_credito", "nacional",
     {"filtro_region_natural": "Sierra"}),
    ("Capacitación de las mujeres productoras por región natural", "capacitacion", "region_natural",
     {"filtro_sexo": "Mujer"}),
    ("Nivel de educación del productor por sexo", "hasta_primaria", "sexo", {}),
    ("¿Cómo evolucionó la pobreza monetaria desde 2014?", "pobreza_monetaria", "anio", {"anio": "ultimo"}),
    ("Productores de 60 años a más entre 2015 y 2025 en la sierra", "productores_60_mas", "anio",
     {"filtro_region_natural": "Sierra"}),
    ("Pobreza monetaria por departamento en 2019", "pobreza_monetaria", "departamento", {"anio": "2019"}),
    ("¿Cuántas productoras de la sierra obtuvieron crédito en 2019?", "obtuvo_credito", "nacional",
     {"anio": "2019", "filtro_region_natural": "Sierra"}),
    ("Edad promedio de los productores de cacao frente al resto", "edad_promedio", "productor_cacao",
     {"solo_cacao": False}),
    ("Pobreza monetaria de los hogares cacaoteros desde 2014", "pobreza_monetaria", "anio", {"solo_cacao": True}),
    ("¿Cuál es el precio en chacra del cacao por departamento?", "cacao_precio_chacra", "departamento",
     {"solo_cacao": False}),
]


@pytest.mark.parametrize("pregunta, indicador, desag, filtros", CASOS)
def test_reglas(pregunta, indicador, desag, filtros):
    c = interpretar_con_reglas(pregunta)
    assert c.en_alcance
    assert c.indicadores[0] == indicador
    assert c.desagregacion == desag
    for k, v in filtros.items():
        assert getattr(c, k) == v


def test_fuera_de_alcance():
    c = interpretar_con_reglas("¿Cuánto cuesta un kilo de papa en Huancayo hoy?")
    assert not c.en_alcance and c.indicadores == []


def test_verificador_acepta_cifras_del_calculo_y_rechaza_inventadas():
    res = [calcular("productores_60_mas", "region_natural")]
    sierra = res[0].tabla.set_index("grupo").loc["Sierra", "valor"]
    bueno = f"Según la ENA 2025, en la sierra el {sierra:.1f} % de los productores tiene 60 años o más.".replace(".", ",", 1)
    bueno = bueno.replace(f"{sierra:.1f}", f"{sierra:.1f}".replace(".", ","))
    assert verificar_cifras(bueno, res) == []
    assert verificar_cifras("En la sierra el 71,3 % tiene 60 años o más.", res) == ["71,3"]


def test_plantilla_siempre_verificable():
    for ind, d in [("edad_promedio", "nacional"), ("asistencia_tecnica", "departamento"),
                   ("estructura_edad", "nacional"), ("pobreza_monetaria", "area"), ("productores_60_mas", "anio"),
                   ("pobreza_monetaria", "anio"), ("obtuvo_credito", "anio"), ("estructura_edad", "anio"),
                   ("cacao_rendimiento", "anio"), ("cacao_precio_chacra", "departamento"),
                   ("pobreza_monetaria", "productor_cacao")]:
        res = [calcular(ind, d)]
        red = redactar_con_plantilla(res)
        assert red.parrafo and verificar_cifras(red.titulo + " " + red.parrafo, res) == [], (ind, red.parrafo)


def test_plantilla_de_serie_no_compara_tramos_de_diseno_distinto():
    red = redactar_con_plantilla([calcular("productores_60_mas", "anio")])
    assert "entre 2014 y 2022" in red.parrafo and "entre 2023 y 2025" in red.parrafo
    assert "nuevo diseño muestral" in red.parrafo
