# 0004 — Acesso de leitura ao cadastro do master-data (banco compartilhado)

Status: Accepted (2026-06-13)

> Nota: uma versão anterior deste ADR propunha um `MasterDataMirror` (réplica
> local sincronizada por eventos + delta). Foi **descartada** ao confirmarmos a
> topologia real: master-data e os spokes compartilham o **mesmo banco por
> account**. Replicar o cadastro criaria cópias das mesmas linhas no mesmo banco.
> Este ADR registra a decisão corrigida.

## Context

O `master-data` é dono do cadastro (`companies`, `products`, `units_of_measure`,
`participants`, `certificates`). Os spokes (`outbound-*`, `sped*`,
`fiscal_reports`, `escrituracaofiscal`) consomem esse cadastro **chamando a API
HTTP do master-data**. Se o serviço HTTP do master-data cai, os consumidores no
caminho crítico (emissão, escrituração) caem junto — a dor que originou esta
investigação.

Topologia confirmada em código:

- `master-data/backend/app/db_pool.py` e `outbound-nfe/backend/app/db_pool.py`
  resolvem o `db_url` da **mesma** forma: contexto do account via Hub
  (`GET /spoke/context/{tenant_id}`). Mesmo account → mesmo `db_url`.
- Cada app usa uma `version_table` Alembic distinta no mesmo banco
  (`alembic_version_masterdata`, `alembic_version_outbound_nfe`,
  `alembic_version_escrituracaofiscal`). Version tables distintas só são
  necessárias quando **vários apps migram para dentro do mesmo banco**.

Ou seja: as tabelas de cadastro do master-data **já vivem no banco que o spoke
abre**. A "SPOF de leitura" não é de rede — é a escolha de ir pela API HTTP em
vez de ler a tabela que está no mesmo banco.

## Problem

Como dar aos spokes acesso resiliente ao cadastro, **sem duplicar dados** e sem
acoplar cada spoke à estrutura física das tabelas do master-data?

- O `inventia-spoke-sdk` é infra agnóstica de domínio e é dependência de todos os
  spokes; não pode depender do master-data (o SDK é a base).
- A escrita do cadastro precisa continuar **exclusiva** do master-data.
- O certificado é cifrado (Fernet) com a chave do master-data — caso à parte.

## Decision

O SDK fornece uma camada de **acesso de leitura compartilhado** ao cadastro,
sobre o **mesmo banco por account** que o spoke já abre — sem HTTP no caminho de
leitura e sem réplica:

1. **Read-models canônicos** (`inventia_spoke_sdk/masterdata/models.py`):
   classes SQLAlchemy somente-leitura (`Company`, `Product`, `UnitOfMeasure`)
   mapeando as tabelas do master-data, num `MetaData` **dedicado e isolado**
   (`ReadBase`). Esse metadata **nunca** entra no `autogenerate`/`create_all` do
   spoke — as tabelas pertencem ao master-data.
2. **Repository tenant-scoped** (`MasterDataRepository`): recebe a
   `AsyncSession` do `session_for(principal)` (não abre conexão própria), e toda
   query filtra por `tenant_id`. Só expõe métodos de leitura.
3. **Escrita permanece no master-data** (via API ou código do próprio
   master-data). O SDK não oferece caminho de escrita ao cadastro.

Os read-models no SDK passam a ser o **contrato gerenciado** entre master-data e
consumidores (no lugar do acoplamento implícito à API HTTP).

## Alternatives considered

### A) Cada spoke chama a API HTTP do master-data (estado atual — rejeitado)

É a SPOF. O dado está no mesmo banco; ir por HTTP adiciona uma dependência de
serviço desnecessária no caminho crítico.

### B) Réplica local sincronizada (mirror: eventos + delta) (rejeitado)

Padrão de microsserviços com **bancos separados**. Na nossa topologia
(banco compartilhado) replicaria as mesmas linhas no mesmo banco — duplicação
pura, contra o princípio explícito de não duplicar dados. Toda a maquinaria
(outbox, watermark, reconcile) resolveria um problema que não temos.

### C) Read-models + repository no SDK sobre o banco compartilhado (escolhido)

Leitura direta, tenant-scoped, sem cópia e sem HTTP. Resiliente por construção:
a indisponibilidade do serviço HTTP do master-data não afeta a leitura.

### D) Cada spoke define seus próprios models das tabelas (rejeitado)

Funciona, mas N definições divergentes da mesma tabela → drift garantido. O SDK
centraliza o contrato.

## Consequences

### Positivas

- **Zero duplicação** — uma única cópia do cadastro, no banco do account.
- **Resiliência** — master-data (HTTP) fora não derruba leitura; só o Postgres
  importa, e ele já é dependência de todos.
- **Sem maquinaria de sync** — sem eventos, sem delta, sem watermark, sem
  consistência eventual. Leitura é sempre a verdade atual.
- **JOIN direto** — como é o mesmo banco, um consumidor pode até juntar
  `companies` nas suas próprias queries (ex.: `fiscal_reports` resolvendo nome).
- Contrato centralizado: um lugar para os models do cadastro.

### Negativas / riscos

- **Acoplamento de schema**: ler as tabelas direto acopla o consumidor à
  estrutura física do master-data. Mitigação: os read-models do SDK são o
  contrato; mudanças destrutivas no master-data exigem coordenar a versão do SDK.
  *Follow-up*: guarda de drift (teste comparando os read-models com o schema real
  do master-data).
- **Escrita read-only por convenção**: o SDK só expõe leitura, mas nada impede
  fisicamente um spoke de escrever na tabela. Mitigação: disciplina +
  (idealmente) `GRANT SELECT`/RLS por papel no banco.
- **Certificado**: cifrado com a chave do master-data. Ler a linha dá ciphertext;
  decifrar exige a chave (segredo compartilhado) ou que a assinatura continue no
  master-data. Decisão de gestão de chave, fora do escopo de leitura — tratada à
  parte.

## Implementation notes

- `Uuid` (SQLAlchemy 2.0, dialect-agnóstico) em `id`/`tenant_id` — lê UUID nativo
  no Postgres e funciona em SQLite nos testes.
- Read-models mapeiam um **subconjunto** das colunas; `SELECT` só pelas mapeadas,
  então adicionar coluna no master-data não quebra a leitura.
- O repositório aceita `tenant_id`/ids como `str | UUID` e coage para `UUID`.

## References

- [`docs/master-data-read-access-spec.md`](../master-data-read-access-spec.md) — desenho completo.
- ADR-0002 — `SessionFactoryResolver`/`session_for`: a sessão que o repositório consome.
- Investigação de topologia (2026-06-13): `db_pool.py` de master-data e outbound-nfe + version tables Alembic.
