"""Prepara las bases livianas de CifraLista (series 2014-2025) a partir de los microdatos públicos del INEI.

    uv run --group datos scripts/preparar_datos.py --descargar      # baja los zip que falten a datos_inei/
    uv run --group datos scripts/preparar_datos.py --dirs datos_inei D:/Base_Datos/ENA D:/Base_Datos/ENAHO

Busca en las carpetas dadas (y dentro de sus .zip) los archivos de cada año, por su nombre:
  ENA (2014-2019, 2021-2025; en 2020 no hubo ENA): capítulos 700 (capacitación y asistencia técnica),
      800 (asociatividad), 900 (servicios financieros; no existe en 2021) y 1100 (el productor y su familia).
  ENAHO (2014-2024): sumaria-AAAA.dta (módulo 34) y enaho01-AAAA-200.dta (módulo 02, miembros del hogar).
El año de cada archivo sale del código del INEI (p. ej. 922-Modulo1842 = ENA 2023) o de la carpeta, y se
comprueba con la variable ANIO de la ENA.

Salidas en data/ (se suben al repo para que la app corra sin descargar 1 GB):
  ena_productores.parquet   una fila por unidad agropecuaria y año, con su factor de expansión
  enaho_hogares.parquet     una fila por hogar y año, con factor07 × mieperho (método del INEI para pobreza)
  enaho_personas.parquet    una fila por residente habitual y año, con facpob07

Solo se guardan las columnas que usa el catálogo (sin coordenadas ni identificadores de vivienda) y el script se
detiene si las cifras clave no coinciden con las publicadas por el INEI.
"""
import argparse
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
URL_INEI = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/{formato}/{codigo}-Modulo{modulo}.zip"

# Código del INEI de cada año y módulos de los capítulos 700, 800, 900 y 1100 de la ENA.
ENA_MODULOS = {
    2014: (505, (783, 784, 785, 787)), 2015: (506, (801, 802, 803, 805)), 2016: (579, (1135, 1136, 1137, 1139)),
    2017: (615, (1328, 1329, 1330, 1332)), 2018: (650, (1464, 1465, 1466, 1468)),
    2019: (701, (1543, 1544, 1545, 1547)), 2021: (868, (1804, 1805, 1807)), 2022: (844, (1750, 1751, 1752, 1754)),
    2023: (922, (1842, 1843, 1844, 1846)), 2024: (973, (1907, 1908, 1909, 1911)),
    2025: (1036, (1907, 1908, 1909, 1911)),
}
ENAHO_CODIGOS = {2014: 440, 2015: 498, 2016: 546, 2017: 603, 2018: 634, 2019: 687, 2020: 737, 2021: 759,
                 2022: 784, 2023: 906, 2024: 966}
CODIGO_A_ANIO = {c: a for a, (c, _) in ENA_MODULOS.items()} | {c: a for a, c in ENAHO_CODIGOS.items()}

DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
    "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
    "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios", "18": "Moquegua",
    "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes", "25": "Ucayali",
}

# Cifras publicadas por el INEI. Solo se usan para COMPARAR al final; ningún resultado se copia de aquí.
# (base, año, columna, filtro, valor publicado, tolerancia)
REFERENCIA_INEI = {
    "ENA 2025 · edad promedio del productor (años)": ("ena", 2025, "edad", None, 54.5, 0.05),
    "ENA 2025 · productores de 60 años a más (%)": ("ena", 2025, "edad_60_mas", None, 37.9, 0.05),
    "ENA 2025 · productores de 15 a 24 años (%)": ("ena", 2025, "edad_15_24", None, 0.9, 0.05),
    "ENA 2025 · edad promedio de las productoras (años)": ("ena", 2025, "edad", ("sexo", "Mujer"), 55.2, 0.05),
    "ENA 2025 · productores con primaria o menos (%)": ("ena", 2025, "hasta_primaria", None, 57.7, 0.05),
    "ENA 2025 · recibió capacitación (%)": ("ena", 2025, "capacitacion", None, 7.4, 0.05),
    "ENAHO 2024 · pobreza monetaria (%)": ("hogares", 2024, "pobre", None, 27.6, 0.1),
    "ENAHO 2024 · pobreza rural (%)": ("hogares", 2024, "pobre", ("area", "Rural"), 39.3, 0.1),
    "ENAHO 2024 · pobreza urbana (%)": ("hogares", 2024, "pobre", ("area", "Urbana"), 24.8, 0.1),
    "ENAHO 2024 · pobreza extrema (%)": ("hogares", 2024, "pobre_extremo", None, 5.5, 0.1),
    "ENA 2022 · productores de 60 años a más (%)": ("ena", 2022, "edad_60_mas", None, 40.2, 0.05),
} | {
    f"ENAHO {anio} · pobreza monetaria (%)": ("hogares", anio, "pobre", None, valor, 0.05)
    for anio, valor in {2014: 22.7, 2015: 21.8, 2016: 20.7, 2017: 21.7, 2018: 20.5, 2019: 20.2, 2020: 30.1,
                        2021: 25.9, 2022: 27.5, 2023: 29.0}.items()
}

# Carpetas de trabajo (bases derivadas, copias de respaldo, paneles): nunca se leen como fuente oficial.
EXCLUIR = {"bak.stunicode", "output", "input", "do", "do files", "cuadros", "graficos", "resultados", "salida",
           "15-21", "panel_2015-2019", "ingreso", "insumo", "agropecuario", "bases", "programas presupuestales"}
PATRON_ENA = {cap: re.compile(rf"^(\d{{1,2}}_)?cap{cap}\.(dta|sav)$", re.I) for cap in ("700", "800", "900", "1100")}
PATRON_SUMARIA = re.compile(r"^sumaria-(20\d\d)\.dta$", re.I)
PATRON_MIEMBROS = re.compile(r"^enaho01-(20\d\d)-200\.dta$", re.I)


# Búsqueda y lectura ---------------------------------------------------------------------------------------------------

def anio_de_ruta(texto):
    """Año a partir del código del INEI («922-Modulo1842») o, si no hay, del último año que aparezca en la ruta."""
    for codigo in re.findall(r"(\d{3,4})[-_]Modulo", texto, re.I)[::-1]:
        if int(codigo) in CODIGO_A_ANIO:
            return CODIGO_A_ANIO[int(codigo)]
    anios = re.findall(r"(?<!\d)(20[12]\d)(?!\d)", texto)
    return int(anios[-1]) if anios else None


def inventario(directorios):
    """{(tipo, año): (ruta, miembro_zip | None)}. Si hay copias, gana la que está en una carpeta o zip oficial del
    INEI («NNN-ModuloNNNN»): una copia suelta puede haber sido modificada a mano."""
    hallados = {}

    def registrar(nombre, ruta, miembro):
        texto = f"{ruta}/{miembro or ''}"
        oficial = re.search(r"\d{3,4}[-_]Modulo", texto, re.I) is not None
        for cap, patron in PATRON_ENA.items():
            if patron.match(nombre):
                anio = anio_de_ruta(texto)
                if anio:
                    hallados.setdefault((f"ena{cap}", anio), []).append((not oficial, (ruta, miembro)))
        for tipo, patron in (("sumaria", PATRON_SUMARIA), ("miembros", PATRON_MIEMBROS)):
            m = patron.match(nombre)
            if m:
                hallados.setdefault((tipo, int(m.group(1))), []).append((not oficial, (ruta, miembro)))

    for d in directorios:
        for p in sorted(Path(d).rglob("*")):
            if not p.is_file() or {x.lower() for x in p.parts} & EXCLUIR:
                continue
            if p.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(p) as zf:
                        for n in zf.namelist():
                            registrar(Path(n).name, p, n)
                except zipfile.BadZipFile:
                    continue
            else:
                registrar(p.name, p, None)
    return {k: min(v, key=lambda t: t[0])[1] for k, v in hallados.items()}


def leer(fuente, columnas):
    """Lee las columnas pedidas (sin importar mayúsculas) de un .dta o .sav, suelto o dentro de un zip."""
    ruta, miembro = fuente
    nombre = (miembro or ruta.name).lower()
    with tempfile.TemporaryDirectory() as tmp:
        if miembro:
            with zipfile.ZipFile(ruta) as zf:
                archivo = Path(tmp) / Path(miembro).name
                archivo.write_bytes(zf.read(miembro))
        else:
            archivo = ruta
        if nombre.endswith(".sav"):
            import pyreadstat
            _, meta = pyreadstat.read_sav(str(archivo), metadataonly=True)
            reales = {c.upper(): c for c in meta.column_names}
            usar = [reales[c] for c in columnas if c in reales]
            df, _ = pyreadstat.read_sav(str(archivo), usecols=usar, apply_value_formats=False)
        else:
            reales = {c.upper(): c for c in pd.read_stata(archivo, iterator=True).variable_labels()}
            usar = [reales[c] for c in columnas if c in reales]
            df = pd.read_stata(archivo, columns=usar, convert_categoricals=False)
    df.columns = [c.upper() for c in df.columns]
    return df


def texto(serie, ancho=None):
    s = serie.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return s.str.zfill(ancho) if ancho else s


def descargar(destino):
    import urllib.request
    destino.mkdir(parents=True, exist_ok=True)
    pedidos = [("SPSS" if a == 2014 else "STATA", c, m) for a, (c, mods) in ENA_MODULOS.items() for m in mods]
    pedidos += [("STATA", c, m) for c in ENAHO_CODIGOS.values() for m in ("34", "02")]
    for formato, codigo, modulo in pedidos:
        archivo = destino / f"{codigo}-Modulo{modulo}.zip"
        if archivo.exists():
            continue
        url = URL_INEI.format(formato=formato, codigo=codigo, modulo=modulo)
        print(f"Bajando {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=900) as r:
            contenido = r.read()
        if not contenido.startswith(b"PK"):
            raise SystemExit(f"El INEI no devolvió un zip para {url}. Bájenlo con el navegador a {destino}.")
        archivo.write_bytes(contenido)


# ENA ------------------------------------------------------------------------------------------------------------------

LLAVES_VIEJAS = ["CCDD", "CCPP", "CCDI", "CONGLOMERADO", "NSELUA", "UA"]      # 2014-2022
LLAVES_NUEVAS = ["CCDD", "CCPP", "CCDI", "NSEGM", "UA"]                        # 2023-2025 (nuevo diseño muestral)
DISENO = ["ANIO", "REGION", "ESTRATO", "FACTOR", "FACTOR_PRODUCTOR", "P102_1", "P102_2", "P142_1", "P142_2"]
VARIABLES = {"700": ["P701", "P704"], "800": ["P801"], "900": ["P901", "P902", "P905", "P907"],
             "1100": ["P1102", "P1103", "P1104_A", "P1105", "P1106"]}


def si(serie):
    """1.0 si la respuesta es «Sí» (código 1), 0.0 si es otra respuesta, NaN si no se preguntó."""
    return np.where(serie.isna(), np.nan, (serie == 1).astype(float))


def ena_anio(anio, inv):
    caps = {}
    for cap, variables in VARIABLES.items():
        if (f"ena{cap}", anio) in inv:
            todas = LLAVES_VIEJAS + LLAVES_NUEVAS + DISENO + variables
            df = leer(inv[(f"ena{cap}", anio)], list(dict.fromkeys(todas)))
            if "ANIO" in df and pd.to_numeric(df["ANIO"], errors="coerce").dropna().astype(int).ne(anio).any():
                raise SystemExit(f"ENA {anio}: el capítulo {cap} trae otro año en ANIO ({inv[(f'ena{cap}', anio)]}).")
            caps[cap] = df
    if "700" not in caps or "1100" not in caps:
        raise SystemExit(f"ENA {anio}: faltan los capítulos 700 o 1100 (encontré {sorted(caps)}).")
    nuevo = "NSEGM" in caps["700"]
    llaves = LLAVES_NUEVAS if nuevo else LLAVES_VIEJAS
    for df in caps.values():
        for c in llaves:
            df[c] = texto(df[c], 2 if c in ("CCDD", "CCPP", "CCDI") else None)
        for c in set(df.columns) - set(llaves):
            df[c] = pd.to_numeric(df[c], errors="coerce")

    base = caps["700"]
    if base.duplicated(llaves).any():
        raise SystemExit(f"ENA {anio}: hay unidades agropecuarias repetidas en el capítulo 700.")
    ua = base
    for cap in ("800", "900"):
        if cap in caps:
            ua = ua.merge(caps[cap][llaves + VARIABLES[cap]], on=llaves, how="left", validate="1:1")
    c1100 = caps["1100"]
    prod = c1100[c1100.P1102 == 1][llaves + [c for c in VARIABLES["1100"] if c in c1100 and c != "P1102"]]
    if prod.duplicated(llaves).any():
        raise SystemExit(f"ENA {anio}: hay más de un productor por unidad agropecuaria en el capítulo 1100.")
    ua = ua.merge(prod, on=llaves, how="left", validate="1:1", indicator=True)
    for c in VARIABLES["700"] + VARIABLES["800"] + VARIABLES["900"] + VARIABLES["1100"]:
        if c not in ua:
            ua[c] = np.nan                                     # p. ej. la ENA 2021 no tuvo capítulo 900

    factor = ua["FACTOR_PRODUCTOR"] if "FACTOR_PRODUCTOR" in ua else ua["FACTOR"]
    # Estrato del diseño: hasta 2019, el ESTRATO del INEI del marco de lista (empresas, granjas); para el marco de
    # áreas, la ENA 2021-2022 y todo el diseño nuevo, departamento × región natural. El «ESTRATO MUESTRAL» de
    # 2023-2025 es tan fino que la mayoría de estratos tiene un solo segmento y el error estándar saldría subestimado.
    est = ua["ESTRATO"] if "ESTRATO" in ua and not nuevo else pd.Series(np.nan, index=ua.index)
    estrato = pd.Series(np.where(est.notna(), "L" + texto(est.fillna(0)), "R" + texto(ua.REGION.fillna(0))),
                        index=ua.index)
    df = pd.DataFrame({
        "anio": anio,
        "ccdd": ua.CCDD,
        "departamento": ua.CCDD.map(DEPARTAMENTOS),
        "region_natural": ua.REGION.map({1: "Costa", 2: "Sierra", 3: "Selva"}),
        "estrato_diseno": f"{anio}-" + ua.CCDD + "-" + estrato,
        "psu": f"{anio}-" + ua.CCDD + ua.CCPP + ua.CCDI + "-" + (ua.NSEGM if nuevo else ua.CONGLOMERADO),
        "factor": factor.astype(float),
        "pequeno_mediano": (ua._merge == "both"),
    })
    df["tipo_productor"] = np.where(df.pequeno_mediano, "Pequeño o mediano productor", "Empresa o gran productor")
    df["sexo"] = ua.P1103.map({1: "Hombre", 2: "Mujer"})
    edad = ua.P1104_A.where(ua.P1104_A.between(12, 110))
    df["edad"] = edad
    df["grupo_edad"] = pd.cut(edad, [11, 24, 44, 59, 200], labels=["15-24", "25-44", "45-59", "60 y más"]).astype(str)
    df.loc[edad.isna(), "grupo_edad"] = None
    educ = ua.P1105.where(ua.P1105.between(1, 10))
    df["nivel_educativo"] = np.select([educ <= 4, educ <= 6, educ >= 7], ["Hasta primaria", "Secundaria", "Superior"],
                                      default=None)
    df.loc[educ.isna(), "nivel_educativo"] = None
    lengua = ua.P1106.where(ua.P1106.between(1, 7))
    df["lengua_materna"] = lengua.map({1: "Quechua", 2: "Aymara", 3: "Otra lengua nativa", 4: "Castellano",
                                       5: "Otra", 6: "Otra", 7: "Otra"})
    agr = (ua.P142_1 if nuevo else ua.P102_1).eq(1)
    pec = (ua.P142_2 if nuevo else ua.P102_2).eq(1)
    df["tipo_actividad"] = np.select([agr & pec, agr, pec], ["Agrícola y pecuaria", "Solo agrícola", "Solo pecuaria"],
                                     default="No realizó actividad")

    persona = df.pequeno_mediano
    df["mujer"] = np.where(persona & df.sexo.notna(), df.sexo.eq("Mujer").astype(float), np.nan)
    df["edad_60_mas"] = np.where(persona & edad.notna(), edad.ge(60).astype(float), np.nan)
    df["edad_15_24"] = np.where(persona & edad.notna(), edad.between(15, 24).astype(float), np.nan)
    df["edad_15_29"] = np.where(persona & edad.notna(), edad.between(15, 29).astype(float), np.nan)
    df["hasta_primaria"] = np.where(persona & educ.notna(), (educ <= 4).astype(float), np.nan)
    df["lengua_originaria"] = np.where(persona & lengua.notna(), lengua.isin([1, 2, 3]).astype(float), np.nan)
    df["capacitacion"] = si(ua.P701)
    df["asistencia_tecnica"] = si(ua.P704)
    df["asociado"] = si(ua.P801)
    df["solicito_credito"] = si(ua.P901)
    df["obtuvo_credito"] = np.where(ua.P901.isna(), np.nan, ua.P902.eq(1).astype(float))
    df["seguro_agrario"] = si(ua.P905)
    df["cuenta_ahorro"] = si(ua.P907)
    df["agricola_y_pecuaria"] = df.tipo_actividad.eq("Agrícola y pecuaria").astype(float)
    df = df[df.factor.gt(0)].reset_index(drop=True)            # sin factor = no respondió (p. ej. 86 casos en 2015)
    persona = df.pequeno_mediano
    sin_cap = sorted(c for c, v in VARIABLES.items() if c not in caps)
    print(f"  ENA {anio}: {len(df):>6,} unidades agropecuarias, {persona.sum():>6,} pequeños y medianos productores"
          f"{' · sin capítulo ' + ', '.join(sin_cap) if sin_cap else ''}{' · diseño nuevo' if nuevo else ''}")
    return df


# ENAHO ----------------------------------------------------------------------------------------------------------------

LLAVES_ENAHO = ["CONGLOME", "VIVIENDA", "HOGAR"]


def enaho_anio(anio, inv):
    s = leer(inv[("sumaria", anio)], LLAVES_ENAHO + ["UBIGEO", "DOMINIO", "ESTRATO", "MIEPERHO", "POBREZA",
                                                     "FACTOR07"])
    p = leer(inv[("miembros", anio)], LLAVES_ENAHO + ["CODPERSO", "P203", "P204", "P205", "P206", "P207", "P208A",
                                                      "FACPOB07"])
    for df in (s, p):
        for c, ancho in {"CONGLOME": 6, "VIVIENDA": 3, "HOGAR": 2, "CODPERSO": 2, "UBIGEO": 6}.items():
            if c in df:
                df[c] = texto(df[c], ancho)
        for c in set(df.columns) - {"CONGLOME", "VIVIENDA", "HOGAR", "CODPERSO", "UBIGEO"}:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    llaves = [c.lower() for c in LLAVES_ENAHO]
    s.columns, p.columns = [c.lower() for c in s.columns], [c.lower() for c in p.columns]
    h = pd.DataFrame({
        "conglome": s.conglome, "vivienda": s.vivienda, "hogar": s.hogar,
        "anio": anio,
        "ccdd": s.ubigeo.str[:2],
        "departamento": s.ubigeo.str[:2].map(DEPARTAMENTOS),
        "area": np.where(s.estrato.le(5), "Urbana", "Rural"),
        "region_natural": s.dominio.map({1: "Costa", 2: "Costa", 3: "Costa", 4: "Sierra", 5: "Sierra", 6: "Sierra",
                                         7: "Selva", 8: "Lima Metropolitana"}),
        "estrato_diseno": f"{anio}-" + s.ubigeo.str[:2] + "-" + s.estrato.astype("Int64").astype(str),
        "psu": f"{anio}-" + s.conglome,
        "factor": (s.factor07 * s.mieperho).astype(float),      # expande el hogar a sus miembros (método INEI)
        "pobre": s.pobreza.le(2).astype(float),
        "pobre_extremo": s.pobreza.eq(1).astype(float),
    })
    h = h[h.factor.gt(0) & s.pobreza.notna()]
    residente = ((p.p204 == 1) & (p.p205 == 2)) | ((p.p204 == 2) & (p.p206 == 1))
    p = p[residente].merge(h, on=llaves, how="inner", validate="m:1")
    personas = pd.DataFrame({
        "anio": anio, "ccdd": p.ccdd, "departamento": p.departamento, "area": p.area,
        "region_natural": p.region_natural, "estrato_diseno": p.estrato_diseno, "psu": p.psu,
        "factor": p.facpob07.astype(float),
        "sexo": p.p207.map({1: "Hombre", 2: "Mujer"}),
        "edad": p.p208a,
        "pobre": p.pobre, "pobre_extremo": p.pobre_extremo,
    })
    personas["grupo_edad"] = pd.cut(personas.edad, [-1, 14, 29, 44, 64, 200],
                                    labels=["0-14", "15-29", "30-44", "45-64", "65 y más"]).astype(str)
    personas = personas[personas.factor.gt(0)]
    print(f"  ENAHO {anio}: {len(h):>6,} hogares · {len(personas):>7,} residentes habituales")
    return h.drop(columns=llaves), personas


# Validación y guardado ------------------------------------------------------------------------------------------------

def promedio(df, col):
    ok = df[col].notna()
    return np.average(df.loc[ok, col], weights=df.loc[ok, "factor"])


def validar(bases):
    fallas = 0
    print("\nComparación con las cifras publicadas por el INEI")
    for nombre, (base, anio, col, filtro, ref, tol) in REFERENCIA_INEI.items():
        df = bases[base][bases[base].anio == anio]
        if filtro:
            df = df[df[filtro[0]] == filtro[1]]
        valor = promedio(df, col) * (1 if col == "edad" else 100)
        bien = abs(round(valor, 1) - ref) <= tol
        fallas += not bien
        print(f"  [{'OK' if bien else 'FALLA'}] {nombre}: {valor:.2f} (INEI {ref})")
    return fallas


def resumen(ena, hogares):
    print("\nSerie (para revisar a ojo que no haya saltos raros)")
    filas = []
    for anio, g in ena.groupby("anio"):
        filas.append({"año": anio, "edad": promedio(g, "edad"), "60+ %": promedio(g, "edad_60_mas") * 100,
                      "primaria %": promedio(g, "hasta_primaria") * 100, "mujer %": promedio(g, "mujer") * 100,
                      "capacit. %": promedio(g, "capacitacion") * 100, "asoc. %": promedio(g, "asociado") * 100,
                      "crédito %": promedio(g, "obtuvo_credito") * 100 if g.obtuvo_credito.notna().any() else np.nan})
    print(pd.DataFrame(filas).round(1).to_string(index=False))
    pob = hogares.groupby("anio").apply(lambda g: pd.Series({"pobreza %": promedio(g, "pobre") * 100,
                                                             "extrema %": promedio(g, "pobre_extremo") * 100}))
    print(pob.round(1).T.to_string())


def compactar(df):
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype("category")
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dirs", nargs="*", default=[str(RAIZ / "datos_inei")],
                    help="carpetas con los microdatos (.dta/.sav sueltos o en .zip) de la ENA y la ENAHO")
    ap.add_argument("--descargar", action="store_true", help="bajar a datos_inei/ los zip del INEI que falten")
    a = ap.parse_args()
    if a.descargar:
        descargar(RAIZ / "datos_inei")
        a.dirs = list(dict.fromkeys(a.dirs + [str(RAIZ / "datos_inei")]))

    inv = inventario(a.dirs)
    anios_ena = sorted({anio for (t, anio) in inv if t == "ena700"})
    anios_enaho = sorted({anio for (t, anio) in inv if t == "sumaria"} & {anio for (t, anio) in inv if t == "miembros"})
    print(f"ENA: {anios_ena}\nENAHO: {anios_enaho}")
    ena = pd.concat([ena_anio(x, inv) for x in anios_ena], ignore_index=True)
    partes = [enaho_anio(x, inv) for x in anios_enaho]
    hogares = pd.concat([h for h, _ in partes], ignore_index=True)
    personas = pd.concat([p for _, p in partes], ignore_index=True)
    resumen(ena, hogares)
    if validar({"ena": ena, "hogares": hogares, "personas": personas}):
        print("\nERROR: alguna cifra no coincide con el INEI; no se guardan las bases.", file=sys.stderr)
        sys.exit(1)
    salida = RAIZ / "data"
    salida.mkdir(exist_ok=True)
    compactar(ena).to_parquet(salida / "ena_productores.parquet", index=False)
    compactar(hogares).to_parquet(salida / "enaho_hogares.parquet", index=False)
    compactar(personas).to_parquet(salida / "enaho_personas.parquet", index=False)
    for f in sorted(salida.glob("*.parquet")):
        print(f"Guardé {f.relative_to(RAIZ)} ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
