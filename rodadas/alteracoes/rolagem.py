"""Rolagem de horizonte de modif.dat, expt.dat e clast.dat (NEWAVE).

A logica de rolagem esta nos modulos ``_*_original`` (portados sem alteracao de
prepara-deck). Aqui ficam so o registro, a regra de aplicabilidade e as conferencias:

- O mes-base e' deduzido do PROPRIO arquivo (menor data), como no algoritmo original.
  O dger.dat nao serve de base: nos decks a rolar ele ja vem no mes-alvo.
- Sugere rolar somente se mes-alvo > mes-base (se forem iguais nada mudaria).
- Mes-alvo anterior ao mes-base: aviso e nao roda, mesmo se o usuario escolher.
- Se o inicio do estudo no dger.dat for diferente do mes-alvo, a rolagem roda e
  devolve um AVISO (o dger.dat nao e' alterado por esta alteracao).
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


def _inicio_no_dger(ctx: Contexto) -> tuple[int, int] | None:
    if ctx.deck.tem("dger"):
        d = ler_dger(ctx.deck.caminho("dger"))
        return d.mes_inicio, d.ano_inicio
    return None


def _aplicavel(papel: str):
    def regra(ctx: Contexto) -> tuple[bool, str]:
        if ctx.mes_alvo is None:
            return False, "mes-alvo nao identificado (coloque AAAAMM no nome da pasta do deck)"
        if not ctx.deck.tem(papel):
            return False, f"{papel}.dat nao encontrado no deck"
        base = _BASE_DO_ARQUIVO[papel](ctx.deck.caminho(papel))
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
            raise ErroAlteracao(f"{nome}: mes-alvo nao identificado (coloque AAAAMM no nome da pasta do deck)")
        caminho = str(ctx.deck.caminho(papel))
        avisos: list[str] = []
        base = _BASE_DO_ARQUIVO[papel](ctx.deck.caminho(papel))
        if base and to_idx(*ctx.mes_alvo) < to_idx(*base):
            avisos.append(
                f"mes-alvo {_fmt(ctx.mes_alvo)} anterior ao mes-base {_fmt(base)}; "
                f"rolagem nao executada")
            return Resultado(nome, False, {"arquivo": f"{papel}.dat", "alterado": False}, avisos)
        inicio = _inicio_no_dger(ctx)
        if inicio and inicio != ctx.mes_alvo:
            avisos.append(
                f"dger.dat indica inicio do estudo em {_fmt(inicio)}, diferente do mes-alvo "
                f"{_fmt(ctx.mes_alvo)} (o dger.dat nao e' alterado por esta rolagem)")
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
