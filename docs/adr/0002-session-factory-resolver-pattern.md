# 0002 — SessionFactoryResolver pattern para multi-tenant

Status: Accepted (2026-05-08)

## Context

Antes do v0.5.0, cada spoke implementava por conta própria a função `_session_for(principal)` para resolver tenant → DB. No master-data:

```python
async def _session_for(principal: SpokePrincipal):
    ctx = await fetch_spoke_context(principal.access_token, str(principal.tenant_id))
    await ensure_schema(ctx.account_id, ctx.db_url)
    acc_engine = await get_engine(ctx.account_id, ctx.db_url)
    return acc_engine.session_factory, ctx
```

Esse mesmo bloco aparecia copiado em **4 módulos** (`api/companies.py`, `api/products.py`, `api/imports.py`, `api/jobs.py`). Outros spokes (outbound-nfe, agente-fiscal, etc) replicariam o padrão, cada um implementando do seu jeito. Sintomas:

- Drift entre spokes: pequenas variações em cache TTL, error mapping, sslmode, etc.
- Onboarding caro: cada spoke novo precisa entender o contrato de Hub → DB.
- Bug fix em isolamento multi-tenant exige varrer N repositórios.

## Problem

Cada spoke tem **liberdade legítima** de escolher como resolver tenant → DB:

- **master-data** usa Hub round-trip para obter `db_url` por account, com pool de engines cached.
- **outbound-nfe** pode usar schema-per-tenant numa única DB.
- Um spoke futuro pode usar shared-DB com filtro `tenant_id` em todas as tabelas.

O SDK **não pode** hardcodar nenhuma dessas estratégias. Ao mesmo tempo, o SDK **deve** garantir que o ponto de entrada seja o mesmo em todos os spokes — `session_for(principal)`.

## Decision

Adotar o padrão **resolver registrável**:

1. SDK expõe `SessionFactoryResolver` (Protocol):
   ```python
   class SessionFactoryResolver(Protocol):
       async def __call__(
           self, principal: SpokePrincipal
       ) -> async_sessionmaker[AsyncSession]: ...
   ```

2. Spoke implementa o resolver na sua linguagem de domínio (Hub call, schema, engine pool, ...) e registra no startup:
   ```python
   from inventia_spoke_sdk import configure_session_resolver

   async def my_resolver(principal):
       ctx = await fetch_spoke_context(principal.access_token, str(principal.tenant_id))
       await ensure_schema(ctx.account_id, ctx.db_url)
       return (await get_engine(ctx.account_id, ctx.db_url)).session_factory

   configure_session_resolver(my_resolver)
   ```

3. SDK expõe o ponto de uso uniforme:
   ```python
   from inventia_spoke_sdk import session_for

   async with session_for(principal) as session:
       ...
   ```

`session_for` chama o resolver registrado, abre `factory()`, faz `async with`, fecha no exit.

## Alternatives considered

### A) SDK hardcoda Hub round-trip (rejeitado)

Mais simples no master-data, mas amarraria todos os spokes ao protocolo Hub específico. Fere o princípio de não decidir como cada spoke resolve.

### B) Cada spoke continua com `_session_for` próprio (rejeitado)

Evita acoplamento, mas perpetua o drift e a duplicação.

### C) Resolver registrável (escolhido)

Compromisso: SDK enforce o **contrato** (`session_for(principal) → AsyncSession`); spoke decide a **implementação**.

## Consequences

### Positivas

- 1 linha em cada spoke para registrar (`configure_session_resolver(my_resolver)`).
- Spokes existentes migram cortando o `_session_for` local e plugando o resolver.
- Spokes novos só precisam aprender o contrato `principal → async_sessionmaker`.
- Helpers FastAPI (`session_dep_for`) e arq (`session_for_job`) ficam viáveis no SDK porque o ponto de uso é uniforme.
- Cross-tenant isolation testável centralmente: o SDK pode oferecer `per_principal_resolver` em testing utilities.

### Negativas

- Estado global mutável (`_resolver: SessionFactoryResolver | None`). Aceito porque:
  - É 1 setup por processo, idempotente.
  - `reset_session_resolver()` existe para isolar testes.
  - O alternative (passar o resolver explicitamente em cada chamada) seria muito verboso.
- Spoke esquecer de chamar `configure_session_resolver` → `RuntimeError("No SessionFactoryResolver configured")` no primeiro request. Mitigação: mensagem de erro auto-explicativa + recomendação no README de chamar no module-import-time.

## Implementation notes

- O resolver é `async` para suportar Hub round-trips e Alembic upgrades (lazy).
- O resolver retorna `async_sessionmaker`, **não** `AsyncSession`. Permite reuso do engine pool entre requests do mesmo tenant.
- `session_for` faz `async with factory() as session: yield session` — abre nova sessão por chamada, fecha no exit. Mesmo ciclo de vida que o legado `async with Session() as db:`.

## References

- PR #5 — implementação inicial.
- `inventia_spoke_sdk/db/session.py` — código fonte do resolver registry e `session_for`.
- ADR-0001 — explicita por que não há wrapper `IUnitOfWork` em cima disso.
