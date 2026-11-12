"""Motor de cálculo: estimaciones ponderadas con factor de expansión, error estándar y coeficiente de variación.

Todo número que muestra CifraLista sale de aquí. El error estándar se aproxima por linealización de Taylor con los
estratos y conglomerados (unidades primarias de muestreo) del diseño de cada encuesta y año; el INEI considera
«referencial» una estimación con coeficiente de variación mayor a 15 %. Cada año se estima con su propia muestra:
una serie es un cálculo por año, no un promedio de años.
"""
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .catalogo import ANIOS_ENA, DESAGREGACIONES, POR_ID, UNIVERSO_UA, Indicador, fuente, periodo

DATA = Path(__file__).resolve().parents[1] / "data"
ARCHIVOS = {"ena": "ena_productores", "hogares": "enaho_hogares", "personas": "enaho_personas"}
CV_REFERENCIAL = 15.0
N_MINIMO = 30
Z95 = 1.96
CAMBIO_DISENO_ENA = 2023          # desde 2023 la ENA usa segmentos (NSEGM) y FACTOR_PRODUCTOR
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
    """Todos los años de una base (ena, hogares o personas)."""
    return pd.read_parquet(DATA / f"{ARCHIVOS[nombre]}.parquet")


@lru_cache(maxsize=None)
def base_anio(nombre, anio):
    """Un año de una base, con su diseño muestral precalculado: código de conglomerado por fila, estrato de cada
    conglomerado y nº de conglomerados por estrato. Así el error estándar se calcula con np.bincount en milisegundos."""
    df = base(nombre)
    df = df[df["anio"] == anio].reset_index(drop=True)
    estrato_txt = df["estrato_diseno"].astype(object).fillna("sin estrato").astype(str)
    psu = pd.factorize(estrato_txt + "|" + df["psu"].astype(object).fillna("sin psu").astype(str))[0]
    estrato = pd.factorize(estrato_txt)[0]
    estrato_de_psu = np.zeros(psu.max() + 1, dtype=int)
    estrato_de_psu[psu] = estrato
    df.attrs["diseno"] = (psu, estrato_de_psu, np.bincount(estrato_de_psu))
    return df


@lru_cache(maxsize=None)
def anios_de(indicador_id):
    """Años en que la encuesta trae la pregunta del indicador (p. ej. la ENA 2021 no tuvo crédito)."""
    ind = POR_ID[indicador_id]
    df = base("ena" if ind.base == "ena" else "hogares")
    return tuple(sorted(int(a) for a in df.loc[df[ind.columna].notna(), "anio"].unique()))


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
    anios: tuple
    avisos: list = field(default_factory=list)

    @property
    def unidad(self):
        return self.indicador.unidad

    @property
    def es_serie(self):
        return self.desagregacion == "anio"

    @property
    def anio(self):
        return None if self.es_serie else self.anios[0]

    @property
    def encuesta_txt(self):
        """«ENA 2025» o «ENA 2014-2025»."""
        return f"{self.indicador.encuesta} {periodo(self.anios)}"

    @property
    def fuente(self):
        return fuente(self.indicador.encuesta, self.anios)

    def ficha(self):
        i = self.indicador
        f = self.filtros.texto()
        return {
            "Indicador": i.nombre,
            "Fuente": self.fuente,
            "Año": periodo(self.anios) + (" (serie, un cálculo por año)" if self.es_serie else ""),
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
    en_dominio = dominio & valores.notna()
    if categoria is not None:          # distribución: proporción de una categoría entre los que respondieron
        v = (valores == categoria).astype(float).to_numpy()
    else:
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


def metodo_de(ind, base_usada, anios):
    if base_usada == "ena":
        if min(anios) >= CAMBIO_DISENO_ENA:
            factor = "FACTOR_PRODUCTOR"
        elif max(anios) < CAMBIO_DISENO_ENA:
            factor = "FACTOR"
        else:
            factor = f"FACTOR (hasta {CAMBIO_DISENO_ENA - 1}) y FACTOR_PRODUCTOR (desde {CAMBIO_DISENO_ENA})"
        return f"Promedio ponderado con {factor} (factor de expansión del productor agropecuario)."
    if base_usada == "hogares":
        return "Promedio ponderado de hogares con factor07 × mieperho (método oficial del INEI para pobreza)."
    return "Promedio ponderado de residentes habituales con facpob07 (factor de expansión de personas)."


def _dominio(df, ind, desagregacion, filtros, avisos):
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
    return dominio


def _avisos_de_anios(ind, anios, serie):
    avisos = []
    if ind.base == "ena":
        if serie and min(anios) < CAMBIO_DISENO_ENA <= max(anios):
            avisos.append(f"Desde {CAMBIO_DISENO_ENA} la ENA usa un nuevo diseño muestral (segmentos y factor del "
                          f"productor): el cambio entre {CAMBIO_DISENO_ENA - 1} y {CAMBIO_DISENO_ENA} puede deberse en "
                          "parte al diseño. Compárenlo con cautela.")
        faltan = [a for a in ANIOS_ENA if min(anios) < a < max(anios) and a not in anios]
        if serie and min(anios) < 2020 < max(anios):
            avisos.append("En 2020 no se realizó la ENA por la pandemia.")
        if serie and faltan:
            avisos.append(f"Sin dato en {', '.join(map(str, faltan))}: la ENA de ese año no incluyó la pregunta.")
        if ind.universo == UNIVERSO_UA and any(2021 <= a <= 2023 for a in anios):
            avisos.append("En 2021-2023 la ENA solo encuestó a pequeños y medianos productores; los demás años "
                          "incluyen empresas, que pesan muy poco en el total.")
    elif 2020 in anios:
        avisos.append("2020 es un año atípico: por la pandemia, parte de las entrevistas de la ENAHO fueron "
                      "telefónicas.")
    return avisos


def calcular(indicador_id, desagregacion="nacional", filtros=None, con_nacional=True, anio=None):
    """Un indicador para un año (por defecto, el último con dato) o, con desagregacion="anio", la serie completa."""
    ind = POR_ID[indicador_id]
    filtros = filtros or Filtros()
    if desagregacion not in ind.desagregaciones:
        raise ValueError(f"«{ind.nombre}» no se puede desagregar por {DESAGREGACIONES[desagregacion].lower()}. "
                         f"Opciones: {', '.join(DESAGREGACIONES[d] for d in ind.desagregaciones)}.")
    disponibles = anios_de(ind.id)
    serie = desagregacion == "anio"
    if serie:
        anios = disponibles
    else:
        anio = disponibles[-1] if anio is None else int(anio)
        if anio not in disponibles:
            raise ValueError(f"«{ind.nombre}» no tiene dato en {anio}. Años con dato: "
                             f"{', '.join(map(str, disponibles))}.")
        anios = (anio,)
    base_usada = elegir_base(ind, desagregacion)
    escala = 1.0 if ind.tipo == "media" else 100.0
    avisos, filas, nacional = [], [], None
    for a in anios:
        df = base_anio(base_usada, a)
        dominio = _dominio(df, ind, desagregacion, filtros, avisos)
        if serie:
            grupos = [(str(a), dominio)]
        elif desagregacion == "nacional":
            grupos = [("Total" if filtros.activos() or ind.tipo == "distribucion" else "Perú", dominio)]
        else:
            grupos = [(g, dominio & df[desagregacion].eq(g)) for g in _grupos(df, desagregacion, dominio)]
        for g, dom in grupos:
            if ind.tipo == "distribucion":
                for cat in ind.categorias:
                    filas.append(_fila(g, estimar(df, ind.columna, dom, categoria=cat), ind.nombre, categoria=cat))
            else:
                filas.append(_fila(g, estimar(df, ind.columna, dom, escala=escala), ind.nombre))
        if con_nacional and desagregacion not in ("nacional", "anio") and ind.tipo != "distribucion":
            nacional = _fila("Total", estimar(df, ind.columna, dominio, escala=escala), ind.nombre)
    tabla = pd.DataFrame(filas)
    avisos += _avisos_de_anios(ind, anios, serie)
    if tabla.referencial.any():
        avisos.append(f"{int(tabla.referencial.sum())} cifra(s) con coeficiente de variación mayor a "
                      f"{CV_REFERENCIAL:.0f} % o menos de {N_MINIMO} casos: úsenlas como referenciales.")
    return Resultado(ind, desagregacion, filtros, tabla, nacional, metodo_de(ind, base_usada, anios), base_usada,
                     tuple(anios), list(dict.fromkeys(avisos)))


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


def _grupos(df, desagregacion, dominio):
    presentes = df.loc[dominio & df[desagregacion].notna(), desagregacion].unique().tolist()
    if desagregacion in ORDEN:
        return [g for g in ORDEN[desagregacion] if g in presentes] + sorted(set(presentes) - set(ORDEN[desagregacion]))
    return sorted(presentes, key=sin_tildes)          # Áncash va después de Amazonas, no al final


def calcular_varios(indicador_ids, desagregacion="nacional", filtros=None, anio=None):
    """Varios indicadores con la misma desagregación. Sin año, todos usan el último año común con dato."""
    if anio is None and desagregacion != "anio" and len(indicador_ids) > 1:
        comunes = set.intersection(*(set(anios_de(i)) for i in indicador_ids))
        anio = max(comunes) if comunes else None
    return [calcular(i, desagregacion, filtros, anio=anio) for i in indicador_ids]


# Código reproducible -------------------------------------------------------------------------------------------------

def codigo_reproducible(res: Resultado):
    """Snippet de pandas que reproduce la cifra principal sin CifraLista (para el anexo metodológico de una tesis)."""
    ind = res.indicador
    lineas = ["import pandas as pd", "",
              f'df = pd.read_parquet("data/{ARCHIVOS[res.base_usada]}.parquet")']
    cond = [] if res.es_serie else [f'(df["anio"] == {res.anio})']
    cond += [f'(df["{k}"] == "{v}")' for k, v in res.filtros.activos().items()]
    if ind.base == "ena" and (res.desagregacion in SOLO_PERSONA_NATURAL or res.filtros.sexo):
        cond.append('df["pequeno_mediano"]')
    col = ind.columna
    if cond:
        lineas.append(f"df = df[{' & '.join(cond)}]")
    if ind.tipo == "distribucion":
        lineas.append(f'df = df[df["{col}"].notna()]')
        por = [] if res.desagregacion == "nacional" else [res.desagregacion]
        lineas.append(f"tabla = df.groupby({por + [col]!r}, observed=True)['factor'].sum()")
        lineas.append(f"tabla = tabla / tabla.groupby(level={0 if por else None!r}).transform('sum') * 100"
                      if por else "tabla = tabla / tabla.sum() * 100")
    else:
        escala = "" if ind.tipo == "media" else " * 100"
        lineas.append(f'df = df[df["{col}"].notna()]')
        f = f'lambda g: (g["{col}"] * g["factor"]).sum() / g["factor"].sum(){escala}'
        if res.desagregacion == "nacional":
            lineas.append(f'valor = (df["{col}"] * df["factor"]).sum() / df["factor"].sum(){escala}')
        else:
            lineas.append(f'tabla = df.groupby("{res.desagregacion}", observed=True).apply({f})')
    return "\n".join(lineas)
