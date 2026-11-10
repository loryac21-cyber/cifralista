"""Una sola puerta a Claude, con dos caminos y salida estructurada en ambos.

1. API de Anthropic (`ANTHROPIC_API_KEY`): el camino de producción, para la URL pública.
2. Claude Code en la misma computadora (`claude -p --json-schema`): usa la sesión iniciada de quien corre la app,
   sin clave de API. Sirve para el demo local y para desarrollar; no se usa en un servidor público.

Si no hay ninguno, `llamar` devuelve None y la app sigue con reglas y plantillas.
"""
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from pydantic import BaseModel

MODELO = os.getenv("CIFRALISTA_MODELO", "claude-haiku-5-5")
PRECIO_ENTRADA, PRECIO_SALIDA = 0.10, 0.50          # Claude Haiku 5.5, US$ por millón de tokens


@dataclass
class Respuesta:
    datos: BaseModel
    via: str                 # "api" | "claude-code"
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float


def claude_code_disponible():
    return os.getenv("CIFRALISTA_CLAUDE_CODE", "1") != "0" and shutil.which("claude") is not None


def camino(api_key=None):
    if api_key or os.getenv("ANTHROPIC_API_KEY"):
        return "api"
    if claude_code_disponible():
        return "claude-code"
    return None


def llamar(sistema, mensaje, esquema: type[BaseModel], api_key=None, max_tokens=2048):
    """Devuelve Respuesta, o None si no hay forma de llamar a Claude. Lanza excepción si la llamada falla."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return _por_api(sistema, mensaje, esquema, api_key, max_tokens)
    if claude_code_disponible():
        return _por_claude_code(sistema, mensaje, esquema)
    return None


def _por_api(sistema, mensaje, esquema, api_key, max_tokens):
    import anthropic
    cliente = anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=45.0)
    r = cliente.messages.parse(
        model=MODELO,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": mensaje}],
        output_config={"effort": "low"},
        output_format=esquema,
    )
    if r.parsed_output is None:
        raise ValueError(f"respuesta sin salida estructurada (stop_reason={r.stop_reason})")
    u = r.usage
    entrada = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    costo = (entrada * PRECIO_ENTRADA + u.output_tokens * PRECIO_SALIDA) / 1e6
    return Respuesta(r.parsed_output, "api", entrada, u.output_tokens, costo)


def _por_claude_code(sistema, mensaje, esquema):
    cmd = [shutil.which("claude"), "-p", "--model", MODELO, "--output-format", "json",
           "--json-schema", json.dumps(esquema.model_json_schema(), ensure_ascii=False),
           "--system-prompt", sistema, "--tools", "", "--no-session-persistence", "--setting-sources", "",
           mensaje]
    # Se corre fuera del proyecto para que Claude Code no cargue CLAUDE.md ni configuraciones locales.
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=tempfile.gettempdir(),
                       timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p terminó con código {r.returncode}: {r.stderr[:300]}")
    salida = json.loads(r.stdout)
    if salida.get("is_error") or salida.get("structured_output") is None:
        raise ValueError(f"Claude Code no devolvió salida estructurada: {str(salida.get('result'))[:300]}")
    u = salida.get("usage", {})
    entrada = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return Respuesta(esquema.model_validate(salida["structured_output"]), "claude-code", entrada,
                     u.get("output_tokens", 0), float(salida.get("total_cost_usd") or 0))
