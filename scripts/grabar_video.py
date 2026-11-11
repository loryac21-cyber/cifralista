"""Graba el video de respaldo de CifraLista con narración de voz sintética.

1. Genera la narración con una voz neuronal (Microsoft Edge TTS, es-PE-CamilaNeural) y mide cada tramo.
2. Graba un recorrido real de la app local (Chrome + Playwright); cada tramo dura lo que dura su narración.
3. Coloca cada audio en el instante en que empezó su tramo y une audio y video en un MP4 (H.264 + AAC).

Requisitos: la app corriendo en http://127.0.0.1:8765 y `playwright install ffmpeg`.
Uso: uv run --no-project --with playwright --with edge-tts --with imageio-ffmpeg python scripts/grabar_video.py <carpeta>
"""
import asyncio
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/"
VOZ = "es-PE-CamilaNeural"
VELOCIDAD = "+6%"
PAUSA = 0.35  # silencio entre tramos (s)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SALIDA = Path(sys.argv[1]).resolve()
SALIDA.mkdir(parents=True, exist_ok=True)

# (clave, texto que se lee, subtítulo en pantalla). En el texto leído algunos nombres van escritos como se
# pronuncian en el Perú («Clod», «Inéi», «Ena», «Enaho»); el subtítulo conserva la grafía normal.
TRAMOS = [
    ("intro", "Esta es CifraLista: convierte una pregunta en cifras oficiales de la Ena y la Enaho, "
              "listas para una nota técnica o una tesis.",
     "CifraLista: cifras oficiales de la ENA y la ENAHO, listas para tu nota técnica"),
    ("ejemplo", "Primero, un ejemplo: productores de sesenta años o más, por departamento.",
     "Pregunta de ejemplo: productores de 60 años a más, por departamento"),
    ("entiende", "Clod entiende la pregunta y elige un indicador de un catálogo validado. "
                 "La inteligencia artificial no calcula.",
     "Claude entiende la pregunta y elige un indicador del catálogo validado"),
    ("grafico", "Python calcula desde los microdatos, con factores de expansión. Las barras rayadas son cifras "
                "referenciales: su coeficiente de variación supera el quince por ciento.",
     "Python calcula con factores de expansión; las barras rayadas son referenciales (CV > 15 %)"),
    ("verifica", "Clod redacta el párrafo, y un verificador comprueba que cada número salga del cálculo.",
     "Claude redacta y un verificador revisa que cada cifra salga del cálculo"),
    ("libre", "Ahora, una pregunta a mi manera: ¿los productores de la selva están más organizados en "
              "cooperativas que los de la sierra?",
     "Una pregunta libre, escrita a tu manera"),
    ("respuesta", "En la selva, el diez coma tres por ciento de los productores está asociado; en la sierra, "
                  "solo el cinco coma uno por ciento.",
     "Selva 10,3 % frente a sierra 5,1 %: el texto sale listo para la nota"),
    ("word", "Sale con cuadro, intervalos de confianza y descarga en Word, con ficha técnica y el código "
             "que reproduce la cifra.",
     "Cuadro con IC 95 % y CV; Word con ficha técnica y código reproducible"),
    ("validacion", "Diez de diez cifras publicadas por el Inéi se reproducen exactas.",
     "Validación: 10 de 10 cifras iguales a las publicadas por el INEI"),
    ("cafe", "Y si le pregunto algo que no está en los datos, como cuánto gana un productor de café, "
             "lo dice. No inventa.",
     "Si no tiene el dato, lo dice: no inventa"),
    ("cierre", "CifraLista: cifras oficiales, listas para tu nota.",
     "Pruébala en cifralista.streamlit.app"),
]


# ---------- 1. Narración ----------
async def _sintetizar():
    for clave, texto, _ in TRAMOS:
        await edge_tts.Communicate(texto, VOZ, rate=VELOCIDAD).save(str(SALIDA / f"{clave}.mp3"))


def duracion_wav(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


asyncio.run(_sintetizar())
DUR = {}
for clave, _, _ in TRAMOS:
    wav = SALIDA / f"{clave}.wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(SALIDA / f"{clave}.mp3"),
                    "-ar", "48000", "-ac", "1", str(wav)], check=True)
    DUR[clave] = duracion_wav(wav)
print("Narración:", {k: round(v, 1) for k, v in DUR.items()}, f"total {sum(DUR.values()):.1f}s")
SUBS = {clave: sub for clave, _, sub in TRAMOS}

# ---------- 2. Grabación ----------
SUB_JS = """(texto) => {
  let d = document.getElementById('sub-cifralista');
  if (!d) {
    d = document.createElement('div'); d.id = 'sub-cifralista';
    Object.assign(d.style, {position:'fixed', left:'50%', bottom:'28px', transform:'translateX(-50%)', zIndex: 99999,
      background:'rgba(13,54,107,0.92)', color:'#fff', font:'600 22px Inter, Segoe UI, sans-serif',
      padding:'12px 22px', borderRadius:'10px', maxWidth:'1050px', textAlign:'center', lineHeight:'1.35',
      boxShadow:'0 4px 18px rgba(0,0,0,.25)'});
    document.body.appendChild(d);
  }
  d.textContent = texto; d.style.display = texto ? 'block' : 'none';
}"""
MARCAS = {}


def rueda(page, dy, pasos=10, pausa=0.08, x=820, y=420):
    page.mouse.move(x, y)
    for _ in range(pasos):
        page.mouse.wheel(0, dy / pasos)
        time.sleep(pausa)


def arriba(page):
    page.mouse.move(820, 300)
    page.mouse.wheel(0, -8000)
    time.sleep(0.6)


def preguntar(page, texto):
    caja = page.get_by_label("Tu pregunta")
    caja.click()
    caja.fill("")
    caja.type(texto, delay=26)
    page.get_by_role("button", name="Calcular").click()


def tramo(page, clave, durante=None, extra=0.0):
    """Muestra el subtítulo, marca el inicio del audio y espera a que termine la narración."""
    inicio = time.time()
    MARCAS[clave] = inicio - T0
    page.evaluate(SUB_JS, SUBS[clave])
    if durante:
        durante()
    falta = DUR[clave] + PAUSA + extra - (time.time() - inicio)
    if falta > 0:
        time.sleep(falta)


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(SALIDA),
                          record_video_size={"width": 1280, "height": 720}, locale="es-PE")
    page = ctx.new_page()
    T0 = time.time()
    page.goto(URL)
    page.get_by_text("CifraLista", exact=True).first.wait_for(timeout=60000)
    page.get_by_text("10/10", exact=True).first.wait_for(timeout=60000)  # métricas ya dibujadas
    page.get_by_role("button", name="Calcular").wait_for(timeout=60000)
    time.sleep(2.0)
    RECORTE = time.time() - T0 - 0.5  # se descarta la pantalla en blanco del inicio

    tramo(page, "intro")

    def ejemplo():
        time.sleep(0.6)
        page.get_by_text("¿Qué porcentaje de productores tiene 60 años o más, por departamento?",
                         exact=True).first.click()
        time.sleep(0.7)
        page.get_by_role("button", name="Calcular").click()
        page.get_by_text("Así entendí tu pregunta").wait_for(timeout=90000)
    tramo(page, "ejemplo", ejemplo)
    tramo(page, "entiende", lambda: (time.sleep(1.2), rueda(page, 520)))
    tramo(page, "grafico", lambda: rueda(page, 420))
    tramo(page, "verifica", lambda: rueda(page, 560))

    arriba(page)

    def libre():
        preguntar(page, "¿Los productores de la selva están más organizados en cooperativas que los de la sierra?")
        page.get_by_text("Así entendí tu pregunta").wait_for(timeout=90000)
    tramo(page, "libre", libre)
    page.wait_for_timeout(500)
    tramo(page, "respuesta", lambda: (rueda(page, 560), time.sleep(0.5), rueda(page, 520)))

    def word():
        rueda(page, 700)
        try:
            with page.expect_download(timeout=20000):
                page.get_by_role("button", name="Descargar Word").click()
        except Exception:
            pass
    tramo(page, "word", word)

    arriba(page)
    tramo(page, "validacion", lambda: rueda(page, 540, pasos=6, pausa=0.1, x=130, y=450))
    page.mouse.move(130, 450)
    page.mouse.wheel(0, -2000)

    def cafe():
        preguntar(page, "¿Cuánto gana un productor de café?")
        page.get_by_text("fuera del catálogo").wait_for(timeout=90000)
        page.wait_for_timeout(400)
        rueda(page, 380)
    tramo(page, "cafe", cafe)
    tramo(page, "cierre", extra=1.5)
    FIN = time.time() - T0
    video_crudo = page.video.path()
    ctx.close()
    nav.close()

# ---------- 3. Mezcla y unión ----------
claves = [c for c, _, _ in TRAMOS]
entradas, filtros = [], []
for i, c in enumerate(claves):
    entradas += ["-i", str(SALIDA / f"{c}.wav")]
    retraso = int(round((MARCAS[c] - RECORTE) * 1000))
    filtros.append(f"[{i + 1}:a]adelay={retraso}:all=1[a{i}]")
mezcla = "".join(f"[a{i}]" for i in range(len(claves)))
filtros.append(f"{mezcla}amix=inputs={len(claves)}:normalize=0:duration=longest,"
               f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad[voz]")
final = SALIDA / "cifralista_demo.mp4"
subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{RECORTE:.2f}", "-t", f"{FIN - RECORTE:.2f}",
                "-i", str(video_crudo), *entradas,
                "-filter_complex", ";".join(filtros), "-map", "0:v", "-map", "[voz]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
(SALIDA / "marcas.json").write_text(json.dumps({"recorte": RECORTE, "fin": FIN, "marcas": MARCAS,
                                                "duraciones": DUR}, indent=2), encoding="utf-8")
print(f"VIDEO: {final}  ({FIN - RECORTE:.1f}s, {final.stat().st_size / 1e6:.1f} MB)")
