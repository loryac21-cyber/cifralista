"""Catálogo de indicadores validados. La IA solo puede elegir entre estos: nunca calcula ni inventa una cifra.

Cada indicador dice de qué encuesta sale, sobre qué universo se calcula, con qué variable del cuestionario y en qué
desagregaciones es válido. Agregar un indicador nuevo es agregar una entrada aquí (y su prueba en tests/).
"""
from dataclasses import dataclass, field

DESAGREGACIONES = {
    "nacional": "Nacional",
    "anio": "Año (serie)",
    "region_natural": "Región natural",
    "departamento": "Departamento",
    "area": "Área de residencia",
    "sexo": "Sexo",
    "grupo_edad": "Grupo de edad",
    "nivel_educativo": "Nivel educativo",
    "lengua_materna": "Lengua materna",
}

DESAG_ENA = ("nacional", "anio", "region_natural", "departamento", "sexo", "grupo_edad", "nivel_educativo",
             "lengua_materna")
DESAG_ENAHO = ("nacional", "anio", "area", "region_natural", "departamento", "sexo", "grupo_edad")

# Años con microdatos en data/ (los arma scripts/preparar_datos.py). En 2020 no hubo ENA por la pandemia.
ANIOS_ENA = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
ANIOS_ENAHO = tuple(range(2014, 2025))
ANIOS = tuple(sorted(set(ANIOS_ENA) | set(ANIOS_ENAHO)))
NOMBRE_ENCUESTA = {"ENA": "Encuesta Nacional Agropecuaria (ENA)", "ENAHO": "Encuesta Nacional de Hogares (ENAHO)"}


def periodo(anios):
    """2025 → «2025»; (2014, …, 2025) → «2014-2025»."""
    anios = sorted(anios)
    return str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"


def fuente(encuesta, anios):
    return f"INEI, {NOMBRE_ENCUESTA[encuesta]} {periodo(anios)}, microdatos"

UNIVERSO_PM = "pequeños y medianos productores agropecuarios (persona natural)"
UNIVERSO_UA = "unidades agropecuarias (productores y empresas)"


@dataclass(frozen=True)
class Indicador:
    id: str
    nombre: str
    encuesta: str                 # ENA | ENAHO (el año va en cada cálculo)
    base: str                     # ena | enaho
    columna: str
    tipo: str                     # proporcion | media | distribucion
    unidad: str
    universo: str
    variable: str                 # pregunta o variable del INEI de donde sale
    sinonimos: tuple = ()
    desagregaciones: tuple = DESAG_ENA
    nota: str = ""
    categorias: tuple = field(default=())

    @property
    def anios(self):
        return ANIOS_ENA if self.base == "ena" else ANIOS_ENAHO


INDICADORES = [
    # ENA: el productor --------------------------------------------------------------------------------------------
    Indicador("edad_promedio", "Edad promedio del productor agropecuario", "ENA", "ena", "edad", "media",
              "años", UNIVERSO_PM, "Cap. 1100, P1104_A (edad del productor, P1102 = 1)",
              ("edad promedio", "edad media", "promedio de edad", "qué edad", "envejec")),
    Indicador("productores_60_mas", "Productores de 60 años a más", "ENA", "ena", "edad_60_mas",
              "proporcion", "%", UNIVERSO_PM, "Cap. 1100, P1104_A ≥ 60",
              ("60 años", "60 a más", "adultos mayores", "mayores de 60", "tercera edad", "60+")),
    Indicador("productores_15_24", "Productores de 15 a 24 años", "ENA", "ena", "edad_15_24", "proporcion",
              "%", UNIVERSO_PM, "Cap. 1100, P1104_A entre 15 y 24",
              ("15 a 24", "jóvenes", "joven", "relevo generacional", "relevo")),
    Indicador("productores_15_29", "Productores de 15 a 29 años", "ENA", "ena", "edad_15_29", "proporcion",
              "%", UNIVERSO_PM, "Cap. 1100, P1104_A entre 15 y 29",
              ("15 a 29", "menores de 30", "menos de 30"),
              nota="Corte comparable con el CENAGRO 2012 y la ENA 2022."),
    Indicador("estructura_edad", "Estructura por edad del productor", "ENA", "ena", "grupo_edad",
              "distribucion", "%", UNIVERSO_PM, "Cap. 1100, P1104_A agrupada como el INEI (15-24, 25-44, 45-59, 60+)",
              ("estructura por edad", "grupos de edad", "distribución por edad", "pirámide", "por tramos de edad"),
              desagregaciones=("nacional", "anio", "region_natural", "sexo"),
              categorias=("15-24", "25-44", "45-59", "60 y más")),
    Indicador("productoras_mujeres", "Productoras mujeres", "ENA", "ena", "mujer", "proporcion", "%",
              UNIVERSO_PM, "Cap. 1100, P1103 = 2 (sexo del productor)",
              ("mujeres", "productoras", "género", "feminización", "sexo femenino"),
              desagregaciones=tuple(d for d in DESAG_ENA if d != "sexo")),
    Indicador("hasta_primaria", "Productores con primaria o menos", "ENA", "ena", "hasta_primaria",
              "proporcion", "%", UNIVERSO_PM, "Cap. 1100, P1105 ≤ 4 (sin nivel, inicial o primaria)",
              ("primaria", "educación", "nivel educativo", "escolaridad", "instrucción"),
              desagregaciones=tuple(d for d in DESAG_ENA if d != "nivel_educativo")),
    Indicador("nivel_educativo_dist", "Nivel educativo del productor", "ENA", "ena", "nivel_educativo",
              "distribucion", "%", UNIVERSO_PM, "Cap. 1100, P1105 agrupada (hasta primaria, secundaria, superior)",
              ("distribución educativa", "nivel educativo alcanzado", "estudios superiores", "secundaria"),
              desagregaciones=("nacional", "anio", "region_natural", "sexo", "grupo_edad"),
              categorias=("Hasta primaria", "Secundaria", "Superior")),
    Indicador("lengua_originaria", "Productores con lengua materna originaria", "ENA", "ena",
              "lengua_originaria", "proporcion", "%", UNIVERSO_PM,
              "Cap. 1100, P1106 = quechua, aymara u otra lengua nativa",
              ("lengua materna", "quechua", "aymara", "lengua originaria", "lengua nativa", "idioma"),
              desagregaciones=tuple(d for d in DESAG_ENA if d != "lengua_materna")),
    # ENA: servicios y activos -------------------------------------------------------------------------------------
    Indicador("capacitacion", "Productores que recibieron capacitación", "ENA", "ena", "capacitacion",
              "proporcion", "%", UNIVERSO_UA, "Cap. 700, P701 (últimos 3 años)",
              ("capacitación", "capacitado", "capacitados", "capacitaciones", "cursos", "talleres"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("asistencia_tecnica", "Productores que recibieron asistencia técnica", "ENA", "ena",
              "asistencia_tecnica", "proporcion", "%", UNIVERSO_UA, "Cap. 700, P704 (últimos 3 años)",
              ("asistencia técnica", "extensión agraria", "extensionista", "asesoría técnica", "asesoramiento"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("asociatividad", "Productores que pertenecen a una asociación, cooperativa o comité", "ENA",
              "ena", "asociado", "proporcion", "%", UNIVERSO_UA, "Cap. 800, P801",
              ("asociación", "asociatividad", "cooperativa", "comité", "organización de productores", "asociados"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("solicito_credito", "Productores que solicitaron crédito", "ENA", "ena", "solicito_credito",
              "proporcion", "%", UNIVERSO_UA, "Cap. 900, P901 (últimos 12 meses)",
              ("solicitaron crédito", "pidieron crédito", "solicitud de crédito", "pidió préstamo"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("obtuvo_credito", "Productores que obtuvieron crédito", "ENA", "ena", "obtuvo_credito",
              "proporcion", "%", UNIVERSO_UA, "Cap. 900, P901 = 1 y P902 = 1 (últimos 12 meses)",
              ("crédito", "financiamiento", "préstamo", "acceso al crédito", "obtuvieron crédito"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("seguro_agrario", "Productores con seguro agropecuario", "ENA", "ena", "seguro_agrario",
              "proporcion", "%", UNIVERSO_UA, "Cap. 900, P905 (últimos 12 meses)",
              ("seguro", "seguro agrario", "seguro agropecuario"),
              nota="Desagregar por sexo, edad, educación o lengua deja solo a los pequeños y medianos productores."),
    Indicador("cuenta_ahorro", "Productores con cuenta de ahorro", "ENA", "ena", "cuenta_ahorro",
              "proporcion", "%", UNIVERSO_PM, "Cap. 900, P907 (últimos 12 meses)",
              ("ahorro", "cuenta de ahorro", "cuenta bancaria", "inclusión financiera", "bancarización")),
    Indicador("tipo_actividad_dist", "Tipo de actividad de la unidad agropecuaria", "ENA", "ena",
              "tipo_actividad", "distribucion", "%", UNIVERSO_UA,
              "P102_1 y P102_2 hasta 2022; P142_1 (agrícola) y P142_2 (pecuaria) desde 2023",
              ("tipo de actividad", "agrícola y pecuaria", "solo agrícola", "solo pecuaria", "crianza"),
              desagregaciones=("nacional", "anio", "region_natural"),
              categorias=("Agrícola y pecuaria", "Solo agrícola", "Solo pecuaria", "No realizó actividad")),
    # ENAHO ---------------------------------------------------------------------------------------------------------
    Indicador("pobreza_monetaria", "Pobreza monetaria", "ENAHO", "enaho", "pobre", "proporcion",
              "% de la población", "población residente habitual",
              "Sumaria, pobreza ≤ 2 (pobre extremo o no extremo)",
              ("pobreza", "pobres", "pobreza monetaria", "incidencia de pobreza"), desagregaciones=DESAG_ENAHO,
              nota="Por área, región o departamento: hogares con factor07 × mieperho (método del INEI); "
                   "por sexo o edad: personas con facpob07."),
    Indicador("pobreza_extrema", "Pobreza extrema", "ENAHO", "enaho", "pobre_extremo", "proporcion",
              "% de la población", "población residente habitual", "Sumaria, pobreza = 1 (pobre extremo)",
              ("pobreza extrema", "extrema pobreza", "pobres extremos", "indigencia"), desagregaciones=DESAG_ENAHO,
              nota="Por área, región o departamento: hogares con factor07 × mieperho (método del INEI); "
                   "por sexo o edad: personas con facpob07."),
]

POR_ID = {i.id: i for i in INDICADORES}
IDS = tuple(POR_ID)

REGIONES = ("Costa", "Sierra", "Selva")
AREAS = ("Urbana", "Rural")
SEXOS = ("Hombre", "Mujer")
DEPARTAMENTOS = ("Amazonas", "Áncash", "Apurímac", "Arequipa", "Ayacucho", "Cajamarca", "Callao", "Cusco",
                 "Huancavelica", "Huánuco", "Ica", "Junín", "La Libertad", "Lambayeque", "Lima", "Loreto",
                 "Madre de Dios", "Moquegua", "Pasco", "Piura", "Puno", "San Martín", "Tacna", "Tumbes", "Ucayali")


def catalogo_para_prompt():
    """Texto compacto del catálogo para el modelo de lenguaje (se cachea: no cambia entre consultas)."""
    lineas = [f"Años: ENA {', '.join(map(str, ANIOS_ENA))} (en 2020 no hubo ENA); ENAHO {periodo(ANIOS_ENAHO)}. "
              "La ENA 2021 no tuvo el capítulo de servicios financieros (crédito, seguro, ahorro) ni lengua materna."]
    for i in INDICADORES:
        lineas.append(f"- {i.id}: {i.nombre} ({i.encuesta}; {i.tipo}; universo: {i.universo}; "
                      f"desagregaciones: {', '.join(i.desagregaciones)})")
    return "\n".join(lineas)
