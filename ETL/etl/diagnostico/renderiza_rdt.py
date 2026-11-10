# -*- coding: utf-8 -*-
"""Gera docs/RDT.md a partir do modelo etl/rdt/RDT.template.md.

Todo número do RDT é um marcador `{{chave}}` ou `{{chave|formato}}` no modelo.
O valor vem de `saida/rdt/registros_afetados.json` (script
`rdt_registros_afetados.py`) ou, com o prefixo `s1:`, de
`saida/diagnostico/numeros.json` (scripts d01 a d06 da Semana 1). Nenhum número
é digitado à mão: se a chave não existir, a geração falha e lista as ausentes.

Formatos: (nenhum) inteiro com ponto de milhar, ou decimal com vírgula;
`pct` 2 casas + %; `brl` R$ com 2 casas; `dec` 2 casas; `dec1` 1 casa.

    docker compose exec etl python -m diagnostico.renderiza_rdt
    cp saida/rdt/RDT.md docs/RDT.md          # a partir do diretório do projeto
"""

import csv
import json
import os
import re
import sys

from config import DIR_SAIDA

MODELO = "/etl/rdt/RDT.template.md"
SAIDA = os.path.join(DIR_SAIDA, "rdt", "RDT.md")
USADOS = os.path.join(DIR_SAIDA, "rdt", "rdt_numeros_usados.csv")
FONTES = {
    "": os.path.join(DIR_SAIDA, "rdt", "registros_afetados.json"),
    "s1:": os.path.join(DIR_SAIDA, "diagnostico", "numeros.json"),
}


def milhar(n):
    return f"{n:,}".replace(",", ".")


def fmt(v, formato):
    if formato == "pct":
        return f"{v:.2f}".replace(".", ",") + "%"
    if formato == "brl":
        inteiro, dec = f"{abs(v):,.2f}".split(".")
        return ("-" if v < 0 else "") + "R$ " + inteiro.replace(",", ".") + "," + dec
    if formato == "dec":
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if formato == "dec1":
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and not formato):
        return milhar(int(v))
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    dados = {p: json.load(open(c, encoding="utf-8")) for p, c in FONTES.items()}
    texto = open(MODELO, encoding="utf-8").read()
    ausentes, usados = [], []

    def troca(m):
        corpo = m.group(1).strip()
        chave, _, formato = corpo.partition("|")
        prefixo = "s1:" if chave.startswith("s1:") else ""
        k = chave[len(prefixo):]
        if k not in dados[prefixo]:
            ausentes.append(chave)
            return m.group(0)
        v = dados[prefixo][k]
        usados.append((chave, v))
        return fmt(v, formato.strip())

    saida = re.sub(r"\{\{(.+?)\}\}", troca, texto)
    if ausentes:
        print("chaves ausentes:", *sorted(set(ausentes)), sep="\n  ")
        sys.exit(1)
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write(saida)
    with open(USADOS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chave", "valor"])
        w.writerows(sorted(set(usados)))
    print(f"{len(usados)} marcadores substituídos ({len(set(usados))} distintos) -> {SAIDA}")


if __name__ == "__main__":
    main()
