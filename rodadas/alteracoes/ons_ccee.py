"""Conversao de deck NEWAVE da versao ONS para a versao CCEE (dger.dat + expt.dat).

A logica esta em ``_ons_ccee_original`` (portada sem alteracao de ONS-to-CCEE).
Entrada externa: planilha GTMIN_CCEE_<mes>.xlsx (``dados_externos["gtmin_ccee_xlsx"]``
ou parametro ``gtmin_xlsx``).
"""

from __future__ import annotations

from pathlib import Path

from ..core.dger import ler_dger
from . import _ons_ccee_original as _orig
from .registro import Contexto, ErroAlteracao, Parametro, Resultado, registrar


def _aplicavel(ctx: Contexto) -> tuple[bool, str]:
    if not (ctx.deck.tem("dger") and ctx.deck.tem("expt")):
        return False, "dger.dat/expt.dat nao encontrados no deck"
    origem = ler_dger(ctx.deck.caminho("dger")).origem
    if origem == "ccee":
        return False, "deck ja esta na versao CCEE (titulo PLD)"
    if origem == "desconhecida":
        return False, "titulo do dger.dat nao comeca com PMO nem PLD; origem desconhecida"
    if "gtmin_ccee_xlsx" not in ctx.dados_externos:
        esperado = (f"GTMIN_CCEE_{ctx.mes_alvo[0]:02d}{ctx.mes_alvo[1]}.xlsx" if ctx.mes_alvo
                    else "GTMIN_CCEE_<mes><ano>.xlsx")
        return False, f"planilha GTMIN CCEE nao encontrada (coloque {esperado} na pasta do deck ou do estudo)"
    return True, "deck de origem ONS (titulo PMO)"


@registrar("ons_para_ccee", "Converte dger.dat e expt.dat da versao ONS para a versao CCEE",
           ("newave",), aplicavel=_aplicavel,
           parametros=(Parametro("gtmin_ccee_xlsx", "Planilha GTMIN CCEE (.xlsx)", "arquivo",
                                 obrigatorio=True, externo="gtmin_ccee_xlsx"),))
def ons_para_ccee(ctx: Contexto, params: dict) -> Resultado:
    xlsx = params.get("gtmin_xlsx") or ctx.dados_externos.get("gtmin_ccee_xlsx")
    if not xlsx or not Path(xlsx).is_file():
        raise ErroAlteracao(f"planilha GTMIN CCEE nao encontrada: {xlsx}")
    dger, expt = ctx.deck.caminho("dger"), ctx.deck.caminho("expt")
    log: list[str] = []
    _orig.transform_dger(dger, dger, log)
    _orig.transform_expt(expt, expt, Path(xlsx), log)
    avisos = [l for l in log if "[ERRO]" in l or "[aviso]" in l or "[fallback]" in l]
    return Resultado("ons_para_ccee", True, {"log": log}, avisos)
