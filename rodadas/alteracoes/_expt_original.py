# PORTE de prepara-deck/roll_deck/modifiers/expt_roller.py (commit 0f5e161).
# A logica das funcoes abaixo e' a original; so mudaram imports e o registro.
# As regras da secao 'wrapper' no fim do arquivo sao novas.

"""Rolagem de horizonte do arquivo EXPT.DAT (NEWAVE/DECOMP).

Implementa as regras descritas em
``instruções arquivos/instrucoes_algoritmo_expt.md``.

Limitacao conhecida (documentada na especificacao): esta rolagem resolve
apenas a parte mecanica (corte de datas passadas + prorrogacao do inicio).
Cerca de 84% das usinas batem 100% com um EXPT real do mesmo avanco de mes;
o resto exige redespacho manual (linhas marcadas com a tag ``AJUSTE`` no
arquivo real), que muda valores de MODIF/GTMIN/FCMAX — isso esta fora do
escopo deste algoritmo.
"""

from __future__ import annotations

from ..core.datas import to_idx

N_HEADER_LINES = 2

_MI = slice(20, 22)
_ANOI = slice(23, 27)
_MF = slice(28, 30)
_ANOF = slice(31, 35)


def _parse_int(field: str) -> int | None:
    field = field.strip()
    return int(field) if field else None


def _detect_old_start_idx(data_lines: list[str]) -> int | None:
    idxs = []
    for raw in data_lines:
        if len(raw) < _ANOI.stop:
            continue
        mi = _parse_int(raw[_MI])
        anoi = _parse_int(raw[_ANOI])
        if mi is not None and anoi is not None:
            idxs.append(to_idx(mi, anoi))
    return min(idxs) if idxs else None


def roll_expt(in_path: str, out_path: str, mes_alvo: int, ano_alvo: int) -> dict:
    with open(in_path, encoding="latin-1", newline="") as f:
        content = f.read()

    eol = "\r\n" if "\r\n" in content else "\n"
    raw_lines = content.split(eol)
    trailing_blank = raw_lines and raw_lines[-1] == ""
    if trailing_blank:
        raw_lines = raw_lines[:-1]

    header = raw_lines[:N_HEADER_LINES]
    data_lines = raw_lines[N_HEADER_LINES:]

    mes_base_ano_base_idx = _detect_old_start_idx(data_lines)
    new_start_idx = to_idx(mes_alvo, ano_alvo)

    removidas = 0
    deslocadas = 0
    mantidas = 0
    out_data: list[str] = []

    if mes_base_ano_base_idx is None or new_start_idx <= mes_base_ano_base_idx:
        out_data = list(data_lines)
        mantidas = len(data_lines)
    else:
        skip_start = mes_base_ano_base_idx
        skip_end = new_start_idx - 1

        for raw in data_lines:
            if len(raw) < _ANOI.stop:
                out_data.append(raw)
                mantidas += 1
                continue

            mi = _parse_int(raw[_MI])
            anoi = _parse_int(raw[_ANOI])
            if mi is None or anoi is None:
                out_data.append(raw)
                mantidas += 1
                continue

            idx_ini = to_idx(mi, anoi)
            if not (skip_start <= idx_ini <= skip_end):
                out_data.append(raw)
                mantidas += 1
                continue

            mf = _parse_int(raw[_MF]) if len(raw) >= _MF.stop else None
            anof = _parse_int(raw[_ANOF]) if len(raw) >= _ANOF.stop else None
            idx_fim = to_idx(mf, anof) if (mf is not None and anof is not None) else None

            if idx_fim is not None and idx_fim <= skip_end:
                removidas += 1
                continue

            novo_mi = f"{mes_alvo:>2}"
            novo_anoi = f"{ano_alvo:>4}"
            nova_linha = raw[: _MI.start] + novo_mi + raw[_MI.stop : _ANOI.start] + novo_anoi + raw[_ANOI.stop :]
            out_data.append(nova_linha)
            deslocadas += 1

    out_lines = header + out_data
    out_content = eol.join(out_lines) + (eol if trailing_blank else "")
    with open(out_path, "w", encoding="latin-1", newline="") as f:
        f.write(out_content)

    return {
        "arquivo": "expt.dat",
        "alterado": removidas > 0 or deslocadas > 0,
        "linhas_removidas": removidas,
        "linhas_deslocadas": deslocadas,
        "linhas_mantidas": mantidas,
        "aviso": (
            "Rolagem puramente mecanica de datas. Usinas com redespacho "
            "manual (tag AJUSTE no deck real) nao sao replicadas por este "
            "algoritmo e exigem revisao manual."
        ),
    }
