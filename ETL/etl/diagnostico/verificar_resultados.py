# -*- coding: utf-8 -*-
"""Verificador (F.3): cada número do relatório de resultados existe nos arquivos do experimento?

    docker compose exec -T etl python -m diagnostico.verificar_resultados \\
        < ../relatorio/semana4/resultados_experimento.md

O relatório chega pela entrada padrão porque a pasta relatorio/ não é montada no contêiner.

Fontes (todas gravadas por scripts versionados): os CSV e o numeros.json de /saida/experimento/ e o
/saida/abt/resumo_correta.csv. Números inteiros pequenos ou com uma casa que sejam parâmetros de definição são conferidos primeiro contra a lista
de constantes. Um número do texto "bate" quando algum valor da fonte, arredondado para as
casas que o texto mostra, é igual a ele. Também são aceitos o valor em módulo (diferenças escritas com sinal) e
o valor ×100 (percentuais). Inteiros (sem casas decimais) exigem igualdade exata.

Ignora títulos, trechos de código, datas, versões de software, rótulos (D44, Tabela 2, seção 4) e a numeração de
listas. As constantes de definição (parâmetros e limites escolhidos, que não são medições) ficam numa lista
explícita, impressa no resultado para revisão. Grava /saida/diagnostico/verificacao_resultados.md e sai com
código 1 se algum número não for encontrado.
"""
import csv
import json
import os
import re
import sys

from config import DIR_SAIDA

DIR_EXP = os.path.join(DIR_SAIDA, "experimento")
SAIDA = os.path.join(DIR_SAIDA, "diagnostico", "verificacao_resultados.md")

FONTES_CSV = ["metricas_orange.csv", "metricas_python.csv", "comparacao_orange.csv", "efeito_vazamento.csv",
              "auc_univariada.csv", "sensibilidade.csv"]

# Parâmetros e limites que o texto cita como definição, não como medição.
CONSTANTES = {
    100: "100 iterações (padrão do Orange) e folha mínima de 100 no teste de sensibilidade",
    10000: "10.000 iterações no teste de sensibilidade",
    1: "folha mínima de 1 no teste de sensibilidade; 'um por versão' etc.",
    0.5: "limiar de decisão do Orange e 'próxima de 0,5' (referência da AUC de um acaso)",
    90: "janela do alvo, em dias (config.py)",
    95: "critério de parada por maioria do Orange (%)",
    4: "limite de páginas do roteiro",
    3: "'três' perguntas/modelos/versões em enumerações",
    2: "'dois' atributos/fluxos em enumerações",
    5: "'cinco' procedimentos em enumerações",
}

NUM = re.compile(r"(?<![\w.,/-])[-−+]?\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\w/])|"
                 r"(?<![\w.,/-])[-−+]?\d+(?:,\d+)?(?![\w/])")


def limpa(texto):
    texto = texto.split("\n## 7.", 1)[0]                                   # a seção de reprodução só tem comandos
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"`[^`]*`", " ", texto)
    texto = "\n".join(l for l in texto.splitlines()
                      if not l.lstrip().startswith("#") and not re.match(r"^\s*\|[-:| ]+\|\s*$", l))
    texto = texto.split("\n## 1.", 1)[-1] if "\n## 1." in texto else texto  # pula a capa
    texto = re.sub(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\b\d{4}/\d\b", " ", texto)       # datas e semestre
    texto = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{1,2}\b", " ", texto)                                        # versões de software
    texto = re.sub(r"\b(?:D\d+|RDT-\d+|Tabela \d+|seção \d+|Seção \d+|item \d+(?:\.\d+)?)\b", " ", texto)
    texto = re.sub(r"\bD\d+ a D\d+\b", " ", texto)
    texto = re.sub(r"^\s*\d+\.\s", " ", texto, flags=re.M)                                  # numeração de listas
    texto = re.sub(r"\b\d+\.\d+\b(?=\s*[Oo]range)", " ", texto)
    texto = re.sub(r"\*\*\(?[a-c]\)", " ", texto)
    return texto


def valor(tok):
    tok = tok.replace("−", "-").replace("+", "").replace(".", "").replace(",", ".")
    return float(tok)


def casas(tok):
    return len(tok.split(",")[1]) if "," in tok else 0


def numero(txt):
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def carrega_fontes():
    """Lista de (valor, origem). Origem = arquivo:linha:coluna."""
    fontes = []
    # só arquivos de resultado: as partições do Orange (ids de cliente e atributos) fariam qualquer inteiro "bater"
    arquivos = [os.path.join(DIR_EXP, n) for n in FONTES_CSV] + [os.path.join(DIR_SAIDA, "abt", "resumo_correta.csv")]
    for arq in arquivos:
        nome = os.path.relpath(arq, DIR_SAIDA)
        with open(arq, encoding="utf-8") as f:
            for i, linha in enumerate(csv.DictReader(f), start=2):
                for col, txt in linha.items():
                    v = numero(txt)
                    if v is not None:
                        fontes.append((v, f"{nome}:{i}:{col}"))
    with open(os.path.join(DIR_EXP, "numeros.json"), encoding="utf-8") as f:
        def percorre(obj, caminho):
            if isinstance(obj, dict):
                for k, x in obj.items():
                    yield from percorre(x, f"{caminho}.{k}")
            elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
                yield float(obj), f"experimento/numeros.json:{caminho[1:]}"
        fontes += list(percorre(json.load(f), ""))
    return fontes


def procura(x, d, fontes):
    """Primeira fonte cujo valor, arredondado para `d` casas, é igual a `x` (ou o módulo, ou ×100)."""
    tol = 0.5 * 10 ** -d + 1e-9 if d > 0 else 1e-9
    for v, origem in fontes:
        for cand, rotulo in ((v, ""), (abs(v), " (módulo)"), (v * 100, " (×100)")):
            if abs(cand - x) <= tol and (d > 0 or float(cand).is_integer()):
                return origem + rotulo
    return None


def main():
    texto = sys.stdin.read()
    fontes = carrega_fontes()
    achados, faltando, constantes = [], [], []
    for linha in limpa(texto).splitlines():
        for m in NUM.finditer(linha):
            tok = m.group(0)
            x, d = valor(tok), casas(tok)
            if d <= 1 and abs(x) in CONSTANTES:          # parâmetro de definição: tem prioridade sobre a busca
                constantes.append((tok, CONSTANTES[abs(x)]))
                continue
            origem = procura(abs(x), d, fontes)
            if origem:
                achados.append((tok, origem))
            else:
                faltando.append((tok, linha.strip()[:120]))

    saida = ["# Verificação dos números do relatório de resultados\n",
             f"- Números encontrados nos arquivos do experimento: {len(achados)}",
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
