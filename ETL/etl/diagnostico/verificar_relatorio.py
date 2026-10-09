# -*- coding: utf-8 -*-
"""Verificador: cada número citado no relatório existe em numeros.json?

    docker compose exec -T etl python -m diagnostico.verificar_relatorio \
        < ../relatorio/semana1/diagnostico_semana1.md

O relatório chega pela entrada padrão porque a pasta relatorio/ não é montada
no contêiner. Ignora capa, títulos, referências, trechos de código, datas,
rótulos (H3, RDT-02, d01) e uma lista explícita de constantes de definição,
que é impressa para revisão. Grava verificacao_relatorio.md e sai com código
1 se algum número não for encontrado.
"""

import json
import re
import sys

from .comum import ARQ_NUMEROS, DIR_DIAG

# Constantes que não são medições: vêm do enunciado, do dicionário ou definem
# um critério. Cada uma é listada no resultado para revisão humana.
CONSTANTES = {
    0.01: "tolerância da reconciliação",
    1.9: "volume declarado no README (milhão)",
    2.2: "volume declarado no roteiro (milhões)",
    2016: "ano de início do ERP segundo o dicionário",
    -1: "valor-sentinela do desconto",
    1: "limite inferior da escala de notas",
    5: "limite superior da escala de notas",
    22: "limite da faixa noturna (22h)",
    20: "início da janela em torno do corte (20h)",
    4: "fim da janela em torno do corte (4h)",
}

NUM = re.compile(r"(?<![\w.,/-])[-−]?\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\w/])|"
                 r"(?<![\w.,/-])[-−]?\d+(?:,\d+)?(?![\w/])")


def limpa(texto):
    texto = texto.split("\n## Referências")[0]
    texto = texto.split("\n## 1 ", 1)[1] if "\n## 1 " in texto else texto  # pula a capa
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"`[^`]*`", " ", texto)
    linhas = [l for l in texto.splitlines() if not l.lstrip().startswith("#")]
    texto = "\n".join(linhas)
    texto = re.sub(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", " ", texto)          # datas
    texto = re.sub(r",\s*(?:19|20)\d{2}\)|\((?:19|20)\d{2}\)", ")", texto)          # citações autor-data
    texto = re.sub(r"\b(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|"
                   r"outubro|novembro|dezembro) de \d{4}", " ", texto)
    texto = re.sub(r"\b(?:RDT-\d+|H\d|d0\d\w*|Tabela \d+|Caso \d+|Seção \d+)\b", " ", texto)
    texto = re.sub(r"\b(\d+)h\b", r"\1", texto)                                   # 8h → 8
    return texto


def valor(tok):
    tok = tok.replace("−", "-").replace(".", "").replace(",", ".")
    return float(tok)


def main():
    texto = sys.stdin.read()
    with open(ARQ_NUMEROS, encoding="utf-8") as f:
        numeros = json.load(f)
    valores = {}
    for k, v in numeros.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        valores.setdefault(round(float(v), 4), k)

    achados, faltando, constantes = [], [], []
    for linha in limpa(texto).splitlines():
        for m in NUM.finditer(linha):
            v = valor(m.group(0))
            chave = valores.get(round(v, 4))
            if chave:
                achados.append((m.group(0), chave))
            elif v in CONSTANTES:
                constantes.append((m.group(0), CONSTANTES[v]))
            else:
                faltando.append((m.group(0), linha.strip()[:120]))

    saida = [f"# Verificação dos números do relatório\n",
             f"- Números encontrados em numeros.json: {len(achados)}",
             f"- Constantes de definição (não são medições): {len(constantes)}",
             f"- Números NÃO encontrados: {len(faltando)}\n"]
    if faltando:
        saida.append("## Não encontrados\n")
        saida += [f"- `{t}` em: {ctx}" for t, ctx in faltando]
    saida.append("\n## Constantes aceitas\n")
    saida += sorted({f"- `{t}`: {r}" for t, r in constantes})
    saida.append("\n## Encontrados (número → id)\n")
    saida += [f"- `{t}` → `{k}`" for t, k in achados]
    caminho = f"{DIR_DIAG}/verificacao_relatorio.md"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(saida) + "\n")
    print("\n".join(saida[:4]))
    for t, ctx in faltando:
        print(f"  FALTA {t}: {ctx}")
    sys.exit(1 if faltando else 0)


if __name__ == "__main__":
    main()
