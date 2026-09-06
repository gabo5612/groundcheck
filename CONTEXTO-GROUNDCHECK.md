# groundcheck — harness de evals para sistemas RAG

**Fecha:** 2026-09-02
**Relación:** cierra el hueco marcado con ❌ explícito en §4 de
`~/Desktop/Gabo/CONTEXTO-AI-PORTFOLIO-CV.md` — *"Evals de RAG (precisión de retrieval,
tasa de alucinación): **falta**"*.
**Sistema bajo prueba:** `~/Desktop/Gabo/shopfloor/CONTEXTO-SHOPFLOOR.md`
**Hermano conceptual:** `crew` — misma tesis: **verificación determinista, ningún modelo
juzgando a otro modelo.**
**Nombre:** *groundcheck* = el chequeo de fundamento (*groundedness*): que cada número y cada
cita de una respuesta esté literal en un chunk recuperado. Es la métrica central de la
herramienta, convertida en nombre. Renombrado desde `assay` el 2026-09-06.

---

## 0. Qué es, en una frase

Un CLI que toma un set de preguntas de oro y mide, de forma reproducible, si un sistema RAG
**recupera lo correcto, responde con fundamento, cita bien y se calla cuando no sabe** — y
falla el CI cuando un cambio lo degrada.

**Se publica como repo propio, junto a `crew`.** Es el artefacto que separa *"monté un RAG"*
de *"sé si mi RAG funciona"*.

---

## 1. El problema

Cambiás el tamaño de chunk de 512 a 1024. Probás tres preguntas. Te parece que responde
mejor. Lo dejás.

**Acabás de tomar una decisión de ingeniería con n=3 y criterio "me parece".** Así está
construido el grueso de los RAG que existen, y por eso casi nadie sabe si el suyo funciona.

### Dos casos reales de lo que pasa sin esto

**Air Canada (2024).** Su chatbot le dijo a un pasajero que podía solicitar la tarifa por
duelo de forma retroactiva. La política real decía lo contrario. El Tribunal de Resolución
Civil de Columbia Británica falló contra la aerolínea. Air Canada argumentó que el chatbot
era *"una entidad legal separada, responsable de sus propios actos"*. El tribunal lo
rechazó: **la empresa responde por lo que dice su sistema.**

**Mata v. Avianca (2023).** Un abogado presentó ante un tribunal federal de Nueva York un
escrito con seis citas de jurisprudencia generadas por ChatGPT. Ninguna existía. Nombres
reales, formato impecable, números de expediente verosímiles, contenido inventado. El juez
Castel impuso sanciones.

Los dos casos son **la misma falla**: una respuesta fluida, con formato correcto, sin
fundamento verificado. En una planta metalúrgica ese mismo error es un procedimiento de
soldadura mal citado o un torque inventado.

---

## 2. Qué mide exactamente

### Sobre el retrieval — operaciones de conjuntos, sin modelos de por medio

| Métrica | Pregunta que responde |
|---|---|
| **Recall@k** | ¿El chunk que contiene la respuesta está entre los k recuperados? |
| **MRR** | ¿En qué posición aparece? |
| **Precision@k** | ¿Cuánta basura entró al contexto? |

### Sobre la generación

| Métrica | Cómo se verifica | Tipo |
|---|---|---|
| **Groundedness numérica** | ¿Cada número/código de la respuesta está literal en un chunk citado? | 🟢 determinista |
| **Exactitud de cita** | ¿El doc/página citado contiene realmente el dato de oro? | 🟢 determinista |
| **Tasa de abstención** | En los controles negativos, ¿se abstuvo? | 🟢 determinista |
| **Vigencia de revisión** | ¿Citó la revisión vigente o una supersedida? | 🟢 determinista |
| **Corrección de respuesta** | Contra la respuesta de oro | 🟡 mixto |
| **Calidad de redacción / matiz** | — | 🔴 LLM-judge |

---

## 3. El golden set

~50 preguntas. **La composición importa más que la cantidad.**

| Categoría | % | Ejemplo | Qué prueba |
|---|---|---|---|
| Lookup factual (número/tabla) | 30% | *"Torque del M24 grado 8.8 del cabezal"* | Chunking estructural (Problema 1 de shopfloor) |
| **Código alfanumérico exacto** | 15% | *"¿Qué es la alarma E-114?"* | Búsqueda híbrida (Problema 2) |
| Procedimental multi-paso | 15% | *"Procedimiento LOTO de la línea de colada"* | Que no se corten los pasos |
| Multi-documento | 10% | *"¿El WPS-014 cumple lo que exige el ITP del cliente?"* | Síntesis entre fuentes |
| **Sin respuesta — control negativo** | **20%** | *"Torque del perno M30 del cabezal"* (no existe) | **Alucinación** |
| Revisión supersedida | 10% | Pregunta cuya respuesta cambió entre Rev B y Rev D | Vigencia (Problema 3) |

> ### El 20% de controles negativos es lo que casi todos olvidan
> Sin ellos, un sistema que **siempre responde con seguridad** puntúa perfecto.
> Con ellos aparece la tasa de alucinación real. Son la métrica más importante del set.

### Formato de una entrada

```yaml
- id: torque-m24-88
  question: "¿Cuál es el torque de apriete del perno M24 grado 8.8 del cabezal del laminador 2?"
  category: factual_lookup
  difficulty: easy
  languages: [es, en]
  gold_answer: "680 ± 30 N·m"
  gold_numbers: ["680", "30"]        # deben aparecer literales en la respuesta
  forbidden_numbers: ["950", "190"]  # las otras filas de la tabla: si aparecen, cruzó filas
  gold_source:
    doc_id: LAM-2-MAINT
    revision: D
    pages: [147]
  must_abstain: false
```

Control negativo:

```yaml
- id: torque-m30-ausente
  question: "¿Cuál es el torque del perno M30 del cabezal del laminador 2?"
  category: negative_control
  must_abstain: true
  gold_answer: null
```

> **`forbidden_numbers` es el detalle que atrapa el bug de la tabla partida.** Si la
> respuesta trae `950` cuando debía traer `680`, no es "una respuesta algo distinta": es
> exactamente la falla del Problema 1 de `shopfloor`, y la métrica la nombra.

---

## 4. La regla de diseño — herencia directa de `crew`

**Primero lo determinista, después lo difuso.**

```
🟢 DETERMINISTA — gratis, reproducible, BLOQUEA el CI
   · recall@k, MRR, precision@k          (operaciones de conjuntos)
   · gold_numbers ⊂ respuesta            (comparación de strings normalizados)
   · forbidden_numbers ⊄ respuesta       (idem)
   · la cita apunta al doc/página de oro (comparación de IDs)
   · se abstuvo en los controles negativos (detector de rechazo)
   · citó la revisión vigente             (comparación de campos)

🔴 LLM-AS-JUDGE — se REPORTA, NO bloquea
   · calidad de redacción, matiz, completitud
   · SIEMPRE publicado junto a su tasa de acuerdo con etiquetas humanas
     sobre una muestra. Un juez sin esa tasa es una opinión con decimales.
```

**Ningún modelo decide si otro modelo aprobó.** Esa distinción, sola, te separa del grueso
de la gente que dice "hago evals".

---

## 5. Interfaz

```bash
# correr una suite contra un sistema
groundcheck run --suite suites/shopfloor.yaml \
          --system http://localhost:8000/ask \
          --out runs/

# reporte legible con desglose POR CATEGORÍA
groundcheck report runs/2026-09-05T10-00.json

# gate de CI: falla si hay regresión contra el baseline
groundcheck gate runs/latest.json \
           --against baselines/main.json \
           --max-regression 0.02

# comparar dos configuraciones (chunk 512 vs 1024, Q4 vs Q8, …)
groundcheck diff runs/chunk512.json runs/chunk1024.json
```

**Contrato del adaptador:** `groundcheck` habla con cualquier sistema que exponga
`pregunta → {respuesta, citas[], abstuvo}`. No conoce nada de `shopfloor` por dentro. Eso lo
hace publicable y reusable, no una utilidad interna.

### El desglose por categoría es el producto

Un número global (*"78% de exactitud"*) no sirve para decidir nada. Lo que se publica es:

```
categoría                n    recall@5   grounded   abstención   
─────────────────────────────────────────────────────────────
factual_lookup          15      —          —           —
alfanumerico_exacto      8      —          —           —
procedimental            7      —          —           —
multi_documento          5      —          —           —
control_negativo        10      n/a       n/a          —      ← el que importa
revision_supersedida     5      —          —           —
```

*(celdas vacías a propósito: se llenan al correrlo. Regla §8 del contexto: no inventar métricas.)*

---

## 6. Los hallazgos que produce este harness

> ⚠️ **Lo que sigue son patrones de falla ilustrativos para explicar qué detecta el sistema.
> NO son mediciones.** Los números reales salen de correrlo.

**1. La mejora que empeora.** Subís el chunk de 512 a 1024. El recall sube —cada chunk
contiene más—. Pero la groundedness **baja**: más texto irrelevante en el contexto es más
superficie para confabular. Sin evals sólo ves *"recupera mejor"* y te quedás con el
cambio malo.

**2. Dónde falla, no sólo que falla.** Migrás de `text-embedding-3-large` (nube) a `bge-m3`
(local). El recall global cae. La tentación es concluir *"el modelo local es peor"* y
volver atrás — **que es abandonar el requisito on-prem entero**. El desglose por categoría
muestra que la caída está concentrada en `alfanumerico_exacto`. El arreglo no es un modelo
más grande: es agregar búsqueda léxica. *Habrías descartado la arquitectura correcta por un
diagnóstico grueso.*

**3. La cuantización que rompe los números.** Bajás Qwen de Q8 a Q4 para que entre en la GPU
disponible. La redacción se mantiene. Los errores de transcripción numérica se multiplican:
el modelo dice 680 donde el documento dice 650. Es **la falla exacta que importa acá**, y es
invisible en cualquier benchmark genérico.

**4. La revisión zombi.** Cargan la Rev E de un manual. El sistema empieza a mezclar Rev D
y Rev E porque las dos están indexadas. La métrica de vigencia lo detecta el mismo día — no
seis meses después, cuando alguien siga un procedimiento obsoleto.

---

## 7. Hitos y criterios de aceptación

| # | Hito | Se acepta cuando |
|---|---|---|
| **M0** | Esqueleto del CLI + formato de suite | `groundcheck run` corre contra un sistema mock y emite JSON |
| **M1** | Métricas de retrieval | recall@k, MRR, precision@k sobre un caso construido a mano cuyo resultado se conoce de antemano |
| **M2** | Checks deterministas de generación | Con una respuesta que trae un número inventado, `grounded` da falso. Con una que trae un `forbidden_number`, también |
| **M3** | Golden set v1 | 20 preguntas, **con el 20% de controles negativos desde el principio** |
| **M4** | Reporte con desglose por categoría | La tabla de §5 se imprime llena, con datos reales de una corrida |
| **M5** | **Gate de CI** | Inyectando a propósito una regresión (p.ej. bajar top-k), el gate **falla el build** |
| **M6** | `groundcheck diff` | Compara dos corridas y nombra qué categoría se movió |
| **M7** | LLM-judge opcional | Se reporta **junto a su tasa de acuerdo** con etiquetas humanas sobre una muestra. Nunca bloquea |
| **M8** | Golden set v2 | 50 preguntas, las 6 categorías cubiertas, multilingüe es/en |

---

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Retro-ajustar el eval para aprobar** | El golden set se congela **antes** de tocar el sistema. Cada cambio al set queda versionado en git con su razón. Un set que cambia junto al sistema no mide nada |
| Etiquetar 50 preguntas es trabajo tedioso | Es el trabajo. Es exactamente lo que nadie hace, y por eso vale. Arrancar con 20 (M3) |
| El detector de abstención da falsos positivos | Empezar con lista de frases + revisión manual de los desacuerdos; no meter un modelo a decidirlo |
| Sobre-ingeniería del LLM-judge | Es M7 y **no bloquea nada**. Si se complica, se corta sin costo |

---

## 9. Por qué los dos juntos

```
groundcheck sin shopfloor  →  un harness sin nada que medir
shopfloor sin groundcheck  →  otro RAG más que "parece que anda"
shopfloor + groundcheck    →  un sistema on-prem CON el número que prueba que funciona
```

Y la diferencia se oye en la entrevista:

| Sin el harness | Con el harness |
|---|---|
| *"Construí un asistente RAG sobre documentación técnica, funciona muy bien."* | *"Construí un asistente RAG on-prem sobre documentación técnica. Estas son sus métricas de retrieval **por categoría de pregunta**, esta su tasa de abstención en controles negativos, y este el gate en CI que impide que un cambio de chunking o de cuantización degrade la exactitud numérica sin que nadie se entere."* |

La primera la dice cualquiera. La segunda no se puede improvisar.

---

## 10. Orden de construcción

**`groundcheck` primero, con corpus chico.** 20 preguntas y unos pocos PDFs, antes de construir
`shopfloor` en serio. Después `shopfloor` se construye contra esas métricas **desde el día uno**.

Al revés se termina retro-ajustando el eval para que el sistema apruebe — el fracaso
clásico y silencioso de este tipo de proyecto, y el que hace que todas las métricas
publicadas dejen de significar algo.
