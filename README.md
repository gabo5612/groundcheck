# assay

**Harness de evals para sistemas RAG.** Mide, de forma reproducible, si un sistema
**recupera lo correcto, responde con fundamento, cita bien y se calla cuando no sabe** —
y falla el CI cuando un cambio lo degrada.

Hermano de [`crew`](https://github.com/gabo5612/crew): misma tesis, **verificación
determinista, ningún modelo juzgando a otro modelo**.

> *assay* = ensayo metalúrgico, el análisis que determina qué contiene realmente una
> muestra. Es literalmente lo que hace esta herramienta.

## Estado: M0 de 8

| Hito | Qué trae | Estado |
|---|---|---|
| **M0** | Esqueleto del CLI + formato de suite + adaptadores | ✅ |
| M1 | recall@k, MRR, precision@k | ⬜ |
| M2 | Checks deterministas de generación | ⬜ |
| M3 | Golden set v1 (20 preguntas, 20% controles negativos) | ⬜ |
| M4 | Reporte con desglose por categoría | ⬜ |
| M5 | Gate de CI | ⬜ |
| M6 | `assay diff` | ⬜ |
| M7 | LLM-judge opcional (reporta, no bloquea) | ⬜ |
| M8 | Golden set v2 (50 preguntas, es/en) | ⬜ |

**M0 no emite ni una métrica, a propósito.** Una corrida guarda sólo lo observado: qué se
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

`report`, `gate` y `diff` están declarados en `--help` con el hito que los trae, y salen
con código 2 en vez de fingir que existen.

## El contrato del adaptador

`assay` habla con cualquier sistema que exponga `pregunta → {answer, citations[], abstained}`.
No sabe nada de ningún RAG por dentro, y por eso sirve para medir cualquiera.

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
