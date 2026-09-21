"""Orquestrador: monta o plano e executa as alteracoes em uma COPIA do deck.

Nao sabe quem o chamou (linha de comando hoje, API amanha). As regras de
aplicabilidade apenas sugerem; o usuario pode escolher, forcar ou pular.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .alteracoes import REGISTRO, Contexto, Resultado
from .alteracoes.registro import avaliar_aplicabilidade
from .core.deck import carregar_deck


@dataclass
class Passo:
    nome: str
    executar: bool
    motivo: str


def montar_plano(ctx: Contexto, escolhidas: list[str] | None = None,
                 forcar: list[str] | None = None, pular: list[str] | None = None) -> list[Passo]:
    """Sem ``escolhidas``: sugere pelas regras. Com ``escolhidas``: usa a ordem
    e a lista do usuario (regras viram so aviso). ``forcar`` ignora a regra de
    aplicabilidade; ``pular`` remove do plano."""
    forcar, pular = set(forcar or []), set(pular or [])
    nomes = escolhidas if escolhidas is not None else list(REGISTRO)
    desconhecidas = [n for n in nomes if n not in REGISTRO]
    if desconhecidas:
        raise KeyError(f"alteracao(oes) inexistente(s): {', '.join(desconhecidas)}")

    plano: list[Passo] = []
    for nome in nomes:
        if nome in pular:
            plano.append(Passo(nome, False, "pulada pelo usuario"))
            continue
        aplica, motivo = avaliar_aplicabilidade(REGISTRO[nome], ctx)
        if escolhidas is not None or nome in forcar:
            origem = "escolhida pelo usuario" if nome not in forcar else "forcada pelo usuario"
            plano.append(Passo(nome, True, origem + ("" if aplica else f" (regra diz: {motivo})")))
        else:
            plano.append(Passo(nome, aplica, motivo))
    return plano


def preparar_copia(pasta_deck: Path, pasta_saida: Path) -> Path:
    """Copia o deck original; todas as alteracoes acontecem na copia."""
    pasta_saida = Path(pasta_saida)
    if pasta_saida.resolve().is_relative_to(Path(pasta_deck).resolve()):
        raise ValueError(f"a pasta de saida nao pode ficar dentro da pasta do deck: {pasta_saida}")
    if pasta_saida.exists():
        raise FileExistsError(f"pasta de saida ja existe: {pasta_saida}")
    shutil.copytree(pasta_deck, pasta_saida)
    return pasta_saida


def executar_plano(plano: list[Passo], ctx: Contexto, params: dict[str, dict] | None = None,
                   simular: bool = False) -> list[Resultado]:
    params = params or {}
    resultados: list[Resultado] = []
    for passo in plano:
        if not passo.executar:
            continue
        if simular:
            resultados.append(Resultado(passo.nome, False, {"simulado": True}))
            continue
        resultados.append(REGISTRO[passo.nome].executar(ctx, params.get(passo.nome, {})))
    return resultados


def rodar(pasta_deck: Path, pasta_saida: Path, mes_alvo: tuple[int, int] | None = None,
          escolhidas: list[str] | None = None, forcar: list[str] | None = None,
          pular: list[str] | None = None, params: dict[str, dict] | None = None,
          dados_externos: dict[str, str] | None = None, simular: bool = False):
    """Ponto de entrada unico (CLI e futura API). Devolve (plano, resultados)."""
    if simular:
        ctx = Contexto(carregar_deck(pasta_deck), mes_alvo, dados_externos or {})
    else:
        copia = preparar_copia(pasta_deck, pasta_saida)
        ctx = Contexto(carregar_deck(copia), mes_alvo, dados_externos or {})
    plano = montar_plano(ctx, escolhidas, forcar, pular)
    return plano, executar_plano(plano, ctx, params, simular)
