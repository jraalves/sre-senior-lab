---
name: sre-alert-triage
description: Use this skill when an alert, paging message, incident channel post or monitoring screenshot arrives and the category and the runbook are not yet known. Trigger on words such as "alerta", "page", "firing", "incidente", "p95 alto", "taxa de erro", "saturacao", "queda de throughput", "o que faco agora", or when a runbook id (rb-01..rb-04) must be chosen. Uses the deterministic classifier in agent/triage.py, never guesses a runbook.
license: Apache-2.0
---
# Triagem de alerta com evidencia

Este skill **nao** decide por intuicao: ele chama a heuristica deterministica do
repositorio (`agent/triage.py`, regras R1..R9) e devolve categoria, runbook e confianca.
A acuracia medida desse classificador esta em `agent/results/metrics.json` (veja `make eval`):
79 casos, 100% intra-amostra — **overfit declarado**, porque o banco foi escrito junto com as
regras (ADR `docs/decisoes/0002-heuristica-deterministica.md`). A robustez medida e mais
honesta: invertendo a ordem das palavras, 94,94% de categoria e 79,75% de correspondencia de
runbook; truncando o texto a 48 caracteres, 98,73% e 70,89%.

## Procedimento
1. Rodar o classificador com o que chegou:
   ```bash
   python3 agent/triage.py --alertname "<nome do alerta>" --text "<texto>" \
     --cluster "<cluster>" --namespace "<namespace>"
   ```
   Varias mensagens de uma vez: `python3 agent/triage.py --stdin < arquivo.jsonl`.
2. Ler no resultado: `categoria`, `runbook`, `confianca` e as regras que dispararam.
   Se `runbook == rb-00-escalada-humana`, **nao** escolher outro no lugar: escalar.
3. Abrir o runbook indicado e executar a secao **Diagnostico (somente leitura)** antes
   de qualquer acao de mitigacao.
4. Registrar a triagem no incidente: alerta, categoria obtida, runbook, hora, proximo
   passo. Sem isso o post-mortem fica sem timeline.

## Como decidir quando a heuristica e ambigua
- confianca baixa **e** dois runbooks empatados: faca o diagnostico somente leitura dos
  dois, compare o primeiro criterio mensuravel de cada um, escolha o que o dado sustenta.
- sinal existe mas o SLO correspondente nao esta definido: isso e lacuna de observabilidade,
  nao incidente — abrir item e dizer explicitamente "sem SLI definido".
- o alerta e artefato de scrape (serie para de crescer, `up == 0`): confirmar com
  `labs/lab-05-golden-signals/metrics.py --report` antes de pagear someone.

## Limites
- Nao adivinhar causa raiz em triagem. Triagem escolhe **procedimento**, nao diagnostico.
- Nao criar alerta novo nem mexer em regra sem `make eval` antes e depois.
- Nenhum dado real de producao entra nos exemplos que voce escrever (regra 1 do `CLAUDE.md`).
