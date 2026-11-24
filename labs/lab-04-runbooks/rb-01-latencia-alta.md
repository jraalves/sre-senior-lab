# RB-01 - Latência alta

**Alvo:** um serviço do namespace de pagamentos está respondendo acima do alvo de
latencia (SLI p95/p99 estourado ou queima de orcamento de latencia acelerando).

Escrito para ser seguido em terminal. Todo comando abaixo usa contextos,
namespaces e nomes de servico **sinteticos** (`payments-core`, `commerce`,
`gke-br-sp1a`): nada aqui aponta para ambiente real de organizacao alguma.

## 1. Gatilho

Dispara quando **qualquer** item abaixo for verdadeiro por 2 avaliacoes seguidas:

| sinal | consulta | condicao |
| --- | --- | --- |
| SLI de latencia | `slo:requests:latencia_ratio:sum5m` | `< 0.99` |
| burn rate lento | `slo:disponibilidade:burn:ratio_rate24h / slo:disponibilidade:burn:ratio_rate14d` | `>= 1` na janela de latencia |
| p95 absoluto | `histogram_quantile(0.95, sum by (le) (rate(http_server_duration_milliseconds_bucket[10m])))` | `> 400` |
| alerta | `LatencySloBurnWarn` (ver lab-02) | `firing` |

Antes de comecar: anote o `alertname`, o `service`, o `namespace` e o momento da
primeira série (`activeAt`). Sem isso a linha do tempo do incidente nao fecha.

## 2. Diagnóstico (5 a 10 min, somente leitura)

Ordem deliberada: trafego antes de dependencia, dependencia antes de codigo.

```bash
# 2.1 Confirmar que o sinal e real e nao um artefato de scrape
kubectl --context gke-br-sp1a -n payments-core \
  get deploy payments-api -o wide
kubectl --context gke-br-sp1a -n payments-core \
  get pods -l app=payments-api -o wide

# 2.2 Golden signals do servico na janela do alerta (Prometheus local)
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=histogram_quantile(0.95, sum by (le) (rate(http_server_duration_milliseconds_bucket{service="payments-api"}[5m])))'

# 2.3 O volume de trafego mudou? (pico legitimo vira lab-06, nao incidente)
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum(rate(http_server_requests_total{service="payments-api"}[10m]))'

# 2.4 A latencia esta no proprio servico ou numa dependencia? Traco de um request.
#      request_id e o X-Request-Id de uma requisicao lenta do log abaixo.
otelcli traces fetch --endpoint http://otel-collector.observability.svc.cluster.local:4318 \
  --trace-id <TRACE_ID> --output json

# 2.5 Uma requisicao lenta concreta, com request_id e trace_id
logcli --address http://loki.observability.svc.cluster.local:3100 query \
  '{namespace="payments-core", app="payments-api"} |~ "duration_ms=[0-9]{4}"' \
  --limit 20 --from -15m

# 2.6 Validar a sintaxe das regras que geram o sinal usado acima
promtool check rules labs/lab-01-slo-error-budget/prometheus/slo_rules.yml
promtool check rules labs/lab-02-burn-rate-alerting/prometheus/alerts.yml
```

Leitura esperada: `spans.jsonl`/Tempo mostra em qual span o tempo esta sendo
gasto. Se o span filho (dependencia) concentra o tempo, va para o RB-02 ou
escale para o dono da dependencia. Se o tempo esta no span proprio, siga.

## 3. Árvore de decisão

| observacao | hipotese | proximo passo |
| --- | --- | --- |
| p95 alto + CPU/mem do pod acima de 85% | saturacao | aplicar RB-03 |
| p95 alto + span de dependencia lento | dependencia externa | RB-02 + acionar time da dependencia |
| p95 alto apos deploy (diff de revisoes nos ultimos 60 min) | regressao de codigo/config | rollback (secao 4) |
| p95 alto + vazao subindo alem do planejado | capacidade | lab-06 / expansao (secao 4) |
| p95 alto + cache hit ratio caindo | camada de cache | verificar TTL e eviction, nao o app |

## 4. Ações

**Baixo risco, reversível, sem aprovação humana obrigatória:**

```bash
# coletar evidencia antes de mexer
kubectl --context gke-br-sp1a -n payments-core describe pod <POD> > /tmp/rb01-describe.txt
kubectl --context gke-br-sp1a -n payments-core logs <POD> --previous --tail=500 > /tmp/rb01-logs.txt
```

**Média risco (anunciar no canal de plantao antes):**

```bash
# aumentar replicas para absorver o pico enquanto o diagnostico continua
kubectl --context gke-br-sp1a -n payments-core scale deploy/payments-api --replicas=14
```

**ALTO RISCO / DESTRUTIVO — aprovação humana obrigatória:**

Rollback de deploy, mudanca de feature flag em producao, alteracao de limite de
rate limit, restart de estado em dependencia com estado. Regra do laboratorio:
**duas pessoas humanas** (quem executa + quem aprova, ambas com contexto)
precisam registrar no canal de incidentes antes de executar.

```bash
# exemplo do caminho de rollback (pipeline declarativo, nao apply manual)
kubectl --context gke-br-sp1a -n payments-core \
  rollout history deploy/payments-api
kubectl --context gke-br-sp1a -n payments-core \
  rollout undo deploy/payments-api --to-revision=<REVISAO_ANTERIOR>
```

## 5. Critério de saída

O runbook se encerra quando **todos** estes itens forem verdadeiros:

1. `slo:requests:latencia_ratio:sum5m >= 0.99` sustentado por 15 minutos;
2. `LatencySloBurnWarn` em `resolved` (nao apenas `inactive` por instabilidade de janela);
3. sem pods em `CrashLoopBackOff` ou `OOMKilled` novo desde a acao;
4. o burn rate de 1h voltou abaixo de 1x;
5. linha do tempo do incidente atualizada com o horario de cada acao.

Se apos 30 minutos o SLI nao voltou, **pare de tentar**: declare incidente,
chame o dono do servico e volte para a secao 2 com mais gente.

## 6. Pós-ação

- Registrar no tracker: sintoma, causa provavel, acao tomada, efeito medido.
- Se a causa foi mudanca, vincular o diff da mudanca e abrir acao no lab-03.
- Se a causa foi volume, levar o numero para o lab-06 (capacity) em vez de
  deixar o cluster com replicas extras "por garantia".
