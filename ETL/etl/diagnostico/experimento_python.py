"""Experimento de vazamento em Python (Semana 4, item 4.4).

Reproduz, fora do Orange, o experimento dos dois fluxos e acrescenta as versões que o Orange não recebeu:

  correta          abt.recompra_90d
  vazamento        abt.recompra_90d_vazamento        (recência e frequência da base inteira + z-score global)
  vazamento_sutil  abt.recompra_90d_vazamento_sutil  (só o z-score global de valor_monetario)
  correta_z_treino controle (D44): versão correta, com z-score de valor_monetario calculado SÓ no treino

Partição: a exportada pelo Orange (`particao_orange_treino.csv` e `particao_orange_teste.csv`, por cliente_sk), o que
elimina a partição como explicação de qualquer diferença. As duas partições vêm de `saida/experimento/` (cópias, com
hash registrado em numeros.json), porque o contêiner não enxerga `relatorio/`.

Modelos: Naive Bayes, Logistic Regression e Tree, espelhando os padrões do Orange 3.40.0 (lidos no código instalado):
  - Logistic Regression: scikit-learn, L2, C=1, lbfgs, max_iter=100, SEM normalização. Pré-processamento do Orange:
    indicadores para a categórica, imputação pela média do treino.
  - Logistic Regression (padronizada): variante extra, com atributos padronizados no treino (não existe no Orange).
  - Naive Bayes: discretização em 4 faixas de mesma frequência (padrão do Orange) e a suavização de Laplace do
    Orange, reimplementados aqui (`NaiveBayesOrange`). Valores ausentes são ignorados.
  - Tree: DecisionTreeClassifier com critério de entropia, profundidade máxima 100, mínimo de 5 para dividir e de 2 por
    folha (os padrões do widget). Divergência conhecida: o Orange usa árvore binária própria, com razão de ganho e
    parada por maioria de 95 %; o scikit-learn não tem esse critério de parada.

Execução (a partir de ETL/ETL):
    docker compose exec etl python -m diagnostico.experimento_python

Saídas em /saida/experimento/: metricas_python.csv, comparacao_orange.csv, efeito_vazamento.csv, auc_univariada.csv,
numeros.json.
"""
import hashlib
import json
import os
import warnings

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import text

from config import DIR_SAIDA, eng_dw

DIR = os.path.join(DIR_SAIDA, "experimento")
ALVO = "alvo_recompra_90d"
META = ["cliente_sk", "data_corte"]
CATEGORICA = "canal_predominante"
VERSOES = {
    "correta": "recompra_90d",
    "vazamento": "recompra_90d_vazamento",
    "vazamento_sutil": "recompra_90d_vazamento_sutil",
}
MODELOS = ["Naive Bayes", "Logistic Regression", "Tree"]
SEMENTE = 42  # só afeta a árvore em empates de divisão; o Orange não expõe semente nos três modelos


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def le_particao(nome):
    """Lê `cliente_sk` de um CSV do Orange (cabeçalho de 3 linhas: nomes, tipos, papéis)."""
    df = pd.read_csv(os.path.join(DIR, nome), skiprows=[1, 2], usecols=["cliente_sk", ALVO])
    return df


# ---------------------------------------------------------------- pré-processamento (como o Orange)
class PreProcessador:
    """Continuize (indicadores para a categórica) + remove colunas todas nulas + imputação pela média do treino."""

    def ajusta(self, X):
        X = pd.get_dummies(X, columns=[CATEGORICA], dtype=float)
        self.colunas = [c for c in X.columns if X[c].notna().any()]
        self.medias = X[self.colunas].mean()
        return self.aplica(X)

    def aplica(self, X):
        if CATEGORICA in X.columns:
            X = pd.get_dummies(X, columns=[CATEGORICA], dtype=float)
        X = X.reindex(columns=self.colunas, fill_value=0.0)
        return X.fillna(self.medias).to_numpy(dtype=float)


# ---------------------------------------------------------------- Naive Bayes (como o Orange)
class NaiveBayesOrange:
    """Naive Bayes do Orange: contínuas em 4 faixas de mesma frequência; Laplace `(n+1)/(n_valor+n_classes)`;
    ausentes ignorados na contagem e na predição.

    Aproximação: os pontos de corte são calculados a partir dos quantis da distribuição (o Orange usa uma rotina em C
    com tratamento próprio de empates). Dá o mesmo resultado quando os quantis caem em valores distintos."""

    def __init__(self, n_faixas=4):
        self.n_faixas = n_faixas

    def _cortes(self, x):
        v = np.sort(x[~np.isnan(x)])
        if len(v) == 0:
            return np.array([])
        unicos, cont = np.unique(v, return_counts=True)
        acum = np.cumsum(cont)
        cortes = []
        for k in range(1, self.n_faixas):
            alvo = k * len(v) / self.n_faixas
            i = int(np.searchsorted(acum, alvo, side="left"))
            if i + 1 < len(unicos):
                cortes.append((unicos[i] + unicos[i + 1]) / 2)
        return np.unique(cortes)

    def _codifica(self, X):
        cod = np.full(X.shape, -1, dtype=int)  # -1 = ausente
        for j, nome in enumerate(self.colunas):
            col = X[:, j]
            ok = ~np.isnan(col)
            if nome == CATEGORICA:
                cod[ok, j] = col[ok].astype(int)
            else:
                cod[ok, j] = np.searchsorted(self.cortes[j], col[ok], side="right")
        return cod

    def ajusta(self, X, y, colunas):
        self.colunas = colunas
        self.cortes = [None if c == CATEGORICA else self._cortes(X[:, j]) for j, c in enumerate(colunas)]
        cod = self._codifica(X)
        ncl = 2
        freq = np.array([(y == k).sum() for k in range(ncl)], dtype=float)
        self.prob_classe = (freq + 1) / (freq.sum() + ncl)
        self.logp = []
        for j in range(len(colunas)):
            nv = int(cod[:, j].max()) + 1
            c = np.zeros((ncl, max(nv, 1)))
            for k in range(ncl):
                v, n = np.unique(cod[(y == k) & (cod[:, j] >= 0), j], return_counts=True)
                c[k, v] = n
            self.logp.append(np.log((c + 1) / (c.sum(axis=0)[None, :] + ncl) / self.prob_classe[:, None]))
        return self

    def prob1(self, X):
        cod = self._codifica(X)
        log = np.tile(np.log(self.prob_classe), (len(X), 1))
        for j, lp in enumerate(self.logp):
            ok = (cod[:, j] >= 0) & (cod[:, j] < lp.shape[1])
            log[ok] += lp[:, cod[ok, j]].T
        log -= log.max(axis=1, keepdims=True)
        p = np.exp(log)
        return p[:, 1] / p.sum(axis=1)


# ---------------------------------------------------------------- treino e avaliação
def treina_e_avalia(treino, teste, aviso):
    """Treina os três modelos com `treino` e avalia em `teste`. Retorna lista de dicts (uma linha por modelo)."""
    ytr, yte = treino[ALVO].to_numpy(), teste[ALVO].to_numpy()
    Xtr_df = treino.drop(columns=META + [ALVO])
    Xte_df = teste.drop(columns=META + [ALVO])
    saidas = []

    # Logistic Regression e Tree: indicadores + imputação
    pre = PreProcessador()
    Xtr = pre.ajusta(Xtr_df)
    Xte = pre.aplica(Xte_df)

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always", ConvergenceWarning)
        lr = LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=100).fit(Xtr, ytr)
        convergiu = not any(issubclass(a.category, ConvergenceWarning) for a in avisos)
    saidas.append(("Logistic Regression", lr.predict_proba(Xte)[:, 1], dict(convergiu=convergiu, iteracoes=int(lr.n_iter_[0]))))

    # Variante da regressão logística com atributos padronizados no treino: converge em todas as versões, o que
    # separa o efeito do vazamento do efeito da falta de convergência (ver experimento_sensibilidade.py).
    esc = StandardScaler().fit(Xtr)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always", ConvergenceWarning)
        lrp = LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=1000).fit(esc.transform(Xtr), ytr)
        convergiu = not any(issubclass(a.category, ConvergenceWarning) for a in avisos)
    saidas.append(("Logistic Regression (padronizada)", lrp.predict_proba(esc.transform(Xte))[:, 1],
                   dict(convergiu=convergiu, iteracoes=int(lrp.n_iter_[0]))))

    arv = DecisionTreeClassifier(criterion="entropy", max_depth=100, min_samples_split=5, min_samples_leaf=2,
                                 random_state=SEMENTE).fit(Xtr, ytr)
    saidas.append(("Tree", arv.predict_proba(Xte)[:, 1], dict(folhas=int(arv.get_n_leaves()), profundidade=int(arv.get_depth()))))

    # Naive Bayes: categórica codificada como inteiro, contínuas ausentes preservadas
    cats = sorted(Xtr_df[CATEGORICA].dropna().unique())
    cod = {c: i for i, c in enumerate(cats)}
    ntr = Xtr_df.assign(**{CATEGORICA: Xtr_df[CATEGORICA].map(cod)}).astype(float)
    nte = Xte_df.assign(**{CATEGORICA: Xte_df[CATEGORICA].map(cod)}).astype(float)
    nb = NaiveBayesOrange().ajusta(ntr.to_numpy(), ytr, list(ntr.columns))
    saidas.append(("Naive Bayes", nb.prob1(nte.to_numpy()), {}))

    linhas = []
    for modelo, p1, extra in saidas:
        pred = (p1 > 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(yte, pred, labels=[0, 1]).ravel()
        rec, esp = tp / (tp + fn), tn / (tn + fp)
        linhas.append(dict(versao=aviso, modelo=modelo, auc=roc_auc_score(yte, p1),
                           acuracia=(tn + tp) / len(yte), recall=rec, especificidade=esp,
                           acuracia_balanceada=(rec + esp) / 2, tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                           n_treino=len(ytr), n_teste=len(yte), **{f"extra_{k}": v for k, v in extra.items()}))
    return linhas


def auc_univariada(df, versao, ids_treino):
    """AUC de cada atributo, sozinho, sobre o treino (orientação livre: max(AUC, 1-AUC))."""
    tr = df[df["cliente_sk"].isin(ids_treino)]
    y = tr[ALVO].to_numpy()
    linhas = []
    for c in tr.columns:
        if c in META + [ALVO, CATEGORICA]:
            continue
        x = tr[c].astype(float)
        ok = x.notna().to_numpy()
        if ok.sum() == 0 or x[ok].nunique() < 2:
            continue
        a = roc_auc_score(y[ok], x[ok])
        linhas.append(dict(versao=versao, atributo=c, auc_univariada=max(a, 1 - a), sentido="+" if a >= 0.5 else "-"))
    return linhas


def main():
    os.makedirs(DIR, exist_ok=True)
    dw = eng_dw()
    tab = {v: pd.read_sql(text(f"SELECT * FROM abt.{t} ORDER BY cliente_sk"), dw) for v, t in VERSOES.items()}

    # ---- partição do Orange
    ptr, pte = le_particao("particao_orange_treino.csv"), le_particao("particao_orange_teste.csv")
    ids_tr, ids_te = set(ptr["cliente_sk"]), set(pte["cliente_sk"])
    conf = {}
    for v, df in tab.items():
        ids = set(df["cliente_sk"])
        conf[v] = dict(linhas=len(df), treino_no_abt=len(ids_tr & ids), teste_no_abt=len(ids_te & ids))
        assert ids == ids_tr | ids_te, f"{v}: a partição do Orange não cobre a ABT"
    assert not (ids_tr & ids_te), "treino e teste se sobrepõem"
    # a classe da partição do Orange deve coincidir com a da tabela no DW
    cl = tab["correta"].set_index("cliente_sk")[ALVO]
    assert (cl.loc[ptr["cliente_sk"]].to_numpy() == ptr[ALVO].to_numpy()).all()
    assert (cl.loc[pte["cliente_sk"]].to_numpy() == pte[ALVO].to_numpy()).all()

    def parte(df):
        return (df[df["cliente_sk"].isin(ids_tr)].reset_index(drop=True),
                df[df["cliente_sk"].isin(ids_te)].reset_index(drop=True))

    # ---- controle D44: correta com z-score só no treino
    cor_tr, cor_te = parte(tab["correta"])
    mu, dp = cor_tr["valor_monetario"].mean(), cor_tr["valor_monetario"].std(ddof=0)
    ctl_tr = cor_tr.assign(valor_monetario_z=(cor_tr["valor_monetario"] - mu) / dp).drop(columns="valor_monetario")
    ctl_te = cor_te.assign(valor_monetario_z=(cor_te["valor_monetario"] - mu) / dp).drop(columns="valor_monetario")

    linhas = []
    for v in VERSOES:
        tr, te = parte(tab[v])
        linhas += treina_e_avalia(tr, te, v)
    linhas += treina_e_avalia(ctl_tr, ctl_te, "correta_z_treino")
    met = pd.DataFrame(linhas)
    met.to_csv(os.path.join(DIR, "metricas_python.csv"), index=False, float_format="%.6f")

    # ---- comparação com o Orange (versões que existem nos dois)
    org = pd.read_csv(os.path.join(DIR, "metricas_orange.csv")).rename(columns={"fluxo": "versao"})
    comp = org.merge(met, on=["versao", "modelo"], suffixes=("_orange", "_python"))
    for m in ["auc", "acuracia", "recall", "especificidade", "acuracia_balanceada"]:
        comp[f"dif_{m}"] = comp[f"{m}_python"] - comp[f"{m}_orange"]
    cols = ["versao", "modelo"] + [f"{m}_{s}" for m in ["auc", "acuracia", "recall", "especificidade", "acuracia_balanceada"] for s in ("orange", "python")] \
        + [f"dif_{m}" for m in ["auc", "acuracia", "recall", "especificidade", "acuracia_balanceada"]]
    comp[cols].to_csv(os.path.join(DIR, "comparacao_orange.csv"), index=False, float_format="%.6f")

    # ---- efeito de cada versão sobre a outra (perguntas a e b do relatório): diferenças em AUC e acurácia balanceada
    efeito = []

    def dif(fonte, tabela, a, b, modelos):
        for m in modelos:
            xa = tabela[(tabela["versao"] == a) & (tabela["modelo"] == m)].iloc[0]
            xb = tabela[(tabela["versao"] == b) & (tabela["modelo"] == m)].iloc[0]
            efeito.append(dict(fonte=fonte, comparacao=f"{a} − {b}", modelo=m,
                               auc_a=xa["auc"], auc_b=xb["auc"], dif_auc=xa["auc"] - xb["auc"],
                               acuracia_balanceada_a=xa["acuracia_balanceada"], acuracia_balanceada_b=xb["acuracia_balanceada"],
                               dif_acuracia_balanceada=xa["acuracia_balanceada"] - xb["acuracia_balanceada"]))

    org_v = org.copy()
    dif("orange", org_v, "vazamento", "correta", MODELOS)
    modelos_py = MODELOS + ["Logistic Regression (padronizada)"]
    for a, b in (("vazamento", "correta"), ("vazamento_sutil", "correta"),
                 ("vazamento_sutil", "correta_z_treino"), ("correta_z_treino", "correta")):
        dif("python", met, a, b, modelos_py)
    pd.DataFrame(efeito).to_csv(os.path.join(DIR, "efeito_vazamento.csv"), index=False, float_format="%.6f")

    # ---- AUC de cada atributo sozinho (como detectar vazamento, pergunta c)
    uni = []
    for v in ("correta", "vazamento"):
        uni += auc_univariada(tab[v], v, ids_tr)
    pd.DataFrame(uni).sort_values(["versao", "auc_univariada"], ascending=[True, False]) \
        .to_csv(os.path.join(DIR, "auc_univariada.csv"), index=False, float_format="%.6f")

    numeros = dict(
        versoes=dict(scikit_learn=sklearn.__version__, scipy=scipy.__version__, pandas=pd.__version__, numpy=np.__version__,
                     orange_referencia="3.40.0"),
        hashes={n: sha256(os.path.join(DIR, n)) for n in
                ["particao_orange_treino.csv", "particao_orange_teste.csv", "metricas_orange.csv"]},
        particao=dict(treino=len(ids_tr), teste=len(ids_te), positivos_treino=int(ptr[ALVO].sum()),
                      positivos_teste=int(pte[ALVO].sum()), conferencia_por_versao=conf),
        z_score_so_no_treino=dict(media=float(mu), desvio=float(dp)),
        diferenca_maxima_abs_orange_python={m: float(comp[f"dif_{m}"].abs().max())
                                             for m in ["auc", "acuracia", "recall", "especificidade", "acuracia_balanceada"]},
    )
    with open(os.path.join(DIR, "numeros.json"), "w", encoding="utf-8") as f:
        json.dump(numeros, f, ensure_ascii=False, indent=2)

    pd.set_option("display.width", 200)
    print(met[["versao", "modelo", "auc", "acuracia", "recall", "especificidade", "acuracia_balanceada"]].round(4).to_string(index=False))
    print("\nDiferença Python − Orange (versões correta e vazamento):")
    print(comp[["versao", "modelo", "dif_auc", "dif_acuracia", "dif_recall", "dif_especificidade"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
