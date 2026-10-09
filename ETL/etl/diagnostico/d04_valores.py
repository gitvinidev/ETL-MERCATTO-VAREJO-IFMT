# -*- coding: utf-8 -*-
"""d04 — Semântica de VALOR_TOTAL e total_amount (pergunta c).

    docker compose exec etl python -m diagnostico.d04_valores

Reconcilia o total gravado no pedido com a soma dos itens, em SQL, sobre
todos os pedidos de cada sistema. Tolerância: 0,01.

    bruto      = Σ qtd × unitário
    desc_linha = Σ desconto
    desc_unid  = Σ qtd × desconto
    H1 total = bruto                  H4 total = bruto + frete
    H2 total = bruto − desc_linha     H5 total = bruto − desc_unid
    H3 total = bruto − desc_linha + frete
    H6 total = bruto − desc_unid + frete

Saídas: d04_valores.md, d04_*.csv e números-chave (prefixo "c.").
"""

import pandas as pd

from .comum import (DATA_AQUISICAO, FUSO_LOCAL, Relatorio, ecom, leg, pct,
                    registrar, salvar_csv)

TOL = 0.01
num = {}
rel = Relatorio("d04_valores.md", "d04 — Semântica dos valores do pedido")

HIP = {
    "H1": "bruto",
    "H2": "bruto - desc_linha",
    "H3": "bruto - desc_linha + frete",
    "H4": "bruto + frete",
    "H5": "bruto - desc_unid",
    "H6": "bruto - desc_unid + frete",
    # variante: sentinela -1 tratado como desconto zero
    "H3s": "bruto - desc_linha_sem_sentinela + frete",
    "H2s": "bruto - desc_linha_sem_sentinela",
}

# Base por pedido. LEFT JOIN preserva pedidos sem itens (bruto nulo).
BASE_LEG = f"""
WITH it AS (
  SELECT ID_PEDIDO,
         COUNT(*) n_itens,
         SUM(QTD * VL_UNITARIO) bruto,
         SUM(VL_DESCONTO) desc_linha,
         SUM(CASE WHEN VL_DESCONTO = -1 THEN 0 ELSE VL_DESCONTO END) desc_linha_sem_sentinela,
         SUM(QTD * VL_DESCONTO) desc_unid,
         SUM(VL_DESCONTO = -1) n_sentinela
  FROM ITENS_PEDIDO GROUP BY ID_PEDIDO),
b AS (
  SELECT p.ID_PEDIDO id, p.VALOR_TOTAL total, p.VALOR_FRETE frete, p.CANAL canal, p.STATUS status,
         CASE WHEN p.DT_PEDIDO >= '{DATA_AQUISICAO}' THEN 'desde_2024_03' ELSE 'antes_2024_03' END periodo,
         COALESCE(it.n_itens, 0) n_itens, it.bruto, it.desc_linha, it.desc_linha_sem_sentinela,
         it.desc_unid, COALESCE(it.n_sentinela, 0) n_sentinela
  FROM PEDIDOS p LEFT JOIN it ON it.ID_PEDIDO = p.ID_PEDIDO)
"""
BASE_ECO = f"""
WITH it AS (
  SELECT order_id,
         COUNT(*) n_itens,
         SUM(quantity * unit_price) bruto,
         SUM(discount) desc_linha,
         SUM(CASE WHEN discount = -1 THEN 0 ELSE discount END) desc_linha_sem_sentinela,
         SUM(quantity * discount) desc_unid,
         SUM((discount = -1)::int) n_sentinela
  FROM shop.order_item GROUP BY order_id),
b AS (
  SELECT o.order_id id, o.total_amount total, o.freight_amount frete, o.channel canal, o.status,
         CASE WHEN (o.placed_at AT TIME ZONE '{FUSO_LOCAL}') >= '{DATA_AQUISICAO}'
              THEN 'desde_2024_03' ELSE 'antes_2024_03' END periodo,
         COALESCE(it.n_itens, 0) n_itens, it.bruto, it.desc_linha, it.desc_linha_sem_sentinela,
         it.desc_unid, COALESCE(it.n_sentinela, 0) n_sentinela
  FROM shop.orders o LEFT JOIN it ON it.order_id = o.order_id)
"""


def flags_sql():
    return ",\n".join(
        f"SUM(CASE WHEN ABS(total - ({e})) <= {TOL} THEN 1 ELSE 0 END) {h.lower()}"
        for h, e in HIP.items())


def por(base, consulta, grupo):
    sel = f"{grupo} grupo," if grupo else "'todos' grupo,"
    gb = f"GROUP BY {grupo}" if grupo else ""
    sql = f"""{base}
SELECT {sel} COUNT(*) pedidos,
       SUM(CASE WHEN n_itens = 0 THEN 1 ELSE 0 END) sem_itens,
       SUM(CASE WHEN n_sentinela > 0 THEN 1 ELSE 0 END) com_desc_sentinela,
       SUM(CASE WHEN frete < 0 THEN 1 ELSE 0 END) frete_negativo,
       {flags_sql()}
FROM b {gb} ORDER BY 1"""
    df = consulta(sql).rename(columns={h.lower(): h for h in HIP})
    for h in HIP:
        df[h + "_pct"] = (100 * df[h].astype(float) / df.pedidos.astype(float)).round(2)
    return df


resultados = {}
for sistema, base, consulta in (("legado", BASE_LEG, leg), ("ecommerce", BASE_ECO, ecom)):
    tabs = []
    for nome, grupo in (("total", None), ("periodo", "periodo"), ("canal", "canal"), ("status", "status")):
        t = por(base, consulta, grupo)
        t.insert(0, "corte", nome)
        tabs.append(t)
    df = pd.concat(tabs, ignore_index=True)
    df.insert(0, "sistema", sistema)
    for c in df.columns:
        if c not in ("sistema", "corte", "grupo") and not c.endswith("_pct"):
            df[c] = df[c].astype(int)
    resultados[sistema] = df
    tot = df[df.corte == "total"].iloc[0]
    for h in HIP:
        num[f"c.{sistema}.{h}.pedidos"] = int(tot[h])
        num[f"c.{sistema}.{h}.pct"] = float(tot[h + "_pct"])
    num[f"c.{sistema}.pedidos"] = int(tot.pedidos)
    num[f"c.{sistema}.sem_itens"] = int(tot.sem_itens)
    num[f"c.{sistema}.com_desc_sentinela"] = int(tot.com_desc_sentinela)
    num[f"c.{sistema}.com_desc_sentinela_pct"] = pct(tot.com_desc_sentinela, tot.pedidos)
    num[f"c.{sistema}.frete_negativo"] = int(tot.frete_negativo)
    num[f"c.{sistema}.frete_negativo_pct"] = pct(tot.frete_negativo, tot.pedidos)
    for _, r in df[df.corte != "total"].iterrows():
        g = str(r.grupo).lower().replace(" ", "_")
        for h in ("H2", "H3", "H3s"):
            num[f"c.{sistema}.{r.corte}.{g}.{h}_pct"] = float(r[h + "_pct"])

tudo = pd.concat(resultados.values(), ignore_index=True)
salvar_csv(tudo, "d04_hipoteses.csv")

resumo = pd.DataFrame({
    "hipotese": list(HIP),
    "formula": list(HIP.values()),
    "legado_pct": [num[f"c.legado.{h}.pct"] for h in HIP],
    "ecommerce_pct": [num[f"c.ecommerce.{h}.pct"] for h in HIP],
})
salvar_csv(resumo, "d04_resumo.csv")
rel.secao(f"Hipóteses (tolerância {TOL}) — todos os pedidos")
rel.tabela(resumo)
rel.texto("\nH2s/H3s: variantes em que o desconto −1 é tratado como zero.")

# --------------------------------------------- resíduos das hipóteses vencedoras
VENC = {"legado": "H3", "ecommerce": "H2"}
RES_SQL = """{base}
SELECT ROUND(total - ({expr}), 2) residuo, COUNT(*) n,
       SUM(CASE WHEN n_sentinela > 0 THEN 1 ELSE 0 END) com_sentinela,
       SUM(n_sentinela) linhas_sentinela_total,
       SUM(CASE WHEN frete < 0 THEN 1 ELSE 0 END) frete_negativo
FROM b GROUP BY ROUND(total - ({expr}), 2) ORDER BY n DESC"""
rel.secao("Distribuição dos resíduos das hipóteses vencedoras")
for sistema, base, consulta in (("legado", BASE_LEG, leg), ("ecommerce", BASE_ECO, ecom)):
    h = VENC[sistema]
    res = consulta(RES_SQL.format(base=base, expr=HIP[h]))
    res["residuo"] = res.residuo.astype(float)
    res.insert(0, "sistema", sistema)
    res.insert(1, "hipotese", h)
    salvar_csv(res, f"d04_residuos_{sistema}.csv")
    rel.texto(f"\n{sistema} — {h} ({HIP[h]}):\n")
    rel.tabela(res.head(15))
    nz = res[res.residuo.abs() > TOL]
    num[f"c.{sistema}.{h}.residuo_nao_nulo"] = int(nz.n.sum())
    num[f"c.{sistema}.{h}.residuos_distintos"] = int(len(nz))
    num[f"c.{sistema}.{h}.residuo_min"] = float(res.residuo.min())
    num[f"c.{sistema}.{h}.residuo_max"] = float(res.residuo.max())
    for _, r in nz.head(5).iterrows():
        num[f"c.{sistema}.{h}.residuo_{r.residuo:g}"] = int(r.n)
    # o resíduo é explicado pelo sentinela? (resíduo = −nº de linhas com −1)
    exp = consulta(f"""{base}
        SELECT SUM(CASE WHEN ABS(total - ({HIP[h]}) + n_sentinela) <= {TOL} THEN 1 ELSE 0 END) explicados,
               SUM(CASE WHEN ABS(total - ({HIP[h]})) > {TOL} THEN 1 ELSE 0 END) nao_batem,
               SUM(CASE WHEN ABS(total - ({HIP[h]})) > {TOL}
                         AND ABS(total - ({HIP[h]}) + n_sentinela) <= {TOL} THEN 1 ELSE 0 END) nao_batem_explicados
        FROM b""").iloc[0]
    num[f"c.{sistema}.{h}.nao_batem"] = int(exp.nao_batem or 0)
    num[f"c.{sistema}.{h}.nao_batem_explicados_por_sentinela"] = int(exp.nao_batem_explicados or 0)

# Pedidos só com itens de quantidade 1: neles desc_linha = desc_unid, e H5/H6
# coincidem com H2/H3. Explica a fração residual das hipóteses por unidade.
q1_l = leg("SELECT COUNT(*) FROM (SELECT ID_PEDIDO FROM ITENS_PEDIDO GROUP BY ID_PEDIDO HAVING MAX(QTD) = 1) x "
           "JOIN PEDIDOS USING (ID_PEDIDO)").iloc[0, 0]
q1_e = ecom("SELECT COUNT(*) FROM (SELECT order_id FROM shop.order_item GROUP BY order_id HAVING MAX(quantity) = 1) x "
            "JOIN shop.orders USING (order_id)").iloc[0, 0]
num["c.legado.pedidos_so_qtd1"] = int(q1_l)
num["c.ecommerce.pedidos_so_qtd1"] = int(q1_e)

# O total do e-commerce exclui o frete; o do legado inclui. Diferença média:
dif = pd.DataFrame([
    ("legado", *leg(f"""{BASE_LEG} SELECT ROUND(AVG(total - (bruto - desc_linha)), 2) m,
                                         ROUND(AVG(frete), 2) f FROM b""").iloc[0]),
    ("ecommerce", *ecom(f"""{BASE_ECO} SELECT ROUND(AVG(total - (bruto - desc_linha)), 2) m,
                                            ROUND(AVG(frete), 2) f FROM b""").iloc[0]),
], columns=["sistema", "media_total_menos_liquido_itens", "media_frete"])
salvar_csv(dif, "d04_total_vs_frete.csv")
for _, r in dif.iterrows():
    num[f"c.{r.sistema}.media_total_menos_itens"] = float(r.media_total_menos_liquido_itens)
    num[f"c.{r.sistema}.media_frete"] = float(r.media_frete)
rel.secao("Total menos líquido dos itens × frete")
rel.tabela(dif)

# Soma financeira por sistema, nas duas definições (insumo da reconciliação da Semana 3)
soma = pd.DataFrame([
    ("legado", *leg(f"""{BASE_LEG} SELECT SUM(total) soma_total, SUM(frete) soma_frete,
                        SUM(bruto - desc_linha_sem_sentinela) soma_liquido_itens FROM b""").iloc[0]),
    ("ecommerce", *ecom(f"""{BASE_ECO} SELECT SUM(total) soma_total, SUM(frete) soma_frete,
                        SUM(bruto - desc_linha_sem_sentinela) soma_liquido_itens FROM b""").iloc[0]),
], columns=["sistema", "soma_total", "soma_frete", "soma_liquido_itens"])
for c in ["soma_total", "soma_frete", "soma_liquido_itens"]:
    soma[c] = soma[c].astype(float).round(2)
for _, r in soma.iterrows():
    for c in ["soma_total", "soma_frete", "soma_liquido_itens"]:
        num[f"c.{r.sistema}.{c}"] = float(r[c])
salvar_csv(soma, "d04_somas.csv")
rel.secao("Somas financeiras por sistema")
rel.tabela(soma.assign(**{c: soma[c].map("{:.2f}".format)
                         for c in ["soma_total", "soma_frete", "soma_liquido_itens"]}),
           disable_numparse=True)

rel.secao("Quebra por período, canal e status")
rel.tabela(tudo[["sistema", "corte", "grupo", "pedidos", "sem_itens", "com_desc_sentinela",
                 "frete_negativo", "H2_pct", "H3_pct", "H3s_pct"]])

registrar(num)
rel.gravar()
print(resumo.to_string(index=False))
print(tudo[["sistema", "corte", "grupo", "pedidos", "com_desc_sentinela", "frete_negativo",
            "H2_pct", "H3_pct", "H3s_pct"]].to_string(index=False))
