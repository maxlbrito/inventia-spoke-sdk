"""Guarda de drift — read-models do SDK vs schema real do master-data.

Ler as tabelas direto acopla o consumidor à estrutura física do master-data
(ADR 0004 §Consequences). Esta guarda detecta o caso perigoso: um read-model
referenciar uma coluna/tabela que não existe mais no master-data (renomeada ou
removida), o que quebraria a leitura em runtime.

Como o SDK é a base (não pode depender do master-data), a CI do master-data é
quem chama isto, passando o schema real extraído do seu próprio ``MetaData``:

    # no CI do master-data:
    from inventia_spoke_sdk.masterdata import assert_no_drift
    schema = {t.name: set(t.columns.keys()) for t in MasterDataBase.metadata.tables.values()}
    assert_no_drift(schema)

Adicionar colunas no master-data é seguro (os read-models mapeiam um
subconjunto) — por isso a checagem é "colunas do read-model ⊆ colunas reais".
"""

from __future__ import annotations

from collections.abc import Mapping

from inventia_spoke_sdk.masterdata.models import ReadBase


class SchemaDriftError(AssertionError):
    """Read-models divergiram do schema real do master-data."""


def check_models_against(schema: Mapping[str, set[str]]) -> list[str]:
    """Retorna a lista de divergências (vazia = sem drift).

    ``schema``: ``{nome_tabela: {coluna, ...}}`` com o schema real do master-data.
    Verifica que cada tabela dos read-models existe e que suas colunas são
    subconjunto das colunas reais.
    """
    problems: list[str] = []
    for table_name, table in ReadBase.metadata.tables.items():
        real_cols = schema.get(table_name)
        if real_cols is None:
            problems.append(f"tabela '{table_name}' não existe no schema do master-data")
            continue
        for col in table.columns.keys():
            if col not in real_cols:
                problems.append(
                    f"'{table_name}.{col}' não existe no master-data (read-model desatualizado)"
                )
    return problems


def assert_no_drift(schema: Mapping[str, set[str]]) -> None:
    """Levanta ``SchemaDriftError`` se houver drift; no-op caso contrário."""
    problems = check_models_against(schema)
    if problems:
        raise SchemaDriftError(
            "drift entre read-models do SDK e o master-data:\n  - " + "\n  - ".join(problems)
        )
