"""Cifras publicadas por el INEI con las que se contrasta el motor (las usa la app y las pruebas)."""
from .motor import Filtros, calcular

# (indicador, desagregación, grupo, cifra publicada, dónde la publica el INEI)
PUBLICADAS = [
    ("edad_promedio", "nacional", "Perú", 54.5, "ENA 2025, resultados del INEI"),
    ("productores_60_mas", "nacional", "Perú", 37.9, "ENA 2025"),
    ("productores_15_24", "nacional", "Perú", 0.9, "ENA 2025"),
    ("edad_promedio", "sexo", "Mujer", 55.2, "ENA 2025"),
    ("hasta_primaria", "nacional", "Perú", 57.7, "ENA 2025"),
    ("capacitacion", "nacional", "Perú", 7.4, "ENA 2025"),
    ("pobreza_monetaria", "nacional", "Perú", 27.6, "ENAHO 2024, informe técnico de pobreza"),
    ("pobreza_monetaria", "area", "Rural", 39.3, "ENAHO 2024"),
    ("pobreza_monetaria", "area", "Urbana", 24.8, "ENAHO 2024"),
    ("pobreza_extrema", "nacional", "Perú", 5.5, "ENAHO 2024"),
]


def contrastar():
    """Lista de dicts: cifra del INEI frente a la que calcula CifraLista desde los microdatos."""
    filas = []
    for ind, desag, grupo, publicada, fuente in PUBLICADAS:
        res = calcular(ind, desag, Filtros(), con_nacional=False)
        valor = float(res.tabla.set_index("grupo").loc[grupo, "valor"])
        etiqueta = res.indicador.nombre + ("" if grupo == "Perú" else f" ({grupo.lower()})")
        filas.append({"Indicador": etiqueta, "INEI": publicada, "CifraLista": round(valor, 1),
                      "Coincide": round(valor, 1) == publicada, "Fuente": fuente})
    return filas
