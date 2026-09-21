"""CVU do CLAST.DAT (estrutural e conjuntural).

PORTE de att-cvu/atualiza_cvu_clast.py (commit 95cff80). A logica de leitura dos
CSVs e de alteracao das linhas e' a original. Mudancas: sys.exit -> ErroAlteracao,
print -> logging, sem abrir janelas/arquivos, pandas/matplotlib carregados so
quando usados, sem modo interativo (input) nem CLI proprio.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .registro import ErroAlteracao

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BLOCO ESTRUTURAL — layout fixo
#  XXXX XXXXXXXXXXXX XXXXXXXXXX XXXX.XX XXXX.XX XXXX.XX XXXX.XX XXXX.XX
# ---------------------------------------------------------------------------
EST_NUM_START    = 1
EST_NUM_END      = 5
EST_NOME_SLICE   = (6, 18)
EST_CUSTO_SLICES = [(30, 37), (38, 45), (46, 53), (54, 61), (62, 69)]
EST_CUSTO_FMT    = "%7.2f"
EST_HEADER_ROWS  = 2
EST_CODIGOS_PRESERVAR = {1, 13}   # Angra 1 e Angra 2 — CVU preservado sem alteração
FIM_BLOCO_1      = "9999"         # linha sentinela que encerra o bloco estrutural

# ---------------------------------------------------------------------------
# BLOCO CONJUNTURAL — layout fixo
#  XXXX   XXXX.XX  XX XXXX  XX XXXX
# ---------------------------------------------------------------------------
CONJ_COD_SLICE     = (0, 5)
CONJ_CUSTO_SLICE   = (5, 15)
CONJ_MES_INI_SLICE = (15, 19)
CONJ_ANO_INI_SLICE = (19, 24)
CONJ_MES_FIM_SLICE = (24, 28)
CONJ_ANO_FIM_SLICE = (28, 33)
CONJ_MIN_LEN       = 33


# ===========================================================================
# BLOCO ESTRUTURAL — carga do CSV e processamento das linhas
# ===========================================================================

def carregar_csv_estrutural(caminho: str, sep: str, encoding: str) -> tuple[dict[int, list[float]], list[int]]:
    """
    Lê o CSV estrutural, filtra pelo MES_REFERENCIA mais recente e retorna:
        ({CODIGO_MODELO_PRECO: [cvu_ano1..cvu_ano5]}, [ano1..ano5])
    Quando há múltiplas parcelas para o mesmo código e ano, usa o menor CVU.
    """
    import pandas as pd
    colunas_req = {"CODIGO_MODELO_PRECO", "ANO_HORIZONTE", "CVU_ESTRUTURAL", "MES_REFERENCIA"}
    try:
        df = pd.read_csv(caminho, sep=sep, encoding=encoding)
    except FileNotFoundError:
        raise ErroAlteracao(f"[ERRO] CSV estrutural não encontrado: {caminho}")
    except Exception as e:
        raise ErroAlteracao(f"[ERRO] Falha ao ler CSV estrutural: {e}")

    ausentes = colunas_req - set(df.columns)
    if ausentes:
        raise ErroAlteracao(f"[ERRO] Colunas ausentes no CSV estrutural: {ausentes}")

    mes_mais_recente = df["MES_REFERENCIA"].max()
    df = df[df["MES_REFERENCIA"] == mes_mais_recente].copy()
    log.info(f"[estrutural] MES_REFERENCIA utilizado : {mes_mais_recente}")

    df["CODIGO_MODELO_PRECO"] = df["CODIGO_MODELO_PRECO"].astype(int)

    df = (
        df.groupby(["CODIGO_MODELO_PRECO", "ANO_HORIZONTE"], as_index=False)["CVU_ESTRUTURAL"]
        .min()
        .sort_values(["CODIGO_MODELO_PRECO", "ANO_HORIZONTE"])
    )

    anos_ordenados = sorted(df["ANO_HORIZONTE"].unique().tolist())

    cvu_map: dict[int, list[float]] = {}
    for codigo, grupo in df.groupby("CODIGO_MODELO_PRECO"):
        valores = grupo["CVU_ESTRUTURAL"].tolist()
        if len(valores) != 5:
            log.info(f"[estrutural][AVISO] Código {codigo}: {len(valores)} ano(s) após agregação (esperado 5). Ignorado.")
            continue
        cvu_map[int(codigo)] = [float(v) for v in valores]

    return cvu_map, anos_ordenados


def _est_extrair_num(linha: str) -> int | None:
    if len(linha) < EST_NUM_END:
        return None
    try:
        return int(linha[EST_NUM_START:EST_NUM_END])
    except ValueError:
        return None


def _est_extrair_nome(linha: str) -> str:
    ini, fim = EST_NOME_SLICE
    return linha[ini:fim].strip() if len(linha) >= fim else linha[ini:].strip()


def _est_extrair_custos(linha: str) -> list[float]:
    custos = []
    for ini, fim in EST_CUSTO_SLICES:
        trecho = linha[ini:fim].strip() if len(linha) >= fim else ""
        try:
            custos.append(float(trecho))
        except ValueError:
            custos.append(0.0)
    return custos


def _est_substituir_custos(linha: str, custos: list[float]) -> str:
    chars = list(linha)
    for i, (ini, fim) in enumerate(EST_CUSTO_SLICES):
        if fim > len(chars):
            chars.extend([" "] * (fim - len(chars)))
        formatado = EST_CUSTO_FMT % custos[i]
        if len(formatado) != 7:
            raise ValueError(f"CVU '{formatado}' excede 7 chars. Valor: {custos[i]:.2f}")
        chars[ini:fim] = list(formatado)
    return "".join(chars)


def processar_bloco_estrutural(linhas: list[str], cvu_map: dict[int, list[float]]):
    """
    Processa as linhas do bloco estrutural (cabeçalho + usinas + sentinela).
    Retorna (novas_linhas, dados_diferenca, atualizadas, sem_match).
    """
    saida: list[str] = []
    dados_diferenca: list[tuple[str, list[float], list[float]]] = []
    atualizadas: list[int] = []
    sem_match: list[int] = []
    header_count = 0

    for linha in linhas:
        if header_count < EST_HEADER_ROWS:
            saida.append(linha)
            header_count += 1
            continue

        if linha.strip() == FIM_BLOCO_1:
            saida.append(linha)
            continue

        num = _est_extrair_num(linha)
        if num is None:
            saida.append(linha)
            continue

        if num in cvu_map:
            dados_diferenca.append((_est_extrair_nome(linha), _est_extrair_custos(linha), cvu_map[num]))
            saida.append(_est_substituir_custos(linha, cvu_map[num]))
            atualizadas.append(num)
        elif num in EST_CODIGOS_PRESERVAR:
            saida.append(linha)
        else:
            saida.append(_est_substituir_custos(linha, [0.0, 0.0, 0.0, 0.0, 0.0]))
            sem_match.append(num)

    return saida, dados_diferenca, atualizadas, sem_match

def gerar_graficos_estrutural(dados, anos: list[int], diretorio: Path) -> None:
    if not dados:
        log.info("[estrutural][AVISO] Nenhuma usina atualizada — gráficos não gerados.")
        return

    diretorio.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    largura = max(10, len(dados) * 0.22)

    for i, ano in enumerate(anos):
        dados_ordenados = sorted(dados, key=lambda d: d[2][i])
        nomes = [nome for nome, _, _ in dados_ordenados]
        valores_antigos = [antigos[i] for _, antigos, _ in dados_ordenados]
        valores_novos = [novos[i] for _, _, novos in dados_ordenados]

        fig, ax = plt.subplots(figsize=(largura, 6))
        ax.plot(nomes, valores_antigos, linewidth=1, marker="", label="CVU antigo")
        ax.plot(nomes, valores_novos, linewidth=1, marker="", label="CVU novo")
        ax.set_xlabel("Usina")
        ax.set_ylabel("CVU")
        ax.set_title(f"CVU estrutural — Ano {ano}")
        ax.tick_params(axis="x", rotation=90)
        ax.legend()
        fig.tight_layout()

        caminho_png = diretorio / f"diferenca_cvu_estrutural_{ano}.png"
        fig.savefig(caminho_png, dpi=150)
        plt.close(fig)
        log.info(f"[estrutural] Gráfico gerado : {caminho_png}")


# ===========================================================================
# BLOCO CONJUNTURAL — carga dos CSVs e processamento das linhas

def _conj_build_cvu_map(df: pd.DataFrame, col_cod: str, col_cvu: str) -> tuple[dict[int, float], int]:
    mes_max = df["MES_REFERENCIA"].max()
    df_mes = df[df["MES_REFERENCIA"] == mes_max]
    cvu_map: dict[int, float] = {}
    for _, row in df_mes.iterrows():
        try:
            cod = int(row[col_cod])
            cvu = float(row[col_cvu])
        except (ValueError, TypeError):
            continue
        if cod not in cvu_map:
            cvu_map[cod] = cvu
    return cvu_map, mes_max


def carregar_csvs_conjuntural(caminho_conj: str, caminho_merch: str):
    """
    Lê os CSVs conjuntural e merchant e retorna:
        (cvu_map {cod: cvu}, mes_ref_map {cod: MES_REFERENCIA de origem})
    Merchant tem prioridade sobre conjuntural quando o código aparece nos dois.
    """
    import pandas as pd
    try:
        df_conj = pd.read_csv(caminho_conj, encoding="latin-1")
    except FileNotFoundError:
        raise ErroAlteracao(f"[ERRO] CSV conjuntural não encontrado: {caminho_conj}")
    try:
        df_merch = pd.read_csv(caminho_merch)
    except FileNotFoundError:
        raise ErroAlteracao(f"[ERRO] CSV merchant não encontrado: {caminho_merch}")

    col_cod_conj = next(c for c in df_conj.columns if "CODIGO" in c)

    map_conj, mes_conj = _conj_build_cvu_map(df_conj, col_cod_conj, "CVU_CONJUNTURAL")
    map_merch, mes_merch = _conj_build_cvu_map(df_merch, "CODIGO_MODELO_PRECO", "CVU_CF")

    cvu_map = {**map_conj, **map_merch}
    mes_ref_map = {cod: mes_conj for cod in map_conj}
    mes_ref_map.update({cod: mes_merch for cod in map_merch})

    log.info(f"[conjuntural] Conjuntural : {len(map_conj)} códigos (mês ref {mes_conj})")
    log.info(f"[conjuntural] Merchant    : {len(map_merch)} códigos (mês ref {mes_merch})")
    log.info(f"[conjuntural] Total       : {len(cvu_map)} códigos únicos")

    return cvu_map, mes_ref_map


def _conj_parse_ano_mes(mes_referencia) -> tuple[int, int]:
    v = int(mes_referencia)
    return v % 100, v // 100  # (mes, ano)


def _conj_next_month(mes: int, ano: int) -> tuple[int, int]:
    mes += 1
    if mes > 12:
        mes = 1
        ano += 1
    return mes, ano


def _conj_parse_int_field(s: str):
    s = s.strip()
    return int(s) if s else None


def _conj_format_custo(v: float) -> str:
    return f"{v:>10.2f}"


def processar_bloco_conjuntural(linhas: list[str], cvu_map: dict[int, float], mes_ref_map: dict[int, int]):
    """
    Processa as linhas do bloco conjuntural (cabeçalho + usinas).
    Retorna (novas_linhas, changed, cvu_comparacao).
    """
    parsed = []
    for linha in linhas:
        s = linha.rstrip("\n\r")
        nl = linha[len(s):]
        entry = {"s": s, "nl": nl, "cod": None}
        if len(s) >= CONJ_MIN_LEN:
            try:
                cod = int(s[CONJ_COD_SLICE[0]:CONJ_COD_SLICE[1]])
                if cod in cvu_map:
                    entry["cod"] = cod
                    entry["mes_ini"] = _conj_parse_int_field(s[CONJ_MES_INI_SLICE[0]:CONJ_MES_INI_SLICE[1]])
                    entry["ano_ini"] = _conj_parse_int_field(s[CONJ_ANO_INI_SLICE[0]:CONJ_ANO_INI_SLICE[1]])
                    entry["mes_fim"] = _conj_parse_int_field(s[CONJ_MES_FIM_SLICE[0]:CONJ_MES_FIM_SLICE[1]])
                    entry["ano_fim"] = _conj_parse_int_field(s[CONJ_ANO_FIM_SLICE[0]:CONJ_ANO_FIM_SLICE[1]])
            except (ValueError, IndexError):
                pass
        parsed.append(entry)

    cod_indices: dict[int, list[int]] = {}
    for i, entry in enumerate(parsed):
        if entry["cod"] is not None:
            cod_indices.setdefault(entry["cod"], []).append(i)

    changed = 0
    cvu_comparacao: list[tuple[int, float, float]] = []

    for cod, indices in cod_indices.items():
        new_custo = cvu_map[cod]
        mes_ref, ano_ref = _conj_parse_ano_mes(mes_ref_map[cod])
        target_mes, target_ano = _conj_next_month(mes_ref, ano_ref)

        next_month_idx = None
        for i in indices:
            e = parsed[i]
            if e["mes_ini"] == target_mes and e["ano_ini"] == target_ano:
                next_month_idx = i
                break

        if next_month_idx is not None:
            e = parsed[next_month_idx]
            s = e["s"]
            old_custo = float(s[CONJ_CUSTO_SLICE[0]:CONJ_CUSTO_SLICE[1]])
            cvu_comparacao.append((cod, old_custo, new_custo))
            if abs(old_custo - new_custo) > 0.001:
                e["s"] = s[:5] + _conj_format_custo(new_custo) + s[15:]
                changed += 1
                log.info(
                    f"[conjuntural] COD {cod:5d} -> CVU aplicado no mês seguinte já cadastrado "
                    f"({target_mes}/{target_ano}): {old_custo:.2f} -> {new_custo:.2f} "
                    f"(mês de referência mantido sem alteração)"
                )
            else:
                log.info(f"[conjuntural] COD {cod:5d} -> mês seguinte ({target_mes}/{target_ano}) já com valor correto, sem alteração")
        else:
            idx = indices[0]
            e = parsed[idx]
            s = e["s"]
            old_custo = float(s[CONJ_CUSTO_SLICE[0]:CONJ_CUSTO_SLICE[1]])
            cvu_comparacao.append((cod, old_custo, new_custo))
            if abs(old_custo - new_custo) > 0.001:
                e["s"] = s[:5] + _conj_format_custo(new_custo) + s[15:]
                changed += 1
                log.info(f"[conjuntural] COD {cod:5d} -> CVU alterado: {old_custo:.2f} -> {new_custo:.2f}")
            else:
                log.info(f"[conjuntural] COD {cod:5d} -> sem alteração (CLAST={old_custo:.2f} CSV={new_custo:.2f})")

            if len(indices) > 1:
                log.info(f"[conjuntural] COD {cod:5d} -> {len(indices) - 1} linha(s) adicional(is) mantida(s) sem alteração")

    saida = [e["s"] + e["nl"] for e in parsed]
    return saida, changed, cvu_comparacao


def gerar_grafico_conjuntural(cvu_comparacao: list[tuple[int, float, float]], diretorio: Path) -> None:
    if not cvu_comparacao:
        log.info("[conjuntural][AVISO] Nenhuma usina atualizada — gráfico não gerado.")
        return

    diretorio.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dados = sorted(cvu_comparacao, key=lambda t: t[1])
    cods = [t[0] for t in dados]
    old_valores = [t[1] for t in dados]
    new_valores = [t[2] for t in dados]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(range(len(cods)), old_valores, label="CVU antigo")
    ax.plot(range(len(cods)), new_valores, label="CVU novo")
    ax.set_xticks(range(len(cods)))
    ax.set_xticklabels(cods, rotation=90, fontsize=6)
    ax.set_xlabel("Código da usina (ordenado por CVU antigo crescente)")
    ax.set_ylabel("CVU")
    ax.set_title("CVU conjuntural — antigo x novo por usina")
    ax.legend()
    fig.tight_layout()

    caminho_png = diretorio / "diferenca_cvu_conjuntural.png"
    fig.savefig(caminho_png, dpi=150)
    plt.close(fig)
    log.info(f"[conjuntural] Gráfico gerado : {caminho_png}")


# ===========================================================================
# Divisão do arquivo CLAST completo em bloco estrutural / bloco conjuntural

def dividir_clast(linhas: list[str]) -> tuple[list[str], list[str]]:
    """
    Retorna (bloco1, bloco2) onde bloco1 vai do início até e incluindo a
    linha sentinela "9999" (bloco estrutural), e bloco2 é o restante do
    arquivo (bloco conjuntural).
    """
    for i, linha in enumerate(linhas):
        if linha.strip() == FIM_BLOCO_1:
            return linhas[: i + 1], linhas[i + 1:]
    raise ErroAlteracao(f"[ERRO] Linha sentinela '{FIM_BLOCO_1}' não encontrada no arquivo CLAST — "
              f"não foi possível separar os blocos estrutural/conjuntural.")


# ===========================================================================
# Main
