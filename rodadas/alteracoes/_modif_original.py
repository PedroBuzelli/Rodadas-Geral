# PORTE de prepara-deck/roll_deck/modifiers/modif_roller.py (commit 0f5e161).
# A logica das funcoes abaixo e' a original; so mudaram imports e o registro.
# As regras da secao 'wrapper' no fim do arquivo sao novas.

"""Rolagem de horizonte do arquivo MODIF.DAT (NEWAVE).

Implementa as regras descritas em
``instruções arquivos/regras_rolagem_modif_generico.md``. Ler aquele
documento antes de mexer neste modulo — ele descreve o *porque* de cada
passo abaixo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.datas import from_idx, to_idx

N_HEADER_LINES = 2

# Um "token" e qualquer sequencia de caracteres nao-espaco. Usamos spans de
# token (inicio/fim) para poder editar so o mes/ano de uma linha sem tocar
# em mais nada — nunca fazemos split+join da linha inteira.
_TOKEN_RE = re.compile(r"\S+")

# Palavras-chave cuja serie e' apenas transladada pela rolagem: cada
# registro desloca pela mesma distancia (novo inicio - antigo inicio),
# mantendo o proprio valor, sem remover, sem criar e sem depender do
# valor do registro.
_TRANSLADA = {"VMINT"}

# Palavras-chave que a rolagem nao toca (linhas copiadas como estao, e suas
# datas nao entram na deteccao do mes-base).
_IGNORADAS = {"TURBMAXT"}

# Duracao do horizonte de estudo: 5 anos civis, sempre terminando em
# dezembro do (ano-alvo + 4) — independente do mes de inicio. Ex.: uma
# rolagem para qualquer mes de 2027 tem horizonte ate dezembro de 2031.
_ANOS_DE_ESTUDO = 5


@dataclass
class _Token:
    text: str
    start: int
    end: int


@dataclass
class _Line:
    raw: str
    index: int  # posicao original no arquivo (0-based, apos o cabecalho)
    is_usina_header: bool = False
    keyword: str | None = None
    tokens: list[_Token] = field(default_factory=list)
    is_dated: bool = False
    mes: int | None = None
    ano: int | None = None
    idx: int | None = None
    mes_tok: _Token | None = None
    ano_tok: _Token | None = None
    value_text: str | None = None


def _tokenize(raw: str) -> list[_Token]:
    return [_Token(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(raw)]


def _classify(raw: str, index: int) -> _Line:
    tokens = _tokenize(raw)
    line = _Line(raw=raw, index=index, tokens=tokens)
    if not tokens:
        return line

    line.keyword = tokens[0].text
    if line.keyword == "USINA":
        line.is_usina_header = True
        return line

    if line.keyword in _IGNORADAS:
        return line

    if len(tokens) < 3:
        return line  # registro estatico (nao tem nem mes nem ano)

    mes_tok, ano_tok, val_tok = tokens[1], tokens[2], tokens[3] if len(tokens) > 3 else None

    if not re.fullmatch(r"\d{1,2}", mes_tok.text):
        return line
    mes = int(mes_tok.text)
    if not (1 <= mes <= 12):
        return line
    if not re.fullmatch(r"\d{4}", ano_tok.text):
        return line
    ano = int(ano_tok.text)

    line.is_dated = True
    line.mes = mes
    line.ano = ano
    line.idx = to_idx(mes, ano)
    line.mes_tok = mes_tok
    line.ano_tok = ano_tok
    line.value_text = val_tok.text if val_tok is not None else None
    return line


def _replace_date(raw: str, mes_tok: _Token, ano_tok: _Token, novo_mes: int, novo_ano: int) -> str:
    """Substitui so os spans de mes/ano da linha, preservando tudo o mais."""
    novo_mes_txt = str(novo_mes)
    novo_ano_txt = str(novo_ano)
    return (
        raw[: mes_tok.start]
        + novo_mes_txt
        + raw[mes_tok.end : ano_tok.start]
        + novo_ano_txt
        + raw[ano_tok.end :]
    )


def _roll_series(
    keyword: str,
    records: list[_Line],
    old_start_idx: int,
    new_start_idx: int,
    horizon_end_idx: int,
    avisos: list[str],
    usina_label: str,
) -> list[_Line]:
    """Aplica a regra central a uma serie (um keyword, dentro de uma usina)."""

    idxs_vistos: set[int] = set()
    for r in records:
        if r.idx in idxs_vistos:
            avisos.append(
                f"{usina_label}: datas duplicadas em '{keyword}' (idx={r.idx}) "
                "— serie preservada sem alteracao para revisao manual."
            )
            return list(records)
        idxs_vistos.add(r.idx)

    distancia = new_start_idx - old_start_idx

    if keyword in _TRANSLADA:
        # Translacao pura: cada registro desloca pela mesma distancia da
        # rolagem, mantendo a ordem e o proprio valor de cada um. Um
        # registro que estourar o fim do horizonte de estudo (5 anos
        # civis a partir do ano-alvo) e' normal — o deck de origem pode
        # ter "um ciclo a mais" de sobra — e' simplesmente descartado
        # (nao propagado), nunca escrito alem do horizonte.
        deslocados: list[_Line] = []
        for r in records:
            novo_idx = r.idx + distancia
            if novo_idx > horizon_end_idx:
                avisos.append(
                    f"{usina_label}: '{keyword}' deslocaria para "
                    f"{'/'.join(map(str, from_idx(novo_idx)))}, alem do fim do "
                    f"horizonte de estudo — registro descartado."
                )
                continue
            novo_mes, novo_ano = from_idx(novo_idx)
            deslocados.append(
                _Line(
                    raw=_replace_date(r.raw, r.mes_tok, r.ano_tok, novo_mes, novo_ano),
                    index=r.index,
                    keyword=keyword,
                    is_dated=True,
                    mes=novo_mes,
                    ano=novo_ano,
                    idx=novo_idx,
                )
            )
        return deslocados

    removed = [r for r in records if r.idx < new_start_idx]
    kept = [r for r in records if r.idx >= new_start_idx]

    # Regra geral (passos 1 e 3).
    if kept and kept[0].idx == new_start_idx:
        return kept

    if not removed:
        return kept

    prev = max(removed, key=lambda r: r.idx)
    novo_mes, novo_ano = from_idx(new_start_idx)
    carregado = _Line(
        raw=_replace_date(prev.raw, prev.mes_tok, prev.ano_tok, novo_mes, novo_ano),
        index=kept[0].index if kept else prev.index,
        keyword=keyword,
        is_dated=True,
        mes=novo_mes,
        ano=novo_ano,
        idx=new_start_idx,
    )
    return [carregado] + kept


def _roll_block(
    lines: list[_Line],
    old_start_idx: int,
    new_start_idx: int,
    horizon_end_idx: int,
    avisos: list[str],
    usina_label: str,
) -> list[str]:
    series: dict[str, list[_Line]] = {}
    for ln in lines:
        if ln.is_dated:
            series.setdefault(ln.keyword, []).append(ln)

    transformed: dict[str, list[_Line]] = {
        kw: _roll_series(kw, recs, old_start_idx, new_start_idx, horizon_end_idx, avisos, usina_label)
        for kw, recs in series.items()
    }

    out: list[str] = []
    emitted: set[str] = set()
    for ln in lines:
        if not ln.is_dated:
            out.append(ln.raw)
            continue
        kw = ln.keyword
        if kw in emitted:
            continue
        emitted.add(kw)
        out.extend(r.raw for r in transformed[kw])
    return out


def _detect_old_start_idx(lines: list[_Line]) -> int | None:
    dated = [ln.idx for ln in lines if ln.is_dated]
    return min(dated) if dated else None


def roll_modif(in_path: str, out_path: str, mes_alvo: int, ano_alvo: int) -> dict:
    with open(in_path, encoding="latin-1", newline="") as f:
        content = f.read()

    eol = "\r\n" if "\r\n" in content else "\n"
    raw_lines = content.split(eol)
    trailing_blank = raw_lines and raw_lines[-1] == ""
    if trailing_blank:
        raw_lines = raw_lines[:-1]

    header = raw_lines[:N_HEADER_LINES]
    body_raw = raw_lines[N_HEADER_LINES:]

    classified = [_classify(raw, i) for i, raw in enumerate(body_raw)]

    old_start_idx = _detect_old_start_idx(classified)
    new_start_idx = to_idx(mes_alvo, ano_alvo)
    horizon_end_idx = to_idx(12, ano_alvo + _ANOS_DE_ESTUDO - 1)

    avisos: list[str] = []

    if old_start_idx is None or old_start_idx == new_start_idx:
        out_lines = header + body_raw
        resumo = {
            "arquivo": "modif.dat",
            "alterado": False,
            "avisos": avisos,
        }
    else:
        out_body: list[str] = []
        block: list[_Line] = []
        usina_label = "(sem usina)"

        def flush():
            if block:
                out_body.extend(
                    _roll_block(block, old_start_idx, new_start_idx, horizon_end_idx, avisos, usina_label)
                )

        for ln in classified:
            if ln.is_usina_header:
                flush()
                block = [ln]
                usina_label = ln.raw.strip()
            else:
                block.append(ln)
        flush()

        out_lines = header + out_body
        resumo = {
            "arquivo": "modif.dat",
            "alterado": True,
            "mes_ano_antigo": from_idx(old_start_idx),
            "mes_ano_novo": (mes_alvo, ano_alvo),
            "avisos": avisos,
        }

    out_content = eol.join(out_lines) + (eol if trailing_blank else "")
    with open(out_path, "w", encoding="latin-1", newline="") as f:
        f.write(out_content)

    return resumo
