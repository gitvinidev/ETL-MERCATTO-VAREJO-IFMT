# Notas para a defesa — Semanas 2 a 4

Material interno da equipe. Continua `relatorio/semana1/notas_para_defesa.md` (decisões D1 a D10),
cuja numeração segue aqui (D11 em diante). Para cada decisão: o que foi adotado, o que foi
descartado e por quê, e a pergunta mais provável. Os números estão em `docs/RDT.md`, na ficha
indicada, e saem de `saida/rdt/registros_afetados.json`. Este arquivo evita repeti-los.

**Estado:** Semanas 2 e 3 concluídas (decisões D11 a D41). A Semana 4 está em andamento (D42 em diante).

---

## Arquitetura do pipeline

### D11. Etapa 2 grava em `cnf`, não em `dw`
- **Adotada:** `02_transformacao.py` grava o esquema `cnf` (conformado); `03_carga_dw.py` carrega o
  esquema estrela a partir dele.
- **Descartada:** preencher `dw.dim_*` já na etapa 2. O esqueleto sugere isso num docstring e o
  contrário num TODO, e `carrega_dim_tempo` faz `TRUNCATE ... CASCADE`, o que apagaria dimensões e
  fatos carregados antes. Além disso, o DDL de `dw` está congelado (regra 3) e não tem colunas para
  `entrega_sem_data`, `frete_negativo`, `classe_mapeamento` etc.
- **Pergunta provável:** "Por que há um esquema que não está no roteiro?" Porque os indicadores
  exigidos pelas fichas não cabem no DDL entregue, e alterar o DDL é proibido.

### D12. Nomes de coluna da `stg` em minúsculas
- **Adotada:** espelham a origem, em minúsculas (`id_cliente`, não `"ID_CLIENTE"`).
- **Descartada:** manter a caixa alta do MySQL. Obrigaria a citar todos os nomes entre aspas no SQL
  sem ganho de informação. A caixa não carrega significado.

### D13. Metadado de procedência da `stg`
- **Adotada:** `_fonte`, `_extraido_em`, `_linha_origem` (ordem da chave primária nos bancos; número
  do registro no CSV; linha física no NDJSON). No NDJSON, também `_chaves_ausentes`,
  `_chaves_nulas` e `_tipos_json` (tipo original dos valores que não eram texto).
- **Motivo:** `rating` 5 e `"5"` ficam iguais como texto; a diferença de tipo é informação da fonte
  e entra em RDT-08. `_extraido_em` fica só na `stg`, para não quebrar o hash dos arquivos de `saida`.

---

## Cliente (RDT-02, RDT-03)

### D14. Chave de identidade: CPF de 11 dígitos, válido ou não, com guarda de nome
- **Adotada:** CPF válido + nome normalizado igual; CPF inválido + nome e UF iguais.
- **Descartada 1:** só CPF válido. Descarta pares em que o dígito errado é o mesmo nos dois
  cadastros e nome e UF concordam sempre. Para o SAC, o CPF inválido encontra cadastro na mesma
  taxa que o válido, o que confirma que o erro é estável.
- **Descartada 2:** CPF sem guarda de nome. Há CPFs repetidos com nomes diferentes (colisões), que
  fundiriam pessoas distintas.
- **Pergunta provável:** "E se o CPF inválido for só um erro de digitação aleatório?" Então não
  coincidiria entre dois cadastros com o mesmo nome e a mesma UF. A coincidência é total nos pares
  observados (RDT-02 a).

### D15. Sem pareamento por nome + UF (nem + cidade)
- **Adotada:** não usar.
- **Descartada:** nome + UF (ou + cidade) para quem não tem CPF utilizável. O teste de validação
  (entre registros com CPF válido dos dois lados, onde a verdade é conhecida) mostrou que nenhuma
  chave é única nos dois cadastros e que há uma fração de pares falsos. Sem chave única, a regra
  escolheria entre homônimos.
- **Custo assumido:** pessoas sem CPF utilizável ficam com o histórico dividido entre os sistemas.
- **Pergunta provável:** "Fundir por engano ou deixar duplicado: qual é pior?" Fundir: o rótulo
  passa a refletir o histórico de duas pessoas e uma delas some da campanha. O duplicado também
  erra o rótulo, mas é reversível. A resposta depende do uso, e para uma campanha de retenção
  escolhemos errar por não fundir.

### D16. Colisão de CPF
- **Adotada:** quando o mesmo CPF válido aparece em pessoas de nomes diferentes, nenhuma é fundida,
  e o CPF fica com o componente de mais registros; em empate, com nenhum.
- **Descartada:** manter o CPF em todas (violaria a unicidade da dimensão) ou fundir (misturaria
  pessoas).
- **Custo:** alguém pode perder um CPF que era seu. É um caso raro (RDT-02 d).

### D17. Duplicatas do legado: fundir, não descartar
- **Adotada:** um sobrevivente (CPF válido > mais completo > menor id) e a ponte guarda os dois ids.
- **Descartada:** descartar um registro (e os pedidos dele). Em quase todos os pares os dois
  registros têm pedidos; descartar apagaria vendas ou as reatribuiria sem rastro.
- **Pergunta provável:** "Por que não só apagar a duplicata?" Porque os dois têm histórico de
  compras, e a ABT precisa do histórico inteiro da pessoa.

---

## Status, valores, categorias (RDT-04 a RDT-07)

### D18. `CANCELADO` único com `motivo_cancelamento` (alternativa iii)
- **Adotada:** quatro status conformados; motivo `CANCELAMENTO` ou `PAGAMENTO_RECUSADO` no
  e-commerce; nulo no legado.
- **Descartadas:** (i) apagar a distinção; (ii) dois status, que criam uma categoria implícita "não sei".
- **Suposição declarada:** `SEPARACAO` = `processing` (pedido aceito, ainda não despachado).
  Alternativa descartada: tratar `SEPARACAO` como `EM_TRANSITO`; "separação" ocorre antes do
  despacho.
- **Nome do motivo:** `CANCELAMENTO` (e não `CLIENTE`) porque o e-commerce não informa quem
  cancelou. O esqueleto supunha "cancelamento pelo cliente"; o dado não diz isso.

### D19. Definição de compra para o alvo
- **Adotada:** todo status conformado diferente de `CANCELADO` conta como compra, inclusive
  `EM_PROCESSAMENTO`. É a mesma regra que o `SQL_ALVO` do esqueleto já usa (`<> 'CANCELADO'`).
- **Descartada 1:** só `ENTREGUE`. Deixa de fora o pedido feito perto do fim da janela, ainda não
  entregue no retrato. Depende do estado do pedido no dia do retrato, não do comportamento do cliente.
- **Descartada 2:** contar também cancelados. Um pedido recusado ou cancelado não é compra.
- **Risco:** um pedido em processamento que vire cancelado depois do retrato conta como compra.
- **Não mudar depois para melhorar resultado** (regra da tarefa).

### D20. `valor_total` com frete nos dois sistemas
- **Adotada:** mercadoria − desconto + frete (a definição do DDL).
- **Descartada:** `valor_total` sem frete. Casaria com `total_amount`, mas tiraria da ABT o que o
  cliente pagou e contrariaria o DDL.
- **Consequência registrada:** a referência de reconciliação do e-commerce na origem é
  `SUM(total_amount) + SUM(freight_amount)`. Comparar com `total_amount` cru dá diferença falsa.
- **`qtd_itens`:** soma das quantidades (unidades), não número de linhas. Alternativa: contar
  linhas; descartada porque "itens" no DDL é mais naturalmente unidades vendidas. Não afeta valores.

### D21. Frete negativo mantido, desconto `-1` virou 0
- **Adotada:** frete negativo preservado com indicador; `-1` → 0 com indicador.
- **Descartadas para o frete:** zerar, nulificar, separar como estorno. Qualquer delas quebraria a
  reconciliação contra a origem, que soma o frete negativo, e o significado não se decide pelo dado.
- **Pergunta provável:** "Por que não tratar frete negativo como erro?" Porque o total gravado pela
  origem o inclui, e não temos evidência de que seja erro (pode ser estorno ou subsídio).

### D22. Preços atípicos: mantidos
- **Critério:** razão alta contra a mediana da categoria *e* venda a preço compatível. Nenhum item
  foi vendido a 10 vezes o preço de tabela; os poucos produtos de preço alto são preços reais.
- **Descartada:** corrigir ou excluir. Nenhuma evidência de erro de digitação (a hipótese do
  esqueleto caiu).

### D23. Categorias: só o que o rótulo sustenta
- **Adotada:** direto → raiz e filho; nível → só a raiz; ambíguo e sem mapeamento → nulo.
- **Descartada 1:** atribuir tudo (ELETRO → Eletrodomésticos). Parece completo e inventa.
- **Descartada 2:** categoria sintética ("Informática/Games"). Não existe na taxonomia comum.
- **Custo:** `categorias_distintas` na ABT ignora os produtos sem nível 1.

### D24. Produtos dos dois sistemas não são unificados
- **Motivo:** o legado não tem SKU, e as coincidências de descrição são acidentais (nomes gerados
  com sufixo numérico). Unificar exigiria uma chave que não existe.

### D25. Mapeamento de canal
- **Adotada:** `LOJA`→`FISICO`, `TELEVENDAS`→`TELEVENDAS`, `SITE`/`web`/`app`→`ONLINE_PROPRIO`,
  `marketplace`→`MARKETPLACE` (as quatro classes que o DDL lista).
- **Ressalva (D4):** `SITE` no legado não se comporta temporalmente como `web`. Conformamos o rótulo,
  não afirmamos que o comportamento seja o mesmo.

---

## Ausências e tempo (RDT-08, RDT-09)

### D26. Entrega anterior ao pedido → `NULL` + indicador
- **Adotada:** `data_entrega` e `dias_entrega` nulos, `entrega_anterior_pedido` verdadeiro; a data do
  pedido fica.
- **Descartadas:** trocar as datas (palpite sobre qual está errada); usar o valor absoluto da
  diferença; manter a diferença negativa (a asserção do esqueleto proíbe `dias_entrega` negativo).
- **Por que a data do pedido fica:** a diferença é de dias inteiros (não de fuso), e a data do
  pedido ancora o corte da ABT.

### D27. Nota 0 do SAC → `NULL` + indicador
- **Descartadas:** manter 0 (derruba a média; a escala é de 1 a 5); recodificar para 1.
- **Pergunta provável:** "E se 0 for 'não respondeu'?" Então seria `NULL` do mesmo jeito; o
  indicador `nota_zero` preserva a possibilidade de investigar.

### D28. `data_fechamento` vazia no SAC → `NULL`, mas horas de resolução preservadas
- **Hipótese que caiu:** "atendimento em aberto". Todos os atendimentos sem data de fechamento têm
  tempo de resolução. É a data que se perdeu.
- **Descartada:** reconstruir a data (abertura + horas). É calculável, mas é imputar um valor derivado.

### D29. Régua de tempo: hora local de Brasília
- **Adotada:** America/Sao_Paulo; legado lido como está; e-commerce convertido de UTC; avaliações
  sem offset lidas como -03:00 (todos os offsets explícitos do arquivo são -03:00).
- **Descartada:** UTC. O efeito sobre o corte e o fim do alvo está em RDT-09 (e); é pequeno, mas
  altera o rótulo de um punhado de clientes. Mantém a D7 da Semana 1.

---

## Fontes de arquivo (RDT-13)

### D30. SAC liga ao cliente pelo CPF; nenhuma fonte de arquivo liga ao pedido
- **Adotada:** `cliente_key` do SAC por CPF; `pedido_key` nulo em SAC e avaliações. O pedido
  declarado fica em `cnf` como referência, não como ligação.
- **Desvio em relação ao enunciado da tarefa:** o texto diz que "SAC e NDJSON ligam ao cliente pelo
  CPF". O NDJSON **não tem campo de CPF** (só `order.ref` e `product.sku`); portanto as avaliações
  **não ligam a cliente algum**, só a produto (pelo SKU, `SKU-n` no e-commerce e `LEG-n` no legado).
  O relatório da Semana 1 já dizia que a ligação vale para o SAC. Consequência para a ABT: o atributo
  de avaliações por cliente fica indisponível, a menos que se aceite o pedido declarado, que não
  se sustenta (o produto avaliado está nos itens do pedido em quase nenhum caso, e metade das
  avaliações é anterior ao pedido).
- **Descartada:** ligar avaliações ao cliente via pedido declarado (`order.ref`). Produziria uma
  ligação que o dado desmente, e levaria atributos pós-corte para dentro da ABT.
- **SAC com CPF ambíguo** (o mesmo CPF em mais de uma pessoa): fica sem cliente, em vez de escolher.
- **SAC repetido:** as linhas repetidas são idênticas; mantém-se a primeira (menor `_linha_origem`),
  e uma asserção prova que a repetição é só de linhas idênticas.

---

## Gestão do trabalho

### D31. RDT gerado a partir de modelo
- **Adotada:** `docs/RDT.md` é gerado por `diagnostico/renderiza_rdt.py` a partir de
  `etl/rdt/RDT.template.md`; cada número é um marcador resolvido contra `registros_afetados.json`
  (ou `numeros.json`, com `s1:`). Se uma chave falta, a geração falha.
- **Descartada:** escrever o RDT à mão e conferir depois. A conferência mostra se o número existe,
  mas não se está no lugar certo.
- **Custo:** quem quiser alterar o texto edita o modelo e gera de novo.

### D32. Arquivo `notas_para_defesa.md` da Semana 1
- O commit `2d35296` removeu `relatorio/semana1/notas_para_defesa.md` e `diagnostico_semana1.md`
  da árvore de trabalho. Lemos o primeiro do histórico (`c50dbc2`) para partir das D1 a D10. Não o
  restauramos. **Atualização:** a equipe pediu a restauração, e o arquivo voltou à pasta como cópia idêntica à do
  commit `c50dbc2` (mesmo SHA-256). Assim, a referência do RDT às decisões D1 a D10 volta a apontar para um arquivo existente.

---

## Limitações do que foi feito até aqui

- O pareamento de pessoas sem CPF não existe; não há como medir quantas fusões estão erradas.
- As suposições de significado (`SEPARACAO` = `processing`; nota 0 fora da escala; `-1` = "sem
  desconto"; frete negativo = dado) são hipóteses sem teste direto.
- A transformação de cliente leva alguns minutos porque o laço por pessoa não é vetorizado; o
  resultado não depende disso.


---

# Semana 3

### D33. Chaves substitutas do DW = chaves determinísticas de `cnf`
- **Adotada:** `cliente_sk` e `produto_sk` são `cliente_key` e `produto_key` (ordenadas pelo menor id de
  origem); `pedido_sk` e `item_sk` por `ROW_NUMBER()` em ordem de sistema (legado primeiro) e identificador.
- **Descartada:** deixar o `BIGSERIAL` numerar na ordem do `INSERT`. Funciona, mas a ordem física não é garantida,
  e o teste do zero exige o mesmo resultado.

### D34. Tabelas `dw.aux_*` para rastro e indicadores
- **Adotada:** ponte de cliente, indicadores de pedido e item, quarentena de itens, referências declaradas de SAC e
  avaliação, em tabelas `dw.aux_*` criadas pelo script.
- **Descartada:** alterar o DDL de `dw` (proibido) ou descartar os indicadores (as fichas os exigem).

### D35. Sem cliente "DESCONHECIDO" (RDT-12)
- O esqueleto sugere o membro "DESCONHECIDO". Verificamos: nenhum pedido está sem cliente. Criar o membro seria
  uma linha de dimensão sem fatos. A carga falha por asserção se aparecer um órfão. **Hipótese do esqueleto
  que caiu.**
- **Pergunta provável:** "Por que não criaram o cliente desconhecido?" Porque não há pedido que precise dele, e
  um membro sem uso aparece em contagens de clientes. O perigo real era a colisão de identificadores entre sistemas,
  tratada pela chave (sistema, id).

### D36. Itens órfãos em quarentena (RDT-10)
- **Descartadas:** pedido sintético (inventa cliente, data e status) e descartar sem registro.
- **Hipótese não demonstrada:** que os pedidos desses itens existam fora do retrato.

### D37. Reconciliação financeira com a fórmula comum
- A referência do e-commerce é `SUM(total_amount + freight_amount)`, calculada na origem. A diferença é **exatamente
  zero** nos dois sistemas. `financeira_detalhe.csv` mostra, para o e-commerce, quanto seria a diferença falsa contra
  o `total_amount` cru, e é por isso que a fórmula comum precisava ser a mesma dos dois lados.
- **Pergunta provável:** "Zero é suspeito?" Não: o DW soma os mesmos itens com a mesma fórmula que o ERP (legado) e
  o `total_amount + frete` (e-commerce), e a Semana 1 já tinha mostrado resíduo nulo. Zero é o esperado; qualquer
  junção que multiplicasse linhas, ou item órfão no fato, tiraria o resultado do zero.

### D38. População da ABT
- **Adotada:** clientes unificados com ao menos um pedido, de qualquer status, até o corte (a base do `SQL_ALVO`
  do esqueleto). Inclui clientes que só têm pedidos cancelados antes do corte (atributos "efetivos" nulos).
- **Descartada:** só clientes com pelo menos um pedido efetivo. Tira da população quem pode ser o alvo de uma
  campanha de retenção, e o rótulo do alvo muda com a escolha, o que seria ajustar a população para mexer na taxa.
- **A decisão não foi trocada depois de ver a taxa de positivos** (regra da tarefa).

### D39. Atributo de entrega só com entregas até o corte
- Há pedidos anteriores ao corte entregues depois dele. Usar `dias_entrega` desses pedidos é vazamento por
  data de entrega. O filtro `data_entrega <= corte` evita isso, e a cópia "no corte" do DW zera as entregas
  posteriores para provar.

### D40. Limitação do status do retrato
- O status é o do dia do retrato. Um pedido cancelado depois do corte entra na ABT como cancelado. Não é possível
  corrigir sem a data do cancelamento. Declarado no RDT-14 (Semana 4), com o número de pedidos expostos.
- **Descartada:** remover `taxa_cancelamento` e usar todos os pedidos como "frequência". Trocaria um viés conhecido
  por uma frequência que conta vendas que não ocorreram.

### D41. Dump do DW
- **Adotado:** `pg_dump --schema=dw --schema=abt --schema=qa`, em `entregas/dw_semana3.sql.gz` (comprimido com `gzip -9`; o conteúdo descomprimido tem o mesmo SHA-256 do `.sql` original, que foi removido).
- **Descartado:** o dump completo do banco, que inclui a `stg` (cópia das origens): o arquivo passa de 650 MB e
  repete o que as origens já têm. O dump restrito ainda é grande; ver o aviso em `PROGRESSO.md`.


---

# Semana 4

### D42. Quais vazamentos, e por quê
- **Adotados:** (1) `recencia_dias` e (2) `frequencia_pedidos` sem o filtro de data; (3) `valor_monetario` padronizado com
  média e desvio de todas as linhas.
- **Motivo:** (1) e (2) são o erro mais comum (agregado sem cláusula de data), plausível num pipeline real. (3) é o erro de
  pré-processamento mais comum.
- **Descartados:** "pedidos nos 90 dias seguintes" como atributo (óbvio demais, ninguém o faria por engano) e vazamento via
  status ou data de entrega pós-corte (existe, mas é fraco e indireto).
- **Pergunta provável:** "O vazamento é realista?" Sim: basta um `WHERE` esquecido. Todos os positivos ficam com
  recência negativa; é um sinal grande demais para ser acaso.
- **Observação:** a recência negativa também alcança quem comprou *depois* da janela do alvo (29/09 em diante), que não é
  positivo. A regra "recência negativa" prevê o alvo com precisão perfeita só em recall, não em precisão.

### D43. Normalização
- **Adotada:** z-score de `valor_monetario`, desvio populacional (`ddof=0`), arredondado a 6 casas. A coluna se chama
  `valor_monetario_z` e substitui `valor_monetario` (na correta ela segue sem normalizar). A média e o desvio ficam em
  `saida/abt/normalizacao_global_*.csv`.
- **Descartadas:** normalizar todos os atributos (deixaria o vazamento sutil mais forte do que o "uma normalização" pedida);
  min-max (equivalente em espírito).
- **Expectativa honesta:** a normalização é linear; para a árvore o efeito deve ser nulo e para os outros dois, pequeno.
  Se o resultado for diferença nula, é isso que o relatório diz.

### D44. Como responder à pergunta (b) sem confundir escala com vazamento
- A versão `--vazamento-sutil` difere da correta em duas coisas: a escala de `valor_monetario` e o fato de a média/desvio
  virem de todas as linhas. Para isolar o segundo, o experimento em Python terá um **controle**: a versão correta com o
  z-score ajustado **só no treino** (e aplicado ao teste). A diferença sutil-contra-controle é o vazamento puro;
  sutil-contra-correta mistura escala e vazamento. O controle não vai ao Orange.

### D45. Acurácia balanceada
- O Test & Score do Orange não traz acurácia balanceada. Definição adotada: `(recall + especificidade) / 2`, classe-alvo 1,
  limiar padrão do Orange. O experimento em Python usa a mesma definição. Alternativa descartada: usar `CA` (acurácia
  simples), que com 22% de positivos premia o modelo que prevê sempre "não".

### D46. Versão sutil fora do Orange; versão correta e com vazamento com o mesmo fluxo
- Regra do roteiro (Orange só com as duas versões). A sutil só entra no Python.

### D47. Partição do Orange exportada (recomendado)
- O Orange não deixa escolher a semente em todas as versões. Para o Python usar a mesma partição, o guia pede que a equipe
  exporte treino e teste do fluxo correto (`Save Data`). A partição do fluxo com vazamento é a mesma porque classe e ordem
  das linhas são iguais.

### D48. O agente não gera `.ows` nem preenche métricas do Orange
- Regra da tarefa. O guia está em `relatorio/semana4/GUIA_ORANGE.md`.

### D49. Dependência nova: scikit-learn
- **Adotada:** `scikit-learn==1.5.2` e `scipy==1.14.1` em `etl/requirements.txt`, contêiner `etl` reconstruído (regra 7 do
  `CLAUDE.md`). Nada é instalado no host.
- **Motivo:** Naive Bayes, regressão logística, árvore e AUC no experimento em Python (checagem do Orange e pergunta (b)).
  Implementar os três modelos à mão seria pior do que declarar a dependência.
- **A registrar no relatório de resultados:** a dependência e a versão.

### D50. Como o experimento em Python espelha o Orange (4.4)
- **Adotada:** mesma partição do Orange (`particao_orange_*.csv`, por `cliente_sk`, com hash em `saida/experimento/numeros.json`)
  e os padrões do Orange 3.40.0 lidos no código instalado: regressão logística L2, C=1, `lbfgs`, 100 iterações, sem
  normalização, com indicadores para a categórica e imputação pela média; Naive Bayes com 4 faixas de mesma frequência e a
  suavização de Laplace do Orange (reimplementado); árvore com entropia, mínimo de 5 para dividir e de 2 por folha, profundidade
  100. Scripts: `etl/diagnostico/experimento_python.py` e `experimento_sensibilidade.py`.
- **Descartada:** usar o pacote `Orange` dentro do contêiner (nova dependência pesada) ou rodá-lo no host (a regra 7 manda
  rodar Python no contêiner). O custo: o Python não reproduz o Orange ao centésimo, e isso é declarado no relatório.
- **Divergências conhecidas (não são erros):** (i) a árvore do Orange é binária, usa razão de ganho e para por maioria de
  95 %; o scikit-learn não tem esse critério de parada. (ii) o Orange usa scikit-learn 1.9.1 e o contêiner, 1.5.2; a
  regressão logística sem normalização não converge em 100 iterações no contêiner. Que a versão seja a causa é hipótese,
  não verificada (exigiria rodar o Orange). (iii) os cortes do Naive Bayes são aproximados.
- **O que sustenta a comparação:** a solução convergida da regressão logística reproduz a AUC do Orange
  (`saida/experimento/sensibilidade.csv`).

### D51. Linha extra "Logistic Regression (padronizada)"
- **Adotada:** acrescentar, só no Python, a regressão logística com atributos padronizados no treino, que converge em todas as
  versões. Serve para a pergunta (b): sem ela, a diferença entre a versão sutil e a correta mistura vazamento com falta de
  convergência (o `sensibilidade.csv` mostra que a diferença some quando a otimização converge).
- **Descartada:** trocar a regressão logística principal por essa variante. Perderia a comparação direta com o Orange.
- **Alternativa descartada também:** aumentar `max_iter` sem padronizar; na versão correta ela não converge nem com 10.000
  iterações.

### D52. Saídas do experimento em `saida/experimento/`
- A pasta foi criada pelo contêiner (a `saida/` pertence ao root; sem `sudo`, regra 11) e liberada para escrita. As cópias
  da partição e das métricas do Orange ficam ali porque o contêiner não enxerga `relatorio/`; os hashes das cópias e dos
  originais são iguais.

### D53. Alcance do teste do zero (F.1)
- **Adotado (decisão da equipe, sobre proposta do agente):** apagar só o destino: os 5 esquemas do `mercatto_dw` e os arquivos gerados em
  `saida/`, reaplicar o DDL de `sql/postgres-dw/` e rodar os seis comandos (mais `--vazamento-sutil` e o experimento em Python), comparando
  impressões digitais (`diagnostico/f1_hashes.py`).
- **Descartado:** `docker compose down -v` + `up` (refaz também as origens). É o que o roteiro diz literalmente, mas, se o seed falhasse (por
  exemplo, sem internet para construir a imagem do gerador), as origens ficariam perdidas até o seed funcionar. O custo da escolha: não
  provamos que o seed reproduz as origens; só que, dadas as origens, o pipeline reproduz o resultado.
- **A `stg` não é idêntica byte a byte:** guarda `_extraido_em`, a hora da extração. Provamos que é a única diferença rodando a extração duas
  vezes e comparando as tabelas com e sem essa coluna (`f1_comparacao_stg_a_stg_b.csv`).
- **Medida do teste:** a impressão digital de uma tabela é o número de linhas mais a soma de `hashtextextended(linha::text)`; não depende da
  ordem das linhas, mas depende de todos os valores, inclusive das chaves substitutas.
