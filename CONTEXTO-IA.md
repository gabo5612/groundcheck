# Contexto para IA

> **assay — harness de evals para sistemas RAG**
>
> Mide, de forma reproducible, si un sistema RAG recupera lo correcto, responde con fundamento, cita bien y se calla cuando no sabe — y falla el CI cuando un cambio lo degrada.

Este archivo existe para que un asistente de IA —o una persona con prisa— entienda el
proyecto **completo** sin ir leyendo archivos al azar. El orden de lectura de abajo no es
arbitrario: cada archivo asume lo del anterior.

## 🔗 Abrir con el contexto ya cargado

**[▸ Abrir en ChatGPT con este proyecto explicado](https://chatgpt.com/?q=Quiero%20que%20entiendas%20a%20fondo%20el%20repositorio%20p%C3%BAblico%20https%3A%2F%2Fgithub.com%2Fgabo5612%2Fassay.%0A%0Aassay%20%E2%80%94%20harness%20de%20evals%20para%20sistemas%20RAG%0AMide%2C%20de%20forma%20reproducible%2C%20si%20un%20sistema%20RAG%20recupera%20lo%20correcto%2C%20responde%20con%20fundamento%2C%20cita%20bien%20y%20se%20calla%20cuando%20no%20sabe%20%E2%80%94%20y%20falla%20el%20CI%20cuando%20un%20cambio%20lo%20degrada.%0A%0ALe%C3%A9%20estos%20archivos%20EN%20ESTE%20ORDEN%2C%20porque%20cada%20uno%20asume%20el%20anterior%3A%0A1.%20%60README.md%60%20%E2%80%94%20qu%C3%A9%20es%2C%20el%20estado%20por%20hito%20y%20las%20decisiones%20de%20dise%C3%B1o%0A2.%20%60suites%2Fanvil-v2.yaml%60%20%E2%80%94%20el%20golden%20set%3A%2039%20preguntas%20con%20su%20raz%C3%B3n%20escrita%20en%20el%20encabezado%0A3.%20%60src%2Fassay%2Fchecks.py%60%20%E2%80%94%20los%20seis%20checks%20deterministas%20y%20por%20qu%C3%A9%20%60None%60%20no%20es%20fallo%0A4.%20%60src%2Fassay%2Fnumbers.py%60%20%E2%80%94%20extracci%C3%B3n%20de%20n%C3%BAmeros%3A%20las%205%20reglas%20salieron%20de%20bugs%20reales%0A5.%20%60src%2Fassay%2Fgate.py%60%20%E2%80%94%20el%20gate%20de%20CI%20y%20por%20qu%C3%A9%20perder%20verificabilidad%20es%20una%20regresi%C3%B3n%0A6.%20%60.github%2Fworkflows%2Fci.yml%60%20%E2%80%94%20el%20CI%20que%20exige%20que%20el%20gate%20detecte%20una%20regresi%C3%B3n%20inyectada%0A%0APrest%C3%A1%20especial%20atenci%C3%B3n%20a%20los%20comentarios%20del%20c%C3%B3digo%3A%20explican%20POR%20QU%C3%89%20algo%20se%20hace%20de%20una%20manera%20y%20no%20de%20otra%2C%20y%20casi%20siempre%20hay%20un%20bug%20real%20detr%C3%A1s.%0A%0ACuando%20termines%2C%20respondeme%20estas%20preguntas%20con%20evidencia%20del%20c%C3%B3digo%3A%0A-%20%C2%BFPor%20qu%C3%A9%20%60forbidden_numbers%60%20no%20es%20redundante%20con%20%60grounded%60%3F%0A-%20%C2%BFQu%C3%A9%20pasa%20cuando%20un%20check%20no%20se%20puede%20verificar%2C%20y%20por%20qu%C3%A9%20no%20cuenta%20como%20fallo%3F%0A-%20%C2%BFC%C3%B3mo%20se%20prueba%20que%20el%20gate%20de%20CI%20sirve%2C%20y%20no%20que%20simplemente%20nunca%20falla%3F%0A-%20%C2%BFQu%C3%A9%20defectos%20encontr%C3%B3%20el%20propio%20harness%20al%20medir%20un%20sistema%20real%3F%0A%0ANo%20resumas%20el%20README%20y%20ya.%20Quiero%20que%20puedas%20discutir%20las%20decisiones%20de%20dise%C3%B1o.)**

Ese link lleva el prompt pre-cargado. Si preferís armarlo a mano, pegá esto:

```text
Quiero que entiendas a fondo el repositorio público https://github.com/gabo5612/assay.

assay — harness de evals para sistemas RAG
Mide, de forma reproducible, si un sistema RAG recupera lo correcto, responde con fundamento, cita bien y se calla cuando no sabe — y falla el CI cuando un cambio lo degrada.

Leé estos archivos EN ESTE ORDEN, porque cada uno asume el anterior:
1. `README.md` — qué es, el estado por hito y las decisiones de diseño
2. `suites/anvil-v2.yaml` — el golden set: 39 preguntas con su razón escrita en el encabezado
3. `src/assay/checks.py` — los seis checks deterministas y por qué `None` no es fallo
4. `src/assay/numbers.py` — extracción de números: las 5 reglas salieron de bugs reales
5. `src/assay/gate.py` — el gate de CI y por qué perder verificabilidad es una regresión
6. `.github/workflows/ci.yml` — el CI que exige que el gate detecte una regresión inyectada

Prestá especial atención a los comentarios del código: explican POR QUÉ algo se hace de una manera y no de otra, y casi siempre hay un bug real detrás.

Cuando termines, respondeme estas preguntas con evidencia del código:
- ¿Por qué `forbidden_numbers` no es redundante con `grounded`?
- ¿Qué pasa cuando un check no se puede verificar, y por qué no cuenta como fallo?
- ¿Cómo se prueba que el gate de CI sirve, y no que simplemente nunca falla?
- ¿Qué defectos encontró el propio harness al medir un sistema real?

No resumas el README y ya. Quiero que puedas discutir las decisiones de diseño.
```

## Orden de lectura

| # | Archivo | Por qué |
|---|---|---|
| 1 | `README.md` | qué es, el estado por hito y las decisiones de diseño |
| 2 | `suites/anvil-v2.yaml` | el golden set: 39 preguntas con su razón escrita en el encabezado |
| 3 | `src/assay/checks.py` | los seis checks deterministas y por qué `None` no es fallo |
| 4 | `src/assay/numbers.py` | extracción de números: las 5 reglas salieron de bugs reales |
| 5 | `src/assay/gate.py` | el gate de CI y por qué perder verificabilidad es una regresión |
| 6 | `.github/workflows/ci.yml` | el CI que exige que el gate detecte una regresión inyectada |

## Las preguntas que este proyecto responde

- ¿Por qué `forbidden_numbers` no es redundante con `grounded`?
- ¿Qué pasa cuando un check no se puede verificar, y por qué no cuenta como fallo?
- ¿Cómo se prueba que el gate de CI sirve, y no que simplemente nunca falla?
- ¿Qué defectos encontró el propio harness al medir un sistema real?

## Cómo está escrito este código

Tres cosas que se repiten en todo el repositorio y conviene saber antes de leerlo:

1. **Los comentarios explican el *porqué*, no el *qué*.** Si un comentario dice que algo
   se hace de una manera rara, ahí hay un bug real detrás, casi siempre uno silencioso.
2. **Lo que no se pudo medir se dice, no se rellena.** Un `n/a` es una respuesta; un cero
   de relleno es una mentira que después se copia a un README.
3. **Los tests que importan son los que prueban que la verificación sirve** — no solo que
   el código pasa. Buscá los que inyectan un fallo a propósito y exigen que sea detectado.

---
*Generado el 2026-09-06. Si el proyecto cambió mucho, este archivo puede estar viejo: el
código manda.*
