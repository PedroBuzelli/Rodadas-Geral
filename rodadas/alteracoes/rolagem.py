"""Rolagem de horizonte de modif.dat, expt.dat e clast.dat (NEWAVE).

A logica de rolagem esta nos modulos ``_*_original`` (portados sem alteracao de
prepara-deck). Aqui ficam so o registro, a regra de aplicabilidade e a
conferencia do mes-base:

- Sugere rolar somente se mes-alvo > mes-base (se forem iguais nada mudaria).
- O mes-base oficial e' o do dger.dat; o arquivo tambem o deduz sozinho e, se
  os dois divergirem, a rolagem roda mesmo assim e devolve um AVISO.
"""

from __future__ import annotations

from typing import Callable

from ..core import mes_base
from ..core.datas import to_idx
from ..core.dger import ler_dger
from . import _clast_original, _expt_original, _modif_original
from .registro import Contexto, ErroAlteracao, Resultado, registrar

_BASE_DO_ARQUIVO = {
    "expt": mes_base.mes_base_expt,
    "modif": mes_base.mes_base_modif,
    "clast": mes_base.mes_base_clast,
}


def _fmt(d: tuple[int, int]) -> str:
    return f"{d[0]:02d}/{d[1]}"


def _base_oficial(ctx: Contexto) -> tuple[int, int] | None:
    if ctx.deck.tem("dger"):
        d = ler_dger(ctx.deck.caminho("dger"))
        return d.mes_inicio, d.ano_inicio
    return None


def _aplicavel(papel: str):
    def regra(ctx: Contexto) -> tuple[bool, str]:
        if ctx.mes_alvo is None:
            return False, "mes-alvo nao informado"
        if not ctx.deck.tem(papel):
            return False, f"{papel}.dat nao encontrado no deck"
        base = _base_oficial(ctx) or _BASE_DO_ARQUIVO[papel](ctx.deck.caminho(papel))
        if base is None:
            return False, f"{papel}.dat sem datas para rolar"
        if ctx.mes_alvo == base:
            return False, f"mes-alvo igual ao mes-base ({_fmt(base)}); nada mudaria"
        if to_idx(*ctx.mes_alvo) < to_idx(*base):
            return False, f"mes-alvo {_fmt(ctx.mes_alvo)} anterior ao mes-base {_fmt(base)}"
        return True, f"mes-base {_fmt(base)} -> mes-alvo {_fmt(ctx.mes_alvo)}"
    return regra


def _executor(papel: str, nome: str, rolar: Callable[..., dict]):
    def executar(ctx: Contexto, params: dict) -> Resultado:
        if ctx.mes_alvo is None:
            raise ErroAlteracao(f"{nome}: informe o mes-alvo")
        caminho = str(ctx.deck.caminho(papel))
        avisos: list[str] = []
        oficial = _base_oficial(ctx)
        no_arquivo = _BASE_DO_ARQUIVO[papel](ctx.deck.caminho(papel))
        if oficial and no_arquivo and oficial != no_arquivo:
            avisos.append(
                f"mes-base do dger.dat ({_fmt(oficial)}) difere do deduzido em {papel}.dat "
                f"({_fmt(no_arquivo)}); a rolagem usa o do proprio arquivo (algoritmo original)")
        base = oficial or no_arquivo
        if base and to_idx(*ctx.mes_alvo) < to_idx(*base):
            avisos.append(
                f"mes-alvo {_fmt(ctx.mes_alvo)} anterior ao mes-base {_fmt(base)}; "
                f"rolagem nao executada")
            return Resultado(nome, False, {"arquivo": f"{papel}.dat", "alterado": False}, avisos)
        resumo = rolar(caminho, caminho, *ctx.mes_alvo)
        avisos += list(resumo.pop("avisos", []) or [])
        if resumo.get("aviso"):
            avisos.append(resumo.pop("aviso"))
        return Resultado(nome, bool(resumo.get("alterado")), resumo, avisos)
    return executar


registrar("rolagem_expt", "Rola o horizonte do expt.dat para o mes-alvo", ("newave",),
          aplicavel=_aplicavel("expt"))(_executor("expt", "rolagem_expt", _expt_original.roll_expt))

registrar("rolagem_modif", "Rola o horizonte do modif.dat para o mes-alvo", ("newave",),
          aplicavel=_aplicavel("modif"))(_executor("modif", "rolagem_modif", _modif_original.roll_modif))

registrar("rolagem_clast", "Rola o bloco conjuntural do clast.dat para o mes-alvo", ("newave",),
          aplicavel=_aplicavel("clast"))(_executor("clast", "rolagem_clast", _clast_original.roll_clast_para_mes))
