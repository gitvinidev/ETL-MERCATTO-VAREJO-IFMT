# Registro de Decisões de Transformação (RDT)

**Equipe:** Gabriel Lemos Gomes · Lucas Peres de Lima · Marcus Vinícius Santos de Almeida
**Disciplina:** Mineração de Dados · IFMT · 2026/2 · Prof. Orlando Júnior
**Estado:** fichas RDT-01 a RDT-15, tabela-resumo e reflexão redigidas e conferidas pela equipe (parada obrigatória do item 4.6 cumprida).

> Este arquivo é **gerado** por `diagnostico/renderiza_rdt.py` a partir de
> `etl/rdt/RDT.template.md`. Cada número vem de `saida/rdt/registros_afetados.json`
> (gerado por `diagnostico/rdt_registros_afetados.py`) ou, quando indicado, de
> `saida/diagnostico/numeros.json` (Semana 1). Nenhum número foi digitado à mão.
> Para alterar o texto, edite o modelo e gere de novo.

**Convenções.** *Registros afetados* são os que a decisão alterou, descartou ou reclassificou;
o percentual usa como base a tabela de origem indicada em cada ficha. "Asserção" é o par
`etapa · nome` gravado em `qa.execucao_assercao`. As decisões partem das da Semana 1
(`relatorio/semana1/notas_para_defesa.md`, D1 a D10) e as mantêm; as que mudam estão
indicadas.

**Camadas.** `stg` guarda a cópia fiel das origens. `cnf` guarda a camada conformada
produzida pela etapa 2 (criada pelo script, porque o DDL de `dw` está congelado e não tem
colunas para os indicadores que as fichas exigem). O esquema estrela `dw` é carregado a
partir de `cnf` na etapa 3.

---

## RDT-01 · Carga completa ou incremental

**Etapa:** 01_extracao.

**(a) O que o dado mostrava.** Nenhuma das duas origens traz coluna de atualização: foram
procuradas colunas com nomes do tipo *updated*, *modified*, *atualizado*, *versão*, e o
resultado é 0. As únicas datas são de evento
(`DT_PEDIDO`, `placed_at`, `DT_CADASTRO`), que não mudam quando o pedido muda de status. Os
itens chegam antes do pedido: há 20.577 itens sem pedido
(1,48% das linhas de item), todos com identificador de pedido
acima do maior pedido existente. O `00_perfilamento.py` usa `LIMIT 200000` e por isso deixa de
ver 1.072.453 registros
(48,62% do total), em `ITENS_PEDIDO`
(197.086), `orders` (80.000) e
`order_item` (795.367). Volume total das quatro fontes:
2.205.864 registros (`saida/extracao/contagens_stg.csv`).

**(b) Alternativas consideradas.**

1. *Incremental por data do pedido* (`DT_PEDIDO`/`placed_at` maior que a última carga).
   Descartada: o pedido muda de status e de data de entrega depois de criado, e a data do
   pedido não muda. O incremental nunca veria essas atualizações. Também não veria o item
   que chega depois do pedido.
2. *Incremental por maior identificador.* Descartada: capta linhas novas, mas não alterações
   de linhas existentes, e perde os itens que chegam com atraso para pedidos antigos.
3. *Captura de mudanças pelo log do banco (CDC).* Inviável: as credenciais são somente leitura
   e o enunciado proíbe tocar nas origens.
4. *Carga completa a cada execução, recriando a `stg`.*

**(c) Decisão e justificativa.** Alternativa 4. Sem coluna de atualização não há critério
de mudança defensável, e o volume (2.205.864 registros) cabe numa leitura completa em
fluxo. A carga completa também é a que torna a etapa idempotente: `DROP` + `CREATE` + `COPY`,
o que permite a reexecução do zero exigida no Entregável 5. A diferença para o perfilamento
está escrita no cabeçalho de `01_extracao.py`: aqui não há `LIMIT`.

**(d) O que se perde.** O histórico de versões de cada linha: cada carga substitui a anterior,
e não é possível saber o que mudou entre duas cargas. A carga completa também não escala se o
volume crescer ordens de grandeza. Aceitamos as duas perdas porque o projeto lida com um
retrato único das origens.

**(e) Registros afetados.** Todos: 2.205.864 registros (100% da base).
Nenhuma linha é descartada na extração.

**(f) Asserção associada.** `01_extracao · linhas <fonte>.<tabela>` (uma por tabela, 11 no
total: contagem da `stg` igual a `COUNT(*)` na origem); `01_extracao · colunas com contagem não
nula divergente: <tabela>` e `colunas com soma divergente: <tabela>` (por coluna, origem contra
`stg`). A conferência com o diagnóstico da Semana 1 é feita por
`diagnostico/e01_conferencia_stg.py` (`saida/diagnostico/e01_stg_vs_d01.csv`).

---

## RDT-02 · Identidade do cliente entre os dois sistemas

**Etapa:** 02_transformacao · `unifica_clientes`.

**(a) O que o dado mostrava.** O CPF é a única ponte direta (e-mail e telefone têm interseção
zero, Semana 1). Em `CLIENTES` faltam 4.423 CPFs
(9,36%) e 3.859 têm dígito
verificador inválido (8,17%); em `customer`, faltam
6.855 (8,06%) e
6.967 são inválidos (8,20%).

- **CPF válido igual nos dois cadastros:** 11.876 pares, e o nome
  normalizado discorda em 2.
- **CPF inválido igual nos dois cadastros:** 1.173 pares, e nome e
  UF concordam em 1.173. O erro de dígito é, portanto,
  o mesmo digitado nos dois sistemas, e o CPF inválido continua identificando a pessoa. No SAC,
  93,90% dos CPFs inválidos encontram um cadastro, taxa
  igual à dos válidos (93,75%).
- **Colisões:** 4 CPFs válidos pertencem a pessoas de nomes diferentes.
- **Nome + UF não identifica:** entre registros com CPF válido dos dois lados, a chave nome + UF
  gera 12.813 pares, dos quais só
  11.469 têm o mesmo CPF; 1.344 são falsos
  (precisão de 89,51%), e **nenhuma** chave é única nos dois cadastros
  (0). Acrescentando a cidade: 11.888
  pares, 650 falsos (precisão de 94,53%),
  também sem chave única (0).

**(b) Alternativas consideradas.**

1. *Só CPF com dígito verificador válido.* Simples e precisa, mas ignora os
   1.173 pares cujo CPF inválido é o mesmo nos dois lados.
2. *CPF de 11 dígitos (válido ou não) com guarda de nome (e de UF, se inválido).*
3. *Alternativa 2 mais nome + UF (ou nome + UF + cidade) para quem não tem CPF utilizável.*
4. *E-mail ou telefone.* Impossível: interseção zero.

**(c) Decisão e justificativa.** Alternativa 2, em três regras de pareamento gravadas na
dimensão (`regra_pareamento`): `CPF_VALIDO_NOME` (mesmo CPF válido e mesmo nome normalizado),
`CPF_INVALIDO_NOME_UF` (mesmo CPF inválido, mesmo nome e mesma UF) e, dentro do legado,
`DUPLICATA_LEGADO` (RDT-03). Respostas às perguntas do esqueleto:
(a) o CPF inválido serve para parear *desde que* nome e UF confirmem, porque nos pares observados
a concordância é total; (b) nome + UF não é usado, pela estimativa de falsos positivos acima:
sem nenhuma chave única, a regra escolheria entre homônimos; (c) o erro mais grave aqui é fundir
duas pessoas, porque o rótulo da ABT passa a refletir o histórico de duas e a campanha deixa de
alcançar uma delas; manter um duplicado também erra o rótulo, mas apenas na parte da pessoa cujo
histórico ficou dividido, e é um erro reversível (basta pareá-los depois, com mais informação);
(d) as duplicatas internas são tratadas antes, pela regra `DUPLICATA_LEGADO`. Quando o mesmo CPF
aparece com nomes diferentes (colisão), ninguém é fundido, e o CPF fica só com o componente de mais
registros; em empate, com nenhum.

**(d) O que se perde.** (i) Pessoas sem CPF utilizável não são pareadas entre os sistemas
(10.462 pessoas, 8,91%), e o histórico delas
continua dividido; a regra por nome + UF alcançaria mais 4.359
pares candidatos, mas sem como escolher entre homônimos. (ii) A confiança no pareamento
depende de a pessoa ter digitado o mesmo nome nos dois sistemas; apelidos ou abreviações não
seriam reconhecidos. (iii) Na colisão de CPF, 8 pessoas
(0,01%) estão envolvidas: o CPF fica com a que tem mais registros
e, em empate, com nenhuma, de modo que alguém pode perder um CPF que era seu. (iv) Não se sabe quantas fusões estariam erradas: o CPF não é verificado por fonte
externa.

**(e) Registros afetados.** 132.250 registros de cliente avaliados
(`CLIENTES` + `customer`). 14.854 deles
(11,23%) deixam de ser uma linha própria, e restam
**117.396 pessoas** (88,77% dos registros). Por origem:
12.604 nos dois sistemas (10,74%),
32.396 só no legado (27,60%) e
72.396 só no e-commerce (61,67%). Por regra:
`CPF_VALIDO_NOME` 10.865 pessoas;
`CPF_INVALIDO_NOME_UF` 1.078;
`DUPLICATA_LEGADO` isolada 605; combinações com a duplicata:
1.501 (com CPF válido) e
144 (com CPF inválido); sem regra:
103.203.

**(f) Asserção associada.** `02_transformacao · dim_cliente: CPF válido duplicado entre pessoas`;
`cliente: pessoas com nomes normalizados distintos`; `cliente: CPF conformado com tamanho diferente
de 11`; `cliente: origem_unificacao`; `cliente: registros de origem na ponte`;
`cliente: (sistema, id) único na ponte`.

---

## RDT-03 · Duplicatas internas do legado

**Etapa:** 02_transformacao · `unifica_clientes` (regra `DUPLICATA_LEGADO`).

**(a) O que o dado mostrava.** 2.250 pares de registros de `CLIENTES`
com o mesmo e-mail, o mesmo telefone e o mesmo nome (4.500 registros,
9,52% da tabela). Em 1.302 pares o CPF
válido também é igual; nos outros 948 pelo menos
um lado não tem CPF válido. Em 1.987 pares, **os dois**
registros têm pedidos.

**(b) Alternativas consideradas.**

1. *Não tratar*, deixando as duas pessoas na dimensão.
2. *Descartar um dos registros e os pedidos dele.* Apaga vendas reais.
3. *Descartar um registro e reatribuir seus pedidos ao outro.* Perde o rastro de que existiam
   dois cadastros.
4. *Fundir*: um sobrevivente fornece os atributos; a tabela-ponte (`cnf.cliente_ponte`) guarda os
   dois identificadores de origem, com o papel `SOBREVIVENTE`/`ABSORVIDO`.

**(c) Decisão e justificativa.** Alternativa 4. Como nos pares com pedidos de ambos os lados o
histórico está dividido entre os dois cadastros, tratá-los como duas pessoas dividiria
recência e frequência na ABT. Sobrevivente: o registro com CPF válido; em empate, o mais completo;
em novo empate, o menor `ID_CLIENTE`. Os três campos que definem o par (e-mail, telefone, nome) são
iguais nos 2.250 casos, o que torna a fusão segura.

**(d) O que se perde.** O que diferencia os dois registros (grafia do nome, máscara do CPF ou o
CPF presente só num deles) fica só nos dados de `stg`; a dimensão mantém o valor do sobrevivente. A
existência do cadastro duplicado só aparece na ponte. Não sabemos se algum dos pares seria, na
realidade, duas pessoas com mesmo e-mail, telefone e nome (improvável, mas não demonstrável).

**(e) Registros afetados.** 2.250 registros absorvidos
(4,76% de `CLIENTES`) e
6.241 pedidos reatribuídos ao sobrevivente
(4,80% dos pedidos do legado).

**(f) Asserção associada.** `02_transformacao · cliente: registros de origem na ponte`
(todo registro pertence a uma pessoa), `cliente: (sistema, id) único na ponte` e
`pedido: sem cliente_key` (nenhum pedido ficou sem pessoa depois da fusão).

---

## RDT-04 · Conformação de status, incluindo a recusa de pagamento

**Etapa:** 02_transformacao · `conforma_status`.

**(a) O que o dado mostrava.** O legado não tem recusa de pagamento: `CANCELADO` responde por
12,13% dos pedidos
(15.774). No e-commerce, `canceled` tem
8,00% (22.413)
e `payment_declined` 5,00%
(13.990), juntos
13,00% (`saida/diagnostico/d03_status.csv`). Nos dois
sistemas, cancelados e recusados não têm data de entrega, têm itens e mantêm o valor cheio.

| Sistema | Status de origem | Status conformado | Motivo | Pedidos | % do sistema |
|---|---|---|---|---:|---:|
| LEGADO | ENTREGUE | ENTREGUE | – | 101.192 | 77,84% |
| LEGADO | EM TRANSITO | EM_TRANSITO | – | 7.798 | 6,00% |
| LEGADO | SEPARACAO | EM_PROCESSAMENTO | – | 5.236 | 4,03% |
| LEGADO | CANCELADO | CANCELADO | **nulo** (não distingue) | 15.774 | 12,13% |
| ECOM | delivered | ENTREGUE | – | 207.204 | 74,00% |
| ECOM | shipped | EM_TRANSITO | – | 22.375 | 7,99% |
| ECOM | processing | EM_PROCESSAMENTO | – | 14.018 | 5,01% |
| ECOM | canceled | CANCELADO | CANCELAMENTO | 22.413 | 8,00% |
| ECOM | payment_declined | CANCELADO | PAGAMENTO_RECUSADO | 13.990 | 5,00% |

**(b) Alternativas consideradas.**

1. *Mapear `payment_declined` para `CANCELADO`, sem motivo.* Simples; apaga a distinção justamente
   onde a origem a faz.
2. *Dois status conformados, `CANCELADO_CLIENTE` e `CANCELADO_PAGAMENTO`, com o legado sem classe.*
   Cria uma terceira categoria implícita ("cancelado, não sei qual") que cada análise teria de tratar.
3. *Um status conformado `CANCELADO` e uma coluna `motivo_cancelamento`, preenchida só onde a origem
   distingue.* É o desenho que o DDL de `dim_status` já prevê.

**(c) Decisão e justificativa.** Alternativa 3. Os quatro status conformados são `ENTREGUE`,
`EM_TRANSITO`, `EM_PROCESSAMENTO` e `CANCELADO`. `SEPARACAO` (legado) foi equiparado a `processing`
(e-commerce): ambos são pedidos já aceitos e ainda não despachados. **Definição de compra para o
alvo (RDT-14):** conta como compra todo pedido de status conformado diferente de `CANCELADO`.
Recusa de pagamento e cancelamento não contam, porque nada foi vendido nem entregue. Esta
alternativa mantém o fato completo (a reconciliação financeira exige todos os pedidos) e deixa a
decisão sobre o que é compra para a ABT, no filtro sobre `dim_status`.

**(d) O que se perde.** No legado, a distinção entre cancelamento e recusa de pagamento é
irrecuperável: 15.774 pedidos (12,13%
do legado) ficam com motivo nulo. Qualquer análise por motivo é assimétrica entre os sistemas. Que
`CANCELADO` seja soma de cancelamento e recusa é hipótese, apoiada só na proporção (12,13% do legado contra
13,00% do e-commerce); o dado não a prova. A equiparação `SEPARACAO` = `processing` também é uma suposição de
significado. Contar `EM_PROCESSAMENTO` como compra pode errar se o pedido vier a ser cancelado
depois do retrato dos dados.

**(e) Registros afetados.** Os 410.000 pedidos passam pelo mapa. Cancelados conformados:
52.177 (12,73%); recusas de pagamento identificadas:
13.990 (5,00% do e-commerce). Contam como compra
357.823 pedidos (87,27%). Efeito sobre o
alvo (base de 109.499 clientes com pedido até o corte): são
24.042 positivos (21,96%); se o cancelado
contasse como compra seriam 27.109
(24,76%), ou seja, 3.067 clientes
(2,80% da base) mudariam de rótulo. Na janela do alvo há
33.503 pedidos, dos quais 4.311 cancelados.

**(f) Asserção associada.** `02_transformacao · status: pedidos cujo status não está no mapa`;
`pedido: sem status_conformado`; `pedido: status_conformado fora da lista`.

---

## RDT-05 · Definição de `VALOR_TOTAL` e `total_amount`

**Etapa:** 02_transformacao · `conforma_valores`.

**(a) O que o dado mostrava.** A reconciliação com a soma dos itens (Semana 1,
`saida/diagnostico/d04_resumo.csv`) mostrou que `total_amount` é a mercadoria líquida (quantidade ×
preço − desconto de linha), **sem frete**, e que `VALOR_TOTAL` é a mercadoria líquida **mais o
frete**, com o desconto `-1` lido como zero. No pipeline, a mesma conta feita em SQL sobre `cnf`:
`VALOR_TOTAL` bate com a fórmula em 130.000 pedidos
(100,00%) e `total_amount + freight_amount` em
280.000 (100,00%).
Somas de referência (todos os pedidos): `VALOR_TOTAL` R$ 281.084.957,13; `total_amount`
R$ 734.859.099,95 e, com o frete, R$ 745.850.860,33. O frete embutido
no legado soma R$ 5.760.932,57.

**(b) Alternativas consideradas.**

1. *Manter cada campo como veio* e chamar os dois de "valor total". Mistura grandezas: somar os
   dois sistemas incluiria o frete só num deles.
2. *`valor_total` sem frete nos dois* (retirar o frete do legado). Casa com `total_amount`, mas
   contraria a definição do DDL (`valor_total = mercadoria + frete − desconto`) e tira da ABT o que
   o cliente realmente pagou.
3. *`valor_total` com frete nos dois* (somar o frete ao e-commerce).

**(c) Decisão e justificativa.** Alternativa 3, com medidas explícitas e a mesma fórmula nos dois
sistemas: `valor_mercadoria = Σ quantidade × preço unitário` (bruto), `valor_desconto = Σ descontos
de linha`, `valor_frete` como gravado e `valor_total = valor_mercadoria − valor_desconto +
valor_frete`. É a definição do DDL e a que reproduz, sem resíduo, o campo que o legado
chama de total. **Consequência para a reconciliação (Semana 3):** a referência do e-commerce na
origem é `SUM(total_amount) + SUM(freight_amount)`, e não `SUM(total_amount)`; comparar o DW com o
`total_amount` cru produziria uma diferença falsa de R$ 10.991.760,38.

**(d) O que se perde.** Nada se apaga: `valor_mercadoria`, `valor_desconto` e `valor_frete` ficam
separados, e o valor sem frete é recuperável (`valor_total − valor_frete`). Perde-se a
identidade com o campo original do e-commerce: quem consultar `total_amount` na origem e
`valor_total` no DW verá números diferentes na quase totalidade dos pedidos. A prova de que o total
do legado tem o frete depende de a soma dos itens ser confiável (itens órfãos ficam de fora, RDT-10).

**(e) Registros afetados.** 279.984 pedidos do e-commerce
(99,99% dos 280.000) têm `valor_total`
diferente do `total_amount` cru, por causa do frete; nos 130.000 do legado o valor
conformado é igual ao `VALOR_TOTAL` em todos. Pedidos com `valor_total` divergente da origem após a
conformação: 0.

**(f) Asserção associada.** `02_transformacao · pedido: valor_total diverge do total da origem
(>0,01)` e `pedido: valor_mercadoria diverge da soma dos itens (>0,01)`. A soma por sistema, dentro
de 0,1%, é a reconciliação financeira da etapa 3.

---

## RDT-06 · Frete negativo, desconto `-1` e preços atípicos

**Etapa:** 02_transformacao · `conforma_valores`.

**(a) O que o dado mostrava.**

- *Desconto `-1` (legado):* 4.056 linhas de item
  (1,02% de `ITENS_PEDIDO`) em 4.003 pedidos
  (3,08% do legado). É o único valor negativo do campo. O total
  gravado pelo ERP trata `-1` como "sem desconto" (RDT-05).
- *Frete negativo:* 362 pedidos no legado (0,28%) e
  812 no e-commerce (0,29%), somando
  -R$ 16.098,86 e -R$ 32.248,65. O total gravado na origem inclui o frete
  negativo como está (fecha com a fórmula), e 142 desses
  pedidos estão cancelados. Nenhum pedido tem `valor_total` negativo (0).
- *Preços:* 7 produtos do e-commerce
  (0,06%) e 1 do legado
  (0,03%) têm preço de tabela de 10 vezes a mediana da categoria ou
  mais (a maior razão é 15,35). Mas **nenhum item**
  foi vendido por 10 vezes o preço de tabela (0; a maior razão
  entre preço vendido e preço de tabela é 3,46).

**(b) Alternativas consideradas.**

*Desconto `-1`:* (1) tratar como valor (acréscimo de R$ 1 por linha); (2) converter para `NULL`
(desconto desconhecido); (3) converter para 0 com indicador `desconto_sentinela`.
*Frete negativo:* (1) manter como gravado, com indicador `frete_negativo`; (2) zerar; (3) converter
para `NULL`; (4) tratar como estorno e separar em outra coluna.
*Preço atípico:* (1) corrigir para a mediana; (2) excluir; (3) manter e registrar.

**(c) Decisão e justificativa.** *Desconto:* alternativa 3. `-1` não é desconto, é sentinela; a
alternativa 1 contrariaria o total que o ERP gravou, e a 2 impediria calcular o total. *Frete:*
alternativa 1. O significado do frete negativo (estorno? subsídio? erro?) não se decide pelo dado: a
origem o somou ao total, e corrigi-lo aqui faria o DW divergir da origem e quebraria a reconciliação.
O indicador permite à análise tratá-lo depois. *Preço:* alternativa 3. O critério da regra é duplo:
razão alta contra a mediana da categoria *e* venda efetiva a preço compatível. Nenhum item foi
vendido a 10× o preço de tabela, o que indica que o preço de tabela alto é um preço real do produto
(nem todo valor alto é erro de digitação).

**(d) O que se perde.** *Desconto:* a informação de que o campo estava preenchido com o sentinela
vira só um indicador; não sabemos se `-1` queria dizer "sem desconto" ou "desconto não informado".
*Frete:* mantemos um valor que pode ser erro; as médias de frete ficam levemente deslocadas para
baixo e o `valor_total` desses pedidos é menor que a mercadoria líquida mais o frete "esperado". *Preço:*
um erro de digitação eventual no preço de tabela não seria detectado, e o julgamento de que "preço alto
vendido a preço alto" é válido pressupõe que a venda reflete o preço correto.

**(e) Registros afetados.** Desconto: 4.056 linhas
(1,02% dos itens do legado) e 4.003 pedidos
(3,08% do legado). Frete negativo: 1.174 pedidos
(0,29% dos 410.000). Preços atípicos: 7 +
1 produtos, nenhum corrigido.

**(f) Asserção associada.** `02_transformacao · valores: descontos negativos que não são o
sentinela -1`; `item: descontos negativos remanescentes`; `pedido: soma do frete difere da origem
(frete negativo preservado)`; `pedido: valor_total negativo`.

---

## RDT-07 · Mapeamento da taxonomia de produtos

**Etapa:** 02_transformacao · `conforma_categorias`.

**(a) O que o dado mostrava.** O legado tem texto livre (27 grafias; após normalizar caixa e
acento, 23 rótulos não vazios mais o vazio); o e-commerce tem uma
taxonomia de dois níveis em que os produtos ocupam as folhas. Classificação dos rótulos do legado
(critério da Semana 1, D10; `saida/diagnostico/d03_categoria_mapa.csv`):

| Classe | Rótulos | Produtos | % dos 3.000 produtos do legado | Itens vendidos | % dos itens |
|---|---:|---:|---:|---:|---:|
| direto (mesmo nível da taxonomia) | 8 | 916 | 30,53% | 119.442 | 30,08% |
| nível (só a raiz corresponde) | 11 | 1.423 | 47,43% | 185.848 | 46,80% |
| ambíguo (ELETRO, informatica e games) | 2 | 321 | 10,70% | 41.781 | 10,52% |
| sem mapeamento (DIVERSOS, OUTROS, vazio) | 3 | 340 | 11,33% | 44.147 | 11,12% |

A descrição do produto não desempata: em ambos os sistemas, cada um dos 50 substantivos iniciais
do legado aparece em no mínimo 16 categorias, e no e-commerce em no mínimo
15 (Semana 1). Produtos com a mesma descrição nos dois sistemas:
43 de 3.000, coincidência de nomes gerados e não identidade.

**(b) Alternativas consideradas.**

1. *Atribuir um destino a todo rótulo* (ELETRO → Eletrodomésticos; "informatica e games" →
   Informática; DIVERSOS → "Outros"). Produz uma taxonomia completa, mas com atribuições
   inventadas.
2. *Atribuir só o que o rótulo sustenta*: direto → raiz e filho; nível → só a raiz; ambíguo e sem
   mapeamento → nulo, mantendo `categoria_origem`.
3. *Classificar pelo texto da descrição.* Descartada: a descrição não carrega informação de categoria.
4. *Criar categorias sintéticas* (por exemplo "Informática/Games").

**(c) Decisão e justificativa.** Alternativa 2. `categoria_nivel1` e `categoria_nivel2` só são
preenchidas onde o rótulo sustenta; `categoria_origem` guarda sempre o texto bruto (conformar não
autoriza apagar a evidência) e `cnf.produto.classe_mapeamento` guarda a classe. Nas raízes que têm
produtos diretamente (Esporte e Lazer, Ferramentas), `categoria_nivel2` é nulo, porque a
taxonomia não tem um segundo nível ali. Produtos do e-commerce herdam a categoria da taxonomia. Os produtos
dos dois sistemas **não são unificados** (o legado não tem SKU).

**(d) O que se perde.** Para os rótulos de nível raiz, o ramo (por exemplo Smartphones contra
Acessórios): 1.423 produtos sem `categoria_nivel2`. Para os ambíguos e sem mapeamento,
toda a categoria: 661 produtos do DW ficam sem `categoria_nivel1`, e o
atributo "categorias distintas compradas" da ABT os ignora. Os dois rótulos ambíguos podem esconder
mais de uma resposta correta; a classe de `TELEFONIA` (nível) e a de `CELULARES` (direto, sem separar
acessórios) são interpretações da equipe.

**(e) Registros afetados.** 3.000 produtos do legado reclassificados
(100% da dimensão do legado); 661 produtos
(4,41% dos 3.000 + 12.000 do DW) ficam sem
`categoria_nivel1`; 321 são ambíguos (10,70% do legado) e
340 sem mapeamento (11,33%).

**(f) Asserção associada.** `02_transformacao · categoria: rótulos do legado sem regra no mapa`;
`produto: ambíguo/sem_mapeamento com nivel1 preenchido`; `produto: nivel1 vazio entre direto/nivel`;
`produto: produtos ECOM sem categoria nivel1`; `produto: linhas conformadas`.

---

## RDT-08 · Classificação e tratamento de cada tipo de ausência

**Etapa:** 02_transformacao · `trata_datas_e_ausencias`, `unifica_clientes`,
`liga_sac_e_avaliacoes`.

**(a) O que o dado mostrava.** Há três naturezas de ausência, e nenhuma é resolvida com média:
*não aplicável* (o dado não existe porque o evento não ocorreu), *não coletada* (o sistema nunca
registrou) e *sentinela* (um valor ocupa o lugar da ausência).

| Campo | Natureza | Tratamento | Registros | % da base |
|---|---|---|---:|---:|
| `DT_ENTREGA = 1900-01-01` (legado; todos com status ENTREGUE) | sentinela | `NULL` + `entrega_sem_data` | 1.025 | 0,79% do legado |
| Data de entrega nula em pedido não entregue | não aplicável | `NULL`, sem indicador | 101.604 | 24,78% dos pedidos |
| Entrega anterior ao pedido | inconsistência | `NULL` + `entrega_anterior_pedido` | 2.458 (775 legado, 1.683 e-commerce) | 0,60% dos pedidos |
| `CIDADE = 'N/A'` (legado) | sentinela | `NULL` | 933 | 1,97% de `CLIENTES` |
| CPF ausente (legado / e-commerce) | não coletada | `NULL` | 4.423 / 6.855 | 9,36% / 8,06% |
| CPF com dígito verificador inválido (legado / e-commerce) | dado incorreto | mantido, `cpf_valido = falso` | 3.859 / 6.967 | 8,17% / 8,20% |
| SAC `nota_satisfacao` vazia | não coletada | `NULL` | 8.682 | 9,03% do SAC |
| SAC `nota_satisfacao = 0` (fora da escala 1 a 5) | sentinela | `NULL` + `nota_zero` | 2.830 | 2,94% do SAC |
| SAC `data_fechamento` vazia (todas com horas de resolução) | dado perdido | `NULL`; horas preservadas | 5.856 | 6,09% do SAC |
| SAC horas de resolução negativas | inconsistência | `NULL` + `horas_negativas` | 353 | 0,37% do SAC |
| Avaliação sem `rating` | não coletada | `NULL` | 4.831 | 3,02% das avaliações |
| `rating` como texto | sintática | convertido para inteiro (indicador `rating_chegou_como_texto`) | 16.108 | 10,07% |
| Avaliação sem `verified_purchase` | não coletada | `NULL` | 15.731 | 9,83% |
| Avaliação sem `helpful_votes` | não coletada | `NULL` | 72.129 | 45,08% |

Pontos que pedem explicação. (1) *`data_fechamento` vazia não é "atendimento em aberto":* os
5.856 atendimentos sem data de fechamento têm tempo de resolução
preenchido, então já foram resolvidos; é a data que se perdeu. (2) *Nenhuma `rating` textual é não
numérica* (0), então o `rating` como texto é problema de tipo, não de conteúdo.
(3) As chaves omitidas do NDJSON atingem 114.294 avaliações
(71,43%), e na `stg` a contagem por chave está em
`saida/extracao/ndjson_chaves_ausentes.csv`.

**(b) Alternativas consideradas.**

1. *Imputar* (média, mediana, ou a data do pedido mais o prazo médio). Inventa dado e esconde a falha.
2. *Manter o sentinela* como valor. Contamina médias: `1900-01-01` geraria prazos de dezenas de milhares
   de dias; a nota 0 puxaria a média de satisfação para baixo.
3. *`NULL` sem indicador.* Perde a distinção entre "não aplicável" e "falha de registro".
4. *`NULL` com indicador* onde a falha de registro é informação (sentinelas e inconsistências).

**(c) Decisão e justificativa.** Alternativa 4 nos sentinelas e inconsistências; `NULL` simples
no que não se aplica ou não foi coletado. Não se imputa nada. A **entrega anterior ao pedido** (que
vira `NULL` com indicador) é impossível; não há como saber qual das duas datas está errada, e como
a diferença é de dias inteiros (não de fuso), mantém-se a data do pedido, a que ancora o corte da ABT.
O **CPF inválido** não é apagado: ele ainda identifica a pessoa (RDT-02), e a coluna `cpf_valido`
informa a qualidade. A **nota 0** é tratada como fora da escala, e não como a pior nota, porque o
SAC pede 1 a 5 e o zero não se concentra em atendimentos sem fechamento (Semana 1): seu significado
é desconhecido.

**(d) O que se perde.** A data real de entrega nos 1.025 pedidos com
sentinela e nos 2.458 inconsistentes; médias de prazo passam a excluí-los e
podem ficar enviesadas se a falha se concentrar em entregas lentas (não verificável). A nota 0, se
significasse "cliente não respondeu", e não "nota mínima", não tem como ser distinguida. A cidade
dos 933 clientes com `N/A` só existe se o cadastro do e-commerce a fornecer. A data de fechamento do
SAC perdida não é reconstruída, embora fosse calculável (abertura + horas), porque isso seria
imputar um valor derivado.

**(e) Registros afetados.** Veja a coluna de registros e de percentual na tabela do item (a),
com a base indicada em cada linha.

**(f) Asserção associada.** `02_transformacao · pedido: data_entrega com sentinela 1900
remanescente`; `pedido: dias_entrega negativo`; `cliente: cidade 'N/A' remanescente`; `cliente: CPF
conformado com tamanho diferente de 11`; `sac: nota fora de 1..5 após conformar`; `sac: horas_resolucao
negativas após conformar`; `avaliação: nota fora de 1..5 após conformar`.

---

## RDT-09 · Padronização de fuso horário

**Etapa:** 02_transformacao · `trata_datas_e_ausencias`.

**(a) O que o dado mostrava.** `DT_PEDIDO`/`DT_ENTREGA` do legado não têm fuso; `placed_at`,
`delivered_at` e `created_at` do e-commerce são `TIMESTAMPTZ` (gravados em UTC); `submitted_at` das
avaliações vem com offset `-03:00` em 128.085 casos e sem offset em
31.915 (19,95%); o conjunto de offsets
explícitos tem 1 valor distinto. Os pedidos do canal `SITE` do legado só
ocorrem entre 8 h e 21 h, o que só faz sentido como hora local.

**(b) Alternativas consideradas.**

1. *UTC como régua única:* converter o legado (local + 3 h) e manter o e-commerce em UTC.
2. *Hora local de Brasília (America/Sao_Paulo) como régua única:* ler o legado como está e
   converter o e-commerce de UTC para local.
3. *Cada fonte na sua régua*, sem converter.

**(c) Decisão e justificativa.** Alternativa 2. O período de dados (2023 a 2025) é posterior à extinção
do horário de verão no Brasil (2019), então o deslocamento é fixo em -3 h. A data de negócio que
interessa à pergunta (fim do dia 30/06 e 28/09) é a data local. As avaliações sem offset são lidas como
hora local, já que todos os offsets explícitos do arquivo são `-03:00`. Só então se extrai a data; as
tabelas de fatos guardam datas (`data_pedido_sk` é `DATE`).

**(d) O que se perde.** (i) O instante exato: o DW guarda a data local, não a hora. (ii) Se o
`DT_PEDIDO` do legado for, na realidade, UTC, o erro é do mesmo tamanho que a escolha da alternativa 1
(ver a seguir), e não temos como verificar. (iii) A interpretação de que as avaliações sem offset
estão em hora local é suposição.

**(e) Registros afetados.** Comparação com a régua UTC (alternativa 1), calculada sobre todos os
pedidos: 34.894 pedidos do e-commerce
(12,46%) e 9.290
do legado (7,15%) mudariam de dia. Em relação aos
limites da pergunta, 78 pedidos
(0,02%) trocariam de lado: 48 no corte de
30/06/2025 e 30 no fim do alvo (28/09/2025). Isso muda o rótulo de
52 clientes (0,05% da base) e faz
2 entrarem ou saírem da base. Nas avaliações, 4.028 das
31.915 sem offset mudariam de data.

**(f) Asserção associada.** `02_transformacao · pedido: data_pedido fora da régua America/Sao_Paulo`;
`pedido: datas fora do intervalo de dim_tempo`.

---

## RDT-10 · Itens órfãos

**Etapa:** 03_carga_dw · `carrega_fato_item`.

**(a) O que o dado mostrava.** 14.709 itens do e-commerce
(1,48% de `order_item`) e 5.868 do legado
(1,48% de `ITENS_PEDIDO`) não têm pedido. Todos têm identificador de pedido
acima do maior pedido existente: 14.709 no e-commerce e
5.868 no legado. Somam R$ 2.791.092,30 em
`valor_linha`. O DDL do e-commerce explica o mecanismo possível: a plataforma grava itens de forma
assíncrona, sem chave estrangeira.

**(b) Alternativas consideradas.**

1. *Descartar sem registro.* Perde a evidência de que os itens existiam.
2. *Criar pedidos sintéticos* para dar casa aos itens. Inventa pedidos (cliente, data, status) que nenhuma
   origem tem, e quebraria a reconciliação financeira, que compara pedidos reais.
3. *Manter no fato com `pedido_sk` nulo.* Impossível: o DDL define `pedido_sk NOT NULL`, e o grão
   declarado exige pedido presente.
4. *Quarentena:* tabela à parte, com todos os campos do item e o motivo.

**(c) Decisão e justificativa.** Alternativa 4: `dw.aux_item_quarentena` (motivo
`PEDIDO_INEXISTENTE_NA_ORIGEM`). O grão de `fato_item_pedido` é "uma linha de item de um pedido presente em
`fato_pedido`", e o item órfão não satisfaz essa frase. A quarentena mantém a evidência e permite recarregá-los
se os pedidos aparecerem em uma carga futura.

**(d) O que se perde.** R$ 2.791.092,30 de mercadoria fora das análises por item e por produto.
Se os pedidos correspondentes forem criados depois do retrato (hipótese compatível com a gravação assíncrona,
não demonstrada), são vendas reais que o DW não enxerga. Não afeta a reconciliação financeira, que opera sobre
pedidos, nem os atributos da ABT calculados sobre `fato_pedido`; afeta `categorias_distintas`, que lê itens.

**(e) Registros afetados.** 20.577 itens (1,48% dos
397.086 + 995.367 de origem) ficam em quarentena; 1.371.876
(98,52%) entram no fato.

**(f) Asserção associada.** `03_carga_dw · fato_item_pedido: itens + quarentena == itens de cnf`;
`fato_item_pedido: linhas == itens com pedido na origem`; `fato_item_pedido: itens sem pedido no fato`;
`fato_item_pedido: mercadoria dos itens != valor_mercadoria dos pedidos`.

---

## RDT-11 · Declaração de grão de `fato_pedido` e `fato_item_pedido`

**Etapa:** 03_carga_dw · `carrega_fato_pedido`, `carrega_fato_item` (frases aprovadas na Semana 1, D1 e D2).

> **`dw.fato_pedido`:** uma linha representa um pedido registrado em um dos dois sistemas de origem,
> identificado pelo par (sistema de origem, identificador do pedido na origem), qualquer que seja o seu status.
>
> **`dw.fato_item_pedido`:** uma linha representa uma linha de item tal como registrada na origem, pertencente a
> um pedido presente em `dw.fato_pedido`.

**(a) O que o dado mostrava.** O identificador do pedido é único dentro de cada sistema
(130.000 e 280.000) mas **colide** entre eles:
130.000 identificadores existem nos dois. Sem o sistema na chave, a união teria
280.000 pedidos em vez de 410.000. O mesmo
produto aparece em mais de uma linha do mesmo pedido em 195 pares no legado e
128 no e-commerce, e o preço é igual em apenas 1 e
2 deles: são vendas distintas. Há 52.177
pedidos cancelados ou recusados (12,73%), com itens e valor cheio, no valor
total de R$ 131.945.183,69.

**(b) Alternativas consideradas.**

1. *"Um pedido efetivado"* (excluir `CANCELADO`, `canceled`, `payment_declined`). Mistura regra de negócio
   da ABT com o grão, e a reconciliação financeira contra a origem passaria a exigir a mesma exclusão dos dois lados.
2. *"Um produto dentro de um pedido"* (agregar por pedido e produto). Transformaria `valor_unitario` em média e
   perderia o preço praticado nas linhas repetidas.
3. *"Um pedido de um cliente unificado".* Descreve a conformação da `dim_cliente`, não o grão, e exigiria um
   "e também" para pedidos de clientes não unificados.
4. *Chave natural só pelo identificador.* Colide entre os sistemas.

**(c) Decisão e justificativa.** As frases acima. A chave natural inclui o sistema (restrição `UNIQUE (id_origem,
sistema_origem)` do DDL). Cancelados e recusados permanecem porque são pedidos (têm itens e valor), a reconciliação
exige todos, e o que conta como compra é decisão da ABT, lida em `dim_status` (RDT-04). A frase cabe sem "e também".
O item não tem identificador de origem no DDL; o rastro fica em `dw.aux_item` (`item_sk` → identificador da linha na origem).

**(d) O que se perde.** Quem somar o fato sem filtrar `dim_status` incluirá pedidos que não geraram venda:
175.632 linhas de item (12,80%)
pertencem a pedidos cancelados. A frase torna isso explícito, mas não impede o uso errado. O grão de item não agrega
linhas repetidas do mesmo produto.

**(e) Registros afetados.** 410.000 pedidos (130.000 do legado e
280.000 do e-commerce; 0 chaves naturais repetidas) e
1.371.876 itens. **Reconciliação financeira** (`saida/reconciliacao/financeira.csv`), soma de `valor_total`
contra o total calculado na origem com a mesma fórmula: legado R$ 281.084.957,13 no DW contra
R$ 281.084.957,13 na origem (diferença R$ 0,00,
0,00%); e-commerce R$ 745.850.860,33 contra
R$ 745.850.860,33 (diferença R$ 0,00,
0,00%), ambos dentro do limite de 0,1%. Contra o `total_amount` cru, o e-commerce
teria uma diferença falsa de R$ 10.991.760,38 (o frete; RDT-05).

**(f) Asserção associada.** `03_carga_dw · fato_pedido: linhas == pedidos das duas origens somados`;
`fato_pedido: FK órfã em cliente_sk` (e `data_pedido_sk`, `canal_sk`, `status_sk`);
`reconciliação financeira: LEGADO, diferença relativa` e `... ECOM, diferença relativa` (e as de diferença
absoluta); `fato_item_pedido: linhas == itens com pedido na origem`.

---

## RDT-12 · Pedidos sem cliente correspondente

**Etapa:** 03_carga_dw · `carrega_fato_pedido`.

**(a) O que o dado mostrava.** Nenhum pedido está sem cliente: 0 pedidos têm um
`ID_CLIENTE` ou `customer_id` inexistente no cadastro do próprio sistema, e 0 têm o
identificador nulo. A hipótese do esqueleto (pedidos órfãos de cliente) **não se confirmou**. O risco real é outro: os
identificadores de cliente também colidem entre os sistemas. Os 130.000
pedidos do legado (100,00%) e
155.913 do e-commerce
(55,68%) apontam para um identificador que existe nos dois
cadastros. Uma junção sem o sistema ligaria o pedido a uma pessoa errada sem acusar erro.

**(b) Alternativas consideradas.**

1. *Cliente "DESCONHECIDO" na dimensão* (solução clássica para chave sem correspondência).
2. *Descartar pedidos sem cliente.*
3. *`cliente_sk` nulo.* Impossível: o DDL define `NOT NULL`.
4. *Nenhum cliente sintético; a carga exige correspondência e falha se ela faltar.*

**(c) Decisão e justificativa.** Alternativa 4. Como não existe pedido sem cliente, um membro "DESCONHECIDO" seria uma
linha da dimensão sem nenhum fato, que apareceria em contagens de clientes sem razão. A correspondência é feita pelo
par (sistema, identificador) na tabela-ponte, o que elimina o risco de colisão. Se uma carga futura trouxer um pedido
sem cliente, as asserções falham e a decisão (criar o membro, descartar, ou investigar) passa a ser humana.

**(d) O que se perde.** Hoje, nada. O custo é só prospectivo: a carga não se adapta sozinha a um pedido órfão e para
na asserção.

**(e) Registros afetados.** 0 pedidos (0,00%
dos 410.000). Membros "DESCONHECIDO" criados: 0. Para dimensionar o que
a junção correta evita: 86.942 pedidos
(21,21%) pertencem a uma pessoa que reúne mais de um registro de
cadastro (RDT-02 e RDT-03).

**(f) Asserção associada.** `03_carga_dw · fato_pedido: FK órfã em cliente_sk`;
`02_transformacao · pedido: sem cliente_key`.

---

## RDT-13 · Atendimentos e avaliações que não ligam a nenhum pedido

**Etapa:** 02_transformacao · `liga_sac_e_avaliacoes`; 03_carga_dw · `carrega_fatos_auxiliares`.

**(a) O que o dado mostrava.**

- *SAC:* 96.140 registros, dos quais 1.140 são linhas idênticas repetidas
  (1,19%), restando 95.000 atendimentos. O pedido declarado
  existe no sistema indicado em 95.000 deles
  (100,00%), mas o CPF do atendimento é o do dono desse pedido em apenas
  1 caso, e a abertura é posterior ao pedido em
  49,82% (o esperado ao acaso). Pelo CPF, 89.075
  atendimentos encontram uma pessoa (93,76%); 5.925
  (6,24%) não encontram, e 7 têm CPF de mais de uma pessoa.
- *Avaliações:* 160.000 objetos. O pedido de `order.ref` existe em
  160.000 (100,00%), mas o produto avaliado está entre os
  itens desse pedido em apenas 80
  (0,05%), e 49,86%
  foram enviadas antes do pedido. **O NDJSON não tem campo de CPF**
  (0), então não há ligação com cliente; o SKU liga ao produto em
  160.000 (100,00%).

**(b) Alternativas consideradas.**

1. *Ligar ao pedido declarado* (SAC: `origem_sistema` + `id_pedido_origem`; avaliação: `order.ref`).
2. *Ligar o SAC ao cliente pelo CPF*, sem pedido.
3. *Descartar os que não ligam.*
4. *Ligar a avaliação ao cliente pelo pedido declarado.*
5. *Ligar a avaliação só ao produto.*

**(c) Decisão e justificativa.** Alternativas 2 e 5, mantendo todos os registros. `pedido_sk` fica nulo em
`fato_atendimento` e `fato_avaliacao` (100% dos registros): o pedido declarado existe, mas os testes de consistência
(CPF, produto, ordem no tempo) mostram que ele não descreve a relação, de modo que ligá-lo produziria uma associação
que o dado desmente. O pedido declarado fica em `dw.aux_atendimento` e `dw.aux_avaliacao` como referência declarada,
não como ligação. O SAC liga ao cliente pelo CPF (de 11 dígitos, válido ou não, pelo critério da RDT-02); CPF de mais de
uma pessoa deixa o atendimento sem cliente em vez de escolher. A repetição do SAC é de linhas idênticas
(asserção), então mantém-se a primeira. A alternativa 4 foi descartada: levaria para a ABT um atributo de avaliação ligado
a um pedido que o dado desmente, e sujeito a data posterior ao corte.

**(d) O que se perde.** (i) A ligação de um atendimento ou avaliação a um pedido específico: análises do tipo
"reclamações sobre o pedido X" ficam impossíveis. Se o pedido declarado estiver correto em alguma fração dos casos, essa
fração se perde com o resto, e não há como identificá-la. (ii) 5.925 atendimentos sem cliente não
contribuem para nenhum atributo da ABT. (iii) As avaliações não contribuem com nenhum atributo por cliente (a nota média de
avaliações), só com análises por produto. (iv) Linhas repetidas do SAC são removidas, e perde-se a informação de que
foram exportadas mais de uma vez (a exportação é manual e concatenada).

**(e) Registros afetados.** SAC: 96.140 registros de entrada,
95.000 no fato; 0 com pedido ligado; 5.925
sem cliente (6,24%). Avaliações: 160.000 no fato, nenhuma com pedido
ou cliente ligado (0).

**(f) Asserção associada.** `03_carga_dw · fato_atendimento: pedido_sk preenchido`; `fato_avaliacao: pedido_sk preenchido`;
`fato_atendimento: cliente_sk órfão`; `fato_avaliacao: produto_sk nulo`; `02_transformacao · sac: protocolos repetidos
com conteúdo diferente`; `sac: protocolo único após remover linhas idênticas`; `avaliação: sem produto_key`.

---

## RDT-14 · Desenho dos atributos da ABT e verificação de ausência de vazamento

**Etapa:** 04_abt · `--correta` (regras completas em `docs/DICIONARIO_ABT.md` e `saida/abt/dicionario_atributos.csv`).

**(a) O que o dado mostrava.** Há informação posterior ao corte em lugares fáceis de usar sem perceber:
2.338 pedidos anteriores a 30/06/2025 foram entregues depois dessa data
(um `dias_entrega` desses pedidos seria conhecimento do futuro); o status gravado é o do retrato dos dados, e a origem
não guarda a data do cancelamento (1.477 dos
341.594 pedidos até o corte são cancelados e foram feitos nos 30 dias anteriores a ele, os mais
expostos à dúvida de "já estava cancelado no corte?"); o cadastro (`dim_cliente`) não tem data de atualização. O histórico
começa em 2023-01-01 (Semana 1): 9.605 clientes
(8,77%) têm o primeiro pedido observado em janeiro de 2023, e para
eles "tempo como cliente" é limitado pelo início dos dados. A população (clientes com ao menos um pedido até o corte) tem
109.499 pessoas, das quais 3.087
(2,82%) só têm pedidos cancelados até o corte. O SAC não traz
nenhum atendimento para 60.486 clientes
(55,24%), e as avaliações não ligam a cliente (RDT-13).

**(b) Alternativas consideradas.**

1. *Atributos de perfil vindos de `dim_cliente`* (cidade, UF, `origem_unificacao`, `dt_primeiro_cadastro`). Descartada:
   o cadastro pode ter sido atualizado depois do corte, e a unificação (RDT-02) olha o cadastro inteiro.
2. *Frequência e valor com todos os status.* Descartada: contaria como histórico de compra pedidos recusados e
   cancelados.
3. *População só com clientes com pedido efetivo até o corte.* Descartada: tira da população quem uma campanha de retenção
   pode alcançar e mexe no rótulo; a taxa de positivos só foi vista depois, e a decisão não foi trocada por causa dela.
4. *Atributo de nota de avaliação por cliente, via pedido declarado.* Descartada (RDT-13).
5. *Imputar os ausentes* (média, zero). Descartada: NaN não é zero; a ausência de entrega ou de SAC é informação.
6. *Atributos calculados sobre os fatos, só com pedidos até o corte, e verificados contra um DW "cortado".*

**(c) Decisão e justificativa.** Alternativa 6. São 14 atributos (recência, frequência, valor,
ticket, pedidos nos últimos 90 dias, taxa de cancelamento, desconto, prazo de entrega, categorias, canal predominante,
presença nos dois sistemas, tempo desde o primeiro pedido, atendimentos e nota do SAC), todos calculados em SQL sobre
`fato_pedido`, `fato_item_pedido` e `fato_atendimento` com `data_pedido_sk <= 2025-06-30`. O prazo de entrega só usa
entregas com data até o corte. Nenhum atributo vem de `dim_cliente`; por exemplo, `ambos_sistemas` sai dos pedidos, não
de `origem_unificacao`. O alvo conta como compra todo pedido não cancelado entre 01/07 e 28/09/2025 (RDT-04), calculado
pelo `SQL_ALVO`, o único ponto que olha o futuro por definição. **Verificação de ausência de vazamento, por asserção e
não só por código:** cria-se um esquema temporário com o DW "como estaria em 30/06/2025" (sem pedidos posteriores, com as
entregas posteriores tratadas como não ocorridas, sem atendimentos posteriores), recalculam-se os atributos nele e exige-se
resultado idêntico ao da ABT. Um vazamento provocado de propósito (RDT-15) é acusado por esse teste.

**(d) O que se perde.** (i) O status do retrato: pedidos cancelados depois do corte entram como cancelados; não há como
corrigir sem a data do cancelamento. (ii) O tempo de relacionamento real, pela censura à esquerda do histórico. (iii) O
perfil cadastral (cidade, UF), que poderia ajudar o modelo, e a nota de avaliações. (iv) A identidade da pessoa usa o
cadastro inteiro: ela diz quem é a pessoa, não o que a pessoa fez depois, mas é uma dependência a registrar. (v) Ausências
deixadas como `NULL` obrigam o fluxo de modelagem a decidir como tratá-las.

**(e) Registros afetados.** A ABT tem 109.499 clientes e 24.042 positivos
(21,96%); 29.255 só no legado
(26,72%), 67.704 só no e-commerce
(61,83%) e 12.540 nos dois
(11,45%). Atributos "efetivos" nulos em
3.087 clientes; prazo de entrega só com entregas até o corte
(2.338 pedidos deixam de contribuir).

**(f) Asserção associada.** `04_abt_correta · atributos: valores que mudam se o DW for cortado em 30/06/2025`;
`alvo: linhas == clientes unificados com pedido até o corte`; `alvo: positivos == recálculo independente em pandas`;
`taxa de positivos do alvo (registrada)`; `atributos: recência negativa`; `atributos: tempo_como_cliente negativo`;
`atributos: data_corte diferente de 2025-06-30`; `atributos: colunas do alvo entre os atributos`.

---

## RDT-15 · Vazamentos introduzidos deliberadamente na versão de comparação

**Etapa:** 04_abt · `--vazamento` e `--vazamento-sutil`.

**(a) O que o dado mostrava.** A informação que vaza já está no DW: há 59.695 pedidos
efetivos posteriores ao corte, dos quais 29.192 na própria janela do alvo. Basta tirar
a cláusula de data de um agregado para que o atributo os enxergue. Na versão construída: a recência muda para
43.292 clientes (39,54%) e fica negativa em todos eles
(43.292; 18.349 com o último pedido dentro da janela do alvo e
24.943 depois dela). **Todos** os 24.042 positivos
(100,00%) têm recência negativa: entre os clientes de recência negativa
55,53% são positivos, e entre os demais, 0,00%.
A frequência passa a incluir 56.141 pedidos a mais em 43.292
clientes (39,54%). A média e o desvio globais do valor monetário, que a
normalização usa, são R$ 6.806,02 e R$ 5.031,50.

**(b) Alternativas consideradas.**

1. *Atributo que conta compras futuras diretamente* (por exemplo, "pedidos nos 90 dias seguintes"). Descartada: é
   vazamento óbvio demais para ser realista; ninguém o cometeria por engano.
2. *Vazar pelo status ou pela data de entrega pós-corte.* Possível (há 2.338
   pedidos anteriores ao corte entregues depois), mas o efeito é indireto e fraco para o experimento.
3. *Esquecer o filtro de data em dois agregados* (recência e frequência) e *padronizar antes da partição.*

**(c) Decisão e justificativa.** Alternativa 3, em três vazamentos, cada um com a coluna e o mecanismo:

| Vazamento | Coluna | O que faz | Versões |
|---|---|---|---|
| 1 · base inteira | `recencia_dias` | busca o último pedido efetivo também depois do corte; quem comprou depois tem recência negativa | `--vazamento` |
| 2 · base inteira | `frequencia_pedidos` | conta os pedidos efetivos de toda a base, inclusive os do próprio alvo | `--vazamento` |
| 3 · normalização antes da partição | `valor_monetario_z` | z-score do valor monetário com média e desvio de todas as linhas, antes de separar treino e teste | `--vazamento` e `--vazamento-sutil` |

Os dois primeiros são os erros mais comuns (agregado sem filtro de data) e geram um sinal forte. O terceiro é sutil: não
traz informação do alvo, mas leva ao treino a escala do conjunto de teste. A versão `--vazamento-sutil` tem só o terceiro
e serve a uma pergunta que, sem ela, não teria resposta em números: o vazamento sutil sozinho produz diferença? Ela não vai
ao Orange. Todos os outros atributos são idênticos aos da versão correta (asserção).

**(d) O que se perde / cuidados.** As tabelas `abt.recompra_90d_vazamento` e `abt.recompra_90d_vazamento_sutil` não respondem
à pergunta de negócio e não podem ser usadas para decidir nada; existem para medir o vazamento. Usar uma por engano
produziria um modelo que parece excelente e é inútil. Por isso têm nome próprio e o `05_exportar_orange.py` as grava com o
sufixo `_vazamento`. A normalização é uma transformação linear: para modelos invariantes a escala (como a árvore) o efeito
esperado é nulo, e a diferença que existir é o resultado a medir, não a supor.

**(e) Registros afetados.** Vazamentos 1 e 2: 43.292 e 43.292 clientes
(39,54% dos 109.499). Vazamento 3: os 109.499 clientes (100%), pois a
média e o desvio são calculados sobre todas as linhas.

**(f) Asserção associada.** `04_abt_vazamento · (intencional) clientes com recencia_dias diferente da correta`;
`(intencional) clientes com recencia_dias negativa`; `(intencional) clientes com frequencia_pedidos diferente da correta`;
`(intencional) média do valor_monetario_z sobre todas as linhas`; `(intencional) desvio do valor_monetario_z sobre todas as linhas`;
`atributos que deveriam ser idênticos aos corretos e diferem`; `população igual à da versão correta`. Na versão sutil
(`04_abt_vazamento_sutil`): `recencia_dias idêntica à correta (versão sutil)` e `frequencia_pedidos idêntica à correta (versão sutil)`.

---

## Tabela-resumo (fichas 01 a 15)

Os números são os mesmos das fichas. "% da base" usa a base indicada em cada ficha. "Asserção" é a principal de cada ficha; a lista
completa está no item (f) de cada uma.

| Ficha | Decisão | Registros afetados | % da base | Informação perdida? | Asserção principal |
|---|---|---:|---:|---|---|
| RDT-01 | Carga completa, recriando a `stg` | 2.205.864 | 100,00% | Histórico de versões das linhas | `01_extracao · linhas <fonte>.<tabela>` |
| RDT-02 | CPF (válido ou não) + guarda de nome/UF; sem nome + UF | 14.854 registros unidos | 11,23% dos registros de cliente | Pessoas sem CPF não são pareadas (10.462) | `cliente: (sistema, id) único na ponte` |
| RDT-03 | Fundir duplicatas do legado (sobrevivente + ponte) | 2.250 registros | 4,76% de `CLIENTES` | Variantes de grafia/CPF do registro absorvido | `cliente: registros de origem na ponte` |
| RDT-04 | `CANCELADO` + `motivo_cancelamento`; compra = não cancelado | 52.177 cancelados | 12,73% dos pedidos | Motivo no legado (15.774) | `pedido: status_conformado fora da lista` |
| RDT-05 | `valor_total` = mercadoria − desconto + frete nos dois | 279.984 pedidos do e-commerce | 99,99% do e-commerce | Não (componentes separados) | `pedido: valor_total diverge do total da origem` |
| RDT-06 | `-1` → 0 com indicador; frete negativo mantido; preços mantidos | 4.056 linhas; 1.174 pedidos | 1,02% dos itens do legado; 0,29% dos pedidos | Significado de `-1` e do frete negativo | `item: descontos negativos remanescentes` |
| RDT-07 | Mapear só o que o rótulo sustenta | 661 produtos sem nível 1 | 4,41% dos produtos | Categoria dos ambíguos e sem mapeamento; ramo dos de nível raiz | `produto: ambíguo/sem_mapeamento com nivel1 preenchido` |
| RDT-08 | `NULL` + indicador em sentinelas e inconsistências; nada imputado | 1.025 entregas com sentinela e 2.458 anteriores ao pedido (as demais ausências estão na tabela da ficha) | 0,79% do legado e 0,60% dos pedidos | Data de entrega, nota 0, data de fechamento | `pedido: data_entrega com sentinela 1900 remanescente` |
| RDT-09 | Hora local de Brasília como régua | 78 pedidos trocariam de lado com UTC | 0,02% dos pedidos | Hora exata do dia | `pedido: data_pedido fora da régua America/Sao_Paulo` |
| RDT-10 | Itens sem pedido em quarentena, fora do fato | 20.577 itens | 1,48% dos itens | R$ 2.791.092,30 de mercadoria fora das análises por item | `fato_item_pedido: itens + quarentena == itens de cnf` |
| RDT-11 | Grão: pedido por (sistema, id), qualquer status; item como na origem | 410.000 pedidos; 1.371.876 itens | 100,00% dos pedidos | Pedidos cancelados ficam no fato e exigem filtro | `fato_pedido: linhas == pedidos das duas origens somados` |
| RDT-12 | Sem cliente "DESCONHECIDO"; a carga exige correspondência | 0 pedidos | 0,00% dos pedidos | Nada hoje | `fato_pedido: FK órfã em cliente_sk` |
| RDT-13 | SAC liga ao cliente pelo CPF; nenhuma fonte liga ao pedido; avaliação só ao produto | 96.140 SAC e 160.000 avaliações sem pedido | 100,00% dos registros | Ligação a pedido; 5.925 atendimentos sem cliente | `fato_atendimento: pedido_sk preenchido` |
| RDT-14 | Atributos só dos fatos, até o corte; verificação contra o DW "cortado" | 109.499 clientes, 14 atributos | 100,00% da população | Status do retrato; tempo de relacionamento real; perfil cadastral e avaliações | `atributos: valores que mudam se o DW for cortado em 30/06/2025` |
| RDT-15 | Dois agregados sem filtro de data + z-score antes da partição | 43.292 clientes (vazamentos 1 e 2); 109.499 (vazamento 3) | 39,54%; 100,00% | Versão sem valor de negócio, só de medida | `04_abt_vazamento · (intencional) clientes com recencia_dias diferente da correta` |

---

## Reflexão

A parte mais cara deste trabalho não foi escrever código, foi decidir o que o dado queria dizer. Quase toda ficha do RDT tem a mesma
forma: o dado admite duas leituras plausíveis, e a escolha altera números que depois alguém cita como se fossem do mundo, e não de uma
decisão nossa.

Três fichas mostram isso. No RDT-05, o `total_amount` cru do e-commerce difere do valor conformado em
279.984 pedidos; sem descobrir que ele não inclui o frete, a reconciliação
financeira acusaria uma diferença que não existe. No RDT-09, a régua de tempo (hora de Brasília, e não UTC) decide de que lado do corte ou do
fim da janela caem 78 pedidos, ou seja, o alvo depende de um fuso. No RDT-04,
tratar pedido cancelado como não-compra define o que é "recompra" para 52.177 cancelamentos.

Nem toda decisão tem como ser conferida. No RDT-02, 14.854 registros foram unidos a outra identidade por
CPF ou por nome e UF, e não existe verdade externa para checar. A guarda de nome e UF reduz o risco; não o elimina.

O experimento de vazamento deixou a lição mais incômoda. As asserções provam que o vazamento sutil existe, mas as métricas não o
mostram (`relatorio/semana4/resultados_experimento.md`). Olhar só o desempenho não basta: é preciso verificar a linhagem do dado, e é por isso
que o RDT-14 testa a ABT contra o DW "como estava" em 30/06/2025.

Deixamos limites declarados, em vez de escondidos. A ABT guarda o status do retrato dos pedidos, não o do corte (D40). Entram na população
3.087 clientes que só têm pedidos cancelados até o corte (D38). As avaliações não ligam a
cliente (D30), e por isso `nota_media_avaliacoes` ficou fora da ABT.

O que levamos: a transformação é o ponto em que o julgamento do analista entra nos dados e permanece lá, invisível. O RDT é a resposta
antecipada à pergunta "de onde veio este número?", e só vale se registrar também o que cada decisão custou.
