# Dicionário da ABT `abt.recompra_90d` (versão correta)

Gerado a partir das regras de `etl/04_abt.py` (lista `ATRIBUTOS`); o mesmo conteúdo, em CSV, é
gravado em `saida/abt/dicionario_atributos.csv`. As decisões completas entram no RDT-14 (Entrega 4).

**Pergunta.** Dado o comportamento do cliente até 30/06/2025, ele fará ao menos uma nova compra entre
01/07/2025 e 28/09/2025?

**Unidade.** Um cliente unificado (`dw.dim_cliente`, RDT-02) com ao menos um pedido, de qualquer status, até a
data de corte. A chave é `(cliente_sk, data_corte)`.

**Data de corte.** `2025-06-30`. Todo atributo usa só `fato_pedido.data_pedido_sk <= 2025-06-30` (e, nos
atributos de entrega e de atendimento, só datas de entrega e de abertura até o corte).

**Alvo `alvo_recompra_90d`.** 1 se o cliente tem ao menos um pedido de status conformado diferente de `CANCELADO`
com `data_pedido_sk` entre 2025-07-01 e 2025-09-28; 0 caso contrário. Cancelamento e recusa de pagamento não
contam como compra (RDT-04). É o único ponto do pipeline que olha para o futuro, por definição.

| Atributo | Regra (todos até 2025-06-30) | Ausente |
|---|---|---|
| `recencia_dias` | dias entre o último pedido efetivo e o corte | NULL se só há pedidos cancelados |
| `frequencia_pedidos` | nº de pedidos efetivos | 0 é a contagem verdadeira |
| `valor_monetario` | soma de `valor_total` dos pedidos efetivos (mercadoria − desconto + frete) | 0 |
| `ticket_medio` | `valor_monetario / frequencia_pedidos` | NULL se frequência 0 |
| `pedidos_ultimos_90d` | pedidos efetivos em (corte − 90 dias, corte] | 0 |
| `taxa_cancelamento` | pedidos cancelados / todos os pedidos do cliente | sempre definida |
| `pct_desconto` | Σ `valor_desconto` / Σ `valor_mercadoria` dos pedidos efetivos | NULL se não há pedido efetivo |
| `prazo_medio_entrega` | média de `dias_entrega` dos pedidos efetivos com **data de entrega ≤ corte** | NULL se nenhuma entrega registrada até o corte |
| `categorias_distintas` | nº de `categoria_nivel1` distintas nos itens dos pedidos efetivos (nulas ignoradas, RDT-07) | 0 |
| `canal_predominante` | canal conformado com mais pedidos efetivos (empate: ordem alfabética) | NULL se não há pedido efetivo |
| `ambos_sistemas` | 1 se há pedido efetivo nos dois sistemas (calculado dos fatos, não do cadastro) | 0 |
| `tempo_como_cliente_dias` | dias entre o primeiro pedido efetivo observado e o corte | NULL se não há pedido efetivo |
| `qtd_atendimentos_sac` | atendimentos ligados ao cliente pelo CPF, com `data_abertura` ≤ corte | 0 |
| `nota_media_sac` | média das notas de 1 a 5 desses atendimentos (nota 0 e vazia ignoradas, RDT-08) | NULL se não há nota |

**Ausências.** Ausência é `NULL`, não zero (NaN não é zero). Onde o zero é a contagem verdadeira, vale zero.
Nenhum valor é imputado na ABT; a decisão de imputar, se houver, cabe ao fluxo de modelagem.

## Limitações declaradas

1. **Histórico começa em 2023-01-01.** `DT_CADASTRO` e `DT_PEDIDO` não têm registros anteriores, embora o ERP exista
   desde 2016 (Semana 1). `tempo_como_cliente_dias` é o tempo desde o **primeiro pedido observado**, não o
   tempo de relacionamento real, e `recencia_dias`/`frequencia_pedidos` desconhecem compras anteriores a 2023.
2. **Status é o do retrato.** A origem não guarda a data do cancelamento. `taxa_cancelamento`, `frequencia_pedidos` e os
   demais atributos "efetivos" assumem que o status gravado já valia em 30/06/2025. Um pedido cancelado depois do
   corte aparece como cancelado nesta ABT.
3. **Nada vem de `dim_cliente`.** O cadastro pode ter sido atualizado depois do corte; por isso `ambos_sistemas`,
   `tempo_como_cliente_dias` etc. saem dos fatos.
4. **Avaliações não entram.** O NDJSON não tem CPF e o pedido que ele declara não se sustenta (RDT-13): não há atributo
   de nota de avaliação por cliente.
5. **Identidade.** A unificação de pessoas (RDT-02) usa o cadastro inteiro, não só o anterior ao corte. Ela descreve
   quem é a pessoa, não o que ela fez depois, mas é um cuidado a registrar no RDT-14.

## Verificação de ausência de vazamento

`04_abt.py --correta` constrói o esquema temporário `dw_corte`: o DW "como estaria em 30/06/2025" (sem pedidos
posteriores, com entregas posteriores tratadas como ainda não ocorridas, sem atendimentos posteriores) e calcula os
mesmos atributos nele. A asserção `04_abt_correta · atributos: valores que mudam se o DW for cortado em 30/06/2025` exige
zero diferenças. Um vazamento provocado de propósito faz dezenas de milhares de linhas divergirem, o que mostra que o
teste enxerga o problema.
