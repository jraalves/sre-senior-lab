# ADR 0002 — Heurística determinística em vez de modelo treinado

- **Status:** aceito
- **Data:** 2026-11
- **Contexto do repositório:** agent/triage.py, agent/evaluate.py

## Contexto

O agente de triagem precisa devolver categoria e runbook a partir de `alertname`,
texto e metadata. O caminho óbvio é um classificador treinado. O banco de casos
aqui tem 79 registros, com vocabulário de um domínio estreito, e o objetivo do
lab é mostrar raciocínio de plantão — não bater benchmark.

## Decisão

Classificador por heurística versionada (`TRIAGE_VERSION`), determinística, com
pesos por termo, catálogo de prefixos de `alertname`, regras por label de
metadata, regras numéricas (percentual de uso e razão "A dos B"), janela de
negação e desempate estável por ordem fixa. Sem `random`, sem modelo, sem
dependência externa.

Três consequências estruturais dessa escolha:

1. **Explicabilidade total.** `classificar()` devolve `motivos` com cada peso
   que contribuiu. Em plantão, saber *por que* o agente apontou rb-02 importa
   mais que a acurácia.
2. **Reprodutibilidade.** Duas execuções produzem byte idêntico de
   `metrics.json`. O avaliador verifica isso e grava o hash (`determinismo`).
3. **Custo de manutenção conhecido.** Ajuste de peso é revisão de código, não
   re-treino; e é por isso mesmo que a armadilha é visível.

## Limite declarado (a parte importante)

Os pesos foram ajustados sobre o próprio banco de 79 casos. A acurácia medida é
**intra-amostra**: ela diz que a heurística é coerente com o vocabulário do
domínio, não que generaliza. O `agent/results/report.md` acompanha duas correções
medidas:

- **ablação** por camada de regra (léxico, catálogo de alertname, metadata,
  numéricas, janela de negação), para expor o que faz o número subir;
- **robustez** sob perturbação determinística da entrada (alertname anônimo,
  metadata vazia, texto truncado, ordem das palavras invertida), que é o
  vizinho mais honesto de um teste cego que 79 casos não permitem.

Regra de parcimônia aplicada: dezoito regras de fronteira que casavam frase
literal de um único caso foram removidas depois que a ablação mostrou que o
léxico já resolvia os casos sozinha. Regra que não muda nenhum número medido é
ornamento, não conhecimento.

## Como medir que a decisão continua boa

`python3 agent/evaluate.py --report` — conferir acurácia, ablação, robustez e se
`determinismo.identico` segue `true`.
