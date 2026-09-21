"""Mes-base deduzido do proprio arquivo (menor data de inicio).

Serve como conferencia contra o mes de inicio oficial do dger.dat.
Formatos e colunas iguais aos dos roladores originais (prepara-deck).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import texto
from .datas import from_idx, to_idx

_N_CABECALHO_EXPT = 2
_EXPT_MI, _EXPT_ANOI = slice(20, 22), slice(23, 27)
_CLAST_MI, _CLAST_ANOI = slice(15, 19), slice(19, 24)
_CLAST_CONJ_RE = re.compile(r"^\s*\d+\s+[\d.]+\s+\d+\s+\d{4}")


def _int(campo: str) -> int | None:
    campo = campo.strip()
    return int(campo) if campo.isdigit() else None


def _menor(datas: list[tuple[int, int]]) -> tuple[int, int] | None:
    if not datas:
        return None
    return from_idx(min(to_idx(m, a) for m, a in datas))


def mes_base_expt(caminho: Path) -> tuple[int, int] | None:
    datas = []
    for linha in texto.ler(caminho).linhas[_N_CABECALHO_EXPT:]:
        if len(linha) < _EXPT_ANOI.stop:
            continue
        mes, ano = _int(linha[_EXPT_MI]), _int(linha[_EXPT_ANOI])
        if mes and ano:
            datas.append((mes, ano))
    return _menor(datas)


def mes_base_clast(caminho: Path) -> tuple[int, int] | None:
    """Menor data de inicio do bloco conjuntural."""
    linhas = texto.ler(caminho).linhas
    inicio = next((i for i, l in enumerate(linhas) if _CLAST_CONJ_RE.match(l)), None)
    if inicio is None:
        return None
    datas = []
    for linha in linhas[inicio:]:
        if len(linha) < _CLAST_ANOI.stop:
            continue
        mes, ano = _int(linha[_CLAST_MI]), _int(linha[_CLAST_ANOI])
        if mes and ano:
            datas.append((mes, ano))
    return _menor(datas)


def mes_base_modif(caminho: Path) -> tuple[int, int] | None:
    """Menor data entre todas as linhas 'PALAVRA-CHAVE mes ano ...'."""
    datas = []
    for linha in texto.ler(caminho).linhas:
        t = linha.split()
        if len(t) < 3 or t[0] == "USINA":
            continue
        if re.fullmatch(r"\d{1,2}", t[1]) and re.fullmatch(r"\d{4}", t[2]) and 1 <= int(t[1]) <= 12:
            datas.append((int(t[1]), int(t[2])))
    return _menor(datas)
