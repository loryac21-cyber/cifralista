"""De la pregunta en lenguaje natural a una consulta del catálogo (salida estructurada con Claude).

El modelo solo elige: qué indicadores, cómo desagregar y qué filtros aplicar, siempre dentro de listas cerradas
(enums del esquema). No ve los microdatos ni devuelve cifras. Si no hay acceso a Claude o la llamada falla, un
intérprete por reglas hace lo mismo con palabras clave, para que el demo nunca se caiga.
"""
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from . import llm
from .catalogo import (ANIOS, AREAS, DEPARTAMENTOS, DESAGREGACIONES, IDS, INDICADORES, POR_ID, REGIONES,
                       catalogo_para_prompt)
from .motor import Filtros, sin_tildes

MODELO = llm.MODELO
ANIOS_TXT = tuple(str(a) for a in ANIOS)


class Consulta(BaseModel):
    """Lo que la app va a calcular. Todos los campos son listas cerradas: el modelo no puede inventar opciones."""
    en_alcance: bool = Field(description="false si la pregunta pide algo que no está en el catálogo")
    indicadores: list[Literal[IDS]] = Field(description="1 a 3 ids del catálogo, en orden de relevancia")
    desagregacion: Literal[tuple(DESAGREGACIONES)]
    anio: Literal[("ultimo",) + ANIOS_TXT] = Field(
        description="año pedido; 'ultimo' si no dice año o si pide la evolución (desagregacion='anio')")
    filtro_region_natural: Literal[("ninguno",) + REGIONES]
    filtro_area: Literal[("ninguno",) + AREAS]
    filtro_departamento: Literal[("ninguno",) + DEPARTAMENTOS]
    filtro_sexo: Literal["ninguno", "Hombre", "Mujer"]
    explicacion: str = Field(description="una oración: qué se calculará, o por qué no se puede y qué sí hay")

    def filtros(self):
        v = lambda x: None if x == "ninguno" else x
        return Filtros(region_natural=v(self.filtro_region_natural), area=v(self.filtro_area),
                       departamento=v(self.filtro_departamento), sexo=v(self.filtro_sexo))

    def anio_int(self):
        return None if self.anio == "ultimo" or self.desagregacion == "anio" else int(self.anio)


@dataclass
class Interpretacion:
    consulta: Consulta
    origen: str                  # "claude" | "reglas"
    aviso: str = ""
    via: str = ""                # "api" | "claude-code" cuando origen es "claude"
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0


SISTEMA = f"""Eres el intérprete de CifraLista, una herramienta que calcula indicadores oficiales del Perú con los \
microdatos de la ENA (2014-2025) y la ENAHO (2014-2024) del INEI. Tu único trabajo es traducir la pregunta del \
usuario a una consulta del catálogo. No calculas ni escribes cifras: el cálculo lo hace Python después.

Catálogo (id: nombre; encuesta; tipo; universo; desagregaciones válidas):
{catalogo_para_prompt()}

Reglas:
- Elige de 1 a 3 indicadores del catálogo que respondan la pregunta. Si son varios, deben admitir la misma \
desagregación.
- La desagregación debe estar entre las válidas de cada indicador elegido. Si el usuario no pide desagregar, usa \
"nacional".
- En el Perú «por regiones», «regional» o «por departamentos» significa departamento. «Región natural», «costa, \
sierra y selva» significa region_natural. «Urbano/rural» es area (solo ENAHO).
- Usa filtros solo cuando la pregunta acota el universo («en la sierra», «en Puno», «de las mujeres»). Si pide \
comparar («hombres y mujeres», «por sexo»), eso es desagregación, no filtro. No filtres por la misma variable que \
desagregas.
- Años: si la pregunta pide la evolución, la tendencia, una serie o un periodo («desde 2014», «entre 2015 y \
2022», «en los últimos años»), usa desagregacion="anio" y anio="ultimo"; los filtros se pueden combinar con la \
serie («evolución de la pobreza en Puno»). Si pide la evolución Y otra desagregación («evolución por región»), \
elige la serie y dilo en la explicación. Si menciona un solo año («en 2019»), pon ese año en anio. Si no dice año, \
anio="ultimo".
- Si pide un año sin dato (ENA 2020 o antes de 2014, ENAHO 2025 o antes de 2014), responde en_alcance=false y di \
qué años hay.
- Si la pregunta pide algo que el catálogo no tiene (ingresos, informalidad, anemia, producción por cultivo, \
distritos…), responde en_alcance=false, deja indicadores vacío y explica en una oración qué sí se puede calcular.
- La explicación va en español, sin cifras."""


def interpretar(pregunta, api_key=None, usar_ia=True):
    """Interpreta con Claude (API o Claude Code local); si no hay ninguno, o si falla, con reglas."""
    if usar_ia and llm.camino(api_key):
        try:
            r = llm.llamar(SISTEMA, pregunta, Consulta, api_key=api_key)
            return Interpretacion(_sanear(r.datos), "claude", via=r.via, tokens_entrada=r.tokens_entrada,
                                  tokens_salida=r.tokens_salida, costo_usd=r.costo_usd)
        except Exception as e:  # el demo sigue con reglas; el aviso se muestra en la app
            return Interpretacion(interpretar_con_reglas(pregunta), "reglas",
                                  aviso=f"No se pudo usar Claude ({type(e).__name__}); se usó el intérprete por reglas.")
    return Interpretacion(interpretar_con_reglas(pregunta), "reglas")


def _sanear(c: Consulta) -> Consulta:
    """Defensa en profundidad: quita duplicados, limita a 3 y corrige desagregaciones no válidas."""
    ids = list(dict.fromkeys(c.indicadores))[:3]
    if ids and not all(c.desagregacion in POR_ID[i].desagregaciones for i in ids):
        validos = [i for i in ids if c.desagregacion in POR_ID[i].desagregaciones]
        ids = validos or ids[:1]
        if c.desagregacion not in POR_ID[ids[0]].desagregaciones:
            c.desagregacion = "nacional"
    c.indicadores = ids
    if c.desagregacion == "anio":
        c.anio = "ultimo"
    if c.desagregacion == "sexo":
        c.filtro_sexo = "ninguno"
    if c.desagregacion == "region_natural":
        c.filtro_region_natural = "ninguno"
    if c.desagregacion == "departamento":
        c.filtro_departamento = "ninguno"
    if ids and POR_ID[ids[0]].base == "ena":
        c.filtro_area = "ninguno"
    c.en_alcance = c.en_alcance and bool(ids)
    return c


# Intérprete por reglas (sin IA) --------------------------------------------------------------------------------------

PALABRAS_SERIE = ["evolucion", "evoluciono", "evolucionado", "tendencia", "serie", "a lo largo", "ultimos anos",
                  "historic", "en el tiempo", "ano a ano", "cada ano", "por ano", "por anos", "anual"]
PATRON_SERIE = re.compile(r"\bdesde (el )?(ano )?20[12]\d\b|\bentre (el )?20[12]\d y (el )?20[12]\d\b|"
                          r"\b20[12]\d ?(-|a|al) ?20[12]\d\b")
PALABRAS_DESAGREGACION = [
    ("region_natural", ["region natural", "regiones naturales", "costa, sierra y selva", "costa sierra y selva",
                        "costa, sierra, selva", "dominio geografico"]),
    ("departamento", ["por departamento", "por departamentos", "por region", "por regiones", "regional",
                      "cada departamento", "cada region", "departamental", "mapa"]),
    ("area", ["urbano y rural", "urbana y rural", "rural y urbano", "rural y urbana", "por area", "area de residencia",
              "rural frente", "urbano frente"]),
    ("sexo", ["por sexo", "hombres y mujeres", "mujeres y hombres", "segun sexo", "brecha de genero", "por genero"]),
    ("grupo_edad", ["por edad", "grupo de edad", "grupos de edad", "por tramos de edad", "segun edad"]),
    ("nivel_educativo", ["por nivel educativo", "segun nivel educativo", "por educacion"]),
    ("lengua_materna", ["por lengua", "segun lengua", "por idioma"]),
]


def interpretar_con_reglas(pregunta):
    t = sin_tildes(pregunta)
    puntajes = []
    for i in INDICADORES:
        p = sum(len(s) for s in i.sinonimos if sin_tildes(s) in t)
        if sin_tildes(i.nombre) in t:
            p += 50
        if p:
            puntajes.append((p, i.id))
    puntajes.sort(reverse=True)
    if "pobreza extrema" in t or "extrema pobreza" in t:          # «pobreza» también está en «pobreza extrema»
        puntajes = [x for x in puntajes if x[1] != "pobreza_monetaria"]
    mujeres_como_filtro = re.search(r"\b(las|entre) (mujeres|productoras)\b", t)
    if mujeres_como_filtro and len(puntajes) > 1:                 # «capacitación de las mujeres» es un filtro
        puntajes = [x for x in puntajes if x[1] != "productoras_mujeres"]
    ids = [i for _, i in puntajes[:3]]

    desagregacion, anio = "nacional", "ultimo"
    if any(k in t for k in PALABRAS_SERIE) or PATRON_SERIE.search(t):
        desagregacion = "anio"                        # la serie manda: una sola desagregación por consulta
    else:
        for d, claves in PALABRAS_DESAGREGACION:
            if any(k in t for k in claves):
                desagregacion = d
                break
        menciones = [a for a in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", t) if a in ANIOS_TXT]
        if menciones:
            anio = menciones[-1]

    filtros = {"filtro_region_natural": "ninguno", "filtro_area": "ninguno", "filtro_departamento": "ninguno",
               "filtro_sexo": "ninguno"}
    if desagregacion != "region_natural":
        for r in REGIONES:
            if re.search(rf"\b(en|de) la {r.lower()}\b", t):
                filtros["filtro_region_natural"] = r
    if desagregacion != "departamento":
        for d in DEPARTAMENTOS:
            if re.search(rf"\b(en|de) {sin_tildes(d)}\b", t):
                filtros["filtro_departamento"] = d
    if desagregacion != "area":
        if re.search(r"\b(zonas?|area|ambito) rural(es)?\b|\ben el campo\b", t):
            filtros["filtro_area"] = "Rural"
        elif re.search(r"\b(zonas?|area|ambito) urban[ao]s?\b", t):
            filtros["filtro_area"] = "Urbana"
    if desagregacion != "sexo" and "productoras_mujeres" not in ids:
        if re.search(r"\b(las|de|entre) (mujeres|productoras)\b", t):
            filtros["filtro_sexo"] = "Mujer"

    consulta = Consulta(en_alcance=bool(ids), indicadores=ids, desagregacion=desagregacion, anio=anio,
                        explicacion=("Se calcula con el catálogo validado." if ids else
                                     "No encontré un indicador del catálogo para esa pregunta; prueben con edad, "
                                     "educación, capacitación, asistencia técnica, crédito, asociatividad o pobreza."),
                        **filtros)
    return _sanear(consulta)
