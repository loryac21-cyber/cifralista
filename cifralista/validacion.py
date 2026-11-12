"""Cifras publicadas por el INEI con las que se contrasta el motor (las usa la app y las pruebas)."""
from .motor import Filtros, calcular

POBREZA_INEI = "INEI, Evolución de la pobreza monetaria 2014-2023 y 2015-2024 (informes técnicos)"

# (indicador, desagregación, grupo, año, cifra publicada, dónde la publica el INEI)
PUBLICADAS = [
    ("edad_promedio", "nacional", "Perú", 2025, 54.5, "ENA 2025, resultados del INEI"),
    ("productores_60_mas", "nacional", "Perú", 2025, 37.9, "ENA 2025"),
    ("productores_15_24", "nacional", "Perú", 2025, 0.9, "ENA 2025"),
    ("edad_promedio", "sexo", "Mujer", 2025, 55.2, "ENA 2025"),
    ("hasta_primaria", "nacional", "Perú", 2025, 57.7, "ENA 2025"),
    ("capacitacion", "nacional", "Perú", 2025, 7.4, "ENA 2025"),
    ("productores_60_mas", "nacional", "Perú", 2022, 40.2, "ENA 2022, nota de prensa del INEI n.º 113-2023"),
    ("pobreza_monetaria", "area", "Rural", 2024, 39.3, "ENAHO 2024, informe técnico de pobreza"),
    ("pobreza_monetaria", "area", "Urbana", 2024, 24.8, "ENAHO 2024"),
    ("pobreza_extrema", "nacional", "Perú", 2024, 5.5, "ENAHO 2024"),
] + [
    ("pobreza_monetaria", "nacional", "Perú", anio, valor, POBREZA_INEI)
    for anio, valor in {2014: 22.7, 2015: 21.8, 2016: 20.7, 2017: 21.7, 2018: 20.5, 2019: 20.2, 2020: 30.1,
                        2021: 25.9, 2022: 27.5, 2023: 29.0, 2024: 27.6}.items()
]


def contrastar():
    """Lista de dicts: cifra del INEI frente a la que calcula CifraLista desde los microdatos."""
    filas = []
    for ind, desag, grupo, anio, publicada, fuente in PUBLICADAS:
        res = calcular(ind, desag, Filtros(), con_nacional=False, anio=anio)
        valor = float(res.tabla.set_index("grupo").loc[grupo, "valor"])
        etiqueta = res.indicador.nombre + ("" if grupo == "Perú" else f" ({grupo.lower()})") + f" {anio}"
        filas.append({"Indicador": etiqueta, "Año": anio, "INEI": publicada, "CifraLista": round(valor, 1),
                      "Coincide": round(valor, 1) == publicada, "Fuente": fuente})
    return filas
