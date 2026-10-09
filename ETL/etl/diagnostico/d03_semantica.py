# -*- coding: utf-8 -*-
"""d03 — Heterogeneidade semântica entre as fontes (pergunta b).

    docker compose exec etl python -m diagnostico.d03_semantica

Cada bloco testa uma hipótese do roteiro e registra o que o dado mostra.
Saídas: d03_semantica.md, d03_*.csv e números-chave em numeros.json
(prefixo "b.").
"""

import re
from collections import Counter

import pandas as pd

from .comum import (DATA_AQUISICAO, FUSO_LOCAL, Relatorio, ecom, leg,
                    ler_avaliacoes, ler_sac, normaliza_texto, pct, registrar,
                    salvar_csv, so_digitos)

num = {}
rel = Relatorio("d03_semantica.md", "d03 — Heterogeneidade semântica")

# ===================================================================== STATUS
st_l = leg("""
SELECT STATUS status, COUNT(*) n,
       SUM(DT_ENTREGA IS NULL) sem_entrega,
       SUM(DT_ENTREGA = '1900-01-01') entrega_sentinela,
       SUM(DT_ENTREGA IS NOT NULL AND DT_ENTREGA <> '1900-01-01') com_entrega,
       ROUND(AVG(VALOR_TOTAL), 2) valor_medio,
       SUM(VALOR_TOTAL = 0) valor_zero
FROM PEDIDOS GROUP BY STATUS ORDER BY n DESC""")
st_e = ecom("""
SELECT status, COUNT(*) n,
       SUM((delivered_at IS NULL)::int) sem_entrega,
       0 entrega_sentinela,
       SUM((delivered_at IS NOT NULL)::int) com_entrega,
       ROUND(AVG(total_amount), 2) valor_medio,
       SUM((total_amount = 0)::int) valor_zero
FROM shop.orders GROUP BY status ORDER BY n DESC""")
# pedidos com itens, por status
it_l = leg("""SELECT p.STATUS status, COUNT(DISTINCT p.ID_PEDIDO) com_itens
              FROM PEDIDOS p JOIN ITENS_PEDIDO i ON i.ID_PEDIDO = p.ID_PEDIDO GROUP BY p.STATUS""")
it_e = ecom("""SELECT o.status, COUNT(DISTINCT o.order_id) com_itens
               FROM shop.orders o JOIN shop.order_item i ON i.order_id = o.order_id GROUP BY o.status""")
st_l = st_l.merge(it_l, on="status", how="left")
st_e = st_e.merge(it_e, on="status", how="left")
st_l.insert(0, "sistema", "legado")
st_e.insert(0, "sistema", "ecommerce")
st = pd.concat([st_l, st_e], ignore_index=True)
st["pct_sistema"] = st.groupby("sistema").n.transform(lambda s: (100 * s / s.sum()).round(2))
st = st.fillna(0)
for c in ["n", "sem_entrega", "entrega_sentinela", "com_entrega", "valor_zero", "com_itens"]:
    st[c] = st[c].astype(int)
salvar_csv(st, "d03_status.csv")
for _, r in st.iterrows():
    p = f"b.status.{r.sistema}.{r.status.lower().replace(' ', '_')}"
    for c in ["n", "pct_sistema", "sem_entrega", "com_entrega", "entrega_sentinela", "valor_medio", "valor_zero", "com_itens"]:
        num[f"{p}.{c}"] = r[c]
n_l, n_e = int(st_l.n.sum()), int(st_e.n.sum())
canc_e = int(st_e.loc[st_e.status.isin(["canceled", "payment_declined"]), "n"].sum())
num["b.status.ecommerce.canceled_mais_declined"] = canc_e
num["b.status.ecommerce.canceled_mais_declined_pct"] = pct(canc_e, n_e)
num["b.status.ecommerce.canceled_pct"] = pct(int(st_e.loc[st_e.status.eq("canceled"), "n"].sum()), n_e)
num["b.status.legado.cancelado_pct"] = pct(int(st_l.loc[st_l.status.eq("CANCELADO"), "n"].sum()), n_l)

rel.secao("Status do pedido")
rel.tabela(st)
rel.texto("\nNenhum status além de ENTREGUE/delivered tem data de entrega. "
          "O legado não tem status próprio para recusa de pagamento; compara-se a "
          "participação de CANCELADO com a de canceled e de canceled + payment_declined.")

# ====================================================================== CANAL
hora_l = leg("""SELECT CANAL canal, HOUR(DT_PEDIDO) hora, COUNT(*) n
                FROM PEDIDOS GROUP BY CANAL, HOUR(DT_PEDIDO)""")
hora_e = ecom(f"""SELECT channel canal,
                         EXTRACT(HOUR FROM placed_at AT TIME ZONE '{FUSO_LOCAL}')::int hora, COUNT(*) n
                  FROM shop.orders GROUP BY 1, 2""")
canal = []
for sistema, df in (("legado", hora_l), ("ecommerce", hora_e)):
    for c, g in df.groupby("canal"):
        tot = int(g.n.sum())
        madrugada = int(g.loc[(g.hora >= 22) | (g.hora < 8), "n"].sum())
        canal.append(dict(sistema=sistema, canal=c, pedidos=tot,
                          hora_min=int(g.hora.min()), hora_max=int(g.hora.max()),
                          pedidos_22h_8h=madrugada, pedidos_22h_8h_pct=pct(madrugada, tot)))
frete_l = leg("""SELECT CANAL canal, ROUND(AVG(VALOR_FRETE), 2) frete_medio,
                        SUM(VALOR_FRETE > 0) frete_positivo, COUNT(*) n FROM PEDIDOS GROUP BY CANAL""")
frete_e = ecom("""SELECT channel canal, ROUND(AVG(freight_amount), 2) frete_medio,
                         SUM((freight_amount > 0)::int) frete_positivo, COUNT(*) n
                  FROM shop.orders GROUP BY channel""")
canal = pd.DataFrame(canal)
fr = pd.concat([frete_l.assign(sistema="legado"), frete_e.assign(sistema="ecommerce")])
fr["frete_positivo_pct"] = [pct(a, b) for a, b in zip(fr.frete_positivo, fr.n)]
canal = canal.merge(fr.drop(columns="n"), on=["sistema", "canal"])
salvar_csv(canal, "d03_canal.csv")
for _, r in canal.iterrows():
    p = f"b.canal.{r.sistema}.{r.canal.lower()}"
    for c in ["pedidos", "hora_min", "hora_max", "pedidos_22h_8h", "pedidos_22h_8h_pct",
              "frete_medio", "frete_positivo_pct"]:
        num[f"{p}.{c}"] = r[c]

aq_l = leg(f"""SELECT CANAL canal, DT_PEDIDO >= '{DATA_AQUISICAO}' depois, COUNT(*) n
               FROM PEDIDOS GROUP BY 1, 2""")
aq_e = ecom(f"""SELECT channel canal, (placed_at AT TIME ZONE '{FUSO_LOCAL}') >= '{DATA_AQUISICAO}' depois,
                       COUNT(*) n FROM shop.orders GROUP BY 1, 2""")
aq = pd.concat([aq_l.assign(sistema="legado"), aq_e.assign(sistema="ecommerce")])
aq["depois"] = aq.depois.astype(bool).map({False: "antes", True: "depois"})
aq = aq.pivot_table(index=["sistema", "canal"], columns="depois", values="n").reset_index()
aq["antes_pct"] = aq.groupby("sistema").antes.transform(lambda s: (100 * s / s.sum()).round(2))
aq["depois_pct"] = aq.groupby("sistema").depois.transform(lambda s: (100 * s / s.sum()).round(2))
salvar_csv(aq, "d03_canal_aquisicao.csv")
for _, r in aq.iterrows():
    num[f"b.canal.{r.sistema}.{r.canal.lower()}.antes_pct"] = r.antes_pct
    num[f"b.canal.{r.sistema}.{r.canal.lower()}.depois_pct"] = r.depois_pct

# canal no NDJSON versus canal do pedido referenciado
aval = ler_avaliacoes()
av = pd.DataFrame({"ref": [a["order"].get("ref") for a in aval],
                   "canal_av": [a["order"].get("channel") for a in aval]})
av["pre"] = av.ref.str.split("-").str[0]
av["id"] = pd.to_numeric(av.ref.str.split("-").str[1])
ch_e = ecom("SELECT order_id id, channel FROM shop.orders")
ch_l = leg("SELECT ID_PEDIDO id, CANAL channel FROM PEDIDOS")
av["canal_pedido"] = av.id.map(ch_l.set_index("id").channel).where(av.pre.eq("LEG"),
                                                                   av.id.map(ch_e.set_index("id").channel))
cx = av.groupby(["pre", "canal_av", "canal_pedido"]).size().reset_index(name="n")
salvar_csv(cx, "d03_canal_ndjson.csv")
num["b.canal.ndjson.marketplace"] = int(av.canal_av.eq("marketplace").sum())
num["b.canal.ndjson.marketplace_pct"] = pct(av.canal_av.eq("marketplace").sum(), len(av))
eco_av = av[av.pre.eq("ECOM")]
num["b.canal.ndjson.ecom_pedido_marketplace"] = int(eco_av.canal_pedido.eq("marketplace").sum())
num["b.canal.ndjson.ecom_pedido_marketplace_pct"] = pct(eco_av.canal_pedido.eq("marketplace").sum(), len(eco_av))
num["b.canal.ndjson.ecom_pedido_nao_marketplace"] = int((~eco_av.canal_pedido.eq("marketplace")).sum())

rel.secao("Canal")
rel.tabela(canal)
rel.texto("\nParticipação de cada canal antes e depois de 2024-03:\n")
rel.tabela(aq)
rel.texto("\nCanal declarado no NDJSON × canal do pedido referenciado:\n")
rel.tabela(cx)

# ================================================================= CATEGORIA
prod = leg("SELECT ID_PRODUTO, CATEGORIA FROM PRODUTOS")
prod["bruto"] = prod.CATEGORIA.fillna("")
prod["norm"] = prod.bruto.map(normaliza_texto)
n_mysql = len(leg("SELECT CATEGORIA FROM PRODUTOS GROUP BY CATEGORIA"))
num["b.categoria.legado.distintos_brutos"] = int(prod.bruto.nunique())
num["b.categoria.legado.distintos_brutos_nao_vazios"] = int(prod.bruto[prod.bruto.str.strip() != ""].nunique())
num["b.categoria.legado.grupos_collation_mysql"] = n_mysql
num["b.categoria.legado.distintos_normalizados_nao_vazios"] = int(prod.norm[prod.norm != ""].nunique())
num["b.categoria.legado.vazios"] = int((prod.norm == "").sum())
num["b.categoria.legado.vazios_pct"] = pct((prod.norm == "").sum(), len(prod))

tax = ecom("""SELECT c.category_id, c.name, c.parent_id,
                     (SELECT COUNT(*) FROM shop.category f WHERE f.parent_id = c.category_id) filhos,
                     (SELECT COUNT(*) FROM shop.product p WHERE p.category_id = c.category_id) produtos
              FROM shop.category c ORDER BY c.category_id""")
num["b.categoria.ecommerce.nos"] = len(tax)
num["b.categoria.ecommerce.raizes"] = int(tax.parent_id.isna().sum())
num["b.categoria.ecommerce.nos_com_produto"] = int((tax.produtos > 0).sum())
num["b.categoria.ecommerce.nos_com_produto_sao_folhas"] = int(((tax.produtos > 0) & (tax.filhos == 0)).sum())
num["b.categoria.ecommerce.raizes_com_produto"] = int(((tax.produtos > 0) & tax.parent_id.isna()).sum())

# Proposta de mapeamento rótulo normalizado → nó da taxonomia, com classificação.
# "direto": o rótulo corresponde a um único nó; "nivel": corresponde a uma raiz
# com filhos, mas os produtos do e-commerce só ficam em folhas; "ambiguo": o
# rótulo cobre dois ramos; "sem_mapeamento": rótulo genérico ou vazio.
MAPA = {
    "audio/video": ("Áudio e TV", "nivel"),
    "tv e som": ("Áudio e TV", "nivel"),
    "televisores": ("Televisores", "direto"),
    "casa": ("Casa e Decoração", "nivel"),
    "casa e decoracao": ("Casa e Decoração", "nivel"),
    "moveis": ("Móveis", "direto"),
    "celulares": ("Smartphones", "direto"),
    "celular/smartphone": ("Smartphones", "direto"),
    "telefonia": ("Telefonia", "nivel"),
    "eletrodomesticos": ("Eletrodomésticos", "nivel"),
    "eletro-domesticos": ("Eletrodomésticos", "nivel"),
    "eletro": ("Eletrodomésticos ou Eletroportáteis ou Áudio e TV", "ambiguo"),
    "esporte": ("Esporte e Lazer", "direto"),
    "esportes e lazer": ("Esporte e Lazer", "direto"),
    "ferramentas": ("Ferramentas", "direto"),
    "ferramentas e construcao": ("Ferramentas", "direto"),
    "games": ("Games", "nivel"),
    "games e consoles": ("Games", "nivel"),
    "info": ("Informática", "nivel"),
    "informatica": ("Informática", "nivel"),
    "informatica e games": ("Informática + Games", "ambiguo"),
    "diversos": ("—", "sem_mapeamento"),
    "outros": ("—", "sem_mapeamento"),
    "": ("—", "sem_mapeamento"),
}
cat = (prod.groupby("norm")
       .agg(variantes=("bruto", lambda s: " | ".join(sorted(set(s)))), produtos=("ID_PRODUTO", "size"))
       .reset_index())
cat["no_taxonomia"] = cat.norm.map(lambda k: MAPA.get(k, ("?", "nao_classificado"))[0])
cat["classe"] = cat.norm.map(lambda k: MAPA.get(k, ("?", "nao_classificado"))[1])
salvar_csv(cat, "d03_categoria_mapa.csv")
for classe, g in cat.groupby("classe"):
    num[f"b.categoria.mapa.{classe}.rotulos"] = len(g)
    num[f"b.categoria.mapa.{classe}.produtos"] = int(g.produtos.sum())
    num[f"b.categoria.mapa.{classe}.produtos_pct"] = pct(g.produtos.sum(), len(prod))
num["b.categoria.legado.rotulos_com_variante_caixa_acento"] = int((cat.variantes.str.count(r"\|") > 0).sum())

# A descrição do produto ajuda a validar a categoria? (substantivo inicial × categoria)
desc_l = leg("SELECT DESCRICAO, CATEGORIA FROM PRODUTOS")
desc_l["subst"] = desc_l.DESCRICAO.str.split().str[0].map(normaliza_texto)
desc_l["norm"] = desc_l.CATEGORIA.map(normaliza_texto)
cat_por_subst_l = desc_l[desc_l.norm != ""].groupby("subst").norm.nunique()
desc_e = ecom("SELECT title, category_id FROM shop.product")
desc_e["subst"] = desc_e.title.str.split().str[0].map(normaliza_texto)
cat_por_subst_e = desc_e.groupby("subst").category_id.nunique()
num["b.categoria.legado.substantivos"] = int(cat_por_subst_l.size)
num["b.categoria.legado.categorias_por_substantivo_min"] = int(cat_por_subst_l.min())
num["b.categoria.ecommerce.substantivos"] = int(cat_por_subst_e.size)
num["b.categoria.ecommerce.categorias_por_substantivo_min"] = int(cat_por_subst_e.min())
num["b.categoria.ecommerce.categorias_por_substantivo_max"] = int(cat_por_subst_e.max())

rel.secao("Categoria")
rel.texto(f"Textos distintos (byte a byte): {num['b.categoria.legado.distintos_brutos']} "
          f"(incluindo o vazio); grupos pelo GROUP BY do MySQL (collation latin1_swedish_ci, "
          f"que ignora caixa e acento): {n_mysql}; após normalizar caixa, acento e espaços: "
          f"{num['b.categoria.legado.distintos_normalizados_nao_vazios']} não vazios.")
rel.tabela(cat)
rel.texto("\nTaxonomia do e-commerce:\n")
rel.tabela(tax)
rel.texto(f"\nSubstantivo inicial da descrição × categoria: no legado, cada um dos "
          f"{cat_por_subst_l.size} substantivos aparece em no mínimo {cat_por_subst_l.min()} "
          f"categorias normalizadas; no e-commerce, cada um dos {cat_por_subst_e.size} aparece "
          f"em {cat_por_subst_e.min()} a {cat_por_subst_e.max()} categorias.")

# ===================================================================== NOTAS
sac = ler_sac()
ns = sac.nota_satisfacao
dom_sac = ns.value_counts().sort_index()
num["b.nota.sac.vazias"] = int((ns == "").sum())
num["b.nota.sac.vazias_pct"] = pct((ns == "").sum(), len(sac))
num["b.nota.sac.fora_1_5"] = int((~ns.isin(list("12345")) & (ns != "")).sum())
num["b.nota.sac.fora_1_5_pct"] = pct(num["b.nota.sac.fora_1_5"], len(sac))
num["b.nota.sac.zero"] = int((ns == "0").sum())
for v, n in dom_sac.items():
    num[f"b.nota.sac.valor_{v or 'vazio'}"] = int(n)

tipos = Counter()
dom_av = Counter()
for a in aval:
    if "rating" not in a:
        tipos["ausente"] += 1
        continue
    r = a["rating"]
    tipos[type(r).__name__] += 1
    dom_av[repr(r)] += 1
for k, v in tipos.items():
    num[f"b.nota.ndjson.tipo_{k}"] = v
    num[f"b.nota.ndjson.tipo_{k}_pct"] = pct(v, len(aval))
vals_av = [int(a["rating"]) for a in aval if "rating" in a and a["rating"] is not None
           and str(a["rating"]).strip().lstrip("-").isdigit()]
num["b.nota.ndjson.fora_1_5"] = sum(1 for v in vals_av if v < 1 or v > 5)
num["b.nota.ndjson.nulo_explicito"] = tipos.get("NoneType", 0)
num["b.nota.ndjson.media"] = round(sum(vals_av) / len(vals_av), 3)
vs = pd.to_numeric(ns[ns.isin(list("12345"))])
num["b.nota.sac.media_1_5"] = round(float(vs.mean()), 3)
dist = pd.DataFrame({
    "valor": ["1", "2", "3", "4", "5"],
    "sac_pct": [pct((vs == i).sum(), len(vs)) for i in range(1, 6)],
    "ndjson_pct": [pct(sum(1 for v in vals_av if v == i), len(vals_av)) for i in range(1, 6)],
})
salvar_csv(dist, "d03_notas.csv")
# nota 0 tem algo de particular? (atendimento sem fechamento, canal)
z = sac[ns == "0"]
num["b.nota.sac.zero_sem_fechamento_pct"] = pct((z.data_fechamento == "").sum(), len(z))
num["b.nota.sac.geral_sem_fechamento_pct"] = pct((sac.data_fechamento == "").sum(), len(sac))

rel.secao("Notas")
rel.texto(f"SAC nota_satisfacao (texto): {dict((k or 'vazio', int(v)) for k, v in dom_sac.items())}")
rel.texto(f"NDJSON rating — tipos: {dict(tipos)}; valores: {dict(dom_av)}")
rel.tabela(dist)

# ===================================================================== TEMPO
offs = Counter()
for a in aval:
    m = re.search(r"(Z|[+-]\d{2}:\d{2})$", a["submitted_at"])
    offs[m.group(1) if m else "sem_offset"] += 1
for k, v in offs.items():
    num[f"b.tempo.submitted_at.{k}"] = v
    num[f"b.tempo.submitted_at.{k}_pct"] = pct(v, len(aval))
num["b.tempo.placed_at.tipo"] = str(ecom("""SELECT data_type FROM information_schema.columns
    WHERE table_schema='shop' AND table_name='orders' AND column_name='placed_at'""").iloc[0, 0])
num["b.tempo.dt_pedido.tipo"] = str(leg("""SELECT DATA_TYPE FROM information_schema.columns
    WHERE table_schema='loja_legado' AND table_name='PEDIDOS' AND column_name='DT_PEDIDO'""").iloc[0, 0])

h = pd.to_numeric(sac.tempo_resolucao_horas.str.replace(",", "."), errors="coerce")
ab = pd.to_datetime(sac.data_abertura, format="%d/%m/%Y")
fe = pd.to_datetime(sac.data_fechamento, format="%d/%m/%Y", errors="coerce")
dias = (fe - ab).dt.days
# Sem hora nas datas, a duração real fica em (24·(d−1), 24·(d+1)).
coerente = (h >= 0) & (h > 24 * (dias - 1)) & (h < 24 * (dias + 1))
num["b.tempo.sac.tempo_negativo"] = int((h < 0).sum())
num["b.tempo.sac.tempo_negativo_pct"] = pct((h < 0).sum(), len(sac))
num["b.tempo.sac.sem_fechamento"] = int(fe.isna().sum())
num["b.tempo.sac.sem_fechamento_pct"] = pct(fe.isna().sum(), len(sac))
num["b.tempo.sac.sem_fechamento_com_tempo"] = int((fe.isna() & h.notna()).sum())
num["b.tempo.sac.fechamento_antes_abertura"] = int((dias < 0).sum())
com_fe = fe.notna()
num["b.tempo.sac.coerente"] = int(coerente[com_fe].sum())
num["b.tempo.sac.coerente_pct_com_fechamento"] = pct(coerente[com_fe].sum(), com_fe.sum())
num["b.tempo.sac.incoerente"] = int((~coerente[com_fe]).sum())
num["b.tempo.sac.incoerente_nao_negativo"] = int((~coerente[com_fe] & (h[com_fe] >= 0)).sum())
tdias = pd.DataFrame({"dias": dias, "h": h, "ok": coerente}).groupby(dias.fillna(-1)).agg(
    n=("h", "size"), coerentes=("ok", "sum"), h_min=("h", "min"), h_max=("h", "max")).reset_index()
salvar_csv(tdias, "d03_tempo_resolucao.csv")

rel.secao("Tempo e fuso")
rel.texto(f"- DT_PEDIDO: {num['b.tempo.dt_pedido.tipo']}; placed_at: {num['b.tempo.placed_at.tipo']}.")
rel.texto(f"- Offsets de submitted_at: {dict(offs)}")
rel.texto("- tempo_resolucao_horas × (data_fechamento − data_abertura), por diferença em dias "
          "(-1 = sem fechamento):\n")
rel.tabela(tdias)

# ============================================================ DESCONTO E FRETE
dl = leg("""SELECT QTD qtd, COUNT(*) linhas,
                   SUM(VL_DESCONTO < 0) negativos, SUM(VL_DESCONTO = -1) sentinela_menos1,
                   SUM(VL_DESCONTO = 0) zero,
                   ROUND(AVG(CASE WHEN VL_DESCONTO >= 0 THEN VL_DESCONTO / (QTD * VL_UNITARIO) END), 4) desc_sobre_linha,
                   ROUND(AVG(CASE WHEN VL_DESCONTO >= 0 THEN VL_DESCONTO / VL_UNITARIO END), 4) desc_sobre_unitario,
                   SUM(VL_DESCONTO > VL_UNITARIO) desc_maior_unitario
            FROM ITENS_PEDIDO GROUP BY QTD ORDER BY QTD""")
de = ecom("""SELECT quantity qtd, COUNT(*) linhas,
                    SUM((discount < 0)::int) negativos, SUM((discount = -1)::int) sentinela_menos1,
                    SUM((discount = 0)::int) zero,
                    ROUND(AVG(discount / (quantity * unit_price)), 4) desc_sobre_linha,
                    ROUND(AVG(discount / unit_price), 4) desc_sobre_unitario,
                    SUM((discount > unit_price)::int) desc_maior_unitario
             FROM shop.order_item GROUP BY quantity ORDER BY quantity""")
dsc = pd.concat([dl.assign(sistema="legado"), de.assign(sistema="ecommerce")], ignore_index=True)
salvar_csv(dsc, "d03_desconto.csv")
for _, r in dsc.iterrows():
    p = f"b.desconto.{r.sistema}.qtd{int(r.qtd)}"
    num[f"{p}.desc_sobre_linha_pct"] = round(100 * float(r.desc_sobre_linha), 2)
    num[f"{p}.desc_sobre_unitario_pct"] = round(100 * float(r.desc_sobre_unitario), 2)
for sistema, df in (("legado", dl), ("ecommerce", de)):
    num[f"b.desconto.{sistema}.linhas"] = int(df.linhas.sum())
    num[f"b.desconto.{sistema}.negativos"] = int(df.negativos.sum())
    num[f"b.desconto.{sistema}.sentinela_menos1"] = int(df.sentinela_menos1.sum())
    num[f"b.desconto.{sistema}.sentinela_menos1_pct"] = pct(df.sentinela_menos1.sum(), df.linhas.sum())
    num[f"b.desconto.{sistema}.zero"] = int(df.zero.sum())

dist_l = leg("""SELECT MIN(VL_DESCONTO) mn, MAX(VL_DESCONTO) mx, ROUND(AVG(VL_DESCONTO), 2) media
                FROM ITENS_PEDIDO WHERE VL_DESCONTO >= 0""").iloc[0]
dist_e = ecom("""SELECT MIN(discount) mn, MAX(discount) mx, ROUND(AVG(discount), 2) media
                 FROM shop.order_item""").iloc[0]
num["b.desconto.legado.max"] = float(dist_l.mx)
num["b.desconto.ecommerce.max"] = float(dist_e.mx)

fl = leg("""SELECT COUNT(*) n, SUM(VALOR_FRETE < 0) negativos, SUM(VALOR_FRETE = 0) zero,
                   SUM(VALOR_FRETE = -1) menos1, MIN(VALOR_FRETE) mn, MAX(VALOR_FRETE) mx,
                   ROUND(AVG(VALOR_FRETE), 2) media FROM PEDIDOS""").iloc[0]
fe_ = ecom("""SELECT COUNT(*) n, SUM((freight_amount < 0)::int) negativos, SUM((freight_amount = 0)::int) zero,
                     SUM((freight_amount = -1)::int) menos1, MIN(freight_amount) mn, MAX(freight_amount) mx,
                     ROUND(AVG(freight_amount), 2) media FROM shop.orders""").iloc[0]
for sistema, r in (("legado", fl), ("ecommerce", fe_)):
    for c in ["negativos", "zero", "menos1", "mn", "mx", "media"]:
        num[f"b.frete.{sistema}.{c}"] = float(r[c])
    num[f"b.frete.{sistema}.negativos_pct"] = pct(r.negativos, r.n)

rel.secao("Desconto e frete")
rel.tabela(dsc)
rel.texto(f"\nFrete legado: { {k: float(v) for k, v in fl.items()} }\n\n"
          f"Frete e-commerce: { {k: float(v) for k, v in fe_.items()} }")
rel.texto("\nSe o desconto fosse por unidade, a razão desconto/unitário seria estável entre "
          "quantidades; se for por linha, a razão desconto/(qtd × unitário) é que fica estável.")

# =========================================================== CPF ao longo do tempo
cpf_t = leg(f"""
SELECT YEAR(DT_CADASTRO) ano, DT_CADASTRO >= '{DATA_AQUISICAO}' depois_aquisicao, COUNT(*) n,
       SUM(CPF LIKE '%.%') mascara,
       SUM(CPF REGEXP '^[0-9]{{11}}$') digitos,
       SUM(CPF IS NULL OR CPF = '') ausente
FROM CLIENTES GROUP BY 1, 2 ORDER BY 1, 2""")
cpf_t["mascara_pct"] = (100 * cpf_t.mascara / cpf_t.n).round(2)
cpf_t["digitos_pct"] = (100 * cpf_t.digitos / cpf_t.n).round(2)
cpf_t["ausente_pct"] = (100 * cpf_t.ausente / cpf_t.n).round(2)
salvar_csv(cpf_t, "d03_cpf_tempo.csv")
cpf_aq = cpf_t.groupby("depois_aquisicao")[["n", "mascara", "digitos", "ausente"]].sum()
for d, r in cpf_aq.iterrows():
    rot = "depois" if d else "antes"
    num[f"b.cpf_tempo.{rot}.digitos_pct"] = pct(r.digitos, r.n)
    num[f"b.cpf_tempo.{rot}.mascara_pct"] = pct(r.mascara, r.n)
    num[f"b.cpf_tempo.{rot}.ausente_pct"] = pct(r.ausente, r.n)
num["b.cpf_tempo.digitos_pct_min_ano"] = float(cpf_t.groupby("ano").apply(
    lambda g: pct(g.digitos.sum(), g.n.sum()), include_groups=False).min())
num["b.cpf_tempo.digitos_pct_max_ano"] = float(cpf_t.groupby("ano").apply(
    lambda g: pct(g.digitos.sum(), g.n.sum()), include_groups=False).max())
sac_fmt = sac.assign(ano=sac.data_abertura.str[-4:],
                     mascara=sac.cpf_cliente.str.contains(r"\.")).groupby("ano").mascara.mean().round(4)
for ano, v in sac_fmt.items():
    num[f"b.cpf_tempo.sac.{ano}.mascara_pct"] = round(100 * float(v), 2)

rel.secao("Formato do CPF ao longo do tempo (CLIENTES.DT_CADASTRO)")
rel.tabela(cpf_t)
rel.texto(f"\nSAC — fração com máscara por ano de abertura: {sac_fmt.to_dict()}")

registrar(num)
rel.gravar()
print(st.to_string(index=False))
print(canal.to_string(index=False))
print(cat.to_string(index=False))
print(dsc.to_string(index=False))
