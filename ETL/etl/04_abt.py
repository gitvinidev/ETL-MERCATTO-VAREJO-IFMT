#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETAPA 4 — TABELA-BASE DE ANÁLISE (ABT) E O EXPERIMENTO DE VAZAMENTO

Pergunta analítica:
    dado o comportamento do cliente ATÉ 2025-06-30, ele comprará de novo
    entre 2025-07-01 e 2025-09-28?

Esta etapa produz DUAS versões da mesma tabela:

    --correta     todos os atributos calculados apenas com dados até a data
                  de corte. É a versão que vale.

    --vazamento   a mesma coisa, só que com dois ou três atributos calculados
                  sobre a base inteira. É a versão errada, que vocês vão
                  construir de propósito, rodar no Orange e comparar.

O objetivo do experimento não é ver um número maior. É medir a distância
entre um resultado que parece excelente e um resultado que é válido —
e descobrir que a diferença entre os dois cabe em uma linha de código.

    docker compose exec etl python 04_abt.py --correta
    docker compose exec etl python 04_abt.py --vazamento
"""

import argparse
import os

import numpy as np
import pandas as pd
from sqlalchemy import text

from config import DATA_CORTE, DATA_FIM_ALVO, DIR_SAIDA, eng_dw
from qualidade.assercoes import Suite

DIR_ABT = os.path.join(DIR_SAIDA, "abt")


# ---------------------------------------------------------------------------
# ALVO — este está pronto, e é o único ponto do pipeline em que é legítimo
# olhar para o futuro, porque é exatamente isso que se quer prever.
# ---------------------------------------------------------------------------
SQL_ALVO = f"""
WITH base AS (
    SELECT DISTINCT c.cliente_sk
    FROM dw.dim_cliente c
    JOIN dw.fato_pedido p ON p.cliente_sk = c.cliente_sk
    WHERE p.data_pedido_sk <= DATE '{DATA_CORTE}'
),
compras_na_janela AS (
    SELECT DISTINCT p.cliente_sk
    FROM dw.fato_pedido p
    JOIN dw.dim_status s ON s.status_sk = p.status_sk
    WHERE p.data_pedido_sk >  DATE '{DATA_CORTE}'
      AND p.data_pedido_sk <= DATE '{DATA_FIM_ALVO}'
      AND s.status_conformado <> 'CANCELADO'   -- ajuste ao SEU mapeamento
)
SELECT b.cliente_sk,
       DATE '{DATA_CORTE}' AS data_corte,
       CASE WHEN j.cliente_sk IS NOT NULL THEN 1 ELSE 0 END AS alvo_recompra_90d
FROM base b
LEFT JOIN compras_na_janela j ON j.cliente_sk = b.cliente_sk
"""


# ---------------------------------------------------------------------------
# ATRIBUTOS DA VERSÃO CORRETA. Todo agregado olha só pedidos com
# data_pedido_sk <= data_corte (30/06/2025). "Efetivo" = status conformado
# diferente de CANCELADO (RDT-04). Ausência é NULL, nunca 0 (NaN não é zero);
# onde 0 é a contagem verdadeira (frequência, atendimentos), vale 0.
#
# Limitações declaradas (RDT-14):
#   · DT_CADASTRO e DT_PEDIDO começam em 2023-01-01; o histórico anterior não
#     foi entregue. "tempo_como_cliente_dias" é tempo DESDE O PRIMEIRO PEDIDO
#     OBSERVADO e subestima o relacionamento real (censura à esquerda).
#   · O status do pedido é o do retrato dos dados; a origem não guarda a data
#     do cancelamento. Assumimos que o status gravado já valia no corte.
#   · Nenhum atributo vem de dim_cliente (cadastro atualizado depois do corte).
# ---------------------------------------------------------------------------
ATRIBUTOS = [
    # nome, tipo SQL, regra, tratamento de ausente
    ("recencia_dias", "INT",
     "dias entre o último pedido efetivo e a data de corte", "NULL se o cliente só tem pedidos cancelados até o corte"),
    ("frequencia_pedidos", "INT",
     "nº de pedidos efetivos com data_pedido <= corte", "0 é a contagem verdadeira"),
    ("valor_monetario", "NUMERIC(14,2)",
     "soma de valor_total dos pedidos efetivos até o corte (mercadoria - desconto + frete)", "0 se não há pedido efetivo"),
    ("ticket_medio", "NUMERIC(14,2)",
     "valor_monetario / frequencia_pedidos", "NULL se frequencia_pedidos = 0"),
    ("pedidos_ultimos_90d", "INT",
     "pedidos efetivos com data no intervalo (corte - 90 dias, corte]", "0 é a contagem verdadeira"),
    ("taxa_cancelamento", "NUMERIC(6,4)",
     "pedidos cancelados / todos os pedidos até o corte (status do retrato)", "sempre definida: todo cliente da ABT tem pedido"),
    ("pct_desconto", "NUMERIC(6,4)",
     "soma de valor_desconto / soma de valor_mercadoria, pedidos efetivos até o corte", "NULL se não há pedido efetivo"),
    ("prazo_medio_entrega", "NUMERIC(8,2)",
     "média de dias_entrega dos pedidos efetivos entregues com data de entrega <= corte", "NULL se nenhuma entrega registrada até o corte"),
    ("categorias_distintas", "INT",
     "nº de categoria_nivel1 distintas nos itens dos pedidos efetivos até o corte (nulas ignoradas, RDT-07)", "0 se nenhum item classificado"),
    ("canal_predominante", "TEXT",
     "canal conformado com mais pedidos efetivos até o corte (empate: ordem alfabética)", "NULL se não há pedido efetivo"),
    ("ambos_sistemas", "SMALLINT",
     "1 se há pedido efetivo nos dois sistemas até o corte, senão 0 (calculado dos fatos, não do cadastro)", "0 é o valor verdadeiro"),
    ("tempo_como_cliente_dias", "INT",
     "dias entre o primeiro pedido efetivo observado e o corte (histórico começa em 2023-01-01)", "NULL se não há pedido efetivo"),
    ("qtd_atendimentos_sac", "INT",
     "atendimentos do SAC ligados ao cliente pelo CPF com data_abertura <= corte", "0 é a contagem verdadeira"),
    ("nota_media_sac", "NUMERIC(4,2)",
     "média das notas 1 a 5 desses atendimentos (nota 0 e vazia ignoradas, RDT-08)", "NULL se não há nota"),
]
COLUNAS_ATR = [a[0] for a in ATRIBUTOS]


def sql_atributos(esquema, corte):
    """Atributos por cliente a partir do esquema `esquema` (dw, ou a cópia 'no corte')."""
    return f"""
    WITH p AS (
        SELECT f.pedido_sk, f.cliente_sk, f.sistema_origem, f.data_pedido_sk AS d,
               f.data_entrega_sk AS de, f.dias_entrega, f.valor_total, f.valor_mercadoria,
               f.valor_desconto, s.status_conformado AS st, c.canal_conformado AS canal
          FROM {esquema}.fato_pedido f
          JOIN {esquema}.dim_status s ON s.status_sk = f.status_sk
          JOIN {esquema}.dim_canal  c ON c.canal_sk  = f.canal_sk
         WHERE f.data_pedido_sk <= DATE '{corte}'
    ), pe AS (SELECT * FROM p WHERE st <> 'CANCELADO'),
    ped AS (
        SELECT cliente_sk,
               COUNT(*)                                          AS n_total,
               COUNT(*) FILTER (WHERE st = 'CANCELADO')          AS n_cancel,
               COUNT(*) FILTER (WHERE st <> 'CANCELADO')         AS freq,
               COALESCE(SUM(valor_total) FILTER (WHERE st <> 'CANCELADO'), 0) AS valor,
               MAX(d) FILTER (WHERE st <> 'CANCELADO')           AS ultima,
               MIN(d) FILTER (WHERE st <> 'CANCELADO')           AS primeira,
               COUNT(*) FILTER (WHERE st <> 'CANCELADO' AND d > DATE '{corte}' - 90) AS n90,
               SUM(valor_desconto)  FILTER (WHERE st <> 'CANCELADO') AS desc_,
               SUM(valor_mercadoria) FILTER (WHERE st <> 'CANCELADO') AS merc,
               AVG(dias_entrega) FILTER (WHERE st <> 'CANCELADO' AND de IS NOT NULL
                                           AND de <= DATE '{corte}')   AS prazo,
               COUNT(DISTINCT sistema_origem) FILTER (WHERE st <> 'CANCELADO') AS n_sis
          FROM p GROUP BY cliente_sk
    ), cat AS (
        SELECT pe.cliente_sk, COUNT(DISTINCT pr.categoria_nivel1) AS n_cat
          FROM pe
          JOIN {esquema}.fato_item_pedido i ON i.pedido_sk = pe.pedido_sk
          JOIN {esquema}.dim_produto pr ON pr.produto_sk = i.produto_sk
         GROUP BY pe.cliente_sk
    ), can AS (
        SELECT cliente_sk, canal FROM (
            SELECT cliente_sk, canal,
                   ROW_NUMBER() OVER (PARTITION BY cliente_sk ORDER BY COUNT(*) DESC, canal) AS r
              FROM pe GROUP BY cliente_sk, canal) x WHERE r = 1
    ), sac AS (
        SELECT cliente_sk, COUNT(*) AS n_sac,
               AVG(nota_satisfacao) FILTER (WHERE nota_satisfacao BETWEEN 1 AND 5) AS nota
          FROM {esquema}.fato_atendimento
         WHERE cliente_sk IS NOT NULL AND data_abertura_sk <= DATE '{corte}'
         GROUP BY cliente_sk
    )
    SELECT ped.cliente_sk,
           (DATE '{corte}' - ped.ultima)                                   AS recencia_dias,
           ped.freq                                                        AS frequencia_pedidos,
           ROUND(ped.valor, 2)                                             AS valor_monetario,
           CASE WHEN ped.freq > 0 THEN ROUND(ped.valor / ped.freq, 2) END  AS ticket_medio,
           ped.n90                                                         AS pedidos_ultimos_90d,
           ROUND(ped.n_cancel::numeric / ped.n_total, 4)                   AS taxa_cancelamento,
           CASE WHEN ped.merc > 0 THEN ROUND(ped.desc_ / ped.merc, 4) END  AS pct_desconto,
           ROUND(ped.prazo, 2)                                             AS prazo_medio_entrega,
           COALESCE(cat.n_cat, 0)                                          AS categorias_distintas,
           can.canal                                                       AS canal_predominante,
           (ped.n_sis = 2)::int                                            AS ambos_sistemas,
           (DATE '{corte}' - ped.primeira)                                 AS tempo_como_cliente_dias,
           COALESCE(sac.n_sac, 0)                                          AS qtd_atendimentos_sac,
           ROUND(sac.nota, 2)                                              AS nota_media_sac
      FROM ped
      LEFT JOIN cat ON cat.cliente_sk = ped.cliente_sk
      LEFT JOIN can ON can.cliente_sk = ped.cliente_sk
      LEFT JOIN sac ON sac.cliente_sk = ped.cliente_sk
    """


def cria_tabela_abt(dw, nome, atributos=None):
    """Recria abt.<nome> com o contrato do DDL (3 colunas, tipos, PK, FK, CHECK) + atributos."""
    atributos = atributos or ATRIBUTOS
    cols = ",\n  ".join(f"{n} {t} NULL" for n, t, _, _ in atributos)
    with dw.begin() as cx:
        cx.execute(text(f"DROP TABLE IF EXISTS abt.{nome} CASCADE"))
        cx.execute(text(f"""
            CREATE TABLE abt.{nome} (
              cliente_sk          BIGINT   NOT NULL REFERENCES dw.dim_cliente (cliente_sk),
              data_corte          DATE     NOT NULL,
              alvo_recompra_90d   SMALLINT NOT NULL CHECK (alvo_recompra_90d IN (0,1)),
              {cols},
              PRIMARY KEY (cliente_sk, data_corte)
            )"""))


def monta_atributos_corretos(dw):
    """Atributos calculados SÓ com dados até a data de corte (ver ATRIBUTOS)."""
    return pd.read_sql(text(sql_atributos("dw", DATA_CORTE)), dw)


def copia_no_corte(dw):
    """Cria o esquema dw_corte: o DW como ele estaria em 30/06/2025. Pedidos posteriores
    saem; entregas posteriores ao corte viram 'não entregue ainda'; atendimentos posteriores saem.
    Serve à asserção de que nenhum atributo usa dado posterior ao corte."""
    with dw.begin() as cx:
        cx.execute(text("DROP SCHEMA IF EXISTS dw_corte CASCADE"))
        cx.execute(text("CREATE SCHEMA dw_corte"))
        cx.execute(text(f"""
            CREATE TABLE dw_corte.fato_pedido AS
            SELECT pedido_sk, id_origem, sistema_origem, cliente_sk, data_pedido_sk,
                   CASE WHEN data_entrega_sk <= DATE '{DATA_CORTE}' THEN data_entrega_sk END AS data_entrega_sk,
                   canal_sk, status_sk, qtd_itens, valor_mercadoria, valor_frete, valor_desconto,
                   valor_total,
                   CASE WHEN data_entrega_sk <= DATE '{DATA_CORTE}' THEN dias_entrega END AS dias_entrega
              FROM dw.fato_pedido WHERE data_pedido_sk <= DATE '{DATA_CORTE}'"""))
        cx.execute(text("CREATE INDEX ON dw_corte.fato_pedido (pedido_sk)"))
        cx.execute(text("""CREATE TABLE dw_corte.fato_item_pedido AS
                           SELECT i.* FROM dw.fato_item_pedido i
                           JOIN dw_corte.fato_pedido p ON p.pedido_sk = i.pedido_sk"""))
        cx.execute(text("CREATE INDEX ON dw_corte.fato_item_pedido (pedido_sk)"))
        cx.execute(text(f"""CREATE TABLE dw_corte.fato_atendimento AS
                            SELECT * FROM dw.fato_atendimento WHERE data_abertura_sk <= DATE '{DATA_CORTE}'"""))
        for t in ("dim_status", "dim_canal", "dim_produto"):
            cx.execute(text(f"CREATE TABLE dw_corte.{t} AS SELECT * FROM dw.{t}"))


def grava_tabela(dw, nome, abt, atributos=None):
    """Grava abt.<nome> ordenado por cliente_sk (saída reprodutível)."""
    atributos = atributos or ATRIBUTOS
    cria_tabela_abt(dw, nome, atributos)
    abt = abt.sort_values("cliente_sk").reset_index(drop=True)
    for n, t, _, _ in atributos:
        if t in ("INT", "SMALLINT"):
            abt[n] = abt[n].astype("Int64")        # inteiros com ausência: não gravar 5.0
    abt["data_corte"] = pd.to_datetime(abt["data_corte"]).dt.date
    abt["alvo_recompra_90d"] = abt["alvo_recompra_90d"].astype(int)
    cols = ["cliente_sk", "data_corte", "alvo_recompra_90d"] + [a[0] for a in atributos]
    abt = abt[cols]
    abt.to_sql(nome, dw, schema="abt", if_exists="append", index=False, method="multi", chunksize=5_000)
    print(f"abt.{nome}: {len(abt)} linhas, {abt.shape[1]} colunas")
    return abt


def grava_correta(dw, alvo, atributos):
    return grava_tabela(dw, "recompra_90d", alvo.merge(atributos, on="cliente_sk", how="left"))


# ---------------------------------------------------------------------------
# VERSÕES COM VAZAMENTO (contraexemplo do experimento, RDT-15). Os vazamentos
# são introduzidos DE PROPÓSITO e cada um está documentado abaixo.
#
#   VAZAMENTO 1 · recencia_dias   calculada sobre a BASE INTEIRA: o último pedido
#       efetivo é buscado também na janela do alvo (01/07 a 28/09/2025 e depois).
#       Quem comprou na janela passa a ter recência pequena ou negativa. É o erro
#       típico de esquecer a cláusula de data num agregado.
#   VAZAMENTO 2 · frequencia_pedidos  idem: conta pedidos efetivos de toda a base,
#       inclusive os que são o próprio alvo. Quem recomprou na janela ganha ao
#       menos uma unidade a mais.
#   VAZAMENTO 3 · valor_monetario_z   (sutil) valor_monetario padronizado (z-score)
#       com média e desvio de TODAS as linhas, antes de qualquer partição treino/
#       teste. Média e desvio incorporam a distribuição do conjunto de teste.
#
# `--vazamento` tem os três; `--vazamento-sutil` tem só o terceiro (serve à
# pergunta (b) do relatório e não vai ao Orange). Nas duas, os demais atributos
# são idênticos aos da versão correta.
# ---------------------------------------------------------------------------
COLUNA_NORMALIZADA = ("valor_monetario_z", "NUMERIC(14,6)",
                      "valor_monetario padronizado com média e desvio de TODAS as linhas (antes da partição)",
                      "0 se não há pedido efetivo, como o atributo original")
ATRIBUTOS_VAZ = [COLUNA_NORMALIZADA if a[0] == "valor_monetario" else a for a in ATRIBUTOS]


def sql_dois_atributos_sobre_a_base_inteira(corte):
    """VAZAMENTOS 1 e 2: o mesmo cálculo de recência e frequência, SEM o filtro de data."""
    return f"""
    SELECT f.cliente_sk,
           (DATE '{corte}' - MAX(f.data_pedido_sk) FILTER (WHERE s.status_conformado <> 'CANCELADO')) AS recencia_dias,
           COUNT(*) FILTER (WHERE s.status_conformado <> 'CANCELADO')                                AS frequencia_pedidos
      FROM dw.fato_pedido f
      JOIN dw.dim_status s ON s.status_sk = f.status_sk
     GROUP BY f.cliente_sk"""


def monta_atributos_com_vazamento(dw, dois_atributos=True):
    """Atributos corretos, com os vazamentos pedidos. `dois_atributos=False` dá a versão sutil."""
    ab = monta_atributos_corretos(dw)
    if dois_atributos:
        v = pd.read_sql(text(sql_dois_atributos_sobre_a_base_inteira(DATA_CORTE)), dw)
        ab = ab.drop(columns=["recencia_dias", "frequencia_pedidos"]).merge(v, on="cliente_sk", how="left")
    return ab


def padroniza_antes_da_particao(abt):
    """VAZAMENTO 3: z-score de valor_monetario com média/desvio de todas as linhas."""
    x = abt["valor_monetario"].astype(float)
    media, desvio = x.mean(), x.std(ddof=0)
    abt = abt.copy()
    abt["valor_monetario_z"] = ((x - media) / desvio).round(6)
    return abt.drop(columns=["valor_monetario"]), media, desvio


def constroi_vazamento(dw, alvo, dois_atributos):
    atr = monta_atributos_com_vazamento(dw, dois_atributos)
    abt = alvo.merge(atr, on="cliente_sk", how="left")
    abt, media, desvio = padroniza_antes_da_particao(abt)
    return abt, media, desvio


def verifica_vazamento(qa, dw, abt, media, desvio, dois_atributos, nome):
    """Asserções da versão de contraexemplo. Algumas confirmam que o vazamento EXISTE
    (é o objetivo), outras que ele está CONFINADO ao que foi documentado."""
    cor = pd.read_sql(text("SELECT * FROM abt.recompra_90d ORDER BY cliente_sk"), dw).set_index("cliente_sk")
    v = abt.sort_values("cliente_sk").set_index("cliente_sk")
    qa.igual("população igual à da versão correta", int(len(v) != len(cor) or not v.index.equals(cor.index)), 0,
             "mesmos clientes, mesmo alvo: a única diferença permitida está nos atributos")
    qa.igual("alvo idêntico ao da versão correta", int((v["alvo_recompra_90d"].astype(int) != cor["alvo_recompra_90d"].astype(int)).sum()), 0)
    z = v["valor_monetario_z"].astype(float)
    qa.entre("(intencional) média do valor_monetario_z sobre todas as linhas", float(z.mean()), -1e-4, 1e-4,
             "z-score global: média 0 em TODO o conjunto, inclusive o que será o teste")
    qa.entre("(intencional) desvio do valor_monetario_z sobre todas as linhas", float(z.std(ddof=0)), 0.999, 1.001,
             "z-score global: desvio 1 em TODO o conjunto")
    qa.igual("valor_monetario_z reconstitui valor_monetario",
             int((np.abs(z * desvio + media - cor["valor_monetario"].astype(float)) > 1e-6 * desvio).sum()), 0,
             "a normalização é só uma mudança de escala (z arredondado a 6 casas: erro <= 1e-6 desvio)")
    iguais = [c for c in COLUNAS_ATR if c not in ("valor_monetario", "recencia_dias", "frequencia_pedidos")]
    n_dif = 0
    for c in iguais:
        a, b = v[c], cor[c]
        if a.dtype == object or b.dtype == object:
            n_dif += int((a.astype(str) != b.astype(str)).sum())
        else:
            n_dif += int((~np.isclose(pd.to_numeric(a).astype(float), pd.to_numeric(b).astype(float), equal_nan=True)).sum())
    qa.igual("atributos que deveriam ser idênticos aos corretos e diferem", n_dif, 0,
             "o vazamento fica confinado às colunas documentadas")
    rec_ok = np.isclose(pd.to_numeric(v["recencia_dias"]).astype(float), pd.to_numeric(cor["recencia_dias"]).astype(float), equal_nan=True)
    fre_ok = np.isclose(pd.to_numeric(v["frequencia_pedidos"]).astype(float), pd.to_numeric(cor["frequencia_pedidos"]).astype(float), equal_nan=True)
    if dois_atributos:
        qa.maior_igual("(intencional) clientes com recencia_dias diferente da correta", int((~rec_ok).sum()), 1,
                       "VAZAMENTO 1: a recência enxerga a janela do alvo")
        qa.maior_igual("(intencional) clientes com recencia_dias negativa", int((pd.to_numeric(v["recencia_dias"]) < 0).sum()), 1,
                       "recência negativa = último pedido DEPOIS do corte: impossível numa tabela 'no corte'")
        qa.maior_igual("(intencional) clientes com frequencia_pedidos diferente da correta", int((~fre_ok).sum()), 1,
                       "VAZAMENTO 2: a frequência conta os pedidos do próprio alvo")
        qa.igual("frequencia_pedidos menor que a correta",
                 int((pd.to_numeric(v["frequencia_pedidos"]) < pd.to_numeric(cor["frequencia_pedidos"])).sum()), 0,
                 "contar a base inteira só pode acrescentar pedidos")
    else:
        qa.igual("recencia_dias idêntica à correta (versão sutil)", int((~rec_ok).sum()), 0, "a versão sutil não tem os dois atributos")
        qa.igual("frequencia_pedidos idêntica à correta (versão sutil)", int((~fre_ok).sum()), 0)
    os.makedirs(DIR_ABT, exist_ok=True)
    pd.DataFrame([dict(tabela=nome, media_global=f"{media:.6f}", desvio_global=f"{desvio:.6f}", linhas=len(v))]).to_csv(
        os.path.join(DIR_ABT, f"normalizacao_global_{nome}.csv"), index=False)


def verifica_correta(qa, dw, alvo, abt):
    # --- alvo -----------------------------------------------------------------
    qa.unico("cliente_sk no alvo", alvo["cliente_sk"])
    n_pop = int(pd.read_sql(text(f"""SELECT COUNT(DISTINCT cliente_sk) FROM dw.fato_pedido
                                     WHERE data_pedido_sk <= DATE '{DATA_CORTE}'"""), dw).iloc[0, 0])
    qa.igual("alvo: linhas == clientes unificados com pedido até o corte", len(alvo), n_pop,
             "uma linha por cliente unificado (RDT-02), população = clientes com histórico até o corte")
    qa.igual("abt: linhas == linhas do alvo", len(abt), len(alvo), "a junção com os atributos não multiplica linhas")
    qa.unico("abt: (cliente_sk, data_corte)", abt["cliente_sk"].astype(str) + "|" + abt["data_corte"].astype(str))
    taxa = float(abt["alvo_recompra_90d"].mean())
    qa.entre("taxa de positivos do alvo (registrada)", taxa, 0.02, 0.60,
             "registrada, não ajustada: classe extremamente desbalanceada indicaria erro na janela")

    # alvo recalculado de forma independente (pandas, a partir dos fatos brutos)
    fp = pd.read_sql(text("""SELECT f.cliente_sk, f.data_pedido_sk d, s.status_conformado st
                               FROM dw.fato_pedido f JOIN dw.dim_status s USING (status_sk)"""), dw)
    corte, fim = pd.Timestamp(DATA_CORTE).date(), pd.Timestamp(DATA_FIM_ALVO).date()
    base = set(fp.cliente_sk[fp.d <= corte])
    pos = set(fp.cliente_sk[(fp.d > corte) & (fp.d <= fim) & (fp.st != "CANCELADO")]) & base
    qa.igual("alvo: positivos == recálculo independente em pandas", int(abt["alvo_recompra_90d"].sum()), len(pos),
             "janela 01/07/2025 a 28/09/2025, status diferente de CANCELADO (RDT-04)")

    # --- nenhum atributo usa dado posterior ao corte ------------------------------
    copia_no_corte(dw)
    ref = pd.read_sql(text(sql_atributos("dw_corte", DATA_CORTE)), dw).set_index("cliente_sk").sort_index()
    cur = abt.set_index("cliente_sk").sort_index()[COLUNAS_ATR]
    assert list(ref.index) == list(cur.index), "populações diferentes entre o DW completo e o DW no corte"
    n_dif = 0
    for c in COLUNAS_ATR:
        a, b = cur[c], ref[c]
        if a.dtype == object or b.dtype == object:
            iguais = (a.astype(str) == b.astype(str))
        else:
            a, b = pd.to_numeric(a).astype(float), pd.to_numeric(b).astype(float)
            iguais = np.isclose(a, b, atol=1e-9, equal_nan=True)
        n_dif += int((~iguais).sum())
    with dw.begin() as cx:
        cx.execute(text("DROP SCHEMA IF EXISTS dw_corte CASCADE"))
    qa.igual("atributos: valores que mudam se o DW for cortado em 30/06/2025", n_dif, 0,
             "nenhum atributo usa dado posterior ao corte: o ABT é idêntico calculado no DW completo e no DW 'como estava no corte'")
    qa.igual("atributos: recência negativa", int((abt["recencia_dias"].dropna() < 0).sum()), 0,
             "recência negativa indicaria pedido posterior ao corte")
    qa.igual("atributos: tempo_como_cliente negativo", int((abt["tempo_como_cliente_dias"].dropna() < 0).sum()), 0)
    qa.igual("atributos: data_corte diferente de 2025-06-30",
             int((pd.to_datetime(abt["data_corte"]) != pd.Timestamp(DATA_CORTE)).sum()), 0)
    # o alvo não pode ser atributo
    qa.igual("atributos: colunas do alvo entre os atributos", len({"alvo_recompra_90d"} & set(COLUNAS_ATR)), 0)


def grava_resumo(abt):
    os.makedirs(DIR_ABT, exist_ok=True)
    pd.DataFrame([dict(atributo=n, tipo=t, regra=r, ausente=a, data_de_corte=DATA_CORTE)
                  for n, t, r, a in ATRIBUTOS]).to_csv(os.path.join(DIR_ABT, "dicionario_atributos.csv"), index=False)
    linhas = [dict(medida="linhas", valor=str(len(abt))),
              dict(medida="positivos", valor=str(int(abt["alvo_recompra_90d"].sum()))),
              dict(medida="taxa_de_positivos", valor=f"{float(abt['alvo_recompra_90d'].mean()):.6f}")]
    for c in COLUNAS_ATR:
        linhas.append(dict(medida=f"nulos.{c}", valor=str(int(abt[c].isna().sum()))))
    pd.DataFrame(linhas).to_csv(os.path.join(DIR_ABT, "resumo_correta.csv"), index=False)


def dicionario_vazamento():
    os.makedirs(DIR_ABT, exist_ok=True)
    pd.DataFrame([
        dict(versao="vazamento", coluna="recencia_dias", vazamento="1 · base inteira",
             o_que_faz="último pedido efetivo buscado também depois de 30/06/2025 (sem o filtro de data)"),
        dict(versao="vazamento", coluna="frequencia_pedidos", vazamento="2 · base inteira",
             o_que_faz="conta pedidos efetivos da base inteira, inclusive os da janela do alvo"),
        dict(versao="vazamento e vazamento-sutil", coluna="valor_monetario_z", vazamento="3 · normalização antes da partição",
             o_que_faz="z-score com média e desvio de todas as linhas (treino e teste juntos)"),
    ]).to_csv(os.path.join(DIR_ABT, "dicionario_vazamento.csv"), index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--correta", action="store_true")
    ap.add_argument("--vazamento", action="store_true")
    ap.add_argument("--vazamento-sutil", dest="sutil", action="store_true",
                    help="só a normalização antes da partição (não vai ao Orange)")
    args = ap.parse_args()
    if not (args.correta or args.vazamento or args.sutil):
        ap.error("escolha --correta, --vazamento ou --vazamento-sutil")

    dw = eng_dw()
    alvo = pd.read_sql(text(SQL_ALVO), dw)
    print(f"alvo: {len(alvo)} clientes | taxa de recompra = "
          f"{alvo['alvo_recompra_90d'].mean():.3f}")

    if args.correta:
        qa = Suite(etapa="04_abt_correta")
        atributos = monta_atributos_corretos(dw)
        antes = len(alvo)
        abt = grava_correta(dw, alvo, atributos)
        qa.cardinalidade_preservada("junção alvo x atributos", antes, len(abt))
        verifica_correta(qa, dw, alvo, abt)
        grava_resumo(abt)
        with dw.begin() as cx:
            cx.execute(text("DELETE FROM qa.execucao_assercao WHERE etapa = :e"), dict(e=qa.etapa))
        qa.registrar(dw)
        qa.imprimir()

    for ligado, etapa, nome, dois in ((args.vazamento, "04_abt_vazamento", "recompra_90d_vazamento", True),
                                      (args.sutil, "04_abt_vazamento_sutil", "recompra_90d_vazamento_sutil", False)):
        if not ligado:
            continue
        qa = Suite(etapa=etapa)
        abt, media, desvio = constroi_vazamento(dw, alvo, dois)
        qa.cardinalidade_preservada("junção alvo x atributos", len(alvo), len(abt))
        abt = grava_tabela(dw, nome, abt, ATRIBUTOS_VAZ)
        verifica_vazamento(qa, dw, abt, media, desvio, dois, nome)
        dicionario_vazamento()
        with dw.begin() as cx:
            cx.execute(text("DELETE FROM qa.execucao_assercao WHERE etapa = :e"), dict(e=qa.etapa))
        qa.registrar(dw)
        qa.imprimir()
