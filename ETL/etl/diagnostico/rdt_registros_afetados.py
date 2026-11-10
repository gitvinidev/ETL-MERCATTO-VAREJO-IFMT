# -*- coding: utf-8 -*-
"""Números do item (e) das fichas do RDT: registros afetados por cada decisão.

Todo número de docs/RDT.md que descreve uma decisão sai daqui, de
`saida/rdt/registros_afetados.json`. Lê a camada stg (cópia fiel das origens),
a camada cnf (conformada) e, nas fichas da etapa 3, o esquema dw.
Contagens sempre sobre tabelas inteiras, no SQL (regra 6 do CLAUDE.md).

    docker compose exec etl python -m diagnostico.rdt_registros_afetados
"""

import json
import os
import sys
from decimal import Decimal

import pandas as pd
from sqlalchemy import text

from config import DATA_CORTE, DATA_FIM_ALVO, DIR_SAIDA, eng_dw, eng_mysql, eng_origem
from .comum import normaliza_texto, pct

DIR_RDT = os.path.join(DIR_SAIDA, "rdt")
os.makedirs(DIR_RDT, exist_ok=True)
FUSO = "America/Sao_Paulo"

dw = eng_dw()
R = {}                                                  # chave -> valor


def q(sql, **p):
    with dw.connect() as cx:
        return cx.execute(text(sql), p).scalar()


def df(sql):
    return pd.read_sql(text(sql), dw)


def put(chave, valor, base=None):
    """Grava `chave` e, se houver base, `chave_pct` (percentual da base)."""
    if isinstance(valor, Decimal):
        valor = int(valor) if valor == valor.to_integral_value() else float(valor)
    R[chave] = valor
    if base:
        R[chave + "_pct"] = pct(valor, base)


def existe(tabela):
    return q("SELECT to_regclass(:t) IS NOT NULL", t=tabela)


# ---------------------------------------------------------------- tamanhos
N_CLI_L = q("SELECT COUNT(*) FROM stg.legado_clientes")
N_CLI_E = q("SELECT COUNT(*) FROM stg.ecommerce_customer")
N_PED_L = q("SELECT COUNT(*) FROM stg.legado_pedidos")
N_PED_E = q("SELECT COUNT(*) FROM stg.ecommerce_orders")
N_PED = N_PED_L + N_PED_E
N_ITEM_L = q("SELECT COUNT(*) FROM stg.legado_itens_pedido")
N_ITEM_E = q("SELECT COUNT(*) FROM stg.ecommerce_order_item")
N_SAC = q("SELECT COUNT(*) FROM stg.sac_atendimentos")
N_AVAL = q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace")
for k, v in dict(clientes_legado=N_CLI_L, clientes_ecom=N_CLI_E, pedidos_legado=N_PED_L,
                 pedidos_ecom=N_PED_E, pedidos=N_PED, itens_legado=N_ITEM_L,
                 itens_ecom=N_ITEM_E, sac=N_SAC, avaliacoes=N_AVAL).items():
    put(f"base.{k}", v)

# ===================================================================== RDT-01
tot = q("SELECT SUM(linhas_stg) FROM stg.extracao_contagem")
put("rdt01.registros_carregados", tot)
LIMITE_PERFILAMENTO = 200_000       # LIMIT do 00_perfilamento.py
fora = df("SELECT tabela, linhas_stg FROM stg.extracao_contagem")
fora = fora[fora.tabela.isin(["ITENS_PEDIDO", "orders", "order_item", "PEDIDOS"])]
ft = (fora.linhas_stg - LIMITE_PERFILAMENTO).clip(lower=0)
put("rdt01.registros_fora_da_amostra_do_perfilamento", int(ft.sum()), int(tot))
for t, n in zip(fora.tabela, ft):
    put(f"rdt01.fora_da_amostra.{t}", int(n))
col_upd = 0
with eng_mysql().connect() as cx:
    col_upd += cx.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='loja_legado' "
        "AND column_name REGEXP 'UPDAT|MODIF|ATUALIZ|ALTERAC|VERSAO'")).scalar()
with eng_origem().connect() as cx:
    col_upd += cx.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='shop' "
        "AND column_name ~* 'updat|modif|atualiz|alterac|version'")).scalar()
put("rdt01.colunas_de_atualizacao_nas_origens", col_upd)

# ===================================================================== RDT-02
put("rdt02.registros_cliente", N_CLI_L + N_CLI_E)
pessoas = q("SELECT COUNT(*) FROM cnf.cliente")
put("rdt02.pessoas", pessoas, N_CLI_L + N_CLI_E)
put("rdt02.registros_unidos_em_outra_pessoa", N_CLI_L + N_CLI_E - pessoas, N_CLI_L + N_CLI_E)
for o, n in df("SELECT origem_unificacao o, COUNT(*) n FROM cnf.cliente GROUP BY 1").values:
    put(f"rdt02.pessoas.{o}", n, pessoas)
for r, n in df("SELECT COALESCE(regra_pareamento,'(sem regra)') r, COUNT(*) n FROM cnf.cliente GROUP BY 1").values:
    put(f"rdt02.pessoas_por_regra.{r}", n, pessoas)
put("rdt02.pessoas_com_cpf_valido", q("SELECT COUNT(*) FROM cnf.cliente WHERE cpf_valido"), pessoas)
put("rdt02.pessoas_com_cpf_invalido", q("SELECT COUNT(*) FROM cnf.cliente WHERE cpf_valido = false"), pessoas)
put("rdt02.pessoas_sem_cpf", q("SELECT COUNT(*) FROM cnf.cliente WHERE cpf_normalizado IS NULL"), pessoas)
put("rdt02.pessoas_com_cpf_em_colisao", q("SELECT COUNT(*) FROM cnf.cliente WHERE cpf_conflito"), pessoas)
put("rdt02.cpfs_em_colisao", q("""SELECT COUNT(*) FROM (SELECT cpf_digitos FROM cnf.cliente_cpf
                                  WHERE cpf_valido GROUP BY 1 HAVING COUNT(DISTINCT cliente_key) > 1) x"""))

# validação das regras alternativas (nome + UF), em pandas sobre as tabelas inteiras
sys.path.insert(0, "/etl")
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("t2", "/etl/02_transformacao.py")
t2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2)

L = df("SELECT id_cliente id, nome, cpf, email, telefone, cidade, uf FROM stg.legado_clientes")
E = df("SELECT customer_id id, full_name nome, tax_id cpf, city cidade, state uf FROM stg.ecommerce_customer")
for D in (L, E):
    D["cpfd"] = D.cpf.fillna("").map(t2.so_digitos)
    D["ok"] = D.cpfd.map(t2.cpf_valido)
    D["nn"] = D.nome.map(t2.normaliza_nome)
    D["cid"] = D.cidade.fillna("").map(t2.normaliza_nome)

# CPF de 11 dígitos igual nos dois cadastros, qualquer validade
m = L[L.cpfd.str.len() == 11].merge(E[E.cpfd.str.len() == 11], on="cpfd", suffixes=("_l", "_e"))
inval = m[(m.ok_l == False) & (m.ok_e == False)]                     # noqa: E712
put("rdt02.pares_cpf_invalido_igual", len(inval))
put("rdt02.pares_cpf_invalido_igual_nome_e_uf_concordam",
    int(((inval.nn_l == inval.nn_e) & (inval.uf_l == inval.uf_e)).sum()))
vv = m[(m.ok_l == True) & (m.ok_e == True)]                          # noqa: E712
put("rdt02.pares_cpf_valido_igual", len(vv))
put("rdt02.pares_cpf_valido_igual_nome_discorda", int((vv.nn_l != vv.nn_e).sum()))

# nome + UF entre registros que têm CPF válido dos dois lados: serve de pareamento?
Lv = L[L.ok == True].drop_duplicates("cpfd")                         # noqa: E712
Ev = E[E.ok == True].drop_duplicates("cpfd")
for rotulo, chave in (("nome_uf", ["nn", "uf"]), ("nome_uf_cidade", ["nn", "uf", "cid"])):
    a = Lv.copy()
    b = Ev.copy()
    a["nl"] = a.groupby(chave).id.transform("size")
    b["ne"] = b.groupby(chave).id.transform("size")
    p = a.merge(b, on=chave, suffixes=("_l", "_e"))
    p["mesmo_cpf"] = p.cpfd_l == p.cpfd_e
    put(f"rdt02.valid_{rotulo}.pares_candidatos", len(p))
    put(f"rdt02.valid_{rotulo}.pares_cpf_igual", int(p.mesmo_cpf.sum()))
    put(f"rdt02.valid_{rotulo}.pares_falsos", int((~p.mesmo_cpf).sum()))
    put(f"rdt02.valid_{rotulo}.precisao_pct", pct(p.mesmo_cpf.sum(), len(p)))
    put(f"rdt02.valid_{rotulo}.chaves_unicas_nos_dois_lados", int(((p.nl == 1) & (p.ne == 1)).sum()))
# registros que a regra por nome+UF alcançaria além do CPF (sem CPF válido em ao menos um lado)
Lsv, Esv = L[L.ok != True], E[E.ok != True]
adic = (Lsv.merge(E, on=["nn", "uf"]).shape[0] + L[L.ok == True].merge(Esv, on=["nn", "uf"]).shape[0])
put("rdt02.pares_extras_por_nome_uf_sem_cpf_valido", adic)

# ===================================================================== RDT-03
leg = df("""SELECT c.id_cliente, c.email, c.nome, c.telefone, c.cpf, p.papel, p.cliente_key
              FROM stg.legado_clientes c
              JOIN cnf.cliente_ponte p ON p.sistema_origem='LEGADO' AND p.id_origem=c.id_cliente""")
leg["nn"] = leg.nome.map(t2.normaliza_nome)
leg["tel"] = leg.telefone.map(t2.so_digitos)
leg["cpfd"] = leg.cpf.fillna("").map(t2.so_digitos)
leg["ok"] = leg.cpfd.map(t2.cpf_valido)
g = leg.groupby(["email", "nn", "tel"]).filter(lambda x: len(x) > 1)
grupos = g.groupby(["email", "nn", "tel"])
put("rdt03.pares_duplicados", grupos.ngroups, N_CLI_L)
put("rdt03.registros_em_pares", len(g), N_CLI_L)
put("rdt03.pares_com_mesmo_cpf_valido", int(sum(1 for _, x in grupos
                                                if (x.ok == True).all() and x.cpfd.nunique() == 1)))  # noqa: E712
put("rdt03.pares_com_cpf_ausente_ou_invalido_em_um_lado", int(sum(1 for _, x in grupos
                                                                  if not (x.ok == True).all())))     # noqa: E712
ped = df("SELECT id_cliente, COUNT(*) n FROM stg.legado_pedidos GROUP BY 1").set_index("id_cliente").n
g = g.assign(n=g.id_cliente.map(ped).fillna(0))
put("rdt03.pares_em_que_os_dois_tem_pedidos", int(sum(1 for _, x in g.groupby(["email", "nn", "tel"])
                                                      if (x.n > 0).all())))
abs_ = leg[leg.papel == "ABSORVIDO"]
put("rdt03.registros_absorvidos_no_legado", len(abs_), N_CLI_L)
put("rdt03.pedidos_reatribuidos_ao_sobrevivente",
    q("""SELECT COUNT(*) FROM stg.legado_pedidos p JOIN cnf.cliente_ponte c
          ON c.sistema_origem='LEGADO' AND c.id_origem=p.id_cliente WHERE c.papel='ABSORVIDO'"""), N_PED_L)

# ===================================================================== RDT-04
mt = df("""SELECT sistema_origem s, status_origem so, status_conformado sc,
                  COALESCE(motivo_cancelamento,'(nulo)') m, COUNT(*) n
             FROM cnf.pedido GROUP BY 1,2,3,4 ORDER BY 1,2""")
for s, so, sc, m, n in mt.values:
    put(f"rdt04.celula.{s}.{so}.{sc}.{m}", n, N_PED_L if s == "LEGADO" else N_PED_E)
put("rdt04.cancelados_total", q("SELECT COUNT(*) FROM cnf.pedido WHERE status_conformado='CANCELADO'"), N_PED)
put("rdt04.cancelados_legado_sem_motivo",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE sistema_origem='LEGADO' AND status_conformado='CANCELADO'"), N_PED_L)
put("rdt04.recusa_pagamento_ecom",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE motivo_cancelamento='PAGAMENTO_RECUSADO'"), N_PED_E)
put("rdt04.pedidos_que_contam_como_compra",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE status_conformado <> 'CANCELADO'"), N_PED)
put("rdt04.pedidos_na_janela_do_alvo",
    q(f"SELECT COUNT(*) FROM cnf.pedido WHERE data_pedido > DATE '{DATA_CORTE}' AND data_pedido <= DATE '{DATA_FIM_ALVO}'"))
put("rdt04.pedidos_cancelados_na_janela_do_alvo",
    q(f"""SELECT COUNT(*) FROM cnf.pedido WHERE status_conformado='CANCELADO'
           AND data_pedido > DATE '{DATA_CORTE}' AND data_pedido <= DATE '{DATA_FIM_ALVO}'"""))
# efeito sobre o alvo: clientes cujo rótulo muda se cancelados contassem como compra
alvo = df(f"""
    WITH base AS (SELECT DISTINCT cliente_key FROM cnf.pedido WHERE data_pedido <= DATE '{DATA_CORTE}'),
         efet AS (SELECT DISTINCT cliente_key FROM cnf.pedido
                   WHERE data_pedido > DATE '{DATA_CORTE}' AND data_pedido <= DATE '{DATA_FIM_ALVO}'
                     AND status_conformado <> 'CANCELADO'),
         todos AS (SELECT DISTINCT cliente_key FROM cnf.pedido
                   WHERE data_pedido > DATE '{DATA_CORTE}' AND data_pedido <= DATE '{DATA_FIM_ALVO}')
    SELECT (SELECT COUNT(*) FROM base) base,
           (SELECT COUNT(*) FROM base b JOIN efet USING (cliente_key)) pos_efetivo,
           (SELECT COUNT(*) FROM base b JOIN todos USING (cliente_key)) pos_qualquer""")
b, pe, pq = (int(x) for x in alvo.iloc[0])
put("rdt04.alvo.clientes_na_base", b)
put("rdt04.alvo.positivos_status_efetivo", pe, b)
put("rdt04.alvo.positivos_se_cancelado_contasse", pq, b)
put("rdt04.alvo.clientes_cujo_rotulo_muda", pq - pe, b)

# ===================================================================== RDT-05
put("rdt05.pedidos_legado_valor_total_igual_a_formula",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE sistema_origem='LEGADO' AND ABS(valor_total-total_origem_conformado)<=0.01"),
    N_PED_L)
put("rdt05.pedidos_ecom_valor_total_igual_a_total_amount_mais_frete",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE sistema_origem='ECOM' AND ABS(valor_total-total_origem_conformado)<=0.01"),
    N_PED_E)
put("rdt05.pedidos_ecom_em_que_total_amount_cru_difere_do_conformado",
    q("SELECT COUNT(*) FROM stg.ecommerce_orders WHERE freight_amount <> 0"), N_PED_E)
put("rdt05.soma_frete_ecom_acrescentada_ao_total",
    q("SELECT SUM(freight_amount) FROM stg.ecommerce_orders"))
put("rdt05.soma_valor_total_legado_origem", q("SELECT SUM(valor_total) FROM stg.legado_pedidos"))
put("rdt05.soma_total_amount_ecom_cru", q("SELECT SUM(total_amount) FROM stg.ecommerce_orders"))
put("rdt05.soma_total_amount_mais_frete_ecom_origem",
    q("SELECT SUM(total_amount + freight_amount) FROM stg.ecommerce_orders"))
put("rdt05.soma_frete_legado_embutido_no_valor_total", q("SELECT SUM(valor_frete) FROM stg.legado_pedidos"))
put("rdt05.pedidos_com_valor_total_divergente_da_origem",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE ABS(valor_total-total_origem_conformado) > 0.01"), N_PED)

# ===================================================================== RDT-06
put("rdt06.linhas_desconto_menos_1", q("SELECT COUNT(*) FROM cnf.item WHERE desconto_sentinela"), N_ITEM_L)
put("rdt06.pedidos_com_desconto_menos_1",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE linhas_desconto_sentinela > 0"), N_PED_L)
put("rdt06.valor_que_o_sentinela_somaria_se_fosse_desconto_real_negativo",
    q("SELECT -SUM(CASE WHEN vl_desconto = -1 THEN vl_desconto END) FROM stg.legado_itens_pedido"))
for s, n in df("SELECT sistema_origem s, COUNT(*) n FROM cnf.pedido WHERE frete_negativo GROUP BY 1").values:
    put(f"rdt06.fretes_negativos.{s}", n, N_PED_L if s == "LEGADO" else N_PED_E)
    put(f"rdt06.soma_fretes_negativos.{s}",
        q("SELECT SUM(valor_frete) FROM cnf.pedido WHERE frete_negativo AND sistema_origem=:s", s=s))
put("rdt06.fretes_negativos_total", q("SELECT COUNT(*) FROM cnf.pedido WHERE frete_negativo"), N_PED)
put("rdt06.pedidos_com_valor_total_negativo", q("SELECT COUNT(*) FROM cnf.pedido WHERE valor_total < 0"), N_PED)
put("rdt06.fretes_negativos_em_pedidos_cancelados",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE frete_negativo AND status_conformado='CANCELADO'"))
# preços: 10x a mediana da categoria
pe = df("""WITH m AS (SELECT category_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY list_price) med
                        FROM stg.ecommerce_product GROUP BY 1)
           SELECT p.product_id, p.list_price/m.med r FROM stg.ecommerce_product p JOIN m USING (category_id)""")
pl = df("""WITH m AS (SELECT lower(categoria) c, percentile_cont(0.5) WITHIN GROUP (ORDER BY preco_tabela) med
                        FROM stg.legado_produtos GROUP BY 1)
           SELECT p.id_produto, p.preco_tabela/m.med r FROM stg.legado_produtos p JOIN m ON m.c = lower(p.categoria)""")
put("rdt06.precos_lista_10x_mediana_categoria.ecom", int((pe.r >= 10).sum()), len(pe))
put("rdt06.precos_lista_10x_mediana_categoria.legado", int((pl.r >= 10).sum()), len(pl))
put("rdt06.maior_razao_preco_lista_mediana_categoria", round(max(pe.r.max(), pl.r.max()), 2))
put("rdt06.itens_vendidos_a_10x_ou_mais_do_preco_de_tabela",
    q("""SELECT (SELECT COUNT(*) FROM stg.legado_itens_pedido i JOIN stg.legado_produtos p USING (id_produto)
                 WHERE i.vl_unitario >= 10 * p.preco_tabela)
              + (SELECT COUNT(*) FROM stg.ecommerce_order_item i JOIN stg.ecommerce_product p USING (product_id)
                 WHERE i.unit_price >= 10 * p.list_price)"""), N_ITEM_L + N_ITEM_E)
put("rdt06.maior_razao_preco_item_preco_tabela",
    q("""SELECT GREATEST((SELECT MAX(i.vl_unitario / p.preco_tabela) FROM stg.legado_itens_pedido i
                          JOIN stg.legado_produtos p USING (id_produto)),
                         (SELECT MAX(i.unit_price / p.list_price) FROM stg.ecommerce_order_item i
                          JOIN stg.ecommerce_product p USING (product_id)))"""))

# ===================================================================== RDT-07
n_prod_l = q("SELECT COUNT(*) FROM cnf.produto WHERE origem='LEGADO'")
n_prod_e = q("SELECT COUNT(*) FROM cnf.produto WHERE origem='ECOM'")
put("rdt07.produtos_legado", n_prod_l)
put("rdt07.produtos_ecom", n_prod_e)
for c, n in df("""SELECT classe_mapeamento c, COUNT(*) n FROM cnf.produto WHERE origem='LEGADO' GROUP BY 1""").values:
    put(f"rdt07.produtos_legado.{c}", n, n_prod_l)
rotulos = df("""SELECT classe_mapeamento c, categoria_origem FROM cnf.produto WHERE origem='LEGADO'""")
rotulos["norm"] = rotulos.categoria_origem.fillna("").map(normaliza_texto)
for c, g in rotulos.groupby("c"):
    put(f"rdt07.rotulos_distintos_por_classe.{c}", g.norm.nunique())
for c, n, v in df("""SELECT p.classe_mapeamento, COUNT(*), SUM(i.valor_linha)
                       FROM cnf.item i JOIN cnf.produto p
                         ON (i.sistema_origem='LEGADO' AND p.origem='LEGADO' AND p.id_legado=i.id_produto_origem)
                      WHERE i.pedido_existe GROUP BY 1""").values:
    put(f"rdt07.itens_vendidos_do_legado.{c}", n, N_ITEM_L)
    put(f"rdt07.valor_vendido_do_legado.{c}", v)
put("rdt07.produtos_sem_categoria_nivel1_no_dw", q("SELECT COUNT(*) FROM cnf.produto WHERE categoria_nivel1 IS NULL"),
    n_prod_l + n_prod_e)
put("rdt07.produtos_com_descricao_igual_nos_dois_sistemas",
    q("""SELECT COUNT(*) FROM stg.legado_produtos l JOIN stg.ecommerce_product e
          ON lower(l.descricao) = lower(e.title)"""), n_prod_l)

# ===================================================================== RDT-08
leg_ped_nao_ent = q("SELECT COUNT(*) FROM cnf.pedido WHERE status_conformado <> 'ENTREGUE' AND data_entrega IS NULL "
                    "AND NOT entrega_sem_data AND NOT entrega_anterior_pedido")
put("rdt08.entrega_nula_nao_aplicavel_pedido_nao_entregue", leg_ped_nao_ent, N_PED)
put("rdt08.entrega_1900_01_01.legado", q("SELECT COUNT(*) FROM cnf.pedido WHERE entrega_sem_data"), N_PED_L)
put("rdt08.entrega_1900_01_01_com_status_entregue",
    q("SELECT COUNT(*) FROM cnf.pedido WHERE entrega_sem_data AND status_conformado='ENTREGUE'"))
for s, n in df("SELECT sistema_origem s, COUNT(*) n FROM cnf.pedido WHERE entrega_anterior_pedido GROUP BY 1").values:
    put(f"rdt08.entrega_anterior_ao_pedido.{s}", n, N_PED_L if s == "LEGADO" else N_PED_E)
put("rdt08.entrega_anterior_ao_pedido.total", q("SELECT COUNT(*) FROM cnf.pedido WHERE entrega_anterior_pedido"), N_PED)
put("rdt08.cidade_na.registros_legado", q("SELECT COUNT(*) FROM stg.legado_clientes WHERE cidade = 'N/A'"), N_CLI_L)
put("rdt08.cpf_ausente.legado", q("SELECT COUNT(*) FROM stg.legado_clientes WHERE regexp_replace(cpf,'\\D','','g') = ''"), N_CLI_L)
put("rdt08.cpf_ausente.ecom", q("SELECT COUNT(*) FROM stg.ecommerce_customer WHERE COALESCE(tax_id,'') = ''"), N_CLI_E)
put("rdt08.cpf_dv_invalido.legado", int((L.ok == False).sum()), N_CLI_L)                           # noqa: E712
put("rdt08.cpf_dv_invalido.ecom", int((E.ok == False).sum()), N_CLI_E)                             # noqa: E712
put("rdt08.sac.nota_zero", q("SELECT COUNT(*) FROM cnf.atendimento WHERE nota_zero"), q("SELECT COUNT(*) FROM cnf.atendimento"))
put("rdt08.sac.nota_vazia", q("SELECT COUNT(*) FROM stg.sac_atendimentos WHERE nota_satisfacao = ''"), N_SAC)
put("rdt08.sac.nota_zero_linhas_stg", q("SELECT COUNT(*) FROM stg.sac_atendimentos WHERE nota_satisfacao = '0'"), N_SAC)
put("rdt08.sac.data_fechamento_vazia", q("SELECT COUNT(*) FROM stg.sac_atendimentos WHERE data_fechamento = ''"), N_SAC)
put("rdt08.sac.data_fechamento_vazia_com_horas_de_resolucao",
    q("SELECT COUNT(*) FROM stg.sac_atendimentos WHERE data_fechamento = '' AND tempo_resolucao_horas <> ''"))
put("rdt08.sac.horas_de_resolucao_negativas", q("SELECT COUNT(*) FROM stg.sac_atendimentos WHERE tempo_resolucao_horas LIKE '-%'"), N_SAC)
put("rdt08.avaliacao.rating_ausente", q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE rating IS NULL"), N_AVAL)
put("rdt08.avaliacao.rating_como_texto",
    q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE rating IS NOT NULL AND NOT COALESCE(_tipos_json ? 'rating', false)"), N_AVAL)
put("rdt08.avaliacao.rating_texto_nao_numerico",
    q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE rating IS NOT NULL AND rating !~ '^[0-9]+$'"))
put("rdt08.avaliacao.verified_purchase_ausente",
    q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE verified_purchase IS NULL"), N_AVAL)
put("rdt08.avaliacao.helpful_votes_ausente",
    q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE helpful_votes IS NULL"), N_AVAL)
put("rdt08.avaliacao.linhas_com_alguma_chave_ausente",
    q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE _chaves_ausentes IS NOT NULL"), N_AVAL)
put("rdt08.avaliacao.title_ausente", q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE title IS NULL"), N_AVAL)
put("rdt08.avaliacao.comment_ausente", q("SELECT COUNT(*) FROM stg.avaliacoes_marketplace WHERE comment IS NULL"), N_AVAL)

# ===================================================================== RDT-09
ecom_dia = df(f"""SELECT COUNT(*) FILTER (WHERE (placed_at AT TIME ZONE '{FUSO}')::date
                                           <> (placed_at AT TIME ZONE 'UTC')::date) dif FROM stg.ecommerce_orders""")
put("rdt09.pedidos_ecom_cuja_data_local_difere_da_data_utc", int(ecom_dia.dif[0]), N_PED_E)
put("rdt09.legado_dt_pedido_que_mudaria_de_dia_se_fosse_levado_a_utc",
    q("SELECT COUNT(*) FROM stg.legado_pedidos WHERE (dt_pedido + interval '3 hours')::date <> dt_pedido::date"), N_PED_L)
# régua alternativa: tudo em UTC (legado = local + 3h; e-commerce = instante em UTC)
pu = df(f"""
    SELECT 'ECOM' s, (placed_at AT TIME ZONE '{FUSO}')::date d_local, (placed_at AT TIME ZONE 'UTC')::date d_utc,
           customer_id id_cli, status s_conf FROM stg.ecommerce_orders
    UNION ALL
    SELECT 'LEGADO', dt_pedido::date, (dt_pedido + interval '3 hours')::date, id_cliente, status FROM stg.legado_pedidos""")
sc = df("SELECT sistema, status_origem, status_conformado FROM cnf.status_map")
pu["conta"] = True
ped = df("SELECT sistema_origem s, id_num id, cliente_key, data_pedido, status_conformado FROM cnf.pedido")
# usa cnf.pedido (que tem cliente_key) e recalcula a data pela régua UTC
pu2 = df(f"""
    SELECT p.cliente_key, p.status_conformado, p.data_pedido d_local,
           CASE WHEN p.sistema_origem='ECOM'
                THEN (o.placed_at AT TIME ZONE 'UTC')::date
                ELSE (l.dt_pedido + interval '3 hours')::date END d_utc
      FROM cnf.pedido p
      LEFT JOIN stg.ecommerce_orders o ON p.sistema_origem='ECOM' AND o.order_id = p.id_num
      LEFT JOIN stg.legado_pedidos   l ON p.sistema_origem='LEGADO' AND l.id_pedido = p.id_num""")
C, F = pd.Timestamp(DATA_CORTE).date(), pd.Timestamp(DATA_FIM_ALVO).date()
lado = lambda d: ((d <= C).astype(int) * 1 + ((d > C) & (d <= F)).astype(int) * 2)       # noqa: E731
pu2["lado_local"], pu2["lado_utc"] = lado(pu2.d_local), lado(pu2.d_utc)
put("rdt09.pedidos_que_trocam_de_lado_do_corte_ou_do_fim_do_alvo",
    int((pu2.lado_local != pu2.lado_utc).sum()), N_PED)
put("rdt09.pedidos_que_trocam_de_lado_do_corte", int(((pu2.d_local <= C) != (pu2.d_utc <= C)).sum()))
put("rdt09.pedidos_que_trocam_de_lado_do_fim_do_alvo", int(((pu2.d_local <= F) != (pu2.d_utc <= F)).sum()))


def rotulos_alvo(d):
    base = set(pu2.cliente_key[d <= C])
    pos = set(pu2.cliente_key[(d > C) & (d <= F) & (pu2.status_conformado != "CANCELADO")])
    return base, pos


b1, p1 = rotulos_alvo(pu2.d_local)
b2, p2 = rotulos_alvo(pu2.d_utc)
muda = len((b1 ^ b2)) + len(((p1 & b1) ^ (p2 & b2)) & (b1 & b2))
put("rdt09.clientes_na_base_que_entram_ou_saem_com_a_regua_utc", len(b1 ^ b2), len(b1))
put("rdt09.clientes_cujo_rotulo_do_alvo_muda_com_a_regua_utc", len(((p1 & b1) ^ (p2 & b2)) & (b1 & b2)), len(b1))
put("rdt09.avaliacoes_sem_offset", q("SELECT COUNT(*) FROM cnf.avaliacao WHERE offset_ausente"), N_AVAL)
put("rdt09.avaliacoes_com_offset", q("SELECT COUNT(*) FROM cnf.avaliacao WHERE NOT offset_ausente"), N_AVAL)
put("rdt09.avaliacoes_sem_offset_cuja_data_mudaria_se_fossem_utc",
    q("""SELECT COUNT(*) FROM cnf.avaliacao WHERE offset_ausente
          AND (enviada_em + interval '3 hours')::date <> enviada_em::date"""))
put("rdt09.avaliacoes_offsets_explicitos_distintos",
    q("SELECT COUNT(DISTINCT substr(submitted_at, 20)) FROM stg.avaliacoes_marketplace WHERE length(submitted_at) > 19"))

# ===================================================================== RDT-10
for s, n in df("SELECT sistema_origem s, COUNT(*) n FROM cnf.item WHERE NOT pedido_existe GROUP BY 1").values:
    put(f"rdt10.itens_orfaos.{s}", n, N_ITEM_L if s == "LEGADO" else N_ITEM_E)
put("rdt10.itens_orfaos.total", q("SELECT COUNT(*) FROM cnf.item WHERE NOT pedido_existe"), N_ITEM_L + N_ITEM_E)
put("rdt10.valor_dos_itens_orfaos", q("SELECT SUM(valor_linha) FROM cnf.item WHERE NOT pedido_existe"))
put("rdt10.itens_orfaos_ecom_com_order_id_acima_do_maior_pedido",
    q("""SELECT COUNT(*) FROM stg.ecommerce_order_item
          WHERE order_id > (SELECT MAX(order_id) FROM stg.ecommerce_orders)"""))
put("rdt10.itens_orfaos_legado_com_id_pedido_acima_do_maior_pedido",
    q("""SELECT COUNT(*) FROM stg.legado_itens_pedido
          WHERE id_pedido > (SELECT MAX(id_pedido) FROM stg.legado_pedidos)"""))

# ===================================================================== RDT-12
put("rdt12.pedidos_sem_cliente_na_origem",
    q("""SELECT (SELECT COUNT(*) FROM stg.legado_pedidos p WHERE NOT EXISTS
                   (SELECT 1 FROM stg.legado_clientes c WHERE c.id_cliente = p.id_cliente))
              + (SELECT COUNT(*) FROM stg.ecommerce_orders p WHERE NOT EXISTS
                   (SELECT 1 FROM stg.ecommerce_customer c WHERE c.customer_id = p.customer_id))"""), N_PED)
put("rdt12.pedidos_com_id_cliente_nulo",
    q("""SELECT (SELECT COUNT(*) FROM stg.legado_pedidos WHERE id_cliente IS NULL)
              + (SELECT COUNT(*) FROM stg.ecommerce_orders WHERE customer_id IS NULL)"""), N_PED)
put("rdt12.pedidos_sem_cliente_conformado", q("SELECT COUNT(*) FROM cnf.pedido WHERE cliente_key IS NULL"), N_PED)

# ===================================================================== RDT-13
put("rdt13.sac.registros", N_SAC)
put("rdt13.sac.linhas_repetidas_removidas", q("SELECT COUNT(*) FROM stg.sac_atendimentos") - q("SELECT COUNT(*) FROM cnf.atendimento"), N_SAC)
n_at = q("SELECT COUNT(*) FROM cnf.atendimento")
put("rdt13.sac.atendimentos_conformados", n_at)
put("rdt13.sac.com_cliente_por_cpf", q("SELECT COUNT(*) FROM cnf.atendimento WHERE cliente_key IS NOT NULL"), n_at)
put("rdt13.sac.sem_cliente", q("SELECT COUNT(*) FROM cnf.atendimento WHERE cliente_key IS NULL"), n_at)
put("rdt13.sac.cpf_ambiguo_entre_pessoas", q("SELECT COUNT(*) FROM cnf.atendimento WHERE cpf_ambiguo"), n_at)
put("rdt13.sac.cpf_valido_com_cliente",
    q("SELECT COUNT(*) FROM cnf.atendimento WHERE cliente_key IS NOT NULL AND cpf_valido"), q("SELECT COUNT(*) FROM cnf.atendimento WHERE cpf_valido"))
put("rdt13.sac.cpf_invalido_com_cliente",
    q("SELECT COUNT(*) FROM cnf.atendimento WHERE cliente_key IS NOT NULL AND NOT cpf_valido"), q("SELECT COUNT(*) FROM cnf.atendimento WHERE NOT cpf_valido"))
put("rdt13.sac.pedido_declarado_existe_no_sistema_indicado",
    q("""SELECT COUNT(*) FROM cnf.atendimento a WHERE EXISTS
          (SELECT 1 FROM cnf.pedido p WHERE p.sistema_origem = a.origem_sistema
              AND p.id_num = a.id_pedido_origem::bigint)"""), n_at)
put("rdt13.sac.cpf_do_atendimento_e_o_do_dono_do_pedido_declarado",
    q("""SELECT COUNT(*) FROM cnf.atendimento a JOIN cnf.pedido p
           ON p.sistema_origem = a.origem_sistema AND p.id_num = a.id_pedido_origem::bigint
          WHERE a.cliente_key = p.cliente_key"""), n_at)
put("rdt13.sac.abertura_posterior_ao_pedido_declarado",
    q("""SELECT COUNT(*) FROM cnf.atendimento a JOIN cnf.pedido p
           ON p.sistema_origem = a.origem_sistema AND p.id_num = a.id_pedido_origem::bigint
          WHERE a.data_abertura >= p.data_pedido"""), n_at)
put("rdt13.sac.pedido_key_preenchido", 0, n_at)
n_av = q("SELECT COUNT(*) FROM cnf.avaliacao")
put("rdt13.avaliacao.registros", n_av)
put("rdt13.avaliacao.com_produto_pelo_sku", q("SELECT COUNT(*) FROM cnf.avaliacao WHERE produto_key IS NOT NULL"), n_av)
put("rdt13.avaliacao.pedido_declarado_existe",
    q("""SELECT COUNT(*) FROM cnf.avaliacao a WHERE EXISTS
          (SELECT 1 FROM cnf.pedido p WHERE p.sistema_origem = a.ref_sistema AND p.id_num = a.ref_id)"""), n_av)
put("rdt13.avaliacao.produto_avaliado_esta_nos_itens_do_pedido_declarado",
    q("""SELECT COUNT(*) FROM cnf.avaliacao a
          JOIN cnf.produto pr ON pr.produto_key = a.produto_key
          WHERE EXISTS (SELECT 1 FROM cnf.item i
                         WHERE i.id_pedido_origem = (CASE a.ref_sistema WHEN 'LEGADO' THEN 'LEG-' ELSE 'ECOM-' END) || a.ref_id
                           AND ((pr.origem = 'LEGADO' AND i.sistema_origem = 'LEGADO' AND i.id_produto_origem = pr.id_legado)
                             OR (pr.origem = 'ECOM'   AND i.sistema_origem = 'ECOM'   AND i.id_produto_origem = pr.id_ecommerce)))"""), n_av)
put("rdt13.avaliacao.enviada_antes_do_pedido_declarado",
    q("""SELECT COUNT(*) FROM cnf.avaliacao a JOIN cnf.pedido p
           ON p.sistema_origem = a.ref_sistema AND p.id_num = a.ref_id
          WHERE a.data_avaliacao < p.data_pedido"""), n_av)
put("rdt13.avaliacao.campos_de_cpf_no_ndjson", 0)
put("rdt13.avaliacao.cliente_key_preenchido", 0, n_av)

# ============================================ etapa 3: DW carregado (RDT-10 a 13)
if existe("dw.fato_pedido") and q("SELECT COUNT(*) FROM dw.fato_pedido") > 0:
    n_fp = q("SELECT COUNT(*) FROM dw.fato_pedido")
    put("rdt11.fato_pedido.linhas", n_fp, N_PED)
    for sis, n in df("SELECT sistema_origem s, COUNT(*) n FROM dw.fato_pedido GROUP BY 1").values:
        put(f"rdt11.fato_pedido.linhas.{sis}", n)
    n_fi = q("SELECT COUNT(*) FROM dw.fato_item_pedido")
    put("rdt11.fato_item.linhas", n_fi, N_ITEM_L + N_ITEM_E)
    put("rdt10.itens_no_fato", n_fi, N_ITEM_L + N_ITEM_E)
    put("rdt10.itens_na_quarentena", q("SELECT COUNT(*) FROM dw.aux_item_quarentena"), N_ITEM_L + N_ITEM_E)
    put("rdt11.pedidos_nao_efetivos_mantidos_no_fato",
        q("""SELECT COUNT(*) FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)
              WHERE s.status_conformado = 'CANCELADO'"""), n_fp)
    put("rdt11.valor_total_dos_cancelados_no_fato",
        q("""SELECT SUM(f.valor_total) FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)
              WHERE s.status_conformado = 'CANCELADO'"""))
    put("rdt11.soma_valor_total_dw", q("SELECT SUM(valor_total) FROM dw.fato_pedido"))
    put("rdt11.pedidos_com_chave_natural_repetida",
        q("""SELECT COUNT(*) FROM (SELECT 1 FROM dw.fato_pedido GROUP BY sistema_origem, id_origem
                                   HAVING COUNT(*) > 1) x"""), n_fp)
    put("rdt11.pedidos_cujo_id_numerico_existe_nos_dois_sistemas",
        q("""SELECT COUNT(*) FROM (SELECT SUBSTRING(id_origem FROM '[0-9]+$')::bigint n FROM dw.fato_pedido
                                   GROUP BY 1 HAVING COUNT(DISTINCT sistema_origem) > 1) x"""))
    put("rdt11.pedidos_distintos_se_o_sistema_fosse_ignorado",
        q("SELECT COUNT(DISTINCT SUBSTRING(id_origem FROM '[0-9]+$')::bigint) FROM dw.fato_pedido"))
    put("rdt11.itens_do_fato_cujo_pedido_e_cancelado",
        q("""SELECT COUNT(*) FROM dw.fato_item_pedido i JOIN dw.fato_pedido f USING (pedido_sk)
              JOIN dw.dim_status s USING (status_sk) WHERE s.status_conformado = 'CANCELADO'"""), n_fi)
    recon = pd.read_csv(os.path.join(DIR_SAIDA, "reconciliacao", "financeira.csv"))
    for _, r in recon.iterrows():
        put(f"rdt11.recon.{r.sistema}.soma_dw", round(float(r.soma_dw), 2))
        put(f"rdt11.recon.{r.sistema}.soma_origem", round(float(r.soma_origem), 2))
        put(f"rdt11.recon.{r.sistema}.diferenca_absoluta", round(float(r.diferenca_absoluta), 2))
        put(f"rdt11.recon.{r.sistema}.diferenca_relativa_pct", round(100 * float(r.diferenca_relativa), 6))
        put(f"rdt11.recon.{r.sistema}.aprovado", int(r.aprovado == "sim"))
    detalhe = pd.read_csv(os.path.join(DIR_SAIDA, "reconciliacao", "financeira_detalhe.csv")).set_index("medida").valor
    put("rdt11.recon.ECOM.diferenca_falsa_contra_total_amount_cru",
        round(float(detalhe["ECOM: diferença DW - total_amount cru (falsa)"]), 2))
    # RDT-12: ligação por cliente
    put("rdt12.fato_pedido_com_cliente_sk_orfao",
        q("""SELECT COUNT(*) FROM dw.fato_pedido f LEFT JOIN dw.dim_cliente c USING (cliente_sk)
              WHERE c.cliente_sk IS NULL"""), n_fp)
    put("rdt12.pedidos_legado_cujo_id_cliente_existe_tambem_no_ecommerce",
        q("""SELECT COUNT(*) FROM stg.legado_pedidos p WHERE EXISTS
              (SELECT 1 FROM stg.ecommerce_customer c WHERE c.customer_id = p.id_cliente)"""), N_PED_L)
    put("rdt12.pedidos_ecom_cujo_id_cliente_existe_tambem_no_legado",
        q("""SELECT COUNT(*) FROM stg.ecommerce_orders p WHERE EXISTS
              (SELECT 1 FROM stg.legado_clientes c WHERE c.id_cliente = p.customer_id)"""), N_PED_E)
    put("rdt12.pedidos_cujo_cliente_foi_fundido_com_outro_registro",
        q("""SELECT COUNT(*) FROM cnf.pedido p JOIN cnf.cliente c USING (cliente_key)
              WHERE c.n_reg_legado + c.n_reg_ecom > 1"""), n_fp)
    put("rdt12.cliente_desconhecido_criado", q("SELECT COUNT(*) FROM dw.dim_cliente WHERE nome_padronizado = 'DESCONHECIDO'"))
    put("rdt13.dw.fato_atendimento.linhas", q("SELECT COUNT(*) FROM dw.fato_atendimento"))
    put("rdt13.dw.fato_atendimento.sem_cliente", q("SELECT COUNT(*) FROM dw.fato_atendimento WHERE cliente_sk IS NULL"),
        q("SELECT COUNT(*) FROM dw.fato_atendimento"))
    put("rdt13.dw.fato_avaliacao.linhas", q("SELECT COUNT(*) FROM dw.fato_avaliacao"))
    # ABT (descrição de população; atributos e vazamento são da etapa 4)
    if existe("abt.recompra_90d") and q("SELECT COUNT(*) FROM abt.recompra_90d") > 0:
        n_abt = q("SELECT COUNT(*) FROM abt.recompra_90d")
        put("abt.linhas", n_abt)
        put("abt.positivos", q("SELECT SUM(alvo_recompra_90d) FROM abt.recompra_90d"), n_abt)
        put("abt.clientes_so_com_pedidos_cancelados_ate_o_corte",
            q("SELECT COUNT(*) FROM abt.recompra_90d WHERE frequencia_pedidos = 0"), n_abt)
        put("abt.pedidos_pre_corte_entregues_depois_do_corte",
            q(f"""SELECT COUNT(*) FROM dw.fato_pedido WHERE data_pedido_sk <= DATE '{DATA_CORTE}'
                   AND data_entrega_sk > DATE '{DATA_CORTE}'"""))
        put("abt.pedidos_cancelados_nos_30_dias_antes_do_corte",
            q(f"""SELECT COUNT(*) FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)
                   WHERE s.status_conformado = 'CANCELADO' AND f.data_pedido_sk <= DATE '{DATA_CORTE}'
                     AND f.data_pedido_sk > DATE '{DATA_CORTE}' - 30"""))
        put("abt.pedidos_ate_o_corte", q(f"SELECT COUNT(*) FROM dw.fato_pedido WHERE data_pedido_sk <= DATE '{DATA_CORTE}'"))
        put("rdt14.atributos", len(pd.read_csv(os.path.join(DIR_SAIDA, "abt", "dicionario_atributos.csv"))))
        put("rdt14.clientes_so_no_legado_na_abt",
            q("""SELECT COUNT(*) FROM abt.recompra_90d a JOIN dw.dim_cliente c USING (cliente_sk)
                  WHERE c.origem_unificacao = 'LEGADO'"""), n_abt)
        put("rdt14.clientes_so_no_ecom_na_abt",
            q("""SELECT COUNT(*) FROM abt.recompra_90d a JOIN dw.dim_cliente c USING (cliente_sk)
                  WHERE c.origem_unificacao = 'ECOM'"""), n_abt)
        put("rdt14.clientes_nos_dois_sistemas_na_abt",
            q("""SELECT COUNT(*) FROM abt.recompra_90d a JOIN dw.dim_cliente c USING (cliente_sk)
                  WHERE c.origem_unificacao = 'AMBOS'"""), n_abt)
        put("rdt14.clientes_sem_qualquer_atendimento_sac", q("SELECT COUNT(*) FROM abt.recompra_90d WHERE qtd_atendimentos_sac = 0"), n_abt)
        put("rdt14.clientes_com_primeiro_pedido_em_2023_01",
            q(f"""SELECT COUNT(*) FROM abt.recompra_90d WHERE tempo_como_cliente_dias >=
                  (DATE '{DATA_CORTE}' - DATE '2023-01-31')"""), n_abt)
    # RDT-15: vazamentos introduzidos de propósito
    if existe("abt.recompra_90d_vazamento") and q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento") > 0:
        nv = q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento")
        put("rdt15.clientes", nv)
        put("rdt15.recencia_diferente_da_correta",
            q("""SELECT COUNT(*) FROM abt.recompra_90d_vazamento v JOIN abt.recompra_90d c USING (cliente_sk)
                  WHERE v.recencia_dias IS DISTINCT FROM c.recencia_dias"""), nv)
        put("rdt15.recencia_negativa", q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento WHERE recencia_dias < 0"), nv)
        put("rdt15.recencia_negativa_na_janela_do_alvo",
            q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento WHERE recencia_dias < 0 AND recencia_dias >= -90"))
        put("rdt15.recencia_negativa_depois_da_janela_do_alvo",
            q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento WHERE recencia_dias < -90"))
        put("rdt15.positivos_com_recencia_negativa",
            q("SELECT COUNT(*) FROM abt.recompra_90d_vazamento WHERE recencia_dias < 0 AND alvo_recompra_90d = 1"),
            q("SELECT SUM(alvo_recompra_90d) FROM abt.recompra_90d_vazamento"))
        put("rdt15.taxa_de_positivos_com_recencia_negativa_pct",
            round(100 * q("SELECT AVG(alvo_recompra_90d::float) FROM abt.recompra_90d_vazamento WHERE recencia_dias < 0"), 2))
        put("rdt15.taxa_de_positivos_com_recencia_nao_negativa_pct",
            round(100 * q("SELECT AVG(alvo_recompra_90d::float) FROM abt.recompra_90d_vazamento WHERE recencia_dias >= 0"), 2))
        put("rdt15.frequencia_diferente_da_correta",
            q("""SELECT COUNT(*) FROM abt.recompra_90d_vazamento v JOIN abt.recompra_90d c USING (cliente_sk)
                  WHERE v.frequencia_pedidos IS DISTINCT FROM c.frequencia_pedidos"""), nv)
        put("rdt15.pedidos_a_mais_na_frequencia",
            q("""SELECT SUM(v.frequencia_pedidos - c.frequencia_pedidos) FROM abt.recompra_90d_vazamento v
                  JOIN abt.recompra_90d c USING (cliente_sk)"""))
        put("rdt15.pedidos_efetivos_apos_o_corte",
            q(f"""SELECT COUNT(*) FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)
                   WHERE f.data_pedido_sk > DATE '{DATA_CORTE}' AND s.status_conformado <> 'CANCELADO'"""))
        put("rdt15.pedidos_efetivos_na_janela_do_alvo",
            q(f"""SELECT COUNT(*) FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)
                   WHERE f.data_pedido_sk > DATE '{DATA_CORTE}' AND f.data_pedido_sk <= DATE '{DATA_FIM_ALVO}'
                     AND s.status_conformado <> 'CANCELADO'"""))
        nz = pd.read_csv(os.path.join(DIR_SAIDA, "abt", "normalizacao_global_recompra_90d_vazamento.csv"))
        put("rdt15.zscore.media_global_de_valor_monetario", round(float(nz.media_global[0]), 2))
        put("rdt15.zscore.desvio_global_de_valor_monetario", round(float(nz.desvio_global[0]), 2))

with open(os.path.join(DIR_RDT, "registros_afetados.json"), "w", encoding="utf-8") as f:
    json.dump(dict(sorted(R.items())), f, ensure_ascii=False, indent=1, default=str)
    f.write("\n")
print(f"{len(R)} números gravados em {DIR_RDT}/registros_afetados.json")
