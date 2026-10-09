---
title: "Relatório de Diagnóstico das Fontes — Semana 1"
lang: pt-BR
---

**INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DE MATO GROSSO — IFMT**
Departamento de Computação · Engenharia de Computação · Mineração de Dados
Prof. Orlando Júnior

# Relatório de Diagnóstico das Fontes — Semana 1

Gabriel Lemos Gomes · Lucas Peres de Lima · Marcus Vinícius Santos de Almeida

Cuiabá, 9 de outubro de 2026 · Ambiente gerado com `ESCALA=1.0` (`saida/diagnostico/00_ambiente.md`)

---

## 1 Escopo e método

Medimos as quatro fontes da Mercatto — as tabelas `CLIENTES`, `PRODUTOS`, `PEDIDOS` e `ITENS_PEDIDO` do MySQL legado, as tabelas `customer`, `category`, `product`, `orders` e `order_item` do esquema `shop`, o CSV do SAC e o NDJSON de avaliações — com seis scripts versionados em `etl/diagnostico/` (`d01` a `d06`), executados no contêiner `etl` com as conexões somente leitura de `config.py`. Cada número citado vem de um arquivo de `saida/diagnostico/`, indicado entre parênteses, e está registrado em `numeros.json`. O script-modelo `00_perfilamento.py` trabalha com amostra (`LIMIT 200000`) e, por isso, trunca `ITENS_PEDIDO`, `orders` e `order_item`; todas as contagens deste relatório agregam as tabelas inteiras, e a reconciliação de valores roda em SQL sobre todos os pedidos. Para executar o perfilamento acrescentamos `cryptography` a `etl/requirements.txt`, exigido pelo PyMySQL para autenticar no MySQL 8.

## 2 Volumes e cobertura temporal

As fontes somam 2.205.864 registros (`d01_volumes.csv`): 577.336 no legado, 1.372.388 no e-commerce, 96.140 atendimentos e 160.000 avaliações. O total desvia 0,27% do valor declarado no roteiro (≈ 2,2 milhões) e 16,1% do declarado no README (≈ 1,9 milhão); é o roteiro que corresponde ao ambiente. O CSV tem 97.518 linhas físicas para 96.140 registros, diferença que vem de quebras de linha dentro de campos.

Os dois sistemas cobrem 36 meses, de 2023-01-01 a 2025-12-30, e portanto toda a janela do alvo (`d01_volumes_periodos.md`). Antes de 01/07/2025 estão 83,13% dos pedidos do legado e 83,4% dos do e-commerce; na janela do alvo, 8,23% e 8,14%; depois dela, 8,64% e 8,45% (`d01_periodos_corte.csv`). A aquisição de março de 2024 não deixa marca no volume nem na composição: o legado registra 3.615,4 pedidos por mês antes e 3.608,4 depois; o e-commerce, 7.770,9 e 7.782,2; a participação de `SITE` passa de 35,2% para 34,7% (`d01_aquisicao_legado.csv`, `d01_aquisicao_ecommerce.csv`). O dicionário afirma que o ERP opera desde 2016, mas o primeiro cadastro e o primeiro pedido datam de 2023-01-01: o histórico anterior não foi entregue, o que limita qualquer atributo de "tempo de casa".

## 3 (a) Chaves de junção

Avaliamos CPF, e-mail e telefone para clientes, e as referências do SAC e do NDJSON para pedidos e produtos. A Tabela 1 resume a cobertura.

**Tabela 1 — Cobertura dos candidatos a chave** (`d02_cobertura.csv`, `d02_cpf.csv`)

| Chave | Sentido | Casados | Base | % |
|---|---|---:|---:|---:|
| CPF válido | CLIENTES → customer | 11.875 | 47.250 | 25,13 |
| CPF válido | customer → CLIENTES | 11.471 | 85.000 | 13,5 |
| CPF do SAC | SAC → algum cadastro | 90.155 | 96.140 | 93,77 |
| E-mail normalizado | CLIENTES ↔ customer | 0 | 47.250 | 0 |
| Telefone normalizado | CLIENTES ↔ customer | 0 | 47.250 | 0 |
| (origem, id_pedido) | SAC → pedido no sistema indicado | 96.140 | 96.140 | 100 |
| CPF do SAC × dono do pedido | SAC → cliente do pedido | 1 | 96.140 | 0 |
| order.ref | NDJSON → pedido | 160.000 | 160.000 | 100 |
| product.sku | NDJSON → produto | 160.000 | 160.000 | 100 |
| order.ref + sku | NDJSON → item do pedido | 80 | 160.000 | 0,05 |

O CPF é o único candidato viável entre cadastros. Após manter só dígitos, o legado tem 4.423 CPFs ausentes (9,36%), dois formatos (40.416 com máscara, 2.411 só dígitos) e 38.968 válidos pelo dígito verificador (82,47%); o e-commerce tem 6.855 ausentes (8,06%) e 71.178 válidos (83,74%). Valores com 11 dígitos que falham no verificador somam 3.859 no legado (8,17% dos registros) e 6.967 no e-commerce (8,2%). A unicidade difere: no legado, 1.302 CPFs válidos se repetem em 2.604 linhas; no e-commerce, só 3. A interseção é de 11.470 CPFs válidos distintos, e nos 11.876 pares de registros o nome normalizado concorda em 11.874 (99,98%), o que confirma o CPF como identificador da pessoa. E-mail e telefone não servem: cada sistema usa um único domínio de e-mail, a interseção é zero e, nos pares casados por CPF, o e-mail discorda em 11.876 de 11.876.

As referências a pedido existem, mas não se sustentam. O teste pedido pelo dicionário — `id_pedido_origem` existe no sistema indicado — passa em 100% e ninguém aponta "só para o outro sistema"; porém os identificadores colidem (todos os 130.000 IDs de pedido do legado também existem no e-commerce, `d02_chaves.md`), de modo que a existência não discrimina. O teste de consistência discrimina: o CPF do atendimento é o do dono do pedido em 1 de 96.140 casos, e a abertura do atendimento é posterior ao pedido em 49,81% dos casos, proporção esperada se data e pedido fossem independentes. No NDJSON, o produto avaliado é item do pedido referenciado em 80 de 160.000 avaliações (`d02_ndjson.csv`). Concluímos que SAC e avaliações se ligam ao cliente pelo CPF (93,77% de cobertura no SAC), não ao pedido.

## 4 (b) Heterogeneidade semântica

Distinguimos heterogeneidade sintática, estrutural e semântica (IFMT, 2026); só a terceira não se resolve por ferramenta e exige reconstruir o significado a partir do dado (SANTOS; DIAS, 2025). Selecionamos os cinco casos mais fortes (`d03_semantica.md`).

**Caso 1 — `VALOR_TOTAL` × `total_amount` ("valor do pedido").** No legado o rótulo inclui o frete; no e-commerce, não (Seção 5). A diferença média entre total e líquido dos itens é 44,28 no legado, igual ao frete médio de 44,31, e 0 no e-commerce, cujo frete médio é 39,26 (`d04_total_vs_frete.csv`). Somar os dois campos mistura grandezas.

**Caso 2 — `CANCELADO` × `canceled`/`payment_declined`.** O legado não tem status de recusa de pagamento. `CANCELADO` responde por 12,13% dos pedidos, mais próximo de `canceled` + `payment_declined` (13%) do que de `canceled` sozinho (8%) (`d03_status.csv`). Nos dois sistemas, cancelados e recusados não têm data de entrega (15.774 de 15.774; 36.403 de 36.403), têm itens e mantêm o valor cheio (média de 2.160,8 em `CANCELADO`, 2.651,28 em `canceled` e 2.644,81 em `payment_declined`, contra 2.162,58 em `ENTREGUE`). A consequência é que `CANCELADO` provavelmente agrega dois significados que o e-commerce separa, e a origem não permite desfazê-los: a coluna `motivo_cancelamento` da `dim_status` ficará nula para o legado.

**Caso 3 — `SITE` × `web`, e `channel` no NDJSON.** `SITE` não se comporta como um canal digital: seus pedidos ocorrem só entre 8h e 21h, como `LOJA` e `TELEVENDAS`, com 0% entre 22h e 8h, enquanto `web` registra 41,67% dos pedidos nessa faixa (`d03_canal.csv`). `DT_PEDIDO` é descrito como "fechamento do pedido"; os dados sugerem que, no legado, o pedido do site é registrado em horário comercial, e não no instante da compra. Além disso, `LOJA` tem frete positivo em 99,75% dos pedidos, o que indica entrega e não venda de balcão. No NDJSON, `order.channel` vale `marketplace` em 100% das avaliações, mas apenas 18,21% dos pedidos ECOM referenciados são de marketplace (`d03_canal_ndjson.csv`): ali o rótulo designa a plataforma da avaliação, não o canal da venda.

**Caso 4 — Categoria.** O legado tem 27 textos distintos byte a byte; o `GROUP BY` do MySQL mostra 24, porque a collation `latin1_swedish_ci` ignora caixa e acento e esconde 3 variantes; após normalização restam 23 rótulos não vazios e 103 produtos sem categoria (3,43%) (`d03_categoria_mapa.csv`). A taxonomia do e-commerce tem 21 nós, mas os produtos ocupam só as 15 folhas. Dos rótulos do legado, 8 mapeiam diretamente (30,53% dos produtos), 11 correspondem a uma raiz com filhos e não descem ao nível em que o e-commerce classifica (47,43%), 2 são ambíguos — `ELETRO` e `informatica e games` (10,7%) — e 3 não têm mapeamento — `DIVERSOS`, `OUTROS` e vazio (11,33%). A descrição não ajuda a desempatar: em ambos os sistemas, cada um dos 50 substantivos iniciais das descrições aparece em 15 ou mais categorias.

**Caso 5 — Notas de 1 a 5.** `nota_satisfacao` é texto, com 2.830 zeros (2,94%) e 8.682 vazios; `rating` chega como inteiro em 139.061 avaliações, como texto em 16.108 e ausente em 4.831 (`d03_notas.csv`). As distribuições de 1 a 5 são praticamente uniformes nas duas fontes (médias de 2,996 e 3,006), o que não permite afirmar nem negar que as escalas sejam a mesma; o zero do SAC não se concentra em atendimentos sem fechamento (6,36% contra 6,09% no geral), e seu significado permanece desconhecido.

Duas hipóteses do roteiro caíram. O desconto é por linha nos dois sistemas: a razão desconto/(quantidade × unitário) fica estável entre 5,73% e 5,99% no legado, enquanto a razão desconto/unitário cresce de 5,73% para 17,97% com a quantidade (`d03_desconto.csv`). E o formato do CPF não varia no tempo: a fração só de dígitos fica entre 4,87% e 5,25% em todos os anos de cadastro (`d03_cpf_tempo.csv`).

## 5 (c) Semântica dos valores

Reconciliamos, em SQL e para todos os pedidos, o total gravado com a soma dos itens, com tolerância de 0,01 (`d04_valores.py`).

**Tabela 2 — Pedidos que satisfazem cada hipótese** (`d04_resumo.csv`)

| Hipótese | Fórmula | Legado (%) | E-commerce (%) |
|---|---|---:|---:|
| H1 | bruto | 0,02 | 0 |
| H2 | bruto − desc_linha | 0,02 | **100** |
| H3 | bruto − desc_linha + frete | **96,92** | 0,02 |
| H4 | bruto + frete | 0,23 | 0 |
| H5 | bruto − desc_unid | 0 | 8,25 |
| H6 | bruto − desc_unid + frete | 9,58 | 0,01 |
| H3 com −1 tratado como 0 | | **100** | 0,02 |

Os dois campos não medem a mesma coisa. `total_amount` é o valor líquido da mercadoria, sem frete (H2 em 280.000 de 280.000 pedidos). `VALOR_TOTAL` é mercadoria líquida mais frete (H3). Os 4.003 pedidos do legado que não satisfazem H3 são exatamente os que contêm desconto `−1`: o resíduo vale −1 em 3.950 pedidos e −2 em 53, igual ao número de linhas com o sentinela (`d04_residuos_legado.csv`). O sistema que calculou o total tratou `−1` como "sem desconto"; com essa leitura, H3 explica 100% dos pedidos. O resultado é idêntico antes e depois de março de 2024, em todos os canais e em todos os status (`d04_hipoteses.csv`), e não há pedidos sem itens em nenhum sistema. Pedidos com frete negativo (362 no legado e 812 no e-commerce) também satisfazem as hipóteses vencedoras: o frete negativo entra na conta como está, e seu significado (estorno? subsídio?) não se decide pelo dado. Para a reconciliação financeira da Semana 3, a referência é 281.084.957,13 de `VALOR_TOTAL` e 734.859.099,95 de `total_amount` (`d04_somas.csv`), que não podem ser somados sem antes retirar 5.760.932,57 de frete do legado.

## 6 (d) Anomalias

Uma anomalia é quantificável agora quando aparece dentro de uma única fonte; ela só aparece depois da integração quando depende de pôr duas fontes na mesma régua — uma chave, um fuso, uma definição de cliente. Os problemas do segundo grupo são os que se propagam silenciosamente até a ABT, o que Sambasivan et al. (2021) chamam de *data cascades*.

**Tabela 3 — Anomalias quantificáveis agora** (`d05_agora.csv`)

| Fonte | Anomalia | n | % |
|---|---|---:|---:|
| Legado | Pares de clientes com mesmo e-mail, telefone e nome | 2.250 | 9,52 das linhas |
| Legado | `DT_ENTREGA = 1900-01-01` (todos `ENTREGUE`) | 1.025 | 0,79 |
| Legado | Entrega anterior ao pedido | 775 | 0,6 |
| Legado | `ITENS_PEDIDO` sem pedido | 5.868 | 1,48 |
| Legado | `VL_DESCONTO = −1` | 4.056 | 1,02 |
| Legado | `CIDADE = 'N/A'` | 933 | 1,97 |
| E-commerce | `order_item` sem pedido (IDs acima do maior pedido) | 14.709 | 1,48 |
| E-commerce | Entrega anterior ao pedido | 1.683 | 0,6 |
| Ambos | Frete negativo | 362 / 812 | 0,28 / 0,29 |
| SAC | Linhas idênticas excedentes | 1.140 | 1,19 |
| SAC | Quebra de linha em `motivo` | 1.377 | 1,43 |
| SAC | Tempo de resolução negativo | 353 | 0,37 |
| NDJSON | `rating` como texto / ausente | 16.108 / 4.831 | 10,07 / 3,02 |
| NDJSON | `submitted_at` sem offset | 31.915 | 19,95 |

Não há pedidos sem cliente, pedidos sem itens nem itens sem produto, e nenhum preço unitário ou de tabela é zero ou negativo. Os itens órfãos do e-commerce têm `order_id` a partir de 280.002, acima do maior pedido existente (280.000), compatível com a gravação assíncrona mencionada no DDL.

**Tabela 4 — Anomalias que só aparecem depois da integração** (`d05_depois.csv`)

| Anomalia | Inferior | Superior | Por que só depois |
|---|---:|---:|---|
| Registros de `CLIENTES` com par no e-commerce | 11.875 | 15.793 | exige cruzar os cadastros; o superior acrescenta pares por nome e UF quando falta CPF válido |
| Atendimentos cujo CPF está só no cadastro do outro sistema | 1.620 | 26.671 | o CSV declara o sistema; a contradição só aparece contra os dois cadastros |
| Pedidos que trocam de lado do corte ou do fim do alvo conforme o fuso | 60 | 78 | o legado não tem fuso e o e-commerce tem; o lado da fronteira depende da régua comum |
| Clientes cujo rótulo do alvo muda com o fuso | 44 | 58 | o rótulo é calculado sobre a base integrada |
| Clientes de CPF comum com compras antes do corte nos dois sistemas | 9.681 | 13.599 | cada sistema vê só parte do histórico |
| Clientes de CPF comum cujo rótulo difere entre um sistema e a visão integrada | 3.681 | 7.599 | a recompra pode ter ocorrido no outro sistema |

O limite superior de clientes comuns é frouxo por construção: entre registros com CPFs válidos e diferentes, 787 coincidem em nome e UF, ou seja, nome e UF produzem homônimos (`d05_anomalias.md`). Na janela de 20h às 4h em torno de 30/06/2025, há 71 pedidos do e-commerce e 24 do legado (`d05_fuso_fronteiras.csv`). O efeito mais forte é o histórico dividido: dos 11.409 clientes de CPF comum com histórico, 84,85% compraram nos dois sistemas antes do corte, e a média de pedidos por pessoa passa de 2,61 (só legado) ou 2,93 (só e-commerce) para 5,13 quando integrada. Sem unificação, 32,26% dessas pessoas teriam ao menos uma linha da ABT com rótulo errado.

## 7 (e) Grão

O grão é a definição explícita do que uma linha da tabela-fato representa (KIMBALL; ROSS, 2013). Verificamos no dado as condições que o sustentam (`d06_grao.md`): `ID_PEDIDO` e `order_id` são únicos em cada sistema (130.000 e 280.000 valores distintos), mas os 130.000 IDs do legado colidem com o e-commerce, de modo que a união sem o sistema teria 280.000 pedidos em vez de 410.000. O mesmo produto aparece em mais de uma linha do pedido em 195 pares no legado e 128 no e-commerce, e as duas linhas têm preços diferentes em todos os pares menos 1 e 2, respectivamente: são vendas distintas, não duplicatas.

> **Uma linha de `dw.fato_pedido` representa um pedido registrado em um dos dois sistemas de origem, identificado pelo par (sistema de origem, identificador do pedido na origem), qualquer que seja o seu status.**

A chave natural inclui o sistema porque só o par é único. Cancelados e recusados permanecem na tabela porque são pedidos — têm itens e valor — e porque a reconciliação financeira contra a origem exige todos os pedidos; excluir os não efetivos (15.774 no legado, 36.403 no e-commerce, `d06_status_abt.csv`) é decisão da ABT, tomada pela `dim_status`, e não do grão.

> **Uma linha de `dw.fato_item_pedido` representa uma linha de item tal como registrada na origem (`ID_ITEM` ou `order_item_id`), pertencente a um pedido presente em `dw.fato_pedido`.**

Agregar por (pedido, produto) misturaria linhas de preços diferentes. Os itens órfãos não entram, porque não têm pedido a que pertencer.

## 8 Questões em aberto para a Semana 2

| Questão indecidível com o dado atual | Ficha |
|---|---|
| Carga completa ou incremental: as origens não têm coluna de atualização, e itens chegam antes do pedido (14.709 órfãos) | RDT-01 |
| Unificar só por CPF válido ou aceitar nome + UF, sabendo que este gera 787 homônimos | RDT-02 |
| Qual registro sobrevive nos 2.250 pares duplicados do legado | RDT-03 |
| Se `CANCELADO` inclui recusa de pagamento; a origem não separa os dois | RDT-04 |
| Conformar `valor_total` como mercadoria + frete − desconto para os dois sistemas | RDT-05 |
| Significado do frete negativo (362 + 812) e tratamento do desconto −1 (4.056 linhas) | RDT-06 |
| Rótulos de nível raiz, ambíguos (321 produtos) e sem mapeamento (340) | RDT-07 |
| Nota 0 do SAC, `rating` ausente, CPF inválido, `DT_ENTREGA` sentinela, `CIDADE = 'N/A'` | RDT-08 |
| Fuso de `DT_PEDIDO` e das 31.915 avaliações sem offset; régua única para o corte | RDT-09 |
| Ligação de SAC e avaliações: pelo CPF, ao cliente; o vínculo com o pedido não se sustenta | RDT-13 |

## Referências

IFMT. *ETL como preparação de dados na mineração de dados: fundamentos, decisões e implicações didáticas*. Referencial teórico da disciplina de Mineração de Dados. Cuiabá: IFMT, 2026.

KIMBALL, Ralph; ROSS, Margy. *The data warehouse toolkit: the definitive guide to dimensional modeling*. 3. ed. Indianapolis: Wiley, 2013.

SAMBASIVAN, Nithya et al. "Everyone wants to do the model work, not the data work": data cascades in high-stakes AI. In: CHI CONFERENCE ON HUMAN FACTORS IN COMPUTING SYSTEMS, 2021, Yokohama. *Proceedings* [...]. New York: ACM, 2021.

SANTOS, Sarah Rúbia de Oliveira; DIAS, Célia da Consolação. Panorama das abordagens de integração de dados: um estudo da produção científica brasileira em Ciência da Informação. *Brazilian Journal of Information Science*, v. 19, p. e025012, 2025.

---

## Apêndice — Comandos de reprodução

```bash
cd ETL
printf 'ESCALA=1.0\n' > .env
docker compose up -d --build            # aguardar "ambiente pronto." em docker compose logs seed
docker compose exec etl python 00_perfilamento.py
for s in d01_volumes_periodos d02_chaves d03_semantica d04_valores d05_anomalias d06_grao; do
  docker compose exec etl python -m diagnostico.$s
done
docker compose exec etl python -m diagnostico.verificar_relatorio
```
