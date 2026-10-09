# -*- coding: utf-8 -*-
"""Funções compartilhadas pelos scripts de diagnóstico.

Todas as consultas usam as conexões somente leitura de `config`. Nenhuma
consulta usa LIMIT: os números saem sempre da tabela inteira.
"""

import json
import os
import re
import unicodedata

import pandas as pd
from sqlalchemy import text

from config import (ARQ_AVALIACOES, ARQ_SAC, DIR_SAIDA, eng_mysql,
                    eng_origem)

DIR_DIAG = os.path.join(DIR_SAIDA, "diagnostico")
ARQ_NUMEROS = os.path.join(DIR_DIAG, "numeros.json")
os.makedirs(DIR_DIAG, exist_ok=True)

DATA_AQUISICAO = "2024-03-01"
FUSO_LOCAL = "America/Sao_Paulo"

_eng = {}


def _engine(nome):
    if nome not in _eng:
        _eng[nome] = eng_mysql() if nome == "mysql" else eng_origem()
    return _eng[nome]


def leg(sql, **params):
    """Consulta no MySQL legado e devolve DataFrame."""
    with _engine("mysql").connect() as cx:
        return pd.read_sql(text(sql), cx, params=params)


def ecom(sql, **params):
    """Consulta no PostgreSQL do e-commerce e devolve DataFrame."""
    with _engine("pg").connect() as cx:
        return pd.read_sql(text(sql), cx, params=params)


def escalar(df):
    v = df.iloc[0, 0]
    return None if pd.isna(v) else v


# ----------------------------------------------------------------- arquivos
def ler_sac():
    """CSV do SAC lido como texto, sem converter vazio em nulo."""
    return pd.read_csv(ARQ_SAC, sep=";", encoding="latin-1", dtype=str,
                       keep_default_na=False)


def ler_avaliacoes():
    """NDJSON como lista de dicionários, na ordem do arquivo."""
    with open(ARQ_AVALIACOES, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f]


# ---------------------------------------------------------------- CPF e texto
def so_digitos(serie):
    return serie.fillna("").astype(str).str.replace(r"\D", "", regex=True)


def cpf_valido(c):
    """Verifica os dois dígitos verificadores; rejeita sequências repetidas."""
    if len(c) != 11 or not c.isdigit() or c == c[0] * 11:
        return False
    d = [int(x) for x in c]
    if (sum(d[i] * (10 - i) for i in range(9)) * 10) % 11 % 10 != d[9]:
        return False
    return (sum(d[i] * (11 - i) for i in range(10)) * 10) % 11 % 10 == d[10]


def normaliza_texto(s):
    """Caixa baixa, sem acento e com espaços colapsados."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def formato(s):
    """Máscara do valor: dígitos viram 9, letras viram A."""
    s = re.sub(r"\d", "9", str(s))
    return re.sub(r"[A-Za-z]", "A", s)


# ------------------------------------------------------------------- saída
def pct(n, base, casas=2):
    return round(100.0 * float(n) / float(base), casas) if base else 0.0


def _limpa(v):
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        v = round(v, 4)
        if v.is_integer() and abs(v) < 1e15:
            v = int(v)
    return v


def registrar(numeros):
    """Acrescenta (ou atualiza) números-chave em numeros.json, ordenado."""
    atual = {}
    if os.path.exists(ARQ_NUMEROS):
        with open(ARQ_NUMEROS, encoding="utf-8") as f:
            atual = json.load(f)
    atual.update({k: _limpa(v) for k, v in numeros.items()})
    with open(ARQ_NUMEROS, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(atual.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")


def salvar_csv(df, nome):
    caminho = os.path.join(DIR_DIAG, nome)
    df.to_csv(caminho, index=False, encoding="utf-8")
    return caminho


class Relatorio:
    """Acumula seções em Markdown e grava ao final."""

    def __init__(self, nome, titulo):
        self.caminho = os.path.join(DIR_DIAG, nome)
        self.partes = [f"# {titulo}\n"]

    def secao(self, titulo):
        self.partes.append(f"\n## {titulo}\n")

    def texto(self, t):
        self.partes.append(t + "\n")

    def tabela(self, df, index=False, **kw):
        self.partes.append(df.to_markdown(index=index, **kw) + "\n")

    def gravar(self):
        with open(self.caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(self.partes))
        print(f">> gravado em {self.caminho}")
