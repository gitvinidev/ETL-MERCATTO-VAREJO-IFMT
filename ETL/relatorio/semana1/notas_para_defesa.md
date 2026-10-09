# Notas para a defesa — Semana 1

Material interno da equipe. Para cada conclusão do relatório: como foi obtida,
o que a invalidaria e a pergunta mais provável do professor. Ao final, as
decisões interpretativas e as alternativas descartadas.

Os números estão em `saida/diagnostico/numeros.json`. Para reproduzir tudo:
`docker compose exec etl python -m diagnostico.<script>` (d01 a d06), a partir de `ETL/`.

---

## Parte 1 — Conclusões

### 1. O total de registros bate com o roteiro (≈ 2,2 mi), não com o README (≈ 1,9 mi)

- **Como:** `d01_volumes_periodos.py` faz `COUNT(*)` em cada tabela das duas bases. Conta os
  registros do CSV com `pandas.read_csv` (que respeita aspas e quebras de linha internas) e os
  objetos do NDJSON linha a linha. Total de 2.205.864, desvio de 0,27% em relação a 2,2 mi
  (`v.total_registros`, `v.desvio_roteiro_2_2mi_pct`).
- **O que invalidaria:** contar linhas físicas do CSV (97.518) em vez de registros, que muda
  pouco. Também excluir `category` (21 linhas), que é irrelevante. O resultado depende de
  `ESCALA=1.0`; com `ESCALA=0.2`, os números caem.
- **Pergunta provável:** "Por que o README fala em 1,9 milhão?" Não sabemos. Uma hipótese é a
  documentação desatualizada em relação ao gerador. Constatamos apenas qual valor corresponde
  ao ambiente.

### 2. Os dois sistemas cobrem 2023-01 a 2025-12, inclusive a janela do alvo, e a aquisição não altera o comportamento

- **Como:** `d01`, com MIN/MAX e `GROUP BY` mensal em SQL. Antes e depois de 2024-03, compara
  pedidos por mês, canais, cancelamento e ticket médio (`d01_aquisicao_*.csv`).
- **O que invalidaria:** uma mudança de semântica que não apareça em volume nem em composição,
  por exemplo o significado de um campo mudando sem mudar a distribuição. Em `d04` testamos
  isso para os valores: as hipóteses dão o mesmo resultado nos dois períodos.
- **Pergunta provável:** "Se o ERP existe desde 2016, onde está o histórico?" Não foi entregue.
  `DT_CADASTRO` e `DT_PEDIDO` começam em 2023-01-01. Isso limita atributos como "tempo de
  relacionamento" e deve aparecer como limitação na ABT.

### 3. O CPF é a única chave viável entre cadastros; e-mail e telefone não servem

- **Como:** `d02_chaves.py` lê as colunas inteiras, sem LIMIT. Normaliza mantendo só dígitos e
  valida os dois dígitos verificadores (`comum.cpf_valido`, que rejeita sequências repetidas).
  A interseção é feita entre conjuntos de CPFs válidos. Nos pares, compara o nome normalizado
  (sem acento, caixa baixa, espaços colapsados) e o e-mail com `lower` + `trim`.
- **O que invalidaria:** pares por CPF em que o nome discorda em massa. Só 2 de 11.876
  discordam, e devem ser CPFs reaproveitados ou digitados errado. Para o e-mail, bastaria um
  domínio comum aos dois sistemas; não existe nenhum.
- **Pergunta provável:** "Cobertura de 25,13% ou de 13,5%: qual é a certa?" As duas, porque
  são os dois sentidos. 25,13% dos registros de CLIENTES têm par no e-commerce; 13,5% dos
  registros de customer têm par no legado. A base de cada percentual é o total de registros
  da tabela de origem, não só os CPFs válidos.
- **Pergunta provável 2:** "E os CPFs inválidos?" Ficam fora da interseção no limite inferior.
  O limite superior (Tabela 4) os recupera por nome + UF, com o custo de 787 homônimos.

### 4. O vínculo do SAC e do NDJSON com o pedido não se sustenta; a ligação possível é pelo CPF

- **Como:** em `d02`, o teste de existência verifica se o id está no conjunto de IDs de cada
  sistema. O teste de consistência compara o CPF do atendimento com o CPF do cliente dono do
  pedido, via `PEDIDOS ⋈ CLIENTES` e `orders ⋈ customer`, nos dois sistemas. O teste temporal
  compara `data_abertura` com a data do pedido em hora local. No NDJSON, verificamos se o par
  (pedido, SKU) existe nos itens.
- **O que invalidaria:** uma regra de correspondência que não testamos, como um id deslocado
  ou um id de outra tabela. Testamos o id no sistema indicado e no outro; nos dois a
  concordância de CPF é praticamente zero (1 caso) e a ordem temporal fica em ≈ 50%,
  exatamente o esperado ao acaso.
- **Pergunta provável:** "O dicionário diz que o id pertence ao sistema indicado. Vocês
  refutaram isso?" Por existência, não: 0 casos "só no outro sistema". O que refutamos é que o
  id identifique o pedido do cliente que abriu o atendimento. A colisão de IDs torna o teste de
  existência incapaz de discriminar, por isso usamos o CPF.

### 5. Heterogeneidade semântica: os cinco casos

| Caso | Como | O que invalidaria | Pergunta provável |
|---|---|---|---|
| Valor do pedido | d04 em SQL | ver conclusão 7 | "Como sabem que a diferença é o frete?" A diferença média total − itens (44,28) bate com o frete médio (44,31), e H3 fecha 100% |
| CANCELADO × canceled/payment_declined | d03, GROUP BY status, com entrega, itens e valor | um campo no legado que distinga a recusa, que não existe | "Então CANCELADO = canceled + payment_declined?" Não afirmamos isso. A proporção (12,13% contra 13%) é compatível, mas é só evidência indireta |
| SITE × web | d03, distribuição horária por canal em hora local | DT_PEDIDO ser outra coisa que não o momento da compra, o que é justamente a hipótese | "Pode ser só o fuso?" Não. Um deslocamento de fuso desloca a faixa, mas não zera a madrugada |
| Categoria | d03, normalização + mapa manual `MAPA` | outra leitura de "ELETRO" | "Por que não usaram a descrição para decidir?" Nos dois sistemas, o substantivo da descrição aparece em 15 ou mais categorias. A descrição não carrega informação de categoria |
| Notas | d03, tipos e domínio | metadado do SAC sobre o zero | "As escalas são iguais?" Não dá para provar. As distribuições são iguais, e isso não basta |

### 6. Desconto por linha; formato de CPF estável no tempo (hipóteses do roteiro que caíram)

- **Como:** `d03`, com razões desconto/(qtd × unitário) e desconto/unitário por quantidade. Em
  `d04`, H5/H6 (por unidade) explicam no máximo 9,58%.
- **O que invalidaria:** um desconto por unidade aplicado só quando a quantidade é 1. Não
  explicaria a estabilidade da razão por linha em qtd 2 e 3.
- **Pergunta provável:** "Por que H5 dá 8,25% no e-commerce?" Nos pedidos em que todos os itens
  têm quantidade 1, desc_linha = desc_unid e H5 coincide com H2. Esses pedidos são 23.084
  (`c.ecommerce.pedidos_so_qtd1`), contra 23.088 que satisfazem H5. No legado, 12.645 pedidos
  só têm quantidade 1, e H6 é satisfeita por 12.456, porque os pedidos com sentinela saem.

### 7. `VALOR_TOTAL` = mercadoria − desconto + frete; `total_amount` = mercadoria − desconto

- **Como:** `d04_valores.py`. Uma CTE agrega os itens por pedido; um LEFT JOIN preserva os
  pedidos sem itens; flags `ABS(total − fórmula) <= 0.01` contadas em SQL; quebra por período,
  canal e status. Os resíduos são agrupados por valor.
- **O que invalidaria:** uma hipótese alternativa que também chegue a ≈ 100%. Nenhuma das seis
  passa de 9,58% fora da vencedora.
- **Pergunta provável:** "E os 4.003 pedidos que não batem?" São exatamente os pedidos com
  desconto −1. O resíduo é −1 por linha com sentinela. O sistema de origem tratou −1 como
  "sem desconto".
- **Pergunta provável 2:** "Frete negativo entra?" Entra como está. H3 é satisfeita também
  nesses pedidos. O significado (estorno, subsídio, erro) não se decide pelo dado → RDT-06.

### 8. Anomalias "agora" × "depois"

- **Critério de classificação:** "agora" = mensurável dentro de uma única fonte, sem
  nenhuma regra de integração. "Depois" = o número depende de uma decisão de integração
  (chave de cliente, fuso comum, definição de pessoa), e por isso damos limites.
- **Como:** `d05_anomalias.py`. Integridade referencial com LEFT JOIN / NOT EXISTS em SQL;
  duplicidade em pandas sobre a tabela inteira; fronteiras de fuso em SQL. Os rótulos
  simulam o alvo "comprou entre 01/07 e 28/09/2025" sobre todos os pedidos, sem filtro de
  status.
- **Limites:**
  - Clientes comuns:
    - inferior: registros com CPF válido em comum;
    - superior: + registros sem CPF válido em ao menos um lado, com par por nome + UF.
  - SAC no sistema errado:
    - inferior: CPF existe só no cadastro do outro sistema;
    - superior: + CPF nos dois cadastros + CPF em nenhum.
  - Fuso:
    - inferior: pedidos do e-commerce cujo dia local ≠ dia UTC, na data do corte e na do fim do alvo;
    - superior: + pedidos do legado que mudariam de dia se o horário sem fuso fosse levado a UTC (+3 h).
- **O que invalidaria:** a regra de unificação real ser outra (a Semana 2 decide), ou
  `DT_PEDIDO` já estar em UTC.
- **Pergunta provável:** "Por que duplicata do legado está em 'agora' e cliente comum em
  'depois', se ambos são duplicidade?" A duplicata interna aparece sem cruzar nenhuma fonte. O
  cliente comum só existe quando as duas fontes são cruzadas, e o número depende da regra de
  cruzamento.
- **Pergunta provável 2:** "Os 2.250 pares do legado são mesmo duplicatas?" Mesmo e-mail,
  mesmo telefone e mesmo nome nos 2.250. Em 1.302, também o mesmo CPF válido; nos demais, ao
  menos um dos lados não tem CPF válido. Os 13 casos a mais em "nome + data de cadastro"
  (4.513 − 4.500) são homônimos.

### 9. Grão

- **Como:** `d06_grao.py`. COUNT DISTINCT dos ids; interseção dos conjuntos de ids; GROUP BY
  (pedido, produto) HAVING COUNT > 1, com contagem de preços distintos; simulação do alvo com
  e sem pedidos não efetivos.
- **O que invalidaria:** a mesma linha de item duplicada com preço igual (seria duplicata e
  não venda distinta). Ocorre em 1 par no legado e 2 no e-commerce.
- **Pergunta provável:** "Se cancelado entra no fato, a ABT conta cancelado como compra?" Não
  necessariamente. O fato guarda o pedido; a ABT filtra pela `dim_status`. Essa é a decisão do
  RDT-04/RDT-14, não do grão.

---

## Parte 2 — Decisões interpretativas e alternativas descartadas

### D1. Frase do grão de `fato_pedido`

- **Adotada:** "um pedido registrado em um dos dois sistemas de origem, identificado pelo par
  (sistema de origem, identificador do pedido na origem), qualquer que seja o seu status".
- **Alternativa mais forte (descartada):** "um pedido efetivado", excluindo `CANCELADO`,
  `canceled` e `payment_declined`. O que mudaria na ABT (`d06_status_abt.csv`):
  - saem 15.774 pedidos do legado (12,13%) e 36.403 do e-commerce (13%);
  - a taxa de alvo positivo cai de 20,44% para 18,08% no legado e de 23,48% para 20,74% no e-commerce;
  - o rótulo muda para 1.006 clientes do legado (2,37%) e 2.176 do e-commerce (2,74%);
  - a frequência muda para 11.398 (26,8%) e 25.532 (32,12%);
  - 1.517 + 2.380 clientes sairiam da população, porque só têm pedidos não efetivos antes do corte.
- **Motivo do descarte:**
  - mistura regra de negócio da ABT com o grão do DW;
  - quebra a reconciliação financeira contra a origem, que exige todos os pedidos;
  - o DDL já prevê `dim_status` para filtrar.
- **Outra alternativa descartada:** "um pedido de um cliente unificado". Isso descreve a
  conformação da `dim_cliente`, não o grão, e exigiria "e também" para pedidos sem cliente
  unificado.

### D2. Frase do grão de `fato_item_pedido`

- **Adotada:** a linha de item tal como registrada na origem.
- **Descartada:** "um produto dentro de um pedido", com agregação por (pedido, produto). Em
  194 de 195 pares do legado e 126 de 128 do e-commerce, os preços diferem. Agregar
  transformaria `valor_unitario` em média e perderia o preço praticado.

### D3. `CANCELADO` e `payment_declined`

- **Adotada no texto:** `CANCELADO` provavelmente agrega cancelamento e recusa de pagamento.
- **Evidência:** proporção (12,13% × 13%), ausência de entrega e itens/valor preservados em
  todos.
- **Descartada:** "`CANCELADO` = `canceled`". Seria a hipótese mais simples, mas a proporção
  fica 4 pontos acima.
- **Indecidível:** quanto de `CANCELADO` é recusa. O legado não tem campo que separe.

### D4. Significado de `SITE` no legado

- **Adotada:** `DT_PEDIDO` de `SITE` registra o fechamento em horário comercial, não o momento
  da compra on-line; portanto `SITE` ≠ `web` no sentido temporal.
- **Descartadas:**
  - (a) "`SITE` é um canal de balcão mal rotulado": não há evidência adicional;
  - (b) "efeito de fuso": um deslocamento constante não esvaziaria a madrugada.

### D5. Notas: mesma escala ou não

- **Adotada:** não é possível afirmar.
- **Descartada:** "as escalas são iguais porque as distribuições são iguais". Distribuição
  igual não implica significado igual, e o 0 do SAC fica sem explicação.

### D6. Classificação "agora × depois"

- **Adotada:** o critério é se o número depende de uma decisão de integração.
- **Descartada:** classificar pelo tipo de erro (duplicidade, data, valor). Isso colocaria
  duplicata interna e cliente comum no mesmo grupo, embora só o segundo dependa de regra de
  cruzamento.

### D7. Leitura de fuso usada nos números

- **Adotada:** hora local (America/Sao_Paulo) para `placed_at`; `DT_PEDIDO` usado como está.
- **Motivo:** os horários de `DT_PEDIDO` (8h–21h) só fazem sentido como hora local de
  operação.
- **Alternativa:** UTC para tudo. Os números alternativos estão em `d01_periodos_corte.csv`
  (coluna `ecommerce_utc`) e em `d05_fuso_fronteiras.csv`.

### D8. Base dos percentuais de cobertura

- **Adotada:** total de registros da tabela de origem.
- **Descartada:** só os CPFs válidos distintos (30,45% e 16,12%, também registrados em
  `numeros.json`). Superestimaria a cobertura em relação à população real de clientes.

### D9. Citação do referencial

- O referencial teórico não traz autor nomeado. Citamos como autoria institucional
  (IFMT, 2026).
- **Alternativa:** citar o professor como autor. Descartada por não constar no documento.
  Convém confirmar com o professor.

### D10. Mapeamento de categorias (classe por rótulo)

- **Critério:** "direto" = existe um nó com o mesmo significado e no nível em que o
  e-commerce classifica; "nível" = só a raiz corresponde; "ambíguo" = cobre dois ramos;
  "sem mapeamento" = genérico ou vazio.
- **Casos discutíveis:**
  - `ELETRO` pode ser eletrodoméstico ou eletrônico;
  - `TELEFONIA` foi classificado como "nível";
  - `CELULARES` foi tratado como `Smartphones`, sem considerar acessórios.

---

## Parte 3 — Limitações do próprio diagnóstico

- O verificador (`verificar_relatorio.py`) confirma que cada número do texto existe em
  `numeros.json`, mas não que ele esteja no lugar certo. Números pequenos (2, 3, 15) casam
  com vários ids. A lista "número → id" em `verificacao_relatorio.md` serve para conferir à mão.
- Os rótulos de alvo em `d05` e `d06` são simulações para medir efeito. Não são a ABT, que
  depende das decisões da Semana 2.
- Não abrimos `docs/PROFESSOR.md` nem o gerador. Tudo o que dizemos sobre a "causa" das
  anomalias é inferência a partir do dado.
