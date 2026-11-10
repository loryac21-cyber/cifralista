"""De la pregunta en lenguaje natural a una consulta del catálogo (salida estructurada con Claude).

El modelo solo elige: qué indicadores, cómo desagregar y qué filtros aplicar, siempre dentro de listas cerradas
(enums del esquema). No ve los microdatos ni devuelve cifras. Si no hay clave de API o la llamada falla, un
intérprete por reglas hace lo mismo con palabras clave, para que el demo nunca se caiga.
"""
import os
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from .catalogo import (AREAS, DEPARTAMENTOS, DESAGREGACIONES, IDS, INDICADORES, POR_ID, REGIONES,
                       catalogo_para_prompt)
from .motor import Filtros, sin_tildes

MODELO = os.getenv("CIFRALISTA_MODELO", "claude-haiku-5-5")


class Consulta(BaseModel):
    """Lo que la app va a calcular. Todos los campos son listas cerradas: el modelo no puede inventar opciones."""
    en_alcance: bool = Field(description="false si la pregunta pide algo que no está en el catálogo")
    indicadores: list[Literal[IDS]] = Field(description="1 a 3 ids del catálogo, en orden de relevancia")
    desagregacion: Literal[tuple(DESAGREGACIONES)]
    filtro_region_natural: Literal[("ninguno",) + REGIONES]
    filtro_area: Literal[("ninguno",) + AREAS]
    filtro_departamento: Literal[("ninguno",) + DEPARTAMENTOS]
    filtro_sexo: Literal["ninguno", "Hombre", "Mujer"]
    explicacion: str = Field(description="una oración: qué se calculará, o por qué no se puede y qué sí hay")

    def filtros(self):
        v = lambda x: None if x == "ninguno" else x
        return Filtros(region_natural=v(self.filtro_region_natural), area=v(self.filtro_area),
                       departamento=v(self.filtro_departamento), sexo=v(self.filtro_sexo))


@dataclass
class Interpretacion:
    consulta: Consulta
    origen: str                  # "claude" | "reglas"
    aviso: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0


SISTEMA = f"""Eres el intérprete de CifraLista, una herramienta que calcula indicadores oficiales del Perú con los \
microdatos de la ENA 2025 y la ENAHO 2024 del INEI. Tu único trabajo es traducir la pregunta del usuario a una \
consulta del catálogo. No calculas ni escribes cifras: el cálculo lo hace Python después.

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
- Si la pregunta pide algo que el catálogo no tiene (ingresos, informalidad, anemia, producción por cultivo, \
años anteriores, distritos…), responde en_alcance=false, deja indicadores vacío y explica en una oración qué sí se \
puede calcular.
- La explicación va en español, sin cifras."""


def _cliente(api_key):
    import anthropic
    return anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=30.0)


def interpretar(pregunta, api_key=None):
    """Interpreta con Claude si hay clave; si no, o si falla, con reglas."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            r = _cliente(api_key).messages.parse(
                model=MODELO,
                max_tokens=2048,
                system=[{"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": pregunta}],
                output_config={"effort": "low"},
                output_format=Consulta,
            )
            consulta = r.parsed_output
            if consulta is None:
                raise ValueError(f"respuesta sin consulta (stop_reason={r.stop_reason})")
            consulta = _sanear(consulta)
            return Interpretacion(consulta, "claude", tokens_entrada=r.usage.input_tokens,
                                  tokens_salida=r.usage.output_tokens)
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

    desagregacion = "nacional"
    for d, claves in PALABRAS_DESAGREGACION:
        if any(k in t for k in claves):
            desagregacion = d
            break

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

    consulta = Consulta(en_alcance=bool(ids), indicadores=ids, desagregacion=desagregacion,
                        explicacion=("Se calcula con el catálogo validado." if ids else
                                     "No encontré un indicador del catálogo para esa pregunta; prueben con edad, "
                                     "educación, capacitación, asistencia técnica, crédito, asociatividad o pobreza."),
                        **filtros)
    return _sanear(consulta)
