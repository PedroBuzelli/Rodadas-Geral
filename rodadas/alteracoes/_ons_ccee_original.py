"""Conversao ONS -> CCEE (dger.dat e expt.dat).

PORTE de ONS-to-CCEE/ons_to_ccee.py (commit c249cb0). A logica das funcoes e' a
original. Unica mudanca funcional: o terminador de linha (CRLF/LF) do arquivo de
entrada e' preservado na saida (o original sempre gravava o expt.dat com LF).
"""

from __future__ import annotations

import re
from pathlib import Path

CRLF = "\r\n"
LF = "\n"


def _eol(caminho: Path) -> str:
    """Terminador de linha do arquivo de entrada (CRLF ou LF)."""
    conteudo = Path(caminho).read_bytes()
    return CRLF if b"\r\n" in conteudo else LF


def add_months(year: int, month: int, n: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + n
    return total // 12, total % 12 + 1


# ---------------------------------------------------------------------------
# EXPT.DAT
# ---------------------------------------------------------------------------

LINE_WIDTH = 50  # largura fixa observada nas linhas de dado do expt.dat


class ExptRecord:
    __slots__ = ("raw", "num", "tipo", "modif", "mi", "anoi", "mf", "anof", "nome_suffix")

    def __init__(self, raw: str):
        self.raw = raw
        self.num = int(raw[0:4])
        self.tipo = raw[5:10].strip()
        self.modif = float(raw[11:19])
        mi = raw[20:22].strip()
        anoi = raw[23:27].strip()
        mf = raw[28:30].strip()
        anof = raw[31:35].strip()
        self.mi = int(mi) if mi else None
        self.anoi = int(anoi) if anoi else None
        self.mf = int(mf) if mf else None
        self.anof = int(anof) if anof else None
        # so existe conteudo (NOME da usina) a partir da coluna 37 nas linhas de POTEF
        self.nome_suffix = raw[35:] if self.tipo == "POTEF" else ""


def read_expt(path: Path) -> tuple[list[str], list[ExptRecord]]:
    with open(path, "r", encoding="ascii", errors="strict") as f:
        lines = [l.rstrip("\n") for l in f]
    header = lines[:2]
    records = [ExptRecord(l) for l in lines[2:] if l.strip()]
    return header, records


def format_expt_line(num: int, tipo: str, modif: float, mi: int, anoi: int,
                      mf: int | None, anof: int | None) -> str:
    mf_str = f"{mf:2d}" if mf is not None else "  "
    anof_str = f"{anof:4d}" if anof is not None else "    "
    line = (
        f"{num:4d} {tipo:<5s} {modif:8.2f} {mi:2d} {anoi:4d} {mf_str} {anof_str}"
    )
    return line.ljust(LINE_WIDTH)


def load_gtmin_excel(path: Path) -> dict[tuple[int, int, int], float]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["GTmin_e_CCEE"]
    result: dict[tuple[int, int, int], float] = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        codigo, _nome, mes, gtmin_agente = row[0], row[1], row[2], row[3]
        if codigo is None or mes is None:
            continue
        result[(int(codigo), mes.year, mes.month)] = float(gtmin_agente)
    return result


def month_range(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    ey, em = end
    while (y, m) <= (ey, em):
        yield (y, m)
        y, m = add_months(y, m, 1)


def build_month_map(usina_records: list[ExptRecord], tipo: str, horizon_end: tuple[int, int]) -> dict[tuple[int, int], float]:
    """Expande os registros de um dado tipo (ex.: IPTER, POTEF, TEIFT) de uma
    usina num mapa mes -> valor. Registro aberto (sem MF/ANOF) se estende ate
    horizon_end."""
    result: dict[tuple[int, int], float] = {}
    for r in usina_records:
        if r.tipo != tipo:
            continue
        start = (r.anoi, r.mi)
        end = (r.anof, r.mf) if (r.anof is not None and r.mf is not None) else horizon_end
        for month in month_range(start, end):
            result[month] = r.modif
    return result


def transform_expt(input_path: Path, output_path: Path, excel_path: Path,
                    log_lines: list[str]) -> None:
    header, records = read_expt(input_path)

    # M = mes de estudo = menor (ano,mes) inicial presente no arquivo
    starts = [(r.anoi, r.mi) for r in records if r.anoi is not None and r.mi is not None]
    m_year, m_month = min(starts)
    m1_year, m1_month = add_months(m_year, m_month, 1)
    m2_year, m2_month = add_months(m_year, m_month, 2)
    protected_months = {(m_year, m_month), (m1_year, m1_month)}

    # horizonte global do deck = maior (ano,mes) final explicito no arquivo inteiro
    ends = [(r.anof, r.mf) for r in records if r.anof is not None and r.mf is not None]
    horizon_end = max(ends)

    excel_map = load_gtmin_excel(excel_path)
    excel_codes = {k[0] for k in excel_map}

    log_lines.append(f"[EXPT] Mes de estudo (M) identificado: {m_month:02d}/{m_year}")
    log_lines.append(f"[EXPT] Horizonte global do deck (fim): {horizon_end[1]:02d}/{horizon_end[0]}")

    # Preserva ordem de aparicao das usinas
    usina_order: list[int] = []
    seen_usinas = set()
    for r in records:
        if r.num not in seen_usinas:
            seen_usinas.add(r.num)
            usina_order.append(r.num)

    # Indice da primeira ocorrencia de GTMIN por usina (posicao de insercao na saida)
    first_gtmin_pos: dict[int, int] = {}
    for idx, r in enumerate(records):
        if r.tipo == "GTMIN" and r.num not in first_gtmin_pos:
            first_gtmin_pos[r.num] = idx

    records_by_usina: dict[int, list[ExptRecord]] = {}
    for r in records:
        records_by_usina.setdefault(r.num, []).append(r)

    altered_usinas: list[int] = []
    fallback_usinas: set[int] = set()
    ipter_adjusted_count = 0
    ipter_adjusted_usinas: set[int] = set()
    total_original_gtmin = sum(1 for r in records if r.tipo == "GTMIN")
    total_generated_gtmin = 0

    # saida: mapa posicao -> lista de linhas a inserir (para nao-GTMIN, 1 linha == propria linha original)
    output_lines: list[str | None] = [None] * len(records)

    for idx, r in enumerate(records):
        if r.tipo != "GTMIN":
            output_lines[idx] = r.raw

    for num in usina_order:
        all_usina_records = records_by_usina[num]
        usina_records = [r for r in all_usina_records if r.tipo == "GTMIN"]
        if not usina_records:
            continue

        # Constroi mapa mes -> valor original (permite gaps entre meses)
        orig_month_value: dict[tuple[int, int], float] = {}
        last_record_is_open: dict[tuple[int, int], bool] = {}
        for r in usina_records:
            start = (r.anoi, r.mi)
            if r.anof is not None and r.mf is not None:
                end = (r.anof, r.mf)
                is_open = False
            else:
                end = horizon_end
                is_open = True
            for month in month_range(start, end):
                orig_month_value[month] = r.modif
                last_record_is_open[month] = is_open

        if not orig_month_value:
            continue

        covered_months = sorted(orig_month_value)
        last_month = covered_months[-1]
        usina_open_ended = last_record_is_open[last_month]

        # Mapas de apoio para a regra GTMIN x IPTER (regra_gtmin_ipter.md)
        ipter_map = build_month_map(all_usina_records, "IPTER", horizon_end)
        potef_map = build_month_map(all_usina_records, "POTEF", horizon_end)

        final_month_value: dict[tuple[int, int], float] = {}
        usina_changed = False
        for month in covered_months:
            if month in protected_months or month < (m2_year, m2_month):
                # Regra 1 do EXPT (absoluta): M e M+1 nunca sao tocados, nem
                # pela substituicao do Excel nem pela regra de IPTER abaixo.
                final_month_value[month] = orig_month_value[month]
                continue
            key = (num, month[0], month[1])
            if key in excel_map:
                value = excel_map[key]
                if abs(value - orig_month_value[month]) > 0.01:
                    usina_changed = True
            else:
                value = orig_month_value[month]
                fallback_usinas.add(num)
                reason = "usina ausente no Excel" if num not in excel_codes else "mes fora do range do Excel"
                log_lines.append(
                    f"[EXPT][fallback] usina {num}, mes {month[1]:02d}/{month[0]}: "
                    f"{reason}; mantido valor original ({orig_month_value[month]:.2f})"
                )

            # Regra GTMIN x IPTER: so se aplica a partir de M+2 (mesmo trecho
            # onde o GTMIN ja e "calculado" pelo algoritmo via Excel/fallback,
            # nunca sobre M/M+1, que ficam protegidos acima).
            ipter = ipter_map.get(month, 0.0)
            if ipter > 0:
                potef = potef_map.get(month)
                if potef is None:
                    log_lines.append(
                        f"[EXPT][ipter][aviso] usina {num}, mes {month[1]:02d}/{month[0]}: "
                        f"IPTER={ipter:.2f}% mas sem POTEF conhecido nesse mes; ajuste nao aplicado"
                    )
                else:
                    cap = potef * (1 - ipter / 100.0)
                    if value < cap - 0.01:
                        # Caso especial da regra: GTMIN_base ja menor que
                        # POTEF*(1-IPTER/100) -> nao ajustar.
                        pass
                    else:
                        adjusted = value * (1 - ipter / 100.0)
                        if abs(adjusted - value) > 0.01:
                            log_lines.append(
                                f"[EXPT][ipter] usina {num}, mes {month[1]:02d}/{month[0]}: "
                                f"GTMIN {value:.2f} -> {adjusted:.2f} (IPTER={ipter:.2f}%)"
                            )
                            ipter_adjusted_count += 1
                            ipter_adjusted_usinas.add(num)
                            usina_changed = True
                        value = adjusted

            final_month_value[month] = value

        if usina_changed:
            altered_usinas.append(num)

        # Regra 4: agrupa meses consecutivos (sem gaps) com o mesmo valor (tol 0.01)
        groups: list[list[tuple[int, int]]] = []
        for month in covered_months:
            value = final_month_value[month]
            if groups:
                prev_month = groups[-1][-1]
                expected_next = add_months(prev_month[0], prev_month[1], 1)
                same_value = abs(final_month_value[prev_month] - value) <= 0.01
                if expected_next == month and same_value:
                    groups[-1].append(month)
                    continue
            groups.append([month])

        new_lines = []
        for group in groups:
            start_month = group[0]
            end_month = group[-1]
            value = final_month_value[start_month]
            is_last_group = end_month == last_month
            if is_last_group and usina_open_ended:
                mf, anof = None, None
            else:
                mf, anof = end_month[1], end_month[0]
            new_lines.append(
                format_expt_line(num, "GTMIN", value, start_month[1], start_month[0], mf, anof)
            )

        total_generated_gtmin += len(new_lines)
        pos = first_gtmin_pos[num]
        output_lines[pos] = "\n".join(new_lines)

    final_lines = [l for l in output_lines if l is not None]

    log_lines.append(f"[EXPT] Usinas com GTMIN efetivamente alterado: {len(altered_usinas)} -> {altered_usinas}")
    log_lines.append(f"[EXPT] Usinas com fallback (casos de borda): {len(fallback_usinas)} -> {sorted(fallback_usinas)}")
    log_lines.append(
        f"[EXPT] Meses ajustados pela regra GTMIN x IPTER: {ipter_adjusted_count} "
        f"(em {len(ipter_adjusted_usinas)} usinas -> {sorted(ipter_adjusted_usinas)})"
    )
    log_lines.append(f"[EXPT] Registros GTMIN originais: {total_original_gtmin} | gerados: {total_generated_gtmin}")

    with open(output_path, "w", encoding="ascii", newline=_eol(input_path)) as f:
        f.write(header[0] + "\n")
        f.write(header[1] + "\n")
        for l in final_lines:
            f.write(l + "\n")


# ---------------------------------------------------------------------------
# DGER.DAT
# ---------------------------------------------------------------------------

DGER_LABEL_GER_PLS = "GER.PLs E NV1 E NV2"
DGER_LABEL_TRATA = "TRATA ARQS CORTES"

VALUE_FIELD_START = 24  # coluna (0-indexed) onde comeca o primeiro campo de 5 caracteres
VALUE_FIELD_WIDTH = 5




def _force_first_n_values_to_zero(line: str, n: int) -> str:
    line = line.rstrip("\n")
    chars = list(line)
    for i in range(n):
        start = VALUE_FIELD_START + i * VALUE_FIELD_WIDTH
        end = start + VALUE_FIELD_WIDTH
        field = line[start:end]
        m = re.match(r"(\s*)-?\d+(\s*)", field)
        if not m:
            continue
        lead, trail = m.group(1), m.group(2)
        new_field = (lead + "0" + trail)
        # mantem largura total do campo
        new_field = new_field.ljust(VALUE_FIELD_WIDTH)[:VALUE_FIELD_WIDTH]
        chars[start:end] = list(new_field)
    return "".join(chars)


def _detect_encoding(path: Path) -> str:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "iso-8859-1"


def transform_dger(input_path: Path, output_path: Path, log_lines: list[str]) -> None:
    encoding = _detect_encoding(input_path)
    with open(input_path, "r", encoding=encoding) as f:
        lines = f.readlines()

    # Regra 2 - titulo (linha 1): PMO -> PLD
    line0 = lines[0].rstrip("\n")
    if line0.startswith("PMO"):
        new_line0 = "PLD" + line0[3:]
        log_lines.append(f"[DGER] Linha 1 (titulo): 'PMO...' -> 'PLD...'")
        lines[0] = new_line0 + "\n"
    else:
        log_lines.append(f"[DGER][aviso] Linha 1 nao comeca com 'PMO' (valor: {line0[:20]!r}); mantida sem alteracao")

    found_ger_pls = False
    found_trata = False
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped.startswith(DGER_LABEL_GER_PLS):
            before = stripped
            lines[i] = _force_first_n_values_to_zero(stripped, 3) + "\n"
            log_lines.append(f"[DGER] Linha '{DGER_LABEL_GER_PLS}': antes/depois:\n  {before!r}\n  {lines[i].rstrip(chr(10))!r}")
            found_ger_pls = True
        elif stripped.startswith(DGER_LABEL_TRATA):
            before = stripped
            lines[i] = _force_first_n_values_to_zero(stripped, 1) + "\n"
            log_lines.append(f"[DGER] Linha '{DGER_LABEL_TRATA}': antes/depois:\n  {before!r}\n  {lines[i].rstrip(chr(10))!r}")
            found_trata = True

    if not found_ger_pls:
        log_lines.append(f"[DGER][ERRO] Linha '{DGER_LABEL_GER_PLS}' nao encontrada no arquivo de entrada.")
    if not found_trata:
        log_lines.append(f"[DGER][ERRO] Linha '{DGER_LABEL_TRATA}' nao encontrada no arquivo de entrada.")

    with open(output_path, "w", encoding=encoding, newline=_eol(input_path)) as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------
