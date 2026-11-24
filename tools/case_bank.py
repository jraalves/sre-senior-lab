"""Banco de casos sinteticos rotulados para avaliacao do agente de triagem.

Cada caso traz rotulo explicito de:
  - categoria: capacidade | latencia | erro | configuracao | rede | dependencia | seguranca
  - sintoma: latency | error | saturation | throughput | none (define o runbook)
  - runbook esperado: derivado do sintoma (rb-00 = nenhum runbook aplica, escalar)

Os textos variam em wording, acentuacao, caixa alta e termos em ingles porque
era assim que as mensagens chegavam no chat de plantao. Casos com "hard" sao
deliberadamente ambigues: contem sinal de mais de uma categoria e a heuristica
vai errar alguns deles. Nenhum texto vem de incidente real.
"""

RB_LATENCY = "rb-01-latencia-alta"
RB_ERROR = "rb-02-taxa-de-erro"
RB_SATURATION = "rb-03-saturacao-cpu-memoria"
RB_THROUGHPUT = "rb-04-queda-de-throughput"
RB_NONE = "rb-00-escalada-humana"

CATEGORIES = [
    "capacidade",
    "latencia",
    "erro",
    "configuracao",
    "dependencia",
    "rede",
    "seguranca",
]

CAPACIDADE = [
    {"id": "CAP-01", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "NodeCPUHigh", "severity": "critical",
     "service": 0, "text": "CPU do node gke-br-sp1a-b-pool-07 em 92% ha 15 minutos; media do cluster em 84%"},
    {"id": "CAP-02", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "ContainerCPUThrottling", "severity": "warning",
     "service": 8, "text": "Throttling de CPU acima de 30% nos pods de orders-worker; cpu pressure sustentado no namespace commerce"},
    {"id": "CAP-03", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "MemoryPressureNode", "severity": "critical",
     "service": 2, "text": "Node gke-br-sa2b-a-pool-12 com 95% de memoria utilizada, kubelet proximo de evadir pods"},
    {"id": "CAP-04", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "DiskSpaceLow", "severity": "warning",
     "service": 1, "text": "Volume persistente do checkout-service com 93% de utilizacao: 11 GB livres em 160 GB"},
    {"id": "CAP-05", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "FileDescriptorLimit", "severity": "warning",
     "service": 4, "text": "Descritores de arquivo do pod ledger-api-7d9f em 96% do limite do processo"},
    {"id": "CAP-06", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "OOMKilled", "severity": "critical",
     "service": 9, "text": "Quatro pods de notification-worker reiniciaram por OOMKilled na ultima hora"},
    {"id": "CAP-07", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "ThreadPoolSaturated", "severity": "warning",
     "service": 0, "text": "Pool de threads e fila de tarefas do payments-api com 98% de ocupacao e 120 tarefas aguardando",
     "hard": "fila tambem aparece em throughput"},
    {"id": "CAP-08", "category": "capacidade", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "NodePidPressure", "severity": "info",
     "service": 7, "text": "Numero de processos no node gke-br-sa2b-c-pool-03 em 4400 dos 4915 permitidos"},
    {"id": "CAP-09", "category": "capacidade", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "KafkaConsumerLag", "severity": "critical",
     "service": 7, "text": "Lag de fila em pricing-consumer subiu de 3 mil para 2,1 milhoes de mensagens em 20 minutos"},
    {"id": "CAP-10", "category": "capacidade", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "BackpressureActive", "severity": "warning",
     "service": 6, "text": "search-indexer aplicando backpressure: taxa de ingestao caiu 60% e fila de entrada crescendo"},
    {"id": "CAP-11", "category": "capacidade", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "ConsumerGroupLag", "severity": "warning",
     "service": 11, "text": "Consumer lag acima de 300 mil mensagens no grupo billing-exporter ha 45 minutos"},
    {"id": "CAP-12", "category": "capacidade", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "HpaAtMaxReplicas", "severity": "warning",
     "service": 3, "text": "HPA de orders-api no teto de 12 replicas e requisicoes por pod acima do planejado; throughput total nao acompanhou o pico",
     "hard": "mencao a HPA puxa para configuracao"},
]

LATENCIA = [
    {"id": "LAT-01", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "P95LatencyHigh", "severity": "critical",
     "service": 0, "text": "p95 da rota /v1/payments/charge em 1,4 s contra alvo de 350 ms nas ultimas 10 janelas"},
    {"id": "LAT-02", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "P99LatencyHigh", "severity": "warning",
     "service": 1, "text": "p99 do checkout-service passou de 2,5 s, medido no proxy do service mesh"},
    {"id": "LAT-03", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "RequestDurationTrend", "severity": "warning",
     "service": 5, "text": "Duracao media das requisicoes no api-gateway 180% acima da baseline de 7 dias"},
    {"id": "LAT-04", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "LatencyDegradation", "severity": "critical",
     "service": 4, "text": "Tempo de resposta do ledger-api quatro vezes maior: p95 em 3,2 s medido no ingress; taxa de erro estavel",
     "hard": "menciona taxa de erro, mas como estavel"},
    {"id": "LAT-05", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "GrpcLatencyHigh", "severity": "warning",
     "service": 6, "text": "p95 das chamadas gRPC do search-indexer em 900 ms contra SLO de 250 ms"},
    {"id": "LAT-06", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "TtfbHigh", "severity": "warning",
     "service": 10, "text": "Tempo ate o primeiro byte da home da storefront-web subiu de 120 ms para 890 ms"},
    {"id": "LAT-07", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "TailLatencyDrift", "severity": "info",
     "service": 5, "text": "Relacao p99/p50 do api-gateway passou de 2,1 para 6,4 nas ultimas duas horas"},
    {"id": "LAT-08", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "LatencySloBurn", "severity": "warning",
     "service": 2, "text": "Queima do error budget de latencia acelerando no notification-hub: p95 fora do alvo ha 2 h"},
    {"id": "LAT-09", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "LatencySpike", "severity": "warning",
     "service": 1, "text": "Spike de latencia a partir de 14h02 no checkout-service; p95 dobrou sem mudanca de taxa de erro"},
    {"id": "LAT-10", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "ProxyQueueWait", "severity": "critical",
     "service": 5, "text": "Fila de espera do proxy do api-gateway com 4,2 s de espera media antes do upstream",
     "hard": "fila + upstream"},
    {"id": "LAT-11", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "SlowSelfSpan", "severity": "info",
     "service": 2, "text": "Traco do notification-hub mostra 1,8 s de espera dentro do proprio servico; nenhum span de dependencia lento",
     "hard": "diz dependencia para negar"},
    {"id": "LAT-12", "category": "latencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "CheckoutSlowPage", "severity": "warning",
     "service": 1, "text": "Latencia percebida no checkout subiu: renderizacao de pagina em 2,3 s na maioria das sessoes"},
]

ERRO = [
    {"id": "ERR-01", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "ErrorRateHigh", "severity": "critical",
     "service": 0, "text": "Taxa de erro HTTP 5xx do payments-api em 4,2% contra SLO de 1%"},
    {"id": "ERR-02", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "AvailabilitySloBreach", "severity": "critical",
     "service": 2, "text": "Disponibilidade do notification-hub em 98,6% nos ultimos 30 minutos, abaixo do alvo de 99,9%"},
    {"id": "ERR-03", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "Http5xxBurst", "severity": "warning",
     "service": 5, "text": "340 respostas 502 do api-gateway em 5 minutos"},
    {"id": "ERR-04", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "CrashLoopBackOff", "severity": "warning",
     "service": 1, "text": "Pod checkout-service-6b8c9d em CrashLoopBackOff: 12 reinicios em 20 minutos"},
    {"id": "ERR-05", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "UnhandledExceptions", "severity": "critical",
     "service": 4, "text": "Pico de excecoes nao tratadas no ledger-api: 1.200 por minuto contra baseline de 40"},
    {"id": "ERR-06", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "BatchJobsFailed", "severity": "warning",
     "service": 4, "text": "34% dos jobs do batch de liquidacao noturna falharam na execucao das 02:00"},
    {"id": "ERR-07", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "SilentFailures", "severity": "warning",
     "service": 6, "text": "12% das respostas do search-indexer voltaram com status 200 e payload vazio"},
    {"id": "ERR-08", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "RetriesExhausted", "severity": "critical",
     "service": 1, "text": "Retentativas esgotadas no checkout-service: 2,3% das requisicoes terminaram em falha definitiva"},
    {"id": "ERR-09", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "DeadLetterSurge", "severity": "warning",
     "service": 9, "text": "Fila de dead letter do notification-worker com 4.800 mensagens novas em 10 minutos",
     "hard": "fila puxa throughput"},
    {"id": "ERR-10", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "FailedProbes", "severity": "warning",
     "service": 3, "text": "Probe de liveness do orders-api falhando em 3 de 12 replicas"},
    {"id": "ERR-11", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "CanaryErrorRate", "severity": "info",
     "service": 0, "text": "Error rate do canary em 6,1% contra 1,1% no baseline durante a analise de progressividade",
     "hard": "canary puxa deploy/configuracao"},
    {"id": "ERR-12", "category": "erro", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "DeclineRateAnomaly", "severity": "warning",
     "service": 0, "text": "Taxa de recusa de cartao subiu de 3,8% para 9,2% sem mudanca de trafego no payments-api"},
]

CONFIGURACAO = [
    {"id": "CFG-01", "category": "configuracao", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "ImagePullBackOff", "severity": "warning",
     "service": 7, "text": "Pod pricing-consumer em ImagePullBackOff: tag v2026.11.003 inexistente no registry"},
    {"id": "CFG-02", "category": "configuracao", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "FailedScheduling", "severity": "critical",
     "service": 3, "text": "FailedScheduling no deployment orders-api: node selector gpu-hcp-40g referencia pool que nao existe no cluster",
     "hard": "selector de GPU puxa capacidade"},
    {"id": "CFG-03", "category": "configuracao", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "ResourceQuotaExceeded", "severity": "warning",
     "service": 0, "text": "Resource quota do namespace payments-experimento excedida: pedidos de CPU somam 42 nucleos com limite de 32"},
    {"id": "CFG-04", "category": "configuracao", "symptom": "saturation",
     "runbook": RB_SATURATION, "alertname": "CpuLimitMisconfigured", "severity": "warning",
     "service": 1, "text": "requests de CPU do checkout-service em 8 nucleos por pod, acima do limite do namespace; escala horizontal bloqueada",
     "hard": "fronteira classica entre capacidade e configuracao"},
    {"id": "CFG-05", "category": "configuracao", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "FeatureFlagDefaultOn", "severity": "warning",
     "service": 5, "text": "Flag de retry exponencial ativada por padrao no release 2026-47 do api-gateway; latencia subiu nas rotas afetadas",
     "hard": "deploy + latencia"},
    {"id": "CFG-06", "category": "configuracao", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "CronScheduleDrift", "severity": "info",
     "service": 4, "text": "Fuso horario errado na agenda cron do ledger-api: job disparou 3 horas antes e o processamento do dia atrasou"},
    {"id": "CFG-07", "category": "configuracao", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "HpaMinReplicasDrop", "severity": "critical",
     "service": 2, "text": "HPA do notification-hub recriado com minReplicas=1 na manutencao; replicas cairam de 8 para 1 e o throughput de entregas despencou"},
    {"id": "CFG-08", "category": "configuracao", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "IngressClassMismatch", "severity": "warning",
     "service": 1, "text": "Ingress do checkout-service recriado com ingressClassName errado; requisicoes caem no listener antigo com timeout de 60 s"},
    {"id": "CFG-09", "category": "configuracao", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "CertificateExpired", "severity": "critical",
     "service": 0, "text": "Certificado TLS do endpoint de cobranca do parceiro externo expirou; handshakes falhando com certificate has expired",
     "hard": "parceiro externo + TLS"},
    {"id": "CFG-10", "category": "configuracao", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "HelmValuesDrift", "severity": "warning",
     "service": 10, "text": "Diff de 214 linhas entre values.yaml e o cluster no release storefront; probes de readiness alterados por engano"},
    {"id": "CFG-11", "category": "configuracao", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "ConfigMapMissingKey", "severity": "warning",
     "service": 11, "text": "ConfigMap payment-rules referencia chave removida no ultimo merge; pods iniciam mas nao servem trafego"},
]

REDE = [
    {"id": "RED-01", "category": "rede", "symptom": "none",
     "runbook": RB_NONE, "alertname": "DnsResolutionFlaky", "severity": "warning",
     "service": 5, "text": "Resolucao de nome intermitente dentro do cluster: sondas de DNS do coredns falhando em 0,8% das tentativas",
     "hard": "percentual sem sintoma de ouro evidente"},
    {"id": "RED-02", "category": "rede", "symptom": "none",
     "runbook": RB_NONE, "alertname": "PacketLossZones", "severity": "warning",
     "service": 3, "text": "Perda de pacotes de 3,2% no link entre os zoneamentos br-sp1a e br-sa2b"},
    {"id": "RED-03", "category": "rede", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "RttSpike", "severity": "critical",
     "service": 5, "text": "RTT medio entre us-east1 e br-sp1a saltou de 38 ms para 210 ms; latencia das rotas do gateway subiu junto",
     "hard": "latencia e rede ao mesmo tempo"},
    {"id": "RED-04", "category": "rede", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "ConntrackFull", "severity": "warning",
     "service": 4, "text": "Tabela conntrack do node gke-br-sa2b-a-pool-05 com 96% de ocupacao; conexoes novas recusadas pelo kernel",
     "hard": "ocupacao alta puxa saturacao"},
    {"id": "RED-05", "category": "rede", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "MtuMismatch", "severity": "warning",
     "service": 6, "text": "MTU divergente entre o plugin CNI e o roteador da VPC: pacotes grandes sendo fragmentados e requisicoes lentas"},
    {"id": "RED-06", "category": "rede", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "NatPortExhaustion", "severity": "critical",
     "service": 7, "text": "Esgotamento de portas do NAT Gateway da sub-rede de saida; vazao de conexoes do pricing-consumer caiu quase a zero",
     "hard": "esgotamento puxa capacidade"},
    {"id": "RED-07", "category": "rede", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "TlsHandshakeIntermitente", "severity": "warning",
     "service": 10, "text": "Falhas intermitentes de handshake TLS no load balancer sem mudanca de certificado"},
    {"id": "RED-08", "category": "rede", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "BgpSessionDrop", "severity": "critical",
     "service": 5, "text": "Sessao BGP com o parceiro de peering caiu; trafego retraindo pelo link de backup com latencia maior"},
    {"id": "RED-09", "category": "rede", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "KubeProxyEndpoints", "severity": "warning",
     "service": 4, "text": "Endpoints do ledger-api sumiram da tabela do kube-proxy em dois nodes; requisicoes ao cluster IP retornando connection refused"},
    {"id": "RED-10", "category": "rede", "symptom": "none",
     "runbook": RB_NONE, "alertname": "EgressIcmpLoss", "severity": "info",
     "service": 2, "text": "Perda de pacotes ICMP de 12% para o gateway da sub-rede durante a janela de manutencao programada"},
]

DEPENDENCIA = [
    {"id": "DEP-01", "category": "dependencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "UpstreamTimeout", "severity": "critical",
     "service": 0, "text": "Timeout nas chamadas ao servico de antifraude do parceiro externo: 3,8% das requisicoes do payments-api sem resposta em 2 s"},
    {"id": "DEP-02", "category": "dependencia", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "ProviderHttp5xx", "severity": "warning",
     "service": 0, "text": "Provedor de pagamentos retornando 500 intermitente; pagina de status do parceiro indica degradacao regional"},
    {"id": "DEP-03", "category": "dependencia", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "BrokerUnreachable", "severity": "critical",
     "service": 2, "text": "Broker de mensageria do cluster de filas inatingivel; publicacao de eventos do notification-hub parada"},
    {"id": "DEP-04", "category": "dependencia", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "DbDeadlocks", "severity": "warning",
     "service": 3, "text": "Deadlocks e locks prolongados no Postgres do orders-api; transacoes abortando com erro"},
    {"id": "DEP-05", "category": "dependencia", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "RateLimitQuota", "severity": "warning",
     "service": 4, "text": "Limite de requisicoes do parceiro de consulta atingido: HTTP 429 em 11% das chamadas do ledger-api"},
    {"id": "DEP-06", "category": "dependencia", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "CacheUnavailable", "severity": "critical",
     "service": 6, "text": "Cluster Redis de cache indisponivel para o search-indexer; tudo passa pelo backend e a vazao de consultas caiu 45%",
     "hard": "backend lento pode ler como latencia"},
    {"id": "DEP-07", "category": "dependencia", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "SsoUnavailable", "severity": "critical",
     "service": 5, "text": "Provedor de identidade fora do ar; logins no console interno falhando com 503"},
    {"id": "DEP-08", "category": "dependencia", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "SupplierTopicStale", "severity": "warning",
     "service": 7, "text": "Topico de eventos do fornecedor de precos sem novas mensagens ha 40 minutos; vazao do pipeline caiu a zero"},
    {"id": "DEP-09", "category": "dependencia", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "AuthErrorsExternos", "severity": "critical",
     "service": 5, "text": "Taxa de erro do provedor de autenticacao externo em 12%; requisicoes chegando ao backend sem validar token",
     "hard": "taxa de erro alta e service mesh no meio"},
    {"id": "DEP-10", "category": "dependencia", "symptom": "throughput",
     "runbook": RB_THROUGHPUT, "alertname": "SmtpQueueBuildup", "severity": "warning",
     "service": 2, "text": "Servico de email do fornecedor com fila acumulada; volume de saida do notification-hub bem abaixo do normal"},
    {"id": "DEP-11", "category": "dependencia", "symptom": "latency",
     "runbook": RB_LATENCY, "alertname": "ThirdPartySpanSlow", "severity": "info",
     "service": 1, "text": "Traco mostra 1,9 s no span de saida para o servico externo de consulta de endereco; resto do fluxo em 90 ms"},
    {"id": "DEP-12", "category": "dependencia", "symptom": "none",
     "runbook": RB_NONE, "alertname": "ExternalDnsFail", "severity": "warning",
     "service": 11, "text": "Resolucao do dominio do parceiro de logistica falhando fora do cluster, sem efeito no trafego interno",
     "hard": "DNS pode ler como rede"},
]

SEGURANCA = [
    {"id": "SEC-01", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "BruteForceLogin", "severity": "critical",
     "service": 10, "text": "Pico de tentativas de login invalido no portal de parceiros: 2.400 requisicoes em 5 minutos partindo do IP 177.20.14.99"},
    {"id": "SEC-02", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "WafBlockedPattern", "severity": "warning",
     "service": 10, "text": "Regras do WAF bloquearam padrao de injecao de SQL em 138 requisicoes para a storefront-web"},
    {"id": "SEC-03", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "PortScanNode", "severity": "warning",
     "service": 8, "text": "Varredura de portas detectada no node gke-br-sp1a-b-pool-19 partindo da rede 45.91.201.0/24",
     "hard": "palavra rede aparece no texto"},
    {"id": "SEC-04", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "NewClusterRoleBinding", "severity": "warning",
     "service": 3, "text": "Novo RoleBinding concedendo cluster-admin para a conta svc-deploy-lab criada ha 6 minutos"},
    {"id": "SEC-05", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "SecretPatternLeak", "severity": "critical",
     "service": 0, "text": "Padrao de chave de API detectado em arquivo publicado em repositorio publico da organizacao"},
    {"id": "SEC-06", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "ContainerDrift", "severity": "critical",
     "service": 4, "text": "Execucao de shell dentro do container do ledger-api fora dos padroes de runtime permitidos"},
    {"id": "SEC-07", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "MetricsEndpointPublic", "severity": "warning",
     "service": 5, "text": "Porta 9090 exposta no load balancer publico sem autenticacao; metricas internas visiveis na internet"},
    {"id": "SEC-08", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "PrivilegeEscalation", "severity": "warning",
     "service": 11, "text": "Indicio de escalada de privilegio: container rodando como root com SYS_ADMIN apos o ultimo deploy do billing-exporter",
     "hard": "deploy puxa configuracao"},
    {"id": "SEC-09", "category": "seguranca", "symptom": "none",
     "runbook": RB_NONE, "alertname": "FirewallRuleChanged", "severity": "critical",
     "service": 4, "text": "Modificacao nao autorizada na regra de firewall da sub-rede de dados: porta 5432 aberta para 0.0.0.0/0",
     "hard": "mudanca de regra puxa configuracao"},
    {"id": "SEC-10", "category": "seguranca", "symptom": "error",
     "runbook": RB_ERROR, "alertname": "CredentialStuffing", "severity": "critical",
     "service": 5, "text": "Pico de login com credenciais testadas em massa gerando erro de autenticacao no api-gateway"},
]

GRUPOS = [CAPACIDADE, LATENCIA, ERRO, CONFIGURACAO, REDE, DEPENDENCIA, SEGURANCA]


def build_cases():
    """Retorna a lista final de casos com metadados de servico preenchidos.

    Deterministico: mesma ordem, mesmos valores, mesmo seed de entrada.
    """
    from data_defs import SERVICES

    cases = []
    for grupo in GRUPOS:
        for c in grupo:
            nome, namespace, cluster = SERVICES[c["service"] % len(SERVICES)]
            cases.append({
                "id": c["id"],
                "text": c["text"],
                "alertname": c["alertname"],
                "severity": c["severity"],
                "metadata": {
                    "service": nome,
                    "namespace": namespace,
                    "cluster": cluster,
                    "channel": "chat-plantao",
                },
                "label_category": c["category"],
                "label_symptom": c["symptom"],
                "label_runbook": c["runbook"],
                "notes": c.get("hard", ""),
            })
    return cases


def stats(cases):
    """Distribuicao por categoria e por runbook (usada pelo gerador na validacao)."""
    from collections import Counter

    cat = Counter(c["label_category"] for c in cases)
    rb = Counter(c["label_runbook"] for c in cases)
    return {"total": len(cases), "por_categoria": dict(cat), "por_runbook": dict(rb)}
