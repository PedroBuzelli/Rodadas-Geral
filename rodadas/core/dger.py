"""Leitura do dger.dat (NEWAVE): mes/ano de inicio do estudo e origem do deck."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import texto

ROTULO_MES = "MES INICIO DO ESTUDO"
ROTULO_ANO = "ANO INICIO DO ESTUDO"
COLUNA_VALOR = 21  # o valor comeca logo apos o rotulo de 21 caracteres


@dataclass
class DgerInfo:
    titulo: str
    mes_inicio: int
    ano_inicio: int
    origem: str  # "ons" (titulo PMO...), "ccee" (PLD...) ou "desconhecida"


def _valor_inteiro(linhas: list[str], rotulo: str) -> int:
    for linha in linhas:
        if linha.startswith(rotulo):
            campo = linha[COLUNA_VALOR:].split()
            if campo:
                return int(campo[0])
    raise ValueError(f"dger.dat: linha {rotulo!r} nao encontrada ou sem valor")


def origem_pelo_titulo(titulo: str) -> str:
    t = titulo.strip().upper()
    if t.startswith("PMO"):
        return "ons"
    if t.startswith("PLD"):
        return "ccee"
    return "desconhecida"


def ler_dger(caminho: Path) -> DgerInfo:
    arq = texto.ler(caminho)
    titulo = arq.linhas[0].rstrip() if arq.linhas else ""
    return DgerInfo(
        titulo=titulo,
        mes_inicio=_valor_inteiro(arq.linhas, ROTULO_MES),
        ano_inicio=_valor_inteiro(arq.linhas, ROTULO_ANO),
        origem=origem_pelo_titulo(titulo),
    )
