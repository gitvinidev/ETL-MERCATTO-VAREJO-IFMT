# -*- coding: utf-8 -*-
"""Teste do zero (F.1): impressão digital do que o pipeline produz, para comparar antes e depois de reconstruir.

    docker compose exec etl python -m diagnostico.f1_hashes antes      # grava saida/diagnostico/f1_antes.csv
    docker compose exec etl python -m diagnostico.f1_hashes depois     # grava saida/diagnostico/f1_depois.csv
    docker compose exec etl python -m diagnostico.f1_hashes comparar   # compara os dois e grava f1_comparacao.csv e f1_resumo.csv
    docker compose exec etl python -m diagnostico.f1_hashes <rótulo>   # qualquer outro rótulo grava f1_<rótulo>.csv
    docker compose exec etl python -m diagnostico.f1_hashes comparar <a> <b>   # compara f1_<a>.csv e f1_<b>.csv

Tipos de item:
  arquivo  SHA-256 do conteúdo dos arquivos produzidos pelos seis comandos do pipeline (e do experimento Python);
  tabela   número de linhas e soma de `hashtextextended(linha::text, 0)` das tabelas de stg, cnf, dw e abt. A soma não
           depende da ordem das linhas, mas depende de cada valor de cada coluna, inclusive das chaves substitutas.
  tabela sem _extraido_em  o mesmo, para as tabelas da stg, sem a coluna que guarda a hora da extração.
  asserção qa.execucao_assercao: contagem por (etapa, nome, aprovado, valor_obtido), sem o carimbo de tempo.

Sai com código 1 em `comparar` se algum item diferir.
"""
import csv
import glob
import hashlib
import os
import sys

from sqlalchemy import text

from config import DIR_SAIDA, eng_dw

DIAG = os.path.join(DIR_SAIDA, "diagnostico")
PADROES_ARQUIVOS = [
    "abt_recompra_correta.csv", "abt_recompra_vazamento.csv",
    "abt/*.csv", "reconciliacao/*.csv", "extracao/*.csv",
    "experimento/metricas_python.csv", "experimento/comparacao_orange.csv",
    "experimento/efeito_vazamento.csv", "experimento/auc_univariada.csv",
]
ESQUEMAS = ["stg", "cnf", "dw", "abt"]


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def coleta():
    itens = []
    for padrao in PADROES_ARQUIVOS:
        for arq in sorted(glob.glob(os.path.join(DIR_SAIDA, padrao))):
            itens.append(("arquivo", os.path.relpath(arq, DIR_SAIDA), sha256(arq)))
    dw = eng_dw()
    with dw.connect() as cx:
        tabelas = cx.execute(text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_schema = ANY(:e) ORDER BY 1, 2"), dict(e=ESQUEMAS)).fetchall()
        for esq, tab in tabelas:
            n, h = cx.execute(text(
                f'SELECT count(*), COALESCE(sum(hashtextextended(t::text, 0)::numeric), 0) FROM "{esq}"."{tab}" t')).one()
            itens.append(("tabela", f"{esq}.{tab}", f"{n} linhas | soma {h}"))
            if esq == "stg":  # a stg guarda `_extraido_em` (hora da carga): impressão também sem esse metadado
                n2, h2 = cx.execute(text(
                    f"SELECT count(*), COALESCE(sum(hashtextextended((to_jsonb(t) - '_extraido_em')::text, 0)::numeric), 0) "
                    f'FROM "{esq}"."{tab}" t')).one()
                itens.append(("tabela sem _extraido_em", f"{esq}.{tab}", f"{n2} linhas | soma {h2}"))
        for etapa, nome, ok, val, n in cx.execute(text(
                "SELECT etapa, nome, aprovado, valor_obtido, count(*) FROM qa.execucao_assercao "
                "GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4")).fetchall():
            itens.append(("asserção", f"{etapa} · {nome}", f"aprovado={ok} valor={val} execuções={n}"))
    return itens


def le(rotulo):
    with open(os.path.join(DIAG, f"f1_{rotulo}.csv"), encoding="utf-8") as f:
        return {(r["tipo"], r["item"]): r["impressao"] for r in csv.DictReader(f)}


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo and modo != "comparar":
        itens = coleta()
        with open(os.path.join(DIAG, f"f1_{modo}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tipo", "item", "impressao"])
            w.writerows(itens)
        por_tipo = {}
        for t, _, _ in itens:
            por_tipo[t] = por_tipo.get(t, 0) + 1
        print(f"f1_{modo}.csv: {len(itens)} itens {por_tipo}")
    elif modo == "comparar":
        rot_a, rot_b = (sys.argv[2], sys.argv[3]) if len(sys.argv) >= 4 else ("antes", "depois")
        a, d = le(rot_a), le(rot_b)
        linhas, diferentes = [], 0
        for chave in sorted(set(a) | set(d)):
            ia, id_ = a.get(chave, "(ausente)"), d.get(chave, "(ausente)")
            igual = ia == id_
            diferentes += not igual
            linhas.append([chave[0], chave[1], "igual" if igual else "DIFERENTE", ia, id_])
        sufixo = "" if rot_a == "antes" and rot_b == "depois" else f"_{rot_a}_{rot_b}"
        with open(os.path.join(DIAG, f"f1_comparacao{sufixo}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tipo", "item", "resultado", "antes", "depois"])
            w.writerows(linhas)
        with open(os.path.join(DIAG, f"f1_resumo{sufixo}.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["itens", "iguais", "diferentes"])
            w.writerow([len(linhas), len(linhas) - diferentes, diferentes])
        print(f"{len(linhas)} itens comparados, {len(linhas) - diferentes} iguais, {diferentes} diferentes")
        for tipo, item, res, ia, id_ in linhas:
            if res != "igual":
                print(f"  DIFERENTE {tipo} {item}\n    antes : {ia}\n    depois: {id_}")
        sys.exit(1 if diferentes else 0)
    else:
        sys.exit("uso: python -m diagnostico.f1_hashes <rótulo>|comparar [a b]")


if __name__ == "__main__":
    main()
