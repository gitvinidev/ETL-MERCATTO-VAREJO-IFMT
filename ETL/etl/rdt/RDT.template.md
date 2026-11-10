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
resultado é {{rdt01.colunas_de_atualizacao_nas_origens}}. As únicas datas são de evento
(`DT_PEDIDO`, `placed_at`, `DT_CADASTRO`), que não mudam quando o pedido muda de status. Os
itens chegam antes do pedido: há {{rdt10.itens_orfaos.total}} itens sem pedido
({{rdt10.itens_orfaos.total_pct|pct}} das linhas de item), todos com identificador de pedido
acima do maior pedido existente. O `00_perfilamento.py` usa `LIMIT 200000` e por isso deixa de
ver {{rdt01.registros_fora_da_amostra_do_perfilamento}} registros
({{rdt01.registros_fora_da_amostra_do_perfilamento_pct|pct}} do total), em `ITENS_PEDIDO`
({{rdt01.fora_da_amostra.ITENS_PEDIDO}}), `orders` ({{rdt01.fora_da_amostra.orders}}) e
`order_item` ({{rdt01.fora_da_amostra.order_item}}). Volume total das quatro fontes:
{{rdt01.registros_carregados}} registros (`saida/extracao/contagens_stg.csv`).

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
de mudança defensável, e o volume ({{rdt01.registros_carregados}} registros) cabe numa leitura completa em
fluxo. A carga completa também é a que torna a etapa idempotente: `DROP` + `CREATE` + `COPY`,
o que permite a reexecução do zero exigida no Entregável 5. A diferença para o perfilamento
está escrita no cabeçalho de `01_extracao.py`: aqui não há `LIMIT`.

**(d) O que se perde.** O histórico de versões de cada linha: cada carga substitui a anterior,
e não é possível saber o que mudou entre duas cargas. A carga completa também não escala se o
volume crescer ordens de grandeza. Aceitamos as duas perdas porque o projeto lida com um
retrato único das origens.

**(e) Registros afetados.** Todos: {{rdt01.registros_carregados}} registros (100% da base).
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
zero, Semana 1). Em `CLIENTES` faltam {{rdt08.cpf_ausente.legado}} CPFs
({{rdt08.cpf_ausente.legado_pct|pct}}) e {{rdt08.cpf_dv_invalido.legado}} têm dígito
verificador inválido ({{rdt08.cpf_dv_invalido.legado_pct|pct}}); em `customer`, faltam
{{rdt08.cpf_ausente.ecom}} ({{rdt08.cpf_ausente.ecom_pct|pct}}) e
{{rdt08.cpf_dv_invalido.ecom}} são inválidos ({{rdt08.cpf_dv_invalido.ecom_pct|pct}}).

- **CPF válido igual nos dois cadastros:** {{rdt02.pares_cpf_valido_igual}} pares, e o nome
  normalizado discorda em {{rdt02.pares_cpf_valido_igual_nome_discorda}}.
- **CPF inválido igual nos dois cadastros:** {{rdt02.pares_cpf_invalido_igual}} pares, e nome e
  UF concordam em {{rdt02.pares_cpf_invalido_igual_nome_e_uf_concordam}}. O erro de dígito é, portanto,
  o mesmo digitado nos dois sistemas, e o CPF inválido continua identificando a pessoa. No SAC,
  {{rdt13.sac.cpf_invalido_com_cliente_pct|pct}} dos CPFs inválidos encontram um cadastro, taxa
  igual à dos válidos ({{rdt13.sac.cpf_valido_com_cliente_pct|pct}}).
- **Colisões:** {{rdt02.cpfs_em_colisao}} CPFs válidos pertencem a pessoas de nomes diferentes.
- **Nome + UF não identifica:** entre registros com CPF válido dos dois lados, a chave nome + UF
  gera {{rdt02.valid_nome_uf.pares_candidatos}} pares, dos quais só
  {{rdt02.valid_nome_uf.pares_cpf_igual}} têm o mesmo CPF; {{rdt02.valid_nome_uf.pares_falsos}} são falsos
  (precisão de {{rdt02.valid_nome_uf.precisao_pct|pct}}), e **nenhuma** chave é única nos dois cadastros
  ({{rdt02.valid_nome_uf.chaves_unicas_nos_dois_lados}}). Acrescentando a cidade: {{rdt02.valid_nome_uf_cidade.pares_candidatos}}
  pares, {{rdt02.valid_nome_uf_cidade.pares_falsos}} falsos (precisão de {{rdt02.valid_nome_uf_cidade.precisao_pct|pct}}),
  também sem chave única ({{rdt02.valid_nome_uf_cidade.chaves_unicas_nos_dois_lados}}).

**(b) Alternativas consideradas.**

1. *Só CPF com dígito verificador válido.* Simples e precisa, mas ignora os
   {{rdt02.pares_cpf_invalido_igual}} pares cujo CPF inválido é o mesmo nos dois lados.
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
({{rdt02.pessoas_sem_cpf}} pessoas, {{rdt02.pessoas_sem_cpf_pct|pct}}), e o histórico delas
continua dividido; a regra por nome + UF alcançaria mais {{rdt02.pares_extras_por_nome_uf_sem_cpf_valido}}
pares candidatos, mas sem como escolher entre homônimos. (ii) A confiança no pareamento
depende de a pessoa ter digitado o mesmo nome nos dois sistemas; apelidos ou abreviações não
seriam reconhecidos. (iii) Na colisão de CPF, {{rdt02.pessoas_com_cpf_em_colisao}} pessoas
({{rdt02.pessoas_com_cpf_em_colisao_pct|pct}}) estão envolvidas: o CPF fica com a que tem mais registros
e, em empate, com nenhuma, de modo que alguém pode perder um CPF que era seu. (iv) Não se sabe quantas fusões estariam erradas: o CPF não é verificado por fonte
externa.

**(e) Registros afetados.** {{rdt02.registros_cliente}} registros de cliente avaliados
(`CLIENTES` + `customer`). {{rdt02.registros_unidos_em_outra_pessoa}} deles
({{rdt02.registros_unidos_em_outra_pessoa_pct|pct}}) deixam de ser uma linha própria, e restam
**{{rdt02.pessoas}} pessoas** ({{rdt02.pessoas_pct|pct}} dos registros). Por origem:
{{rdt02.pessoas.AMBOS}} nos dois sistemas ({{rdt02.pessoas.AMBOS_pct|pct}}),
{{rdt02.pessoas.LEGADO}} só no legado ({{rdt02.pessoas.LEGADO_pct|pct}}) e
{{rdt02.pessoas.ECOM}} só no e-commerce ({{rdt02.pessoas.ECOM_pct|pct}}). Por regra:
`CPF_VALIDO_NOME` {{rdt02.pessoas_por_regra.CPF_VALIDO_NOME}} pessoas;
`CPF_INVALIDO_NOME_UF` {{rdt02.pessoas_por_regra.CPF_INVALIDO_NOME_UF}};
`DUPLICATA_LEGADO` isolada {{rdt02.pessoas_por_regra.DUPLICATA_LEGADO}}; combinações com a duplicata:
{{rdt02.pessoas_por_regra.CPF_VALIDO_NOME+DUPLICATA_LEGADO}} (com CPF válido) e
{{rdt02.pessoas_por_regra.CPF_INVALIDO_NOME_UF+DUPLICATA_LEGADO}} (com CPF inválido); sem regra:
{{rdt02.pessoas_por_regra.(sem regra)}}.

**(f) Asserção associada.** `02_transformacao · dim_cliente: CPF válido duplicado entre pessoas`;
`cliente: pessoas com nomes normalizados distintos`; `cliente: CPF conformado com tamanho diferente
de 11`; `cliente: origem_unificacao`; `cliente: registros de origem na ponte`;
`cliente: (sistema, id) único na ponte`.

---

## RDT-03 · Duplicatas internas do legado

**Etapa:** 02_transformacao · `unifica_clientes` (regra `DUPLICATA_LEGADO`).

**(a) O que o dado mostrava.** {{rdt03.pares_duplicados}} pares de registros de `CLIENTES`
com o mesmo e-mail, o mesmo telefone e o mesmo nome ({{rdt03.registros_em_pares}} registros,
{{rdt03.registros_em_pares_pct|pct}} da tabela). Em {{rdt03.pares_com_mesmo_cpf_valido}} pares o CPF
válido também é igual; nos outros {{rdt03.pares_com_cpf_ausente_ou_invalido_em_um_lado}} pelo menos
um lado não tem CPF válido. Em {{rdt03.pares_em_que_os_dois_tem_pedidos}} pares, **os dois**
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
iguais nos {{rdt03.pares_duplicados}} casos, o que torna a fusão segura.

**(d) O que se perde.** O que diferencia os dois registros (grafia do nome, máscara do CPF ou o
CPF presente só num deles) fica só nos dados de `stg`; a dimensão mantém o valor do sobrevivente. A
existência do cadastro duplicado só aparece na ponte. Não sabemos se algum dos pares seria, na
realidade, duas pessoas com mesmo e-mail, telefone e nome (improvável, mas não demonstrável).

**(e) Registros afetados.** {{rdt03.registros_absorvidos_no_legado}} registros absorvidos
({{rdt03.registros_absorvidos_no_legado_pct|pct}} de `CLIENTES`) e
{{rdt03.pedidos_reatribuidos_ao_sobrevivente}} pedidos reatribuídos ao sobrevivente
({{rdt03.pedidos_reatribuidos_ao_sobrevivente_pct|pct}} dos pedidos do legado).

**(f) Asserção associada.** `02_transformacao · cliente: registros de origem na ponte`
(todo registro pertence a uma pessoa), `cliente: (sistema, id) único na ponte` e
`pedido: sem cliente_key` (nenhum pedido ficou sem pessoa depois da fusão).

---

## RDT-04 · Conformação de status, incluindo a recusa de pagamento

**Etapa:** 02_transformacao · `conforma_status`.

**(a) O que o dado mostrava.** O legado não tem recusa de pagamento: `CANCELADO` responde por
{{rdt04.celula.LEGADO.CANCELADO.CANCELADO.(nulo)_pct|pct}} dos pedidos
({{rdt04.celula.LEGADO.CANCELADO.CANCELADO.(nulo)}}). No e-commerce, `canceled` tem
{{rdt04.celula.ECOM.canceled.CANCELADO.CANCELAMENTO_pct|pct}} ({{rdt04.celula.ECOM.canceled.CANCELADO.CANCELAMENTO}})
e `payment_declined` {{rdt04.celula.ECOM.payment_declined.CANCELADO.PAGAMENTO_RECUSADO_pct|pct}}
({{rdt04.celula.ECOM.payment_declined.CANCELADO.PAGAMENTO_RECUSADO}}), juntos
{{s1:b.status.ecommerce.canceled_mais_declined_pct|pct}} (`saida/diagnostico/d03_status.csv`). Nos dois
sistemas, cancelados e recusados não têm data de entrega, têm itens e mantêm o valor cheio.

| Sistema | Status de origem | Status conformado | Motivo | Pedidos | % do sistema |
|---|---|---|---|---:|---:|
| LEGADO | ENTREGUE | ENTREGUE | – | {{rdt04.celula.LEGADO.ENTREGUE.ENTREGUE.(nulo)}} | {{rdt04.celula.LEGADO.ENTREGUE.ENTREGUE.(nulo)_pct|pct}} |
| LEGADO | EM TRANSITO | EM_TRANSITO | – | {{rdt04.celula.LEGADO.EM TRANSITO.EM_TRANSITO.(nulo)}} | {{rdt04.celula.LEGADO.EM TRANSITO.EM_TRANSITO.(nulo)_pct|pct}} |
| LEGADO | SEPARACAO | EM_PROCESSAMENTO | – | {{rdt04.celula.LEGADO.SEPARACAO.EM_PROCESSAMENTO.(nulo)}} | {{rdt04.celula.LEGADO.SEPARACAO.EM_PROCESSAMENTO.(nulo)_pct|pct}} |
| LEGADO | CANCELADO | CANCELADO | **nulo** (não distingue) | {{rdt04.celula.LEGADO.CANCELADO.CANCELADO.(nulo)}} | {{rdt04.celula.LEGADO.CANCELADO.CANCELADO.(nulo)_pct|pct}} |
| ECOM | delivered | ENTREGUE | – | {{rdt04.celula.ECOM.delivered.ENTREGUE.(nulo)}} | {{rdt04.celula.ECOM.delivered.ENTREGUE.(nulo)_pct|pct}} |
| ECOM | shipped | EM_TRANSITO | – | {{rdt04.celula.ECOM.shipped.EM_TRANSITO.(nulo)}} | {{rdt04.celula.ECOM.shipped.EM_TRANSITO.(nulo)_pct|pct}} |
| ECOM | processing | EM_PROCESSAMENTO | – | {{rdt04.celula.ECOM.processing.EM_PROCESSAMENTO.(nulo)}} | {{rdt04.celula.ECOM.processing.EM_PROCESSAMENTO.(nulo)_pct|pct}} |
| ECOM | canceled | CANCELADO | CANCELAMENTO | {{rdt04.celula.ECOM.canceled.CANCELADO.CANCELAMENTO}} | {{rdt04.celula.ECOM.canceled.CANCELADO.CANCELAMENTO_pct|pct}} |
| ECOM | payment_declined | CANCELADO | PAGAMENTO_RECUSADO | {{rdt04.celula.ECOM.payment_declined.CANCELADO.PAGAMENTO_RECUSADO}} | {{rdt04.celula.ECOM.payment_declined.CANCELADO.PAGAMENTO_RECUSADO_pct|pct}} |

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
irrecuperável: {{rdt04.cancelados_legado_sem_motivo}} pedidos ({{rdt04.cancelados_legado_sem_motivo_pct|pct}}
do legado) ficam com motivo nulo. Qualquer análise por motivo é assimétrica entre os sistemas. Que
`CANCELADO` seja soma de cancelamento e recusa é hipótese, apoiada só na proporção ({{rdt04.celula.LEGADO.CANCELADO.CANCELADO.(nulo)_pct|pct}} do legado contra
{{s1:b.status.ecommerce.canceled_mais_declined_pct|pct}} do e-commerce); o dado não a prova. A equiparação `SEPARACAO` = `processing` também é uma suposição de
significado. Contar `EM_PROCESSAMENTO` como compra pode errar se o pedido vier a ser cancelado
depois do retrato dos dados.

**(e) Registros afetados.** Os {{base.pedidos}} pedidos passam pelo mapa. Cancelados conformados:
{{rdt04.cancelados_total}} ({{rdt04.cancelados_total_pct|pct}}); recusas de pagamento identificadas:
{{rdt04.recusa_pagamento_ecom}} ({{rdt04.recusa_pagamento_ecom_pct|pct}} do e-commerce). Contam como compra
{{rdt04.pedidos_que_contam_como_compra}} pedidos ({{rdt04.pedidos_que_contam_como_compra_pct|pct}}). Efeito sobre o
alvo (base de {{rdt04.alvo.clientes_na_base}} clientes com pedido até o corte): são
{{rdt04.alvo.positivos_status_efetivo}} positivos ({{rdt04.alvo.positivos_status_efetivo_pct|pct}}); se o cancelado
contasse como compra seriam {{rdt04.alvo.positivos_se_cancelado_contasse}}
({{rdt04.alvo.positivos_se_cancelado_contasse_pct|pct}}), ou seja, {{rdt04.alvo.clientes_cujo_rotulo_muda}} clientes
({{rdt04.alvo.clientes_cujo_rotulo_muda_pct|pct}} da base) mudariam de rótulo. Na janela do alvo há
{{rdt04.pedidos_na_janela_do_alvo}} pedidos, dos quais {{rdt04.pedidos_cancelados_na_janela_do_alvo}} cancelados.

**(f) Asserção associada.** `02_transformacao · status: pedidos cujo status não está no mapa`;
`pedido: sem status_conformado`; `pedido: status_conformado fora da lista`.

---

## RDT-05 · Definição de `VALOR_TOTAL` e `total_amount`

**Etapa:** 02_transformacao · `conforma_valores`.

**(a) O que o dado mostrava.** A reconciliação com a soma dos itens (Semana 1,
`saida/diagnostico/d04_resumo.csv`) mostrou que `total_amount` é a mercadoria líquida (quantidade ×
preço − desconto de linha), **sem frete**, e que `VALOR_TOTAL` é a mercadoria líquida **mais o
frete**, com o desconto `-1` lido como zero. No pipeline, a mesma conta feita em SQL sobre `cnf`:
`VALOR_TOTAL` bate com a fórmula em {{rdt05.pedidos_legado_valor_total_igual_a_formula}} pedidos
({{rdt05.pedidos_legado_valor_total_igual_a_formula_pct|pct}}) e `total_amount + freight_amount` em
{{rdt05.pedidos_ecom_valor_total_igual_a_total_amount_mais_frete}} ({{rdt05.pedidos_ecom_valor_total_igual_a_total_amount_mais_frete_pct|pct}}).
Somas de referência (todos os pedidos): `VALOR_TOTAL` {{rdt05.soma_valor_total_legado_origem|brl}}; `total_amount`
{{rdt05.soma_total_amount_ecom_cru|brl}} e, com o frete, {{rdt05.soma_total_amount_mais_frete_ecom_origem|brl}}. O frete embutido
no legado soma {{rdt05.soma_frete_legado_embutido_no_valor_total|brl}}.

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
`total_amount` cru produziria uma diferença falsa de {{rdt05.soma_frete_ecom_acrescentada_ao_total|brl}}.

**(d) O que se perde.** Nada se apaga: `valor_mercadoria`, `valor_desconto` e `valor_frete` ficam
separados, e o valor sem frete é recuperável (`valor_total − valor_frete`). Perde-se a
identidade com o campo original do e-commerce: quem consultar `total_amount` na origem e
`valor_total` no DW verá números diferentes na quase totalidade dos pedidos. A prova de que o total
do legado tem o frete depende de a soma dos itens ser confiável (itens órfãos ficam de fora, RDT-10).

**(e) Registros afetados.** {{rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado}} pedidos do e-commerce
({{rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado_pct|pct}} dos {{base.pedidos_ecom}}) têm `valor_total`
diferente do `total_amount` cru, por causa do frete; nos {{base.pedidos_legado}} do legado o valor
conformado é igual ao `VALOR_TOTAL` em todos. Pedidos com `valor_total` divergente da origem após a
conformação: {{rdt05.pedidos_com_valor_total_divergente_da_origem}}.

**(f) Asserção associada.** `02_transformacao · pedido: valor_total diverge do total da origem
(>0,01)` e `pedido: valor_mercadoria diverge da soma dos itens (>0,01)`. A soma por sistema, dentro
de 0,1%, é a reconciliação financeira da etapa 3.

---

## RDT-06 · Frete negativo, desconto `-1` e preços atípicos

**Etapa:** 02_transformacao · `conforma_valores`.

**(a) O que o dado mostrava.**

- *Desconto `-1` (legado):* {{rdt06.linhas_desconto_menos_1}} linhas de item
  ({{rdt06.linhas_desconto_menos_1_pct|pct}} de `ITENS_PEDIDO`) em {{rdt06.pedidos_com_desconto_menos_1}} pedidos
  ({{rdt06.pedidos_com_desconto_menos_1_pct|pct}} do legado). É o único valor negativo do campo. O total
  gravado pelo ERP trata `-1` como "sem desconto" (RDT-05).
- *Frete negativo:* {{rdt06.fretes_negativos.LEGADO}} pedidos no legado ({{rdt06.fretes_negativos.LEGADO_pct|pct}}) e
  {{rdt06.fretes_negativos.ECOM}} no e-commerce ({{rdt06.fretes_negativos.ECOM_pct|pct}}), somando
  {{rdt06.soma_fretes_negativos.LEGADO|brl}} e {{rdt06.soma_fretes_negativos.ECOM|brl}}. O total gravado na origem inclui o frete
  negativo como está (fecha com a fórmula), e {{rdt06.fretes_negativos_em_pedidos_cancelados}} desses
  pedidos estão cancelados. Nenhum pedido tem `valor_total` negativo ({{rdt06.pedidos_com_valor_total_negativo}}).
- *Preços:* {{rdt06.precos_lista_10x_mediana_categoria.ecom}} produtos do e-commerce
  ({{rdt06.precos_lista_10x_mediana_categoria.ecom_pct|pct}}) e {{rdt06.precos_lista_10x_mediana_categoria.legado}} do legado
  ({{rdt06.precos_lista_10x_mediana_categoria.legado_pct|pct}}) têm preço de tabela de 10 vezes a mediana da categoria ou
  mais (a maior razão é {{rdt06.maior_razao_preco_lista_mediana_categoria|dec}}). Mas **nenhum item**
  foi vendido por 10 vezes o preço de tabela ({{rdt06.itens_vendidos_a_10x_ou_mais_do_preco_de_tabela}}; a maior razão
  entre preço vendido e preço de tabela é {{rdt06.maior_razao_preco_item_preco_tabela|dec}}).

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

**(e) Registros afetados.** Desconto: {{rdt06.linhas_desconto_menos_1}} linhas
({{rdt06.linhas_desconto_menos_1_pct|pct}} dos itens do legado) e {{rdt06.pedidos_com_desconto_menos_1}} pedidos
({{rdt06.pedidos_com_desconto_menos_1_pct|pct}} do legado). Frete negativo: {{rdt06.fretes_negativos_total}} pedidos
({{rdt06.fretes_negativos_total_pct|pct}} dos {{base.pedidos}}). Preços atípicos: {{rdt06.precos_lista_10x_mediana_categoria.ecom}} +
{{rdt06.precos_lista_10x_mediana_categoria.legado}} produtos, nenhum corrigido.

**(f) Asserção associada.** `02_transformacao · valores: descontos negativos que não são o
sentinela -1`; `item: descontos negativos remanescentes`; `pedido: soma do frete difere da origem
(frete negativo preservado)`; `pedido: valor_total negativo`.

---

## RDT-07 · Mapeamento da taxonomia de produtos

**Etapa:** 02_transformacao · `conforma_categorias`.

**(a) O que o dado mostrava.** O legado tem texto livre ({{s1:b.categoria.legado.distintos_brutos}} grafias; após normalizar caixa e
acento, {{s1:b.categoria.legado.distintos_normalizados_nao_vazios}} rótulos não vazios mais o vazio); o e-commerce tem uma
taxonomia de dois níveis em que os produtos ocupam as folhas. Classificação dos rótulos do legado
(critério da Semana 1, D10; `saida/diagnostico/d03_categoria_mapa.csv`):

| Classe | Rótulos | Produtos | % dos {{rdt07.produtos_legado}} produtos do legado | Itens vendidos | % dos itens |
|---|---:|---:|---:|---:|---:|
| direto (mesmo nível da taxonomia) | {{rdt07.rotulos_distintos_por_classe.direto}} | {{rdt07.produtos_legado.direto}} | {{rdt07.produtos_legado.direto_pct|pct}} | {{rdt07.itens_vendidos_do_legado.direto}} | {{rdt07.itens_vendidos_do_legado.direto_pct|pct}} |
| nível (só a raiz corresponde) | {{rdt07.rotulos_distintos_por_classe.nivel}} | {{rdt07.produtos_legado.nivel}} | {{rdt07.produtos_legado.nivel_pct|pct}} | {{rdt07.itens_vendidos_do_legado.nivel}} | {{rdt07.itens_vendidos_do_legado.nivel_pct|pct}} |
| ambíguo (ELETRO, informatica e games) | {{rdt07.rotulos_distintos_por_classe.ambiguo}} | {{rdt07.produtos_legado.ambiguo}} | {{rdt07.produtos_legado.ambiguo_pct|pct}} | {{rdt07.itens_vendidos_do_legado.ambiguo}} | {{rdt07.itens_vendidos_do_legado.ambiguo_pct|pct}} |
| sem mapeamento (DIVERSOS, OUTROS, vazio) | {{rdt07.rotulos_distintos_por_classe.sem_mapeamento}} | {{rdt07.produtos_legado.sem_mapeamento}} | {{rdt07.produtos_legado.sem_mapeamento_pct|pct}} | {{rdt07.itens_vendidos_do_legado.sem_mapeamento}} | {{rdt07.itens_vendidos_do_legado.sem_mapeamento_pct|pct}} |

A descrição do produto não desempata: em ambos os sistemas, cada um dos {{s1:b.categoria.legado.substantivos}} substantivos iniciais
do legado aparece em no mínimo {{s1:b.categoria.legado.categorias_por_substantivo_min}} categorias, e no e-commerce em no mínimo
{{s1:b.categoria.ecommerce.categorias_por_substantivo_min}} (Semana 1). Produtos com a mesma descrição nos dois sistemas:
{{rdt07.produtos_com_descricao_igual_nos_dois_sistemas}} de {{rdt07.produtos_legado}}, coincidência de nomes gerados e não identidade.

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
Acessórios): {{rdt07.produtos_legado.nivel}} produtos sem `categoria_nivel2`. Para os ambíguos e sem mapeamento,
toda a categoria: {{rdt07.produtos_sem_categoria_nivel1_no_dw}} produtos do DW ficam sem `categoria_nivel1`, e o
atributo "categorias distintas compradas" da ABT os ignora. Os dois rótulos ambíguos podem esconder
mais de uma resposta correta; a classe de `TELEFONIA` (nível) e a de `CELULARES` (direto, sem separar
acessórios) são interpretações da equipe.

**(e) Registros afetados.** {{rdt07.produtos_legado}} produtos do legado reclassificados
(100% da dimensão do legado); {{rdt07.produtos_sem_categoria_nivel1_no_dw}} produtos
({{rdt07.produtos_sem_categoria_nivel1_no_dw_pct|pct}} dos {{rdt07.produtos_legado}} + {{rdt07.produtos_ecom}} do DW) ficam sem
`categoria_nivel1`; {{rdt07.produtos_legado.ambiguo}} são ambíguos ({{rdt07.produtos_legado.ambiguo_pct|pct}} do legado) e
{{rdt07.produtos_legado.sem_mapeamento}} sem mapeamento ({{rdt07.produtos_legado.sem_mapeamento_pct|pct}}).

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
| `DT_ENTREGA = 1900-01-01` (legado; todos com status ENTREGUE) | sentinela | `NULL` + `entrega_sem_data` | {{rdt08.entrega_1900_01_01.legado}} | {{rdt08.entrega_1900_01_01.legado_pct|pct}} do legado |
| Data de entrega nula em pedido não entregue | não aplicável | `NULL`, sem indicador | {{rdt08.entrega_nula_nao_aplicavel_pedido_nao_entregue}} | {{rdt08.entrega_nula_nao_aplicavel_pedido_nao_entregue_pct|pct}} dos pedidos |
| Entrega anterior ao pedido | inconsistência | `NULL` + `entrega_anterior_pedido` | {{rdt08.entrega_anterior_ao_pedido.total}} ({{rdt08.entrega_anterior_ao_pedido.LEGADO}} legado, {{rdt08.entrega_anterior_ao_pedido.ECOM}} e-commerce) | {{rdt08.entrega_anterior_ao_pedido.total_pct|pct}} dos pedidos |
| `CIDADE = 'N/A'` (legado) | sentinela | `NULL` | {{rdt08.cidade_na.registros_legado}} | {{rdt08.cidade_na.registros_legado_pct|pct}} de `CLIENTES` |
| CPF ausente (legado / e-commerce) | não coletada | `NULL` | {{rdt08.cpf_ausente.legado}} / {{rdt08.cpf_ausente.ecom}} | {{rdt08.cpf_ausente.legado_pct|pct}} / {{rdt08.cpf_ausente.ecom_pct|pct}} |
| CPF com dígito verificador inválido (legado / e-commerce) | dado incorreto | mantido, `cpf_valido = falso` | {{rdt08.cpf_dv_invalido.legado}} / {{rdt08.cpf_dv_invalido.ecom}} | {{rdt08.cpf_dv_invalido.legado_pct|pct}} / {{rdt08.cpf_dv_invalido.ecom_pct|pct}} |
| SAC `nota_satisfacao` vazia | não coletada | `NULL` | {{rdt08.sac.nota_vazia}} | {{rdt08.sac.nota_vazia_pct|pct}} do SAC |
| SAC `nota_satisfacao = 0` (fora da escala 1 a 5) | sentinela | `NULL` + `nota_zero` | {{rdt08.sac.nota_zero_linhas_stg}} | {{rdt08.sac.nota_zero_linhas_stg_pct|pct}} do SAC |
| SAC `data_fechamento` vazia (todas com horas de resolução) | dado perdido | `NULL`; horas preservadas | {{rdt08.sac.data_fechamento_vazia}} | {{rdt08.sac.data_fechamento_vazia_pct|pct}} do SAC |
| SAC horas de resolução negativas | inconsistência | `NULL` + `horas_negativas` | {{rdt08.sac.horas_de_resolucao_negativas}} | {{rdt08.sac.horas_de_resolucao_negativas_pct|pct}} do SAC |
| Avaliação sem `rating` | não coletada | `NULL` | {{rdt08.avaliacao.rating_ausente}} | {{rdt08.avaliacao.rating_ausente_pct|pct}} das avaliações |
| `rating` como texto | sintática | convertido para inteiro (indicador `rating_chegou_como_texto`) | {{rdt08.avaliacao.rating_como_texto}} | {{rdt08.avaliacao.rating_como_texto_pct|pct}} |
| Avaliação sem `verified_purchase` | não coletada | `NULL` | {{rdt08.avaliacao.verified_purchase_ausente}} | {{rdt08.avaliacao.verified_purchase_ausente_pct|pct}} |
| Avaliação sem `helpful_votes` | não coletada | `NULL` | {{rdt08.avaliacao.helpful_votes_ausente}} | {{rdt08.avaliacao.helpful_votes_ausente_pct|pct}} |

Pontos que pedem explicação. (1) *`data_fechamento` vazia não é "atendimento em aberto":* os
{{rdt08.sac.data_fechamento_vazia_com_horas_de_resolucao}} atendimentos sem data de fechamento têm tempo de resolução
preenchido, então já foram resolvidos; é a data que se perdeu. (2) *Nenhuma `rating` textual é não
numérica* ({{rdt08.avaliacao.rating_texto_nao_numerico}}), então o `rating` como texto é problema de tipo, não de conteúdo.
(3) As chaves omitidas do NDJSON atingem {{rdt08.avaliacao.linhas_com_alguma_chave_ausente}} avaliações
({{rdt08.avaliacao.linhas_com_alguma_chave_ausente_pct|pct}}), e na `stg` a contagem por chave está em
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

**(d) O que se perde.** A data real de entrega nos {{rdt08.entrega_1900_01_01.legado}} pedidos com
sentinela e nos {{rdt08.entrega_anterior_ao_pedido.total}} inconsistentes; médias de prazo passam a excluí-los e
podem ficar enviesadas se a falha se concentrar em entregas lentas (não verificável). A nota 0, se
significasse "cliente não respondeu", e não "nota mínima", não tem como ser distinguida. A cidade
dos {{rdt08.cidade_na.registros_legado}} clientes com `N/A` só existe se o cadastro do e-commerce a fornecer. A data de fechamento do
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
avaliações vem com offset `-03:00` em {{rdt09.avaliacoes_com_offset}} casos e sem offset em
{{rdt09.avaliacoes_sem_offset}} ({{rdt09.avaliacoes_sem_offset_pct|pct}}); o conjunto de offsets
explícitos tem {{rdt09.avaliacoes_offsets_explicitos_distintos}} valor distinto. Os pedidos do canal `SITE` do legado só
ocorrem entre {{s1:b.canal.legado.site.hora_min}} h e {{s1:b.canal.legado.site.hora_max}} h, o que só faz sentido como hora local.

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
pedidos: {{rdt09.pedidos_ecom_cuja_data_local_difere_da_data_utc}} pedidos do e-commerce
({{rdt09.pedidos_ecom_cuja_data_local_difere_da_data_utc_pct|pct}}) e {{rdt09.legado_dt_pedido_que_mudaria_de_dia_se_fosse_levado_a_utc}}
do legado ({{rdt09.legado_dt_pedido_que_mudaria_de_dia_se_fosse_levado_a_utc_pct|pct}}) mudariam de dia. Em relação aos
limites da pergunta, {{rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo}} pedidos
({{rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo_pct|pct}}) trocariam de lado: {{rdt09.pedidos_que_trocam_de_lado_do_corte}} no corte de
30/06/2025 e {{rdt09.pedidos_que_trocam_de_lado_do_fim_do_alvo}} no fim do alvo (28/09/2025). Isso muda o rótulo de
{{rdt09.clientes_cujo_rotulo_do_alvo_muda_com_a_regua_utc}} clientes ({{rdt09.clientes_cujo_rotulo_do_alvo_muda_com_a_regua_utc_pct|pct}} da base) e faz
{{rdt09.clientes_na_base_que_entram_ou_saem_com_a_regua_utc}} entrarem ou saírem da base. Nas avaliações, {{rdt09.avaliacoes_sem_offset_cuja_data_mudaria_se_fossem_utc}} das
{{rdt09.avaliacoes_sem_offset}} sem offset mudariam de data.

**(f) Asserção associada.** `02_transformacao · pedido: data_pedido fora da régua America/Sao_Paulo`;
`pedido: datas fora do intervalo de dim_tempo`.

---

## RDT-10 · Itens órfãos

**Etapa:** 03_carga_dw · `carrega_fato_item`.

**(a) O que o dado mostrava.** {{rdt10.itens_orfaos.ECOM}} itens do e-commerce
({{rdt10.itens_orfaos.ECOM_pct|pct}} de `order_item`) e {{rdt10.itens_orfaos.LEGADO}} do legado
({{rdt10.itens_orfaos.LEGADO_pct|pct}} de `ITENS_PEDIDO`) não têm pedido. Todos têm identificador de pedido
acima do maior pedido existente: {{rdt10.itens_orfaos_ecom_com_order_id_acima_do_maior_pedido}} no e-commerce e
{{rdt10.itens_orfaos_legado_com_id_pedido_acima_do_maior_pedido}} no legado. Somam {{rdt10.valor_dos_itens_orfaos|brl}} em
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

**(d) O que se perde.** {{rdt10.valor_dos_itens_orfaos|brl}} de mercadoria fora das análises por item e por produto.
Se os pedidos correspondentes forem criados depois do retrato (hipótese compatível com a gravação assíncrona,
não demonstrada), são vendas reais que o DW não enxerga. Não afeta a reconciliação financeira, que opera sobre
pedidos, nem os atributos da ABT calculados sobre `fato_pedido`; afeta `categorias_distintas`, que lê itens.

**(e) Registros afetados.** {{rdt10.itens_orfaos.total}} itens ({{rdt10.itens_orfaos.total_pct|pct}} dos
{{base.itens_legado}} + {{base.itens_ecom}} de origem) ficam em quarentena; {{rdt10.itens_no_fato}}
({{rdt10.itens_no_fato_pct|pct}}) entram no fato.

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
({{s1:e.legado.pedidos_ids_distintos}} e {{s1:e.ecommerce.pedidos_ids_distintos}}) mas **colide** entre eles:
{{s1:e.colisao.pedido_ids_em_comum}} identificadores existem nos dois. Sem o sistema na chave, a união teria
{{rdt11.pedidos_distintos_se_o_sistema_fosse_ignorado}} pedidos em vez de {{rdt11.fato_pedido.linhas}}. O mesmo
produto aparece em mais de uma linha do mesmo pedido em {{s1:e.legado.produto_repetido.pares}} pares no legado e
{{s1:e.ecommerce.produto_repetido.pares}} no e-commerce, e o preço é igual em apenas {{s1:e.legado.produto_repetido.mesmo_preco}} e
{{s1:e.ecommerce.produto_repetido.mesmo_preco}} deles: são vendas distintas. Há {{rdt11.pedidos_nao_efetivos_mantidos_no_fato}}
pedidos cancelados ou recusados ({{rdt11.pedidos_nao_efetivos_mantidos_no_fato_pct|pct}}), com itens e valor cheio, no valor
total de {{rdt11.valor_total_dos_cancelados_no_fato|brl}}.

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
{{rdt11.itens_do_fato_cujo_pedido_e_cancelado}} linhas de item ({{rdt11.itens_do_fato_cujo_pedido_e_cancelado_pct|pct}})
pertencem a pedidos cancelados. A frase torna isso explícito, mas não impede o uso errado. O grão de item não agrega
linhas repetidas do mesmo produto.

**(e) Registros afetados.** {{rdt11.fato_pedido.linhas}} pedidos ({{rdt11.fato_pedido.linhas.LEGADO}} do legado e
{{rdt11.fato_pedido.linhas.ECOM}} do e-commerce; {{rdt11.pedidos_com_chave_natural_repetida}} chaves naturais repetidas) e
{{rdt11.fato_item.linhas}} itens. **Reconciliação financeira** (`saida/reconciliacao/financeira.csv`), soma de `valor_total`
contra o total calculado na origem com a mesma fórmula: legado {{rdt11.recon.LEGADO.soma_dw|brl}} no DW contra
{{rdt11.recon.LEGADO.soma_origem|brl}} na origem (diferença {{rdt11.recon.LEGADO.diferenca_absoluta|brl}},
{{rdt11.recon.LEGADO.diferenca_relativa_pct|pct}}); e-commerce {{rdt11.recon.ECOM.soma_dw|brl}} contra
{{rdt11.recon.ECOM.soma_origem|brl}} (diferença {{rdt11.recon.ECOM.diferenca_absoluta|brl}},
{{rdt11.recon.ECOM.diferenca_relativa_pct|pct}}), ambos dentro do limite de 0,1%. Contra o `total_amount` cru, o e-commerce
teria uma diferença falsa de {{rdt11.recon.ECOM.diferenca_falsa_contra_total_amount_cru|brl}} (o frete; RDT-05).

**(f) Asserção associada.** `03_carga_dw · fato_pedido: linhas == pedidos das duas origens somados`;
`fato_pedido: FK órfã em cliente_sk` (e `data_pedido_sk`, `canal_sk`, `status_sk`);
`reconciliação financeira: LEGADO, diferença relativa` e `... ECOM, diferença relativa` (e as de diferença
absoluta); `fato_item_pedido: linhas == itens com pedido na origem`.

---

## RDT-12 · Pedidos sem cliente correspondente

**Etapa:** 03_carga_dw · `carrega_fato_pedido`.

**(a) O que o dado mostrava.** Nenhum pedido está sem cliente: {{rdt12.pedidos_sem_cliente_na_origem}} pedidos têm um
`ID_CLIENTE` ou `customer_id` inexistente no cadastro do próprio sistema, e {{rdt12.pedidos_com_id_cliente_nulo}} têm o
identificador nulo. A hipótese do esqueleto (pedidos órfãos de cliente) **não se confirmou**. O risco real é outro: os
identificadores de cliente também colidem entre os sistemas. Os {{rdt12.pedidos_legado_cujo_id_cliente_existe_tambem_no_ecommerce}}
pedidos do legado ({{rdt12.pedidos_legado_cujo_id_cliente_existe_tambem_no_ecommerce_pct|pct}}) e
{{rdt12.pedidos_ecom_cujo_id_cliente_existe_tambem_no_legado}} do e-commerce
({{rdt12.pedidos_ecom_cujo_id_cliente_existe_tambem_no_legado_pct|pct}}) apontam para um identificador que existe nos dois
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

**(e) Registros afetados.** {{rdt12.fato_pedido_com_cliente_sk_orfao}} pedidos ({{rdt12.fato_pedido_com_cliente_sk_orfao_pct|pct}}
dos {{rdt11.fato_pedido.linhas}}). Membros "DESCONHECIDO" criados: {{rdt12.cliente_desconhecido_criado}}. Para dimensionar o que
a junção correta evita: {{rdt12.pedidos_cujo_cliente_foi_fundido_com_outro_registro}} pedidos
({{rdt12.pedidos_cujo_cliente_foi_fundido_com_outro_registro_pct|pct}}) pertencem a uma pessoa que reúne mais de um registro de
cadastro (RDT-02 e RDT-03).

**(f) Asserção associada.** `03_carga_dw · fato_pedido: FK órfã em cliente_sk`;
`02_transformacao · pedido: sem cliente_key`.

---

## RDT-13 · Atendimentos e avaliações que não ligam a nenhum pedido

**Etapa:** 02_transformacao · `liga_sac_e_avaliacoes`; 03_carga_dw · `carrega_fatos_auxiliares`.

**(a) O que o dado mostrava.**

- *SAC:* {{rdt13.sac.registros}} registros, dos quais {{rdt13.sac.linhas_repetidas_removidas}} são linhas idênticas repetidas
  ({{rdt13.sac.linhas_repetidas_removidas_pct|pct}}), restando {{rdt13.sac.atendimentos_conformados}} atendimentos. O pedido declarado
  existe no sistema indicado em {{rdt13.sac.pedido_declarado_existe_no_sistema_indicado}} deles
  ({{rdt13.sac.pedido_declarado_existe_no_sistema_indicado_pct|pct}}), mas o CPF do atendimento é o do dono desse pedido em apenas
  {{rdt13.sac.cpf_do_atendimento_e_o_do_dono_do_pedido_declarado}} caso, e a abertura é posterior ao pedido em
  {{rdt13.sac.abertura_posterior_ao_pedido_declarado_pct|pct}} (o esperado ao acaso). Pelo CPF, {{rdt13.sac.com_cliente_por_cpf}}
  atendimentos encontram uma pessoa ({{rdt13.sac.com_cliente_por_cpf_pct|pct}}); {{rdt13.sac.sem_cliente}}
  ({{rdt13.sac.sem_cliente_pct|pct}}) não encontram, e {{rdt13.sac.cpf_ambiguo_entre_pessoas}} têm CPF de mais de uma pessoa.
- *Avaliações:* {{rdt13.avaliacao.registros}} objetos. O pedido de `order.ref` existe em
  {{rdt13.avaliacao.pedido_declarado_existe}} ({{rdt13.avaliacao.pedido_declarado_existe_pct|pct}}), mas o produto avaliado está entre os
  itens desse pedido em apenas {{rdt13.avaliacao.produto_avaliado_esta_nos_itens_do_pedido_declarado}}
  ({{rdt13.avaliacao.produto_avaliado_esta_nos_itens_do_pedido_declarado_pct|pct}}), e {{rdt13.avaliacao.enviada_antes_do_pedido_declarado_pct|pct}}
  foram enviadas antes do pedido. **O NDJSON não tem campo de CPF**
  ({{rdt13.avaliacao.campos_de_cpf_no_ndjson}}), então não há ligação com cliente; o SKU liga ao produto em
  {{rdt13.avaliacao.com_produto_pelo_sku}} ({{rdt13.avaliacao.com_produto_pelo_sku_pct|pct}}).

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
fração se perde com o resto, e não há como identificá-la. (ii) {{rdt13.sac.sem_cliente}} atendimentos sem cliente não
contribuem para nenhum atributo da ABT. (iii) As avaliações não contribuem com nenhum atributo por cliente (a nota média de
avaliações), só com análises por produto. (iv) Linhas repetidas do SAC são removidas, e perde-se a informação de que
foram exportadas mais de uma vez (a exportação é manual e concatenada).

**(e) Registros afetados.** SAC: {{rdt13.sac.registros}} registros de entrada,
{{rdt13.dw.fato_atendimento.linhas}} no fato; {{rdt13.sac.pedido_key_preenchido}} com pedido ligado; {{rdt13.dw.fato_atendimento.sem_cliente}}
sem cliente ({{rdt13.dw.fato_atendimento.sem_cliente_pct|pct}}). Avaliações: {{rdt13.dw.fato_avaliacao.linhas}} no fato, nenhuma com pedido
ou cliente ligado ({{rdt13.avaliacao.cliente_key_preenchido}}).

**(f) Asserção associada.** `03_carga_dw · fato_atendimento: pedido_sk preenchido`; `fato_avaliacao: pedido_sk preenchido`;
`fato_atendimento: cliente_sk órfão`; `fato_avaliacao: produto_sk nulo`; `02_transformacao · sac: protocolos repetidos
com conteúdo diferente`; `sac: protocolo único após remover linhas idênticas`; `avaliação: sem produto_key`.

---

## RDT-14 · Desenho dos atributos da ABT e verificação de ausência de vazamento

**Etapa:** 04_abt · `--correta` (regras completas em `docs/DICIONARIO_ABT.md` e `saida/abt/dicionario_atributos.csv`).

**(a) O que o dado mostrava.** Há informação posterior ao corte em lugares fáceis de usar sem perceber:
{{abt.pedidos_pre_corte_entregues_depois_do_corte}} pedidos anteriores a 30/06/2025 foram entregues depois dessa data
(um `dias_entrega` desses pedidos seria conhecimento do futuro); o status gravado é o do retrato dos dados, e a origem
não guarda a data do cancelamento ({{abt.pedidos_cancelados_nos_30_dias_antes_do_corte}} dos
{{abt.pedidos_ate_o_corte}} pedidos até o corte são cancelados e foram feitos nos 30 dias anteriores a ele, os mais
expostos à dúvida de "já estava cancelado no corte?"); o cadastro (`dim_cliente`) não tem data de atualização. O histórico
começa em 2023-01-01 (Semana 1): {{rdt14.clientes_com_primeiro_pedido_em_2023_01}} clientes
({{rdt14.clientes_com_primeiro_pedido_em_2023_01_pct|pct}}) têm o primeiro pedido observado em janeiro de 2023, e para
eles "tempo como cliente" é limitado pelo início dos dados. A população (clientes com ao menos um pedido até o corte) tem
{{abt.linhas}} pessoas, das quais {{abt.clientes_so_com_pedidos_cancelados_ate_o_corte}}
({{abt.clientes_so_com_pedidos_cancelados_ate_o_corte_pct|pct}}) só têm pedidos cancelados até o corte. O SAC não traz
nenhum atendimento para {{rdt14.clientes_sem_qualquer_atendimento_sac}} clientes
({{rdt14.clientes_sem_qualquer_atendimento_sac_pct|pct}}), e as avaliações não ligam a cliente (RDT-13).

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

**(c) Decisão e justificativa.** Alternativa 6. São {{rdt14.atributos}} atributos (recência, frequência, valor,
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

**(e) Registros afetados.** A ABT tem {{abt.linhas}} clientes e {{abt.positivos}} positivos
({{abt.positivos_pct|pct}}); {{rdt14.clientes_so_no_legado_na_abt}} só no legado
({{rdt14.clientes_so_no_legado_na_abt_pct|pct}}), {{rdt14.clientes_so_no_ecom_na_abt}} só no e-commerce
({{rdt14.clientes_so_no_ecom_na_abt_pct|pct}}) e {{rdt14.clientes_nos_dois_sistemas_na_abt}} nos dois
({{rdt14.clientes_nos_dois_sistemas_na_abt_pct|pct}}). Atributos "efetivos" nulos em
{{abt.clientes_so_com_pedidos_cancelados_ate_o_corte}} clientes; prazo de entrega só com entregas até o corte
({{abt.pedidos_pre_corte_entregues_depois_do_corte}} pedidos deixam de contribuir).

**(f) Asserção associada.** `04_abt_correta · atributos: valores que mudam se o DW for cortado em 30/06/2025`;
`alvo: linhas == clientes unificados com pedido até o corte`; `alvo: positivos == recálculo independente em pandas`;
`taxa de positivos do alvo (registrada)`; `atributos: recência negativa`; `atributos: tempo_como_cliente negativo`;
`atributos: data_corte diferente de 2025-06-30`; `atributos: colunas do alvo entre os atributos`.

---

## RDT-15 · Vazamentos introduzidos deliberadamente na versão de comparação

**Etapa:** 04_abt · `--vazamento` e `--vazamento-sutil`.

**(a) O que o dado mostrava.** A informação que vaza já está no DW: há {{rdt15.pedidos_efetivos_apos_o_corte}} pedidos
efetivos posteriores ao corte, dos quais {{rdt15.pedidos_efetivos_na_janela_do_alvo}} na própria janela do alvo. Basta tirar
a cláusula de data de um agregado para que o atributo os enxergue. Na versão construída: a recência muda para
{{rdt15.recencia_diferente_da_correta}} clientes ({{rdt15.recencia_diferente_da_correta_pct|pct}}) e fica negativa em todos eles
({{rdt15.recencia_negativa}}; {{rdt15.recencia_negativa_na_janela_do_alvo}} com o último pedido dentro da janela do alvo e
{{rdt15.recencia_negativa_depois_da_janela_do_alvo}} depois dela). **Todos** os {{rdt15.positivos_com_recencia_negativa}} positivos
({{rdt15.positivos_com_recencia_negativa_pct|pct}}) têm recência negativa: entre os clientes de recência negativa
{{rdt15.taxa_de_positivos_com_recencia_negativa_pct|pct}} são positivos, e entre os demais, {{rdt15.taxa_de_positivos_com_recencia_nao_negativa_pct|pct}}.
A frequência passa a incluir {{rdt15.pedidos_a_mais_na_frequencia}} pedidos a mais em {{rdt15.frequencia_diferente_da_correta}}
clientes ({{rdt15.frequencia_diferente_da_correta_pct|pct}}). A média e o desvio globais do valor monetário, que a
normalização usa, são {{rdt15.zscore.media_global_de_valor_monetario|brl}} e {{rdt15.zscore.desvio_global_de_valor_monetario|brl}}.

**(b) Alternativas consideradas.**

1. *Atributo que conta compras futuras diretamente* (por exemplo, "pedidos nos 90 dias seguintes"). Descartada: é
   vazamento óbvio demais para ser realista; ninguém o cometeria por engano.
2. *Vazar pelo status ou pela data de entrega pós-corte.* Possível (há {{abt.pedidos_pre_corte_entregues_depois_do_corte}}
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

**(e) Registros afetados.** Vazamentos 1 e 2: {{rdt15.recencia_diferente_da_correta}} e {{rdt15.frequencia_diferente_da_correta}} clientes
({{rdt15.recencia_diferente_da_correta_pct|pct}} dos {{rdt15.clientes}}). Vazamento 3: os {{rdt15.clientes}} clientes (100%), pois a
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
| RDT-01 | Carga completa, recriando a `stg` | {{rdt01.registros_carregados}} | 100,00% | Histórico de versões das linhas | `01_extracao · linhas <fonte>.<tabela>` |
| RDT-02 | CPF (válido ou não) + guarda de nome/UF; sem nome + UF | {{rdt02.registros_unidos_em_outra_pessoa}} registros unidos | {{rdt02.registros_unidos_em_outra_pessoa_pct|pct}} dos registros de cliente | Pessoas sem CPF não são pareadas ({{rdt02.pessoas_sem_cpf}}) | `cliente: (sistema, id) único na ponte` |
| RDT-03 | Fundir duplicatas do legado (sobrevivente + ponte) | {{rdt03.registros_absorvidos_no_legado}} registros | {{rdt03.registros_absorvidos_no_legado_pct|pct}} de `CLIENTES` | Variantes de grafia/CPF do registro absorvido | `cliente: registros de origem na ponte` |
| RDT-04 | `CANCELADO` + `motivo_cancelamento`; compra = não cancelado | {{rdt04.cancelados_total}} cancelados | {{rdt04.cancelados_total_pct|pct}} dos pedidos | Motivo no legado ({{rdt04.cancelados_legado_sem_motivo}}) | `pedido: status_conformado fora da lista` |
| RDT-05 | `valor_total` = mercadoria − desconto + frete nos dois | {{rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado}} pedidos do e-commerce | {{rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado_pct|pct}} do e-commerce | Não (componentes separados) | `pedido: valor_total diverge do total da origem` |
| RDT-06 | `-1` → 0 com indicador; frete negativo mantido; preços mantidos | {{rdt06.linhas_desconto_menos_1}} linhas; {{rdt06.fretes_negativos_total}} pedidos | {{rdt06.linhas_desconto_menos_1_pct|pct}} dos itens do legado; {{rdt06.fretes_negativos_total_pct|pct}} dos pedidos | Significado de `-1` e do frete negativo | `item: descontos negativos remanescentes` |
| RDT-07 | Mapear só o que o rótulo sustenta | {{rdt07.produtos_sem_categoria_nivel1_no_dw}} produtos sem nível 1 | {{rdt07.produtos_sem_categoria_nivel1_no_dw_pct|pct}} dos produtos | Categoria dos ambíguos e sem mapeamento; ramo dos de nível raiz | `produto: ambíguo/sem_mapeamento com nivel1 preenchido` |
| RDT-08 | `NULL` + indicador em sentinelas e inconsistências; nada imputado | {{rdt08.entrega_1900_01_01.legado}} entregas com sentinela e {{rdt08.entrega_anterior_ao_pedido.total}} anteriores ao pedido (as demais ausências estão na tabela da ficha) | {{rdt08.entrega_1900_01_01.legado_pct|pct}} do legado e {{rdt08.entrega_anterior_ao_pedido.total_pct|pct}} dos pedidos | Data de entrega, nota 0, data de fechamento | `pedido: data_entrega com sentinela 1900 remanescente` |
| RDT-09 | Hora local de Brasília como régua | {{rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo}} pedidos trocariam de lado com UTC | {{rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo_pct|pct}} dos pedidos | Hora exata do dia | `pedido: data_pedido fora da régua America/Sao_Paulo` |
| RDT-10 | Itens sem pedido em quarentena, fora do fato | {{rdt10.itens_orfaos.total}} itens | {{rdt10.itens_orfaos.total_pct|pct}} dos itens | {{rdt10.valor_dos_itens_orfaos|brl}} de mercadoria fora das análises por item | `fato_item_pedido: itens + quarentena == itens de cnf` |
| RDT-11 | Grão: pedido por (sistema, id), qualquer status; item como na origem | {{rdt11.fato_pedido.linhas}} pedidos; {{rdt11.fato_item.linhas}} itens | 100,00% dos pedidos | Pedidos cancelados ficam no fato e exigem filtro | `fato_pedido: linhas == pedidos das duas origens somados` |
| RDT-12 | Sem cliente "DESCONHECIDO"; a carga exige correspondência | {{rdt12.fato_pedido_com_cliente_sk_orfao}} pedidos | {{rdt12.fato_pedido_com_cliente_sk_orfao_pct|pct}} dos pedidos | Nada hoje | `fato_pedido: FK órfã em cliente_sk` |
| RDT-13 | SAC liga ao cliente pelo CPF; nenhuma fonte liga ao pedido; avaliação só ao produto | {{rdt13.sac.registros}} SAC e {{rdt13.avaliacao.registros}} avaliações sem pedido | 100,00% dos registros | Ligação a pedido; {{rdt13.sac.sem_cliente}} atendimentos sem cliente | `fato_atendimento: pedido_sk preenchido` |
| RDT-14 | Atributos só dos fatos, até o corte; verificação contra o DW "cortado" | {{abt.linhas}} clientes, {{rdt14.atributos}} atributos | 100,00% da população | Status do retrato; tempo de relacionamento real; perfil cadastral e avaliações | `atributos: valores que mudam se o DW for cortado em 30/06/2025` |
| RDT-15 | Dois agregados sem filtro de data + z-score antes da partição | {{rdt15.recencia_diferente_da_correta}} clientes (vazamentos 1 e 2); {{rdt15.clientes}} (vazamento 3) | {{rdt15.recencia_diferente_da_correta_pct|pct}}; 100,00% | Versão sem valor de negócio, só de medida | `04_abt_vazamento · (intencional) clientes com recencia_dias diferente da correta` |

---

## Reflexão

A parte mais cara deste trabalho não foi escrever código, foi decidir o que o dado queria dizer. Quase toda ficha do RDT tem a mesma
forma: o dado admite duas leituras plausíveis, e a escolha altera números que depois alguém cita como se fossem do mundo, e não de uma
decisão nossa.

Três fichas mostram isso. No RDT-05, o `total_amount` cru do e-commerce difere do valor conformado em
{{rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado}} pedidos; sem descobrir que ele não inclui o frete, a reconciliação
financeira acusaria uma diferença que não existe. No RDT-09, a régua de tempo (hora de Brasília, e não UTC) decide de que lado do corte ou do
fim da janela caem {{rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo}} pedidos, ou seja, o alvo depende de um fuso. No RDT-04,
tratar pedido cancelado como não-compra define o que é "recompra" para {{rdt04.cancelados_total}} cancelamentos.

Nem toda decisão tem como ser conferida. No RDT-02, {{rdt02.registros_unidos_em_outra_pessoa}} registros foram unidos a outra identidade por
CPF ou por nome e UF, e não existe verdade externa para checar. A guarda de nome e UF reduz o risco; não o elimina.

O experimento de vazamento deixou a lição mais incômoda. As asserções provam que o vazamento sutil existe, mas as métricas não o
mostram (`relatorio/semana4/resultados_experimento.md`). Olhar só o desempenho não basta: é preciso verificar a linhagem do dado, e é por isso
que o RDT-14 testa a ABT contra o DW "como estava" em 30/06/2025.

Deixamos limites declarados, em vez de escondidos. A ABT guarda o status do retrato dos pedidos, não o do corte (D40). Entram na população
{{abt.clientes_so_com_pedidos_cancelados_ate_o_corte}} clientes que só têm pedidos cancelados até o corte (D38). As avaliações não ligam a
cliente (D30), e por isso `nota_media_avaliacoes` ficou fora da ABT.

O que levamos: a transformação é o ponto em que o julgamento do analista entra nos dados e permanece lá, invisível. O RDT é a resposta
antecipada à pergunta "de onde veio este número?", e só vale se registrar também o que cada decisão custou.
