# Pitch de 3 minutos y video de respaldo

Turno 3 · miércoles 11 de noviembre, ~7:12 p. m. Llegar a las 7:00 con la app abierta en la URL pública **y** en local
(`uv run streamlit run app.py`), y el video listo por si se cae internet.

## Guion (3:00)

**0:00 – 0:30 · El problema** *(sin diapositivas, con la app abierta)*

> «Soy economista en el MIDAGRI y escribo notas técnicas. En mi última nota, sobre el envejecimiento del productor
> agropecuario, tuve que citar notas de prensa del INEI, porque calcular una sola cifra de la Encuesta Nacional
> Agropecuaria toma horas: quince capítulos, seis llaves, factores de expansión. Y si le preguntas a un chatbot, inventa
> la cifra con una cita que parece real. Les pasa a analistas, consultores y a cientos de tesistas: en el repositorio
> nacional hay 644 trabajos con la ENAHO y solo 19 con la ENA.»

**0:30 – 2:30 · Demo en vivo**

1. *(0:30)* Clic en el ejemplo **«¿Qué porcentaje de productores tiene 60 años o más, por departamento?»** → Calcular.
   > «Claude entiende la pregunta y la traduce a una consulta de un catálogo validado: indicador, desagregación,
   > filtros. No calcula nada.»
2. *(0:50)* Señalar el gráfico.
   > «Python calcula con el factor de expansión y el error estándar del diseño muestral. Puno: 54,6 %. Las barras
   > rayadas son cifras referenciales, con coeficiente de variación mayor a 15 %, como pide el INEI.»
3. *(1:10)* Señalar el párrafo y la etiqueta verde.
   > «Claude redacta el párrafo para la nota, y un verificador comprueba que cada número del texto salga del cálculo.»
4. *(1:25)* Abrir la barra lateral, **Validación contra el INEI**.
   > «Diez de diez cifras publicadas por el INEI se reproducen exactas: edad promedio 54,5 años, pobreza 27,6 %.»
5. *(1:40)* Escribir: **«Capacitación y asistencia técnica de las mujeres productoras por región natural»** → Calcular.
   > «Dos indicadores, un filtro y una desagregación, en una sola pregunta.»
6. *(2:00)* **Descargar Word** y abrirlo.
   > «Sale listo para pegar: gráfico, párrafo, cuadro con intervalos de confianza, ficha técnica y el código que
   > reproduce la cifra para el anexo de una tesis.»
7. *(2:20)* Escribir: **«¿Cuánto gana un productor de café?»** → Calcular.
   > «Y cuando no tiene el dato, lo dice. No inventa.»

**2:30 – 3:00 · El negocio**

> «Pagan tesistas, S/ 19 al mes, y analistas y consultores, S/ 49. Cada consulta me cuesta menos de una décima de
> centavo de dólar en IA, así que el margen supera el 90 %. Empiezo vendiendo notas express hechas con CifraLista, de
> S/ 350 a 800, para financiar lo que sigue: más módulos de la ENAHO, series desde 2015 y el Censo por distrito. Usa dos
> herramientas del curso: salidas estructuradas con Claude y Streamlit; y el mismo motor como servidor MCP.
> CifraLista: cifras oficiales, listas para tu nota.»

**Ensayo con cronómetro:** hacerlo 2 veces con el celular en modo cronómetro; si pasa de 3:00, cortar el paso 5.

## Video de respaldo (75 s)

Grabar la pantalla con la herramienta Recortes de Windows (**Win + Mayús + R** → Grabar) o con Clipchamp, con la app en
la URL pública y narrando en vivo.

| Tiempo | Pantalla | Narración |
|---|---|---|
| 0–10 s | Inicio de la app | «CifraLista convierte una pregunta en cifras oficiales de la ENA y la ENAHO, listas para una nota técnica.» |
| 10–30 s | Ejemplo de 60 años por departamento → gráfico | «Claude entiende la pregunta; Python calcula con factores de expansión y marca las cifras referenciales.» |
| 30–45 s | Párrafo con la etiqueta verde | «El párrafo lo redacta la IA y un verificador revisa cada número contra el cálculo.» |
| 45–60 s | Barra lateral: validación 10/10 → Descargar Word | «Diez de diez cifras del INEI se reproducen exactas. Todo sale en Word, con cuadro y ficha técnica.» |
| 60–75 s | Pregunta fuera de alcance | «Y si no tiene el dato, lo dice: no inventa. Tesistas S/ 19, profesionales S/ 49 al mes.» |

Guardar como `docs/video/cifralista_demo.mp4` solo si pesa menos de 25 MB; si pesa más, subirlo a YouTube (no
listado) o a Google Drive con acceso por enlace, y pegar el enlace en el README y en el comentario del issue.

## Comentario para el issue #204 (antes del martes 10, 11:59 p. m.)

```
Nombre: Lory Acosta Carbajal
Startup y one-liner: CifraLista. Hacemos gráficos, párrafos y cuadros con cifras oficiales de la ENA y la ENAHO para analistas públicos, consultores y tesistas del Perú, mediante una IA que entiende la pregunta y un motor que calcula desde los microdatos del INEI, sin inventar ninguna cifra.
Link del demo (URL pública, o "corre en local"): https://cifralista.streamlit.app
Link del repo: https://github.com/loryac21-cyber/cifralista
Herramientas del curso que usa: LLMs con salidas estructuradas (sesión 08, cifralista/interprete.py y redactor.py) y Dashboards con Streamlit (sesión 05, app.py). Extra: MCP (sesión 04, mcp_server.py) y Skills de la ENAHO (sesión 16, scripts/preparar_datos.py).
Video de respaldo: <enlace>
```
