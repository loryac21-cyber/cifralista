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


def redactar_con_plantilla(resultados: list[Resultado]):
    """Texto determinístico, sin IA: siempre verificable."""
    oraciones, titulo = [], ""
    for h, r in zip(hechos(resultados), resultados):
        u = " años" if r.unidad == "años" else " %"
        nombre = h["indicador"][0].lower() + h["indicador"][1:]
        filtros = r.filtros.texto()
        ambito = f" ({filtros})" if filtros else ""
        if r.indicador.tipo == "distribucion":
            vals = [v for v in h["valores"] if v["grupo"] in ("Total", "Perú")] or h["valores"]
            partes = ", ".join(f"{v['categoria']}: {v['valor']}{u}" for v in vals)
            oraciones.append(f"Según la {h['encuesta']}, la distribución de {nombre}{ambito} es: {partes}.")
            titulo = titulo or r.indicador.nombre
        elif len(h["valores"]) == 1:
            v = h["valores"][0]
            ic = h.get("intervalo_95")
            extra = f" (intervalo de confianza al 95 %: {ic[0]}–{ic[1]}{u})" if ic else ""
            if r.unidad == "años":
                oraciones.append(f"Según la {h['encuesta']}, la {nombre}{ambito} es de {v['valor']} años{extra}.")
            else:
                oraciones.append(f"Según la {h['encuesta']}, el indicador «{h['indicador']}»{ambito} alcanza "
                                 f"el {v['valor']} % del universo de {h['universo']}{extra}.")
            titulo = titulo or f"{h['indicador']}: {v['valor']}{u}"
        else:
            if "mayor" in h:
                oraciones.append(
                    f"Según la {h['encuesta']}, {nombre}{ambito} varía de {h['menor']['valor']}{u} en "
                    f"{h['menor']['grupo']} a {h['mayor']['valor']}{u} en {h['mayor']['grupo']}, una diferencia de "
                    f"{h['diferencia_mayor_menor']}.")
                titulo = titulo or f"{h['mayor']['grupo']} registra el mayor valor: {h['mayor']['valor']}{u}"
            if "total_del_universo" in h:
                oraciones.append(f"El valor para el total es {h['total_del_universo']}{u}.")
    return Redaccion(titulo, " ".join(oraciones), "plantilla")
