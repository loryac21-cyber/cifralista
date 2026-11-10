"""Motor de cálculo: estimaciones ponderadas con factor de expansión, error estándar y coeficiente de variación.

Todo número que muestra CifraLista sale de aquí. El error estándar se aproxima por linealización de Taylor con los
estratos y conglomerados (unidades primarias de muestreo) del diseño de cada encuesta; el INEI considera
«referencial» una estimación con coeficiente de variación mayor a 15 %.
"""
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .catalogo import DESAGREGACIONES, POR_ID, Indicador

DATA = Path(__file__).resolve().parents[1] / "data"
CV_REFERENCIAL = 15.0
N_MINIMO = 30
Z95 = 1.96
SOLO_PERSONA_NATURAL = {"sexo", "grupo_edad", "nivel_educativo", "lengua_materna"}
ORDEN = {
    "region_natural": ["Costa", "Sierra", "Selva", "Lima Metropolitana"],
    "area": ["Urbana", "Rural"],
    "sexo": ["Hombre", "Mujer"],
    "nivel_educativo": ["Hasta primaria", "Secundaria", "Superior"],
    "lengua_materna": ["Castellano", "Quechua", "Aymara", "Otra lengua nativa", "Otra"],
}


@lru_cache(maxsize=None)
def base(nombre):
    archivos = {"ena": "ena2025_productores", "hogares": "enaho2024_hogares", "personas": "enaho2024_personas"}
    df = pd.read_parquet(DATA / f"{archivos[nombre]}.parquet")
    # Diseño muestral precalculado: código de conglomerado por fila, estrato de cada conglomerado y nº de
    # conglomerados por estrato. Así el error estándar se calcula con np.bincount en milisegundos.
    psu = pd.factorize(df["estrato_diseno"].astype(str) + "|" + df["psu"].astype(str))[0]
    estrato = pd.factorize(df["estrato_diseno"].astype(str))[0]
    estrato_de_psu = np.zeros(psu.max() + 1, dtype=int)
    estrato_de_psu[psu] = estrato
    df.attrs["diseno"] = (psu, estrato_de_psu, np.bincount(estrato_de_psu))
    return df


@dataclass
class Filtros:
    region_natural: str | None = None
    area: str | None = None
    departamento: str | None = None
    sexo: str | None = None

    def activos(self):
        return {k: v for k, v in self.__dict__.items() if v}

    def texto(self):
        return ", ".join(f"{DESAGREGACIONES[k].lower()}: {v}" for k, v in self.activos().items())


@dataclass
class Resultado:
    indicador: Indicador
    desagregacion: str
    filtros: Filtros
    tabla: pd.DataFrame
    nacional: dict | None
    metodo: str
    base_usada: str
    avisos: list = field(default_factory=list)

    @property
    def unidad(self):
        return self.indicador.unidad

    def ficha(self):
        i = self.indicador
        f = self.filtros.texto()
        return {
            "Indicador": i.nombre,
            "Fuente": i.fuente,
            "Universo": i.universo + (f" ({f})" if f else ""),
            "Variable": i.variable,
            "Desagregación": DESAGREGACIONES[self.desagregacion],
            "Método": self.metodo,
            "Precisión": f"Error estándar por linealización de Taylor (estratos y conglomerados). Coeficiente de "
                         f"variación > {CV_REFERENCIAL:.0f} % o menos de {N_MINIMO} casos = cifra referencial.",
        }


# Estimación con diseño muestral --------------------------------------------------------------------------------------

def razon_con_error(df, y, x, peso="factor"):
    """R = Σ w·y / Σ w·x y su error estándar por linealización (y, x son 0 fuera del dominio)."""
    w = df[peso].to_numpy()
    X = float((w * x).sum())
    if X == 0:
        return np.nan, np.nan
    R = float((w * y).sum()) / X
    z = w * (y - R * x) / X
    psu, estrato_de_psu, n_h = df.attrs["diseno"]
    zc = np.bincount(psu, weights=z, minlength=len(estrato_de_psu))          # total linealizado por conglomerado
    media_h = np.bincount(estrato_de_psu, weights=zc, minlength=len(n_h)) / n_h
    ss = np.bincount(estrato_de_psu, weights=(zc - media_h[estrato_de_psu]) ** 2, minlength=len(n_h))
    validos = n_h > 1                                                         # estratos con un solo conglomerado
    var = float((n_h[validos] / (n_h[validos] - 1) * ss[validos]).sum())
    return R, var ** 0.5


def estimar(df, columna, dominio, categoria=None, escala=100.0):
    """Media (o proporción × 100) de `columna` dentro de `dominio`, con todo el diseño para el error estándar."""
    valores = df[columna]
    if categoria is not None:          # distribución: proporción de una categoría entre los que respondieron
        en_dominio = dominio & valores.notna()
        v = (valores == categoria).astype(float).to_numpy()
    else:
        en_dominio = dominio & valores.notna()
        v = valores.fillna(0).astype(float).to_numpy()
    d = en_dominio.to_numpy().astype(float)
    R, ee = razon_con_error(df, d * v, d)
    n = int(en_dominio.sum())
    N = float(df.loc[en_dominio, "factor"].sum())
    return {"valor": R * escala, "ee": ee * escala, "n": n, "N": N}


def _fila(grupo, est, indicador_nombre, categoria=None):
    cv = abs(est["ee"] / est["valor"] * 100) if est["valor"] else np.nan
    fila = {"indicador": indicador_nombre, "grupo": grupo, "valor": est["valor"], "ee": est["ee"], "cv": cv,
            "ic_inf": est["valor"] - Z95 * est["ee"], "ic_sup": est["valor"] + Z95 * est["ee"],
            "n": est["n"], "N": est["N"], "referencial": bool(cv > CV_REFERENCIAL or est["n"] < N_MINIMO)}
    if categoria is not None:
        fila["categoria"] = categoria
    return fila


def elegir_base(ind, desagregacion):
    if ind.base == "ena":
        return "ena"
    return "personas" if desagregacion in {"sexo", "grupo_edad"} else "hogares"


def metodo_de(ind, base_usada):
    if base_usada == "ena":
        return "Promedio ponderado con FACTOR_PRODUCTOR (factor de expansión del productor agropecuario)."
    if base_usada == "hogares":
        return "Promedio ponderado de hogares con factor07 × mieperho (método oficial del INEI para pobreza)."
    return "Promedio ponderado de residentes habituales con facpob07 (factor de expansión de personas)."


def calcular(indicador_id, desagregacion="nacional", filtros=None, con_nacional=True):
    ind = POR_ID[indicador_id]
    filtros = filtros or Filtros()
    if desagregacion not in ind.desagregaciones:
        raise ValueError(f"«{ind.nombre}» no se puede desagregar por {DESAGREGACIONES[desagregacion].lower()}. "
                         f"Opciones: {', '.join(DESAGREGACIONES[d] for d in ind.desagregaciones)}.")
    base_usada = elegir_base(ind, desagregacion)
    df = base(base_usada)
    avisos = []
    dominio = pd.Series(True, index=df.index)
    for k, v in filtros.activos().items():
        if k not in df.columns:
            raise ValueError(f"La {ind.encuesta} no permite filtrar por {DESAGREGACIONES[k].lower()}.")
        dominio &= df[k].eq(v)
    if ind.base == "ena" and (desagregacion in SOLO_PERSONA_NATURAL or filtros.sexo) and "pequeno_mediano" in df:
        if ind.universo.startswith("unidades"):
            avisos.append("Por sexo, edad, educación o lengua, el universo son solo los pequeños y medianos "
                          "productores (persona natural); las empresas no tienen esas características.")
        dominio &= df["pequeno_mediano"]

    filas = []
    if ind.tipo == "distribucion":
        grupos = [("Total", dominio)] if desagregacion == "nacional" else [
            (g, dominio & df[desagregacion].eq(g)) for g in _grupos(df, desagregacion, dominio)]
        for g, dom in grupos:
            for cat in ind.categorias:
                filas.append(_fila(g, estimar(df, ind.columna, dom, categoria=cat), ind.nombre, categoria=cat))
    else:
        escala = 1.0 if ind.tipo == "media" else 100.0
        if desagregacion == "nacional":
            filas.append(_fila("Total" if filtros.activos() else "Perú",
                               estimar(df, ind.columna, dominio, escala=escala), ind.nombre))
        else:
            for g in _grupos(df, desagregacion, dominio):
                filas.append(_fila(g, estimar(df, ind.columna, dominio & df[desagregacion].eq(g), escala=escala),
                                   ind.nombre))
    tabla = pd.DataFrame(filas)
    nacional = None
    if con_nacional and desagregacion != "nacional" and ind.tipo != "distribucion":
        escala = 1.0 if ind.tipo == "media" else 100.0
        nacional = _fila("Total", estimar(df, ind.columna, dominio, escala=escala), ind.nombre)
    if tabla.referencial.any():
        avisos.append(f"{int(tabla.referencial.sum())} cifra(s) con coeficiente de variación mayor a "
                      f"{CV_REFERENCIAL:.0f} % o menos de {N_MINIMO} casos: úsenlas como referenciales.")
    return Resultado(ind, desagregacion, filtros, tabla, nacional, metodo_de(ind, base_usada), base_usada, avisos)


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


def _grupos(df, desagregacion, dominio):
    presentes = df.loc[dominio & df[desagregacion].notna(), desagregacion].unique().tolist()
    if desagregacion in ORDEN:
        return [g for g in ORDEN[desagregacion] if g in presentes] + sorted(set(presentes) - set(ORDEN[desagregacion]))
    return sorted(presentes, key=sin_tildes)          # Áncash va después de Amazonas, no al final


def calcular_varios(indicador_ids, desagregacion="nacional", filtros=None):
    return [calcular(i, desagregacion, filtros) for i in indicador_ids]


# Código reproducible -------------------------------------------------------------------------------------------------

def codigo_reproducible(res: Resultado):
    """Snippet de pandas que reproduce la cifra principal sin CifraLista (para el anexo metodológico de una tesis)."""
    ind = res.indicador
    archivo = {"ena": "ena2025_productores", "hogares": "enaho2024_hogares", "personas": "enaho2024_personas"}
    lineas = ["import pandas as pd", "",
              f'df = pd.read_parquet("data/{archivo[res.base_usada]}.parquet")']
    cond = [f'(df["{k}"] == "{v}")' for k, v in res.filtros.activos().items()]
    if ind.base == "ena" and (res.desagregacion in SOLO_PERSONA_NATURAL or res.filtros.sexo):
        cond.append('df["pequeno_mediano"]')
    col = ind.columna
    if cond:
        lineas.append(f"df = df[{' & '.join(cond)}]")
    if ind.tipo == "distribucion":
        lineas.append(f'df = df[df["{col}"].notna()]')
        por = [] if res.desagregacion == "nacional" else [res.desagregacion]
        lineas.append(f"tabla = df.groupby({por + [col]!r})['factor'].sum()")
        lineas.append(f"tabla = tabla / tabla.groupby(level={0 if por else None!r}).transform('sum') * 100"
                      if por else "tabla = tabla / tabla.sum() * 100")
    else:
        escala = "" if ind.tipo == "media" else " * 100"
        lineas.append(f'df = df[df["{col}"].notna()]')
        f = f'lambda g: (g["{col}"] * g["factor"]).sum() / g["factor"].sum(){escala}'
        if res.desagregacion == "nacional":
            lineas.append(f'valor = (df["{col}"] * df["factor"]).sum() / df["factor"].sum(){escala}')
        else:
            lineas.append(f'tabla = df.groupby("{res.desagregacion}").apply({f})')
    return "\n".join(lineas)
