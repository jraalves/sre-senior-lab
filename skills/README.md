# Agent Skills deste repositorio

Quatro skills no formato oficial de Agent Skills (front-matter `name` / `description` e
corpo em Markdown), criadas por mim a partir dos scripts e templates que ja existem neste
repositorio. Nada aqui foi transcrito de outro projeto.

| skill | o que ela opera de verdade no repo |
|---|---|
| `sre-alert-triage` | `agent/triage.py` (heuristica R1..R9), `agent/data/eval_cases.jsonl`, `agent/results/metrics.json` |
| `sre-runbook-drafter` | `labs/lab-04-runbooks/rb-01..rb-04`, vocabulario do `triage.py`, `tests/` |
| `sre-postmortem-writer` | `labs/lab-03-incidente-postmortem/templates/postmortem-template.md`, `analyze.py`, `data/timeline.csv` |
| `sre-change-review` | `labs/lab-01-slo-error-budget/slo.py`, `labs/lab-02-burn-rate-alerting/burnrate.py`, `docs/decisoes/` |

Instalar no Claude Code (a sintaxe exata do cliente pode variar entre versoes — confira
`/plugin` na sua build):

```
/plugin marketplace add jraalves/sre-senior-lab
/plugin          # entao escolha "sre-ops-skills" e instale
```

Sem o Claude Code, estas mesmas instrucoes continuam uteis: cada arquivo `SKILL.md` e um
procedimento legivel, versionado e com criterio de saida — que e o que um runbook deveria
ser de qualquer forma.

**O que estas skills nao sao:** elas nao medem nada por si. Os numeros citados nelas sao
do classificador heuristico do repositorio (79 casos; 100% intra-amostra, declarado como
overfit; 94,94% de acerto de categoria e 79,75% de correspondencia de runbook sob
perturbacao). Qualidade de prompt/skill nao e medida aqui — onde nao ha medicao, o texto
diz "nao medido".
