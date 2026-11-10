# -*- coding: utf-8 -*-
"""Figuras do guia de estudo (docs/DOCUMENTACAO.md): SVG gerados dos arquivos de /saida.

    docker compose exec etl python -m diagnostico.gera_figuras
    mkdir -p docs/figuras && cp saida/figuras/*.svg docs/figuras/     # a partir de ETL/ (docs/ não é montado no contêiner)

Cada número desenhado vem de um arquivo gerado por script versionado (numeros.json da Semana 1, registros_afetados.json,
contagens_stg.csv, f1_depois.csv, metricas_orange.csv, experimento/numeros.json); as datas, de config.py (e do período
coberto, medido na Semana 1). Só a biblioteca padrão do Python é usada.

Cores: paleta de referência da skill de visualização (azul, laranja e verde-água, nessa ordem; o par azul/laranja foi
validado com `validate_palette.py`). O texto usa sempre a tinta de texto, nunca a cor da série: a identidade vem do
marcador colorido ao lado do texto.
"""
import csv
import json
import os
from datetime import date
from xml.sax.saxutils import escape

from config import DATA_CORTE, DATA_FIM_ALVO, DIR_SAIDA, JANELA_ALVO_DIAS

SAIDA = os.path.join(DIR_SAIDA, "figuras")
FONTE = "'Noto Sans','DejaVu Sans',system-ui,sans-serif"
AZUL, LARANJA, VERDE = "#2a78d6", "#eb6834", "#1baf7a"
TINTA, TINTA2, MUDO = "#0b0b0b", "#52514e", "#898781"
GRADE, EIXO, SUPERFICIE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
LAVA = {AZUL: "#e9f1fb", LARANJA: "#fdeee8", VERDE: "#e6f6f0", MUDO: "#f1f0ed"}


# ------------------------------------------------------------------ dados
def json_(nome):
    with open(os.path.join(DIR_SAIDA, nome), encoding="utf-8") as f:
        return json.load(f)


def csv_(nome):
    with open(os.path.join(DIR_SAIDA, nome), encoding="utf-8") as f:
        return list(csv.DictReader(f))


REG = json_("rdt/registros_afetados.json")
S1 = json_("diagnostico/numeros.json")
EXP = json_("experimento/numeros.json")
ORANGE = csv_("experimento/metricas_orange.csv")
STG = csv_("extracao/contagens_stg.csv")
F1 = csv_("diagnostico/f1_depois.csv")


def nf(n):
    return f"{int(round(float(n))):,}".replace(",", ".")


def dec(x, casas=2):
    return f"{float(x):.{casas}f}".replace(".", ",")


def dec_min3(x):
    """Como no arquivo: até 4 casas, sem zeros sobrando, no mínimo 3."""
    s = f"{float(x):.4f}".rstrip("0")
    if len(s.split(".")[1]) < 3:
        s = f"{float(x):.3f}"
    return s.replace(".", ",")


def linhas_tabela(nome):
    for r in F1:
        if r["tipo"] == "tabela" and r["item"] == nome:
            return int(r["impressao"].split(" ")[0])
    raise KeyError(nome)


# ------------------------------------------------------------------ primitivos SVG
def svg(w, h, titulo, descricao, corpo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-labelledby="t d" font-family="{FONTE}">\n<title id="t">{escape(titulo)}</title>'
            f'<desc id="d">{escape(descricao)}</desc>\n'
            f'<defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{TINTA2}"/></marker></defs>\n'
            f'<rect width="{w}" height="{h}" fill="{SUPERFICIE}"/>\n{corpo}\n</svg>\n')


def txt(x, y, s, tam=12, cor=TINTA, ancora="start", peso="400"):
    return (f'<text x="{x}" y="{y}" font-size="{tam}" fill="{cor}" text-anchor="{ancora}" '
            f'font-weight="{peso}">{escape(s)}</text>')


def ret(x, y, w, h, preenche, borda=None, rx=6):
    b = f' stroke="{borda}" stroke-width="1"' if borda else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{preenche}"{b}/>'


def caixa(x, y, w, h, titulo, linhas=(), faixa=None, tam=12):
    """Cartão: borda fina, faixa colorida à esquerda (identidade), título em negrito e linhas de apoio."""
    out = [ret(x, y, w, h, SUPERFICIE, EIXO)]
    if faixa:
        out.append(ret(x, y, 7, h, faixa, None, 3))
    cy = y + 20
    out.append(txt(x + 17, cy, titulo, tam + 1, TINTA, peso="600"))
    for ln in linhas:
        cy += 16
        out.append(txt(x + 17, cy, ln, tam, TINTA2))
    return "\n".join(out)


def seta(x1, y1, x2, y2, rotulo=None, rx=None, ry=None, ancora="start"):
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{TINTA2}" stroke-width="1.5" marker-end="url(#seta)"/>']
    if rotulo:
        out.append(txt(rx if rx is not None else x1 + 8, ry if ry is not None else (y1 + y2) / 2 + 4, rotulo, 12, TINTA2, ancora))
    return "\n".join(out)


def legenda(x, y, itens, passo=None):
    out, cx = [], x
    for cor, nome in itens:
        out.append(ret(cx, y - 10, 12, 12, cor, None, 3))
        out.append(txt(cx + 18, y, nome, 12, TINTA2))
        cx += passo if passo else 18 + int(6.6 * len(nome)) + 24
    return "\n".join(out)


def grava(nome, conteudo):
    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8") as f:
        f.write(conteudo)
    print("figura:", nome)


SEMANAS = [(MUDO, "Semana 1"), (AZUL, "Semana 2"), (LARANJA, "Semana 3"), (VERDE, "Semana 4")]


# ------------------------------------------------------------------ 1. visão geral do projeto
def fig_visao_geral():
    cont = {f: sum(int(r["linhas_stg"]) for r in STG if r["fonte"] == f) for f in ("legado", "ecommerce", "sac", "avaliacoes")}
    total = sum(cont.values())
    n_asser = sum(1 for r in F1 if r["tipo"] == "asserção")
    auc_c = [float(r["auc"]) for r in ORANGE if r["fluxo"] == "correta"]
    auc_v = [float(r["auc"]) for r in ORANGE if r["fluxo"] == "vazamento"]
    W, H = 780, 740
    b = [ret(20, 10, 740, 42, LAVA[MUDO], EIXO), ret(20, 10, 7, 42, MUDO, None, 3),
         txt(37, 29, "Semana 1 · Diagnóstico (scripts d01 a d06)", 13, TINTA, peso="600"),
         txt(37, 45, "mede as quatro fontes sem alterá-las: chaves, significado dos campos, valores, anomalias e grão", 12, TINTA2)]
    fontes = [("ERP legado (MySQL)", nf(cont["legado"]) + " registros"), ("E-commerce (PostgreSQL)", nf(cont["ecommerce"]) + " registros"),
              ("SAC (CSV)", nf(cont["sac"]) + " atendimentos"), ("Avaliações (NDJSON)", nf(cont["avaliacoes"]) + " avaliações")]
    for i, (t, n) in enumerate(fontes):
        b.append(caixa(20 + i * 190, 68, 180, 54, t, [n], MUDO))
    b.append(seta(390, 126, 390, 162, "01_extracao.py · cópia fiel, sem transformar", 402, 148))
    b.append(caixa(20, 166, 740, 50, "stg · cópia fiel das origens", [f"{nf(total)} registros, 11 tabelas conferidas contra as origens"], AZUL))
    b.append(seta(390, 220, 390, 254, "02_transformacao.py · decisões RDT-01 a RDT-09", 402, 242))
    b.append(caixa(20, 258, 740, 50, "cnf · camada conformada", [
        f"{nf(REG['rdt02.pessoas'])} pessoas a partir de {nf(REG['base.clientes_legado'] + REG['base.clientes_ecom'])} cadastros; "
        "status, valores, ausências e fuso padronizados"], AZUL))
    b.append(seta(390, 312, 390, 346, "03_carga_dw.py · reconciliação financeira com diferença zero", 402, 334))
    b.append(caixa(20, 350, 740, 50, "dw · esquema estrela", [
        f"{nf(REG['rdt11.fato_pedido.linhas'])} pedidos e {nf(REG['rdt11.fato_item.linhas'])} itens; "
        f"{nf(REG['rdt10.itens_orfaos.total'])} itens sem pedido em quarentena"], LARANJA))
    b.append(seta(205, 404, 205, 440, "04_abt.py --correta", 217, 427))
    b.append(seta(575, 404, 575, 440, "04_abt.py --vazamento", 587, 427))
    b.append(caixa(20, 444, 360, 62, "ABT correta (só dados até o corte)", [f"{nf(REG['abt.linhas'])} clientes",
                   f"{dec(REG['abt.positivos_pct'], 2)}% recompram"], LARANJA))
    b.append(caixa(400, 444, 360, 62, "ABT com vazamento (de propósito)", ["recência e frequência usam também o futuro",
                   "z-score antes da partição"], VERDE))
    b.append(seta(390, 510, 390, 544, "05_exportar_orange.py", 402, 532))
    b.append(caixa(20, 548, 360, 50, "Orange 3.40.0", ["3 modelos, partição 70/30, mesmo fluxo nas duas ABT"], VERDE))
    b.append(caixa(400, 548, 360, 50, "Python (scikit-learn)", ["mesmo experimento, na partição do Orange"], VERDE))
    b.append(seta(390, 602, 390, 628))
    b.append(caixa(20, 632, 740, 40, f"AUC {dec(min(auc_c), 3)} a {dec(max(auc_c), 3)} na versão correta, "
                   f"{dec(min(auc_v), 3)} a {dec(max(auc_v), 3)} com vazamento", [], VERDE))
    b.append(txt(20, 696, f"Em todas as etapas: RDT (15 fichas) · {n_asser} asserções registradas · números rastreáveis · Git com a equipe", 12, TINTA2))
    b.append(legenda(20, 722, SEMANAS, 110))
    return svg(W, H, "Visão geral do projeto",
               "Fluxo das quatro fontes até o resultado do experimento: stg, cnf, dw, ABT correta e com vazamento, Orange e Python.",
               "\n".join(b))


# ------------------------------------------------------------------ 2. ligações entre as fontes (Semana 1)
def fig_ligacoes():
    cpf_n, cpf_b = S1["a.cpf.legado_registros_com_par"], S1["a.cpf.legado.registros"]
    sac_n, sac_b = S1["a.sac.cpf_em_algum"], S1["a.cpf.sac.registros"]
    dono_n = S1["a.sac.cpf_bate_dono_indicado"]
    sku_n, sku_p = S1["a.ndjson.sku_esta_no_pedido"], S1["a.ndjson.sku_esta_no_pedido_pct"]
    ava_n = S1["e01.stg.avaliacoes.total"]
    sku_ok = S1["a.ndjson.ecom.sku_existe"] + S1["a.ndjson.leg.sku_existe"]
    W, H = 780, 440
    b = [txt(20, 24, "O que liga o quê: só o CPF liga pessoas; SAC e avaliações não ligam a pedido", 14, TINTA, peso="600")]
    b.append(caixa(20, 56, 190, 52, "Clientes do legado", [f"{nf(cpf_b)} cadastros"], MUDO))
    b.append(caixa(570, 56, 190, 52, "Clientes do e-commerce", [f"{nf(REG['base.clientes_ecom'])} cadastros"], MUDO))
    b.append(f'<line x1="212" y1="82" x2="568" y2="82" stroke="{AZUL}" stroke-width="2.5"/>')
    b.append(txt(390, 74, "CPF válido", 12, TINTA, "middle", "600"))
    b.append(txt(390, 100, f"{nf(cpf_n)} de {nf(cpf_b)} do legado ({dec(S1['a.cpf.legado_registros_com_par_pct'])}%)", 12, TINTA2, "middle"))
    b.append(txt(390, 116, "e-mail e telefone: 0 correspondências", 12, TINTA2, "middle"))
    b.append(caixa(20, 190, 190, 52, "SAC (atendimentos)", [f"{nf(sac_b)} registros"], MUDO))
    b.append(f'<line x1="115" y1="190" x2="115" y2="110" stroke="{AZUL}" stroke-width="2.5"/>')
    b.append(txt(125, 150, f"CPF: {nf(sac_n)} de {nf(sac_b)} ({dec(S1['a.sac.cpf_em_algum_pct'])}%) casam com um cadastro", 12, TINTA2))
    b.append(caixa(570, 190, 190, 162, "Pedidos", [f"{nf(REG['base.pedidos'])} nos dois sistemas"], MUDO))
    b.append(f'<line x1="212" y1="216" x2="568" y2="216" stroke="{MUDO}" stroke-width="2"/>')
    b.append(ret(380, 206, 20, 20, SUPERFICIE, MUDO, 10)); b.append(txt(390, 221, "✕", 13, TINTA2, "middle", "700"))
    b.append(txt(390, 200, "SAC → pedido não se sustenta", 12, TINTA, "middle", "600"))
    b.append(txt(390, 244, f"o CPF do atendimento é o do dono do pedido", 12, TINTA2, "middle"))
    b.append(txt(390, 260, f"em {nf(dono_n)} de {nf(sac_b)} casos", 12, TINTA2, "middle"))
    b.append(caixa(20, 290, 190, 64, "Avaliações (NDJSON)", [f"{nf(ava_n)} objetos", "produto ligado pelo SKU"], MUDO))
    b.append(f'<line x1="212" y1="322" x2="568" y2="322" stroke="{MUDO}" stroke-width="2"/>')
    b.append(ret(380, 312, 20, 20, SUPERFICIE, MUDO, 10)); b.append(txt(390, 327, "✕", 13, TINTA2, "middle", "700"))
    b.append(txt(390, 306, "avaliação → pedido não se sustenta", 12, TINTA, "middle", "600"))
    b.append(txt(390, 350, f"o produto avaliado está no pedido citado", 12, TINTA2, "middle"))
    b.append(txt(390, 366, f"em {nf(sku_n)} de {nf(ava_n)} avaliações ({dec(sku_p)}%)", 12, TINTA2, "middle"))
    b.append(txt(20, 400, f"O SKU existe no cadastro de produtos em {nf(sku_ok)} de {nf(ava_n)}: a ligação possível é ao produto.", 12, TINTA2))
    b.append(ret(20, 418, 12, 12, AZUL, None, 3)); b.append(txt(38, 429, "liga (evidência no dado)", 12, TINTA2))
    b.append(ret(210, 418, 12, 12, MUDO, None, 3)); b.append(txt(228, 429, "não se sustenta (✕)", 12, TINTA2))
    return svg(W, H, "O que liga as fontes",
               "Mapa das ligações entre clientes do legado e do e-commerce, SAC, avaliações e pedidos, com a cobertura medida na Semana 1.",
               "\n".join(b))


# ------------------------------------------------------------------ 3. unificação de clientes (Semana 2)
def fig_unificacao():
    leg, eco = REG["base.clientes_legado"], REG["base.clientes_ecom"]
    so_l, amb, so_e = REG["rdt02.pessoas.LEGADO"], REG["rdt02.pessoas.AMBOS"], REG["rdt02.pessoas.ECOM"]
    pessoas = REG["rdt02.pessoas"]
    esc = 700 / (leg + eco)
    x0 = 40
    W, H = 780, 340
    b = [txt(20, 24, "Unificação de clientes: dos cadastros às pessoas", 14, TINTA, peso="600")]

    def barra(y, partes, rotulo):
        out = [txt(x0, y - 8, rotulo, 12, TINTA2)]
        x = x0
        for n, cor, nome in partes:
            w = n * esc
            out.append(ret(x + 1, y, max(w - 2, 1), 34, cor, None, 4))
            if w > 60:
                out.append(txt(x + w / 2, y + 22, nf(n), 12, "#ffffff", "middle", "600"))
            x += w
        return "\n".join(out)

    b.append(barra(62, [(leg, AZUL, "legado"), (eco, LARANJA, "e-commerce")],
                   f"{nf(leg + eco)} registros de cadastro (um por cliente em cada sistema)"))
    b.append(seta(390, 106, 390, 154))
    b.append(txt(402, 128, "mesmo CPF (válido ou não) e mesmo nome e UF,", 12, TINTA2))
    b.append(txt(402, 144, "ou duplicata dentro do legado", 12, TINTA2))
    b.append(barra(180, [(so_l, AZUL, "só no legado"), (amb, VERDE, "nos dois"), (so_e, LARANJA, "só no e-commerce")],
                   f"{nf(pessoas)} pessoas"))
    b.append(legenda(40, 252, [(AZUL, "só no legado"), (VERDE, "nos dois sistemas"), (LARANJA, "só no e-commerce")]))
    b.append(txt(40, 284, f"{nf(REG['rdt02.registros_unidos_em_outra_pessoa'])} registros foram unidos a outra identidade "
                 f"({dec(REG['rdt02.registros_unidos_em_outra_pessoa_pct'])}% dos registros de cadastro).", 12, TINTA2))
    b.append(txt(40, 302, f"{nf(REG['rdt02.pessoas_sem_cpf'])} pessoas não têm CPF e não são pareadas.", 12, TINTA2))
    b.append(txt(40, 320, "Não há verdade externa para conferir as uniões: a regra é prudente (guarda de nome e UF), não infalível.", 12, TINTA2))
    return svg(W, H, "Unificação de clientes",
               "Barras proporcionais: registros de cadastro do legado e do e-commerce e as pessoas resultantes da unificação.",
               "\n".join(b))


# ------------------------------------------------------------------ 4. esquema estrela (Semana 3)
def fig_estrela():
    n = linhas_tabela
    W, H = 780, 470
    dim, fato = AZUL, LARANJA
    b = [txt(20, 24, "Esquema estrela (dw) e quantas linhas cada tabela tem", 14, TINTA, peso="600")]
    pos = {"fato_pedido": (300, 190, 190, 56), "dim_cliente": (30, 190, 170, 56), "dim_tempo": (590, 190, 160, 56),
           "dim_canal": (110, 60, 160, 56), "dim_status": (520, 60, 160, 56),
           "fato_item_pedido": (300, 330, 190, 56), "dim_produto": (590, 330, 160, 56),
           "fato_atendimento": (30, 330, 170, 56), "fato_avaliacao": (590, 410, 160, 50)}

    def centro(nome):
        x, y, w, h = pos[nome]
        return x + w / 2, y + h / 2

    def lig(a, c, rot=None, dx=0, dy=0):
        (x1, y1), (x2, y2) = centro(a), centro(c)
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{MUDO}" stroke-width="1.5"/>'
                + (txt((x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy, rot, 11, TINTA2, "middle") if rot else ""))
    for a, c in (("fato_pedido", "dim_cliente"), ("fato_pedido", "dim_tempo"), ("fato_pedido", "dim_canal"),
                 ("fato_pedido", "dim_status"), ("fato_item_pedido", "fato_pedido"), ("fato_item_pedido", "dim_produto"),
                 ("fato_atendimento", "dim_cliente"), ("fato_avaliacao", "dim_produto")):
        b.append(lig(a, c))
    for nome, (x, y, w, h) in pos.items():
        cor = fato if nome.startswith("fato") else dim
        b.append(caixa(x, y, w, h, nome, [nf(n("dw." + nome)) + " linhas"], cor))
    b.append(txt(30, 404, "atendimento e avaliação não", 11, TINTA2))
    b.append(txt(30, 418, "ligam a pedido (RDT-13)", 11, TINTA2))
    b.append(txt(310, 410, "itens sem pedido ficam em", 11, TINTA2))
    b.append(txt(310, 424, f"dw.aux_item_quarentena ({nf(n('dw.aux_item_quarentena'))} linhas)", 11, TINTA2))
    b.append(legenda(20, 452, [(fato, "tabela-fato (eventos)"), (dim, "dimensão (descrições)")]))
    return svg(W, H, "Esquema estrela do DW",
               "Tabelas-fato de pedido, item, atendimento e avaliação ligadas às dimensões de cliente, tempo, canal, status e produto.",
               "\n".join(b))


# ------------------------------------------------------------------ 5. corte, alvo e vazamento (Semana 4)
def fig_tempo():
    ini, fim_dados = date(2023, 1, 1), date(2025, 12, 30)   # período coberto pelos dois sistemas (d01_volumes_periodos.md)
    corte, fim_alvo = date.fromisoformat(DATA_CORTE), date.fromisoformat(DATA_FIM_ALVO)
    W, H = 780, 370
    x0, x1 = 40, 740
    esc = (x1 - x0) / (fim_dados - ini).days

    def X(d):
        return x0 + (d - ini).days * esc
    b = [txt(20, 24, "Corte, janela do alvo e onde nasce o vazamento", 14, TINTA, peso="600")]
    xc, xf = X(corte), X(fim_alvo)
    b.append(ret(x0, 50, xc - x0, 150, LAVA[AZUL], None, 0))
    b.append(ret(xc, 50, xf - xc, 150, LAVA[LARANJA], None, 0))
    b.append(ret(xf, 50, x1 - xf, 150, LAVA[MUDO], None, 0))
    b.append(f'<line x1="{xc}" y1="44" x2="{xc}" y2="206" stroke="{TINTA2}" stroke-width="1.5"/>')
    b.append(f'<line x1="{xf}" y1="44" x2="{xf}" y2="206" stroke="{TINTA2}" stroke-width="1.5"/>')
    b.append(txt(x0 + 8, 70, "histórico (2023-01 em diante)", 12, TINTA, peso="600"))
    b.append(txt(x0 + 8, 86, "o que se sabe no dia do corte", 12, TINTA2))
    b.append(f'<line x1="{xf}" y1="206" x2="{xf}" y2="236" stroke="{TINTA2}" stroke-width="1"/>')
    b.append(txt(xc - 6, 224, f"corte · {date.fromisoformat(DATA_CORTE).strftime('%d/%m/%Y')}", 12, TINTA, "end", "600"))
    b.append(txt(x1 + 30, 250, f"fim do alvo · {fim_alvo.strftime('%d/%m/%Y')}", 12, TINTA, "end", "600"))
    b.append(txt((xc + xf) / 2, 70, "alvo", 12, TINTA, "middle", "600"))
    b.append(txt((xc + xf) / 2, 86, f"{JANELA_ALVO_DIAS} dias", 12, TINTA2, "middle"))
    b.append(txt((xf + x1) / 2, 70, "depois", 12, TINTA, "middle", "600"))
    b.append(txt((xf + x1) / 2, 86, "do alvo", 12, TINTA2, "middle"))
    # versão correta
    b.append(ret(x0, 106, xc - x0, 14, AZUL, None, 4))
    b.append(txt(x0 + 8, 140, "Versão correta: todo atributo usa só o histórico", 12, TINTA2))
    # versão com vazamento
    b.append(ret(x0, 156, x1 - x0, 14, LARANJA, None, 4))
    b.append(txt(x0 + 8, 190, "Com vazamento: recência e frequência usam também o alvo e o que vem depois", 12, TINTA2))
    b.append(txt(20, 282, f"Efeito: em {nf(REG['rdt15.recencia_negativa'])} clientes ({dec(REG['rdt15.recencia_negativa_pct'] if 'rdt15.recencia_negativa_pct' in REG else REG['rdt15.recencia_diferente_da_correta_pct'])}%) "
                 "a recência fica negativa, porque o último pedido é posterior ao corte;", 12, TINTA2))
    b.append(txt(20, 300, f"isso acontece em todos os {nf(REG['rdt15.positivos_com_recencia_negativa'])} positivos. "
                 "O modelo \"vê\" a resposta.", 12, TINTA2))
    b.append(legenda(20, 340, [(AZUL, "dados permitidos (até o corte)"), (LARANJA, "dados que não existiriam no momento da predição")], 260))
    return svg(W, H, "Corte, janela do alvo e vazamento",
               "Linha do tempo de 2023 a 2025 com o corte, a janela de 90 dias do alvo e quais períodos cada versão da tabela usa.",
               "\n".join(b))


# ------------------------------------------------------------------ 6. fluxo do Orange (Semana 4)
def fig_orange():
    p = EXP["particao"]
    W, H = 780, 350
    b = [txt(20, 24, "O fluxo do Orange (idêntico nas duas versões; muda só o arquivo de entrada)", 14, TINTA, peso="600")]
    for i, (nome, x, w) in enumerate([("Naive Bayes", 370, 124), ("Logistic Regression", 504, 152), ("Tree", 666, 100)]):
        b.append(caixa(x, 44, w, 38, nome, [], VERDE, tam=11))
        b.append(seta(x + w / 2, 84, 520 + i * 55, 138))
    b.append(caixa(10, 150, 132, 52, "File", ["abt_recompra_*.csv"], MUDO, tam=11))
    b.append(seta(144, 176, 168, 176))
    b.append(caixa(170, 126, 190, 100, "Data Sampler", ["70% treino · 30% teste", "estratificado", "semente fixa, sem reposição"], VERDE))
    b.append(seta(362, 158, 468, 158))
    b.append(txt(366, 150, f"treino: {nf(p['treino'])}", 12, TINTA2))
    b.append(txt(366, 174, f"({nf(p['positivos_treino'])} positivos)", 11, TINTA2))
    b.append(seta(362, 206, 468, 206))
    b.append(txt(366, 198, f"teste: {nf(p['teste'])}", 12, TINTA2))
    b.append(txt(366, 222, f"({nf(p['positivos_teste'])} positivos)", 11, TINTA2))
    b.append(caixa(470, 138, 210, 84, "Test & Score", ["avalia no conjunto de teste", "classe-alvo 1 · parâmetros padrão"], VERDE))
    b.append(seta(530, 224, 530, 268))
    b.append(seta(620, 224, 660, 268))
    b.append(caixa(450, 270, 150, 40, "Confusion Matrix", [], VERDE, tam=11))
    b.append(caixa(620, 270, 140, 40, "ROC Analysis", [], VERDE, tam=11))
    b.append(txt(20, 336, "Métricas lidas: AUC, acurácia, recall e especificidade; acurácia balanceada = (recall + especificidade) / 2.", 12, TINTA2))
    return svg(W, H, "Fluxo do Orange",
               "File, Data Sampler com partição 70/30 estratificada, três modelos ligados ao Test & Score, Confusion Matrix e ROC Analysis.",
               "\n".join(b))


# ------------------------------------------------------------------ 7. AUC e acurácia balanceada (Semana 4)
def fig_resultados():
    modelos = ["Naive Bayes", "Logistic Regression", "Tree"]
    dados = {(r["fluxo"], r["modelo"]): r for r in ORANGE}
    W, H = 780, 380
    b = [txt(20, 24, "Resultados no Orange, conjunto de teste: versão correta contra versão com vazamento", 14, TINTA, peso="600")]
    b.append(legenda(20, 50, [(AZUL, "Versão correta"), (LARANJA, "Versão com vazamento")], 150))

    def painel(x0, titulo, campo):
        larg, alt, topo = 330, 200, 90
        base = topo + alt
        out = [txt(x0, 76, titulo, 13, TINTA, peso="600")]
        for v in (0, 0.5, 1):
            y = base - v * alt
            out.append(f'<line x1="{x0}" y1="{y}" x2="{x0 + larg}" y2="{y}" stroke="{EIXO if v == 0 else GRADE}" stroke-width="1"/>')
            out.append(txt(x0 - 6, y + 4, dec(v, 1) if v not in (0, 1) else str(int(v)), 11, MUDO, "end"))
        out.append(txt(x0 + larg + 2, base - 0.5 * alt - 4, "acaso", 11, MUDO, "end"))
        grupo = larg / 3
        for i, m in enumerate(modelos):
            cx = x0 + i * grupo + grupo / 2
            for j, (fluxo, cor) in enumerate((("correta", AZUL), ("vazamento", LARANJA))):
                v = float(dados[(fluxo, m)][campo])
                h = v * alt
                bx = cx - 23 + j * 24
                y = base - h
                r = 4
                out.append(f'<path d="M{bx},{base} V{y + r} a{r},{r} 0 0 1 {r},-{r} h{22 - 2 * r} a{r},{r} 0 0 1 {r},{r} V{base} z" fill="{cor}"/>')
                ancora, rx = ("end", bx + 22) if j == 0 else ("start", bx)
                rotulo = dec_min3(v)
                # halo (contorno na cor da superfície) desenhado por baixo, para o valor não "riscar" a grade
                out.append(f'<text x="{rx}" y="{y - 5}" font-size="11" fill="{SUPERFICIE}" text-anchor="{ancora}" '
                           f'stroke="{SUPERFICIE}" stroke-width="3">{rotulo}</text>')
                out.append(txt(rx, y - 5, rotulo, 11, TINTA, ancora))
            out.append(txt(cx, base + 18, m, 11, TINTA2, "middle"))
        return "\n".join(out)
    b.append(painel(40, "AUC", "auc"))
    b.append(painel(430, "Acurácia balanceada", "acuracia_balanceada"))
    b.append(txt(20, 350, "Com vazamento a AUC sobe de perto do acaso (0,5) para 0,87 a 0,97. O número alto não mede capacidade de predição:", 12, TINTA2))
    b.append(txt(20, 368, "dois atributos já contêm informação sobre o alvo. Valores exatos na tabela de resultados da Semana 4.", 12, TINTA2))
    return svg(W, H, "Resultados do experimento",
               "Barras agrupadas por modelo mostrando AUC e acurácia balanceada nas versões correta e com vazamento, no Orange.",
               "\n".join(b))


def main():
    grava("01_visao_geral.svg", fig_visao_geral())
    grava("02_ligacoes_fontes.svg", fig_ligacoes())
    grava("03_unificacao_clientes.svg", fig_unificacao())
    grava("04_esquema_estrela.svg", fig_estrela())
    grava("05_corte_janela_vazamento.svg", fig_tempo())
    grava("06_fluxo_orange.svg", fig_orange())
    grava("07_resultados.svg", fig_resultados())


if __name__ == "__main__":
    main()
