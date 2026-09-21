# PORTE de prepara-deck/roll_deck/modifiers/clast_roller.py (commit 0f5e161).
# A logica das funcoes abaixo e' a original; so mudaram imports e o registro.
# As regras da secao 'wrapper' no fim do arquivo sao novas.

"""Rolagem do bloco conjuntural do CLAST.DAT (DECOMP).

Implementa as regras descritas em
``instruções arquivos/GUIA_ROLAGEM_CLAST.md``.

Diferente do MODIF e do EXPT, aqui nenhum registro e' removido ou criado:
a data mais antiga do bloco conjuntural e' sempre o mes-base do proprio
arquivo de entrada, entao a rolagem e' uma translacao uniforme de todas as
datas por N meses.
"""

from __future__ import annotations

import re

from ..core.datas import from_idx, to_idx

_CONJUNTURAL_LINE_RE = re.compile(r"^\s*\d+\s+[\d.]+\s+\d+\s+\d{4}")

_MI = slice(15, 19)
_ANOI = slice(19, 24)
_MF = slice(24, 28)
_ANOF = slice(28, 33)


def _parse_int(field: str) -> int | None:
    field = field.strip()
    return int(field) if field else None


def _find_bloco_conjuntural_start(lines: list[str]) -> int | None:
    for i, raw in enumerate(lines):
        if _CONJUNTURAL_LINE_RE.match(raw):
            return i
    return None


def _roll_line(raw: str, n_meses: int) -> str:
    mi = _parse_int(raw[_MI]) if len(raw) >= _MI.stop else None
    anoi = _parse_int(raw[_ANOI]) if len(raw) >= _ANOI.stop else None
    if mi is None or anoi is None:
        return raw

    novo_mi, novo_anoi = from_idx(to_idx(mi, anoi) + n_meses)
    novo_mi_txt = f"{novo_mi:>4}"
    novo_anoi_txt = f"{novo_anoi:>5}"

    mf = _parse_int(raw[_MF]) if len(raw) >= _MF.stop else None
    anof = _parse_int(raw[_ANOF]) if len(raw) >= _ANOF.stop else None
    if mf is not None and anof is not None:
        novo_mf, novo_anof = from_idx(to_idx(mf, anof) + n_meses)
        novo_mf_txt = f"{novo_mf:>4}"
        novo_anof_txt = f"{novo_anof:>5}"
    else:
        novo_mf_txt = raw[_MF] if len(raw) >= _MF.stop else " " * 4
        novo_anof_txt = raw[_ANOF] if len(raw) >= _ANOF.stop else " " * 5

    resto = raw[_ANOF.stop :] if len(raw) > _ANOF.stop else ""
    return (
        raw[: _MI.start]
        + novo_mi_txt
        + novo_anoi_txt
        + novo_mf_txt
        + novo_anof_txt
        + resto
    )


def roll_clast(in_path: str, out_path: str, n_meses: int) -> dict:
    """Rola o bloco conjuntural do CLAST.DAT em ``n_meses`` meses.

    Assinatura de baixo nivel (n_meses ja calculado) — usada diretamente
    por quem ja sabe o deslocamento. O orquestrador do projeto usa
    ``roll_clast_para_mes`` (registrada), que detecta o mes-base sozinha a
    partir do arquivo, igual aos outros roladores.
    """
    with open(in_path, encoding="latin-1", newline="") as f:
        content = f.read()

    eol = "\r\n" if "\r\n" in content else "\n"
    lines = content.split(eol)
    trailing_blank = lines and lines[-1] == ""
    if trailing_blank:
        lines = lines[:-1]

    start = _find_bloco_conjuntural_start(lines)
    if start is None:
        out_lines = list(lines)
    else:
        out_lines = lines[:start] + [_roll_line(l, n_meses) for l in lines[start:]]

    out_content = eol.join(out_lines) + (eol if trailing_blank else "")
    with open(out_path, "w", encoding="latin-1", newline="") as f:
        f.write(out_content)

    return {
        "arquivo": "clast.dat",
        "alterado": n_meses != 0 and start is not None,
        "n_meses": n_meses,
        "linhas_bloco_conjuntural": (len(lines) - start) if start is not None else 0,
    }


def _detect_old_start_idx(lines: list[str], start: int) -> int | None:
    idxs = []
    for raw in lines[start:]:
        mi = _parse_int(raw[_MI]) if len(raw) >= _MI.stop else None
        anoi = _parse_int(raw[_ANOI]) if len(raw) >= _ANOI.stop else None
        if mi is not None and anoi is not None:
            idxs.append(to_idx(mi, anoi))
    return min(idxs) if idxs else None


def roll_clast_para_mes(in_path: str, out_path: str, mes_alvo: int, ano_alvo: int) -> dict:
    """Adapta ``roll_clast`` a interface comum (mes/ano alvo), detectando
    o mes-base automaticamente a partir do proprio arquivo — igual ao
    modif.dat e ao expt.dat, para caber no mesmo orquestrador."""
    with open(in_path, encoding="latin-1", newline="") as f:
        content = f.read()
    eol = "\r\n" if "\r\n" in content else "\n"
    lines = content.split(eol)
    if lines and lines[-1] == "":
        lines = lines[:-1]

    start = _find_bloco_conjuntural_start(lines)
    old_start_idx = _detect_old_start_idx(lines, start) if start is not None else None
    new_start_idx = to_idx(mes_alvo, ano_alvo)

    n_meses = 0 if old_start_idx is None else (new_start_idx - old_start_idx)

    resumo = roll_clast(in_path, out_path, n_meses)
    resumo["mes_ano_antigo"] = from_idx(old_start_idx) if old_start_idx is not None else None
    resumo["mes_ano_novo"] = (mes_alvo, ano_alvo)
    return resumo
