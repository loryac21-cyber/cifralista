"""Redacta el párrafo para la nota técnica y verifica que cada cifra del texto salga del cálculo.

Claude recibe solo la tabla ya calculada (y las diferencias ya restadas), escribe un título analítico y un párrafo,
y luego `verificar_cifras` compara cada número del texto con los números permitidos. Si aparece uno que no está en
el cálculo, la app lo marca y ofrece el texto por plantilla, que no usa IA.
"""
import json
import os
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .catalogo import DESAGREGACIONES
from .motor import Resultado

MODELO = os.getenv("CIFRALISTA_MODELO", "claude-haiku-5-5")
# Números que pueden aparecer sin venir del cálculo: años, cortes de edad del INEI, «últimos 12 meses», «95 %».
NUMEROS_LIBRES = {2012, 2022, 2023, 2024, 2025, 2026, 0, 1, 3, 12, 14, 15, 24, 25, 29, 30, 44, 45, 59, 60, 64, 65, 95}


def fmt(x, dec=1):
    """54.52 → «54,5»; 2507033 → «2 507 033» (separadores del INEI)."""
    if x is None or x != x:
        return "s. d."
    s = f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",")


def fmt_valor(x, unidad):
    return f"{fmt(x)} años" if unidad == "años" else f"{fmt(x)} %"


# Hechos que puede usar el redactor ----------------------------------------------------------------------------------

def hechos(resultados: list[Resultado]):
    """Todo lo que el texto puede decir, ya calculado y redondeado. El modelo no hace restas ni promedios."""
    salida = []
    for r in resultados:
        t = r.tabla
        h = {"indicador": r.indicador.nombre, "encuesta": r.indicador.encuesta, "unidad": r.unidad,
             "universo": r.indicador.universo, "desagregacion": r.desagregacion,
             "filtros": r.filtros.activos(), "fuente": r.indicador.fuente}
        if "categoria" in t:
            h["valores"] = [{"grupo": g, "categoria": c, "valor": fmt(v)}
                            for g, c, v in zip(t.grupo, t.categoria, t.valor)]
        else:
            h["valores"] = [{"grupo": g, "valor": fmt(v), "referencial": bool(ref)}
                            for g, v, ref in zip(t.grupo, t.valor, t.referencial)]
            confiables = t[~t.referencial]
            if len(confiables) > 1:
                alto, bajo = confiables.loc[confiables.valor.idxmax()], confiables.loc[confiables.valor.idxmin()]
                h["mayor"] = {"grupo": alto.grupo, "valor": fmt(alto.valor)}
                h["menor"] = {"grupo": bajo.grupo, "valor": fmt(bajo.valor)}
                h["diferencia_mayor_menor"] = fmt(alto.valor - bajo.valor) + (
                    " años" if r.unidad == "años" else " puntos porcentuales")
                if len(confiables) == 2:
                    h["razon_mayor_menor"] = fmt(alto.valor / bajo.valor) if bajo.valor else None
            if r.nacional:
                h["total_del_universo"] = fmt(r.nacional["valor"])
            if len(t) == 1:
                h["intervalo_95"] = [fmt(t.ic_inf.iloc[0]), fmt(t.ic_sup.iloc[0])]
                h["poblacion_expandida"] = fmt(t.N.iloc[0], 0)
                h["poblacion_expandida_millones"] = fmt(t.N.iloc[0] / 1e6, 1)
        salida.append(h)
    return salida


# Verificador ---------------------------------------------------------------------------------------------------------

_NUM = re.compile(r"(?<![\w,])\d{1,3}(?:[  ]\d{3})+(?:,\d+)?|(?<![\w,])\d+(?:,\d+)?")


def _a_float(token):
    return float(token.replace(" ", "").replace(" ", "").replace(",", "."))


def numeros_permitidos(resultados, pregunta=""):
    permitidos = set(NUMEROS_LIBRES)
    for h in hechos(resultados):
        texto = json.dumps(h, ensure_ascii=False)
        permitidos |= {_a_float(n) for n in _NUM.findall(texto)}
    permitidos |= {_a_float(n) for n in _NUM.findall(pregunta)}
    return permitidos


def verificar_cifras(texto, resultados, pregunta=""):
    """Devuelve la lista de números del texto que NO salen del cálculo (vacía = todo verificado)."""
    permitidos = numeros_permitidos(resultados, pregunta)
    return [n for n in _NUM.findall(texto) if _a_float(n) not in permitidos]


# Redacción -----------------------------------------------------------------------------------------------------------

@dataclass
class Redaccion:
    titulo: str
    parrafo: str
    origen: str                          # claude | plantilla
    no_verificadas: list = field(default_factory=list)
    aviso: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0


class Texto(BaseModel):
    titulo: str = Field(description="título analítico del gráfico: dice el hallazgo, máximo 90 caracteres")
    parrafo: str = Field(description="2 a 4 oraciones para una nota técnica")


SISTEMA = """Eres analista de estudios económicos en el Estado peruano y escribes notas técnicas con datos del \
INEI. Recibes cifras YA CALCULADAS en JSON. Escribe:
1) un título analítico (el hallazgo principal, no la descripción del gráfico, máximo 90 caracteres);
2) un párrafo de 2 a 4 oraciones, en español formal y claro, listo para pegar en una nota técnica.

Reglas estrictas:
- Usa solo cifras que estén literalmente en el JSON, con coma decimal y el símbolo % separado por un espacio \
(«37,9 %»). No calcules, no redondees distinto, no restes ni promedies: si necesitas una diferencia, usa \
«diferencia_mayor_menor».
- Si un valor tiene "referencial": true, no lo destaques como hallazgo.
- Describe, no expliques causas: no afirmes por qué ocurre algo.
- Menciona la encuesta y el año en el texto (por ejemplo, «según la ENA 2025»). No pongas la cita de la fuente \
al final: la app la agrega.
- Sin viñetas ni markdown."""


def redactar(resultados: list[Resultado], pregunta="", api_key=None):
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            cliente = anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=45.0)
            r = cliente.messages.parse(
                model=MODELO,
                max_tokens=4096,
                system=SISTEMA,
                messages=[{"role": "user", "content":
                           f"Pregunta del usuario: {pregunta}\n\nCifras calculadas:\n"
                           f"{json.dumps(hechos(resultados), ensure_ascii=False, indent=1)}"}],
                output_config={"effort": "low"},
                output_format=Texto,
            )
            t = r.parsed_output
            if t is None:
                raise ValueError(f"respuesta sin texto (stop_reason={r.stop_reason})")
            malos = verificar_cifras(t.titulo + " " + t.parrafo, resultados, pregunta)
            return Redaccion(t.titulo.strip(), t.parrafo.strip(), "claude", malos,
                             tokens_entrada=r.usage.input_tokens, tokens_salida=r.usage.output_tokens)
        except Exception as e:
            red = redactar_con_plantilla(resultados)
            red.aviso = f"No se pudo usar Claude ({type(e).__name__}); el texto se armó con la plantilla."
            return red
    return redactar_con_plantilla(resultados)


def _sujeto(r):
    """«la edad promedio…», «el porcentaje de productores…», «la pobreza monetaria»."""
    nombre = r.indicador.nombre[0].lower() + r.indicador.nombre[1:]
    if r.indicador.tipo == "media" or r.indicador.base == "enaho":
        return f"la {nombre}"
    return f"el porcentaje de {nombre}"


def _lista(partes):
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def redactar_con_plantilla(resultados: list[Resultado]):
    """Texto determinístico, sin IA: siempre verificable."""
    oraciones, titulo = [], ""
    for k, (h, r) in enumerate(zip(hechos(resultados), resultados)):
        u = " años" if r.unidad == "años" else " %"
        filtros = r.filtros.texto()
        ambito = f" ({filtros})" if filtros else ""
        inicio = f"Según la {h['encuesta']}, " if k == 0 else "Por su parte, "
        sujeto = _sujeto(r)
        if r.indicador.tipo == "distribucion":
            grupos = list(dict.fromkeys(v["grupo"] for v in h["valores"]))
            partes = []
            for g in grupos:
                vals = [v for v in h["valores"] if v["grupo"] == g]
                top = max(vals, key=lambda v: float(v["valor"].replace(",", ".")))
                partes.append((f"en {g.lower()}, " if len(grupos) > 1 else "") + f"el grupo más numeroso es "
                              f"«{top['categoria']}» ({top['valor']}{u})")
            oraciones.append(f"{inicio}en la {r.indicador.nombre.lower()}{ambito}, {_lista(partes)}.")
            titulo = titulo or r.indicador.nombre
        elif len(h["valores"]) == 1:
            v = h["valores"][0]
            ic = h.get("intervalo_95")
            extra = f" (intervalo de confianza al 95 %: {ic[0]}–{ic[1]}{u})" if ic else ""
            verbo = "es de" if r.unidad == "años" else "es"
            oraciones.append(f"{inicio}{sujeto}{ambito} {verbo} {v['valor']}{u}{extra}.")
            titulo = titulo or f"{r.indicador.nombre}: {v['valor']}{u}"
        else:
            if len(h["valores"]) <= 5:
                partes = [f"{v['valor']}{u} en {v['grupo']}" + (" (referencial)" if v["referencial"] else "")
                          for v in h["valores"]]
                oraciones.append(f"{inicio}{sujeto}{ambito} es de {_lista(partes)}.")
            if "mayor" in h:
                rango = (f"en {h['mayor']['grupo']} ({h['mayor']['valor']}{u}) y el más bajo en "
                         f"{h['menor']['grupo']} ({h['menor']['valor']}{u}), una diferencia de "
                         f"{h['diferencia_mayor_menor']}")
                oraciones.append(f"El valor más alto se registra {rango}." if len(h["valores"]) <= 5
                                 else f"{inicio}{sujeto}{ambito} alcanza su valor más alto {rango}.")
                titulo = titulo or f"{h['mayor']['grupo']} registra el valor más alto: {h['mayor']['valor']}{u}"
            if "total_del_universo" in h:
                oraciones.append(f"Para el total, {sujeto} es {h['total_del_universo']}{u}.")
            titulo = titulo or f"{r.indicador.nombre} según {DESAGREGACIONES[r.desagregacion].lower()}"
    texto = " ".join(o[0].upper() + o[1:] for o in oraciones)
    if any(v.get("referencial") for h in hechos(resultados) for v in h["valores"]):
        texto += " Las cifras referenciales tienen un coeficiente de variación mayor a 15 % o menos de 30 casos."
    return Redaccion(titulo, texto, "plantilla")
