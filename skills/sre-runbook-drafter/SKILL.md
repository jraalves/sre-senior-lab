---
name: sre-runbook-drafter
description: Use this skill when a symptom has no runbook yet, when an existing runbook is out of date, or when the user asks to "escrever um runbook", "padronizar procedimento", "documentar o passo a passo de X" or to review a runbook written by someone else. Produces a runbook in the repository's canonical five-part structure, with executable read-only diagnostics and measurable exit criteria.
license: Apache-2.0
---
# Redator de runbook no formato canonico do laboratorio

Modelo de referencia: `labs/lab-04-runbooks/rb-01-latencia-alta.md`. Todo runbook novo
tem as mesmas cinco partes, na mesma ordem, com os mesmos tipos de criterio.

| parte | conteudo obrigatorio | teste de qualidade |
|---|---|---|
| 1. Gatilho | tabela `sinal / consulta / condicao`, com a metrica e o threshold | da para ligar o runbook a um alerta existente? |
| 2. Diagnóstico | passos **somente leitura**, numerados (`2.1`, `2.2`...), cada um com comando e o que procurar | nenhum passo escreve estado |
| 3. Árvore de decisão | tabela `observacao / hipotese / proximo passo` | cada linha tem proximo passo concreto |
| 4. Mitigação | acao + efeito esperado + **criterio de saida** medivel | "quando parar" esta escrito |
| 5. Escalonamento | para quem, com que dado, em quanto tempo | sem "escalar se persistir" vago |

## Procedimento
1. Perguntar (ou deduzir do alerta) o **sintoma**, nao a causa: latencia, erro, saturacao,
   throughput, dependencia, capacidade, custo.
2. Ver se ja existe: `ls labs/lab-04-runbooks` e o vocabulario em `agent/triage.py`
   (o mapa R2 e o que escolhe runbook). Se existir, o trabalho e revisao, nao criacao.
3. Escrever em `labs/lab-04-runbooks/rb-NN-<slug>.md` usando a estrutura acima. Comandos
   PromQL/LogQL devem bater com as regras de `labs/lab-05-golden-signals/` e
   `labs/lab-02-burn-rate-alerting/` — nao inventar nome de serie temporal.
4. Adicionar o sintoma ao vocabulario do classificador **com teste novo** em `tests/` e
   ao menos um caso em `agent/data/eval_cases.jsonl`.
5. Rodar `make test && make eval`. Se a acuracia cair, explicar a queda no commit — nao
   "ajustar" o banco de casos para a metrica ficar bonita.

## Anti-padroes que este skill deve recusar
- "Reinicie o pod" como primeiro passo (apaga evidencia).
- Threshold sem serie temporal definida; alerta sem condicao mensuravel.
- Runbook que cita cliente, hostname real, IP de producao ou ticket verdadeiro.
- Passo sem criterio de saida: quem esta de plantao nao sabe quando parou de funcionar.
