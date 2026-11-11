"""Graba un recorrido real de CifraLista (Chrome instalado + Playwright) con subtítulos superpuestos."""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/"
SALIDA = Path(sys.argv[1])
SALIDA.mkdir(parents=True, exist_ok=True)

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


def sub(page, texto, espera=0.0):
    page.evaluate(SUB_JS, texto)
    if espera:
        time.sleep(espera)


def rueda(page, dy, pasos=10, pausa=0.08):
    page.mouse.move(820, 420)
    for _ in range(pasos):
        page.mouse.wheel(0, dy / pasos)
        time.sleep(pausa)


def preguntar(page, texto):
    caja = page.get_by_label("Tu pregunta")
    caja.click()
    caja.fill("")
    caja.type(texto, delay=28)
    page.get_by_role("button", name="Calcular").click()


with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(SALIDA),
                          record_video_size={"width": 1280, "height": 720}, locale="es-PE")
    page = ctx.new_page()
    page.goto(URL)
    page.get_by_text("CifraLista", exact=True).first.wait_for(timeout=60000)
    time.sleep(2.5)
    sub(page, "CifraLista: cifras oficiales de la ENA y la ENAHO, listas para tu nota técnica", 4.5)
    sub(page, "Pregunta de ejemplo: productores de 60 años a más, por departamento", 1.5)
    page.get_by_text("¿Qué porcentaje de productores tiene 60 años o más, por departamento?", exact=True).first.click()
    time.sleep(1.5)
    page.get_by_role("button", name="Calcular").click()
    page.get_by_text("Así entendí tu pregunta").wait_for(timeout=90000)
    time.sleep(1.0)
    sub(page, "Claude entiende la pregunta y la traduce a un indicador del catálogo validado", 1.0)
    rueda(page, 520)
    time.sleep(2.5)
    sub(page, "Python calcula con factores de expansión; las barras rayadas son cifras referenciales (CV > 15 %)", 1.0)
    rueda(page, 420)
    time.sleep(3.0)
    rueda(page, 560)
    sub(page, "Claude redacta el párrafo y un verificador revisa que cada cifra salga del cálculo", 4.5)

    page.mouse.move(820, 300)
    page.mouse.wheel(0, -6000)
    time.sleep(1.0)
    sub(page, "Una pregunta libre, escrita a tu manera", 0.5)
    preguntar(page, "¿Los productores de la selva están más organizados en cooperativas que los de la sierra?")
    page.get_by_text("Así entendí tu pregunta").wait_for(timeout=90000)
    page.wait_for_timeout(1500)
    rueda(page, 560)
    time.sleep(2.0)
    rueda(page, 520)
    sub(page, "Selva 10,3 % frente a sierra 5,1 %: el texto sale listo para la nota", 4.0)
    rueda(page, 700)
    sub(page, "Cuadro con IC 95 % y CV, y descarga en Word con ficha técnica y código reproducible", 1.0)
    try:
        with page.expect_download(timeout=20000):
            page.get_by_role("button", name="Descargar Word").click()
    except Exception:
        pass
    time.sleep(3.0)

    page.mouse.move(820, 300)
    page.mouse.wheel(0, -6000)
    page.mouse.move(130, 450)
    for _ in range(6):
        page.mouse.wheel(0, 90)
        time.sleep(0.1)
    sub(page, "Validación: 10 de 10 cifras iguales a las publicadas por el INEI", 4.0)
    page.mouse.move(130, 450)
    page.mouse.wheel(0, -2000)

    sub(page, "Y si no tiene el dato, lo dice: no inventa", 0.5)
    preguntar(page, "¿Cuánto gana un productor de café?")
    page.get_by_text("fuera del catálogo").wait_for(timeout=90000)
    page.wait_for_timeout(500)
    rueda(page, 380)
    time.sleep(4.0)
    sub(page, "cifralista.streamlit.app · github.com/loryac21-cyber/cifralista · Tesis S/ 19 · Profesional S/ 49 al mes", 4.0)
    video = page.video.path()
    ctx.close()
    nav.close()
    print("VIDEO:", video)
