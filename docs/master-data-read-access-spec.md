# Acesso de leitura ao cadastro do master-data (banco compartilhado)

> Status: implementação inicial entregue (SDK ≥ 0.7.0). Decisão em ADR 0004.
> Substitui a proposta anterior de `MasterDataMirror` (réplica) — descartada por
> não caber na topologia de banco compartilhado.

## 1. Contexto e topologia

A casa usa **1 Account = 1 banco** (Tier 1 removido). master-data e os spokes
resolvem o **mesmo `db_url`** por account via Hub. As tabelas de cadastro
(`companies`, `products`, `units_of_measure`, `participants`, `certificates`) do
master-data **vivem no mesmo banco** que cada spoke já abre — vários apps migram
para o mesmo banco, isolados por `version_table` Alembic distinta.

Consequência: a "SPOF do master-data" para **leitura** não é de rede. É a escolha
de chamar a API HTTP do master-data em vez de ler a tabela que está ali, no mesmo
banco. Replicar o cadastro (a ideia anterior) duplicaria as mesmas linhas no mesmo
banco — não fazemos isso.

## 2. Decisão

O SDK provê **acesso de leitura compartilhado** ao cadastro, direto no banco do
account, tenant-scoped, sem HTTP e sem cópia. Escrita permanece exclusiva do
master-data.

## 3. O que o SDK fornece

`inventia_spoke_sdk/masterdata/`:

- **`models.py`** — read-models canônicos (`Company`, `Product`, `UnitOfMeasure`)
  num `MetaData` próprio (`ReadBase`), ISOLADO do `Base` do spoke. Mapeiam um
  subconjunto das colunas que os consumidores precisam.
- **`repository.py`** — `MasterDataRepository`, métodos de leitura que recebem a
  `AsyncSession` do `session_for(principal)` e filtram por `tenant_id`:
  `get_company`, `get_company_by_tax_id`, `list_companies`, `get_product_by_code`,
  `list_products_by_codes`, `get_unit`.

Uso:

```python
from inventia_spoke_sdk import session_for
from inventia_spoke_sdk.masterdata import MasterDataRepository

repo = MasterDataRepository()
async with session_for(principal) as session:
    emit = await repo.get_company(session, tenant_id=tid, company_id=cid)
    un = await repo.get_unit(session, tenant_id=tid, unit_code="UN")
```

## 4. Invariantes

1. **Somente leitura.** O SDK não expõe escrita ao cadastro. Escrita só pelo
   master-data. (Idealmente reforçar com `GRANT SELECT`/RLS por papel.)
2. **Tenant scoping sempre.** Toda query filtra `tenant_id` (regra dura dos spokes).
3. **Não migrar as tabelas.** `ReadBase.metadata` nunca entra no
   `autogenerate`/`create_all` do spoke — as tabelas pertencem ao master-data.
4. **Contrato no SDK.** Os read-models são o contrato gerenciado master-data ↔
   consumidores; mudança destrutiva de schema coordena a versão do SDK.

## 5. Consequências

- **Zero duplicação**; uma cópia só do cadastro.
- **Resiliência por construção**: master-data (HTTP) fora não afeta a leitura — só
  o Postgres importa, e já é dependência de todos.
- **Sem sync**: nada de eventos/delta/watermark/consistência eventual. Leitura é a
  verdade atual.
- **JOIN direto** possível (mesmo banco) — ex.: `fiscal_reports` resolvendo nome de
  empresa direto na query, sem N+1 de HTTP.

## 6. Acoplamento de schema (o trade-off real)

Ler as tabelas direto acopla o consumidor à estrutura física do master-data — era
o que a API HTTP encapsulava. Mitigação: os read-models do SDK centralizam esse
contrato (em vez de N spokes adivinhando o schema). **Follow-up**: teste de guarda
de drift comparando os read-models com o schema real do master-data no CI.

## 7. Certificado — caso à parte

`certificates` guarda `pfx_encrypted`/`password_encrypted` cifrados com a chave
Fernet do master-data. Ler a linha direto entrega ciphertext. Para assinar, ou a
chave é um segredo compartilhado disponível ao signatário, ou a assinatura
continua no master-data. É decisão de **gestão de chave**, não de acesso a dado —
fora do escopo desta spec de leitura.

## 8. Migração dos consumidores

- **outbound-nfe**: hoje copia empresa para `company_nfe` no enroll (duplicação) e
  chama `/companies/candidates` por HTTP. Alvo: ler via `MasterDataRepository`;
  manter em `company_nfe` apenas o que é config específica de NF-e (séries, etc.),
  referenciando a empresa canônica por id.
- **fiscal_reports / escrituracaofiscal (nomes)**: trocar o lookup HTTP por leitura
  direta (ou JOIN), eliminando o cache TTL + fallback do `master_data_client`.

## 9. O que NÃO fazer

- Não replicar o cadastro (cópia no mesmo banco).
- Não escrever no cadastro a partir de um spoke.
- Não incluir `ReadBase.metadata` nas migrations do spoke.
- Não consultar sem `tenant_id`.

## 10. Rollout

| Fase | Onde | Entrega |
|---|---|---|
| 1 (feito) | SDK | read-models + `MasterDataRepository` (company/product/unit) |
| 2 (feito) | SDK | participants, certificado (metadados), referências IBGE/CNAE + `assert_no_drift` |
| 3 | master-data | CI chama `assert_no_drift(schema)`; piloto outbound-nfe (ler via repo, enxugar `company_nfe`) |
| 4 | demais consumidores | migrar leitura; aposentar caminhos HTTP de leitura |
| — | master-data | (opcional) `GRANT SELECT`/RLS por papel para reforçar read-only |

### Cobertura atual do `MasterDataRepository`

- Company: `get_company`, `get_company_by_tax_id`, `list_companies`
- Product: `get_product`, `get_product_by_code`, `list_products_by_codes`, `list_products`
- Unit: `get_unit`, `list_units`
- Participant: `get_participant`, `get_participant_by_cnpj`, `get_participant_by_cpf`, `list_participants`
- Certificate (metadados): `get_active_certificate` (sem pfx/senha)
- Referência global: `get_municipality`, `get_cnae`

## 11. Decisões em aberto

1. Gestão da chave do certificado: segredo compartilhado para o signatário vs
   assinatura sempre no master-data. (Leitura de **metadados** já disponível via
   `get_active_certificate`; material cifrado segue fora deste caminho.)
2. Reforço físico de read-only: `GRANT`/RLS por papel vs só convenção.
3. ~~Guarda de drift~~ **RESOLVIDO**: `masterdata.assert_no_drift(schema)` —
   a CI do master-data passa o schema real (do seu `MetaData`) e a função
   verifica que as colunas dos read-models são subconjunto. Falta só ligar essa
   chamada no CI do master-data (Fase 3).
