# 0003 — OpenTelemetry helpers como opt-in extra

Status: Accepted (2026-05-09)

## Context

RFC-001 §4.2 (issue [#4](https://github.com/maxlbrito/inventia-spoke-sdk/issues/4)) prioriza tracing distribuído com `trace_id` único cobrindo Hub → Spoke API → arq worker. Os spokes do Inventia precisam disso para debugar incidentes fiscais ("cliente diz que NFe sumiu") em minutos, não em horas correlacionando logs em 3 processos.

A pergunta é **onde** essa instrumentação vive:

1. Em cada spoke (drift entre spokes, código repetido).
2. Como dependência **obrigatória** do SDK (todos os spokes pagam custo OTEL mesmo sem usar).
3. Como dependência **opt-in** do SDK (spokes que querem ligam, os outros não pagam).

OpenTelemetry traz dependências pesadas (~10MB de wheels: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, FastAPI/httpx/SQLAlchemy instrumentations). Forçar isso em todo spoke é custo desproporcional para um spoke que ainda não tem volume de tráfego que justifique tracing.

## Decision

Helpers OTEL vivem em `inventia_spoke_sdk.telemetry`. As dependências OTEL são **opcionais**, expostas via extra `[otel]`:

```toml
[project.optional-dependencies]
otel = [
    "opentelemetry-api>=1.27",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.48b0",
]
```

Spokes que querem usam:
```toml
"inventia-spoke-sdk[otel] @ git+...@v0.5.x"
```

### Comportamento sem o extra

`inventia_spoke_sdk.telemetry._compat.HAS_OTEL` indica se OTEL está instalado. Quando `False`:

- `setup_otel(...)` → retorna `False`, log info "OTEL extras not installed".
- `@traced` → passthrough zero-cost (retorna a função original).
- `@traced_arq_job` → idem.
- `enqueue_with_trace(pool, fn, *args, **kwargs)` → encaminha para `pool.enqueue_job(...)` sem injetar `_otel_carrier`.

Isso significa que spokes podem **decorar Service methods com `@traced` sem instalar o extra**. Pagam zero. Quando algum cliente exigir tracing, basta bumpar a dep para `[otel]` e ligar `setup_otel`.

### Helpers exportados

| Helper | Função |
|---|---|
| `setup_otel(service_name, ...)` | Idempotente. Lê `OTEL_*` env vars; auto-instrumenta FastAPI / httpx / SQLAlchemy. |
| `shutdown_otel()` | Flush + reset (graceful stop, testes). |
| `@traced` | Decorator para métodos `BaseService`. Span `<Class>.<method>`, attrs `inventia.tenant_id` / `user_id` / `client_id`. |
| `enqueue_with_trace(pool, name, *a, **kw)` | Drop-in para `pool.enqueue_job` que injeta W3C `traceparent` em `_otel_carrier` kwarg. |
| `@traced_arq_job` | Worker-side. Pop `_otel_carrier`, restaura contexto, abre span `arq.job <name>`. |

## Alternatives considered

### A) OTEL como dependência obrigatória do SDK (rejeitado)

Mais simples (sem `HAS_OTEL` guard), mas força ~10MB de deps em todo spoke. Spokes em fase pré-prod (ex: agente-fiscal piloto) pagariam custo sem benefício.

### B) OTEL fora do SDK, em pacote separado `inventia-otel-helpers` (rejeitado)

Limpa, mas dobra o número de pacotes a manter. SDK perde a propriedade "tudo que o spoke compartilha está aqui".

### C) `[otel]` extra (escolhido)

Convenção Python idiomática. Custo zero quando não usado. Trivial para ligar.

## Consequences

### Positivas

- Spokes pré-prod não pagam custo de OTEL.
- Spokes que querem tracing têm wiring de 3 linhas:
  ```python
  setup_otel(service_name="md-api", environment="production",
             otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
  ```
- `@traced` pode ser adotado livremente em código que pode ou não ter OTEL instalado — fica como documentação da intenção, vira span quando o extra estiver presente.
- Trace propagation Hub → Spoke API → arq worker funciona end-to-end (ver teste de propagação em `tests/test_telemetry.py`).

### Negativas

- Lógica `HAS_OTEL` no SDK: dois caminhos a manter.
- Quem instala o spoke sem `[otel]` e espera ver spans, não vê. Mitigação: log info no `setup_otel(...)` quando o extra não está presente.

### Cuidado operacional

- Sampling: default `1.0` (todas as traces). Em produção, ajustar via `OTEL_TRACES_SAMPLER_ARG` env var para evitar custo de armazenamento no backend OTEL.
- PII: spans capturam `inventia.tenant_id` / `user_id`, mas **não** capturam payloads. Garantir que isso continue assim em qualquer evolução do `@traced`.

## References

- PR #6 — implementação OTEL completa, 10 testes (no-OTEL passthrough + with-OTEL roundtrip).
- `inventia_spoke_sdk/telemetry/` — código.
- `inventia_spoke_sdk/telemetry/arq_propagation.py` — implementa propagação por queue (W3C traceparent via `_otel_carrier` kwarg).
- master-data PR #151 — primeiro consumidor real do extra.
