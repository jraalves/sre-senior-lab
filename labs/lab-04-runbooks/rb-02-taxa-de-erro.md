# RB-02 - Taxa de erro

**Alvo:** erro 5xx, falha de job, excecao nao tratada ou violacao de SLI de
disponibilidade acima do orcamento.

Ambientes, namespaces e nomes de servico sao **sinteticos**. Nenhum comando deste
arquivo aponta para infraestrutura real.

## 1. Gatilho

| sinal | consulta | condicao |
| --- | --- | --- |
| SLI de disponibilidade | `slo:requests:disponibilidade_ratio:sum5m` | `< 0.999` |
| burn rate rapido | `slo:disponibilidade:burn:ratio_rate1h` | `>= 14.4` |
| erro absoluto | `sum(rate(http_server_responses_total{status=~"5.."}[5m]))` | `> 0` sustentado |
| alerta | `SLOErrorBudgetBurnFast` (lab-02) | `firing` |

Regra de ouro: **erro com deploy recente e erro sem deploy recente sao problemas
diferentes.** Descubra qual voce tem antes de tocar em qualquer coisa.

## 2. Diagnóstico (somente leitura)

```bash
# 2.1 Houve mudanca nos ultimos 90 minutos? (responde a pergunta antes de qualquer outra)
kubectl --context gke-br-sp1a -n payments-core \
  get rollout -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.checksum}{"\t"}{.metadata.creationTimestamp}{"\n"}{end}'

# 2.2 Distribuir o erro: e em todo pod ou em alguns?
kubectl --context gke-br-sp1a -n payments-core get pods -l app=payments-api \
  --field-selector=status.phase=Running -o wide

# 2.3 Que padrao de erro domina? agrupar por mensagem e por rota
logcli --address http://loki.observability.svc.cluster.local:3100 query \
  '{namespace="payments-core", app="payments-api", level="ERROR"}' \
  --stats --from -15m

# 2.4 Erro por rota (o sufixo de rota conta mais que o total)
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum by (route) (rate(http_server_responses_total{service="payments-api",status=~"5.."}[5m]))'

# 2.5 Um request com erro, de ponta a ponta: log -> metrica -> traco
python3 labs/lab-05-golden-signals/correlate.py --list-errors --limit 5
python3 labs/lab-05-golden-signals/correlate.py --request-id <REQUEST_ID>

# 2.6 O erro e do servico ou da dependencia? ver status de terminacao do proxy
logcli --address http://loki.observability.svc.cluster.local:3100 query \
  '{namespace="edge", app="api-gateway"} |~ "status=(502|503|504)"' --limit 50 --from -15m

# 2.7 Confiabilidade do proprio pipeline de telemetria (erro 0 falso existe)
otelcli validate traces --endpoint http://otel-collector.observability.svc.cluster.local:4318
promtool check rules labs/lab-01-slo-error-budget/prometheus/slo_rules.yml
```

## 3. Árvore de decisão

| observacao | hipotese | acao |
| --- | --- | --- |
| erro comecou junto com deploy | regressao | rollback (secao 4, **destrutivo**) |
| erro concentrado em uma rota e em um downstream | dependencia | ativar fallback/circuit breaker; acionar dono |
| erro distribuido, pods reiniciando sem deploy | ambiente/recursos | RB-03 |
| erro 502/504 no proxy, upstream saudavel | rede/malha de servico | verificar CNI e certificados; RB-01 secao 3 |
| erro em job cron, sem trafego | configuracao/dado | reprocessar com idempotencia apos corrigir config |
| erro zero mas alerta ligado | telemetria quebrada | validar collector/exporter antes de celebrar |

## 4. Ações

**Baixo risco:** coleta de evidencia, snapshot de config, `logs --previous`,
`describe`, dump de metricas.

```bash
kubectl --context gke-br-sp1a -n payments-core logs deploy/payments-api \
  --since=20m --prefix > /tmp/rb02-erros.txt
```

**Médio risco (anunciar antes):** ativar circuit breaker, reduzir trafego para a
rota afetada, escalar replicas para absorver retry storm.

```bash
kubectl --context gke-br-sp1a -n payments-core scale deploy/payments-api --replicas=16
```

**ALTO RISCO / DESTRUTIVO — aprovação humana obrigatória:**

Rollback, reaplicar configuracao anterior, limpar fila, forcar restart de
dependencia com estado, mudar flag de validacao em producao. Duas pessoas
humana precisam aparecer no canal do incidente: quem executa e quem aprova.

```bash
# depois de registrar a aprovacao, o caminho e pelo pipeline, nunca por apply manual
kubectl --context gke-br-sp1a -n payments-core rollout undo deploy/payments-api
kubectl --context gke-br-sp1a -n payments-core rollout status deploy/payments-api --timeout=180s
```

## 5. Critério de saída

1. `slo:requests:disponibilidade_ratio:sum5m >= 0.999` por 15 minutos;
2. burn rate de 1h abaixo de 1x;
3. `SLOErrorBudgetBurnFast` em `resolved`;
4. nenhum pod novo em `CrashLoopBackOff`;
5. o padrao de erro que dominava desapareceu do log (verificar com a mesma
   consulta da secao 2.3, nao por impressao).

## 6. Pós-ação

- erro que consumiu orcamento vira numero no lab-01 e vira acao no lab-03;
- erro causado por dependencia vira exigencia de contrato de SLO com o fornecedor;
- erro por telemetria vira teste no lab-05, nao "sorte".
