# Post-mortem {{ID_INCIDENTE}}

> **Aviso de veracidade:** este documento e todos os numeros que aparecem nele
> sao **sinteticos**. As duracoes sao de exemplo e nao representam um incidente
> real, uma empresa real ou um cliente real. Servem para demonstrar o processo.
>
> Dados sinteticos: {{SINTETICO}}

| Campo | Valor |
| --- | --- |
| ID | {{ID_INCIDENTE}} |
| Servico afetado | {{SERVICO}} |
| Data do alerta (T0) | {{DATA_T0}} |
| severidade declarada | {{SEVERIDADE}} |
| redator | {{REDATOR}} |
| status | {{STATUS}} |

## 1. Resumo

{{RESUMO}}

## 2. Impacto

- Duracao do impacto ao usuario: **{{MTTR_MIN}} minutos** (do alerta a resolucao).
- Contenção declarada em: {{DURACAO_CONTENCAO_MIN}} minutos.
- Janela coberta pela timeline: {{PERIODO}}, com {{EVENTOS_TOTAL}} eventos de {{FONTES_TOTAL}} fontes.
- Pedidos afetados e receita: **nao medido aqui** — em um documento real esta secao
  usaria numeros do negocio; neste laboratorio nao ha negocio por tras, entao a
  lacuna e intencional.

## 3. Detecção

- O alerta disparou antes de qualquer reclamação humana, pelo caminho
  fast-burn (janela 1h) definido no lab-02.
- MTTD (confirmação efetiva da detecção): **{{MTTD_MIN}} minutos**.
- Reconhecimento do alerta (MTTA): **{{MTTA_RECONHECIMENTO_MIN}} minutos**.

## 4. Diagnóstico e contenção

- Tempo entre confirmar a detecção e pedir a ação de mitigação: ver tabela de
  intervalos no relatorio do `analyze.py`.
- Mitigação aplicada (MTRA): **{{MTRA_MIN}} minutos** a partir de T0.
- Tempo entre o pedido formal e a execução da mitigação (MTTM): **{{MTTM_MIN}} minutos** —
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
{{TABELA_MARCOS}}

Duracao por fase:

| fase | inicio | fim | minutos | eventos |
| --- | --- | --- | --- | --- |
{{TABELA_FASES}}

## 10. Custo de toil estimado

Ordem de grandeza a partir das premissoes declaradas no codigo, nao de apontamento
de horas real. Total: **{{TOIL_TOTAL_H}} horas-homem**.

| item | horas |
| --- | --- |
{{TABELA_TOIL}}

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
`{{ARQUIVO}}`.
