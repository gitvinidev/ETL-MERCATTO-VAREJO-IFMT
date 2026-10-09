# -*- coding: utf-8 -*-
"""d05 — Anomalias quantificáveis agora × só depois da integração (pergunta d).

    docker compose exec etl python -m diagnostico.d05_anomalias

Grupo "agora": anomalias internas a uma fonte, medidas sem cruzar sistemas.
Grupo "depois": anomalias que só existem quando as fontes são integradas;
quando o número não é fixável, informa-se limite inferior e superior.

Saídas: d05_anomalias.md, d05_agora.csv, d05_depois.csv e números-chave
(prefixo "d.").
"""

import re
from collections import Counter

import pandas as pd

from config import DATA_CORTE, DATA_FIM_ALVO

from .comum import (FUSO_LOCAL, Relatorio, cpf_valido, ecom, leg,
                    ler_avaliacoes, ler_sac, normaliza_texto, pct, registrar,
                    salvar_csv, so_digitos)

INICIO_ALVO = "2025-07-01"
num = {}
rel = Relatorio("d05_anomalias.md", "d05 — Anomalias")
agora = []   # (fonte, anomalia, n, base, pct)


def reg(fonte, chave, descricao, n, base):
    n = int(n)
    agora.append((fonte, descricao, n, int(base), pct(n, base)))
    num[f"d.agora.{chave}"] = n
    num[f"d.agora.{chave}_pct"] = pct(n, base)


# ======================================================= clientes duplicados
cli = leg("SELECT ID_CLIENTE, NOME, CPF, EMAIL, TELEFONE, DT_CADASTRO, CIDADE, UF FROM CLIENTES")
cus = ecom("SELECT customer_id, full_name, tax_id, email, phone, created_at, city, state FROM shop.customer")
cli["cpf"] = so_digitos(cli.CPF)
cli["cpf_ok"] = cli.cpf.map(cpf_valido)
cli["em"] = cli.EMAIL.fillna("").str.strip().str.lower()
cli["nome"] = cli.NOME.map(normaliza_texto)
cus["cpf"] = so_digitos(cus.tax_id)
cus["cpf_ok"] = cus.cpf.map(cpf_valido)
cus["nome"] = cus.full_name.map(normaliza_texto)

dup_cpf = cli.cpf_ok & cli.duplicated("cpf", keep=False) & cli.cpf.ne("")
dup_em = cli.em.ne("") & cli.duplicated("em", keep=False)
dup_nd = cli.duplicated(["nome", "DT_CADASTRO"], keep=False)
dup_tel = cli.duplicated("TELEFONE", keep=False)
N = len(cli)
reg("legado", "cli_dup_cpf_linhas", "CLIENTES: linhas que repetem CPF válido", dup_cpf.sum(), N)
reg("legado", "cli_dup_email_linhas", "CLIENTES: linhas que repetem e-mail", dup_em.sum(), N)
reg("legado", "cli_dup_nome_data_linhas", "CLIENTES: linhas que repetem nome + DT_CADASTRO", dup_nd.sum(), N)
reg("legado", "cli_dup_qualquer_linhas", "CLIENTES: linhas em ao menos um critério de duplicidade",
    (dup_cpf | dup_em | dup_nd).sum(), N)
num["d.agora.cli_dup_email_e_telefone_linhas"] = int((dup_em & dup_tel).sum())
num["d.agora.cli_dup_cpf_e_email_linhas"] = int((dup_cpf & dup_em).sum())
num["d.agora.cli_dup_email_grupos"] = int(cli.loc[dup_em, "em"].nunique())
num["d.agora.cli_dup_cpf_grupos"] = int(cli.loc[dup_cpf, "cpf"].nunique())
# Nos grupos de e-mail repetido, o nome também repete?
g = cli[dup_em].groupby("em").agg(nomes=("nome", "nunique"), cpfs=("cpf", "nunique"), n=("ID_CLIENTE", "size"))
num["d.agora.cli_dup_email_grupos_mesmo_nome"] = int((g.nomes == 1).sum())
num["d.agora.cli_dup_email_grupos_tamanho_max"] = int(g.n.max())
# Excesso de linhas (o que sobraria após deduplicar por e-mail)
num["d.agora.cli_excesso_por_email"] = int(dup_em.sum() - cli.loc[dup_em, "em"].nunique())
reg("ecommerce", "cus_dup_cpf_linhas", "customer: linhas que repetem CPF válido",
    (cus.cpf_ok & cus.duplicated("cpf", keep=False)).sum(), len(cus))

# ======================================================================= SAC
sac = ler_sac()
NS = len(sac)
reg("sac", "sac_linhas_identicas_excedentes", "SAC: linhas idênticas a uma anterior (excedentes)",
    sac.duplicated().sum(), NS)
prot_rep = sac.duplicated("protocolo", keep=False)
ident = sac.duplicated(keep=False)
num["d.agora.sac_protocolo_repetido_linhas"] = int(prot_rep.sum())
num["d.agora.sac_protocolo_repetido_nao_identico"] = int((prot_rep & ~ident).sum())
num["d.agora.sac_protocolos_distintos"] = int(sac.protocolo.nunique())
quebra = {c: int(sac[c].str.contains(r"[\r\n]").sum()) for c in sac.columns}
for c, v in quebra.items():
    if v:
        num[f"d.agora.sac_quebra_linha.{c}"] = v
reg("sac", "sac_quebra_linha", "SAC: registros com quebra de linha em algum campo",
    sac.apply(lambda s: s.str.contains(r"[\r\n]")).any(axis=1).sum(), NS)
reg("sac", "sac_nota_fora_dominio", "SAC: nota_satisfacao fora de 1–5 (valor 0)",
    (~sac.nota_satisfacao.isin(list("12345") + [""])).sum(), NS)
reg("sac", "sac_nota_vazia", "SAC: nota_satisfacao vazia", (sac.nota_satisfacao == "").sum(), NS)
h = pd.to_numeric(sac.tempo_resolucao_horas.str.replace(",", "."), errors="coerce")
reg("sac", "sac_tempo_negativo", "SAC: tempo_resolucao_horas negativo", (h < 0).sum(), NS)
reg("sac", "sac_canal_caixa_mista", "SAC: canal fora de caixa alta (chat, telefone)",
    (sac.canal != sac.canal.str.upper()).sum(), NS)
num["d.agora.sac_canais_brutos"] = int(sac.canal.nunique())
num["d.agora.sac_canais_normalizados"] = int(sac.canal.str.upper().nunique())
num["d.agora.sac_motivos_brutos"] = int(sac.motivo.nunique())
num["d.agora.sac_motivos_normalizados"] = int(
    sac.motivo.str.split("\n").str[0].map(normaliza_texto).nunique())

# =============================================================== datas-sentinela
sent_l = leg("""SELECT
   SUM(DT_ENTREGA < '2000-01-01') entrega_antiga,
   SUM(DT_ENTREGA = '1900-01-01') entrega_1900,
   SUM(DT_PEDIDO < '2000-01-01' OR DT_PEDIDO > '2030-01-01') pedido_fora,
   SUM(DT_ENTREGA > '2030-01-01') entrega_futura,
   SUM(DT_ENTREGA IS NOT NULL AND DT_ENTREGA >= '2000-01-01' AND DT_ENTREGA < DT_PEDIDO) entrega_antes_pedido,
   COUNT(*) n FROM PEDIDOS""").iloc[0]
sent_c = leg("""SELECT SUM(DT_CADASTRO < '2000-01-01' OR DT_CADASTRO > '2030-01-01') cad_fora,
                       SUM(CIDADE IN ('N/A', 'NA', '-', '')) cidade_sentinela, COUNT(*) n FROM CLIENTES""").iloc[0]
sent_e = ecom("""SELECT
   SUM((delivered_at < '2000-01-01')::int) entrega_antiga,
   SUM((placed_at < '2000-01-01' OR placed_at > '2030-01-01')::int) pedido_fora,
   SUM((delivered_at < placed_at)::int) entrega_antes_pedido,
   COUNT(*) n FROM shop.orders""").iloc[0]
reg("legado", "ped_entrega_1900", "PEDIDOS: DT_ENTREGA = 1900-01-01", sent_l.entrega_1900, sent_l.n)
num["d.agora.ped_entrega_antes_2000"] = int(sent_l.entrega_antiga)
num["d.agora.ped_data_pedido_fora"] = int(sent_l.pedido_fora)
reg("legado", "ped_entrega_antes_pedido", "PEDIDOS: entrega anterior ao pedido (sem sentinela)",
    sent_l.entrega_antes_pedido, sent_l.n)
reg("legado", "cli_cidade_sentinela", "CLIENTES: CIDADE = 'N/A'", sent_c.cidade_sentinela, sent_c.n)
num["d.agora.cli_cadastro_fora"] = int(sent_c.cad_fora)
num["d.agora.orders_entrega_antes_2000"] = int(sent_e.entrega_antiga)
reg("ecommerce", "orders_entrega_antes_pedido", "orders: delivered_at anterior a placed_at",
    sent_e.entrega_antes_pedido, sent_e.n)
ab = pd.to_datetime(sac.data_abertura, format="%d/%m/%Y", errors="coerce")
fe = pd.to_datetime(sac.data_fechamento, format="%d/%m/%Y", errors="coerce")
num["d.agora.sac_data_fora"] = int(((ab < "2000-01-01") | (fe < "2000-01-01")).sum())
# intervalo entre pedido e entrega (para mostrar que 1900 é sentinela, não dado)
ent = leg("""SELECT MIN(DATEDIFF(DT_ENTREGA, DT_PEDIDO)) mn, MAX(DATEDIFF(DT_ENTREGA, DT_PEDIDO)) mx
             FROM PEDIDOS WHERE DT_ENTREGA >= '2000-01-01'""").iloc[0]
num["d.agora.ped_dias_entrega_min"] = int(ent.mn)
num["d.agora.ped_dias_entrega_max"] = int(ent.mx)

# ====================================================== integridade referencial
ri = [
    ("legado", "itens_sem_pedido", "ITENS_PEDIDO sem PEDIDOS",
     "SELECT COUNT(*) FROM ITENS_PEDIDO i LEFT JOIN PEDIDOS p ON p.ID_PEDIDO = i.ID_PEDIDO WHERE p.ID_PEDIDO IS NULL",
     "SELECT COUNT(*) FROM ITENS_PEDIDO"),
    ("legado", "pedidos_sem_itens", "PEDIDOS sem ITENS_PEDIDO",
     "SELECT COUNT(*) FROM PEDIDOS p WHERE NOT EXISTS (SELECT 1 FROM ITENS_PEDIDO i WHERE i.ID_PEDIDO = p.ID_PEDIDO)",
     "SELECT COUNT(*) FROM PEDIDOS"),
    ("legado", "pedidos_sem_cliente", "PEDIDOS sem CLIENTES",
     "SELECT COUNT(*) FROM PEDIDOS p LEFT JOIN CLIENTES c ON c.ID_CLIENTE = p.ID_CLIENTE WHERE c.ID_CLIENTE IS NULL",
     "SELECT COUNT(*) FROM PEDIDOS"),
    ("legado", "itens_sem_produto", "ITENS_PEDIDO sem PRODUTOS",
     "SELECT COUNT(*) FROM ITENS_PEDIDO i LEFT JOIN PRODUTOS p ON p.ID_PRODUTO = i.ID_PRODUTO WHERE p.ID_PRODUTO IS NULL",
     "SELECT COUNT(*) FROM ITENS_PEDIDO"),
    ("ecommerce", "itens_sem_pedido", "order_item sem orders",
     "SELECT COUNT(*) FROM shop.order_item i LEFT JOIN shop.orders o ON o.order_id = i.order_id WHERE o.order_id IS NULL",
     "SELECT COUNT(*) FROM shop.order_item"),
    ("ecommerce", "pedidos_sem_itens", "orders sem order_item",
     "SELECT COUNT(*) FROM shop.orders o WHERE NOT EXISTS (SELECT 1 FROM shop.order_item i WHERE i.order_id = o.order_id)",
     "SELECT COUNT(*) FROM shop.orders"),
    ("ecommerce", "pedidos_sem_cliente", "orders sem customer",
     "SELECT COUNT(*) FROM shop.orders o LEFT JOIN shop.customer c ON c.customer_id = o.customer_id WHERE c.customer_id IS NULL",
     "SELECT COUNT(*) FROM shop.orders"),
    ("ecommerce", "itens_sem_produto", "order_item sem product",
     "SELECT COUNT(*) FROM shop.order_item i LEFT JOIN shop.product p ON p.product_id = i.product_id WHERE p.product_id IS NULL",
     "SELECT COUNT(*) FROM shop.order_item"),
]
for fonte, chave, desc, sql_n, sql_b in ri:
    q = leg if fonte == "legado" else ecom
    reg(fonte, f"ri.{fonte}.{chave}", desc, q(sql_n).iloc[0, 0], q(sql_b).iloc[0, 0])
orf_e = ecom("""SELECT COUNT(DISTINCT i.order_id) pedidos, MIN(i.order_id) mn, MAX(i.order_id) mx
                FROM shop.order_item i LEFT JOIN shop.orders o ON o.order_id = i.order_id
                WHERE o.order_id IS NULL""").iloc[0]
orf_l = leg("""SELECT COUNT(DISTINCT i.ID_PEDIDO) pedidos, MIN(i.ID_PEDIDO) mn, MAX(i.ID_PEDIDO) mx
               FROM ITENS_PEDIDO i LEFT JOIN PEDIDOS p ON p.ID_PEDIDO = i.ID_PEDIDO
               WHERE p.ID_PEDIDO IS NULL""").iloc[0]
num["d.agora.ri.ecommerce.itens_sem_pedido_ids_distintos"] = int(orf_e.pedidos)
num["d.agora.ri.ecommerce.itens_sem_pedido_id_min"] = int(orf_e.mn)
num["d.agora.ri.legado.itens_sem_pedido_ids_distintos"] = int(orf_l.pedidos)
num["d.agora.ri.legado.itens_sem_pedido_id_min"] = int(orf_l.mn)
num["d.agora.ri.legado.itens_sem_pedido_id_max"] = int(orf_l.mx)

# ======================================================= preços e valores
pv_l = leg("""SELECT (SELECT SUM(VL_UNITARIO <= 0) FROM ITENS_PEDIDO) unit,
                     (SELECT SUM(PRECO_TABELA <= 0 OR PRECO_TABELA IS NULL) FROM PRODUTOS) tabela,
                     (SELECT SUM(VALOR_TOTAL <= 0) FROM PEDIDOS) total,
                     (SELECT SUM(QTD <= 0) FROM ITENS_PEDIDO) qtd""").iloc[0]
pv_e = ecom("""SELECT (SELECT SUM((unit_price <= 0)::int) FROM shop.order_item) unit,
                      (SELECT SUM((list_price <= 0 OR list_price IS NULL)::int) FROM shop.product) tabela,
                      (SELECT SUM((total_amount <= 0)::int) FROM shop.orders) total,
                      (SELECT SUM((quantity <= 0)::int) FROM shop.order_item) qtd""").iloc[0]
for s, r in (("legado", pv_l), ("ecommerce", pv_e)):
    for c in ["unit", "tabela", "total", "qtd"]:
        num[f"d.agora.preco_zero_ou_negativo.{s}.{c}"] = int(r[c] or 0)
fr = leg("SELECT SUM(VALOR_FRETE < 0) n, COUNT(*) b FROM PEDIDOS").iloc[0]
reg("legado", "frete_negativo", "PEDIDOS: VALOR_FRETE negativo", fr.n, fr.b)
fr = ecom("SELECT SUM((freight_amount < 0)::int) n, COUNT(*) b FROM shop.orders").iloc[0]
reg("ecommerce", "frete_negativo_eco", "orders: freight_amount negativo", fr.n, fr.b)
ds = leg("SELECT SUM(VL_DESCONTO = -1) n, COUNT(*) b FROM ITENS_PEDIDO").iloc[0]
reg("legado", "desconto_sentinela", "ITENS_PEDIDO: VL_DESCONTO = −1", ds.n, ds.b)

# ============================================================== NDJSON
aval = ler_avaliacoes()
NA = len(aval)
chaves = Counter()
for a in aval:
    chaves.update(a.keys())
todas = ["review_id", "order", "product", "submitted_at", "rating", "verified_purchase",
         "title", "comment", "helpful_votes"]
for k in todas:
    num[f"d.agora.ndjson.ausente.{k}"] = NA - chaves.get(k, 0)
reg("avaliacoes", "ndjson_rating_ausente", "NDJSON: chave rating ausente", NA - chaves["rating"], NA)
reg("avaliacoes", "ndjson_rating_texto", "NDJSON: rating como texto ('1'..'5')",
    sum(1 for a in aval if isinstance(a.get("rating"), str)), NA)
reg("avaliacoes", "ndjson_verified_ausente", "NDJSON: verified_purchase ausente",
    NA - chaves["verified_purchase"], NA)
reg("avaliacoes", "ndjson_sem_offset", "NDJSON: submitted_at sem offset",
    sum(1 for a in aval if not re.search(r"(Z|[+-]\d{2}:\d{2})$", a["submitted_at"])), NA)
rid = Counter(a["review_id"] for a in aval)
num["d.agora.ndjson.review_id_repetido"] = sum(v for v in rid.values() if v > 1)

tab_agora = pd.DataFrame(agora, columns=["fonte", "anomalia", "n", "base", "pct"])
salvar_csv(tab_agora, "d05_agora.csv")
rel.secao("Grupo 1 — quantificáveis agora (dentro de uma única fonte)")
rel.tabela(tab_agora)

# =================================================================
# Grupo 2 — só depois da integração
# =================================================================
depois = []


def reg2(chave, descricao, inferior, superior, base, porque):
    depois.append((descricao, int(inferior), int(superior), int(base),
                   pct(inferior, base), pct(superior, base), porque))
    num[f"d.depois.{chave}.inferior"] = int(inferior)
    num[f"d.depois.{chave}.superior"] = int(superior)
    num[f"d.depois.{chave}.inferior_pct"] = pct(inferior, base)
    num[f"d.depois.{chave}.superior_pct"] = pct(superior, base)


# ------------------------------------------- clientes presentes nos dois sistemas
cpf_l = set(cli.loc[cli.cpf_ok, "cpf"])
cpf_e = set(cus.loc[cus.cpf_ok, "cpf"])
inter = cpf_l & cpf_e
# Limite superior: soma aos pares por CPF os registros do legado sem par por CPF
# cujo (nome normalizado, UF) existe no e-commerce em registro também sem par.
cli["chave_nu"] = cli.nome + "|" + cli.UF.fillna("")
cus["chave_nu"] = cus.nome + "|" + cus.state.fillna("")
l_sem = cli[~cli.cpf.isin(inter)]
e_sem = cus[~cus.cpf.isin(inter)]
cand = l_sem[l_sem.chave_nu.isin(set(e_sem.chave_nu))]
# taxa de homônimo: entre pares com CPF válido diferente, quantos coincidem em nome+UF?
l_val_sem = l_sem[l_sem.cpf_ok]
e_val_sem = e_sem[e_sem.cpf_ok]
homon = l_val_sem.chave_nu.isin(set(e_val_sem.chave_nu)).sum()
num["d.depois.clientes_comuns.candidatos_nome_uf"] = len(cand)
num["d.depois.clientes_comuns.candidatos_nome_uf_sem_cpf_valido_algum_lado"] = int(
    (~cand.cpf_ok | cand.chave_nu.isin(set(e_sem.loc[~e_sem.cpf_ok, "chave_nu"]))).sum())
num["d.depois.clientes_comuns.homonimos_com_cpfs_validos_distintos"] = int(homon)
# Para o limite superior só contam candidatos em que ao menos um lado não tem CPF válido
# (se os dois têm CPF válido e diferente, são pessoas diferentes).
e_sem_inval = set(e_sem.loc[~e_sem.cpf_ok, "chave_nu"])
e_sem_val = set(e_sem.loc[e_sem.cpf_ok, "chave_nu"])
sup_extra = int(((~l_sem.cpf_ok) & l_sem.chave_nu.isin(set(e_sem.chave_nu))).sum()
                + (l_sem.cpf_ok & l_sem.chave_nu.isin(e_sem_inval)).sum())
cli_par = int(cli.cpf.isin(inter).sum())
reg2("clientes_comuns", "Registros de CLIENTES com par no e-commerce (CPF válido; + nome e UF quando falta CPF)",
     cli_par, cli_par + sup_extra, len(cli),
     "exige cruzar CLIENTES e customer; nenhuma fonte isolada sabe que o cliente existe na outra")
num["d.depois.clientes_comuns.cpfs_distintos"] = len(inter)

# ------------------------------- SAC e avaliações apontando para o sistema errado
sac["cpf"] = so_digitos(sac.cpf_cliente)
em_l = sac.cpf.isin(set(cli.cpf) - {""})
em_e = sac.cpf.isin(set(cus.cpf) - {""})
leg_t = sac.origem_sistema.eq("LEGADO")
so_outro = (leg_t & ~em_l & em_e) | (~leg_t & ~em_e & em_l)
ambos = em_l & em_e
num["d.depois.sac_sistema_errado.cpf_so_no_outro"] = int(so_outro.sum())
num["d.depois.sac_sistema_errado.cpf_nos_dois"] = int(ambos.sum())
num["d.depois.sac_sistema_errado.cpf_em_nenhum"] = int((~em_l & ~em_e).sum())
reg2("sac_sistema_errado",
     "Atendimentos do SAC cujo cliente (pelo CPF) pertence ao outro sistema",
     so_outro.sum(), so_outro.sum() + ambos.sum() + (~em_l & ~em_e).sum(), NS,
     "o CSV declara o sistema, mas só o cruzamento do CPF com os dois cadastros revela a contradição")

av = pd.DataFrame({"ref": [a["order"]["ref"] for a in aval], "sku": [a["product"]["sku"] for a in aval]})
av["pre"] = av.ref.str.split("-").str[0]
av["id"] = pd.to_numeric(av.ref.str.split("-").str[1])
ids_l = set(leg("SELECT ID_PEDIDO FROM PEDIDOS").ID_PEDIDO)
ids_e = set(ecom("SELECT order_id FROM shop.orders").order_id)
dupla = av.id.isin(ids_l) & av.id.isin(ids_e)
item_e = ecom("""SELECT DISTINCT i.order_id, p.sku FROM shop.order_item i
                 JOIN shop.product p ON p.product_id = i.product_id""")
item_l = leg("SELECT DISTINCT ID_PEDIDO, CONCAT('LEG-', ID_PRODUTO) sku FROM ITENS_PEDIDO")
par_e = set(zip(item_e.order_id, item_e.sku))
par_l = set(zip(item_l.ID_PEDIDO, item_l.sku))
no_ind = [((i, s) in par_e) if p == "ECOM" else ((i, s) in par_l) for p, i, s in zip(av.pre, av.id, av.sku)]
no_out = [((i, s) in par_l) if p == "ECOM" else ((i, s) in par_e) for p, i, s in zip(av.pre, av.id, av.sku)]
num["d.depois.ndjson_sistema_errado.sku_no_pedido_indicado"] = int(sum(no_ind))
num["d.depois.ndjson_sistema_errado.sku_no_pedido_do_outro"] = int(sum(no_out))
num["d.depois.ndjson_sistema_errado.id_existe_nos_dois"] = int(dupla.sum())
reg2("ndjson_sistema_errado",
     "Avaliações cujo produto não é item do pedido referenciado (vínculo inconsistente)",
     len(av) - sum(no_ind), len(av) - sum(no_ind), len(av),
     "o NDJSON sozinho só mostra que o pedido e o SKU existem; a inconsistência aparece ao juntar com os itens")

# ------------------------------------------------- fuso em torno do corte
n_pedidos = int(leg("SELECT COUNT(*) FROM PEDIDOS").iloc[0, 0]) + \
    int(ecom("SELECT COUNT(*) FROM shop.orders").iloc[0, 0])
fronteiras = {"corte": "2025-06-30", "fim_alvo": DATA_FIM_ALVO}
fz = []
for nome, d in fronteiras.items():
    d1 = (pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    # janela ampla pedida: D 20:00 a D+1 04:00, em hora local
    nl = int(leg(f"SELECT COUNT(*) FROM PEDIDOS WHERE DT_PEDIDO >= '{d} 20:00' AND DT_PEDIDO < '{d1} 04:00'").iloc[0, 0])
    ne = int(ecom(f"""SELECT COUNT(*) FROM shop.orders
                      WHERE (placed_at AT TIME ZONE '{FUSO_LOCAL}') >= '{d} 20:00'
                        AND (placed_at AT TIME ZONE '{FUSO_LOCAL}') < '{d1} 04:00'""").iloc[0, 0])
    # pedidos que trocam de lado: data local = D e data UTC = D+1 (local 21:00–23:59)
    fl = int(leg(f"SELECT COUNT(*) FROM PEDIDOS WHERE DT_PEDIDO >= '{d} 21:00' AND DT_PEDIDO < '{d1}'").iloc[0, 0])
    fe_ = int(ecom(f"""SELECT COUNT(*) FROM shop.orders
                       WHERE (placed_at AT TIME ZONE '{FUSO_LOCAL}')::date = '{d}'
                         AND (placed_at AT TIME ZONE 'UTC')::date = '{d1}'""").iloc[0, 0])
    sem_off = sum(1 for a in aval if len(a["submitted_at"]) == 19 and
                  f"{d}T20:00" <= a["submitted_at"] < f"{d1}T04:00")
    fz.append(dict(fronteira=nome, data=d, legado_20h_04h=nl, ecommerce_20h_04h=ne,
                   legado_troca_lado=fl, ecommerce_troca_lado=fe_, avaliacoes_sem_offset_20h_04h=sem_off))
    num[f"d.depois.fuso.{nome}.legado_20h_04h"] = nl
    num[f"d.depois.fuso.{nome}.ecommerce_20h_04h"] = ne
    num[f"d.depois.fuso.{nome}.legado_troca_lado"] = fl
    num[f"d.depois.fuso.{nome}.ecommerce_troca_lado"] = fe_
    num[f"d.depois.fuso.{nome}.avaliacoes_sem_offset_20h_04h"] = sem_off
tab_fz = pd.DataFrame(fz)
salvar_csv(tab_fz, "d05_fuso_fronteiras.csv")

# Rótulo do alvo por cliente nas duas leituras do fuso
def rotulos(pedidos, col_cli, col_ts):
    p = pedidos.copy()
    p["eh_hist"] = p[col_ts] < pd.Timestamp(INICIO_ALVO)
    p["alvo"] = (p[col_ts] >= pd.Timestamp(INICIO_ALVO)) & \
                (p[col_ts] < pd.Timestamp(DATA_FIM_ALVO) + pd.Timedelta(days=1))
    g = p.groupby(col_cli).agg(n_hist=("eh_hist", "sum"), alvo=("alvo", "any"))
    return g


pe = ecom(f"""SELECT customer_id, placed_at AT TIME ZONE '{FUSO_LOCAL}' ts_local,
                     placed_at AT TIME ZONE 'UTC' ts_utc FROM shop.orders""")
rl = rotulos(pe, "customer_id", "ts_local")
ru = rotulos(pe, "customer_id", "ts_utc")
pop = rl.index[(rl.n_hist > 0) | (ru.n_hist > 0)]
muda_e = int((rl.loc[pop, "alvo"] != ru.loc[pop, "alvo"]).sum())
muda_hist_e = int((rl.loc[pop, "n_hist"] != ru.loc[pop, "n_hist"]).sum())
pl = leg("SELECT ID_CLIENTE, DT_PEDIDO ts_local FROM PEDIDOS")
pl["ts_utc"] = pl.ts_local + pd.Timedelta(hours=3)  # se o naive fosse lido como local e levado a UTC
rll = rotulos(pl, "ID_CLIENTE", "ts_local")
rlu = rotulos(pl, "ID_CLIENTE", "ts_utc")
popl = rll.index[(rll.n_hist > 0) | (rlu.n_hist > 0)]
muda_l = int((rll.loc[popl, "alvo"] != rlu.loc[popl, "alvo"]).sum())
num["d.depois.fuso.ecommerce.clientes_populacao"] = len(pop)
num["d.depois.fuso.ecommerce.clientes_rotulo_muda"] = muda_e
num["d.depois.fuso.ecommerce.clientes_contagem_hist_muda"] = muda_hist_e
num["d.depois.fuso.legado.clientes_populacao"] = len(popl)
num["d.depois.fuso.legado.clientes_rotulo_muda"] = muda_l
troca = int(tab_fz.legado_troca_lado.sum() + tab_fz.ecommerce_troca_lado.sum())
reg2("fuso_pedidos", "Pedidos que trocam de lado de uma fronteira (corte ou fim do alvo) conforme o fuso",
     int(tab_fz.ecommerce_troca_lado.sum()), troca, n_pedidos,
     "só importa quando datas sem fuso (legado) e com fuso (e-commerce) são postas na mesma régua")
reg2("fuso_rotulo", "Clientes cujo rótulo do alvo muda com a leitura do fuso",
     muda_e, muda_e + muda_l, len(pop) + len(popl),
     "o rótulo é calculado sobre a base integrada; a escolha do fuso é uma decisão de integração")

# ------------------------------------- histórico dividido entre os dois sistemas
ped_l = leg("""SELECT c.CPF cpf_raw, p.DT_PEDIDO ts FROM PEDIDOS p JOIN CLIENTES c ON c.ID_CLIENTE = p.ID_CLIENTE""")
ped_e = ecom(f"""SELECT c.tax_id cpf_raw, p.placed_at AT TIME ZONE '{FUSO_LOCAL}' ts
                 FROM shop.orders p JOIN shop.customer c ON c.customer_id = p.customer_id""")
ped_l["cpf"] = so_digitos(ped_l.cpf_raw)
ped_e["cpf"] = so_digitos(ped_e.cpf_raw)
ped_l = ped_l[ped_l.cpf.isin(inter)]
ped_e = ped_e[ped_e.cpf.isin(inter)]
gl = rotulos(ped_l, "cpf", "ts")
ge = rotulos(ped_e, "cpf", "ts")
both = gl.join(ge, lsuffix="_l", rsuffix="_e", how="outer").infer_objects().fillna({"n_hist_l": 0, "n_hist_e": 0,
                                                                    "alvo_l": False, "alvo_e": False})
both["alvo_l"] = both.alvo_l.astype(bool)
both["alvo_e"] = both.alvo_e.astype(bool)
both["dividido"] = (both.n_hist_l > 0) & (both.n_hist_e > 0)
both["integrado"] = both.alvo_l | both.alvo_e
pop_b = both[(both.n_hist_l > 0) | (both.n_hist_e > 0)]
num["d.depois.historico.pessoas_cpf_comum"] = len(inter)
num["d.depois.historico.pessoas_com_historico"] = len(pop_b)
num["d.depois.historico.dividido"] = int(pop_b.dividido.sum())
num["d.depois.historico.dividido_pct"] = pct(pop_b.dividido.sum(), len(pop_b))
# Sem integração cada pessoa vira até duas linhas; conta-se em quantas pessoas
# alguma dessas linhas teria rótulo diferente do rótulo integrado.
errado_l = (pop_b.n_hist_l > 0) & (pop_b.alvo_l != pop_b.integrado)
errado_e = (pop_b.n_hist_e > 0) & (pop_b.alvo_e != pop_b.integrado)
num["d.depois.historico.rotulo_muda_pessoas"] = int((errado_l | errado_e).sum())
num["d.depois.historico.rotulo_muda_pessoas_pct"] = pct((errado_l | errado_e).sum(), len(pop_b))
num["d.depois.historico.linhas_abt_duplicadas"] = int(pop_b.dividido.sum())
num["d.depois.historico.pedidos_hist_medio_integrado"] = round(float((pop_b.n_hist_l + pop_b.n_hist_e).mean()), 2)
num["d.depois.historico.pedidos_hist_medio_so_legado"] = round(float(pop_b.loc[pop_b.n_hist_l > 0, "n_hist_l"].mean()), 2)
num["d.depois.historico.pedidos_hist_medio_so_ecommerce"] = round(float(pop_b.loc[pop_b.n_hist_e > 0, "n_hist_e"].mean()), 2)
reg2("historico_dividido", "Clientes (CPF comum) com compras anteriores ao corte nos dois sistemas",
     pop_b.dividido.sum(), pop_b.dividido.sum() + sup_extra, len(pop_b) + sup_extra,
     "cada sistema vê só metade do histórico; a contagem de compras e o rótulo da ABT mudam ao unificar")
reg2("historico_rotulo", "Clientes (CPF comum) cujo rótulo difere entre a visão de um sistema e a integrada",
     int((errado_l | errado_e).sum()), int((errado_l | errado_e).sum()) + sup_extra, len(pop_b) + sup_extra,
     "o alvo 'comprou de novo' pode estar no outro sistema")

tab_depois = pd.DataFrame(depois, columns=["anomalia", "inferior", "superior", "base",
                                           "inferior_pct", "superior_pct", "por_que_so_depois"])
salvar_csv(tab_depois, "d05_depois.csv")
rel.secao("Grupo 2 — só depois da integração")
rel.tabela(tab_depois)
rel.texto("\nPedidos perto das fronteiras (hora local; 'troca_lado' = data local D e data UTC D+1):\n")
rel.tabela(tab_fz)
rel.texto(f"\nRótulo do alvo, e-commerce, local × UTC: muda para {muda_e} de {len(pop)} clientes. "
          f"Legado, naive como local × deslocado +3 h: muda para {muda_l} de {len(popl)}.")

registrar(num)
rel.gravar()
print(tab_agora.to_string(index=False))
print(tab_depois.drop(columns="por_que_so_depois").to_string(index=False))
print(tab_fz.to_string(index=False))
