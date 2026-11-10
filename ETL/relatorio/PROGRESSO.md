# Progresso do projeto

Cada sessão começa lendo este arquivo. Uma semana por sessão.

## Estado atual

| Semana | Estado |
|---|---|
| 1 · Perfilar | Concluída (entregue em `relatorio/semana1/diagnostico_semana1.pdf`) |
| 2 · Extrair e conformar | Concluída |
| 3 · Carregar e verificar | Concluída |
| 4 · Modelar, comparar e defender | Concluída (4.3 a 4.6 e fase final); restam só o commit e a entrega pela equipe (ver abaixo) |

**Feito depois da parada 4.3:** os fluxos, capturas, partição e `metricas_orange.csv` foram entregues pela equipe (Orange 3.40.0).
4.4: `etl/diagnostico/experimento_python.py` e `experimento_sensibilidade.py` → `saida/experimento/`. 4.5:
`relatorio/semana4/resultados_experimento.md`. 4.6: tabela-resumo final e reflexão (328 palavras) em `etl/rdt/RDT.template.md`,
renderizados para `docs/RDT.md`. Decisões D50 a D52 (e D53, da fase final) em `relatorio/notas_para_defesa_semanas_2_4.md`.
**Fase final (feita):** F.1 teste do zero (destino apagado e reconstruído; `saida/diagnostico/f1_*.csv`, resultado no `README.md`; decisão D53);
F.2 `README.md` da raiz; F.3 `etl/diagnostico/verificar_resultados.py` (saída em `saida/diagnostico/verificacao_resultados.md`); F.4 `git status`
entregue à equipe (nenhum commit feito).

**Documentação de estudo:** `docs/DOCUMENTACAO.md` (por semana: feito, como executar, resultados, interpretação, perguntas da defesa), verificada por
`etl/diagnostico/verificar_documentacao.py` (saída em `saida/diagnostico/verificacao_documentacao.md`).

**Figuras do guia:** 7 ilustrações em `docs/figuras/` (SVG), geradas por `etl/diagnostico/gera_figuras.py` a partir dos arquivos de `saida/`; `docs/DOCUMENTACAO.pdf` as inclui.

**Parada 4.6 cumprida:** a equipe conferiu as fichas do RDT e confirmou que sabe defender as decisões; o estado do RDT foi atualizado.
**Falta (equipe):** (1) decidir se `entregas/dw_semana3.sql.gz` vai no repositório (cerca de 56 MB; o GitHub avisa acima de 50 MB, mas aceita
até 100 MB) ou por outro meio; o `.sql` original de 185 MB foi comprimido e removido, com hash do conteúdo idêntico; (2) fazer o commit.
Os PDFs (`docs/RDT.pdf` e `relatorio/semana4/resultados_experimento.pdf`) foram gerados a partir dos `.md`; se o texto mudar, é preciso gerá-los de novo.

## Semana 4 — o que foi feito até a parada 4.3 (histórico; as paradas 4.3 e 4.6 já foram cumpridas)

```bash
docker compose exec etl python 04_abt.py --correta --vazamento --vazamento-sutil
docker compose exec etl python 05_exportar_orange.py     # abt_recompra_correta.csv e abt_recompra_vazamento.csv
```

- `04_abt.py`: `--vazamento` (recência e frequência sem filtro de data + z-score global de `valor_monetario`) e
  `--vazamento-sutil` (só o z-score global, não vai ao Orange). Asserções: `04_abt_vazamento` 11, `04_abt_vazamento_sutil` 9,
  todas aprovadas; as marcadas "(intencional)" confirmam que o vazamento existe.
- `05_exportar_orange.py` (não alterado) gera os dois CSVs em `saida/` com o cabeçalho de três linhas do Orange.
- `relatorio/semana4/GUIA_ORANGE.md`: passo a passo para a equipe.
- `docs/RDT.md`: fichas RDT-01 a RDT-15 redigidas (14 e 15 novas). A tabela-resumo final e a reflexão foram feitas depois (ver o início deste arquivo).
- `relatorio/notas_para_defesa_semanas_2_4.md`: D42 a D48.

**PARADA OBRIGATÓRIA (4.3), já cumprida.** A equipe precisou entregar, em `relatorio/semana4/`: `fluxo_correta.ows`,
`fluxo_vazamento.ows`, `capturas/` e `metricas_orange.csv` (formato no guia, item 4); de preferência também
`particao_orange_treino.csv` e `particao_orange_teste.csv`. Só depois disso:

1. **4.4 Experimento em Python.** `scikit-learn==1.5.2` e `scipy==1.14.1` foram acrescentados a `etl/requirements.txt` e o
   contêiner `etl` foi reconstruído (regra 7; **registrar no relatório de resultados**). A primeira tentativa falhou por falta
   de internet; a segunda construiu a imagem. Dados e bancos não foram afetados. Três modelos, três versões
   (correta, vazamento, vazamento-sutil) mais o controle "correta com z-score só no treino" (D44), mesma partição 70/30
   estratificada com semente fixa (ou a do Orange, se exportada). Saída: `saida/experimento/metricas_python.csv` e
   `numeros.json`. Comparar com `metricas_orange.csv`; se a diferença for grande, investigar antes de escrever.
2. **4.5** `relatorio/semana4/resultados_experimento.md` (máx. 4 páginas; perguntas a, b, c).
3. **4.6** Tabela-resumo final e reflexão (máx. 400 palavras) no RDT. **PARADA OBRIGATÓRIA:** a equipe confere ao menos
   duas fichas e confirma que sabe defender cada decisão.
4. **Fase final:** teste do zero com hashes (F.1), README (F.2), verificador de números (F.3), `git status` (F.4).

## Semana 3 — o que foi feito

```bash
docker compose exec etl python 03_carga_dw.py          # dw + dw.aux_* + reconciliação (~40 s)
docker compose exec etl python 04_abt.py --correta     # abt.recompra_90d (~40 s)
docker compose exec etl python -m diagnostico.rdt_registros_afetados
docker compose exec etl python -m diagnostico.renderiza_rdt && cp saida/rdt/RDT.md docs/RDT.md
docker compose exec -T pg_dw pg_dump -U postgres --schema=dw --schema=abt --schema=qa mercatto_dw | gzip -9 > entregas/dw_semana3.sql.gz
```

- `03_carga_dw.py`: 27 asserções, 0 falhas. `fato_pedido` 410.000 linhas, `fato_item_pedido` 1.371.876, 20.577 itens em
  quarentena, `fato_atendimento` 95.000, `fato_avaliacao` 160.000. Nenhuma FK órfã.
- **Reconciliação financeira** (`saida/reconciliacao/financeira.csv`): diferença **zero** nos dois sistemas (mesma
  fórmula dos dois lados; ver RDT-05 e RDT-11). `financeira_detalhe.csv` mostra a diferença falsa que haveria contra o
  `total_amount` cru do e-commerce.
- `04_abt.py --correta`: 12 asserções, 0 falhas; 109.499 clientes, taxa de positivos 21,96%. Nenhum atributo usa dado
  posterior ao corte (teste com o DW "como estava em 30/06/2025", `dicionario_atributos.csv`, `docs/DICIONARIO_ABT.md`).
- `docs/RDT.md`: fichas RDT-01 a RDT-13.
- Reexecutar 03 e 04 reproduz tabelas e arquivos idênticos (comparação de hash).
- `entregas/dw_semana3.sql.gz`: dump de `dw`, `abt` e `qa` (**185 MB** sem comprimir, cerca de 56 MB comprimido; o dump completo, com a `stg`, passaria de 650 MB).

**Atenção (resolvido em parte):** o `.sql` tinha 185 MB, acima dos 100 MB por arquivo do GitHub. Foi comprimido (`.gz`, cerca de 56 MB) e o
original removido. Acima de 50 MB o GitHub avisa, mas aceita. Não alteramos o `.gitignore`. A equipe decide se o dump vai no repositório ou por outro meio.

**Pontos que dependem da equipe (Semana 3):**

1. A população da ABT inclui clientes que só têm pedidos cancelados até o corte (D38); os atributos "efetivos" deles
   ficam nulos.
2. O status do pedido é o do retrato dos dados (D40): é uma limitação da ABT, não um erro corrigível.
3. (Registro da Semana 3; o `--vazamento` foi implementado na Semana 4.) Naquele momento o `--vazamento` ainda não existia no `04_abt.py`; `05_exportar_orange.py` já exporta a versão correta
   como `saida/abt_recompra_correta.csv` (nome do exportador, não `abt_correta.csv`).

## Semana 2 — o que foi feito

**Código** (rodar a partir de `ETL/ETL`, dentro do contêiner `etl`):

```bash
docker compose exec etl python 01_extracao.py                       # stg: 2.205.864 registros
docker compose exec etl python 02_transformacao.py                  # cnf: camada conformada (471 s no teste do zero)
docker compose exec etl python -m diagnostico.e01_conferencia_stg   # stg x d01_volumes.csv
docker compose exec etl python -m diagnostico.rdt_registros_afetados
docker compose exec etl python -m diagnostico.renderiza_rdt
cp saida/rdt/RDT.md docs/RDT.md                                      # no host, a partir de ETL/ETL
```

**Resultados**

- `01_extracao.py`: carga completa, sem `LIMIT`. 32 asserções, 0 falhas. Contagem da `stg` igual à
  do diagnóstico da Semana 1 em todas as 11 tabelas (`saida/diagnostico/e01_stg_vs_d01.csv`).
- `02_transformacao.py`: 46 asserções, 0 falhas. Grava o esquema `cnf` (cliente, ponte, produto,
  item, pedido, atendimento, avaliação, mapas de status e canal).
- `docs/RDT.md`: fichas RDT-01 a RDT-09 com as seis partes, geradas do modelo
  `etl/rdt/RDT.template.md`; números em `saida/rdt/registros_afetados.json`.
- `relatorio/notas_para_defesa_semanas_2_4.md`: decisões D11 a D32 com alternativas descartadas.

**Arquivos novos:** `etl/diagnostico/e01_conferencia_stg.py`,
`etl/diagnostico/rdt_registros_afetados.py`, `etl/diagnostico/renderiza_rdt.py`,
`etl/rdt/RDT.template.md`, `docs/RDT.md`, `relatorio/notas_para_defesa_semanas_2_4.md`,
`relatorio/PROGRESSO.md`. **Alterados:** `etl/01_extracao.py`, `etl/02_transformacao.py`.
Nenhum arquivo protegido (regra 3) foi modificado. Nenhum commit foi feito.

## Pontos que dependem da equipe

1. **`notas_para_defesa.md` da Semana 1** tinha sido apagado no commit `2d35296` (junto com
   `diagnostico_semana1.md`). **Restaurado** a pedido da equipe, como cópia idêntica à do commit `c50dbc2`. O
   `diagnostico_semana1.md` continua só no histórico (o PDF é o entregável); para o verificador da Semana 1, use `git show c50dbc2:...`.
2. **Desvio em relação ao texto da tarefa (D30):** o NDJSON de avaliações não tem CPF, então as
   avaliações **não** ligam a cliente (só a produto, pelo SKU). Só o SAC liga ao cliente pelo CPF. Isso
   tira da ABT o atributo `nota_media_avaliacoes` por cliente, salvo decisão em contrário.
3. **Cumprido (conferir ao menos duas fichas):** a equipe conferiu as fichas e confirmou que sabe defendê-las.
4. O verificador da Semana 1 lê o relatório pela **entrada padrão**; rodá-lo sem entrada zera
   `saida/diagnostico/verificacao_relatorio.md`. Isso aconteceu uma vez nesta sessão, e o arquivo foi
   regenerado a partir da versão do relatório que está no histórico do git.

## Observações para a Semana 3

- (feito na Semana 3) **Reconciliação financeira:** a referência do e-commerce na origem é `SUM(total_amount) +
  SUM(freight_amount)`, não `SUM(total_amount)` (RDT-05). A referência do legado é `SUM(VALOR_TOTAL)`.
- **Itens órfãos** ficam em `cnf.item` com `pedido_existe = false`; não entram em `dw.fato_item_pedido`
  (RDT-10). Pedidos sem cliente: zero (RDT-12).
- **Alvo:** `status_conformado <> 'CANCELADO'` conta como compra (RDT-04). O `SQL_ALVO` do esqueleto
  já usa essa regra. A população da ABT são os clientes com ao menos um pedido até 30/06/2025.
- `grava()` em `04_abt.py` usa `if_exists="replace"`, que descarta chaves e tipos do contrato da
  tabela; trocar por `TRUNCATE` + `append`.
- `carrega_dim_tempo` faz `TRUNCATE ... CASCADE`: rodar antes das demais cargas, e limpar o `dw` por
  completo para a carga ser idempotente.
- Chaves substitutas: `cnf.cliente.cliente_key` e `cnf.produto.produto_key` são determinísticas
  (ordenadas pelo menor id de origem); usá-las como `cliente_sk` e `produto_sk`.
- Um dump completo do DW inclui a `stg` (2,2 milhões de linhas); decidir se o arquivo
  `entregas/dw_semana3.sql.gz` terá só `dw`, `qa` e `abt` (decidido: só esses três), ou se entra no `.gitignore`.
- A etapa 2 leva alguns minutos (laço por pessoa em `unifica_clientes`); considerar vetorizar antes do
  teste do zero (F.1).
