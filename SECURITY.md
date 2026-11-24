# Política de segurança

Este repositório é um **laboratório de estudo** com dados sintéticos. Ele não
roda serviço algum na internet e não processa dados reais.

## Escopo

O que existe aqui: scripts Python de linha de comando, CSVs/JSONL sintéticos,
runbooks em Markdown, um `docker-compose.yml` de stack open source e uma
heurística determinística de triagem de alertas.

O que **não** existe: produção, clientes, segredos, dados de terceiros.

## Se você vai rodar a stack do lab-05

`labs/lab-05-golden-signals/docker-compose.yml` sobe Prometheus, Loki, Tempo,
Grafana e um OpenTelemetry Collector com as configurações mais simples possível.
Isso é intencional para treino e é exatamente o motivo pelo qual não pode virar
ambiente real:

- Nenhuma das cinco aplicações tem autenticação. O Grafana usa acesso anônimo
  somente-leitor. Não exponha essas portas além de `127.0.0.1`.
- Nenhum arquivo do repositório contém chave, token, senha ou credencial. Se um
  dia conter, isso é um bug: reporte.
- Os arquivos de configuração usam portas padrão dos projetos e volume somente
  leitura para as configs.

## Reportando um problema

Abra uma issue comum no repositório. Não existe canal privado de segurança
porque não há superfície de ataque: não há servidor, não há autenticação, não há
dado sensível. Se você encontrar um dado real (não sintético) perdido neste
repositório, abra a issue marcando o título com `DADO REAL` que eu removo na
hora.

## Dados sintéticos

Todo conteúdo vem de `tools/synth.py`, com seed fixa. Nomes de serviço, cluster,
namespace, IP, custo e duração são fictícios. Ver
`docs/decisoes/0001-dados-sinteticos.md`.
