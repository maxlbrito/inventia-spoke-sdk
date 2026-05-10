# Architecture Decision Records — inventia-spoke-sdk

ADRs documentam **decisões arquiteturais** do SDK que afetam contratos públicos, integração com spokes, ou comportamento em produção. Não documentam "como funciona" (isso vai no README e nos docstrings).

## Quando escrever um ADR no SDK

- A decisão muda a API pública (símbolos exportados, assinatura de funções).
- A decisão tem alternativas plausíveis e a escolha precisa ser justificada.
- A decisão tem consequência operacional (custo, segurança, perf, multi-tenant).
- Reverter custaria mais de um dia de trabalho.

Refactor interno, rename de variável privada, bump de minor → **não** precisa.

## Naming

`NNNN-slug.md` em quatro dígitos zero-padded, sequencial, imutável.

## Index

- [0001 — AsyncSession já é Unit of Work; sem wrapper](0001-no-iunitofwork-asyncsession-is-uow.md)
- [0002 — SessionFactoryResolver pattern para multi-tenant](0002-session-factory-resolver-pattern.md)
- [0003 — OpenTelemetry helpers como opt-in extra](0003-otel-helpers-opt-in-extra.md)
