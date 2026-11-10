# -*- coding: utf-8 -*-
"""Verificador da documentação: cada número de docs/DOCUMENTACAO.md existe em algum arquivo de /saida?

    docker compose exec -T etl python -m diagnostico.verificar_documentacao < docs/DOCUMENTACAO.md

Mesma regra de `verificar_resultados.py` (um número "bate" quando algum valor da fonte, arredondado para as casas que o
texto mostra, é igual a ele; inteiros exigem igualdade exata), com fontes de todas as semanas:

  Semana 1   /saida/diagnostico/numeros.json
  Semanas 2 e 3   /saida/rdt/registros_afetados.json, /saida/extracao/contagens_stg.csv, /saida/reconciliacao/*.csv,
                  /saida/abt/resumo_correta.csv, contagens de linhas em /saida/diagnostico/f1_depois.csv
  Semana 4   /saida/experimento/*.csv e numeros.json
  Fase final /saida/diagnostico/f1_resumo*.csv, f1_execucao.log (tempos e asserções) e contagens por tipo de f1_depois.csv

Contagens derivadas (número de linhas de um arquivo, número de itens por tipo) entram como fontes, com a origem indicada.
Constantes de definição (parâmetros que o texto cita como escolha, não como medição) ficam numa lista, impressa no resultado.
Grava /saida/diagnostico/verificacao_documentacao.md e sai com código 1 se algum número não for encontrado.
"""
import csv
import glob
import json
import os
import re
import sys

from config import DIR_SAIDA

from .verificar_resultados import FONTES_CSV, NUM, casas, numero, procura, valor

DIAG = os.path.join(DIR_SAIDA, "diagnostico")
SAIDA = os.path.join(DIAG, "verificacao_documentacao.md")

CONSTANTES = {
    0.5: "referência da AUC de um acaso",
    1: "'1 de 96.140', 'classe 1', 'um minuto' etc. (enumerações)",
    2: "'dois' sistemas/atributos/versões (enumeração)",
    3: "'três' (enumeração)",
    4: "'quatro' fontes (enumeração)",
    5: "esquemas do banco (stg, cnf, dw, abt, qa) e itens de enumeração",
    6: "seis fórmulas testadas e seis comandos do pipeline (enumeração)",
    15: "ficha RDT-15 / 15 decisões",
    30: "dia do mês (30/06) e 30% do teste",
    70: "proporção 70/30 do treino",
    90: "janela do alvo, em dias (config.py)",
    95: "critério de parada por maioria do Orange (%)",
}


def limpa(texto):
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"`[^`]*`", " ", texto)
    texto = "\n".join(l for l in texto.splitlines()
                      if not l.lstrip().startswith("#") and not re.match(r"^\s*\|[-:| ]+\|\s*$", l))
    texto = re.sub(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{1,2}/\d{2}\b|\b\d{4}/\d\b", " ", texto)  # datas, 30/06, semestre
    texto = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{1,2}\b", " ", texto)                                   # versões de software
    texto = re.sub(r"\b(?:RDT-\d+|D\d+|Tabela \d+|Figuras? \d+|[Ss]eção \d+|[Ss]emana \d+|[Ff]ichas? \d+(?: e \d+| a \d+)?)\b", " ", texto)
    texto = re.sub(r"\bRDT-\d+ a RDT-\d+\b|\bD\d+ a D\d+\b", " ", texto)
    texto = re.sub(r"^\s*\d+\.\s", " ", texto, flags=re.M)                              # numeração de listas
    texto = re.sub(r"\b(?:q|\()?[a-e]\)", " ", texto)
    texto = re.sub(r"\b\d+\.\d+\b(?=\s*[Oo]range)", " ", texto)
    texto = re.sub(r"\(c\)|\(\d\)|\b[a-e]\)", " ", texto)
    return texto


def flatten(obj, prefixo):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefixo}.{k}")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield float(obj), prefixo


def csv_numeros(arq):
    nome = os.path.relpath(arq, DIR_SAIDA)
    with open(arq, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    for i, linha in enumerate(linhas, start=2):
        for col, txt in linha.items():
            v = numero(txt)
            if v is not None:
                yield v, f"{nome}:{i}:{col}"
    yield float(len(linhas)), f"{nome} (número de linhas)"


def carrega_fontes():
    fontes = []
    for arq, rot in ((os.path.join(DIAG, "numeros.json"), "diagnostico/numeros.json"),
                     (os.path.join(DIR_SAIDA, "rdt", "registros_afetados.json"), "rdt/registros_afetados.json"),
                     (os.path.join(DIR_SAIDA, "experimento", "numeros.json"), "experimento/numeros.json")):
        with open(arq, encoding="utf-8") as f:
            fontes += list(flatten(json.load(f), rot))
    arquivos = [os.path.join(DIR_SAIDA, "experimento", n) for n in FONTES_CSV]
    arquivos += [os.path.join(DIR_SAIDA, "abt", "resumo_correta.csv"),
                 os.path.join(DIR_SAIDA, "extracao", "contagens_stg.csv")]
    arquivos += sorted(glob.glob(os.path.join(DIR_SAIDA, "reconciliacao", "*.csv")))
    arquivos += sorted(glob.glob(os.path.join(DIAG, "f1_resumo*.csv")))
    for arq in arquivos:
        fontes += list(csv_numeros(arq))
    # f1_depois.csv: "N linhas" de cada tabela e contagem de itens por tipo
    por_tipo = {}
    with open(os.path.join(DIAG, "f1_depois.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            por_tipo[r["tipo"]] = por_tipo.get(r["tipo"], 0) + 1
            m = re.match(r"(\d+) linhas", r["impressao"])
            if m:
                fontes.append((float(m.group(1)), f"diagnostico/f1_depois.csv:{r['item']} (linhas)"))
    fontes += [(float(n), f"diagnostico/f1_depois.csv (itens do tipo {t})") for t, n in por_tipo.items()]
    # f1_execucao.log: tempos por etapa e contagem de asserções
    with open(os.path.join(DIAG, "f1_execucao.log"), encoding="utf-8") as f:
        for linha in f:
            for tok in re.findall(r"\bem (\d+) s\b|^\s+(\d+) asserções", linha):
                for n in tok:
                    if n:
                        fontes.append((float(n), "diagnostico/f1_execucao.log"))
    return fontes


def main():
    texto = sys.stdin.read()
    fontes = carrega_fontes()
    achados, faltando, constantes = [], [], []
    for linha in limpa(texto).splitlines():
        for m in NUM.finditer(linha):
            tok = m.group(0)
            x, d = valor(tok), casas(tok)
            if d <= 1 and abs(x) in CONSTANTES:
                constantes.append((tok, CONSTANTES[abs(x)]))
                continue
            origem = procura(abs(x), d, fontes)
            if origem:
                achados.append((tok, origem))
            else:
                faltando.append((tok, linha.strip()[:130]))

    saida = ["# Verificação dos números da documentação\n",
             f"- Números encontrados nos arquivos de saida/: {len(achados)}",
             f"- Constantes de definição (não são medições): {len(constantes)}",
             f"- Números NÃO encontrados: {len(faltando)}\n"]
    if faltando:
        saida.append("## Não encontrados\n")
        saida += [f"- `{t}` em: {ctx}" for t, ctx in faltando]
    saida.append("\n## Constantes aceitas\n")
    saida += sorted({f"- `{t}`: {r}" for t, r in constantes})
    saida.append("\n## Encontrados (número → origem)\n")
    saida += [f"- `{t}` → `{o}`" for t, o in achados]
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write("\n".join(saida) + "\n")
    print("\n".join(saida[:4]))
    for t, ctx in faltando:
        print(f"  FALTA {t}: {ctx}")
    sys.exit(1 if faltando else 0)


if __name__ == "__main__":
    main()
