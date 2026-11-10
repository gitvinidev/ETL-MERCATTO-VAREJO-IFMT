#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETAPA 3 — CARGA NO ESQUEMA ESTRELA

DECLARAÇÃO DE GRÃO (relatório da Semana 1, seção 7; RDT-11):

    "Uma linha de dw.fato_pedido representa um pedido registrado em um dos
     dois sistemas de origem, identificado pelo par (sistema de origem,
     identificador do pedido na origem), qualquer que seja o seu status."
    "Uma linha de dw.fato_item_pedido representa uma linha de item tal como
     registrada na origem, pertencente a um pedido presente em
     dw.fato_pedido."

Carrega `dw` a partir da camada conformada `cnf` (etapa 2). Como o DDL de `dw`
é congelado e não tem colunas para os indicadores das fichas do RDT, as tabelas
`dw.aux_*` (criadas aqui) guardam rastro e indicadores ao lado do esquema
estrela, sem alterá-lo. Chaves substitutas são determinísticas (ordem da chave
de origem), para a reexecução do zero reproduzir o mesmo resultado.

A reconciliação financeira (soma de valor_total por sistema contra o total
calculado DIRETAMENTE na origem, tolerância de 0,1%) grava
saida/reconciliacao/financeira.csv.

    docker compose exec etl python 03_carga_dw.py
"""

import os
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from config import DIR_SAIDA, eng_dw, eng_mysql, eng_origem
from qualidade.assercoes import Suite

TOLERANCIA_RECONCILIACAO = 0.001      # 0,1% (roteiro, seção 3.3)
DIR_RECON = os.path.join(DIR_SAIDA, "reconciliacao")


def roda(eng, sql, **p):
    with eng.begin() as cx:
        return cx.execute(text(sql), p)


def escalar(eng, sql, **p):
    with eng.connect() as cx:
        return cx.execute(text(sql), p).scalar()


def carrega_dim_tempo(engine, ini=date(2022, 12, 1), fim=date(2026, 3, 31)):
    """Esta dimensão está pronta — é a única sem decisão a tomar."""
    MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
    linhas = []
    d = ini
    while d <= fim:
        linhas.append(dict(data_sk=d, ano=d.year, trimestre=(d.month - 1) // 3 + 1,
                           mes=d.month, dia=d.day, dia_semana=d.isoweekday(),
                           nome_mes=MESES[d.month - 1],
                           eh_fim_semana=d.isoweekday() >= 6))
        d += timedelta(days=1)
    df = pd.DataFrame(linhas)
    with engine.begin() as cx:
        cx.execute(text("TRUNCATE dw.dim_tempo CASCADE"))
    df.to_sql("dim_tempo", engine, schema="dw", if_exists="append", index=False)
    print(f"dim_tempo: {len(df)} datas")
    return len(df)


def limpa_dw(eng):
    """Recarga completa e idempotente: esvazia o esquema estrela e os auxiliares."""
    roda(eng, """TRUNCATE dw.fato_item_pedido, dw.fato_atendimento, dw.fato_avaliacao,
                          dw.fato_pedido, dw.dim_cliente, dw.dim_produto, dw.dim_canal,
                          dw.dim_status, dw.dim_tempo RESTART IDENTITY CASCADE""")
    for t in ("aux_ponte_cliente", "aux_cliente", "aux_produto", "aux_pedido", "aux_item",
              "aux_item_quarentena", "aux_atendimento", "aux_avaliacao"):
        roda(eng, f"DROP TABLE IF EXISTS dw.{t}")


def carrega_dimensoes(qa):
    """dim_cliente, dim_produto, dim_canal, dim_status a partir de cnf (etapa 2)."""
    eng = eng_dw()
    # surrogate keys = chaves determinísticas de cnf (ordenadas pelo menor id de origem)
    roda(eng, """
        INSERT INTO dw.dim_cliente (cliente_sk, cpf_normalizado, cpf_valido, nome_padronizado,
               cidade, uf, dt_primeiro_cadastro, id_legado, id_ecommerce,
               origem_unificacao, regra_pareamento)
        SELECT cliente_key, cpf_normalizado, cpf_valido, nome_padronizado, cidade, uf,
               dt_primeiro_cadastro, id_legado, id_ecommerce, origem_unificacao, regra_pareamento
          FROM cnf.cliente ORDER BY cliente_key""")
    roda(eng, "SELECT setval(pg_get_serial_sequence('dw.dim_cliente','cliente_sk'), "
              "(SELECT MAX(cliente_sk) FROM dw.dim_cliente))")
    roda(eng, """
        INSERT INTO dw.dim_produto (produto_sk, sku, descricao, categoria_nivel1, categoria_nivel2,
               categoria_origem, preco_referencia, ativo, id_legado, id_ecommerce, origem)
        SELECT produto_key, sku, descricao, categoria_nivel1, categoria_nivel2, categoria_origem,
               preco_referencia, ativo, id_legado, id_ecommerce, origem
          FROM cnf.produto ORDER BY produto_key""")
    roda(eng, "SELECT setval(pg_get_serial_sequence('dw.dim_produto','produto_sk'), "
              "(SELECT MAX(produto_sk) FROM dw.dim_produto))")
    roda(eng, "CREATE INDEX IF NOT EXISTS ix_dim_produto_origem ON dw.dim_produto "
              "(origem, (COALESCE(id_legado, id_ecommerce)))")
    roda(eng, """INSERT INTO dw.dim_canal (canal_origem, canal_conformado, sistema)
                 SELECT canal_origem, canal_conformado, sistema FROM cnf.canal_map
                  ORDER BY sistema, canal_origem""")
    roda(eng, """INSERT INTO dw.dim_status (status_origem, sistema, status_conformado, motivo_cancelamento)
                 SELECT status_origem, sistema, status_conformado, motivo_cancelamento
                   FROM cnf.status_map ORDER BY sistema, status_origem""")

    # rastro e indicadores que o DDL não comporta
    roda(eng, """CREATE TABLE dw.aux_ponte_cliente AS
                 SELECT sistema_origem, id_origem::bigint AS id_origem, cliente_key AS cliente_sk, papel
                   FROM cnf.cliente_ponte""")
    roda(eng, """CREATE TABLE dw.aux_cliente AS
                 SELECT cliente_key AS cliente_sk, n_reg_legado, n_reg_ecom, cpf_conflito FROM cnf.cliente""")
    roda(eng, """CREATE TABLE dw.aux_produto AS
                 SELECT produto_key AS produto_sk, classe_mapeamento FROM cnf.produto""")

    qa.igual("dim_cliente: linhas == pessoas de cnf", escalar(eng, "SELECT COUNT(*) FROM dw.dim_cliente"),
             escalar(eng, "SELECT COUNT(*) FROM cnf.cliente"), "RDT-02")
    qa.igual("dim_cliente: registros de origem na ponte do DW", escalar(eng, "SELECT COUNT(*) FROM dw.aux_ponte_cliente"),
             escalar(eng, "SELECT (SELECT COUNT(*) FROM stg.legado_clientes) + (SELECT COUNT(*) FROM stg.ecommerce_customer)"),
             "todo cliente de origem tem rastro no DW")
    qa.igual("dim_produto: linhas == produtos das duas origens", escalar(eng, "SELECT COUNT(*) FROM dw.dim_produto"),
             escalar(eng, "SELECT (SELECT COUNT(*) FROM stg.legado_produtos) + (SELECT COUNT(*) FROM stg.ecommerce_product)"))
    qa.igual("dim_canal: linhas", escalar(eng, "SELECT COUNT(*) FROM dw.dim_canal"), 6)
    qa.igual("dim_status: linhas", escalar(eng, "SELECT COUNT(*) FROM dw.dim_status"), 9)


def carrega_fato_pedido(qa):
    """Grão: um pedido por (sistema_origem, id_origem), qualquer que seja o status (RDT-11)."""
    eng = eng_dw()
    # cliente_sk e as demais FKs vêm de cnf; nenhum pedido ficou sem cliente (RDT-12),
    # por isso não há cliente "DESCONHECIDO": a asserção abaixo falharia se surgisse um.
    roda(eng, """
        INSERT INTO dw.fato_pedido (pedido_sk, id_origem, sistema_origem, cliente_sk,
               data_pedido_sk, data_entrega_sk, canal_sk, status_sk, qtd_itens,
               valor_mercadoria, valor_frete, valor_desconto, valor_total, dias_entrega)
        SELECT ROW_NUMBER() OVER (ORDER BY CASE p.sistema_origem WHEN 'LEGADO' THEN 0 ELSE 1 END, p.id_num),
               p.id_origem, p.sistema_origem, p.cliente_key, p.data_pedido, p.data_entrega,
               c.canal_sk, s.status_sk, p.qtd_itens, p.valor_mercadoria, p.valor_frete,
               p.valor_desconto, p.valor_total, p.dias_entrega
          FROM cnf.pedido p
          JOIN dw.dim_canal  c ON c.sistema = p.sistema_origem AND c.canal_origem = p.canal_origem
          JOIN dw.dim_status s ON s.sistema = p.sistema_origem AND s.status_origem = p.status_origem""")
    roda(eng, "SELECT setval(pg_get_serial_sequence('dw.fato_pedido','pedido_sk'), "
              "(SELECT MAX(pedido_sk) FROM dw.fato_pedido))")
    roda(eng, """
        CREATE TABLE dw.aux_pedido AS
        SELECT f.pedido_sk, p.entrega_sem_data, p.entrega_anterior_pedido, p.frete_negativo,
               p.linhas_desconto_sentinela
          FROM cnf.pedido p JOIN dw.fato_pedido f
            ON f.sistema_origem = p.sistema_origem AND f.id_origem = p.id_origem""")
    roda(eng, "CREATE INDEX ix_aux_pedido ON dw.aux_pedido (pedido_sk)")

    n_origens = escalar(eng, "SELECT (SELECT COUNT(*) FROM stg.legado_pedidos) + (SELECT COUNT(*) FROM stg.ecommerce_orders)")
    qa.igual("fato_pedido: linhas == pedidos das duas origens somados",
             escalar(eng, "SELECT COUNT(*) FROM dw.fato_pedido"), n_origens,
             "grão: um pedido por (sistema, id) em qualquer status; nenhum pedido perdido ou multiplicado")
    for fk, dim, col in (("cliente_sk", "dim_cliente", "cliente_sk"), ("data_pedido_sk", "dim_tempo", "data_sk"),
                         ("canal_sk", "dim_canal", "canal_sk"), ("status_sk", "dim_status", "status_sk")):
        qa.igual(f"fato_pedido: FK órfã em {fk}", escalar(eng, f"""
            SELECT COUNT(*) FROM dw.fato_pedido f LEFT JOIN dw.{dim} d ON d.{col} = f.{fk}
             WHERE d.{col} IS NULL"""), 0, "nenhuma chave órfã (RDT-12)")
    qa.igual("fato_pedido: data_entrega_sk órfã", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_pedido f LEFT JOIN dw.dim_tempo d ON d.data_sk = f.data_entrega_sk
         WHERE f.data_entrega_sk IS NOT NULL AND d.data_sk IS NULL"""), 0)
    qa.igual("fato_pedido: pedidos com dias_entrega negativo", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_pedido WHERE dias_entrega < 0"""), 0,
             "prazo_nao_negativo: entrega anterior ao pedido vira NULL com indicador (RDT-08)")
    qa.igual("fato_pedido: valor_total != mercadoria - desconto + frete", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_pedido
         WHERE ABS(valor_total - (valor_mercadoria - valor_desconto + valor_frete)) > 0.01"""), 0, "RDT-05")


def carrega_fato_item(qa):
    """Grão: uma linha de item como registrada na origem, de pedido presente em fato_pedido.
    Itens sem pedido (órfãos) vão para dw.aux_item_quarentena, com motivo (RDT-10)."""
    eng = eng_dw()
    roda(eng, "DROP TABLE IF EXISTS cnf.item_carga")
    roda(eng, """
        CREATE TABLE cnf.item_carga AS
        SELECT ROW_NUMBER() OVER (ORDER BY CASE i.sistema_origem WHEN 'LEGADO' THEN 0 ELSE 1 END,
                                           i._linha_origem) AS item_sk,
               i.sistema_origem, i.id_item_origem, i.id_pedido_origem, i.id_produto_origem,
               f.pedido_sk, pr.produto_sk, i.quantidade, i.valor_unitario, i.valor_desconto,
               i.valor_linha, i.desconto_sentinela
          FROM cnf.item i
          JOIN dw.fato_pedido f ON f.sistema_origem = i.sistema_origem AND f.id_origem = i.id_pedido_origem
          JOIN dw.dim_produto pr ON pr.origem = i.sistema_origem
                                AND COALESCE(pr.id_legado, pr.id_ecommerce) = i.id_produto_origem""")
    roda(eng, """
        INSERT INTO dw.fato_item_pedido (item_sk, pedido_sk, produto_sk, quantidade, valor_unitario,
                                         valor_desconto, valor_linha)
        SELECT item_sk, pedido_sk, produto_sk, quantidade, valor_unitario, valor_desconto, valor_linha
          FROM cnf.item_carga ORDER BY item_sk""")
    roda(eng, "SELECT setval(pg_get_serial_sequence('dw.fato_item_pedido','item_sk'), "
              "(SELECT MAX(item_sk) FROM dw.fato_item_pedido))")
    roda(eng, """CREATE TABLE dw.aux_item AS
                 SELECT item_sk, sistema_origem, id_item_origem, desconto_sentinela FROM cnf.item_carga""")
    roda(eng, "CREATE INDEX ix_aux_item ON dw.aux_item (item_sk)")
    roda(eng, """
        CREATE TABLE dw.aux_item_quarentena AS
        SELECT sistema_origem, id_item_origem, id_pedido_origem, id_produto_origem, quantidade,
               valor_unitario, valor_desconto, valor_linha, desconto_sentinela,
               'PEDIDO_INEXISTENTE_NA_ORIGEM'::text AS motivo
          FROM cnf.item WHERE NOT pedido_existe ORDER BY sistema_origem, id_item_origem""")
    roda(eng, "DROP TABLE IF EXISTS cnf.item_carga")

    n_item = escalar(eng, "SELECT COUNT(*) FROM cnf.item")
    n_fato = escalar(eng, "SELECT COUNT(*) FROM dw.fato_item_pedido")
    n_quar = escalar(eng, "SELECT COUNT(*) FROM dw.aux_item_quarentena")
    n_tem_pedido = escalar(eng, """
        SELECT (SELECT COUNT(*) FROM stg.legado_itens_pedido i WHERE EXISTS
                  (SELECT 1 FROM stg.legado_pedidos p WHERE p.id_pedido = i.id_pedido))
             + (SELECT COUNT(*) FROM stg.ecommerce_order_item i WHERE EXISTS
                  (SELECT 1 FROM stg.ecommerce_orders p WHERE p.order_id = i.order_id))""")
    qa.igual("fato_item_pedido: linhas == itens com pedido na origem", n_fato, n_tem_pedido,
             "grão: uma linha de item de pedido existente; nenhuma junção multiplicou ou perdeu itens (RDT-10)")
    qa.igual("fato_item_pedido: itens + quarentena == itens de cnf", n_fato + n_quar, n_item,
             "todo item da origem está no fato ou na quarentena (RDT-10)")
    qa.igual("fato_item_pedido: itens sem pedido no fato", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_item_pedido i LEFT JOIN dw.fato_pedido p ON p.pedido_sk = i.pedido_sk
         WHERE p.pedido_sk IS NULL"""), 0, "nenhum item órfão no fato (RDT-10)")
    qa.igual("fato_item_pedido: mercadoria dos itens != valor_mercadoria dos pedidos", escalar(eng, """
        SELECT ROUND(SUM(i.quantidade * i.valor_unitario) - (SELECT SUM(valor_mercadoria) FROM dw.fato_pedido), 2)
          FROM dw.fato_item_pedido i"""), 0, "a soma dos itens do fato reproduz a mercadoria dos pedidos")


def carrega_fatos_auxiliares(qa):
    """fato_atendimento (SAC) e fato_avaliacao. pedido_sk é sempre nulo (RDT-13)."""
    eng = eng_dw()
    roda(eng, """
        INSERT INTO dw.fato_atendimento (protocolo, cliente_sk, pedido_sk, data_abertura_sk,
               data_fechamento_sk, canal, motivo_conformado, nota_satisfacao, horas_resolucao)
        SELECT protocolo, cliente_key, NULL, data_abertura, data_fechamento, canal,
               motivo_conformado, nota_satisfacao::int, horas_resolucao::numeric(10,2)
          FROM cnf.atendimento ORDER BY _linha_origem""")
    roda(eng, """
        CREATE TABLE dw.aux_atendimento AS
        SELECT f.atendimento_sk, a.origem_sistema AS origem_sistema_declarada,
               a.id_pedido_origem AS id_pedido_declarado, a.cpf_digitos, a.cpf_valido, a.cpf_ambiguo,
               a.reiterou_contato, a.nota_zero, a.fechamento_ausente, a.horas_negativas
          FROM cnf.atendimento a JOIN dw.fato_atendimento f ON f.protocolo = a.protocolo""")
    roda(eng, """
        INSERT INTO dw.fato_avaliacao (review_id, pedido_sk, produto_sk, data_sk, nota,
               compra_verificada, votos_uteis)
        SELECT review_id, NULL, produto_key, data_avaliacao, nota::int, compra_verificada, votos_uteis::int
          FROM cnf.avaliacao ORDER BY _linha_origem""")
    roda(eng, """
        CREATE TABLE dw.aux_avaliacao AS
        SELECT f.avaliacao_sk, a.ref_sistema AS ref_sistema_declarada, a.ref_id AS ref_pedido_declarado,
               a.offset_ausente, a.rating_ausente, a.rating_chegou_como_texto
          FROM cnf.avaliacao a JOIN dw.fato_avaliacao f ON f.review_id = a.review_id""")

    qa.igual("fato_atendimento: linhas == atendimentos de cnf",
             escalar(eng, "SELECT COUNT(*) FROM dw.fato_atendimento"),
             escalar(eng, "SELECT COUNT(*) FROM cnf.atendimento"), "RDT-13")
    qa.igual("fato_atendimento: pedido_sk preenchido", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_atendimento WHERE pedido_sk IS NOT NULL"""), 0,
             "RDT-13: a ligação do SAC ao pedido não se sustenta")
    qa.igual("fato_atendimento: cliente_sk órfão", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_atendimento f LEFT JOIN dw.dim_cliente c ON c.cliente_sk = f.cliente_sk
         WHERE f.cliente_sk IS NOT NULL AND c.cliente_sk IS NULL"""), 0)
    qa.igual("fato_avaliacao: linhas == avaliações de cnf",
             escalar(eng, "SELECT COUNT(*) FROM dw.fato_avaliacao"),
             escalar(eng, "SELECT COUNT(*) FROM cnf.avaliacao"), "RDT-13")
    qa.igual("fato_avaliacao: pedido_sk preenchido", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_avaliacao WHERE pedido_sk IS NOT NULL"""), 0, "RDT-13")
    qa.igual("fato_avaliacao: produto_sk nulo", escalar(eng, """
        SELECT COUNT(*) FROM dw.fato_avaliacao WHERE produto_sk IS NULL"""), 0)


def reconcilia(qa):
    """Reconciliação financeira (obrigatória): soma de valor_total no DW, por sistema,
    contra o total calculado DIRETAMENTE na origem com a MESMA fórmula conformada.

        legado      : SUM(VALOR_TOTAL)                  (já é mercadoria - desconto + frete)
        e-commerce  : SUM(total_amount + freight_amount) (total_amount não inclui o frete: RDT-05)

    Comparar o DW com SUM(total_amount) cru daria uma diferença falsa, igual ao frete.
    Se a diferença passar de 0,1%, a carga NÃO segue: a causa é procurada e registrada.
    """
    eng = eng_dw()
    with eng_mysql().connect() as cx:
        origem_leg = cx.execute(text("SELECT SUM(VALOR_TOTAL) FROM PEDIDOS")).scalar()
    with eng_origem().connect() as cx:
        origem_eco = cx.execute(text("SELECT SUM(total_amount + freight_amount) FROM shop.orders")).scalar()
        cru_eco = cx.execute(text("SELECT SUM(total_amount) FROM shop.orders")).scalar()
    linhas, detalhe = [], []
    for sistema, orig in (("LEGADO", origem_leg), ("ECOM", origem_eco)):
        dw_ = escalar(eng, "SELECT SUM(valor_total) FROM dw.fato_pedido WHERE sistema_origem = :s", s=sistema)
        dif = dw_ - orig
        rel = abs(dif) / orig
        ok = rel <= TOLERANCIA_RECONCILIACAO
        linhas.append(dict(sistema=sistema, soma_dw=f"{dw_:.2f}", soma_origem=f"{orig:.2f}",
                           diferenca_absoluta=f"{dif:.2f}", diferenca_relativa=f"{rel:.10f}",
                           aprovado="sim" if ok else "não"))
        qa.entre(f"reconciliação financeira: {sistema}, diferença relativa", float(rel), 0.0,
                 TOLERANCIA_RECONCILIACAO, "soma de valor_total no DW contra a origem (mesma fórmula): até 0,1%")
        qa.igual(f"reconciliação financeira: {sistema}, diferença absoluta", float(dif), 0.0,
                 "esperado exato: a conformação não perde nem inventa valor")
    os.makedirs(DIR_RECON, exist_ok=True)
    pd.DataFrame(linhas).to_csv(os.path.join(DIR_RECON, "financeira.csv"), index=False)

    # Evidência de por que a fórmula comum importa (RDT-05): o total_amount cru não bate.
    dw_eco = escalar(eng, "SELECT SUM(valor_total) FROM dw.fato_pedido WHERE sistema_origem = 'ECOM'")
    detalhe.append(dict(medida="ECOM: soma de valor_total no DW", valor=f"{dw_eco:.2f}"))
    detalhe.append(dict(medida="ECOM: SUM(total_amount) cru na origem", valor=f"{cru_eco:.2f}"))
    detalhe.append(dict(medida="ECOM: SUM(freight_amount) na origem", valor=f"{origem_eco - cru_eco:.2f}"))
    detalhe.append(dict(medida="ECOM: diferença DW - total_amount cru (falsa)", valor=f"{dw_eco - cru_eco:.2f}"))
    pd.DataFrame(detalhe).to_csv(os.path.join(DIR_RECON, "financeira_detalhe.csv"), index=False)
    print(pd.DataFrame(linhas).to_string(index=False))
    return all(l["aprovado"] == "sim" for l in linhas)


if __name__ == "__main__":
    dw = eng_dw()
    qa = Suite(etapa="03_carga_dw")
    limpa_dw(dw)
    carrega_dim_tempo(dw)
    carrega_dimensoes(qa)
    carrega_fato_pedido(qa)
    carrega_fato_item(qa)
    carrega_fatos_auxiliares(qa)
    ok = reconcilia(qa)

    roda(dw, "DELETE FROM qa.execucao_assercao WHERE etapa = :e", e=qa.etapa)
    qa.registrar(dw)
    qa.imprimir()
    if not ok:
        raise SystemExit("reconciliação financeira acima de 0,1%: NÃO siga; ache a causa e registre no RDT.")
