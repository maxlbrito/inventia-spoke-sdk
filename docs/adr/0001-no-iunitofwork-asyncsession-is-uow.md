# 0001 — AsyncSession já é Unit of Work; sem wrapper

Status: Accepted (2026-05-08)

## Context

A versão original do RFC-001 §4.1 (issue [#3](https://github.com/maxlbrito/inventia-spoke-sdk/issues/3)) propunha que o SDK introduzisse um wrapper `IUnitOfWork` em cima da sessão SQLAlchemy, com adapter `SqlAlchemyUnitOfWork` e versão `InMemoryUnitOfWork` para testes. O argumento original ecoava DDD .NET/Java: "Service deve falar em portas; trocar banco vira reescrever adaptadores, não revisar regras".

Inspecionando a stack que os spokes realmente usam — SQLAlchemy 2.0 async — `AsyncSession` **já implementa** Unit of Work:

- Identity map (objetos rastreados por chave primária).
- Change tracking (dirty/new/deleted).
- Flush atrasado até `flush()` / `commit()`.
- Fronteira de transação explícita via `async with session.begin():`.
- `commit()` / `rollback()` no contrato público.

Wrapping `AsyncSession` numa interface seria adicionar uma camada que repete a API embaixo, sem ganho técnico real.

## Alternatives considered

### A) `IUnitOfWork` + `SqlAlchemyUnitOfWork` (rejeitado)

```python
class IUnitOfWork(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def __aenter__(self) -> "IUnitOfWork": ...
    async def __aexit__(self, *exc) -> None: ...

class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession): ...
    async def commit(self): await self.session.commit()
    async def rollback(self): await self.session.rollback()
```

**Por que rejeitado:**
- Repete a API de `AsyncSession` sem adicionar comportamento.
- Argumento "trocar banco" é fraco no nosso contexto: Postgres não vai sair (compliance fiscal BR, multi-region em DOKS, cliente paga).
- `InMemoryUnitOfWork` para testes seria útil, mas o padrão **rollback-per-test** com `AsyncSession` real (transação aberta no setup, `rollback()` no teardown) já entrega isolamento equivalente sem código extra.
- DDD literature pré-data ORMs modernos. `AsyncSession` é a porta; é só nomear assim.

### B) `AsyncSession` direto, mais um helper de fronteira (escolhido)

O SDK não embrulha. O contrato comum entre spokes é:
- **`session_for(principal)`** — context manager que entrega `AsyncSession` já vinculada ao tenant.
- **`BaseService(session, principal)`** — base de service que recebe a sessão por construtor.

Quem precisa de transação explícita usa `async with session.begin():` direto na sessão. Para teste, a fixture clássica de SQLAlchemy (rollback-per-test) cobre.

### C) `IRepository<T>` abstrato (rejeitado fora deste ADR)

Discutido junto, rejeitado pelo mesmo motivo que A. Adicionar `IRepository` para "trocar persistência" é over-engineering quando a única persistência é Postgres. Ver issue de discussão.

## Decision

**Não introduzir `IUnitOfWork`.** A camada do SDK exporta:

- `inventia_spoke_sdk.session_for(principal)` (context manager).
- `inventia_spoke_sdk.BaseService` (parent class).
- `inventia_spoke_sdk.configure_session_resolver(...)` (registry).

O Service recebe `AsyncSession` direta. Transações explícitas via `async with self.session.begin():` quando necessário.

## Consequences

### Positivas

- Menos código no SDK (zero classes-wrapper para manter).
- API do SDK parece "naturalmente Python": qualquer dev SQLAlchemy 2.0 entende sem treinamento.
- Performance: sem layer adicional na hot path de query.
- Testabilidade preservada: rollback-per-test funciona; `inventia_spoke_sdk.testing` exporta helpers.

### Negativas

- Subcasses de `BaseService` ficam acopladas a SQLAlchemy `AsyncSession` por tipo. Se um dia surgisse um spoke não-SQLAlchemy (improvável), a base não serviria. Risco aceito.
- Pessoas que vêm de C#/Java DDD podem estranhar a ausência de `IUnitOfWork`. Mitigação: README + este ADR explicam.

### Compensação adicional

`BaseService` expõe `self.log` (LoggerAdapter com `tenant_id` anexado) e está pronto para ganhar `@traced` decorator (ADR-0003). A fronteira que importa — observabilidade + tenant scope — está coberta sem o wrapper.

## References

- Discussão original: issue [inventia-spoke-sdk#3](https://github.com/maxlbrito/inventia-spoke-sdk/issues/3) (versão 1 vs versão 2).
- RFC-001 §4.1 v2 (2026-05-08) — registro da reversão.
- SQLAlchemy 2.0 docs: [Session Basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html) — explicita que Session é UoW.
- PR #5 — implementação que materializou a decisão.
