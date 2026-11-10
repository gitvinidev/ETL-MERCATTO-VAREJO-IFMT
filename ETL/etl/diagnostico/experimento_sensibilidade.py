"""Sensibilidade do experimento Python (Semana 4, item 4.4): por que o Python não coincide exatamente com o Orange.

Duas perguntas, cada uma com números gravados em /saida/experimento/sensibilidade.csv:

  1. A Logistic Regression do experimento não converge em 100 iterações (atributos sem normalização). Com muitas
     iterações (e, separadamente, com atributos padronizados), as versões correta, vazamento_sutil e correta_z_treino
     passam a dar a mesma AUC? Se sim, a diferença entre elas com 100 iterações vem da otimização, não do vazamento.
  2. A Tree do scikit-learn cresce até folhas muito pequenas. O quanto o recall e a acurácia dependem do tamanho mínimo
     da folha? (O Orange para antes, por maioria de 95 %, critério que o scikit-learn não tem.)

Execução (depois de `diagnostico.experimento_python`):
    docker compose exec etl python -m diagnostico.experimento_sensibilidade
"""
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import text

from config import eng_dw
from diagnostico.experimento_python import ALVO, DIR, META, VERSOES, PreProcessador, le_particao


def carrega():
    dw = eng_dw()
    tab = {v: pd.read_sql(text(f"SELECT * FROM abt.{t} ORDER BY cliente_sk"), dw) for v, t in VERSOES.items()}
    ids_tr = set(le_particao("particao_orange_treino.csv")["cliente_sk"])
    pares = {}
    for v, df in tab.items():
        pares[v] = (df[df["cliente_sk"].isin(ids_tr)].reset_index(drop=True),
                    df[~df["cliente_sk"].isin(ids_tr)].reset_index(drop=True))
    tr, te = pares["correta"]
    mu, dp = tr["valor_monetario"].mean(), tr["valor_monetario"].std(ddof=0)
    pares["correta_z_treino"] = tuple(
        d.assign(valor_monetario_z=(d["valor_monetario"] - mu) / dp).drop(columns="valor_monetario") for d in (tr, te))
    return pares


def matriz(tr, te):
    pre = PreProcessador()
    return pre.ajusta(tr.drop(columns=META + [ALVO])), pre.aplica(te.drop(columns=META + [ALVO])), \
        tr[ALVO].to_numpy(), te[ALVO].to_numpy()


def main():
    pares = carrega()
    linhas = []

    # ---- 1. Logistic Regression: iterações e padronização
    for v, (tr, te) in pares.items():
        Xtr, Xte, ytr, yte = matriz(tr, te)
        esc = StandardScaler().fit(Xtr)
        for rotulo, a, b, it in (("100 iterações, sem padronizar (experimento)", Xtr, Xte, 100),
                                  ("10000 iterações, sem padronizar", Xtr, Xte, 10_000),
                                  ("padronizada no treino, 1000 iterações", esc.transform(Xtr), esc.transform(Xte), 1000)):
            with warnings.catch_warnings(record=True) as av:
                warnings.simplefilter("always", ConvergenceWarning)
                m = LogisticRegression(C=1.0, solver="lbfgs", max_iter=it).fit(a, ytr)
                conv = not any(issubclass(x.category, ConvergenceWarning) for x in av)
            p = m.predict_proba(b)[:, 1]
            linhas.append(dict(bloco="logistic_regression", versao=v, configuracao=rotulo, auc=roc_auc_score(yte, p),
                               convergiu=conv, iteracoes=int(m.n_iter_[0]), acuracia=np.nan, recall=np.nan))

    # ---- 2. Tree: tamanho mínimo da folha
    for v in ("correta", "vazamento"):
        Xtr, Xte, ytr, yte = matriz(*pares[v])
        for folha in (1, 2, 5, 20, 50, 100):
            m = DecisionTreeClassifier(criterion="entropy", max_depth=100, min_samples_split=max(5, 2 * folha),
                                       min_samples_leaf=folha, random_state=42).fit(Xtr, ytr)
            p = m.predict_proba(Xte)[:, 1]
            tn, fp, fn, tp = confusion_matrix(yte, (p > 0.5).astype(int), labels=[0, 1]).ravel()
            linhas.append(dict(bloco="tree", versao=v, configuracao=f"min_samples_leaf={folha}", auc=roc_auc_score(yte, p),
                               convergiu=np.nan, iteracoes=np.nan, acuracia=(tn + tp) / len(yte), recall=tp / (tp + fn),
                               folhas=int(m.get_n_leaves())))
    out = pd.DataFrame(linhas)
    out.to_csv(os.path.join(DIR, "sensibilidade.csv"), index=False, float_format="%.6f")
    pd.set_option("display.width", 200)
    print(out.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
