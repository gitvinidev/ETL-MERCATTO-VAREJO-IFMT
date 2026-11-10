# Guia para montar os fluxos no Orange

O agente **não gera os arquivos `.ows`** (formato XML frágil; o Orange pode recusá-lo). Este guia é o passo a passo
para a equipe. O que a equipe entrega ao final:

| Entregável | Onde |
|---|---|
| Fluxo da versão correta | `relatorio/semana4/fluxo_correta.ows` |
| Fluxo da versão com vazamento | `relatorio/semana4/fluxo_vazamento.ows` |
| Capturas de tela dos fluxos e dos resultados | `relatorio/semana4/capturas/` |
| Métricas do Test & Score | `relatorio/semana4/metricas_orange.csv` |
| (recomendado) partição treino/teste exportada | `relatorio/semana4/particao_orange_treino.csv` e `particao_orange_teste.csv` |

**Regra do experimento:** a única diferença entre os dois fluxos é o arquivo de entrada. Mesmos widgets, mesmas
ligações, mesmos parâmetros, mesma semente. Não ajustem nada num fluxo e não no outro.

## 0. Antes de começar

1. Rodem, a partir de `ETL/ETL`, se ainda não rodaram:

   ```bash
   docker compose exec etl python 04_abt.py --correta
   docker compose exec etl python 04_abt.py --vazamento
   docker compose exec etl python 05_exportar_orange.py
   ```

2. Confirmem que existem, em `saida/`:
   - `abt_recompra_correta.csv`
   - `abt_recompra_vazamento.csv`

   Os nomes são os do `05_exportar_orange.py` (não `abt_correta.csv`). Os dois arquivos têm o cabeçalho de três linhas do
   Orange (nomes, tipos, papéis) e o mesmo número de linhas (`saida/abt/resumo_correta.csv`). **Não usem** os CSVs de
   `dados/`.
3. **Anotem a versão do Orange** (Ajuda → Sobre). Ela vai para o relatório de resultados.
4. A versão `--vazamento-sutil` **não vai ao Orange**: ela é usada só no experimento em Python.

## 1. Fluxo da versão correta

### 1.1 File
- Widget **File**, arquivo `saida/abt_recompra_correta.csv`.
- Conferir o painel de colunas, sem alterar nada: `alvo_recompra_90d` é a **classe** (target), `cliente_sk` e `data_corte`
  são **meta**, `canal_predominante` é categórica e os demais atributos são numéricos.
- O número de instâncias deve ser o de `saida/abt/resumo_correta.csv` (linha `linhas`).

### 1.2 Data Sampler (estratificado 70/30, semente fixa)
- Widget **Data Sampler** ligado ao File.
- *Sampling Type:* **Fixed proportion of data**, **70 %**.
- **Desmarcar** *Sample with replacement*.
- **Marcar** *Stratify sample (when possible)*.
- **Marcar** *Replicable (deterministic) sampling*. Com ela marcada, o Orange usa uma semente interna fixa, e a mesma
  partição se repete a cada *Sample Data*. **Anotem** que a semente é a interna do Orange e a versão do programa (se a sua
  versão permitir escolher a semente, usem 42 e anotem).
- Clicar em *Sample Data*.
- Anotar no relatório os tamanhos de *Data Sample* (treino) e de *Remaining Data* (teste) e a proporção de positivos de cada
  um (deve ficar muito próxima nos dois).

### 1.3 Modelos
Três widgets, **com os parâmetros padrão** (se mudarem algum, anotem e mudem igual nos dois fluxos):
- **Naive Bayes**
- **Logistic Regression**
- **Tree**

### 1.4 Test & Score
- Widget **Test & Score**.
- Ligações:
  - *Data Sampler → Data Sample* → **Data** do Test & Score (é o conjunto de **treino**);
  - *Data Sampler → Remaining Data* → **Test Data** do Test & Score;
  - Naive Bayes, Logistic Regression e Tree → **Learner**.
- Ajustes: **Test on test data** (não usem validação cruzada); *Target Class*: **1**.
- Colunas visíveis: **AUC**, **CA**, **Recall**, e **Specificity** se a sua versão tiver (senão, veja o item 4).

### 1.5 Confusion Matrix e ROC Analysis
- **Confusion Matrix** e **ROC Analysis** ligados à saída *Evaluation Results* do Test & Score.
- Na Confusion Matrix, mostrar *Number of instances* e escolher cada modelo para anotar TN, FP, FN, TP.

### 1.6 Salvar
- Salvar como `relatorio/semana4/fluxo_correta.ows`.

## 2. Fluxo da versão com vazamento

1. Com o fluxo correto aberto, *Salvar como* `relatorio/semana4/fluxo_vazamento.ows` **antes** de mexer em qualquer coisa.
2. No widget **File** do novo fluxo, trocar **apenas** o arquivo para `saida/abt_recompra_vazamento.csv`.
3. Clicar em *Sample Data* de novo, com as mesmas opções (a partição é a mesma, porque a classe e a ordem das linhas são
   idênticas nas duas versões).
4. Salvar.

> A coluna `valor_monetario` da versão correta aparece como `valor_monetario_z` na versão com vazamento (é a normalização
> antes da partição, RDT-15). Isso é diferença do **arquivo**, não do fluxo.

## 3. Capturas de tela

Em `relatorio/semana4/capturas/`, com estes nomes:
- `fluxo_correta_canvas.png` e `fluxo_vazamento_canvas.png`: a tela inteira do fluxo (widgets e ligações);
- `fluxo_correta_testscore.png` e `fluxo_vazamento_testscore.png`: janela do Test & Score com a tabela de resultados;
- `fluxo_correta_roc.png` e `fluxo_vazamento_roc.png`: janela do ROC Analysis;
- `fluxo_correta_confusion_<modelo>.png` e `fluxo_vazamento_confusion_<modelo>.png`, se couber.

## 4. Métricas: `relatorio/semana4/metricas_orange.csv`

Um CSV com **6 linhas** (2 fluxos × 3 modelos) e exatamente este cabeçalho:

```
fluxo,modelo,auc,acuracia,recall,especificidade,acuracia_balanceada
```

- `fluxo`: `correta` ou `vazamento`.
- `modelo`: `Naive Bayes`, `Logistic Regression` ou `Tree`.
- `auc`, `acuracia` (coluna **CA**), `recall` (da classe 1): do Test & Score, na janela de resultados.
- `especificidade`: a coluna **Specificity** do Test & Score; se a sua versão não tiver, calcular na Confusion Matrix:
  `TN / (TN + FP)`.
- `acuracia_balanceada` = `(recall + especificidade) / 2`.
- Ponto como separador decimal; **não arredondem** além de 4 casas (copiem o valor mostrado, não o refaçam de cabeça).

O Orange não traz a acurácia balanceada pronta. Por isso o cálculo acima, com a classe 1 como classe-alvo, é o definido para
este projeto (e é o mesmo que o experimento em Python usa).

## 5. (Recomendado) Exportar a partição

Para o experimento em Python usar **exatamente** a partição do Orange (e eliminar a partição como explicação de qualquer
diferença), no fluxo correto:
1. Ligar *Data Sample* a um widget **Save Data** e salvar `relatorio/semana4/particao_orange_treino.csv`;
2. Ligar *Remaining Data* a outro **Save Data** e salvar `relatorio/semana4/particao_orange_teste.csv`.

Os arquivos devem conter `cliente_sk` (coluna meta). Dispensável no fluxo com vazamento: a partição é a mesma.

## 5.1 Os `.ows` guardam caminhos absolutos

O widget File grava o caminho completo do CSV (por exemplo, `/home/<usuário>/.../saida/abt_recompra_correta.csv`). Quem abrir o
`.ows` em outro computador precisa religar o File ao CSV de `saida/` (rodando antes `05_exportar_orange.py`). Os dois Save Data
estão com o salvamento automático desligado, então abrir o fluxo não regrava a partição.

## 6. Verificações antes de entregar

- [ ] Os dois fluxos têm os mesmos widgets e as mesmas ligações.
- [ ] O treino tem cerca de 70 % das linhas, o teste cerca de 30 %, e a proporção de positivos é praticamente a mesma nos
      dois conjuntos e nos dois fluxos.
- [ ] *Test on test data*, classe-alvo 1, parâmetros padrão.
- [ ] `metricas_orange.csv` tem 6 linhas e as 7 colunas.
- [ ] Capturas salvas; versão do Orange anotada.

Quando tudo estiver pronto, avisem ao agente que `metricas_orange.csv` e os dois `.ows` existem. Só então o experimento
em Python é rodado e comparado com os resultados do Orange.
