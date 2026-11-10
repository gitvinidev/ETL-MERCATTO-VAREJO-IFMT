#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETAPA 2 — TRANSFORMAÇÃO E CONFORMAÇÃO

Lê a camada `stg` (cópia fiel das origens) e grava a camada conformada no
esquema `cnf`. A etapa 3 carrega o esquema estrela `dw` a partir de `cnf`.
(Motivo: o DDL de `dw` está congelado, e vários indicadores que o RDT exige,
como `entrega_sem_data` ou `frete_negativo`, não têm coluna lá. Em `cnf` eles
ficam ao lado dos valores conformados.)

Cada bloco corresponde a uma decisão sem resposta única, registrada em
docs/RDT.md (fichas RDT-02 a RDT-09 e RDT-13). Os números das fichas saem de
`diagnostico/rdt_registros_afetados.py`.

Régua de tempo (RDT-09): America/Sao_Paulo (UTC-3, sem horário de verão no
período). DT_PEDIDO/DT_ENTREGA do legado, que não têm fuso, são lidos como
hora local; os TIMESTAMPTZ do e-commerce e as avaliações são convertidos
para essa hora local antes de se extrair a data.

    docker compose exec etl python 02_transformacao.py
"""

import re
import unicodedata

import pandas as pd
from sqlalchemy import text

from config import eng_dw
from qualidade.assercoes import Suite

FUSO = "America/Sao_Paulo"
TOLERANCIA = 0.01


# ---------------------------------------------------------------------------
# Utilitários prontos
# ---------------------------------------------------------------------------
def so_digitos(txt):
    return re.sub(r"\D", "", txt or "")


def cpf_valido(cpf):
    """Valida os dois dígitos verificadores. Retorna None se não tiver 11 dígitos."""
    c = so_digitos(cpf)
    if len(c) != 11 or len(set(c)) == 1:
        return None if len(c) != 11 else False
    b = [int(x) for x in c]
    s = sum((10 - i) * b[i] for i in range(9))
    d1 = 0 if (11 - s % 11) >= 10 else (11 - s % 11)
    s = sum((11 - i) * (b[:9] + [d1])[i] for i in range(10))
    d2 = 0 if (11 - s % 11) >= 10 else (11 - s % 11)
    return b[9] == d1 and b[10] == d2


def normaliza_nome(nome):
    """MAIÚSCULAS sem acento, espaços colapsados. Base para pareamento aproximado."""
    n = unicodedata.normalize("NFD", (nome or "").strip().upper())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", n)


def normaliza_minusculo(txt):
    """minúsculas sem acento, espaços colapsados (rótulos de categoria e motivo)."""
    return normaliza_nome(txt).lower()


def roda(eng, sql, **params):
    with eng.begin() as cx:
        return cx.execute(text(sql), params)


def escalar(eng, sql, **params):
    with eng.connect() as cx:
        return cx.execute(text(sql), params).scalar()


def grava(df, eng, tabela):
    roda(eng, f"DROP TABLE IF EXISTS cnf.{tabela}")
    df.to_sql(tabela, eng, schema="cnf", index=False, method="multi", chunksize=5_000)


# ===========================================================================
# DECISÃO 1 — IDENTIDADE DO CLIENTE ENTRE OS DOIS SISTEMAS   (RDT-02, RDT-03)
# ===========================================================================
def unifica_clientes(qa):
    """
    Regras de pareamento, da mais forte à mais fraca. Em todas, uma aresta liga
    dois registros; cada pessoa é um componente conexo do grafo.

      DUPLICATA_LEGADO       (RDT-03) mesmo e-mail, mesmo telefone e mesmo nome
                             normalizado, dentro do legado.
      CPF_VALIDO_NOME        mesmo CPF com dígito verificador válido E mesmo nome
                             normalizado (em qualquer par de registros).
      CPF_INVALIDO_NOME_UF   mesmo CPF de 11 dígitos com dígito verificador
                             inválido E mesmo nome normalizado E mesma UF.

    Não há regra por nome + UF (nem + cidade): nenhuma chave nome+UF é única
    nos dois cadastros, e entre CPFs válidos ela produz pares falsos (ver RDT-02).

    CPF igual com nomes diferentes não funde: é colisão de CPF. O CPF fica só
    com o componente de mais registros; em empate, com nenhum.
    """
    eng = eng_dw()
    roda(eng, "CREATE SCHEMA IF NOT EXISTS cnf")

    L = pd.read_sql(
        "SELECT id_cliente, nome, cpf, email, dt_cadastro, cidade, uf, telefone "
        "FROM stg.legado_clientes ORDER BY id_cliente", eng)
    E = pd.read_sql(
        f"SELECT customer_id, full_name, tax_id, email, "
        f"(created_at AT TIME ZONE '{FUSO}')::date AS dt_cadastro, city, state, phone "
        f"FROM stg.ecommerce_customer ORDER BY customer_id", eng)

    def limpa(v):
        v = (v or "").strip()
        return None if v == "" else v

    L = pd.DataFrame(dict(
        sis="L", id=L.id_cliente, nome=L.nome, email=L.email, tel=L.telefone,
        cpf_bruto=L.cpf, cidade=L.cidade, uf=L.uf, dt_cad=L.dt_cadastro))
    E = pd.DataFrame(dict(
        sis="E", id=E.customer_id, nome=E.full_name, email=E.email, tel=E.phone,
        cpf_bruto=E.tax_id, cidade=E.city, uf=E.state, dt_cad=E.dt_cadastro))
    N = pd.concat([L, E], ignore_index=True)
    n = len(N)

    N["nn"] = N.nome.map(normaliza_nome)
    N["cpfd"] = N.cpf_bruto.fillna("").map(so_digitos)
    N["cpf_ok"] = N.cpfd.map(cpf_valido)                       # True / False / None
    N["cpf_usavel"] = N.cpfd.map(lambda c: len(c) == 11 and len(set(c)) > 1)
    N["email_n"] = N.email.fillna("").str.strip().str.lower()
    N["tel_n"] = N.tel.fillna("").map(so_digitos)
    # Ausência com sentinela: CIDADE = 'N/A' no legado é "não informada" (RDT-08).
    N["cidade_l"] = N.cidade.map(limpa).map(lambda c: None if c and c.upper() == "N/A" else c)
    N["uf_l"] = N.uf.map(limpa)

    pai = list(range(n))

    def acha(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def une(grupo):
        base = acha(grupo[0])
        for i in grupo[1:]:
            pai[acha(i)] = base

    arestas = {"DUPLICATA_LEGADO": [], "CPF_VALIDO_NOME": [], "CPF_INVALIDO_NOME_UF": []}

    leg = N[(N.sis == "L") & (N.email_n != "")]
    for _, g in leg.groupby(["email_n", "nn", "tel_n"]):
        if len(g) > 1:
            arestas["DUPLICATA_LEGADO"].append(list(g.index))

    val = N[N.cpf_ok == True]                                  # noqa: E712
    for _, g in val.groupby(["cpfd", "nn"]):
        if len(g) > 1:
            arestas["CPF_VALIDO_NOME"].append(list(g.index))

    inv = N[(N.cpf_ok == False) & N.cpf_usavel]                # noqa: E712
    for _, g in inv.groupby(["cpfd", "nn", "uf_l"], dropna=False):
        if len(g) > 1:
            arestas["CPF_INVALIDO_NOME_UF"].append(list(g.index))

    for grupos in arestas.values():
        for g in grupos:
            une(g)
    N["comp"] = [acha(i) for i in range(n)]

    regras = {}
    for nome_regra, grupos in arestas.items():
        for g in grupos:
            regras.setdefault(acha(g[0]), set()).add(nome_regra)

    # Componentes -> uma linha por pessoa -------------------------------------
    N["completo"] = (N.cpf_usavel.astype(int) + N.cidade_l.notna().astype(int)
                     + N.uf_l.notna().astype(int) + (N.tel_n != "").astype(int)
                     + (N.email_n != "").astype(int))
    N["rank_val"] = (N.cpf_ok != True).astype(int)             # noqa: E712
    ordem = N.sort_values(["comp", "rank_val", "completo", "id"],
                          ascending=[True, True, False, True], kind="stable")

    pessoas = []
    for comp, g in ordem.groupby("comp", sort=False):
        gl, ge = g[g.sis == "L"], g[g.sis == "E"]
        # CPF: o válido, se houver; senão o inválido mais frequente
        usaveis = g[g.cpf_usavel]
        cpf = None
        if len(usaveis):
            validos = usaveis[usaveis.cpf_ok == True]       # noqa: E712
            base = validos if len(validos) else usaveis
            cpf = base.cpfd.mode().sort_values().iloc[0]
        # atributos: o e-commerce (cadastro controlado) tem prioridade; depois o
        # sobrevivente do legado
        ref = pd.concat([ge, gl])
        nome = next(iter(ref.nome))
        cidade = next((c for c in ref.cidade_l if c), None)
        uf = next((u for u in ref.uf_l if u), None)
        dts = [d for d in g.dt_cad if pd.notna(d)]
        pessoas.append(dict(
            comp=comp,
            cpf_normalizado=cpf,
            cpf_valido=None if cpf is None else bool(cpf_valido(cpf)),
            nome_padronizado=" ".join(nome.strip().upper().split()),
            nn=g.nn.iloc[0],
            n_nomes_distintos=g.nn.nunique(),
            cidade=cidade, uf=uf,
            dt_primeiro_cadastro=min(dts) if dts else None,
            id_legado=int(gl.id.iloc[0]) if len(gl) else None,
            id_ecommerce=int(ge.id.min()) if len(ge) else None,
            n_reg_legado=len(gl), n_reg_ecom=len(ge),
            origem_unificacao="AMBOS" if len(gl) and len(ge) else ("LEGADO" if len(gl) else "ECOM"),
            regra_pareamento="+".join(sorted(regras[comp])) if comp in regras else None,
            chave_ord=(0, int(gl.id.min())) if len(gl) else (1, int(ge.id.min())),
        ))
    P = pd.DataFrame(pessoas).sort_values("chave_ord").reset_index(drop=True)
    P["cliente_key"] = P.index + 1

    # Colisão de CPF: mesmo CPF válido em componentes diferentes ---------------
    P["cpf_conflito"] = False
    P["n_reg"] = P.n_reg_legado + P.n_reg_ecom
    com_cpf = P[(P.cpf_valido == True)]                        # noqa: E712
    for cpf, g in com_cpf.groupby("cpf_normalizado"):
        if len(g) > 1:
            P.loc[g.index, "cpf_conflito"] = True
            top = g.n_reg.max()
            donos = g[g.n_reg == top]
            perdedores = g.index if len(donos) > 1 else g.index.difference(donos.index)
            P.loc[perdedores, ["cpf_normalizado", "cpf_valido"]] = [None, None]

    # Tabelas de saída ----------------------------------------------------------
    chave = dict(zip(P.comp, P.cliente_key))
    ponte = N[["sis", "id", "comp", "cpfd", "cpf_ok", "cpf_usavel"]].copy()
    ponte["cliente_key"] = ponte.comp.map(chave)
    ponte["sistema_origem"] = ponte.sis.map({"L": "LEGADO", "E": "ECOM"})
    sobrev = ({("L", int(x)) for x in P.id_legado.dropna()}
              | {("E", int(x)) for x in P.id_ecommerce.dropna()})
    ponte["papel"] = [("SOBREVIVENTE" if (s, int(i)) in sobrev else "ABSORVIDO")
                      for s, i in zip(ponte.sis, ponte.id)]
    ponte = ponte.rename(columns={"id": "id_origem"})[
        ["sistema_origem", "id_origem", "cliente_key", "papel"]]
    grava(ponte, eng, "cliente_ponte")

    cpf_membros = N[N.cpf_usavel][["comp", "cpfd", "cpf_ok"]].drop_duplicates()
    cpf_membros["cliente_key"] = cpf_membros.comp.map(chave)
    grava(cpf_membros.rename(columns={"cpfd": "cpf_digitos", "cpf_ok": "cpf_valido"})[
        ["cliente_key", "cpf_digitos", "cpf_valido"]], eng, "cliente_cpf")

    saida = P[["cliente_key", "cpf_normalizado", "cpf_valido", "nome_padronizado", "cidade",
               "uf", "dt_primeiro_cadastro", "id_legado", "id_ecommerce",
               "origem_unificacao", "regra_pareamento", "n_reg_legado", "n_reg_ecom",
               "cpf_conflito"]]
    saida = saida.astype({"id_legado": "Int64", "id_ecommerce": "Int64"})
    grava(saida, eng, "cliente")

    # Asserções -----------------------------------------------------------------
    qa.igual("cliente: registros de origem na ponte", len(ponte), n,
             "todo registro de CLIENTES e customer pertence a exatamente uma pessoa")
    qa.unico("cliente: (sistema, id) único na ponte",
             ponte.sistema_origem + "|" + ponte.id_origem.astype(str))
    qa.igual("cliente: pessoas com nomes normalizados distintos", int((P.n_nomes_distintos > 1).sum()), 0,
             "nenhuma fusão pode juntar nomes diferentes")
    dup = P[P.cpf_valido == True].cpf_normalizado                   # noqa: E712
    qa.igual("dim_cliente: CPF válido duplicado entre pessoas", int(dup.duplicated().sum()), 0,
             "colisões de CPF resolvidas: o CPF fica com um só componente (RDT-02)")
    cpfs = P.cpf_normalizado.dropna()
    qa.igual("cliente: CPF conformado com tamanho diferente de 11",
             int((cpfs.str.len() != 11).sum()), 0, "RDT-02/RDT-08")
    qa.igual("cliente: cidade 'N/A' remanescente", int((P.cidade == "N/A").sum()), 0,
             "RDT-08: o sentinela virou NULL")
    qa.dominio("cliente: origem_unificacao", P.origem_unificacao, {"LEGADO", "ECOM", "AMBOS"})
    qa.igual("cliente: nome_padronizado vazio", int((P.nome_padronizado == "").sum()), 0)
    qa.maior_igual("cliente: pessoas pareadas entre os sistemas (AMBOS)",
                   int((P.origem_unificacao == "AMBOS").sum()), 1,
                   "o pareamento por CPF tem de produzir ao menos um par")
    print(f"clientes: {n:,} registros -> {len(P):,} pessoas "
          f"({int((P.origem_unificacao == 'AMBOS').sum()):,} nos dois sistemas)".replace(",", "."))


# ===========================================================================
# DECISÃO 2 — CONFORMAÇÃO DE STATUS E CANAL                       (RDT-04)
# ===========================================================================
STATUS = [
    # sistema, status_origem, status_conformado, motivo_cancelamento
    ("LEGADO", "ENTREGUE", "ENTREGUE", None),
    ("LEGADO", "EM TRANSITO", "EM_TRANSITO", None),
    ("LEGADO", "SEPARACAO", "EM_PROCESSAMENTO", None),
    # o legado não distingue cancelamento de recusa de pagamento: motivo NULL
    ("LEGADO", "CANCELADO", "CANCELADO", None),
    ("ECOM", "delivered", "ENTREGUE", None),
    ("ECOM", "shipped", "EM_TRANSITO", None),
    ("ECOM", "processing", "EM_PROCESSAMENTO", None),
    ("ECOM", "canceled", "CANCELADO", "CANCELAMENTO"),
    ("ECOM", "payment_declined", "CANCELADO", "PAGAMENTO_RECUSADO"),
]
CANAL = [
    # sistema, canal_origem, canal_conformado
    ("LEGADO", "LOJA", "FISICO"),
    ("LEGADO", "TELEVENDAS", "TELEVENDAS"),
    ("LEGADO", "SITE", "ONLINE_PROPRIO"),
    ("ECOM", "web", "ONLINE_PROPRIO"),
    ("ECOM", "app", "ONLINE_PROPRIO"),
    ("ECOM", "marketplace", "MARKETPLACE"),
]


def conforma_status(qa):
    """
    Alternativa (iii): status_conformado = CANCELADO nos dois sistemas, com
    motivo_cancelamento preenchido só onde a origem o distingue. O legado fica
    com motivo NULL. Conta como compra todo status diferente de CANCELADO.
    """
    eng = eng_dw()
    grava(pd.DataFrame(STATUS, columns=["sistema", "status_origem",
                                        "status_conformado", "motivo_cancelamento"]),
          eng, "status_map")
    grava(pd.DataFrame(CANAL, columns=["sistema", "canal_origem", "canal_conformado"]),
          eng, "canal_map")

    # Todo status e todo canal que aparece na origem tem de estar no mapa.
    sem_status = escalar(eng, """
        SELECT (SELECT COUNT(*) FROM stg.legado_pedidos p
                 WHERE NOT EXISTS (SELECT 1 FROM cnf.status_map m
                                    WHERE m.sistema='LEGADO' AND m.status_origem=p.status))
             + (SELECT COUNT(*) FROM stg.ecommerce_orders p
                 WHERE NOT EXISTS (SELECT 1 FROM cnf.status_map m
                                    WHERE m.sistema='ECOM' AND m.status_origem=p.status))""")
    qa.igual("status: pedidos cujo status não está no mapa", sem_status, 0,
             "nenhum status fora da lista conformada")
    sem_canal = escalar(eng, """
        SELECT (SELECT COUNT(*) FROM stg.legado_pedidos p
                 WHERE NOT EXISTS (SELECT 1 FROM cnf.canal_map m
                                    WHERE m.sistema='LEGADO' AND m.canal_origem=p.canal))
             + (SELECT COUNT(*) FROM stg.ecommerce_orders p
                 WHERE NOT EXISTS (SELECT 1 FROM cnf.canal_map m
                                    WHERE m.sistema='ECOM' AND m.canal_origem=p.channel))""")
    qa.igual("canal: pedidos cujo canal não está no mapa", sem_canal, 0)


# ===========================================================================
# DECISÃO 3 — SEMÂNTICA DOS VALORES MONETÁRIOS                (RDT-05, RDT-06)
# ===========================================================================
def conforma_valores(qa):
    """
    Medidas por pedido, iguais nos dois sistemas (fórmula única):
        valor_mercadoria = soma de quantidade x preço unitário (bruto)
        valor_desconto   = soma dos descontos de linha (-1 do legado conta 0)
        valor_frete      = frete como gravado (negativo preservado)
        valor_total      = mercadoria - desconto + frete

    A semana 1 mostrou que VALOR_TOTAL já é essa soma (com -1 tratado como 0)
    e que total_amount é a soma SEM o frete. Por isso a referência do
    e-commerce na reconciliação é total_amount + freight_amount.
    """
    eng = eng_dw()
    roda(eng, "DROP TABLE IF EXISTS cnf.item")
    roda(eng, """
        CREATE TABLE cnf.item AS
        SELECT 'LEGADO'::text AS sistema_origem,
               'LEG-'  || i.id_item   AS id_item_origem,
               'LEG-'  || i.id_pedido AS id_pedido_origem,
               i.id_produto           AS id_produto_origem,
               i.qtd                  AS quantidade,
               i.vl_unitario          AS valor_unitario,
               CASE WHEN i.vl_desconto = -1 THEN 0 ELSE i.vl_desconto END AS valor_desconto,
               (i.vl_desconto = -1)   AS desconto_sentinela,
               (p.id_pedido IS NOT NULL) AS pedido_existe,
               i._linha_origem
          FROM stg.legado_itens_pedido i
          LEFT JOIN stg.legado_pedidos p ON p.id_pedido = i.id_pedido
        UNION ALL
        SELECT 'ECOM', 'ECOM-' || i.order_item_id, 'ECOM-' || i.order_id,
               i.product_id, i.quantity, i.unit_price, i.discount, false,
               (o.order_id IS NOT NULL),
               i._linha_origem
          FROM stg.ecommerce_order_item i
          LEFT JOIN stg.ecommerce_orders o ON o.order_id = i.order_id""")
    roda(eng, "ALTER TABLE cnf.item ADD COLUMN valor_linha numeric(12,2)")
    roda(eng, "UPDATE cnf.item SET valor_linha = quantidade * valor_unitario - valor_desconto")
    roda(eng, "CREATE INDEX ON cnf.item (id_pedido_origem)")

    outros_neg = escalar(eng, """
        SELECT COUNT(*) FROM stg.legado_itens_pedido WHERE vl_desconto < 0 AND vl_desconto <> -1""")
    qa.igual("valores: descontos negativos que não são o sentinela -1", outros_neg, 0,
             "o tratamento de -1 como 0 só vale para o sentinela (RDT-06)")


# ===========================================================================
# DECISÃO 4 — TAXONOMIA DE PRODUTO                                (RDT-07)
# ===========================================================================
# rótulo normalizado (minúsculas, sem acento) -> (nivel1, nivel2, classe)
MAPA_CATEGORIA = {
    # direto: existe nó com o mesmo significado no nível em que o e-commerce classifica
    "televisores": ("Áudio e TV", "Televisores", "direto"),
    "moveis": ("Casa e Decoração", "Móveis", "direto"),
    "celulares": ("Telefonia", "Smartphones", "direto"),
    "celular/smartphone": ("Telefonia", "Smartphones", "direto"),
    "esporte": ("Esporte e Lazer", None, "direto"),
    "esportes e lazer": ("Esporte e Lazer", None, "direto"),
    "ferramentas": ("Ferramentas", None, "direto"),
    "ferramentas e construcao": ("Ferramentas", None, "direto"),
    # nível: só a raiz corresponde; não se inventa o filho
    "audio/video": ("Áudio e TV", None, "nivel"),
    "tv e som": ("Áudio e TV", None, "nivel"),
    "casa": ("Casa e Decoração", None, "nivel"),
    "casa e decoracao": ("Casa e Decoração", None, "nivel"),
    "telefonia": ("Telefonia", None, "nivel"),
    "eletrodomesticos": ("Eletrodomésticos", None, "nivel"),
    "eletro-domesticos": ("Eletrodomésticos", None, "nivel"),
    "games": ("Games", None, "nivel"),
    "games e consoles": ("Games", None, "nivel"),
    "info": ("Informática", None, "nivel"),
    "informatica": ("Informática", None, "nivel"),
    # ambíguo: cobre mais de uma raiz; nada é atribuído
    "eletro": (None, None, "ambiguo"),
    "informatica e games": (None, None, "ambiguo"),
    # sem mapeamento: genérico ou vazio
    "diversos": (None, None, "sem_mapeamento"),
    "outros": (None, None, "sem_mapeamento"),
    "": (None, None, "sem_mapeamento"),
}


def conforma_categorias(qa):
    """
    Conformar não autoriza apagar a evidência: categoria_origem guarda o valor
    bruto; a classe do mapeamento (direto, nivel, ambiguo, sem_mapeamento) fica
    em cnf.produto.classe_mapeamento.

    Produtos dos dois sistemas NÃO são unificados entre si: o legado não tem
    SKU, e a coincidência de descrições é acidental (43 em 15.000).
    """
    eng = eng_dw()
    pl = pd.read_sql("SELECT id_produto, descricao, categoria, preco_tabela, ativo "
                     "FROM stg.legado_produtos ORDER BY id_produto", eng)
    chaves = pl.categoria.fillna("").map(normaliza_minusculo)
    desconhecidos = sorted(set(chaves) - set(MAPA_CATEGORIA))
    qa.igual("categoria: rótulos do legado sem regra no mapa", len(desconhecidos), 0,
             f"rótulos novos precisam de decisão: {desconhecidos}")
    mapa = chaves.map(lambda k: MAPA_CATEGORIA.get(k, (None, None, "sem_mapeamento")))
    leg = pd.DataFrame(dict(
        sku=None, descricao=pl.descricao,
        categoria_nivel1=[m[0] for m in mapa], categoria_nivel2=[m[1] for m in mapa],
        categoria_origem=pl.categoria, classe_mapeamento=[m[2] for m in mapa],
        preco_referencia=pl.preco_tabela, ativo=pl.ativo.map({"S": True, "N": False}),
        id_legado=pl.id_produto, id_ecommerce=pd.NA, origem="LEGADO"))

    pe = pd.read_sql("""
        SELECT p.product_id, p.sku, p.title, p.list_price, p.active,
               COALESCE(pai.name, c.name) AS nivel1,
               CASE WHEN pai.category_id IS NULL THEN NULL ELSE c.name END AS nivel2,
               c.name AS categoria_origem
          FROM stg.ecommerce_product p
          LEFT JOIN stg.ecommerce_category c   ON c.category_id = p.category_id
          LEFT JOIN stg.ecommerce_category pai ON pai.category_id = c.parent_id
         ORDER BY p.product_id""", eng)
    eco = pd.DataFrame(dict(
        sku=pe.sku, descricao=pe.title, categoria_nivel1=pe.nivel1,
        categoria_nivel2=pe.nivel2, categoria_origem=pe.categoria_origem,
        classe_mapeamento="taxonomia_origem", preco_referencia=pe.list_price,
        ativo=pe.active, id_legado=pd.NA, id_ecommerce=pe.product_id, origem="ECOM"))
    prod = pd.concat([leg, eco], ignore_index=True)
    prod.insert(0, "produto_key", prod.index + 1)
    prod = prod.astype({"id_legado": "Int64", "id_ecommerce": "Int64"})
    grava(prod, eng, "produto")

    qa.igual("produto: linhas conformadas", len(prod), len(pl) + len(pe),
             "uma linha por produto de cada origem, sem fusão entre sistemas")
    qa.unico("produto: produto_key", prod.produto_key)
    qa.igual("produto: produtos ECOM sem categoria nivel1",
             int(eco.categoria_nivel1.isna().sum()), 0,
             "toda categoria do e-commerce existe na taxonomia")
    sem_regra = prod[prod.classe_mapeamento.isin(["ambiguo", "sem_mapeamento"])]
    qa.igual("produto: ambíguo/sem_mapeamento com nivel1 preenchido",
             int(sem_regra.categoria_nivel1.notna().sum()), 0,
             "RDT-07: nada é atribuído onde o rótulo cobre mais de uma raiz ou não informa")
    mapeados = prod[prod.classe_mapeamento.isin(["direto", "nivel"])]
    qa.igual("produto: nivel1 vazio entre direto/nivel", int(mapeados.categoria_nivel1.isna().sum()), 0)


# ===========================================================================
# DECISÃO 5 — DATAS, AUSÊNCIAS E SENTINELAS                (RDT-08, RDT-09)
# ===========================================================================
def trata_datas_e_ausencias(qa):
    """
    Classificação das ausências e sentinelas (detalhe em RDT-08):

      DT_ENTREGA = 1900-01-01     sentinela        -> NULL + entrega_sem_data
      DT_ENTREGA nula, não entregue  não aplicável  -> NULL (sem indicador)
      entrega anterior ao pedido  inconsistência   -> NULL + entrega_anterior_pedido
      CIDADE = 'N/A'              sentinela        -> NULL   (feito em unifica_clientes)
      SAC nota 0 / vazia          fora da escala / não coletada -> NULL (+ nota_zero)
      SAC data_fechamento vazia   dado perdido (horas de resolução existem) -> NULL
      SAC horas negativas         inconsistência   -> NULL
      rating ausente              não coletada     -> NULL

    Fuso (RDT-09): tudo é levado à hora local de America/Sao_Paulo e só então
    se extrai a data. O legado já está em hora local (seu horário comercial só
    faz sentido assim, semana 1, D7).
    """
    eng = eng_dw()
    roda(eng, "DROP TABLE IF EXISTS cnf.pedido_base")
    roda(eng, f"""
        CREATE TABLE cnf.pedido_base AS
        SELECT 'LEGADO'::text AS sistema_origem,
               'LEG-' || p.id_pedido AS id_origem,
               p.id_pedido           AS id_num,
               p.id_cliente          AS id_cliente_origem,
               p.dt_pedido           AS ts_pedido_local,
               CASE WHEN p.dt_entrega::date = DATE '1900-01-01' THEN NULL
                    ELSE p.dt_entrega END AS ts_entrega_local,
               COALESCE(p.dt_entrega::date = DATE '1900-01-01', false) AS entrega_sem_data,
               p.status AS status_origem, p.canal AS canal_origem,
               p.valor_frete, p.valor_total AS total_origem_conformado,
               p._linha_origem
          FROM stg.legado_pedidos p
        UNION ALL
        SELECT 'ECOM', 'ECOM-' || o.order_id, o.order_id, o.customer_id,
               o.placed_at    AT TIME ZONE '{FUSO}',
               o.delivered_at AT TIME ZONE '{FUSO}',
               false, o.status, o.channel, o.freight_amount,
               -- total_amount é SEM frete; a fórmula conformada soma o frete (RDT-05)
               o.total_amount + o.freight_amount,
               o._linha_origem
          FROM stg.ecommerce_orders o""")


def monta_pedido(qa):
    """Junta valores, datas, status, canal e cliente em cnf.pedido (grão: um pedido)."""
    eng = eng_dw()
    roda(eng, "DROP TABLE IF EXISTS cnf.pedido")
    roda(eng, """
        CREATE TABLE cnf.pedido AS
        WITH v AS (
            SELECT id_pedido_origem,
                   SUM(quantidade)                      AS qtd_itens,
                   SUM(quantidade * valor_unitario)     AS valor_mercadoria,
                   SUM(valor_desconto)                  AS valor_desconto,
                   COUNT(*) FILTER (WHERE desconto_sentinela) AS linhas_desconto_sentinela
              FROM cnf.item
             GROUP BY id_pedido_origem
        ), b AS (
            SELECT b.*,
                   COALESCE(b.ts_entrega_local < b.ts_pedido_local, false) AS entrega_anterior_pedido
              FROM cnf.pedido_base b
        )
        SELECT b.sistema_origem, b.id_origem, b.id_num,
               c.cliente_key,
               b.ts_pedido_local,
               b.ts_pedido_local::date AS data_pedido,
               CASE WHEN b.ts_entrega_local IS NULL OR b.entrega_anterior_pedido THEN NULL
                    ELSE b.ts_entrega_local::date END AS data_entrega,
               b.entrega_sem_data, b.entrega_anterior_pedido,
               b.status_origem, s.status_conformado, s.motivo_cancelamento,
               b.canal_origem, cm.canal_conformado,
               COALESCE(v.qtd_itens, 0)                       AS qtd_itens,
               COALESCE(v.valor_mercadoria, 0)::numeric(12,2) AS valor_mercadoria,
               b.valor_frete::numeric(12,2)                   AS valor_frete,
               COALESCE(v.valor_desconto, 0)::numeric(12,2)   AS valor_desconto,
               (COALESCE(v.valor_mercadoria, 0) - COALESCE(v.valor_desconto, 0)
                   + b.valor_frete)::numeric(12,2)            AS valor_total,
               b.total_origem_conformado,
               COALESCE(v.linhas_desconto_sentinela, 0)       AS linhas_desconto_sentinela,
               (b.valor_frete < 0)                            AS frete_negativo,
               b._linha_origem
          FROM b
          LEFT JOIN v ON v.id_pedido_origem = b.id_origem
          LEFT JOIN cnf.cliente_ponte c
                 ON c.sistema_origem = b.sistema_origem AND c.id_origem = b.id_cliente_origem
          LEFT JOIN cnf.status_map s
                 ON s.sistema = b.sistema_origem AND s.status_origem = b.status_origem
          LEFT JOIN cnf.canal_map cm
                 ON cm.sistema = b.sistema_origem AND cm.canal_origem = b.canal_origem""")
    roda(eng, "ALTER TABLE cnf.pedido ADD COLUMN dias_entrega integer")
    roda(eng, "UPDATE cnf.pedido SET dias_entrega = data_entrega - data_pedido "
              "WHERE data_entrega IS NOT NULL")
    roda(eng, "CREATE UNIQUE INDEX ON cnf.pedido (sistema_origem, id_origem)")
    roda(eng, "CREATE INDEX ON cnf.pedido (cliente_key)")

    # Asserções --------------------------------------------------------------
    n_stg = escalar(eng, "SELECT (SELECT COUNT(*) FROM stg.legado_pedidos) + "
                         "(SELECT COUNT(*) FROM stg.ecommerce_orders)")
    n_cnf = escalar(eng, "SELECT COUNT(*) FROM cnf.pedido")
    qa.igual("pedido: linhas conformadas == pedidos da stg", n_cnf, n_stg,
             "nenhuma junção multiplicou ou perdeu pedidos (grão: um pedido)")
    qa.cardinalidade_preservada("pedido: junção com itens/cliente/status/canal", n_stg, n_cnf)
    qa.igual("pedido: sem cliente_key", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido "
                                                      "WHERE cliente_key IS NULL"), 0,
             "todo pedido tem cliente (RDT-12)")
    qa.igual("pedido: sem status_conformado", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido "
                                                            "WHERE status_conformado IS NULL"), 0)
    qa.igual("pedido: sem canal_conformado", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido "
                                                           "WHERE canal_conformado IS NULL"), 0)
    qa.dominio("pedido: status_conformado fora da lista",
               pd.read_sql("SELECT status_conformado FROM cnf.pedido", eng).status_conformado,
               {"ENTREGUE", "EM_TRANSITO", "EM_PROCESSAMENTO", "CANCELADO"})
    qa.igual("pedido: sem itens", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido WHERE qtd_itens = 0"), 0,
             "toda a base tem itens; um pedido sem item mudaria a reconciliação")

    # soma de valor_mercadoria por pedido == soma dos itens da stg (±0,01)
    dif_merc = escalar(eng, f"""
        WITH i AS (
            SELECT 'LEG-' || id_pedido AS k, SUM(qtd * vl_unitario) m
              FROM stg.legado_itens_pedido GROUP BY 1
            UNION ALL
            SELECT 'ECOM-' || order_id, SUM(quantity * unit_price)
              FROM stg.ecommerce_order_item GROUP BY 1)
        SELECT COUNT(*) FROM cnf.pedido p JOIN i ON i.k = p.id_origem
         WHERE ABS(p.valor_mercadoria - i.m) > {TOLERANCIA}""")
    qa.igual("pedido: valor_mercadoria diverge da soma dos itens (>0,01)", dif_merc, 0,
             "mercadoria do pedido == soma qtd x preço dos itens na stg")
    # valor_total recalculado == total gravado na origem, mesma fórmula
    dif_tot = escalar(eng, f"""
        SELECT COUNT(*) FROM cnf.pedido
         WHERE ABS(valor_total - total_origem_conformado) > {TOLERANCIA}""")
    qa.igual("pedido: valor_total diverge do total da origem (>0,01)", dif_tot, 0,
             "legado: VALOR_TOTAL; e-commerce: total_amount + freight_amount (RDT-05)")
    qa.igual("pedido: valor_total negativo", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido "
                                                          "WHERE valor_total < 0"), 0,
             "nem o frete negativo (RDT-06) leva o total abaixo de zero")
    qa.igual("pedido: dias_entrega negativo", escalar(eng, "SELECT COUNT(*) FROM cnf.pedido "
                                                           "WHERE dias_entrega < 0"), 0,
             "entrega anterior ao pedido vira NULL com indicador (RDT-08)")
    qa.igual("pedido: data_pedido fora da régua America/Sao_Paulo", escalar(eng, f"""
        SELECT COUNT(*) FROM cnf.pedido p
          LEFT JOIN stg.ecommerce_orders o ON p.sistema_origem = 'ECOM' AND o.order_id = p.id_num
          LEFT JOIN stg.legado_pedidos   l ON p.sistema_origem = 'LEGADO' AND l.id_pedido = p.id_num
         WHERE p.data_pedido <> CASE WHEN p.sistema_origem = 'ECOM'
                                     THEN (o.placed_at AT TIME ZONE '{FUSO}')::date
                                     ELSE l.dt_pedido::date END"""), 0,
             "RDT-09: legado lido como hora local; e-commerce convertido de UTC para hora local")
    qa.igual("pedido: data_entrega com sentinela 1900 remanescente", escalar(eng, """
        SELECT COUNT(*) FROM cnf.pedido WHERE data_entrega < DATE '2000-01-01'"""), 0,
             "RDT-08: 1900-01-01 virou NULL + entrega_sem_data")
    qa.igual("pedido: soma do frete difere da origem (frete negativo preservado)", escalar(eng, """
        SELECT (SELECT SUM(valor_frete) FROM cnf.pedido)
             - (SELECT SUM(valor_frete) FROM stg.legado_pedidos)
             - (SELECT SUM(freight_amount) FROM stg.ecommerce_orders)"""), 0,
             "RDT-06: o frete negativo entra como gravado, sem correção")
    qa.igual("item: descontos negativos remanescentes", escalar(eng, """
        SELECT COUNT(*) FROM cnf.item WHERE valor_desconto < 0"""), 0,
             "RDT-06: o sentinela -1 virou 0 com indicador")
    fora = escalar(eng, """
        SELECT COUNT(*) FROM cnf.pedido
         WHERE data_pedido < DATE '2022-12-01' OR data_pedido > DATE '2026-03-31'
            OR data_entrega < DATE '2022-12-01' OR data_entrega > DATE '2026-03-31'""")
    qa.igual("pedido: datas fora do intervalo de dim_tempo", fora, 0,
             "toda data tem linha em dw.dim_tempo (2022-12-01 a 2026-03-31)")


# ===========================================================================
# DECISÃO 6 — CHAVES DAS FONTES DE ARQUIVO                          (RDT-13)
# ===========================================================================
MOTIVOS = {
    "atraso na entrega": "ATRASO_ENTREGA", "atraso entrega": "ATRASO_ENTREGA",
    "produto avariado": "PRODUTO_AVARIADO_OU_DEFEITUOSO",
    "produto com defeito": "PRODUTO_AVARIADO_OU_DEFEITUOSO",
    "produto nao recebido": "PRODUTO_NAO_RECEBIDO",
    "devolucao": "DEVOLUCAO", "troca": "TROCA", "troca de produto": "TROCA",
    "estorno nao realizado": "ESTORNO_NAO_REALIZADO",
    "cancelamento a pedido do cliente": "CANCELAMENTO_CLIENTE",
    "cancelamento cliente": "CANCELAMENTO_CLIENTE",
    "cobranca indevida": "COBRANCA_INDEVIDA",
    "endereco incorreto": "ENDERECO_INCORRETO",
    "duvida sobre pagamento": "DUVIDA_PAGAMENTO", "elogio": "ELOGIO",
}


def liga_sac_e_avaliacoes(qa):
    """
    SAC: liga ao CLIENTE pelo CPF (todo registro tem 11 dígitos). O pedido
    declarado não se sustenta (o CPF do atendimento é o do dono do pedido em 1
    de 96.140 casos) e fica só como referência declarada; pedido_key = NULL.
    Avaliações: o NDJSON não traz CPF, logo não há ligação com cliente; o pedido
    referenciado não é confiável (o produto avaliado está nos itens do pedido
    em 80 de 160.000). Liga-se apenas ao PRODUTO, pelo SKU.
    """
    eng = eng_dw()

    # ------------------------------------------------------------------ SAC
    sac = pd.read_sql("SELECT * FROM stg.sac_atendimentos ORDER BY _linha_origem", eng)
    sac["cpf_digitos"] = sac.cpf_cliente.map(so_digitos)
    sac["cpf_valido"] = sac.cpf_digitos.map(cpf_valido)
    cpfs = pd.read_sql("SELECT cliente_key, cpf_digitos FROM cnf.cliente_cpf", eng)
    por_cpf = cpfs.groupby("cpf_digitos").cliente_key.agg(lambda s: sorted(set(s)))
    chaves = sac.cpf_digitos.map(por_cpf)
    sac["cliente_key"] = [c[0] if isinstance(c, list) and len(c) == 1 else None for c in chaves]
    sac["cpf_ambiguo"] = [isinstance(c, list) and len(c) > 1 for c in chaves]

    sac["data_abertura_d"] = pd.to_datetime(sac.data_abertura, format="%d/%m/%Y", errors="coerce").dt.date
    sac["data_fechamento_d"] = pd.to_datetime(sac.data_fechamento, format="%d/%m/%Y", errors="coerce").dt.date
    sac["horas_resolucao"] = pd.to_numeric(sac.tempo_resolucao_horas.str.replace(",", ".", regex=False),
                                           errors="coerce")
    sac["fechamento_ausente"] = sac.data_fechamento.str.strip() == ""
    sac["horas_negativas"] = sac.horas_resolucao < 0
    sac.loc[sac.horas_negativas, "horas_resolucao"] = None
    sac["nota_bruta"] = sac.nota_satisfacao.str.strip()
    sac["nota_zero"] = sac.nota_bruta == "0"
    nota = pd.to_numeric(sac.nota_bruta, errors="coerce")
    sac["nota_satisfacao_c"] = nota.where(nota.between(1, 5))
    sac["canal_c"] = sac.canal.str.strip().str.upper()
    limpo = sac.motivo.map(lambda m: re.sub(r"\s+", " ", m or "").strip())
    sac["reiterou_contato"] = limpo.str.contains(r"obs:\s*cliente reiterou", case=False, regex=True)
    base = limpo.map(lambda m: normaliza_minusculo(re.sub(r"\s*obs:.*$", "", m, flags=re.I)))
    sac["motivo_conformado"] = base.map(MOTIVOS)
    qa.igual("sac: motivos sem regra de conformação", int(sac.motivo_conformado.isna().sum()), 0,
             f"motivos novos: {sorted(set(base[sac.motivo_conformado.isna()]))[:5]}")

    sac["duplicada"] = sac.duplicated("protocolo", keep="first")
    colunas_iguais = ["protocolo", "origem_sistema", "id_pedido_origem", "cpf_cliente",
                      "data_abertura", "data_fechamento", "canal", "motivo",
                      "nota_satisfacao", "tempo_resolucao_horas"]
    n_distintas = len(sac[colunas_iguais].drop_duplicates())
    qa.igual("sac: protocolos repetidos com conteúdo diferente",
             int(sac.protocolo.nunique() - n_distintas), 0,
             "a repetição é de linhas idênticas; manter a primeira não descarta informação")

    saida = sac[~sac.duplicada][[
        "protocolo", "cliente_key", "cpf_digitos", "cpf_valido", "cpf_ambiguo",
        "origem_sistema", "id_pedido_origem", "data_abertura_d", "data_fechamento_d",
        "canal_c", "motivo", "motivo_conformado", "reiterou_contato",
        "nota_satisfacao_c", "nota_zero", "horas_resolucao", "fechamento_ausente",
        "horas_negativas", "_linha_origem"]].rename(columns={
            "data_abertura_d": "data_abertura", "data_fechamento_d": "data_fechamento",
            "canal_c": "canal", "nota_satisfacao_c": "nota_satisfacao"})
    saida["pedido_key"] = None            # decisão RDT-13: a ligação ao pedido não se sustenta
    saida["cliente_key"] = saida.cliente_key.astype("Int64")
    grava(saida, eng, "atendimento")

    qa.unico("sac: protocolo único após remover linhas idênticas", saida.protocolo)
    qa.igual("sac: linhas na stg == atendimentos + repetidas", len(saida) + int(sac.duplicada.sum()),
             len(sac))
    qa.igual("sac: data_abertura inválida", int(saida.data_abertura.isna().sum()), 0,
             "formato dd/mm/aaaa")
    qa.igual("sac: nota fora de 1..5 após conformar",
             int(((saida.nota_satisfacao < 1) | (saida.nota_satisfacao > 5)).sum()), 0, "RDT-08")
    qa.igual("sac: horas_resolucao negativas após conformar",
             int((saida.horas_resolucao < 0).sum()), 0, "RDT-08")

    # ------------------------------------------------------------ AVALIAÇÕES
    av = pd.read_sql("SELECT * FROM stg.avaliacoes_marketplace ORDER BY _linha_origem", eng)
    ts = av.submitted_at
    av["offset_ausente"] = ~ts.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True)
    # sem offset -> hora local (todos os offsets explícitos do arquivo são -03:00)
    instante = pd.to_datetime(ts.where(~av.offset_ausente, ts + "-03:00"), utc=True, format="ISO8601")
    av["enviada_em"] = instante.dt.tz_convert(FUSO).dt.tz_localize(None)
    av["data_avaliacao"] = av.enviada_em.dt.date
    av["rating_n"] = pd.to_numeric(av.rating, errors="coerce")
    # o tipo original fica em _tipos_json (só os não-texto são listados)
    rating_numerico = av._tipos_json.map(lambda j: isinstance(j, dict) and "rating" in j)
    av["rating_chegou_como_texto"] = av.rating.notna() & ~rating_numerico
    av["rating_ausente"] = av.rating.isna()
    av["nota"] = av.rating_n.where(av.rating_n.between(1, 5))
    av["compra_verificada"] = av.verified_purchase.map({"true": True, "false": False})
    av["votos_uteis"] = pd.to_numeric(av.helpful_votes, errors="coerce")
    ref = av.order_ref.str.extract(r"^(LEG|ECOM)-(\d+)$")
    av["ref_sistema"] = ref[0].map({"LEG": "LEGADO", "ECOM": "ECOM"})
    av["ref_id"] = pd.to_numeric(ref[1])
    sku = av.product_sku.str.extract(r"^(SKU|LEG)-(\d+)$")
    prod = pd.read_sql("SELECT produto_key, sku, id_legado FROM cnf.produto", eng)
    k_sku = dict(zip(prod.sku, prod.produto_key))
    k_leg = dict(zip(prod.id_legado.dropna().astype(int), prod.produto_key[prod.id_legado.notna()]))
    av["produto_key"] = [k_sku.get(s) if p == "SKU" else k_leg.get(int(n))
                         for s, p, n in zip(av.product_sku, sku[0], sku[1])]
    av["produto_key"] = av.produto_key.astype("Int64")

    saida = av[["review_id", "produto_key", "ref_sistema", "ref_id", "enviada_em",
                "data_avaliacao", "offset_ausente", "nota", "rating_ausente",
                "rating_chegou_como_texto", "compra_verificada", "votos_uteis",
                "_linha_origem"]].copy()
    saida["pedido_key"] = None            # decisão RDT-13
    grava(saida, eng, "avaliacao")

    qa.unico("avaliação: review_id único", saida.review_id)
    qa.igual("avaliação: sem produto_key", int(saida.produto_key.isna().sum()), 0,
             "o SKU de toda avaliação existe (SKU-n no e-commerce, LEG-n no legado)")
    qa.igual("avaliação: referência de pedido fora do formato", int(saida.ref_id.isna().sum()), 0)
    qa.igual("avaliação: linhas == stg", len(saida), len(av))
    qa.igual("avaliação: nota fora de 1..5 após conformar",
             int(((saida.nota < 1) | (saida.nota > 5)).sum()), 0, "RDT-08")


if __name__ == "__main__":
    eng = eng_dw()
    qa = Suite(etapa="02_transformacao")
    unifica_clientes(qa)
    conforma_status(qa)
    conforma_valores(qa)
    conforma_categorias(qa)
    trata_datas_e_ausencias(qa)
    monta_pedido(qa)
    liga_sac_e_avaliacoes(qa)

    roda(eng, "DELETE FROM qa.execucao_assercao WHERE etapa = :e", e=qa.etapa)
    qa.registrar(eng)
    if qa.imprimir():
        print("Há asserções em falha. Isso não impede seguir, mas precisa "
              "aparecer no RDT com explicação.")
