# -*- coding: utf-8 -*-
"""d01 — Volumes de cada fonte e cobertura temporal dos pedidos.

    docker compose exec etl python -m diagnostico.d01_volumes_periodos

Saídas: d01_volumes.csv, d01_pedidos_mensal.csv, d01_volumes_periodos.md
e números-chave em numeros.json (prefixo "v.").

Convenção de tempo: DT_PEDIDO (legado) não tem fuso e é usado como está.
placed_at (e-commerce) é TIMESTAMPTZ; a leitura principal converte para
America/Sao_Paulo, e a leitura em UTC aparece como alternativa.
"""

import pandas as pd

from config import DATA_CORTE, DATA_FIM_ALVO

from .comum import (ARQ_AVALIACOES, ARQ_SAC, DATA_AQUISICAO, FUSO_LOCAL,
                    Relatorio, ecom, escalar, leg, ler_avaliacoes, ler_sac,
                    pct, registrar, salvar_csv)

INICIO_ALVO = "2025-07-01"
num = {}
rel = Relatorio("d01_volumes_periodos.md", "d01 — Volumes e cobertura temporal")

# ---------------------------------------------------------------- volumes
linhas = []
for t in ["CLIENTES", "PRODUTOS", "PEDIDOS", "ITENS_PEDIDO"]:
    n = int(escalar(leg(f"SELECT COUNT(*) FROM {t}")))
    linhas.append(("legado", t, n))
for t in ["customer", "category", "product", "orders", "order_item"]:
    n = int(escalar(ecom(f"SELECT COUNT(*) FROM shop.{t}")))
    linhas.append(("ecommerce", t, n))

sac = ler_sac()
with open(ARQ_SAC, "rb") as f:
    linhas_fisicas_sac = sum(1 for _ in f)
aval = ler_avaliacoes()
with open(ARQ_AVALIACOES, "rb") as f:
    linhas_fisicas_aval = sum(1 for _ in f)
linhas.append(("sac", "atendimentos_sac.csv (registros)", len(sac)))
linhas.append(("avaliacoes", "avaliacoes_marketplace.json (objetos)", len(aval)))

vol = pd.DataFrame(linhas, columns=["fonte", "tabela", "linhas"])
salvar_csv(vol, "d01_volumes.csv")
for fonte, tabela, n in linhas:
    chave = tabela.split(" ")[0].replace(".csv", "").replace(".json", "").lower()
    num[f"v.{fonte}.{chave}.linhas"] = n
por_fonte = vol.groupby("fonte", sort=False).linhas.sum()
for fonte, n in por_fonte.items():
    num[f"v.{fonte}.total"] = int(n)
total = int(vol.linhas.sum())
num["v.total_registros"] = total
num["v.sac.linhas_fisicas_arquivo"] = linhas_fisicas_sac
num["v.avaliacoes.linhas_fisicas_arquivo"] = linhas_fisicas_aval

# comparação com os dois valores declarados (README ≈ 1,9 mi; roteiro ≈ 2,2 mi)
num["v.desvio_readme_1_9mi_pct"] = pct(total - 1_900_000, 1_900_000)
num["v.desvio_roteiro_2_2mi_pct"] = pct(total - 2_200_000, 2_200_000)

rel.secao("Volumes (contagem completa)")
rel.tabela(vol)
rel.texto(f"\nTotal: {total} registros. Desvio em relação ao README (≈ 1,9 milhão): "
          f"{num['v.desvio_readme_1_9mi_pct']}%. Desvio em relação ao roteiro "
          f"(≈ 2,2 milhões): {num['v.desvio_roteiro_2_2mi_pct']}%.")
rel.texto(f"\nO CSV do SAC tem {linhas_fisicas_sac} linhas físicas (cabeçalho incluído) "
          f"para {len(sac)} registros: a diferença vem de quebras de linha dentro de campos.")

# ------------------------------------------------------- intervalo de datas
lim_leg = leg("SELECT MIN(DT_PEDIDO) mn, MAX(DT_PEDIDO) mx FROM PEDIDOS").iloc[0]
lim_eco = ecom(f"""SELECT MIN(placed_at AT TIME ZONE '{FUSO_LOCAL}') mn,
                          MAX(placed_at AT TIME ZONE '{FUSO_LOCAL}') mx,
                          MIN(placed_at AT TIME ZONE 'UTC') mn_utc,
                          MAX(placed_at AT TIME ZONE 'UTC') mx_utc
                   FROM shop.orders""").iloc[0]
intervalos = pd.DataFrame([
    ("legado", "DT_PEDIDO (sem fuso)", lim_leg.mn, lim_leg.mx),
    ("ecommerce", f"placed_at em {FUSO_LOCAL}", lim_eco.mn, lim_eco.mx),
    ("ecommerce", "placed_at em UTC", lim_eco.mn_utc, lim_eco.mx_utc),
], columns=["sistema", "campo", "minimo", "maximo"])
rel.secao("Intervalo de datas dos pedidos")
rel.tabela(intervalos)
num["v.legado.pedido_data_min"] = str(lim_leg.mn)[:10]
num["v.legado.pedido_data_max"] = str(lim_leg.mx)[:10]
num["v.ecommerce.pedido_data_min"] = str(lim_eco.mn)[:10]
num["v.ecommerce.pedido_data_max"] = str(lim_eco.mx)[:10]
num["v.cobre_fim_alvo.legado"] = bool(str(lim_leg.mx)[:10] >= DATA_FIM_ALVO)
num["v.cobre_fim_alvo.ecommerce"] = bool(str(lim_eco.mx)[:10] >= DATA_FIM_ALVO)

# ------------------------------------------------------- contagem mensal
men_leg = leg("""SELECT DATE_FORMAT(DT_PEDIDO, '%Y-%m') mes, COUNT(*) legado
                 FROM PEDIDOS GROUP BY mes ORDER BY mes""")
men_eco = ecom(f"""SELECT TO_CHAR(placed_at AT TIME ZONE '{FUSO_LOCAL}', 'YYYY-MM') mes,
                          COUNT(*) ecommerce
                   FROM shop.orders GROUP BY mes ORDER BY mes""")
mensal = men_leg.merge(men_eco, on="mes", how="outer").fillna(0).sort_values("mes")
mensal[["legado", "ecommerce"]] = mensal[["legado", "ecommerce"]].astype(int)
salvar_csv(mensal, "d01_pedidos_mensal.csv")
rel.secao("Pedidos por mês")
rel.tabela(mensal)
num["v.meses_com_pedidos.legado"] = int((mensal.legado > 0).sum())
num["v.meses_com_pedidos.ecommerce"] = int((mensal.ecommerce > 0).sum())
num["v.legado.pedidos_mes_min"] = int(mensal.legado.min())
num["v.legado.pedidos_mes_max"] = int(mensal.legado.max())
num["v.ecommerce.pedidos_mes_min"] = int(mensal.ecommerce.min())
num["v.ecommerce.pedidos_mes_max"] = int(mensal.ecommerce.max())

# ---------------------------------------------- períodos em torno do corte
SQL_PER_LEG = f"""
SELECT CASE WHEN DT_PEDIDO <  '{INICIO_ALVO}' THEN '1_antes_corte'
            WHEN DT_PEDIDO <  DATE_ADD('{DATA_FIM_ALVO}', INTERVAL 1 DAY) THEN '2_janela_alvo'
            ELSE '3_depois' END periodo, COUNT(*) n
FROM PEDIDOS GROUP BY periodo ORDER BY periodo"""


def sql_per_eco(fuso):
    ts = f"(placed_at AT TIME ZONE '{fuso}')"
    return f"""
SELECT CASE WHEN {ts} <  '{INICIO_ALVO}' THEN '1_antes_corte'
            WHEN {ts} <  DATE '{DATA_FIM_ALVO}' + 1 THEN '2_janela_alvo'
            ELSE '3_depois' END periodo, COUNT(*) n
FROM shop.orders GROUP BY periodo ORDER BY periodo"""


per = leg(SQL_PER_LEG).rename(columns={"n": "legado"})
per = per.merge(ecom(sql_per_eco(FUSO_LOCAL)).rename(columns={"n": "ecommerce_local"}), on="periodo")
per = per.merge(ecom(sql_per_eco("UTC")).rename(columns={"n": "ecommerce_utc"}), on="periodo")
for c in ["legado", "ecommerce_local", "ecommerce_utc"]:
    per[c + "_pct"] = (100 * per[c] / per[c].sum()).round(2)
salvar_csv(per, "d01_periodos_corte.csv")
rel.secao(f"Distribuição em relação ao corte ({DATA_CORTE}) e à janela do alvo "
          f"({INICIO_ALVO} a {DATA_FIM_ALVO})")
rel.tabela(per)
for _, r in per.iterrows():
    p = r.periodo[2:]
    num[f"v.periodo.{p}.legado"] = int(r.legado)
    num[f"v.periodo.{p}.legado_pct"] = float(r.legado_pct)
    num[f"v.periodo.{p}.ecommerce"] = int(r.ecommerce_local)
    num[f"v.periodo.{p}.ecommerce_pct"] = float(r.ecommerce_local_pct)
    num[f"v.periodo.{p}.ecommerce_utc"] = int(r.ecommerce_utc)

# ------------------------------------------- antes × depois da aquisição
SQL_AQ_LEG = f"""
SELECT DT_PEDIDO >= '{DATA_AQUISICAO}' AS depois, COUNT(*) n,
       COUNT(DISTINCT DATE_FORMAT(DT_PEDIDO, '%Y-%m')) meses,
       ROUND(AVG(VALOR_TOTAL), 2) ticket_medio,
       ROUND(100 * AVG(CANAL = 'LOJA'), 2) loja_pct,
       ROUND(100 * AVG(CANAL = 'SITE'), 2) site_pct,
       ROUND(100 * AVG(CANAL = 'TELEVENDAS'), 2) televendas_pct,
       ROUND(100 * AVG(STATUS = 'CANCELADO'), 2) cancelado_pct
FROM PEDIDOS GROUP BY depois ORDER BY depois"""
SQL_AQ_ECO = f"""
SELECT (placed_at AT TIME ZONE '{FUSO_LOCAL}') >= '{DATA_AQUISICAO}' AS depois, COUNT(*) n,
       COUNT(DISTINCT TO_CHAR(placed_at AT TIME ZONE '{FUSO_LOCAL}', 'YYYY-MM')) meses,
       ROUND(AVG(total_amount), 2) ticket_medio,
       ROUND(100 * AVG((channel = 'web')::int), 2) web_pct,
       ROUND(100 * AVG((channel = 'app')::int), 2) app_pct,
       ROUND(100 * AVG((channel = 'marketplace')::int), 2) marketplace_pct,
       ROUND(100 * AVG((status = 'canceled')::int), 2) canceled_pct,
       ROUND(100 * AVG((status = 'payment_declined')::int), 2) payment_declined_pct
FROM shop.orders GROUP BY depois ORDER BY depois"""
aq_leg = leg(SQL_AQ_LEG)
aq_eco = ecom(SQL_AQ_ECO)
for df in (aq_leg, aq_eco):
    df["depois"] = df["depois"].astype(bool).map({False: "antes_2024_03", True: "desde_2024_03"})
    df["pedidos_por_mes"] = (df.n / df.meses).round(1)
salvar_csv(aq_leg, "d01_aquisicao_legado.csv")
salvar_csv(aq_eco, "d01_aquisicao_ecommerce.csv")
rel.secao(f"Antes e depois da aquisição ({DATA_AQUISICAO})")
rel.texto("Legado:")
rel.tabela(aq_leg)
rel.texto("\nE-commerce:")
rel.tabela(aq_eco)
for nome, df in (("legado", aq_leg), ("ecommerce", aq_eco)):
    for _, r in df.iterrows():
        for c in df.columns:
            if c != "depois":
                num[f"v.aquisicao.{nome}.{r.depois}.{c}"] = float(r[c])

# ----------------------------------- cadastro de clientes e fontes de arquivo
cad_leg = leg("SELECT MIN(DT_CADASTRO) mn, MAX(DT_CADASTRO) mx FROM CLIENTES").iloc[0]
cad_eco = ecom(f"""SELECT MIN(created_at AT TIME ZONE '{FUSO_LOCAL}') mn,
                          MAX(created_at AT TIME ZONE '{FUSO_LOCAL}') mx FROM shop.customer""").iloc[0]
ab = pd.to_datetime(sac.data_abertura, format="%d/%m/%Y")
sub = pd.Series([a["submitted_at"][:10] for a in aval])
outros = pd.DataFrame([
    ("CLIENTES.DT_CADASTRO", str(cad_leg.mn)[:10], str(cad_leg.mx)[:10]),
    ("customer.created_at (local)", str(cad_eco.mn)[:10], str(cad_eco.mx)[:10]),
    ("SAC.data_abertura", str(ab.min())[:10], str(ab.max())[:10]),
    ("avaliacoes.submitted_at", sub.min(), sub.max()),
], columns=["campo", "minimo", "maximo"])
rel.secao("Outros intervalos de datas")
rel.tabela(outros)
num["v.legado.cadastro_data_min"] = str(cad_leg.mn)[:10]
num["v.legado.cadastro_data_max"] = str(cad_leg.mx)[:10]

registrar(num)
rel.gravar()
print(vol.to_string(index=False))
print(per.to_string(index=False))
