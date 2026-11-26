---
name: sre-runbook-drafter
description: Use this skill when a symptom has no runbook yet, when an existing runbook is out of date, or when the user asks to "escrever um runbook", "padronizar procedimento", "documentar o passo a passo de X" or to review a runbook written by someone else. Produces a runbook in the repository's canonical five-part structure, with executable read-only diagnostics and measurable exit criteria.
license: Apache-2.0
---

# Redator de runbook no formato canonico do laboratorio

Modelo de referencia: `labs/lab-04-runbooks/rb-01-latencia-alta.md`. Todo runbook deste
repositorio tem as mesmas **seis** secoes, na mesma ordem — o texto abaixo e a estrutura
real dos arquivos `rb-01` a `rb-04`, nao um formato inventado.

| secao | conteudo obrigatorio | teste de qualidade |
|---|---|---|
| `1. Gatilho` | tabela `sinal / consulta / condicao`, com a metrica e o threshold | da para ligar o runbook a um alerta que ja existe? |
| `2. Diagnóstico (somente leitura)` | passos numerados (`2.1`, `2.2`...), cada um com comando e o que procurar | nenhum passo escreve estado |
| `3. Árvore de decisão` | tabela `observacao / hipotese / proximo passo` | cada linha termina em acao concreta |
| `4. Ações` | agrupadas por risco: **baixo** (reversivel, sem aprovacao), **medio** (anunciar no canal de plantao), **alto/destrutivo** (aprovacao humana de duas pessoas) | o risco esta declarado antes da acao |
| `5. Critério de saída` | lista de itens que devem ser **todos** verdadeiros para encerrar + a regra de "pare de tentar" | cada item e um numero consultavel, nao "se melhorar" |
| `6. Pós-ação` | registrar no tracker; vincular a causa ao lab certo (mudanca → lab-03, volume → lab-06) | fecha o loop com evidencia |

## Procedimento
1. Fixar o **sintoma** observado (latencia, erro, saturacao, throughput, dependencia,
   capacidade, custo) — nao a causa hipotetica.
2. Ver se ja existe: `ls labs/lab-04-runbooks` e o vocabulario em `agent/triage.py` (e ele
   que escolhe o runbook na triagem). Se existir, o trabalho e revisao, nao criacao.
3. Escrever em `labs/lab-04-runbooks/rb-NN-<slug>.md` com as seis secoes acima. As consultas
   precisam bater com as regras dos labs — por exemplo
   `slo:requests:latencia_ratio:sum5m` e `histogram_quantile(0.95, ...)` ja usados em
   `rb-01` e definidos em `labs/lab-02-burn-rate-alerting/` e
   `labs/lab-05-golden-signals/`. **Nao inventar nome de serie temporal.**
4. Incluir na secao 5 o estado "inativo por instabilidade de janela" como **nao** resolvido
   (armadilha real que `rb-01` ja documenta).
5. Registrar o novo sintoma no vocabulario do classificador **com teste novo** em `tests/`
   e ao menos um caso em `agent/data/eval_cases.jsonl`.
6. Rodar `make test && make eval`. Se a acuracia cair, explicar a queda no commit — nunca
   "ajustar" o banco de casos para a metrica ficar bonita.

## Anti-padroes que este skill recusa
- "Reinicie o pod" como primeiro passo: apaga a evidencia que a secao 2 ainda vai precisar.
- Threshold sem serie temporal definida; alerta sem condicao mensuravel.
- Acao sem faixa de risco; secao 5 escrita como "se melhorar, encerra".
- Runbook que cita cliente, hostname real, IP de producao ou ticket verdadeiro
  (regra 1 do `CLAUDE.md`).
- Passo que so o autor entende: quem esta de plantao as 3h da manha precisa executar sem
  perguntar nada no chat.
