# ADR 0001 — Dados sintéticos em vez de dados reais ou de exemplo

- **Status:** aceito
- **Data:** 2026-11
- **Contexto do repositório:** labs/lab-01 a lab-07, agent/data

## Contexto

Um laboratório de SRE só é útil se os números tiverem estrutura realista:
janelas de 5 minutos, erro que queima orçamento, fila que acumula, incidente com
timeline. Usar dados de produção é impossível (segredo, cliente, LGPD) e usar
"dados de exemplo" de tutorial é pior: costumam ser ruído uniforme, sem
incidente plantado, e o exercício vira API de biblioteca em vez de decisão.

## Decisão

Todo artefato de dado vem de `tools/synth.py`, com seed fixa (`SEED_PADRAO=42`)
e um manifest declarando cada arquivo gerado. O gerador é a única fonte: o CSV
commitado no repositório é saída dele, conferida por `python3 tools/synth.py
--check`, que valida presença, contagem de linhas, integridade interna
(`fast + slow == requests`) e rótulos obrigatórios do banco de casos.

Nomes de serviço, cluster, namespace, IP, custo e duração são fictícios e
rotulados como sintéticos no próprio arquivo ou no README do lab.

## Consequência

- Positiva: qualquer pessoa reproduz byte a byte, o CI barra regressão de dado,
  e dá para plantar incidente de propósito (há quatro em `data_defs.py`) e
  depois medir se o método detecta.
- Positiva: zero risco de vazar dado de terceiro.
- Negativa: o mundo real é mais sujo que o sintético. Números daqui não
  dimensionam nada real, e a heurística do agente avaliada sobre eles tem viés
  de vocabulário. Isso está declarado no `agent/results/report.md` e no README.

## Como medir que a decisão continua boa

`python3 tools/synth.py --check` (código zero) e conferir o sha256 parcial
impresso por `python3 tools/synth.py --report` contra o arquivo commitado.
