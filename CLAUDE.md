<!-- Licenca: Apache-2.0 (ver LICENSE). Conteudo: dados sinteticoss, seed fixa. -->
# sre-senior-lab — instrucoes para agente (Claude Code / agentes compataveis)

## O que este projeto e
Laboratorio **offline** de plantao SRE: 7 labs encadeados (SLI e orcamento de erro, burn
rate, post-mortem, runbooks, golden signals com OpenTelemetry, capacidade e custo), um
agente de triagem deterministico e 88 testes. Nao ha servico externo, credencial, dado de
producao ou cliente aqui — e isso e uma decisao registrada
(`docs/decisoes/0001-dados-sinteticos.md`), nao um descuido.

## Mapa do repositorio
| Path | O que e |
|---|---|
| `labs/lab-01-slo-error-budget/slo.py` | SLI, SLO e orcamento de erro sobre CSV sintetico |
| `labs/lab-02-burn-rate-alerting/burnrate.py` | burn rate multi-janela (fast/slow) e criterio de page |
| `labs/lab-03-incidente-postmortem/analyze.py` | timeline do incidente e MTTD/MTTA/MTTR |
| `labs/lab-03-incidente-postmortem/templates/postmortem-template.md` | template de post-mortem em 11 secoes |
| `labs/lab-04-runbooks/rb-01-latencia-alta.md` | runbook canonico (formato de referencia dos demais) |
| `labs/lab-04-runbooks/rb-02-taxa-de-erro.md` | runbook de erro |
| `labs/lab-04-runbooks/rb-03-saturacao-cpu-memoria.md` | runbook de saturacao |
| `labs/lab-04-runbooks/rb-04-queda-de-throughput.md` | runbook de throughput |
| `labs/lab-05-golden-signals/metrics.py` | four golden signals a partir de requests/spans/logs |
| `labs/lab-05-golden-signals/correlate.py` | correlacao por `request_id` / `trace_id` |
| `labs/lab-05-golden-signals/docker-compose.yml` | Prometheus + Loki + Tempo + Grafana + OTel collector |
| `labs/lab-06-capacity-planning/capacity.py` | projetao de capacidade e ponto de saturacao |
| `labs/lab-07-finops/cost_model.py` | modelo de custo por servico/ambiente |
| `agent/triage.py` | heuristica deterministica R1..R9 que escolhe categoria e runbook |
| `agent/evaluate.py` | avaliacao com ablos e perturbacao; grava `agent/results/` |
| `agent/data/eval_cases.jsonl` | banco de casos rotulados (79 casos) |
| `tools/synth.py` | gera os dados sinteticos e confere reprodutibilidade |
| `skills/` | Agent Skills deste repositorio (formato oficial `SKILL.md`) |
| `.claude-plugin/marketplace.json` | empacota essas skills como plugin instalavel |
| `docs/decisoes/` | ADRs (dados sinteticos, heuristica deterministica, stack open source) |
| `tests/` | suíte unittest, incluindo `tests/test_anonimato.py` |

## Comandos
```bash
make help          # lista alvos
make test          # suíte unittest completa (88 testes)
make eval          # roda a avaliacao do agente e imprime as metricas medidas
make labs          # executa os 7 labs em sequencia
make lab04         # executa um lab isolado (lab01..lab07)
make run           # regenera dados sinteticoss e confere (--check)
python3 agent/triage.py --alertname P95LatencyHigh --text "p95 em 1,4 s"
python3 agent/triage.py --stdin < agent/data/eval_cases.jsonl
```

## Regras duras — o agente deve recusar e explicar, nao contornar
1. **Nenhum dado real.** Proibido inserir nome de cliente, empresa, hostname real, IP
   publico, credencial, DSN, ticket ou numero de producao. Os exemplos usam
   `svc-pagamentos`, `cluster-01` e enderecos gerados a partir da seed. Se um pedido
   exigir dado real, recuse e sugira a versao sintetica.
2. **Nenhuma metrica inventada.** Todo numero citado em documento vem de `make eval`
   (`agent/results/metrics.json`) ou da saida de um script do proprio lab. Sem medicao,
   escreva "nao medido" — nao estime.
3. **Stack open source por padrao.** Prometheus, Loki, Tempo, Grafana e OpenTelemetry.
   Se algo proprietario for necessario, diga o motivo e o custo de saida.
4. **Runbook e procedimento executavel:** gatilho mensuravel, diagnostico somente
   leitura, arvore de decisao, mitigacao com criterio de saida e condicao de escala.
   Quando nenhum runbook se aplica, use o rotulo `rb-00-escalada-humana` e declare o que
   esta sendo escalado.
5. **Mudar a heuristica exige antes/depois.** Rode `make eval` com e sem a mudanca e
   registre o delta em um ADR novo. Sem isso, a mudanca nao entra.
6. **Escrita limitada ao repo.** O agente nao cria repositorio, nao apaga nada fora do
   repo, nao faz push sem pedido explicito e nao toca em `.git/`.

## Skills deste repositorio
| Skill | Quando usar |
|---|---|
| `skills/sre-alert-triage` | alerta chegou, categoria e runbook desconhecidos |
| `skills/sre-runbook-drafter` | existe sintoma sem runbook, ou runbook desatualizado |
| `skills/sre-postmortem-writer` | incidente resolvido e precisa de documento sem culpa |
| `skills/sre-change-review` | revisao de uma mudanca antes de ir ao ar |
