"""Atualizacao de CVU: bloco estrutural/conjuntural do clast.dat (NEWAVE) e
registros CT do dadger (DECOMP).

A logica de calculo esta em ``_cvu_clast_original`` e ``_cvu_dadger_original``
(portados sem alteracao de att-cvu). Aqui: localizacao dos CSVs, leitura/escrita
do arquivo preservando codificacao e terminador de linha, e o registro.

Onde ficam os CSVs (ordem de prioridade):
  1. parametro explicito da alteracao (``csv_estrutural``, ``csv_conjuntural``, ``csv_merchant``);
  2. ``dados_externos`` (mesmas chaves, prefixadas por ``cvu_``: ``cvu_estrutural_csv`` ...);
  3. ``dados_externos["cvu_dir"]`` + nome padrao com o ano (``ano_csv``, senao o do mes-alvo/dger).
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from ..core import texto
from ..core.dger import ler_dger
from . import _cvu_clast_original as _clast
from . import _cvu_dadger_original as _dadger
from .registro import Contexto, ErroAlteracao, Parametro, Resultado, registrar

log = logging.getLogger(__name__)

_P_CVU_DIR = Parametro("cvu_dir", "Pasta com os CSVs de CVU", "pasta", obrigatorio=True,
                       externo="cvu_dir", lembrar=True)
_P_CONJ = Parametro("conjuntural", "Qual CSV conjuntural usar", "opcao", ("revisado", "normal"), "revisado")
_P_ANO = Parametro("ano_csv", "Ano no nome dos CSVs (Enter = ano do mes-alvo/dger)", "texto")

_NOMES_CSV = {
    "estrutural": "custo_variavel_unitario_estrutural_{ano}.csv",
    "conjuntural_normal": "custo_variavel_unitario_conjuntural_{ano}.csv",
    "conjuntural_revisado": "custo_variavel_unitario_conjuntural_revisado_{ano}.csv",
    "merchant": "custo_variavel_unitario_merchant_{ano}.csv",
}


def _ano_csv(ctx: Contexto, params: dict) -> int:
    if params.get("ano_csv"):
        return int(params["ano_csv"])
    if ctx.mes_alvo:
        return ctx.mes_alvo[1]
    if ctx.deck.tem("dger"):
        return ler_dger(ctx.deck.caminho("dger")).ano_inicio
    raise ErroAlteracao("nao foi possivel definir o ano dos CSVs de CVU; informe 'ano_csv'")


def _caminho_csv(ctx: Contexto, params: dict, tipo: str) -> str:
    """tipo: estrutural | conjuntural_normal | conjuntural_revisado | merchant"""
    base = tipo.split("_")[0]  # 'conjuntural_revisado' -> 'conjuntural'
    explicito = params.get(f"csv_{base}") if base != "conjuntural" else (
        params.get("csv_conjuntural"))
    externo = ctx.dados_externos.get(f"cvu_{base}_csv")
    if tipo.startswith("conjuntural") and externo is None:
        externo = ctx.dados_externos.get(f"cvu_{tipo}_csv")
    caminho = explicito or externo
    if not caminho:
        pasta = ctx.dados_externos.get("cvu_dir")
        if not pasta:
            raise ErroAlteracao(
                f"CSV de CVU '{tipo}' nao informado (use 'cvu_dir' ou o caminho do arquivo)")
        caminho = str(Path(pasta) / _NOMES_CSV[tipo].format(ano=_ano_csv(ctx, params)))
    if not Path(caminho).is_file():
        raise ErroAlteracao(f"CSV de CVU nao encontrado: {caminho}")
    return caminho


def _csv_conjuntural(ctx: Contexto, params: dict) -> str:
    fonte = params.get("conjuntural", "revisado")
    if fonte not in ("normal", "revisado"):
        raise ErroAlteracao("parametro 'conjuntural' deve ser 'normal' ou 'revisado'")
    return _caminho_csv(ctx, params, f"conjuntural_{fonte}")


def _tem_cvu_externos(ctx: Contexto) -> tuple[bool, str]:
    if any(k.startswith("cvu_") for k in ctx.dados_externos):
        return True, "CSVs de CVU informados"
    return False, "CSVs de CVU nao informados"


def _ler_linhas(caminho: Path) -> tuple[list[str], str]:
    dados = caminho.read_bytes()
    enc = texto.detectar_encoding(dados)
    # newline="" mantem CRLF/LF exatamente como estao
    return io.StringIO(dados.decode(enc), newline="").readlines(), enc


# ---------------------------------------------------------------------------
# clast.dat
# ---------------------------------------------------------------------------

def _aplicavel_clast(ctx: Contexto) -> tuple[bool, str]:
    if not ctx.deck.tem("clast"):
        return False, "clast.dat nao encontrado no deck"
    return _tem_cvu_externos(ctx)


@registrar("cvu_clast", "Atualiza o CVU (estrutural e/ou conjuntural) do clast.dat a partir dos CSVs",
           ("newave",), aplicavel=_aplicavel_clast,
           parametros=(_P_CVU_DIR,
                       Parametro("modo", "O que atualizar", "opcao", ("ambos", "estrutural", "conjuntural"), "ambos"),
                       _P_CONJ, _P_ANO,
                       Parametro("graficos", "Gerar graficos antigo x novo", "bool", padrao=False)))
def cvu_clast(ctx: Contexto, params: dict) -> Resultado:
    """params: modo ('ambos'|'estrutural'|'conjuntural'), conjuntural ('revisado'|'normal'),
    graficos (bool, padrao False), csv_estrutural/csv_conjuntural/csv_merchant, ano_csv."""
    modo = params.get("modo", "ambos")
    if modo not in ("estrutural", "conjuntural", "ambos"):
        raise ErroAlteracao("parametro 'modo' deve ser 'estrutural', 'conjuntural' ou 'ambos'")
    caminho = ctx.deck.caminho("clast")
    linhas, enc = _ler_linhas(caminho)
    bloco1, bloco2 = _clast.dividir_clast(linhas)

    fazer_est = modo in ("estrutural", "ambos")
    fazer_conj = modo in ("conjuntural", "ambos")
    graficos = bool(params.get("graficos", False))
    pasta_graficos = ctx.deck.pasta.parent / f"{ctx.deck.pasta.name}_graficos_cvu"
    resumo: dict = {"modo": modo}

    if fazer_est:
        csv_est = _caminho_csv(ctx, params, "estrutural")
        cvu_map, anos = _clast.carregar_csv_estrutural(csv_est, sep=",", encoding="utf-8")
        bloco1, dif, atualizadas, sem_match = _clast.processar_bloco_estrutural(bloco1, cvu_map)
        if graficos:
            _clast.gerar_graficos_estrutural(dif, anos, pasta_graficos)
        resumo.update(estrutural_atualizadas=len(atualizadas), estrutural_sem_match=len(sem_match),
                      estrutural_codigos_sem_match=sem_match)

    if fazer_conj:
        csv_conj = _csv_conjuntural(ctx, params)
        csv_merch = _caminho_csv(ctx, params, "merchant")
        cvu_map, mes_ref_map = _clast.carregar_csvs_conjuntural(csv_conj, csv_merch)
        bloco2, alteradas, comparacao = _clast.processar_bloco_conjuntural(bloco2, cvu_map, mes_ref_map)
        if graficos:
            _clast.gerar_grafico_conjuntural(comparacao, pasta_graficos)
        resumo.update(conjuntural_linhas_alteradas=alteradas)

    caminho.write_bytes("".join(bloco1 + bloco2).encode(enc))
    avisos = []
    if resumo.get("estrutural_sem_match"):
        avisos.append(f"{resumo['estrutural_sem_match']} usina(s) do bloco estrutural sem CVU nos CSVs "
                      f"tiveram os 5 CVUs zerados (comportamento original): "
                      f"{resumo['estrutural_codigos_sem_match']}")
    return Resultado("cvu_clast", True, resumo, avisos)


# ---------------------------------------------------------------------------
# dadger (DECOMP)
# ---------------------------------------------------------------------------

def _aplicavel_dadger(ctx: Contexto) -> tuple[bool, str]:
    if not ctx.deck.tem("dadger"):
        return False, "dadger nao encontrado no deck"
    return _tem_cvu_externos(ctx)


@registrar("cvu_dadger", "Atualiza o CVU dos registros CT do dadger a partir dos CSVs conjuntural + merchant",
           ("decomp",), aplicavel=_aplicavel_dadger,
           parametros=(_P_CVU_DIR, _P_CONJ, _P_ANO,
                       Parametro("estagios_preservar", "Estagios a NAO alterar (numeros separados por virgula; Enter = nenhum)",
                                 "lista_int", padrao=[])))
def cvu_dadger(ctx: Contexto, params: dict) -> Resultado:
    """params: conjuntural ('revisado'|'normal'), estagios_preservar (lista de int, padrao vazia),
    csv_conjuntural/csv_merchant, ano_csv."""
    preservar = params.get("estagios_preservar", [])
    if isinstance(preservar, (int, str)):
        preservar = [preservar]
    preservar = {int(e) for e in preservar}
    caminho = ctx.deck.caminho("dadger")
    cvu_map, _ = _clast.carregar_csvs_conjuntural(_csv_conjuntural(ctx, params),
                                                   _caminho_csv(ctx, params, "merchant"))
    linhas = caminho.read_bytes().decode("latin-1").splitlines(keepends=True)
    saida, alteradas = [], 0
    for linha in linhas:
        nova, cod, antigo, novo = _dadger.atualizar_linha_ct(linha, cvu_map, preservar)
        if nova != linha:
            alteradas += 1
            log.info("[dadger] COD %5d -> CVU alterado: %.2f -> %.2f", cod, antigo, novo)
        saida.append(nova)
    caminho.write_bytes("".join(saida).encode("latin-1"))
    return Resultado("cvu_dadger", alteradas > 0, {"linhas_ct_alteradas": alteradas,
                                                  "estagios_preservados": sorted(preservar)})
