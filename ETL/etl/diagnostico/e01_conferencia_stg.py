# -*- coding: utf-8 -*-
"""Semana 2 · conferência da extração contra o volume diagnosticado na Semana 1.

Compara `stg.extracao_contagem` (gravada por 01_extracao.py) com
`saida/diagnostico/d01_volumes.csv` (gravado por d01_volumes_periodos.py) e
confere o total 577.336 + 1.372.388 + 96.140 + 160.000 = 2.205.864.

    docker compose exec etl python -m diagnostico.e01_conferencia_stg
"""

import os

import pandas as pd

from config import eng_dw
from .comum import DIR_DIAG, registrar, salvar_csv


def main():
    d01 = pd.read_csv(os.path.join(DIR_DIAG, "d01_volumes.csv"))
    stg = pd.read_sql("SELECT fonte, tabela, linhas_stg, linhas_origem "
                      "FROM stg.extracao_contagem", eng_dw())
    # d01 chama as fontes de arquivo de "sac" e "avaliacoes", com o mesmo nome de tabela
    cmp_ = d01.merge(stg, on=["fonte", "tabela"], how="outer", indicator=True)
    cmp_["linhas_d01"] = cmp_["linhas"]
    cmp_["bate"] = (cmp_["linhas_d01"] == cmp_["linhas_stg"]) & (cmp_["_merge"] == "both")
    cmp_ = cmp_[["fonte", "tabela", "linhas_d01", "linhas_origem", "linhas_stg", "bate"]]
    salvar_csv(cmp_, "e01_stg_vs_d01.csv")
    print(cmp_.to_string(index=False))

    por_fonte = cmp_.groupby("fonte")["linhas_stg"].sum()
    total = int(cmp_["linhas_stg"].sum())
    registrar({
        "e01.stg.legado.total": int(por_fonte["legado"]),
        "e01.stg.ecommerce.total": int(por_fonte["ecommerce"]),
        "e01.stg.sac.total": int(por_fonte["sac"]),
        "e01.stg.avaliacoes.total": int(por_fonte["avaliacoes"]),
        "e01.stg.total": total,
        "e01.stg.tabelas_divergentes_d01": int((~cmp_["bate"]).sum()),
    })
    print(f"\ntotal na stg = {total:,}".replace(",", "."),
          "| tabelas que não batem com d01:", int((~cmp_["bate"]).sum()))


if __name__ == "__main__":
    main()
