"""Definicoes dos dados sinteticos do laboratorio.

Nada aqui representa infraestrutura, clientes ou empresas reais. Os nomes de
servico, cluster, namespace e recursos sao ficticios e gerados de forma
deterministica. Ver docs/decisoes/0001.
"""

SEED_PADRAO = 42

# Nome de servico, namespace e cluster (todos ficticios).
SERVICES = [
    ("payments-api", "payments-core", "gke-br-sp1a"),
    ("checkout-service", "commerce", "gke-br-sp1a"),
    ("notification-hub", "messaging", "gke-br-sa2b"),
    ("orders-api", "commerce", "gke-br-sp1a"),
    ("ledger-api", "finance-core", "gke-br-sa2b"),
    ("api-gateway", "edge", "gke-br-sp1a"),
    ("search-indexer", "discovery", "gke-br-sa2b"),
    ("pricing-consumer", "discovery", "gke-br-sa2b"),
    ("orders-worker", "commerce", "gke-br-sp1a"),
    ("notification-worker", "messaging", "gke-br-sa2b"),
    ("storefront-web", "edge", "gke-br-sp1a"),
    ("billing-exporter", "finance-core", "gke-br-sa2b"),
]

# ------------------------------------------------------------------- lab-01
SLO_TARGET_DISPONIBILIDADE = 0.999
SLO_TARGET_LATENCIA = 0.990
LATENCIA_ALVO_MS = 400
SLO_DIAS = 24
SLO_BUCKET_MIN = 60

# Incidentes plantados: (dia, hora inicial, duracao em horas, taxa de erro,
# fracao de requisicoes acima do alvo de latencia).
SLO_INCIDENTES = [
    # (dia, hora inicial, duracao em horas, taxa de erro, taxa acima do alvo)
    (6, 3, 2, 0.075, 0.010),
    (10, 21, 2, 0.060, 0.012),
    (13, 9, 3, 0.004, 0.062),
    (19, 14, 2, 0.050, 0.004),
]

# ------------------------------------------------------------------- lab-02
BURN_INTERVAL_MIN = 5
BURN_BUCKETS = 4032           # 14 dias de serie em granulos de 5 minutos
BURN_ERRO_BASE = 0.0005
# (bucket inicial, bucket final exclusivo, taxa de erro do episodio)
BURN_INCIDENTES = [
    (900, 920, 0.030),
    (1500, 1524, 0.026),
    (2400, 2418, 0.034),
    (3960, 4032, 0.025),   # incidente em andamento no ultimo bucket da serie
]

# ------------------------------------------------------------------- lab-05
GOLDEN_REQUESTS = 2400

# ------------------------------------------------------------------- lab-06
CAPACITY_SEMANAS = 26
CAPACITY_SERVICES = [
    # (servico, carga inicial em rps, crescimento semanal absoluto,
    #  amplitude sazonal, saturacao em rps, rps por replica)
    ("payments-api", 620.0, 13.0, 0.045, 1600.0, 190.0),
    ("checkout-service", 410.0, 24.0, 0.075, 1150.0, 150.0),
    ("notification-hub", 1350.0, -0.8, 0.030, 4200.0, 310.0),
    ("search-indexer", 95.0, 1.4, 0.020, 1400.0, 120.0),
    ("billing-exporter", 240.0, -4.5, 0.050, 1900.0, 160.0),
    ("orders-worker", 320.0, -9.0, 0.060, 1500.0, 140.0),
]

# ------------------------------------------------------------------- lab-07
COST_PERIODOS = ["2026-07", "2026-08", "2026-09"]
COST_COMPONENTES = ["compute", "storage", "network", "licensing"]
COST_SERVICES = [
    # (servico, equipe, ambiente, cpu_milis, ram_gib, replicasa_base)
    ("payments-api", "time-pagamentos", "prod", 2400, 8.0, 12),
    ("checkout-service", "time-commerce", "prod", 3200, 12.0, 18),
    ("notification-hub", "time-mensageria", "prod", 1500, 6.0, 9),
    ("orders-api", "time-commerce", "prod", 2100, 8.0, 10),
    ("ledger-api", "time-financeiro", "prod", 1800, 8.0, 8),
    ("search-indexer", "time-busca", "prod", 4200, 16.0, 14),
    ("billing-exporter", "time-financeiro", "prod", 900, 4.0, 4),
    ("payments-sandbox", "time-pagamentos", "dev", 500, 2.0, 12),
    ("checkout-loadtest", "time-commerce", "staging", 800, 4.0, 14),
]

# Precos unitarios ficticios (USD), para dar forma ao modelo. NAO sao preco de
# fornecedor real: ver README do lab-07 e ADR 0001.
PRECO_CPU_CORE_MES = 29.0
PRECO_RAM_GIB_MES = 3.9
PRECO_DISK_GIB_MES = 0.12
PRECO_SNAPSHOT_GIB_MES = 0.06
PRECO_EGRESS_GIB = 0.087
PRECO_NAT_GIB = 0.045
PRECO_LB_HORAS = 0.018
PRECO_LICENSE_SEATS = 41.0
PRECO_OBS_GIB = 2.15
