# ETL Mercatto Varejo

Projeto prático da disciplina de **Mineração de Dados** (IFMT, 2026/2, Prof. Orlando Júnior).
Equipe: Gabriel Lemos Gomes, Lucas Peres de Lima e Marcus Vinícius Santos de Almeida.

O projeto integra quatro fontes heterogêneas de uma rede de varejo (ERP legado em MySQL, e-commerce em PostgreSQL, atendimentos
do SAC em CSV e avaliações de marketplace em NDJSON) num repositório analítico, e usa esse repositório para responder a uma
pergunta preditiva: **o cliente que comprou até 30/06/2025 recompra entre 01/07/2025 e 28/09/2025?** O experimento central mede o efeito
do **vazamento de dados** sobre os resultados de três modelos treinados no Orange.

O código está em `ETL/`. Este arquivo é o mapa do repositório; o enunciado e o referencial teórico (`Projeto_Pratico_ETL_Mercatto-1.pdf` e
`ETL.pdf`) ficam em `referencias/`, junto com o enunciado da tarefa da Semana 1 (`TAREFA_SEMANA1.md`) e a árvore inicial do projeto (`arvore.txt`). Essa pasta e o `CLAUDE.md` estão no `.gitignore` (são material local, não vão para o repositório remoto).

## 1. Requisitos e ambiente

- Docker e Docker Compose v2; 8 GB de RAM recomendados; cerca de 2 GB livres em disco.
- [Orange Data Mining](https://orangedatamining.com/) instalado no computador (não roda em contêiner). Usamos a versão 3.40.0.
- Todo o Python roda dentro do contêiner `etl`. Nada é instalado no computador, e dependências novas entram em
  `ETL/etl/requirements.txt` (nesta entrega, `scikit-learn` e `scipy`, usados só no experimento em Python).

```bash
cd ETL
echo 'ESCALA=1.0' > .env              # volume dos dados; 1.0 é a escala usada na entrega
docker compose up -d --build
docker compose logs -f seed           # espere "ambiente pronto." (alguns minutos)
```

As origens (`mysql_legado` e `pg_ecommerce`) são **somente leitura** para o ETL, de propósito. O destino é o `pg_dw` (banco
`mercatto_dw`). Os arquivos do SAC e das avaliações ficam em `ETL/dados/`, e as saídas, em `ETL/saida/`.

## 2. O pipeline

Executar **a partir de `ETL/`**, nesta ordem:

```bash
docker compose exec etl python 01_extracao.py                 # origens -> esquema stg (cópia fiel, carga completa)
docker compose exec etl python 02_transformacao.py            # stg -> esquema cnf (camada conformada, ~8 min)
docker compose exec etl python 03_carga_dw.py                 # cnf -> dw (estrela) + reconciliação financeira
docker compose exec etl python 04_abt.py --correta            # abt.recompra_90d
docker compose exec etl python 04_abt.py --vazamento          # abt.recompra_90d_vazamento
docker compose exec etl python 05_exportar_orange.py          # saida/abt_recompra_{correta,vazamento}.csv
```

Passos adicionais:

```bash
docker compose exec etl python 04_abt.py --vazamento-sutil    # só a normalização antes da partição (não vai ao Orange)
docker compose exec etl python -m diagnostico.experimento_python        # experimento em Python (~20 s)
docker compose exec etl python -m diagnostico.experimento_sensibilidade  # por que o Python não coincide com o Orange (~5 min)
```

Cada etapa grava suas **asserções** em `qa.execucao_assercao` e as imprime no fim. Uma asserção que falha fica registrada e marcada `FALHA`, mas não interrompe a etapa; a exceção é a reconciliação financeira da etapa 3, que aborta se a diferença passar de 0,1%.

| Etapa | O que faz | Onde ficam as decisões |
|---|---|---|
| `01_extracao` | Copia as quatro fontes para `stg`, sem filtro, e confere cada contagem com a origem | RDT-01 |
| `02_transformacao` | Unifica clientes, conforma status, valores, datas e ausências; liga SAC e avaliações | RDT-02 a RDT-09 |
| `03_carga_dw` | Carrega o esquema estrela, põe itens órfãos em quarentena e reconcilia valores | RDT-10 a RDT-13 |
| `04_abt` | Monta a tabela-base (ABT) correta e as versões com vazamento | RDT-14 e RDT-15 |
| `05_exportar_orange` | Exporta as ABT com o cabeçalho de 3 linhas do Orange | |

Datas analíticas: corte em 30/06/2025; janela do alvo de 01/07/2025 a 28/09/2025 (`ETL/etl/config.py`).

## 3. Entregáveis

| # | Entregável | Onde |
|---|---|---|
| 1 | Diagnóstico das quatro fontes (Semana 1) | `ETL/relatorio/semana1/diagnostico_semana1.pdf`; scripts em `ETL/etl/diagnostico/d0*.py` |
| 2 | RDT parcial e etapas 1 e 2 | `ETL/docs/RDT.md` (fichas 01 a 09); `ETL/etl/01_extracao.py`, `02_transformacao.py` |
| 3 | DW carregado, asserções, fichas 10 a 13 | `ETL/etl/03_carga_dw.py`; dump em `ETL/entregas/dw_semana3.sql.gz` (esquemas `dw`, `abt` e `qa` da Semana 3; restaurar com `gunzip -c ETL/entregas/dw_semana3.sql.gz | docker compose exec -T pg_dw psql -U postgres -d mercatto_dw`, depois de limpar esses esquemas) |
| 4 | RDT integral com tabela-resumo e reflexão | `ETL/docs/RDT.md` (fichas 01 a 15) |
| 5 | Pipeline reexecutável do zero | Seção 2 e seção 5 |
| 6 | Fluxos do Orange das duas versões | `ETL/relatorio/semana4/fluxo_correta.ows`, `fluxo_vazamento.ows` e `capturas/` |
| 7 | Relatório de resultados do experimento | `ETL/relatorio/semana4/resultados_experimento.md` |
| 8 | Defesa oral | `ETL/relatorio/semana1/notas_para_defesa.md` (D1 a D10) e `ETL/relatorio/notas_para_defesa_semanas_2_4.md` (D11 a D53): decisões e alternativas descartadas |

**Guia de estudo para a defesa:** `ETL/docs/DOCUMENTACAO.md` (por semana: o que foi feito, como executar, resultados, interpretação e perguntas prováveis).

Outros arquivos úteis: `ETL/docs/DICIONARIO_ABT.md` (atributos da ABT), `ETL/relatorio/PROGRESSO.md` (histórico por semana) e
`ETL/relatorio/semana4/GUIA_ORANGE.md` (como montar os fluxos).

## 4. O experimento de vazamento

- **Versão correta:** todo atributo é calculado só com dados até 30/06/2025.
- **Com vazamento:** `recencia_dias` e `frequencia_pedidos` calculados sobre a base inteira, e `valor_monetario` padronizado (z-score) antes
  da partição treino/teste.
- **Vazamento sutil:** só a padronização antes da partição, avaliada em Python.
- No Orange, os dois fluxos são idênticos (amostragem estratificada 70/30, Naive Bayes, Logistic Regression e Tree em Test & Score,
  Confusion Matrix e ROC Analysis); muda apenas o arquivo de entrada. As métricas do Orange estão em
  `ETL/relatorio/semana4/metricas_orange.csv`, e a partição exportada, em `particao_orange_*.csv`.
- O experimento em Python usa a **mesma partição** e grava as métricas em `ETL/saida/experimento/`.

## 5. Verificação

Todo número citado nos relatórios vem de um script versionado em `ETL/etl/diagnostico/` e de um arquivo em `ETL/saida/`.

```bash
# números do relatório da Semana 1 contra saida/diagnostico/numeros.json (o texto em Markdown está no histórico do git, commit c50dbc2)
git show c50dbc2:ETL/relatorio/semana1/diagnostico_semana1.md | docker compose exec -T etl python -m diagnostico.verificar_relatorio
# números do relatório de resultados contra saida/experimento/
docker compose exec -T etl python -m diagnostico.verificar_resultados < relatorio/semana4/resultados_experimento.md
# números da documentação (docs/DOCUMENTACAO.md) contra todos os arquivos de saida/
docker compose exec -T etl python -m diagnostico.verificar_documentacao < docs/DOCUMENTACAO.md
# figuras do guia (SVG em docs/figuras/), geradas dos arquivos de saida/
docker compose exec etl python -m diagnostico.gera_figuras
mkdir -p docs/figuras && cp saida/figuras/*.svg docs/figuras/
# RDT: gerado do modelo etl/rdt/RDT.template.md; a geração falha se um número não existir
docker compose exec etl python -m diagnostico.rdt_registros_afetados
docker compose exec etl python -m diagnostico.renderiza_rdt && cp saida/rdt/RDT.md docs/RDT.md
```

**Teste do zero (F.1).** O script `diagnostico/f1_hashes.py` grava uma impressão digital (SHA-256 dos arquivos gerados e, por tabela, o
número de linhas e a soma de hashes das linhas) antes e depois de apagar o destino e rodar o pipeline de novo; `comparar` compara os dois.

**Resultado do teste do zero.** Apagamos o destino (os 5 esquemas do `mercatto_dw` e os arquivos gerados em `ETL/saida/`), reaplicamos o DDL
de `ETL/sql/postgres-dw/` e rodamos os seis comandos do pipeline, mais `--vazamento-sutil` e o experimento em Python. Todas as etapas terminaram
sem falha de asserção. As origens e `ETL/dados/` não foram tocadas.

- **Idênticos:** os 15 arquivos gerados, todas as tabelas de `cnf`, `dw` e `abt` (linhas e soma de hashes das linhas, inclusive as chaves
  substitutas) e as 137 asserções registradas (`ETL/saida/diagnostico/f1_comparacao.csv`).
- **Diferentes:** as 11 tabelas da `stg` que têm a coluna `_extraido_em` (hora da extração, que muda por construção). Uma segunda extração
  seguida mostrou que, sem essa coluna, as 13 tabelas da `stg` são idênticas (`f1_comparacao_stg_a_stg_b.csv`).
- **Limite:** não derrubamos os volumes das origens nem refizemos o seed; elas foram tomadas como dadas (o gerador tem semente fixa).
  O registro de cada etapa está em `ETL/saida/diagnostico/f1_execucao.log`.

## 6. Regras de trabalho da equipe

- As origens são somente leitura; nunca se escreve em `mysql_legado` nem em `pg_ecommerce`.
- A Semana 1 descreve, não transforma. A partir da Semana 2, a implementação segue as tarefas de cada semana.
- Hipóteses não são conclusões: o relatório diz o que o dado mostrou, inclusive quando a hipótese cai.
- Decisões interpretativas ficam no RDT e, com as alternativas descartadas, nas notas de defesa (`ETL/relatorio/semana1/` e `ETL/relatorio/notas_para_defesa_semanas_2_4.md`).
- Os arquivos `.ows` do Orange guardam o caminho absoluto do CSV de entrada (do computador onde foram montados). Em outro computador, o Orange pede para religar o widget File a `ETL/saida/abt_recompra_correta.csv` (ou `..._vazamento.csv`).
