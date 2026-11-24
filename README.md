# SRE Senior Lab

Laboratório de prática de SRE/plantão: sete labs encadeados (SLO, alertagem por
burn rate, postmortem, runbooks, sinais dourados, capacidade, custo) mais um
agente de triagem determinístico com avaliador próprio. Tudo roda offline, com
**biblioteca padrão do Python 3** e dados **100% sintéticos**.

## Público-alvo

Quem já faz plantão e quer treinar o julgamento que não aparece em curso: decidir
se um alerta é latência ou dependência, se queima orçamento ou é ruído, se a
resposta é um runbook ou escalar para humano, e quanto aquilo custa. Também serve
como material de onboarding de plantão e como referência de estrutura (runbook,
ADR, postmortem, testes de arithmetic).

Não é para quem procura um sistema de monitoramento pronto para produção: a stack
do lab-05 sobe sem autenticação de propósito. Leia `SECURITY.md`.

## Pré-requisitos

- Python 3.10 ou superior (`python3 --version`). Nenhuma dependência externa:
  `requirements.txt` é só documentação, não há nada a instalar.
- `make` opcional (os alvos chamam os mesmos comandos de linha).
- Docker apenas para o lab-05 querer ver no Grafana o que os scripts já
  calculam. Nenhum lab precisa da stack para funcionar.

## O que é sintético

**Todo** dado do repositório. Nada aqui veio de produção, de cliente ou de
fornecedor.

- Único gerador: `tools/synth.py`, seed fixa `42`, manifest declarando cada
  artefato. Reproduzível byte a byte: `python3 tools/synth.py --check`.
- Nomes de serviço, cluster, namespace, IP, custo, duração e tráfego são
  fictícios. Os quatro incidentes das séries são plantados de propósito para o
  exercício ter o que detectar.
- Os runbooks de `labs/lab-04-runbooks/` são modelos genéricos escritos para o
  lab, não documentos de nenhuma empresa.
- O banco de 79 casos de avaliação (`agent/data/eval_cases.jsonl`) é gerado por
  `tools/case_bank.py`. Os pesos da heurística foram ajustados sobre ele, então
  a acurácia medida é intra-amostra — o README diz isso e o relatório mede o
  efeito. Detalhe em `docs/decisoes/0002-heuristica-deterministica.md`.

## Os sete labs

| lab | o que você faz | como rodar |
| --- | --- | --- |
| lab-01 SLO e orçamento de erro | SLI de disponibilidade e latência, consumo por dia/semana, política de release gate | `python3 labs/lab-01-slo-error-budget/slo.py --report` |
| lab-02 alertagem por burn rate | burn rate multi-janela, matriz de regras 99,9/99,95/99,99, o que pagaria de madrugada | `python3 labs/lab-02-burn-rate-alerting/burnrate.py --report` |
| lab-03 incidente e postmortem | reconstrói timeline a partir de eventos, mede MTTD/MTTR e gera rascunho de postmortem | `python3 labs/lab-03-incidente-postmortem/analyze.py --report` |
| lab-04 runbooks | quatro runbooks com gatilho, triagem, mitigação e validação | sem script: `ls labs/lab-04-runbooks` (ou `make lab04`) |
| lab-05 sinais dourados | latência/trafego/erro/saturação por request_id, árvore de trace, stack open source | `python3 labs/lab-05-golden-signals/metrics.py` e `python3 labs/lab-05-golden-signals/correlate.py --summary` |
| lab-06 capacidade | mínimos quadrados escritos à mão, semana de saturação, lead time, expandir/observar/reduzir | `python3 labs/lab-06-capacity-planning/capacity.py --report` |
| lab-07 custo | custo por componente, alocação por tag, desperdício, projeção trimestral, três cenários | `python3 labs/lab-07-finops/cost_model.py --report` |

Atalhos: `make help` lista os alvos, `make run` regenera e confere os dados,
`make labs` roda os sete em sequência, `make test` roda a suíte, `make eval`
reavalia o agente, `make clean` remove cache e resultados gerados.

### lab-05 com Docker

```bash
cd labs/lab-05-golden-signals
docker compose config -q     # valida o arquivo
docker compose up -d         # collector, Prometheus, Loki, Tempo, Grafana
```

Portas padrão de cada projeto: OTLP 4317/4318, Prometheus 9090, Loki 3100,
Tempo 3200, Grafana 3000. Sem segredo em nenhum arquivo. Ver
`docs/decisoes/0003-stack-open-source.md`.

## Agente de triagem

`agent/triage.py` recebe um alerta (`alertname`, texto livre e metadata) e devolve
categoria, sintoma dourado, runbook sugerido, confiança e os **motivos** da
decisão. Heurística versionada (`TRIAGE_VERSION`), determinística, sem modelo
treinado e sem `random`: pesos por termo, catálogo de prefixos de `alertname`,
regras por label de metadata, regras numéricas (percentual de uso e razão "A dos
B"), janela de negação ("a taxa de erro está **estável**" não conta como erro) e
desempate estável por ordem fixa de categorias.

```bash
python3 agent/triage.py --alertname ErrorRateHigh \
    --text "Taxa de erro HTTP 5xx em 4,2% contra SLO de 1%" \
    --metadata '{"service":"ledger-api","channel":"chat-plantao"}'
```

Categorias e runbooks respeitam exatamente o vocabulário do banco de casos.
`rb-00-escalada-humana` é um rótulo legítimo: significa que nenhum runbook se
aplica e a triagem deve chamar uma pessoa.

### Resultados medidos

Executado em 2026-11-24 com `python3 agent/evaluate.py --report` (heurística
1.1.0, banco de 79 casos). Os números abaixo foram copiados de
`agent/results/metrics.json` gerado nessa execução.

| metrica | valor medido |
| --- | --- |
| casos avaliados | 79 |
| acuracia de categoria | 100.00% (79/79) |
| correspondencia de runbook | 100.00% (79/79) |
| macro media F1 (categoria) | 100.00% |
| erros de categoria | 0 |
| erros de runbook | 0 |
| determinismo | byte identico entre execucoes, sha256 5f680b9cded1c616 |

| categoria | support | precision | recall | F1 |
| --- | --- | --- | --- | --- |
| capacidade | 12 | 100.00% | 100.00% | 100.00% |
| latencia | 12 | 100.00% | 100.00% | 100.00% |
| erro | 12 | 100.00% | 100.00% | 100.00% |
| configuracao | 11 | 100.00% | 100.00% | 100.00% |
| dependencia | 12 | 100.00% | 100.00% | 100.00% |
| rede | 10 | 100.00% | 100.00% | 100.00% |
| seguranca | 10 | 100.00% | 100.00% | 100.00% |

### Como ler estes numeros

Os 100% da tabela acima sao **intra-amostra**: os pesos da heuristica foram ajustados
sobre o mesmo banco de 79 casos gerado por `tools/case_bank.py`. Isso mede consistencia
interna e determinismo, **nao** desempenho em producao. O que da ideia de comportamento
real e a tabela abaixo, em que a entrada e degradada:

| perturbacao | acuracia de categoria | correspondencia de runbook |
| --- | --- | --- |
| alertname anonimo | 98.73% | 100.00% |
| metadata vazia | 100.00% | 100.00% |
| ordem das palavras invertida | 94.94% | 79.75% |
| texto truncado 48 | 98.73% | 70.89% |

Sem um banco rotulado por incidentes reais, qualquer numero maior que esse seria
invencao — por isso ele aparece aqui com o limite explicito. A leitura honesta: a heuristica
acerta no cenario limpo e degrada de forma previsivel e auditavel (as confusoes ficam entre
`dependencia` e `rede`, e entre `configuracao` e `erro`), que e o comportamento esperado de um
classificador por regras com motivos declarados.

### Quanto cada camada de regra contribui (ablação)

| camada desligada | acuracia categoria | runbook |
| --- | --- | --- |
| sem_catalogo_de_alertname | 98.73% | 100.00% |
| sem_janela_de_negacao | 100.00% | 98.73% |
| sem_metadata | 100.00% | 100.00% |
| sem_regras_de_fronteira | 100.00% | 100.00% |
| so_lexico | 100.00% | 100.00% |
| so_lexico_e_numericas | 98.73% | 100.00% |

A leitura honesta: desligar camadas quase não muda o resultado, porque o léxico
ponderado já resolve os casos. Foi por isso que dezoito regras de fronteira que
só casavam a frase literal de um único caso foram removidas — regra que não muda
nenhum número medido é memorização, não conhecimento.

### O número que sobrevive a entrada bagunçada (robustez)

| perturbacao da entrada | acuracia categoria | runbook |
| --- | --- | --- |
| alertname_anonimo | 98.73% | 100.00% |
| metadata_vazia | 100.00% | 100.00% |
| ordem_das_palavras_invertida | 94.94% | 79.75% |
| texto_truncado_48 | 98.73% | 70.89% |

Inverter a ordem das palavras derruba a acurácia de 100% para
94.94% e a correspondência de runbook para
79.75%. Esse é o número que eu citaria numa conversa sobre o quanto o
método generaliza. Os 100% intra-amostra medem coerência com o vocabulário do
domínio, não capacidade de encontrar um incidente que ainda não vi.

## Política de privacidade

- Nenhuma coleta. Não há telemetria, análise, cookie, servidor nem chamada de
  rede em nenhum script do repositório.
- Nenhum dado pessoal: não há nome de pessoa, e-mail, numero de contato, IP real,
  contrato, fornecedor ou cliente. Os IPs e identificadores nos CSVs são gerados
  a partir da seed.
- Nenhuma credencial em texto: chaves, tokens e senhas estão fora do repositório
  por construção (a stack do lab-05 roda sem autenticação justamente porque não
  há segredo a colocar).
- Se você encontrar aqui algo que pareça dado real, abra uma issue com o título
  começando por `DADO REAL` que eu removo imediatamente (`SECURITY.md`).

## Como contribuir

1. Abra uma issue descrevendo o problema antes de escrever código; ajuste de peso
   de heurística e mudança de dado passam por discussão.
2. Branch a partir de `main`, um commit por ideia, mensagem no imperativo.
3. Rode a validação completa e cole a saída no PR:

```bash
python3 tools/synth.py --check
python3 agent/evaluate.py --report
python3 -m unittest discover -s tests
```

4. Se mexer na heurística, atualize `docs/decisoes/0002-heuristica-deterministica.md`
   e confira se ablação e robustez continuam contadas no `agent/results/report.md`.
5. Se criar dado novo, crie no gerador (`tools/`), nunca à mão, e confirme o
   `--check`. Rode também o grep de anonimato descrito em
   `tests/test_anonimato.py`.
6. Mudanças de comportamento pedem teste em `tests/` (stdlib, sem pytest).

## English summary

A self-contained SRE training lab: seven chained exercises (SLO and error budget,
multi-window burn-rate alerting, incident timeline and postmortem, runbooks,
golden signals with cross-signal correlation by `request_id`, capacity planning,
FinOps cost model) plus a deterministic alert-triage agent with its own
evaluator. Everything runs offline on the Python 3 standard library, with zero
third-party dependencies. Every dataset is synthetic, generated by a single
seeded tool (`tools/synth.py --check` proves byte-level reproducibility); no
production metric, customer name or credential appears anywhere.

The triage agent maps an alert (name, free text, metadata) to one of seven
categories and five runbooks, and returns the reasons behind its own decision.
On the 79-case bank it measures 100.00% category accuracy and
100.00% runbook match, with 100% macro F1. Those numbers are in-sample: the
weights were tuned on the same bank. The evaluator therefore also reports a
rule-family ablation and a deterministic input-perturbation stress test; under
word-order inversion accuracy falls to 94.94% and runbook match to
79.75%, which is the honest estimate of how much of the 100% generalizes.
Contributions, licensing (MIT) and privacy notes are described above.
