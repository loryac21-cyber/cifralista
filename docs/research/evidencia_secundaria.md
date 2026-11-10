# Evidencia secundaria (fuentes públicas)

Recogida el 10/11/2026. No reemplaza las conversaciones: sirve para dimensionar y para saber con quién compite
CifraLista.

## Señales de demanda

| Señal | Dato | Fuente |
|---|---|---|
| Trabajos académicos que usan la ENAHO | **644** registros con «ENAHO» y 610 con «Encuesta Nacional de Hogares» | Búsqueda en [ALICIA (CONCYTEC)](https://alicia.concytec.gob.pe/vufind/Search/Results?lookfor=ENAHO&type=AllFields), 10/11/2026 |
| Trabajos que usan la ENA | **19** registros con «Encuesta Nacional Agropecuaria» | [ALICIA](https://alicia.concytec.gob.pe/vufind/Search/Results?lookfor=%22Encuesta+Nacional+Agropecuaria%22&type=AllFields), 10/11/2026 |
| Tiempo que se va en preparar datos | Los profesionales de datos dedican ~38 % de su tiempo a preparar y limpiar datos | Anaconda, *State of Data Science 2022* (3 493 encuestados) |
| Se venden cursos para procesar la ENAHO | La Escuela del INEI (ENEI) y universidades ofrecen cursos de Stata con microdatos del INEI | [INEI · cursos de Stata](https://m.inei.gob.pe/media/ENEI/cursos_programados/modeloDifusionSTATAbasico_v1.pdf), [PUCP CISEPA · taller ENAHO](https://cisepa.pucp.edu.pe/wp-content/uploads/2023/06/brochure-actulizado-qlab-1_compressed-1.pdf) |
| Los chatbots inventan cifras sin datos | Sin herramientas: 0/10 correctas y, obligado a responder, 3 cifras falsas con citas creíbles; con herramientas: 10/10 | Mi evaluación de la tarea 4 (`tarea-4/evaluacion/comparacion.md`) |
| La IA no sustituye a la encuesta | Encuestados sintéticos se equivocan ~12 puntos en promedio | [Pew Research Center, 30/09/2026](https://www.pewresearch.org/data-labs/2026/09/30/can-ai-stand-in-for-human-survey-takers-not-really/) |
| El dolor en primera persona | Mi nota «Sin relevo en el campo» cita notas de prensa del INEI y deja un «dato pendiente» porque la cifra no estaba publicada | Nota técnica propia (MIDAGRI, 2026) |

**Lectura:** la ENAHO tiene una base grande de usuarios académicos; la ENA está subutilizada (19 frente a 644), aunque
es la fuente principal sobre el productor agropecuario. Hacerla accesible es el diferencial.

## Competencia y alternativas

| Alternativa | Qué hace bien | Qué le falta para una nota técnica |
|---|---|---|
| Stata / R / Python a mano | Control total | Requiere saber programar y conocer el diseño de cada encuesta; horas por cifra |
| Paquetes `enaho` (R), `enahodata` e `inei-microdatos` (Python) | Descargan y leen los módulos | No calculan indicadores ni redactan; siguen exigiendo programar |
| Publicaciones del INEI y REDATAM | Cifras oficiales | Solo los cortes publicados; poco flexibles |
| ChatGPT, Claude o Julius AI (US$ 35–45 al mes) con archivos subidos | Rápidos y flexibles | No conocen factores, estratos ni residentes habituales; pueden inventar cifras |
| Consultores y asesores de tesis | Hacen el trabajo completo | Caros y lentos para una sola cifra |

Fuentes: [`enaho` en CRAN](https://packages.oit.ncsu.edu/cran/web/packages/enaho/index.html),
[`inei-microdatos` en PyPI](https://pypi.org/project/inei-microdatos/), [precios de Julius AI](https://coefficient.io/julius-ai-pricing).

## Lo que no encontramos

No hallamos una encuesta publicada a usuarios de microdatos del INEI sobre sus dificultades, ni un estudio de una
consultora o universidad sobre este mercado. Por eso las 3 conversaciones y el formulario son la evidencia principal.
