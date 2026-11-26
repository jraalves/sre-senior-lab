---
name: sre-postmortem-writer
description: Use this skill after an incident is contained or resolved and a blameless written record is needed - when the user says "post-mortem", "postmortem", "RCA", "causa raiz", "documento de incidente", "registrar o incidente" ou traz uma timeline. Also use it to audit an existing postmortem for missing timing metrics and action owners. Fills the repository's 11-section template and computes MTTD/MTTA/MTTR with the lab script.
license: Apache-2.0
---
# Post-mortem sem culpa, com numeros que batem

Template oficial deste repositorio:
`labs/lab-03-incidente-postmortem/templates/postmortem-template.md` (11 secoes).
Timeline de entrada: `labs/lab-03-incidente-postmortem/data/timeline.csv`.
Metricas calculadas por `python3 labs/lab-03-incidente-postmortem/analyze.py --report`.

## Ordem de trabalho
1. **Montar a timeline primeiro**, nao a narrativa: hora do sinal, hora do page, primeira
   acao de diagnostico, contencao, resolucao. Uma linha por evento, UTC, com fonte
   (log, alerta, chat).
2. Rodar `make lab03` para obter MTTD / MTTA / MTTR **medidos** e colar os valores no
   documento. Se a timeline estiver incompleta, escreva "nao medido — falta o evento X";
   nunca arredondar sem base.
3. Preencher as 11 secoes na ordem do template: Resumo, Impacto, Detecção,
   Diagnóstico e contenção, Causa raiz, O que funcionou bem, O que não funcionou bem,
   Ações, Métricas de tempo, Custo de toil estimado, Como este documento foi produzido.
4. Causa raiz em cinco porquês, terminando em **decisao de projeto ou de processo** —
   nunca em " alguem esqueceu". Cada porquê aponta para uma evidencia da timeline.
5. Acoes: cada uma com dono, prazo, tipo (preventiva/detectiva/mitigadora) e o criterio
   que prova que fechou. Acao detectiva deve citar o SLI ou o alerta novo correspondente.
6. Toil: estimar a partir de `analyze.py` e dizer o metodo na secao 11.

## Regras
- Blameless: nome de pessoa nao entra no documento; entra funcao e decisao.
- Sem cliente, sem hostname real, sem ID de ticket verdadeiro (regra 1 do `CLAUDE.md`).
- A secao 11 ("Como este documento foi produzido") declara o que e script, o que e
  humano e o que e agente. Documento gerado sem essa linha e recusado.
- Se nao houve impacto mensuravel, dizer o impacto zero e o que faltou para medir.
