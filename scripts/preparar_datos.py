"""Prepara las bases livianas de CifraLista a partir de los microdatos públicos del INEI.

    uv run scripts/preparar_datos.py --ena "D:/Base_Datos/ENA/2025" --enaho "../tareas-python/tarea-4/datos/enaho"
    uv run scripts/preparar_datos.py --descargar          # baja los zip del INEI a datos_inei/

Entradas (microdatos del INEI, formato Stata):
  ENA 2025 (código 1036): 19_CAP1100 (productor y su familia), 15_CAP700 (capacitación y asistencia técnica),
                          16_CAP800 (asociatividad), 17_CAP900 (servicios financieros).
  ENAHO 2024 (código 966): módulo 34 (sumaria) y módulo 02 (miembros del hogar).

Salidas en data/ (se suben al repo para que la app corra sin descargar 1 GB):
  ena2025_productores.parquet   una fila por unidad agropecuaria, con FACTOR_PRODUCTOR
  enaho2024_hogares.parquet     una fila por hogar, con factor07 × mieperho (método del INEI para pobreza)
  enaho2024_personas.parquet    una fila por residente habitual, con facpob07

Solo se guardan las columnas que usa el catálogo (sin coordenadas ni identificadores de vivienda) y el script se
detiene si las cifras clave no coinciden con las publicadas por el INEI.
"""
import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
URL_INEI = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/{codigo}-Modulo{modulo}.zip"
ENA_CODIGO, ENA_MODULOS = 1036, {"19_CAP1100": 1911, "15_CAP700": 1907, "16_CAP800": 1908, "17_CAP900": 1909}
ENAHO_CODIGO = 966
LLAVES_ENA = ["ANIO", "CCDD", "CCPP", "CCDI", "NSEGM", "UA"]
LLAVES_ENAHO = ["conglome", "vivienda", "hogar"]

DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
    "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
    "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios", "18": "Moquegua",
    "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes", "25": "Ucayali",
}

# Cifras publicadas por el INEI. Solo se usan para COMPARAR al final; ningún resultado se copia de aquí.
REFERENCIA_INEI = {
    "ENA 2025 · edad promedio del productor (años)": ("ena", "edad", None, 54.5, 0.05),
    "ENA 2025 · productores de 60 años a más (%)": ("ena", "edad_60_mas", None, 37.9, 0.05),
    "ENA 2025 · productores de 15 a 24 años (%)": ("ena", "edad_15_24", None, 0.9, 0.05),
    "ENA 2025 · edad promedio de las productoras (años)": ("ena", "edad", ("sexo", "Mujer"), 55.2, 0.05),
    "ENA 2025 · productores con primaria o menos (%)": ("ena", "hasta_primaria", None, 57.7, 0.05),
    "ENA 2025 · recibió capacitación (%)": ("ena", "capacitacion", None, 7.4, 0.05),
    "ENAHO 2024 · pobreza monetaria (%)": ("hogares", "pobre", None, 27.6, 0.1),
    "ENAHO 2024 · pobreza rural (%)": ("hogares", "pobre", ("area", "Rural"), 39.3, 0.1),
    "ENAHO 2024 · pobreza urbana (%)": ("hogares", "pobre", ("area", "Urbana"), 24.8, 0.1),
    "ENAHO 2024 · pobreza extrema (%)": ("hogares", "pobre_extremo", None, 5.5, 0.1),
}


# Lectura -------------------------------------------------------------------------------------------------------------

def buscar(directorios, nombre):
    """Primer archivo que se llame `nombre` (o un zip que lo contenga) dentro de los directorios dados."""
    for d in directorios:
        for p in Path(d).rglob(nombre):
            return p
    return None


def leer_ena(directorios, base, columnas):
    ruta = buscar(directorios, f"{base}.dta")
    if ruta is None:
        for d in directorios:
            for z in Path(d).rglob(f"{ENA_CODIGO}-Modulo{ENA_MODULOS[base]}.zip"):
                with zipfile.ZipFile(z) as zf:
                    nombre = next(n for n in zf.namelist() if n.lower().endswith(f"{base.lower()}.dta"))
                    ruta = io.BytesIO(zf.read(nombre))
                break
    if ruta is None:
        raise SystemExit(f"No encontré {base}.dta de la ENA 2025 en {directorios}. Usen --descargar o --ena.")
    lector = pd.read_stata(ruta, iterator=True, convert_categoricals=False)
    disponibles = lector.variable_labels()
    usar = [c for c in LLAVES_ENA + ["REGION", "ESTRATO", "FACTOR_PRODUCTOR"] + columnas if c in disponibles]
    if isinstance(ruta, io.BytesIO):
        ruta.seek(0)
    df = pd.read_stata(ruta, columns=usar, convert_categoricals=False)
    for c in ["CCDD", "CCPP", "CCDI"]:
        df[c] = df[c].astype(str).str.strip().str.zfill(2)
    df["NSEGM"] = df["NSEGM"].astype(str).str.strip()
    df["UA"] = df["UA"].astype(str).str.strip()
    print(f"  {base}: {len(df):,} filas")
    return df


def leer_zip_enaho(zip_path, empieza, columnas):
    with zipfile.ZipFile(zip_path) as zf:
        nombres = sorted((n for n in zf.namelist() if Path(n).name.lower().startswith(empieza)
                          and n.lower().endswith(".dta")), key=len)
        if not nombres:
            raise SystemExit(f"No encontré {empieza}*.dta en {zip_path}")
        df = pd.read_stata(io.BytesIO(zf.read(nombres[0])), convert_categoricals=False)
    df.columns = [c.lower() for c in df.columns]
    for c, ancho in {"conglome": 6, "vivienda": 3, "hogar": 2, "codperso": 2, "ubigeo": 6}.items():
        if c in df:
            df[c] = df[c].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(ancho)
    return df[columnas].copy()


def descargar(destino):
    import urllib.request
    destino.mkdir(parents=True, exist_ok=True)
    pedidos = [(ENA_CODIGO, m) for m in ENA_MODULOS.values()] + [(ENAHO_CODIGO, "34"), (ENAHO_CODIGO, "02")]
    for codigo, modulo in pedidos:
        archivo = destino / f"{codigo}-Modulo{modulo}.zip"
        if archivo.exists():
            continue
        url = URL_INEI.format(codigo=codigo, modulo=modulo)
        print(f"Bajando {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=900) as r:
            contenido = r.read()
        if not contenido.startswith(b"PK"):
            raise SystemExit(f"El INEI no devolvió un zip para {url}. Bájenlo con el navegador a {destino}.")
        archivo.write_bytes(contenido)


# ENA 2025 ------------------------------------------------------------------------------------------------------------

def si(serie):
    """1.0 si la respuesta es «Sí» (código 1), 0.0 si es otra respuesta, NaN si no se preguntó."""
    return np.where(serie.isna(), np.nan, (serie == 1).astype(float))


def construir_ena(directorios):
    print("ENA 2025")
    c1100 = leer_ena(directorios, "19_CAP1100", ["P1102", "P1103", "P1104_A", "P1105", "P1106"])
    c700 = leer_ena(directorios, "15_CAP700", ["P142_1", "P142_2", "P142_3", "P701", "P704"])
    c800 = leer_ena(directorios, "16_CAP800", ["P801"])
    c900 = leer_ena(directorios, "17_CAP900", ["P901", "P902", "P905", "P907"])

    prod = c1100[c1100.P1102 == 1].drop(columns=["REGION", "ESTRATO", "FACTOR_PRODUCTOR", "P1102"])
    if prod.duplicated(LLAVES_ENA).any():
        raise SystemExit("Hay más de un productor por unidad agropecuaria en el capítulo 1100.")

    ua = (c700.merge(c800[LLAVES_ENA + ["P801"]], on=LLAVES_ENA, how="left", validate="1:1")
              .merge(c900[LLAVES_ENA + ["P901", "P902", "P905", "P907"]], on=LLAVES_ENA, how="left", validate="1:1")
              .merge(prod, on=LLAVES_ENA, how="left", validate="1:1", indicator=True))

    df = pd.DataFrame({
        "ccdd": ua.CCDD,
        "departamento": ua.CCDD.map(DEPARTAMENTOS),
        "region_natural": ua.REGION.map({1: "Costa", 2: "Sierra", 3: "Selva"}),
        "estrato_diseno": ua.CCDD + "-" + ua.ESTRATO.astype(str).str.strip().str.replace(r"\.0$", "", regex=True),
        "psu": ua.CCDD + ua.CCPP + ua.CCDI + "-" + ua.NSEGM,
        "factor": ua.FACTOR_PRODUCTOR.astype(float),
        "pequeno_mediano": (ua._merge == "both"),
    })
    df["tipo_productor"] = np.where(df.pequeno_mediano, "Pequeño o mediano productor", "Empresa o gran productor")
    df["sexo"] = ua.P1103.map({1: "Hombre", 2: "Mujer"})
    df["edad"] = ua.P1104_A
    df["grupo_edad"] = pd.cut(df.edad, [14, 24, 44, 59, 200], labels=["15-24", "25-44", "45-59", "60 y más"]).astype(str)
    df.loc[df.edad.isna(), "grupo_edad"] = None
    educ = ua.P1105
    df["nivel_educativo"] = np.select([educ <= 4, educ <= 6, educ >= 7], ["Hasta primaria", "Secundaria", "Superior"],
                                      default=None)
    df.loc[educ.isna(), "nivel_educativo"] = None
    df["lengua_materna"] = ua.P1106.map({1: "Quechua", 2: "Aymara", 3: "Otra lengua nativa", 4: "Castellano",
                                         5: "Otra", 6: "Otra", 7: "Otra"})
    agr, pec = ua.P142_1.eq(1), ua.P142_2.eq(1)
    df["tipo_actividad"] = np.select([agr & pec, agr, pec], ["Agrícola y pecuaria", "Solo agrícola", "Solo pecuaria"],
                                     default="No realizó actividad")

    persona = df.pequeno_mediano
    df["mujer"] = np.where(persona, df.sexo.eq("Mujer").astype(float), np.nan)
    df["edad_60_mas"] = np.where(persona, df.edad.ge(60).astype(float), np.nan)
    df["edad_15_24"] = np.where(persona, df.edad.between(15, 24).astype(float), np.nan)
    df["edad_15_29"] = np.where(persona, df.edad.between(15, 29).astype(float), np.nan)
    df["hasta_primaria"] = np.where(persona & educ.notna(), (educ <= 4).astype(float), np.nan)
    df["lengua_originaria"] = np.where(persona & ua.P1106.notna(), ua.P1106.isin([1, 2, 3]).astype(float), np.nan)
    df["capacitacion"] = si(ua.P701)
    df["asistencia_tecnica"] = si(ua.P704)
    df["asociado"] = si(ua.P801)
    df["solicito_credito"] = si(ua.P901)
    df["obtuvo_credito"] = np.where(ua.P901.isna(), np.nan, ua.P902.eq(1).astype(float))
    df["seguro_agrario"] = si(ua.P905)
    df["cuenta_ahorro"] = si(ua.P907)
    df["agricola_y_pecuaria"] = df.tipo_actividad.eq("Agrícola y pecuaria").astype(float)
    print(f"  unidades agropecuarias: {len(df):,} ({persona.sum():,} pequeños y medianos productores)")
    return df


# ENAHO 2024 ----------------------------------------------------------------------------------------------------------

def construir_enaho(directorios):
    print("ENAHO 2024")
    z34 = buscar(directorios, f"{ENAHO_CODIGO}-Modulo34.zip")
    z02 = buscar(directorios, f"{ENAHO_CODIGO}-Modulo02.zip")
    if z34 is None or z02 is None:
        raise SystemExit(f"Faltan {ENAHO_CODIGO}-Modulo34.zip o {ENAHO_CODIGO}-Modulo02.zip en {directorios}.")
    s = leer_zip_enaho(z34, "sumaria", LLAVES_ENAHO + ["ubigeo", "dominio", "estrato", "mieperho", "pobreza",
                                                       "factor07"])
    p = leer_zip_enaho(z02, "enaho01-2024-200", LLAVES_ENAHO + ["codperso", "p203", "p204", "p205", "p206", "p207",
                                                                "p208a", "facpob07"])
    h = pd.DataFrame({
        "conglome": s.conglome, "vivienda": s.vivienda, "hogar": s.hogar,
        "ccdd": s.ubigeo.str[:2],
        "departamento": s.ubigeo.str[:2].map(DEPARTAMENTOS),
        "area": np.where(s.estrato.le(5), "Urbana", "Rural"),
        "region_natural": s.dominio.map({1: "Costa", 2: "Costa", 3: "Costa", 4: "Sierra", 5: "Sierra", 6: "Sierra",
                                         7: "Selva", 8: "Lima Metropolitana"}),
        "estrato_diseno": s.ubigeo.str[:2] + "-" + s.estrato.astype("Int64").astype(str),
        "psu": s.conglome,
        "factor": (s.factor07 * s.mieperho).astype(float),      # expande el hogar a sus miembros (método INEI)
        "pobre": s.pobreza.le(2).astype(float),
        "pobre_extremo": s.pobreza.eq(1).astype(float),
    })
    residente = ((p.p204 == 1) & (p.p205 == 2)) | ((p.p204 == 2) & (p.p206 == 1))
    p = p[residente].merge(h, on=LLAVES_ENAHO, how="left", validate="m:1")
    personas = pd.DataFrame({
        "ccdd": p.ccdd, "departamento": p.departamento, "area": p.area, "region_natural": p.region_natural,
        "estrato_diseno": p.estrato_diseno, "psu": p.psu, "factor": p.facpob07.astype(float),
        "sexo": p.p207.map({1: "Hombre", 2: "Mujer"}),
        "edad": p.p208a,
        "pobre": p.pobre, "pobre_extremo": p.pobre_extremo,
    })
    personas["grupo_edad"] = pd.cut(personas.edad, [-1, 14, 29, 44, 64, 200],
                                    labels=["0-14", "15-29", "30-44", "45-64", "65 y más"]).astype(str)
    h = h.drop(columns=["conglome", "vivienda", "hogar"])
    print(f"  hogares: {len(h):,} · residentes habituales: {len(personas):,}")
    return h, personas


# Validación ----------------------------------------------------------------------------------------------------------

def validar(bases):
    fallas = 0
    print("\nComparación con las cifras publicadas por el INEI")
    for nombre, (base, col, filtro, ref, tol) in REFERENCIA_INEI.items():
        df = bases[base]
        if filtro:
            df = df[df[filtro[0]] == filtro[1]]
        ok = df[col].notna()
        valor = np.average(df.loc[ok, col], weights=df.loc[ok, "factor"])
        valor = valor if col == "edad" else valor * 100
        bien = abs(round(valor, 1) - ref) <= tol
        fallas += not bien
        print(f"  [{'OK' if bien else 'FALLA'}] {nombre}: {valor:.2f} (INEI {ref})")
    return fallas


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ena", nargs="*", default=[str(RAIZ / "datos_inei")], help="carpetas con los .dta o zip de la ENA")
    ap.add_argument("--enaho", nargs="*", default=[str(RAIZ / "datos_inei")], help="carpetas con los zip de la ENAHO")
    ap.add_argument("--descargar", action="store_true", help="bajar los zip del INEI a datos_inei/")
    a = ap.parse_args()
    if a.descargar:
        descargar(RAIZ / "datos_inei")

    ena = construir_ena(a.ena)
    hogares, personas = construir_enaho(a.enaho)
    if validar({"ena": ena, "hogares": hogares, "personas": personas}):
        print("\nERROR: alguna cifra no coincide con el INEI; no se guardan las bases.", file=sys.stderr)
        sys.exit(1)
    salida = RAIZ / "data"
    salida.mkdir(exist_ok=True)
    ena.to_parquet(salida / "ena2025_productores.parquet", index=False)
    hogares.to_parquet(salida / "enaho2024_hogares.parquet", index=False)
    personas.to_parquet(salida / "enaho2024_personas.parquet", index=False)
    for f in sorted(salida.glob("*.parquet")):
        print(f"Guardé {f.relative_to(RAIZ)} ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
