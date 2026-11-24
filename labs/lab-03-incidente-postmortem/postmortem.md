<!-- gerado por labs/lab-03-incidente-postmortem/analyze.py --write-postmortem; nao editar a mao -->

# Post-mortem INCT-2026-0042 (sintetico)

> **Aviso de veracidade:** este documento e todos os numeros que aparecem nele
> sao **sinteticos**. As duracoes sao de exemplo e nao representam um incidente
> real, uma empresa real ou um cliente real. Servem para demonstrar o processo.
>
> Dados sinteticos: sim - todas as duracoes, nomes e numeros deste documento sao de exemplo, gerados por tools/synth.py (seed 42)

| Campo | Valor |
| --- | --- |
| ID | INCT-2026-0042 (sintetico) |
| Servico afetado | payments-api e checkout-service (namespaces payments-core e commerce) |
| Data do alerta (T0) | 2026-10-01T14:00:00Z (referencia sintetica da serie) |
| severidade declarada | S1 - degradacao parcial de disponibilidade com impacto em transacoes |
| redator | SRE de plantao (papel), revisado pelo tech lead da plataforma |
| status | rascunho pronto para revisao blameless |

## 1. Resumo

Na referencia sintetica adotada, uma mudanca de configuracao no componente de validacao de assinatura passou a rejeitar parte das requisicoes de pagamento. O alerta de queima acelerada de error budget abriu o incidente: foram 29 minutos para confirmar a deteccao, 101 minutos ate a mitigacao aplicada (reversao de configuracao, com aprovacao humana obrigatoria) e 152 minutos ate a resolucao. Nao houve perda de dados nem corrupcao de estado.

## 2. Impacto

- Duracao do impacto ao usuario: **152 minutos** (do alerta a resolucao).
- Contenção declarada em: 118 minutos.
- Janela coberta pela timeline: T-150 min a T+360 min, com 44 eventos de 17 fontes.
- Pedidos afetados e receita: **nao medido aqui** — em um documento real esta secao
  usaria numeros do negocio; neste laboratorio nao ha negocio por tras, entao a
  lacuna e intencional.

## 3. Detecção

- O alerta disparou antes de qualquer reclamação humana, pelo caminho
  fast-burn (janela 1h) definido no lab-02.
- MTTD (confirmação efetiva da detecção): **29 minutos**.
- Reconhecimento do alerta (MTTA): **5 minutos**.

## 4. Diagnóstico e contenção

- Tempo entre confirmar a detecção e pedir a ação de mitigação: ver tabela de
  intervalos no relatorio do `analyze.py`.
- Mitigação aplicada (MTRA): **101 minutos** a partir de T0.
- Tempo entre o pedido formal e a execução da mitigação (MTTM): **13 minutos** —
  inclui a **aprovação humana obrigatória** para a ação destrutiva (reversão de
  configuração em produção).

## 5. Causa raiz

Causa direta: mudança de configuração aplicada sem o pre-requisito documentado do
componente de chaves, fazendo a validação de assinatura falhar em uma parte do
tráfego e retardando o resto.

Causas de contribuição (5 porquês, versão sintética):

1. **Por que a validação falhou?** Uma flag nova foi habilitada sem a rotação
   completa das chaves que ela exige.
2. **Por que a rotação não aconteceu?** Porque o runbook de aplicação da
   configuração não lista a rotação como pre-requisito.
3. **Por que o runbook não lista?** Porque a mudança foi tratada como
   configuração de baixo risco, sem revisão de quem maintaina o componente.
4. **Por que não houve revisão?** Porque o pipeline de configuração não separa
   mudança de flag de mudança de chave.
5. **Por que o pipeline não separa?** Porque essa distinção nunca foi
   formalizada num critério de risco — lacuna de processo, não de ferramenta.

## 6. O que funcionou bem

- Deteção automatica por alerta de queima acelerada, sem depender de usuario final.
- Correlacao por `X-Request-Id` entre log, metrica e traco reduziu o tempo de
  diagnostico para identificar o componente de assinatura.
- A decisao de reverter em vez de rotacionar chaves durante o incidente encurtou
  a contencao.

## 7. O que nao funcionou bem

- Quarenta e quatro minutos entre o primeiro sinal de degradacao no p95 e o
  alerta, porque o alerta de latencia estava em outra janela de avaliacao.
- Vinte e nove minutos entre confirmar a deteccao e pedir a mitigacao, a maior
  parte deles lendo documentacao do componente de chave.
- A aprovacao da reversao dependeu de uma pessoa especifica estar disponivel.

## 8. Acoes

| # | Acao | Tipo | Dono (papel) | Prioridade |
| --- | --- | --- | --- | --- |
| 1 | Incluir rotacao de chave como pre-requisito no runbook de aplicacao de config | Preventiva | Plataforma de chaves | P1 |
| 2 | Separar no pipeline mudanca de flag de mudanca de material criptografico | Detetive | CI/CD | P1 |
| 3 | Deixar o alerta de latencia com janela que pegue degradacao de 40 min | Detetive | SRE | P2 |
| 4 | Definir duas pessoas com contexto para aprovar reversao em producao | Corretiva | Lideranca tecnica | P2 |
| 5 | Automatizar o calculo deste post-mortem a partir da timeline | Corretiva | Ferramental | P3 |

Em um documento real, cada acao teria link para um item de tracker e prazo com
data; aqui os itens ficam no nivel de proposta porque nao existe tracker atras.

## 9. Metricas de tempo

Marcos localizados automaticamente na timeline (`offset_min` a partir do alerta):

| marco | offset | descricao |
| --- | --- | --- |
| alerta | +0 min | alerta disparado |
| reconhecimento | +5 min | primeiro aceite humano do alerta |
| registro | +7 min | registro formal do incidente aberto |
| confirmacao deteccao | +29 min | confirmacao do momento de deteccao efetiva |
| inicio diagnostico | +35 min | primeiro evento de diagnostico |
| pedido mitigacao | +88 min | solicitacao formal de acao de mitigacao |
| aprovacao | +94 min | aprovacao humana da acao destrutiva |
| mitigacao | +101 min | acao de mitigacao executada |
| contencao | +118 min | incidente declarado contido |
| recuperacao sli | +130 min | SLI de volta dentro do alvo |
| resolucao | +152 min | incidente encerrado |
| fim pos incidente | +360 min | ultimo evento de follow-up registrado |

Duracao por fase:

| fase | inicio | fim | minutos | eventos |
| --- | --- | --- | --- | --- |
| pre-incidente | -02:30 | -00:30 | 120 | 10 |
| deteccao | +00:00 | +00:29 | 29 | 7 |
| diagnostico | +00:35 | +01:28 | 53 | 8 |
| contencao | +01:34 | +01:58 | 24 | 4 |
| recuperacao | +02:10 | +02:24 | 14 | 3 |
| resolvido | +02:32 | +02:32 | 0 | 1 |
| pos-incidente | +02:48 | +06:00 | 192 | 11 |

## 10. Custo de toil estimado

Ordem de grandeza a partir das premissoes declaradas no codigo, nao de apontamento
de horas real. Total: **78.95 horas-homem**.

| item | horas |
| --- | --- |
| responders janela | 8.11 h |
| war room | 12.67 h |
| stakeholders | 4.17 h |
| reunioes pos incidente | 24.00 h |
| escrita postmortem | 10.00 h |
| execucao acoes | 20.00 h |

Detalhamento das premissoes e de como cada numero foi obtido esta no rodape do
relatorio gerado por `analyze.py --report`.

## 11. Como este documento foi produzido

```bash
python3 tools/synth.py --only timeline
python3 labs/lab-03-incidente-postmortem/analyze.py --write-postmortem
python3 labs/lab-03-incidente-postmortem/analyze.py --check-postmortem
```

Nenhum numero desta secao foi digitado a mao: os tokens `{{ CHAVE }}` do
template sao substituidos pelos valores calculados pelo script sobre
`labs/lab-03-incidente-postmortem/data/timeline.csv`.
