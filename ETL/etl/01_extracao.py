#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETAPA 1 — EXTRAÇÃO

Objetivo: trazer as quatro fontes para o esquema `stg` do DW, SEM transformar
significado. Renomear, converter tipo e decidir o que é nulo vem depois.

Regra da camada stg (seção 2.3 do referencial):
  · nomes de coluna espelham a origem (apenas em minúsculas, para dispensar
    aspas nas consultas; o nome da tabela leva o prefixo da fonte);
  · nenhum valor é descartado, corrigido ou reinterpretado;
  · acrescentam-se apenas metadados de procedência:
        _fonte           de onde veio
        _extraido_em     quando
        _linha_origem    posição na origem (ordem da chave primária nos bancos;
                         número do registro no CSV; linha física no NDJSON)

CARGA COMPLETA (RDT-01). Esta etapa lê cada tabela inteira, sem LIMIT. O
`00_perfilamento.py` usava `LIMIT 200000` e por isso trabalhava com amostra:
ITENS_PEDIDO, orders e order_item ficavam truncados. Aqui não há amostra, e a
asserção de contagem prova isso. As origens não têm coluna de atualização
(nenhum `updated_at`), logo não há critério de mudança para uma carga
incremental. Cada execução recria as tabelas de stg (DROP + CREATE), o que
torna a etapa idempotente.

FUSO (RDT-09). A stg NÃO padroniza fuso. Os TIMESTAMPTZ do e-commerce entram
com o instante exato (sessão em UTC nas duas pontas); os DATETIME do legado
entram sem fuso. A régua única é escolhida na etapa 2.

    docker compose exec etl python 01_extracao.py
"""

import csv
import io
import json
import os
from datetime import datetime, timezone

import pandas as pd
import pymysql
from sqlalchemy import text

from config import (ARQ_AVALIACOES, ARQ_SAC, DIR_SAIDA, eng_dw, eng_mysql,
                    eng_origem)
from qualidade.assercoes import Suite

AGORA = datetime.now(timezone.utc)
AGORA_TXT = AGORA.strftime("%Y-%m-%d %H:%M:%S+00")
LOTE = 50_000          # leitura do MySQL em blocos: a base não cabe confortavelmente na RAM
DIR_EXTRACAO = os.path.join(DIR_SAIDA, "extracao")

# ---------------------------------------------------------------------------
# Esquema da stg: (coluna, tipo no PostgreSQL). Tipos espelham a origem;
# VARCHAR/CHAR viram TEXT (o MySQL já remove espaços finais de CHAR).
# ---------------------------------------------------------------------------
LEGADO = {
    # tabela_stg: (tabela na origem, chave de ordenação, colunas)
    "legado_clientes": ("CLIENTES", "ID_CLIENTE", [
        ("id_cliente", "integer"), ("nome", "text"), ("cpf", "text"),
        ("email", "text"), ("dt_cadastro", "date"), ("cidade", "text"),
        ("uf", "text"), ("telefone", "text")]),
    "legado_produtos": ("PRODUTOS", "ID_PRODUTO", [
        ("id_produto", "integer"), ("descricao", "text"), ("categoria", "text"),
        ("preco_tabela", "numeric(10,2)"), ("ativo", "text")]),
    "legado_pedidos": ("PEDIDOS", "ID_PEDIDO", [
        ("id_pedido", "integer"), ("id_cliente", "integer"),
        ("dt_pedido", "timestamp"), ("dt_entrega", "timestamp"),
        ("status", "text"), ("valor_total", "numeric(10,2)"),
        ("valor_frete", "numeric(10,2)"), ("canal", "text")]),
    "legado_itens_pedido": ("ITENS_PEDIDO", "ID_ITEM", [
        ("id_item", "integer"), ("id_pedido", "integer"),
        ("id_produto", "integer"), ("qtd", "integer"),
        ("vl_unitario", "numeric(10,2)"), ("vl_desconto", "numeric(10,2)")]),
}

ECOMMERCE = {
    "ecommerce_customer": ("customer", "customer_id", [
        ("customer_id", "bigint"), ("full_name", "text"), ("tax_id", "text"),
        ("email", "text"), ("created_at", "timestamptz"), ("city", "text"),
        ("state", "text"), ("phone", "text")]),
    "ecommerce_category": ("category", "category_id", [
        ("category_id", "integer"), ("name", "text"), ("parent_id", "integer")]),
    "ecommerce_product": ("product", "product_id", [
        ("product_id", "bigint"), ("sku", "text"), ("title", "text"),
        ("category_id", "integer"), ("list_price", "numeric(12,2)"),
        ("active", "boolean")]),
    "ecommerce_orders": ("orders", "order_id", [
        ("order_id", "bigint"), ("customer_id", "bigint"),
        ("placed_at", "timestamptz"), ("delivered_at", "timestamptz"),
        ("status", "text"), ("total_amount", "numeric(12,2)"),
        ("freight_amount", "numeric(12,2)"), ("channel", "text")]),
    "ecommerce_order_item": ("order_item", "order_item_id", [
        ("order_item_id", "bigint"), ("order_id", "bigint"),
        ("product_id", "bigint"), ("quantity", "integer"),
        ("unit_price", "numeric(12,2)"), ("discount", "numeric(12,2)")]),
}

# SAC: tudo texto. A tipagem (data dd/mm/aaaa, decimal com vírgula, nota) é
# transformação, e portanto fica para a etapa 2.
COLUNAS_SAC = ["protocolo", "origem_sistema", "id_pedido_origem", "cpf_cliente",
               "data_abertura", "data_fechamento", "canal", "motivo",
               "nota_satisfacao", "tempo_resolucao_horas"]

# NDJSON: o aninhamento vira colunas explícitas. Caminho no JSON -> coluna.
CAMINHOS_AVAL = [
    ("review_id", ("review_id",)),
    ("order_ref", ("order", "ref")),
    ("order_channel", ("order", "channel")),
    ("product_sku", ("product", "sku")),
    ("submitted_at", ("submitted_at",)),
    ("rating", ("rating",)),
    ("title", ("title",)),
    ("comment", ("comment",)),
    ("verified_purchase", ("verified_purchase",)),
    ("helpful_votes", ("helpful_votes",)),
]
META = [("_fonte", "text"), ("_extraido_em", "timestamptz"),
        ("_linha_origem", "bigint")]

CONTAGENS = []         # (fonte, tabela, linhas_origem, linhas_stg)


# ---------------------------------------------------------------------------
# Infraestrutura
# ---------------------------------------------------------------------------
def cria_tabela(cx, tabela, colunas, extras=()):
    """Recria stg.<tabela>. `extras` são colunas de procedência adicionais."""
    cols = ", ".join(f"{n} {t}" for n, t in list(colunas) + list(extras) + META)
    cx.execute(text(f"DROP TABLE IF EXISTS stg.{tabela}"))
    cx.execute(text(f"CREATE TABLE stg.{tabela} ({cols})"))


def esc(v):
    """Valor -> campo do formato texto do COPY (NULL = \\N)."""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    s = str(v)
    return (s.replace("\\", "\\\\").replace("\t", "\\t")
             .replace("\n", "\\n").replace("\r", "\\r"))


def copia(dw, tabela, nomes, buffer):
    buffer.seek(0)
    with dw.cursor() as cur:
        cur.copy_expert(f"COPY stg.{tabela} ({', '.join(nomes)}) FROM STDIN", buffer)


def contagem_stg(dw_eng, tabela):
    with dw_eng.connect() as cx:
        return cx.execute(text(f"SELECT COUNT(*) FROM stg.{tabela}")).scalar()


def registra_contagem(fonte, tabela, origem, stg):
    CONTAGENS.append((fonte, tabela, int(origem), int(stg)))
    print(f"  {fonte}.{tabela}: {stg:>10,} linhas na stg (origem {origem:,})".replace(",", "."))


# ---------------------------------------------------------------------------
# Origens relacionais
# ---------------------------------------------------------------------------
def extrai_mysql(qa):
    eng, dw_eng = eng_mysql(), eng_dw()
    print("MySQL legado (latin1, vindo de config.py):")
    with dw_eng.begin() as cx:
        for tab, (_, _, cols) in LEGADO.items():
            cria_tabela(cx, tab, cols)

    conn = eng.raw_connection()          # pymysql, charset do DSN (latin1)
    dw = dw_eng.raw_connection()
    try:
        for tab, (orig, pk, cols) in LEGADO.items():
            nomes = [c for c, _ in cols]
            sel = ", ".join(c.upper() for c in nomes)
            cur = conn.cursor(pymysql.cursors.SSCursor)   # leitura em fluxo
            cur.execute(f"SELECT {sel} FROM {orig} ORDER BY {pk}")
            ordem = 0
            while True:
                bloco = cur.fetchmany(LOTE)
                if not bloco:
                    break
                buf = io.StringIO()
                for linha in bloco:
                    ordem += 1
                    campos = [esc(v) for v in linha] + ["legado", AGORA_TXT, str(ordem)]
                    buf.write("\t".join(campos) + "\n")
                copia(dw, tab, nomes + [n for n, _ in META], buf)
            cur.close()
            dw.commit()
            with eng.connect() as cx:
                n_orig = cx.execute(text(f"SELECT COUNT(*) FROM {orig}")).scalar()
            registra_contagem("legado", orig, n_orig, contagem_stg(dw_eng, tab))
    finally:
        conn.close()
        dw.close()


def extrai_postgres(qa):
    eng, dw_eng = eng_origem(), eng_dw()
    print("PostgreSQL e-commerce (shop):")
    with dw_eng.begin() as cx:
        for tab, (_, _, cols) in ECOMMERCE.items():
            cria_tabela(cx, tab, cols)

    conn = eng.raw_connection()
    dw = dw_eng.raw_connection()
    try:
        with conn.cursor() as c:
            # Fuso da sessão em UTC: o COPY escreve o instante com offset +00,
            # e a stg recebe o mesmo instante. Nenhuma conversão de fuso aqui.
            c.execute("SET TIME ZONE 'UTC'")
        with dw.cursor() as c:
            c.execute("SET TIME ZONE 'UTC'")
        for tab, (orig, pk, cols) in ECOMMERCE.items():
            nomes = [c for c, _ in cols]
            bruto = io.StringIO()
            with conn.cursor() as cur:
                cur.copy_expert(f"COPY (SELECT {', '.join(nomes)} FROM shop.{orig} "
                                f"ORDER BY {pk}) TO STDOUT", bruto)
            bruto.seek(0)
            buf = io.StringIO()
            for ordem, linha in enumerate(bruto, start=1):
                buf.write(linha.rstrip("\n") + f"\tecommerce\t{AGORA_TXT}\t{ordem}\n")
            copia(dw, tab, nomes + [n for n, _ in META], buf)
            dw.commit()
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM shop.{orig}")
                n_orig = cur.fetchone()[0]
            registra_contagem("ecommerce", orig, n_orig, contagem_stg(dw_eng, tab))
        conn.rollback()
    finally:
        conn.close()
        dw.close()


# ---------------------------------------------------------------------------
# Origens em arquivo
# ---------------------------------------------------------------------------
def extrai_sac(qa):
    """CSV do SAC: sep=';', latin-1, tudo como texto, nenhuma linha removida."""
    dw_eng = eng_dw()
    print("SAC (CSV latin-1):")
    # dtype=str + keep_default_na=False: nada vira NaN, '' continua ''. O parser
    # do pandas respeita as aspas e as quebras de linha dentro dos campos.
    df = pd.read_csv(ARQ_SAC, sep=";", encoding="latin-1", dtype=str,
                     keep_default_na=False, na_filter=False)
    assert list(df.columns) == COLUNAS_SAC, df.columns.tolist()

    # Contagem independente: outro parser (módulo csv), outro caminho de código.
    with open(ARQ_SAC, encoding="latin-1", newline="") as f:
        n_arquivo = sum(1 for _ in csv.reader(f, delimiter=";")) - 1   # sem cabeçalho

    with dw_eng.begin() as cx:
        cria_tabela(cx, "sac_atendimentos", [(c, "text") for c in COLUNAS_SAC])
    buf = io.StringIO()
    for ordem, linha in enumerate(df.itertuples(index=False, name=None), start=1):
        buf.write("\t".join([esc(v) for v in linha] + ["sac", AGORA_TXT, str(ordem)]) + "\n")
    dw = dw_eng.raw_connection()
    try:
        copia(dw, "sac_atendimentos", COLUNAS_SAC + [n for n, _ in META], buf)
        dw.commit()
    finally:
        dw.close()
    registra_contagem("sac", "atendimentos_sac.csv (registros)", n_arquivo,
                      contagem_stg(dw_eng, "sac_atendimentos"))


def extrai_avaliacoes(qa):
    """NDJSON: uma linha por objeto; chave omitida vira NULL e é contada."""
    dw_eng = eng_dw()
    print("Avaliações (NDJSON):")
    nomes = [n for n, _ in CAMINHOS_AVAL]
    extras = [("_chaves_ausentes", "text"), ("_chaves_nulas", "text"),
              ("_tipos_json", "jsonb")]
    with dw_eng.begin() as cx:
        cria_tabela(cx, "avaliacoes_marketplace", [(n, "text") for n in nomes], extras)

    buf = io.StringIO()
    ausentes, nulas = dict.fromkeys(nomes, 0), dict.fromkeys(nomes, 0)
    com_ausente = n_linhas = n_nao_vazias = 0
    with open(ARQ_AVALIACOES, encoding="utf-8") as f:
        for n_fisica, bruto in enumerate(f, start=1):
            n_linhas += 1
            if not bruto.strip():
                continue
            n_nao_vazias += 1
            obj = json.loads(bruto)
            valores, aus, nul, tipos = [], [], [], {}
            for nome, caminho in CAMINHOS_AVAL:
                v, achou = obj, True
                for k in caminho:
                    if isinstance(v, dict) and k in v:
                        v = v[k]
                    else:
                        achou = False
                        break
                if not achou:
                    aus.append(nome)
                    ausentes[nome] += 1
                    valores.append(None)
                elif v is None:
                    nul.append(nome)
                    nulas[nome] += 1
                    valores.append(None)
                else:
                    # tipo original preservado à parte: rating 5 e "5" ficam iguais
                    # como texto, e a diferença é informação da fonte.
                    if not isinstance(v, str):
                        tipos[nome] = type(v).__name__
                    valores.append(json.dumps(v) if isinstance(v, bool) else v)
            com_ausente += bool(aus)
            campos = [esc(v) for v in valores]
            campos += [esc(",".join(aus) or None), esc(",".join(nul) or None),
                       esc(json.dumps(tipos, sort_keys=True) if tipos else None),
                       "avaliacoes", AGORA_TXT, str(n_fisica)]
            buf.write("\t".join(campos) + "\n")

    dw = dw_eng.raw_connection()
    try:
        copia(dw, "avaliacoes_marketplace",
              nomes + [n for n, _ in extras] + [n for n, _ in META], buf)
        dw.commit()
    finally:
        dw.close()
    registra_contagem("avaliacoes", "avaliacoes_marketplace.json (objetos)",
                      n_nao_vazias, contagem_stg(dw_eng, "avaliacoes_marketplace"))

    # Contagem de linhas com chave ausente (exigência da extração).
    linhas = [dict(caminho=n, linhas_com_chave_ausente=ausentes[n],
                   linhas_com_valor_nulo=nulas[n]) for n in nomes]
    linhas.append(dict(caminho="(qualquer chave)",
                       linhas_com_chave_ausente=com_ausente, linhas_com_valor_nulo=0))
    os.makedirs(DIR_EXTRACAO, exist_ok=True)
    pd.DataFrame(linhas).to_csv(
        os.path.join(DIR_EXTRACAO, "ndjson_chaves_ausentes.csv"), index=False)
    with dw_eng.begin() as cx:
        cx.execute(text("DROP TABLE IF EXISTS stg.extracao_chaves_ausentes"))
        cx.execute(text("CREATE TABLE stg.extracao_chaves_ausentes ("
                        "caminho text, linhas_com_chave_ausente bigint, "
                        "linhas_com_valor_nulo bigint)"))
        for r in linhas:
            cx.execute(text("INSERT INTO stg.extracao_chaves_ausentes VALUES "
                            "(:caminho, :a, :n)"),
                       dict(caminho=r["caminho"], a=r["linhas_com_chave_ausente"],
                            n=r["linhas_com_valor_nulo"]))
    print(f"  linhas com ao menos uma chave ausente: {com_ausente:,}".replace(",", "."))
    return n_linhas, n_nao_vazias


# ---------------------------------------------------------------------------
# Asserções: extração que perde linha ou valor em silêncio é o defeito mais
# caro do pipeline.
# ---------------------------------------------------------------------------
def tipo_numerico(t):
    return t.startswith(("integer", "bigint", "numeric"))


def confere_colunas(qa, dw_eng, eng, tab, orig, cols, sql_texto_origem):
    """Para cada tabela: COUNT(coluna) e SUM(coluna numérica) iguais na origem e na stg."""
    div_cont, div_soma = [], []
    for c, t in cols:
        col_o = c.upper() if sql_texto_origem else c
        qs = f"COUNT({col_o})" + (f", SUM({col_o})" if tipo_numerico(t) else "")
        with eng.connect() as cx:
            o = cx.execute(text(f"SELECT {qs} FROM {orig}")).fetchone()
        with dw_eng.connect() as cx:
            s = cx.execute(text(
                f"SELECT " + (f"COUNT({c}), SUM({c})" if tipo_numerico(t) else f"COUNT({c})")
                + f" FROM stg.{tab}")).fetchone()
        if o[0] != s[0]:
            div_cont.append(c)
        if tipo_numerico(t) and (o[1] != s[1]):
            div_soma.append(c)
    qa.igual(f"colunas com contagem não nula divergente: {tab}", len(div_cont), 0,
             f"COUNT(coluna) na origem x stg; divergentes: {div_cont}")
    qa.igual(f"colunas com soma divergente: {tab}", len(div_soma), 0,
             f"SUM(coluna numérica) na origem x stg; divergentes: {div_soma}")


def verifica(qa):
    dw_eng = eng_dw()
    # 1. contagem por tabela == contagem na origem (COUNT(*) feito na própria origem)
    for fonte, tabela, n_orig, n_stg in CONTAGENS:
        qa.igual(f"linhas {fonte}.{tabela}", n_stg, n_orig,
                 "carga completa: stg tem o mesmo número de registros da origem")

    # 2. COUNT(coluna) e SUM(coluna) por coluna, nas tabelas relacionais
    eng_m, eng_p = eng_mysql(), eng_origem()
    for tab, (orig, _, cols) in LEGADO.items():
        confere_colunas(qa, dw_eng, eng_m, tab, orig, cols, True)
    for tab, (orig, _, cols) in ECOMMERCE.items():
        confere_colunas(qa, dw_eng, eng_p, tab, f"shop.{orig}", cols, False)

    # 3. acentos: a leitura latin1 não pode ter produzido mojibake nem U+FFFD
    with dw_eng.connect() as cx:
        moj = cx.execute(text(
            "SELECT (SELECT COUNT(*) FROM stg.legado_clientes WHERE nome ~ 'Ã[^A-Za-z ]|Â[^A-Za-z ]' "
            "OR cidade ~ 'Ã[^A-Za-z ]|Â[^A-Za-z ]' OR nome LIKE '%' || chr(65533) || '%') + "
            "(SELECT COUNT(*) FROM stg.legado_produtos WHERE descricao ~ 'Ã[^A-Za-z ]|Â[^A-Za-z ]' "
            "OR categoria ~ 'Ã[^A-Za-z ]|Â[^A-Za-z ]') + "
            "(SELECT COUNT(*) FROM stg.sac_atendimentos WHERE motivo LIKE '%' || chr(65533) || '%')"
        )).scalar()
    qa.igual("linhas com acento corrompido (legado e SAC)", moj, 0,
             "conexão latin1 do config.py e CSV em latin-1 devem preservar os acentos")

    # 4. identificadores
    stg_aval = pd.read_sql(text("SELECT review_id FROM stg.avaliacoes_marketplace"), dw_eng)
    stg_sac = pd.read_sql(text("SELECT protocolo FROM stg.sac_atendimentos"), dw_eng)
    qa.unico("review_id das avaliações", stg_aval["review_id"],
             "cada objeto do NDJSON tem review_id próprio")
    qa.igual("protocolo do SAC vazio", int((stg_sac["protocolo"] == "").sum()), 0,
             "o protocolo identifica o atendimento; as linhas repetidas do SAC "
             "(1.140) ficam na stg e são tratadas na etapa 2")


def grava_contagens(dw_eng):
    """Contagem por tabela em stg.extracao_contagem e em saida/extracao/."""
    df = pd.DataFrame(CONTAGENS, columns=["fonte", "tabela", "linhas_origem", "linhas_stg"])
    df["iguais"] = df["linhas_origem"] == df["linhas_stg"]
    os.makedirs(DIR_EXTRACAO, exist_ok=True)
    df.to_csv(os.path.join(DIR_EXTRACAO, "contagens_stg.csv"), index=False)
    with dw_eng.begin() as cx:
        cx.execute(text("DROP TABLE IF EXISTS stg.extracao_contagem"))
        cx.execute(text("CREATE TABLE stg.extracao_contagem (fonte text, tabela text, "
                        "linhas_origem bigint, linhas_stg bigint, iguais boolean)"))
    df.to_sql("extracao_contagem", dw_eng, schema="stg", if_exists="append", index=False)
    print(f"  total na stg: {int(df['linhas_stg'].sum()):,}".replace(",", "."))


if __name__ == "__main__":
    qa = Suite(etapa="01_extracao")
    dw_eng = eng_dw()
    extrai_mysql(qa)
    extrai_postgres(qa)
    extrai_sac(qa)
    extrai_avaliacoes(qa)
    grava_contagens(dw_eng)
    verifica(qa)

    # Idempotência do registro: sem isto, cada reexecução duplicaria as asserções.
    with dw_eng.begin() as cx:
        cx.execute(text("DELETE FROM qa.execucao_assercao WHERE etapa = :e"),
                   dict(e=qa.etapa))
    qa.registrar(dw_eng)
    qa.imprimir()
