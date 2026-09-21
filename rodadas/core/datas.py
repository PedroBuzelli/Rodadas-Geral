"""Aritmetica de mes/ano.

Datas sao comparadas por um indice absoluto (``ano * 12 + mes``), o que
torna "somar N meses" e comparacoes cronologicas corretas na virada de ano.
"""

from __future__ import annotations


def to_idx(mes: int, ano: int) -> int:
    return ano * 12 + mes


def from_idx(idx: int) -> tuple[int, int]:
    """Inverso de ``to_idx``: retorna (mes, ano)."""
    return (idx - 1) % 12 + 1, (idx - 1) // 12


def add_months(mes: int, ano: int, n: int) -> tuple[int, int]:
    return from_idx(to_idx(mes, ano) + n)
