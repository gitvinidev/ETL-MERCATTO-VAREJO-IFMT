# -*- coding: utf-8 -*-
"""d06 — Verificações que sustentam o grão das tabelas-fato (pergunta e).

    docker compose exec etl python -m diagnostico.d06_grao

Saídas: d06_grao.md, d06_produto_repetido.csv, d06_status_abt.csv e
números-chave em numeros.json (prefixo "e.").
"""

import pandas as pd

from config import DATA_FIM_ALVO

from .comum import FUSO_LOCAL, Relatorio, ecom, leg, pct, registrar, salvar_csv

INICIO_ALVO = "2025-07-01"
num = {}
rel = Relatorio("d06_grao.md", "d06 — Verificações do grão")

# ------------------------------------------------ unicidade do id de pedido
u_l = leg("SELECT COUNT(*) n, COUNT(DISTINCT ID_PEDIDO) d, SUM(ID_PEDIDO IS NULL) nulos FROM PEDIDOS").iloc[0]
u_e = ecom("SELECT COUNT(*) n, COUNT(DISTINCT order_id) d, SUM((order_id IS NULL)::int) nulos FROM shop.orders").iloc[0]
num["e.legado.pedidos"] = int(u_l.n)
num["e.legado.pedidos_ids_distintos"] = int(u_l.d)
num["e.ecommerce.pedidos"] = int(u_e.n)
num["e.ecommerce.pedidos_ids_distintos"] = int(u_e.d)
ui_l = leg("SELECT COUNT(*) n, COUNT(DISTINCT ID_ITEM) d FROM ITENS_PEDIDO").iloc[0]
ui_e = ecom("SELECT COUNT(*) n, COUNT(DISTINCT order_item_id) d FROM shop.order_item").iloc[0]
num["e.legado.itens"] = int(ui_l.n)
num["e.legado.itens_ids_distintos"] = int(ui_l.d)
num["e.ecommerce.itens"] = int(ui_e.n)
num["e.ecommerce.itens_ids_distintos"] = int(ui_e.d)

# ------------------------------------------------ colisão entre sistemas
ids_l = set(leg("SELECT ID_PEDIDO FROM PEDIDOS").ID_PEDIDO)
ids_e = set(ecom("SELECT order_id FROM shop.orders").order_id)
num["e.colisao.pedido_ids_em_comum"] = len(ids_l & ids_e)
num["e.colisao.pedido_ids_em_comum_pct_legado"] = pct(len(ids_l & ids_e), len(ids_l))
num["e.uniao_pedidos_sem_sistema"] = len(ids_l | ids_e)
num["e.uniao_pedidos_com_sistema"] = len(ids_l) + len(ids_e)

# ------------------------------------- mesmo produto em mais de uma linha
SQL_REP_L = """
SELECT COUNT(*) pares, SUM(n) linhas, SUM(n - 1) excedentes,
       SUM(precos = 1) mesmo_preco, SUM(descs = 1) mesmo_desconto
FROM (SELECT ID_PEDIDO, ID_PRODUTO, COUNT(*) n,
             COUNT(DISTINCT VL_UNITARIO) precos, COUNT(DISTINCT VL_DESCONTO) descs
      FROM ITENS_PEDIDO GROUP BY ID_PEDIDO, ID_PRODUTO HAVING COUNT(*) > 1) x"""
SQL_REP_E = """
SELECT COUNT(*) pares, SUM(n) linhas, SUM(n - 1) excedentes,
       SUM((precos = 1)::int) mesmo_preco, SUM((descs = 1)::int) mesmo_desconto
FROM (SELECT order_id, product_id, COUNT(*) n,
             COUNT(DISTINCT unit_price) precos, COUNT(DISTINCT discount) descs
      FROM shop.order_item GROUP BY order_id, product_id HAVING COUNT(*) > 1) x"""
rep = pd.concat([leg(SQL_REP_L).assign(sistema="legado"), ecom(SQL_REP_E).assign(sistema="ecommerce")])
# Desses pares, quantos têm itens órfãos (pedido inexistente)?
orf_l = leg("""SELECT COUNT(*) FROM (SELECT i.ID_PEDIDO, i.ID_PRODUTO FROM ITENS_PEDIDO i
               WHERE i.ID_PEDIDO IN (SELECT ID_PEDIDO FROM PEDIDOS)
               GROUP BY i.ID_PEDIDO, i.ID_PRODUTO HAVING COUNT(*) > 1) x""").iloc[0, 0]
orf_e = ecom("""SELECT COUNT(*) FROM (SELECT i.order_id, i.product_id FROM shop.order_item i
                WHERE i.order_id IN (SELECT order_id FROM shop.orders)
                GROUP BY i.order_id, i.product_id HAVING COUNT(*) > 1) x""").iloc[0, 0]
rep["pares_em_pedido_existente"] = [int(orf_l), int(orf_e)]
for c in ["pares", "linhas", "excedentes", "mesmo_preco", "mesmo_desconto"]:
    rep[c] = rep[c].astype(int)
salvar_csv(rep, "d06_produto_repetido.csv")
for _, r in rep.iterrows():
    for c in ["pares", "linhas", "excedentes", "mesmo_preco", "mesmo_desconto", "pares_em_pedido_existente"]:
        num[f"e.{r.sistema}.produto_repetido.{c}"] = int(r[c])
num["e.legado.produto_repetido.linhas_pct"] = pct(rep.iloc[0].linhas, ui_l.n)
num["e.ecommerce.produto_repetido.linhas_pct"] = pct(rep.iloc[1].linhas, ui_e.n)

# ------------------- cancelados/recusados: o que muda na ABT se ficarem de fora
pl = leg("SELECT ID_CLIENTE cli, DT_PEDIDO ts, STATUS st FROM PEDIDOS")
pe = ecom(f"""SELECT customer_id cli, placed_at AT TIME ZONE '{FUSO_LOCAL}' ts, status st
              FROM shop.orders""")
NAO_EFETIVO = {"legado": {"CANCELADO"}, "ecommerce": {"canceled", "payment_declined"}}
linhas = []
for sistema, p in (("legado", pl), ("ecommerce", pe)):
    p = p.copy()
    p["eh_hist"] = p.ts < pd.Timestamp(INICIO_ALVO)
    p["janela"] = (p.ts >= pd.Timestamp(INICIO_ALVO)) & (p.ts < pd.Timestamp(DATA_FIM_ALVO) + pd.Timedelta(days=1))
    p["efetivo"] = ~p.st.isin(NAO_EFETIVO[sistema])
    p["hist_ef"] = p.eh_hist & p.efetivo
    p["janela_ef"] = p.janela & p.efetivo
    g = p.groupby("cli").agg(n_h=("eh_hist", "sum"), n_h_ef=("hist_ef", "sum"),
                             alvo=("janela", "any"), alvo_ef=("janela_ef", "any"))
    pop = g[g.n_h > 0]
    d = dict(sistema=sistema,
             pedidos=len(p),
             pedidos_nao_efetivos=int((~p.efetivo).sum()),
             clientes_com_historico=len(pop),
             clientes_so_historico_nao_efetivo=int((pop.n_h_ef == 0).sum()),
             alvo_1_todos_status=int(pop.alvo.sum()),
             alvo_1_so_efetivos=int((pop.alvo_ef).sum()),
             rotulo_muda=int((pop.alvo != pop.alvo_ef).sum()),
             frequencia_muda=int((pop.n_h != pop.n_h_ef).sum()))
    linhas.append(d)
    for k, v in d.items():
        if k != "sistema":
            num[f"e.status_abt.{sistema}.{k}"] = v
    num[f"e.status_abt.{sistema}.pedidos_nao_efetivos_pct"] = pct(d["pedidos_nao_efetivos"], d["pedidos"])
    num[f"e.status_abt.{sistema}.rotulo_muda_pct"] = pct(d["rotulo_muda"], d["clientes_com_historico"])
    num[f"e.status_abt.{sistema}.frequencia_muda_pct"] = pct(d["frequencia_muda"], d["clientes_com_historico"])
    num[f"e.status_abt.{sistema}.alvo_1_todos_status_pct"] = pct(d["alvo_1_todos_status"], d["clientes_com_historico"])
    num[f"e.status_abt.{sistema}.alvo_1_so_efetivos_pct"] = pct(d["alvo_1_so_efetivos"], d["clientes_com_historico"])
tab = pd.DataFrame(linhas)
salvar_csv(tab, "d06_status_abt.csv")

rel.secao("Unicidade e colisão")
rel.texto(f"- PEDIDOS: {u_l.n} linhas, {u_l.d} ID_PEDIDO distintos; orders: {u_e.n} linhas, "
          f"{u_e.d} order_id distintos.")
rel.texto(f"- IDs em comum entre os sistemas: {len(ids_l & ids_e)}; união sem o sistema: "
          f"{len(ids_l | ids_e)}; com o sistema: {len(ids_l) + len(ids_e)}.")
rel.secao("Mesmo produto em mais de uma linha do pedido")
rel.tabela(rep)
rel.secao("Pedidos não efetivos (cancelados e recusados) e a ABT")
rel.texto("População: clientes com ao menos um pedido (qualquer status) antes de 2025-07-01, "
          "por sistema, sem unificação entre sistemas.")
rel.tabela(tab)

registrar(num)
rel.gravar()
print(rep.to_string(index=False))
print(tab.to_string(index=False))
