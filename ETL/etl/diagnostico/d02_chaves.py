# -*- coding: utf-8 -*-
"""d02 — Candidatos a chave de junção entre as fontes (pergunta a).

    docker compose exec etl python -m diagnostico.d02_chaves

Saídas: d02_chaves.md, d02_cpf.csv, d02_cobertura.csv, d02_sac_pedido.csv,
d02_ndjson.csv e números-chave em numeros.json (prefixo "a.").

Todas as leituras são da tabela inteira. A validação do dígito verificador
do CPF é feita em Python sobre a coluna completa.
"""

import pandas as pd

from .comum import (FUSO_LOCAL, Relatorio, cpf_valido, ecom, formato, leg,
                    ler_avaliacoes, ler_sac, normaliza_texto, pct, registrar,
                    salvar_csv, so_digitos)

num = {}
rel = Relatorio("d02_chaves.md", "d02 — Chaves de junção e cobertura")

# ============================================================== dados base
cli = leg("SELECT ID_CLIENTE, NOME, CPF, EMAIL, TELEFONE, CIDADE, UF FROM CLIENTES")
cus = ecom("SELECT customer_id, full_name, tax_id, email, phone, city, state FROM shop.customer")
sac = ler_sac()
aval = ler_avaliacoes()

cli["cpf"] = so_digitos(cli.CPF)
cus["cpf"] = so_digitos(cus.tax_id)
sac["cpf"] = so_digitos(sac.cpf_cliente)
for df in (cli, cus, sac):
    df["cpf_ok"] = df.cpf.map(cpf_valido)

# ===================================================================== CPF
rel.secao("CPF — formato, validade e unicidade")
linhas = []
for fonte, df, campo in (("legado", cli, "CLIENTES.CPF"),
                         ("ecommerce", cus, "customer.tax_id"),
                         ("sac", sac, "cpf_cliente")):
    bruto = df[{"legado": "CPF", "ecommerce": "tax_id", "sac": "cpf_cliente"}[fonte]]
    n = len(df)
    ausentes = int((df.cpf == "").sum())
    onze = int((df.cpf.str.len() == 11).sum())
    validos = int(df.cpf_ok.sum())
    vd = df.loc[df.cpf_ok, "cpf"]
    distintos = int(vd.nunique())
    cont = vd.value_counts()
    cpfs_repetidos = int((cont > 1).sum())
    linhas_repetidas = int(cont[cont > 1].sum())
    fmts = bruto.fillna("").map(formato).value_counts()
    linhas.append(dict(fonte=fonte, campo=campo, registros=n, ausentes=ausentes,
                       onze_digitos=onze, dv_valido=validos,
                       onze_digitos_dv_invalido=onze - validos,
                       cpfs_validos_distintos=distintos,
                       cpfs_validos_repetidos=cpfs_repetidos,
                       linhas_com_cpf_repetido=linhas_repetidas,
                       formatos="; ".join(f"'{k}': {v}" for k, v in fmts.items())))
    p = f"a.cpf.{fonte}"
    num[f"{p}.registros"] = n
    num[f"{p}.ausentes"] = ausentes
    num[f"{p}.ausentes_pct"] = pct(ausentes, n)
    num[f"{p}.onze_digitos"] = onze
    num[f"{p}.onze_digitos_pct"] = pct(onze, n)
    num[f"{p}.validos"] = validos
    num[f"{p}.validos_pct"] = pct(validos, n)
    num[f"{p}.dv_invalido"] = onze - validos
    num[f"{p}.dv_invalido_pct"] = pct(onze - validos, n)
    num[f"{p}.distintos_validos"] = distintos
    num[f"{p}.cpfs_repetidos"] = cpfs_repetidos
    num[f"{p}.linhas_cpf_repetido"] = linhas_repetidas
    for k, v in fmts.items():
        rot = {"999.999.999-99": "mascara", "99999999999": "digitos", "": "vazio"}.get(k, k)
        num[f"{p}.formato.{rot}"] = int(v)
tab_cpf = pd.DataFrame(linhas)
salvar_csv(tab_cpf, "d02_cpf.csv")
rel.tabela(tab_cpf.drop(columns="formatos"))
rel.texto("\nFormatos (dígito → 9):\n")
for r in linhas:
    rel.texto(f"- {r['fonte']}: {r['formatos']}")

# ------------------------------------------ interseção legado × e-commerce
cpf_l = set(cli.loc[cli.cpf_ok, "cpf"])
cpf_e = set(cus.loc[cus.cpf_ok, "cpf"])
inter = cpf_l & cpf_e
num["a.cpf.intersecao_distintos"] = len(inter)
num["a.cpf.intersecao_pct_legado_distintos"] = pct(len(inter), len(cpf_l))
num["a.cpf.intersecao_pct_ecommerce_distintos"] = pct(len(inter), len(cpf_e))
cli_cob = int(cli.cpf.isin(inter).sum())
cus_cob = int(cus.cpf.isin(inter).sum())
num["a.cpf.legado_registros_com_par"] = cli_cob
num["a.cpf.legado_registros_com_par_pct"] = pct(cli_cob, len(cli))
num["a.cpf.ecommerce_registros_com_par"] = cus_cob
num["a.cpf.ecommerce_registros_com_par_pct"] = pct(cus_cob, len(cus))

# Pares casados por CPF: o nome e o e-mail concordam?
pares = cli[cli.cpf_ok].merge(cus[cus.cpf_ok], on="cpf")
pares["nome_ok"] = pares.NOME.map(normaliza_texto) == pares.full_name.map(normaliza_texto)
pares["email_ok"] = (pares.EMAIL.fillna("").str.strip().str.lower()
                     == pares.email.fillna("").str.strip().str.lower())
num["a.cpf.pares_registros"] = len(pares)
num["a.cpf.pares_nome_concorda"] = int(pares.nome_ok.sum())
num["a.cpf.pares_nome_concorda_pct"] = pct(pares.nome_ok.sum(), len(pares))
num["a.cpf.pares_nome_discorda"] = int((~pares.nome_ok).sum())
num["a.cpf.pares_uf_concorda"] = int((pares.UF == pares.state).sum())

# SAC: o CPF do atendimento existe em algum cadastro?
sac["cpf_em_leg"] = sac.cpf.isin(set(cli.cpf) - {""})
sac["cpf_em_eco"] = sac.cpf.isin(set(cus.cpf) - {""})
for orig, g in sac.groupby("origem_sistema"):
    o = orig.lower()
    num[f"a.sac.{o}.cpf_em_legado"] = int(g.cpf_em_leg.sum())
    num[f"a.sac.{o}.cpf_em_ecommerce"] = int(g.cpf_em_eco.sum())
    num[f"a.sac.{o}.cpf_em_algum"] = int((g.cpf_em_leg | g.cpf_em_eco).sum())
    num[f"a.sac.{o}.cpf_em_nenhum"] = int((~(g.cpf_em_leg | g.cpf_em_eco)).sum())
    num[f"a.sac.{o}.registros"] = len(g)
num["a.sac.cpf_em_algum"] = int((sac.cpf_em_leg | sac.cpf_em_eco).sum())
num["a.sac.cpf_em_algum_pct"] = pct(num["a.sac.cpf_em_algum"], len(sac))
num["a.sac.cpf_validos"] = int(sac.cpf_ok.sum())
num["a.sac.cpf_validos_pct"] = pct(sac.cpf_ok.sum(), len(sac))

# ================================================================== e-mail
cli["em"] = cli.EMAIL.fillna("").str.strip().str.lower()
cus["em"] = cus.email.fillna("").str.strip().str.lower()
em_l, em_e = set(cli.em) - {""}, set(cus.em) - {""}
num["a.email.legado.distintos"] = len(em_l)
num["a.email.legado.linhas_repetidas"] = int(cli.em.duplicated(keep=False).sum())
num["a.email.ecommerce.distintos"] = len(em_e)
num["a.email.ecommerce.linhas_repetidas"] = int(cus.em.duplicated(keep=False).sum())
num["a.email.intersecao"] = len(em_l & em_e)
num["a.email.pares_cpf_concorda"] = int(pares.email_ok.sum())
num["a.email.pares_cpf_discorda"] = int((~pares.email_ok).sum())
dom_l = cli.em.str.split("@").str[1].value_counts()
dom_e = cus.em.str.split("@").str[1].value_counts()
num["a.email.legado.dominios"] = len(dom_l)
num["a.email.ecommerce.dominios"] = len(dom_e)

# telefone (candidato adicional): DDD + número, sem o +55 do e-commerce
cli["tel"] = so_digitos(cli.TELEFONE)
cus["tel"] = so_digitos(cus.phone).str.replace(r"^55", "", regex=True)
num["a.telefone.intersecao"] = len(set(cli.tel) & set(cus.tel))
num["a.telefone.pares_cpf_concorda"] = int(
    (pares.TELEFONE.pipe(so_digitos) == pares.phone.pipe(so_digitos).str.replace(r"^55", "", regex=True)).sum())

rel.secao("E-mail e telefone")
rel.texto(f"- Domínios do legado: { {k: int(v) for k, v in dom_l.items()} }; "
          f"do e-commerce: { {k: int(v) for k, v in dom_e.items()} }")
rel.texto(f"- Interseção de e-mails normalizados: {num['a.email.intersecao']}")
rel.texto(f"- Pares casados por CPF ({len(pares)} registros): e-mail concorda em "
          f"{num['a.email.pares_cpf_concorda']}, discorda em {num['a.email.pares_cpf_discorda']}; "
          f"nome normalizado concorda em {num['a.cpf.pares_nome_concorda']}.")
rel.texto(f"- Interseção de telefones normalizados: {num['a.telefone.intersecao']}")

# ============================================ tabela-resumo de cobertura
cob = pd.DataFrame([
    ("CPF válido", "CLIENTES → customer", cli_cob, len(cli)),
    ("CPF válido", "customer → CLIENTES", cus_cob, len(cus)),
    ("CPF (SAC)", "SAC → algum cadastro", num["a.sac.cpf_em_algum"], len(sac)),
    ("E-mail", "CLIENTES → customer", int(cli.em.isin(em_e).sum()), len(cli)),
    ("E-mail", "customer → CLIENTES", int(cus.em.isin(em_l).sum()), len(cus)),
    ("Telefone", "CLIENTES → customer", int(cli.tel.isin(set(cus.tel)).sum()), len(cli)),
], columns=["chave", "sentido", "casados", "base"])
cob["pct"] = [pct(a, b) for a, b in zip(cob.casados, cob.base)]

# ============================================== SAC: (origem, id_pedido)
ped_l = leg("""SELECT p.ID_PEDIDO id, p.DT_PEDIDO dt, c.CPF cpf_raw
               FROM PEDIDOS p LEFT JOIN CLIENTES c ON c.ID_CLIENTE = p.ID_CLIENTE""")
ped_e = ecom(f"""SELECT o.order_id id, (o.placed_at AT TIME ZONE '{FUSO_LOCAL}') dt, c.tax_id cpf_raw
                 FROM shop.orders o LEFT JOIN shop.customer c ON c.customer_id = o.customer_id""")
for df in (ped_l, ped_e):
    df["cpf"] = so_digitos(df.cpf_raw)
ids_l, ids_e = set(ped_l.id), set(ped_e.id)

sac["id"] = pd.to_numeric(sac.id_pedido_origem, errors="coerce")
num["a.sac.id_nao_numerico"] = int(sac.id.isna().sum())
sac["no_leg"] = sac.id.isin(ids_l)
sac["no_eco"] = sac.id.isin(ids_e)
sac["no_indicado"] = (sac.origem_sistema.eq("LEGADO") & sac.no_leg) | (sac.origem_sistema.eq("ECOM") & sac.no_eco)
sac["no_outro"] = (sac.origem_sistema.eq("LEGADO") & sac.no_eco) | (sac.origem_sistema.eq("ECOM") & sac.no_leg)

# Teste de consistência: o CPF do atendimento é o do cliente dono do pedido?
cpf_l = ped_l.set_index("id").cpf
cpf_e = ped_e.set_index("id").cpf
dt_l = ped_l.set_index("id").dt
dt_e = ped_e.set_index("id").dt
sac["cpf_dono_leg"] = sac.id.map(cpf_l)
sac["cpf_dono_eco"] = sac.id.map(cpf_e)
sac["cpf_bate_leg"] = sac.cpf.ne("") & sac.cpf.eq(sac.cpf_dono_leg)
sac["cpf_bate_eco"] = sac.cpf.ne("") & sac.cpf.eq(sac.cpf_dono_eco)
sac["abertura"] = pd.to_datetime(sac.data_abertura, format="%d/%m/%Y")
sac["dt_ind"] = sac.id.map(dt_l).where(sac.origem_sistema.eq("LEGADO"), sac.id.map(dt_e))
sac["dt_out"] = sac.id.map(dt_e).where(sac.origem_sistema.eq("LEGADO"), sac.id.map(dt_l))
sac["abre_apos_ind"] = sac.abertura >= sac.dt_ind.dt.normalize()
sac["abre_apos_out"] = sac.abertura >= sac.dt_out.dt.normalize()

linhas = []
for orig, g in sac.groupby("origem_sistema"):
    o = orig.lower()
    n = len(g)
    d = dict(origem_sistema=orig, registros=n,
             existe_no_indicado=int(g.no_indicado.sum()),
             existe_so_no_outro=int((~g.no_indicado & g.no_outro).sum()),
             existe_nos_dois=int((g.no_indicado & g.no_outro).sum()),
             nao_existe=int((~g.no_indicado & ~g.no_outro).sum()),
             cpf_bate_dono_legado=int(g.cpf_bate_leg.sum()),
             cpf_bate_dono_ecommerce=int(g.cpf_bate_eco.sum()),
             abertura_apos_pedido_indicado=int(g.abre_apos_ind.sum()),
             abertura_antes_pedido_indicado=int((g.dt_ind.notna() & ~g.abre_apos_ind).sum()))
    linhas.append(d)
    for k, v in d.items():
        if k not in ("origem_sistema",):
            num[f"a.sac.{o}.{k}"] = v
            if k != "registros":
                num[f"a.sac.{o}.{k}_pct"] = pct(v, n)
tab_sac = pd.DataFrame(linhas)
salvar_csv(tab_sac, "d02_sac_pedido.csv")
num["a.sac.abertura_apos_pedido_indicado_pct"] = pct(sac.abre_apos_ind.sum(), sac.dt_ind.notna().sum())
num["a.sac.cpf_bate_dono_algum"] = int((sac.cpf_bate_leg | sac.cpf_bate_eco).sum())
num["a.sac.cpf_bate_dono_algum_pct"] = pct(num["a.sac.cpf_bate_dono_algum"], len(sac))

rel.secao("SAC — (origem_sistema, id_pedido_origem)")
rel.tabela(tab_sac)
rel.texto("\n'existe_nos_dois' indica que o mesmo número de pedido existe nos dois "
          "sistemas (colisão de identificadores), o que torna o teste de existência "
          "pouco informativo. O teste de consistência compara o CPF do atendimento "
          "com o CPF do cliente dono do pedido em cada sistema.")

# =================================================== NDJSON: order.ref, sku
av = pd.DataFrame({
    "ref": [a.get("order", {}).get("ref") for a in aval],
    "sku": [a.get("product", {}).get("sku") for a in aval],
    "sub": [a.get("submitted_at") for a in aval],
})
av["prefixo"] = av.ref.str.split("-").str[0]
av["id"] = pd.to_numeric(av.ref.str.split("-").str[1], errors="coerce")
av["sku_prefixo"] = av.sku.str.split("-").str[0]
av["sku_num"] = pd.to_numeric(av.sku.str.split("-").str[1], errors="coerce")
num["a.ndjson.ref_ausente"] = int(av.ref.isna().sum())
num["a.ndjson.sku_ausente"] = int(av.sku.isna().sum())

prod_l = set(leg("SELECT ID_PRODUTO FROM PRODUTOS").ID_PRODUTO)
skus_e = ecom("SELECT product_id, sku FROM shop.product")
item_e = ecom("SELECT DISTINCT order_id, product_id FROM shop.order_item")
item_e = item_e.merge(skus_e, on="product_id")
item_l = leg("SELECT DISTINCT ID_PEDIDO, ID_PRODUTO FROM ITENS_PEDIDO")
par_e = set(zip(item_e.order_id, item_e.sku))
par_l = set(zip(item_l.ID_PEDIDO, item_l.ID_PRODUTO))

av["sub_local"] = pd.to_datetime(av["sub"].str[:19])  # offsets observados: só -03:00 ou nenhum
av["no_leg"] = av.id.isin(ids_l)
av["no_eco"] = av.id.isin(ids_e)
eh_leg = av.prefixo.eq("LEG")
av["no_indicado"] = (eh_leg & av.no_leg) | (~eh_leg & av.no_eco)
av["no_outro"] = (eh_leg & av.no_eco) | (~eh_leg & av.no_leg)
av["sku_existe"] = (av.sku_prefixo.eq("SKU") & av.sku.isin(set(skus_e.sku))) | \
                   (av.sku_prefixo.eq("LEG") & av.sku_num.isin(prod_l))
av["sku_no_pedido"] = [((i, s) in par_e) if p == "ECOM" else ((i, n) in par_l)
                       for p, i, s, n in zip(av.prefixo, av.id, av.sku, av.sku_num)]
av["dt_ped"] = av.id.map(dt_l).where(eh_leg, av.id.map(dt_e))
av["sub_apos"] = av.sub_local >= av.dt_ped

linhas = []
for pre, g in av.groupby("prefixo"):
    n = len(g)
    d = dict(prefixo=pre, registros=n,
             prefixo_sku=", ".join(f"{k}: {v}" for k, v in g.sku_prefixo.value_counts().items()),
             pedido_existe_no_indicado=int(g.no_indicado.sum()),
             pedido_existe_so_no_outro=int((~g.no_indicado & g.no_outro).sum()),
             pedido_existe_nos_dois=int((g.no_indicado & g.no_outro).sum()),
             pedido_nao_existe=int((~g.no_indicado & ~g.no_outro).sum()),
             sku_existe=int(g.sku_existe.sum()),
             sku_esta_no_pedido=int(g.sku_no_pedido.sum()),
             enviada_apos_pedido=int(g.sub_apos.sum()))
    linhas.append(d)
    for k, v in d.items():
        if k not in ("prefixo", "prefixo_sku"):
            num[f"a.ndjson.{pre.lower()}.{k}"] = v
            if k != "registros":
                num[f"a.ndjson.{pre.lower()}.{k}_pct"] = pct(v, n)
tab_av = pd.DataFrame(linhas)
salvar_csv(tab_av, "d02_ndjson.csv")
num["a.ndjson.sku_esta_no_pedido"] = int(av.sku_no_pedido.sum())
num["a.ndjson.sku_esta_no_pedido_pct"] = pct(av.sku_no_pedido.sum(), len(av))
num["a.ndjson.enviada_apos_pedido_pct"] = pct(av.sub_apos.sum(), av.dt_ped.notna().sum())

rel.secao("NDJSON — order.ref e product.sku")
rel.tabela(tab_av)
rel.texto("\nSKUs com prefixo LEG- foram procurados em PRODUTOS.ID_PRODUTO; os com SKU- "
          "em shop.product.sku. 'sku_esta_no_pedido' verifica se o produto avaliado é "
          "um item do pedido referenciado.")

# ================================================= colisão de identificadores
ids_cli_l = set(cli.ID_CLIENTE)
ids_cli_e = set(cus.customer_id)
num["a.colisao.pedido_ids_em_comum"] = len(ids_l & ids_e)
num["a.colisao.pedido_ids_em_comum_pct_legado"] = pct(len(ids_l & ids_e), len(ids_l))
num["a.colisao.cliente_ids_em_comum"] = len(ids_cli_l & ids_cli_e)
num["a.colisao.cliente_ids_em_comum_pct_legado"] = pct(len(ids_cli_l & ids_cli_e), len(ids_cli_l))
num["a.colisao.legado_pedido_id_max"] = max(ids_l)
num["a.colisao.ecommerce_pedido_id_max"] = max(ids_e)
rel.secao("Colisão de identificadores numéricos")
rel.texto(f"- ID_PEDIDO × order_id em comum: {num['a.colisao.pedido_ids_em_comum']} "
          f"({num['a.colisao.pedido_ids_em_comum_pct_legado']}% dos pedidos do legado)")
rel.texto(f"- ID_CLIENTE × customer_id em comum: {num['a.colisao.cliente_ids_em_comum']} "
          f"({num['a.colisao.cliente_ids_em_comum_pct_legado']}% dos clientes do legado)")

cob = pd.concat([cob, pd.DataFrame([
    ("SAC (origem, id)", "SAC → pedido no sistema indicado",
     int(sac.no_indicado.sum()), len(sac)),
    ("SAC CPF × dono do pedido", "SAC → cliente do pedido indicado",
     int(((sac.origem_sistema == "LEGADO") & sac.cpf_bate_leg | (sac.origem_sistema == "ECOM") & sac.cpf_bate_eco).sum()),
     len(sac)),
    ("order.ref", "NDJSON → pedido no sistema do prefixo", int(av.no_indicado.sum()), len(av)),
    ("product.sku", "NDJSON → produto", int(av.sku_existe.sum()), len(av)),
    ("order.ref + sku", "NDJSON → item do pedido", int(av.sku_no_pedido.sum()), len(av)),
], columns=["chave", "sentido", "casados", "base"])])
cob["pct"] = [pct(a, b) for a, b in zip(cob.casados, cob.base)]
salvar_csv(cob, "d02_cobertura.csv")
num["a.sac.cpf_bate_dono_indicado"] = int(cob.iloc[7].casados)
num["a.sac.cpf_bate_dono_indicado_pct"] = float(cob.iloc[7].pct)
rel.secao("Resumo de cobertura")
rel.tabela(cob)

registrar(num)
rel.gravar()
print(cob.to_string(index=False))
print(tab_sac.to_string(index=False))
print(tab_av.to_string(index=False))
