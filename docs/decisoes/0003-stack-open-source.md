# ADR 0003 — Stack open source em vez de SaaS de observabilidade

- **Status:** aceito
- **Data:** 2026-11
- **Contexto do repositório:** labs/lab-05-golden-signals/docker-compose.yml

## Contexto

Os labs ensinam a ler sinais dourados, correlacionar por `request_id` e escrever
runbook. Uma plataforma comercial de observabilidade ensinaria o mesmo, mas
introduz três coisas que não são o exercício: conta, chave de API e um modelo de
custo por ingestão/cardinalidade que é decisão de procurement, não de SRE.

## Decisão

Stack composta só por projeto open source com imagem oficial e porta padrão:

| componente | imagem | porta |
| --- | --- | --- |
| coleta | `otel/opentelemetry-collector-contrib` | 4317, 4318, 8888, 8889 |
| métricas | `prom/prometheus` | 9090 |
| logs | `grafana/loki` | 3100, 3101 |
| traces | `grafana/tempo` | 3200 |
| visualização | `grafana/grafana` | 3000 |

Protocolo de entrada é OTLP, padrão aberto: trocar o backend não reescreve a
aplicação. Nenhuma configuração contém segredo; o Grafana sobe com acesso
anônimo somente-leitor porque isto é lab em `127.0.0.1` (ver SECURITY.md).

Os scripts Python do lab **não dependem** da stack: `metrics.py`, `correlate.py`
e afins trabalham sobre `data/*.jsonl`. A stack existe para ver no Grafana o que
o script já calculou. Se Docker não estiver disponível, nada no laboratório
para de funcionar.

## Consequência

- Positiva: reproduzível sem custo e sem credencial, e o preço da decisão fica
  explícito — cardinalidade de label e retenção agora são problema seu.
- Negativa: você administra cinco serviços. É proposital: ver o custo operacional
  de segurar a stack também faz parte do treino.

## Como medir que a decisão continua boa

`docker compose config -q` no diretório do lab-05 (sintaxe e resolução do
arquivo), e `python3 -m unittest discover -s tests`, que roda sem tocar na
stack.
