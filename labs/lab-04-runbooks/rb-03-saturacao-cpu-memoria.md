# RB-03 - Saturação de CPU e memória

**Alvo:** CPU throttled, memoria proxima do limite, OOMKilled, pressao no node ou
descritores/procs esgotados. Saturacao e o sinal que mais cedo vira "so aumentar
o limite" e esconde o problema real.

Contextos, nodes e nomes de recurso **sinteticos**.

## 1. Gatilho

| sinal | consulta | condicao |
| --- | --- | --- |
| cpu do container | `rate(container_cpu_cfs_throttled_periods_total{namespace="payments-core"}[5m])` | `> 0.25` do total de periodos |
| memoria do container | `container_memory_working_set_bytes / container_spec_memory_limit_bytes` | `> 0.90` |
| pressao no node | `kube_node_status_condition{condition="MemoryPressure",status="true"}` | `== 1` |
| disco | `1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)` | `> 0.90` |
| alerta | `NodeCPUHigh`, `MemoryPressureNode`, `OOMKilled` (lab-02/04) | `firing` |

## 2. Diagnóstico (somente leitura)

```bash
# 2.1 Quem esta consumindo, nao "quanto"
kubectl --context gke-br-sp1a top pods -n payments-core --sort-by=cpu
kubectl --context gke-br-sp1a top pods -n payments-core --sort-by=memory
kubectl --context gke-br-sp1a top nodes

# 2.2 Limites e requests declarados (conferir se o limite esta absurdo ou ausente)
kubectl --context gke-br-sp1a -n payments-core \
  get deploy payments-api -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\t"}{.resources}{\"\\n\"}{end}'

# 2.3 O consumo cresceu com o trafego ou cresceu sozinho? (vazamento nao segue curva)
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum by (pod) (container_memory_working_set_bytes{namespace="payments-core", pod!=""})'
curl -sG http://prometheus.observability.svc.cluster.local:9090/api/v1/query --data-urlencode \
  'query=sum(rate(http_server_requests_total{service="payments-api"}[5m]))'

# 2.4 Historico de restart e motivo
kubectl --context gke-br-sp1a -n payments-core \
  get pods -l app=payments-api \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\t"}{.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}'

# 2.5 Pressao no node: quem mais esta no mesmo node
kubectl --context gke-br-sp1a get pods -A -o wide --field-selector spec.nodeName=<NODE> --chunk-size=0

# 2.6 Descriptors e threads (quando o limite nao e CPU nem RAM)
kubectl --context gke-br-sp1a -n payments-core exec <POD> -- sh -c \
  'cat /proc/1/limits | grep -E "open files|max processes"; ls /proc/1/fd | wc -l'
```

## 3. Árvore de decisão

| observacao | hipotese | acao |
| --- | --- | --- |
| memoria sobe linearmente e cai em OOM, sem relacao com trafego | vazamento | preserva evidencia, restart com janela maior + acao de correcao |
| cpu throttled com pico de vazao legitimo | capacidade | RB-04 e lab-06; expandir e nao remarcar limite no susto |
| consumo alto em um pod so, outros normais | noisy neighbor / affinity ruim | realocar, nao escalar tudo |
| node em disk pressure | log/temporario | limpar com retencao declarada; ver se o collector esta retendo |
| consumo alto apos deploy | regressao de eficiencia | rollback (destrutivo) |

## 4. Ações

**Baixo risco:** coletar `top`, `describe`, limites atuais e contagem de restart
**antes** de mexer; sem evidencia previa o post-mortem nao sai do lab-03.

```bash
kubectl --context gke-br-sp1a -n payments-core describe node <NODE> > /tmp/rb03-node.txt
```

**Médio risco (aprovação do dono do serviço recomendada):** escala horizontal.

```bash
kubectl --context gke-br-sp1a -n payments-core scale deploy/payments-api --replicas=18
kubectl --context gke-br-sp1a -n payments-core patch hpa payments-api --type=merge \
  -p '{"spec":{"maxReplicas":24}}'
```

**ALTO RISCO / DESTRUTIVO — aprovação humana obrigatória:** mudar requests/limits
de CPU e memoria em producao, drenar node, remover pods, reiniciar dependencia com
estado, mexer em PDB. Cada um destes pode causar mais indisponibilidade do que a
saturacao que pretende resolver. **Duas pessoas humanas** registram a decisao no
canal do incidente antes da execucao, e a execucao e feita por quem nao escreveu
a mudanca original.

```bash
# exemplo: ajuste de limite feito por patch declarativo, com valor explicito
kubectl --context gke-br-sp1a -n payments-core patch deploy payments-api --type=merge -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"app",
    "resources":{"requests":{"cpu":"1500m","memory":"3Gi"},
                 "limits":{"cpu":"3","memory":"6Gi"}}}]}}}}'
kubectl --context gke-br-sp1a -n payments-core rollout status deploy/payments-api --timeout=300s
```

## 5. Critério de saída

1. throttling abaixo de 0.05 do total de periodos de CFS por 10 minutos;
2. `container_memory_working_set_bytes / limit < 0.80` em todos os pods;
3. nenhum `OOMKilled` novo desde a acao;
4. node sem `MemoryPressure`/`DiskPressure`;
5. SLI de latencia voltou ao alvo (saturacao raramente e o fim da cadeia).

## 6. Pós-ação

- toda mudanca de limite abre item no lab-06 para verificar se a conta de
  capacidade bate com o novo pedido;
- vazamento confirmado vira teste de stress no servico, nao "reiniciar de tempos
  em tempos";
- se a solucao foi escalar, registrar o custo no lab-07 (finops).
