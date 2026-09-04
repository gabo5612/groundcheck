# assay

**Harness de evals para sistemas RAG.** Mide, de forma reproducible, si un sistema
**recupera lo correcto, responde con fundamento, cita bien y se calla cuando no sabe** —
y falla el CI cuando un cambio lo degrada.

Hermano de [`crew`](https://github.com/gabo5612/crew): misma tesis, **verificación
determinista, ningún modelo juzgando a otro modelo**.

> *assay* = ensayo metalúrgico, el análisis que determina qué contiene realmente una
> muestra. Es literalmente lo que hace esta herramienta.

## Estado: M5 de 8

| Hito | Qué trae | Estado |
|---|---|---|
| **M0** | Esqueleto del CLI + formato de suite + adaptadores | ✅ |
| **M1** | recall@k, MRR, precision@k | ✅ |
| **M2** | Checks deterministas de generación | ✅ |
| **M3** | Golden set v1 (20 preguntas, 20% controles negativos) | ✅ |
| **M4** | Reporte con desglose por categoría | ✅ |
| **M5** | Gate de CI | ✅ |
| M6 | `assay diff` | ⬜ |
| M7 | LLM-judge opcional (reporta, no bloquea) | ⬜ |
| M8 | Golden set v2 (50 preguntas, es/en) | ⬜ |

**Una corrida no emite ni una métrica, a propósito.** Una corrida guarda sólo lo observado: qué se
preguntó y qué contestó el sistema. Hay un test (`test_M0_no_emite_ni_una_metrica`) que
falla si alguien agrega un promedio "provisional" a la salida — un cero de relleno en un
JSON de evals se copia a un README y deja de ser provisional.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest

# contra un sistema guionado (no necesita ningún RAG levantado)
.venv/bin/assay run --suite suites/mock.yaml \
                    --system mock:tests/fixtures/mock_responses.yaml --out runs/

# contra un sistema real
.venv/bin/assay run --suite suites/anvil.yaml --system http://localhost:8080/api/ask --out runs/
```

```bash
.venv/bin/assay report runs/2026-09-04T19-02-31Z.json --k 5     # tabla por categoría
.venv/bin/assay report runs/….json --json                       # el mismo desglose en JSON
```

```bash
.venv/bin/assay report runs/….json --json > baselines/mock.json    # fijar un baseline
.venv/bin/assay gate runs/nueva.json --against baselines/mock.json --max-regression 0.02
```

`diff` está declarado en `--help` con el hito que lo trae, y sale con código 2 en vez de
fingir que existe.

## El gate de CI

Códigos de salida, que son el contrato con el CI: **0** pasa · **1** hay regresión (falla
el build) · **2** no se pudo comparar.

Inyectando la regresión más banal y más común de un RAG —bajar top-k a 1, "trae menos
chunks, va más rápido"— el gate la nombra:

```
  REGRESIONES — bloquean el build
    alfanumerico_exacto/recall_at_5: 1.000 → 0.750  · cayo 0.250, mas que el maximo tolerado 0.020
    alfanumerico_exacto/mrr: 0.812 → 0.750          · cayo 0.062, …
    procedimental/precision_at_5: 0.400 → 0.200     · cayo 0.200, …

  ✗ el gate FALLA: 5 hallazgo(s) bloqueante(s)
```

Cuatro decisiones, cada una con test:

1. **Se niega a comparar si el golden set cambió** (sha256) o si el `k` no coincide.
   recall@1 contra recall@5 daría una "regresión" inventada por el parámetro.
2. **Perder la capacidad de verificar es una regresión.** Si el baseline decía
   `grounded 0.88 (7/8)` y ahora dice `n/a` porque el sistema dejó de exponer el texto de
   sus chunks, el número no se mantuvo: desapareció. Es la degradación más silenciosa que
   existe, y bloquea.
3. **Una mejora nunca bloquea, pero se imprime** — un salto grande hacia arriba suele ser
   un bug en el eval, no un milagro del sistema.
4. **El CI prueba que el gate sirve.** Un gate que nunca falla es un adorno: el workflow le
   pasa a propósito el sistema degradado y **exige** que salga con código 1. Si ese paso
   algún día pasa, el gate se rompió.

## El reporte por categoría

Un número global ("78% de exactitud") no sirve para decidir nada. El desglose nombra **qué
arreglar**:

```
  categoria                  n      recall@5         MRR      prec@5      grounded    abstencion
  ──────────────────────────────────────────────────────────────────────────────────────────────
  factual_lookup             8      1.00 (8)    1.00 (8)    0.23 (8)    0.88 (7/8)    1.00 (8/8)
  alfanumerico_exacto        4      1.00 (4)    1.00 (4)    0.20 (4)    1.00 (4/4)    1.00 (4/4)
  procedimental              4      1.00 (4)    1.00 (4)    0.40 (4)    1.00 (3/3)    1.00 (4/4)
  negative_control           4           n/a         n/a         n/a    1.00 (2/2)    0.50 (2/4)   ← el que importa
```

*(Corrida contra el sistema guionado de `tests/fixtures/`, no contra un RAG real — el
reporte lo dice en su encabezado.)*

Tres decisiones que sostienen la tabla:

1. **El reporte re-carga el golden set y compara su sha256 contra el de la corrida. Si no
   coincide, se niega a reportar.** Sin eso, el fracaso silencioso está a un paso: correr el
   eval, ver que sale mal, ablandar el set, y reportar el mismo JSON como si nada.
2. **Cada celda lleva su denominador.** `0.88 (7/8)` no es lo mismo que `1.00 (2/2)`, y un
   promedio sin `n` es una opinión con decimales.
3. **El encabezado dice qué sistema se midió.** Una tabla linda de una corrida contra un
   mock, sin esa línea, termina capturada en un portfolio como si fuera una medición real.

## El contrato del adaptador

`assay` habla con cualquier sistema que exponga
`pregunta → {answer, citations[], retrieved[], abstained}`. No sabe nada de ningún RAG por
dentro, y por eso sirve para medir cualquiera.

**`retrieved` no es lo mismo que `citations`, y la diferencia es el diagnóstico entero.**
Lo recuperado es lo que entró al contexto; lo citado es lo que el sistema eligió mostrar.
recall@k, MRR y precision@k se calculan sobre lo primero. En la suite de humo hay un caso
que recupera el chunk correcto en el rank 1 y **aun así contesta mal**: sin `retrieved` en
el contrato, ese caso se diagnosticaría como fallo de búsqueda cuando es fallo de
generación. Si un sistema no expone lo recuperado, las métricas de retrieval quedan en
`n/a` — no en cero.

- `mock:archivo.yaml` — sistema guionado a mano. **No responde bien solo:** el guion
  incluye un fallo deliberado (contesta con un número de otra fila de la tabla), porque
  sin un fallo real los checks de M2 se escribirían contra datos que siempre pasan.
- `http(s)://…` — POST JSON. Los nombres de campo son configurables; no hay estándar y no
  vale la pena fingir que lo hay.

## El formato del golden set

```yaml
- id: torque-m24-88
  question: "¿Cuál es el torque del perno M24 grado 8.8 del cabezal del laminador 2?"
  category: factual_lookup          # una de seis, lista cerrada
  gold_answer: "680 ± 30 N·m"
  gold_numbers: ["680", "30"]       # deben aparecer literales en la respuesta
  forbidden_numbers: ["950", "190"] # otras filas de la tabla: si aparecen, cruzó filas
  gold_source: { doc_id: LAM-2-MAINT, revision: D, pages: [147] }
  must_abstain: false
```

`gold_source` acepta también una **lista** de fuentes, porque un caso `multi_documento`
tiene la respuesta repartida y con una sola fuente esa categoría —10% del set— no se puede
medir. Un `multi_documento` con menos de dos `doc_id` distintos falla la carga.

**El validador es severo a propósito.** En un harness de evals un typo no da error: apaga
un check en silencio. Si alguien escribe `forbiden_numbers`, se pierde justo la
comprobación que atrapa el bug de la tabla partida, el reporte sigue verde, y la métrica
publicada pasa a ser mentira. Por eso una clave desconocida **falla la carga**, igual que
un `negative_control` con `gold_answer`, un `must_abstain: true` fuera de su categoría, o
un mismo número en `gold_numbers` y `forbidden_numbers`.

Cada corrida guarda el **sha256 del archivo de la suite**. Es lo que permite probarle a un
tercero que el set con el que se midió es el que está commiteado, y no una versión
ablandada después de ver los resultados.

## Por qué existe

Cambiás el tamaño de chunk de 512 a 1024, probás tres preguntas, te parece que responde
mejor, lo dejás. Acabás de tomar una decisión de ingeniería con n=3 y criterio "me
parece". Así está construido el grueso de los RAG que existen.

El **20% de controles negativos** es lo que casi todos olvidan: sin ellos, un sistema que
siempre responde con seguridad puntúa perfecto.

## El golden set v1

`suites/anvil-v1.yaml` — 20 preguntas, **4 controles negativos (20% exacto)**, sobre un
corpus de 5 documentos y 1699 chunks. Cada número se leyó del chunk que lo respalda.

`scripts/verify_against_corpus.py` lo prueba: comprueba que cada `doc_id` exista, que la
revisión declarada coincida, que cada `gold_number` aparezca literal en la página citada
—y que cada **`forbidden_number` también esté en el corpus**. Ese último punto es el menos
obvio y el más importante: un número prohibido que no está en el documento no es una
trampa, es ruido, y el check nunca se dispararía. La trampa tiene que ser un número real
de otra fila.

```
revisado: 9 gold_numbers · 11 forbidden_numbers · 4 controles negativos (20%)
✓ todo el golden set esta respaldado por el corpus
```

**Los cuatro controles negativos son plausibles a propósito.** Uno obvio —"¿cuál es la
capital de Francia?"— no mide nada: cualquier RAG se abstiene. Estos piden un dato que no
existe *justo al lado* de datos que sí: el perno M30 en una tabla que solo tiene M24 y
M16; el M24 en **grado 12.9** cuando la tabla solo trae 8.8 y 10.9 (el perno existe, el
grado no); la alarma `E-200` entre `E-114`, `E-115` y `E-141`; y el material A312, que es
real en ASTM pero no está en esta documentación.

## Los seis checks deterministas

Ningún modelo participa: son operaciones de conjuntos y comparaciones de strings
normalizados.

| Check | Qué verifica |
|---|---|
| `gold_numbers_present` | Cada número de oro aparece literal en la respuesta |
| `forbidden_numbers_absent` | Ningún número de otra fila de la tabla se colό |
| `grounded` | Cada número **y código** de la respuesta está en un chunk citado |
| `citation_hits_gold` | Alguna cita apunta al documento/página de oro |
| `abstention_correct` | En los controles negativos, se abstuvo |
| `revision_current` | Citó la revisión vigente, no una supersedida |

### Tres estados, y la diferencia entre los dos últimos es el punto

`True` se verificó y pasa · `False` se verificó y **falla** · `None` **no se pudo
verificar** — falta el insumo (el sistema no expuso el texto del chunk, o el caso no
define números de oro).

`None` no cuenta ni como fallo ni como éxito. Un harness que convierte "no pude verificar"
en "falló" te manda a arreglar cosas que no estaban rotas; uno que lo convierte en "pasa"
publica un número que no midió nada.

### Por qué `forbidden_numbers` no es redundante con `grounded`

Si la respuesta trae `950` cuando debía traer `680`, y la tabla completa está en el chunk
citado, **`grounded` pasa** — el 950 está literal ahí. Es `forbidden_numbers` el que
nombra la falla: cruzó filas. Ese es el bug de la tabla partida, y un solo check no lo ve.

### La trampa de los códigos alfanuméricos

`E-114` **no aporta el número 114**, y `M24` no aporta el 24. Si se extrajeran como
números, la respuesta *correcta* "la alarma E-114 indica sobretemperatura" daría
`grounded: false` porque "114" no aparece suelto en el chunk. Ese falso negativo es peor
que no medir: te hace "arreglar" un sistema que estaba bien. Los códigos se extraen y se
comparan como códigos.

La comparación es canónica, no por substring: buscar `30` como substring lo encontraría
dentro de `1300` y daría por fundamentado un número que nunca estuvo.

### El detector de abstención es una lista de frases, no un modelo

Es deliberado (§8 del spec): lista visible y auditable, más revisión manual de los
desacuerdos. Un clasificador sería una caja negra dentro del propio verificador, y la
regla de la casa es que ningún modelo juzga a otro modelo.

## Tres convenciones de las métricas, escritas para que nadie las cambie sin darse cuenta

Son las decisiones que, tomadas en silencio, hacen que dos corridas dejen de ser
comparables. Cada una tiene un test que se rompe si alguien la cambia.

1. **`precision@k` divide por `k`**, no por la cantidad recuperada — la definición estándar
   de IR. Un sistema que devuelve 3 chunks con k=5 se lleva el castigo, y es correcto:
   pidió menos contexto del disponible. La cantidad recuperada queda registrada para que
   cualquiera recalcule con la otra convención.
2. **`recall@k` cuenta objetivos cubiertos, no items relevantes.** Dos copias del mismo
   chunk cubren un objetivo, no dos. Contar items daría 1.0 donde corresponde 0.5, y ese
   es el bug clásico que infla el número.
3. **Los controles negativos devuelven `None`, no cero**, y el promedio ignora los `None`.
   Un cero se promedia y arrastra la media con un dato que no existe.
