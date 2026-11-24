# RB-04 - Queda de throughput

**Alvo:** vazao de requisicoes ou de processamento caiu de forma relevante
sem que a disponibilidade tenha zerado. E o sintoma mais facil de ignorar,
porque quase sempre nao gera alerta de erro: o sistema parece saudavel, so esta
mais lento para processar trabalho.

Contextos, filas, topics e nomes de recurso **sinteticos**.

## 1. Gatilho

| sinal | consulta | condicao |
| --- | --- | --- |
| vazao | `sum(rate(http_server_requests_total{service="payments-api"}[10m]))` | `< 0.7 * avg_over_time(...[7d])` |
| fila | `queue_depth{namespace="messaging"}` ou `kafka_consumer_lag_messages` | `> 100000` |
| vazao de job | `rate(batch_jobs_processed_total[15m])` | `< 0.5` do esperado |
| pipeline parado | `absent_over_time(pipeline_processed_total{job="pricing-consumer"}[15m])` | `== 1` |
| alerta | `ConsumerLagHigh`, `QueueDepthHigh`, `ThroughputDropWarn` | `firing` |

Definir a baseline antes de agir: compare com a mesma hora e o mesmo dia da
semana. Comparar com "agora ha 1 hora" engana em horario de pico.

## 2. Diagnóstico (somente leitura)

```bash
# 2.1 A queda e de entrada (menos trafego chegando) ou de saida (processando menos)?
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum by (direction) (rate(gateway_requests_total[10m]))'

# 2.2 Baseline da mesma hora nos ultimos 7 dias
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query_range --data-urlencode \
  'query=sum(rate(http_server_requests_total{service="pricing-consumer"}[10m]))' \
  --data-urlencode 'start=-7d' --data-urlencode 'end=-5m' --data-urlencode 'step=1h'

# 2.3 Fila e backpressure: quem segura quem
logcli --address http://loki.observability.svc.cluster.local:3100 query \
  '{namespace="messaging", app=~"notification-worker|pricing-consumer"} |~ "backpressure|retry-after|429"' \
  --limit 30 --from -30m

# 2.4 Dependencia de dados: o upstream parou de produzir?
curl -s http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum by (topic) (rate(kafka_topic_partitions_messages_in[10m]))'

# 2.5 Confiabilidade da propria coleta (vazao zero pode ser scrape quebrado)
promtool check config /etc/prometheus/prometheus.yml
curl -s http://prometheus.observability.svc.cluster.local:9090/api/v1/targets | python3 -c \
  'import json,sys; d=json.load(sys.stdin); print("\n".join(t["labels"].get("job","?")+" "+t["health"] for t in d["data"]["activeTargets"] if t["health"]!="up"))'

# 2.6 Um item de trabalho perdido no meio do fluxo
python3 labs/lab-05-golden-signals/correlate.py --list-errors --limit 5
```

## 3. Árvore de decisão

| observacao | hipotese | acao |
| --- | --- | --- |
| entrada caiu junto com a saida, sem erro | menos demanda (campanha acabou, feriado) | nada; registrar baseline no lab-06 |
| entrada normal, saida caindo, fila crescendo | capacidade de processamento | RB-03 + escala |
| entrada normal, saida normal, fila crescendo | particionamento / hotspot de chave | balancear particoes, nao escalar cegamente |
| erros 429/retry-after de dependencia | limite do fornecedor | negociar quota, ajustar taxa de consumo |
| vazao zero e target `down` | telemetria | corrigir coleta antes de qualquer acao em producao |
| job cron com atraso acumulado | configuracao de agenda/fuso | reprocessar com idempotencia |

## 4. Ações

**Baixo risco:** medir, capturar estado de fila, salvar as consultas acima em
`/tmp/rb04-*.txt`, anunciar no canal.

**Médio risco (anunciar e observar por 15 minutos):** escalar consumidores,
aumentar paralelismo de consumo dentro do limite do partition count.

```bash
kubectl --context gke-br-sa2b -n messaging scale deploy/pricing-consumer --replicas=10
```

**ALTO RISCO / DESTRUTIVO — aprovação humana obrigatória:**

Resetar offset de fila, descartar mensagens para liberar backlog, recriar
consumer group, mudar taxa de consumo acima do limite negociado com o
fornecedor, subir paralelismo acima do numero de particoes. Reset de offset
pode **reprocessar ou perder trabalho**: em sistema financeiro isso tem
consequencia de negocio, e a decisao e humana, com nome registrado.

```bash
# o comando existe e esta aqui para o operador saber qual e o caminho formal,
# mas so roda com aprovacao humana dupla registrada no canal do incidente
kubectl --context gke-br-sa2b -n messaging exec deploy/kafka-tools -- \
  kafka-consumer-groups.sh --bootstrap-server kafka.messaging.svc.cluster.local:9092 \
  --group pricing-consumer --describe
```

## 5. Critério de saída

1. vazao dentro de 10% da baseline da mesma hora nos ultimos 7 dias;
2. fila/lag decrescendo ha pelo menos 20 minutos (nao apenas um degrau);
3. nenhuma mensagem descartada sem decisao registrada;
4. `ConsumerLagHigh`/`ThroughputDropWarn` em `resolved`;
5. custo adicional registrado (lab-07) se a solucao foi escalar.

## 6. Pós-ação

- se a causa foi volume estrutural, o plano de capacidade (lab-06) muda, nao o
  runbook;
- se a causa foi limite do fornecedor, o contrato/SLO com o fornecedor muda;
- todo reset de fila, mesmo "sem impacto", gera post-mortem (lab-03).
