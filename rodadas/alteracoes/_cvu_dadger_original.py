"""CVU do bloco CT do dadger (DECOMP).

PORTE de att-cvu/atualiza_cvu_dadger.py (commit 95cff80). A funcao
``atualizar_linha_ct`` e' a original (sys.exit -> ErroAlteracao).
"""

from __future__ import annotations

from .registro import ErroAlteracao

CT_COD_SLICE = (2, 7)
CT_ESTAGIO_POS = 25
CT_CVU_SLICES = [(39, 49), (59, 69), (79, 89)]
CT_LEN = 89



def atualizar_linha_ct(linha: str, cvu_map: dict[int, float], estagios_preservar: set[int]):
    """Retorna (nova_linha, cod, cvu_antigo, cvu_novo) ou (linha, None, None, None) se não alterada."""
    s = linha.rstrip("\r\n")
    if not (s.startswith("CT") and len(s) == CT_LEN):
        return linha, None, None, None
    try:
        cod = int(s[CT_COD_SLICE[0]:CT_COD_SLICE[1]])
        estagio = int(s[CT_ESTAGIO_POS])
    except ValueError:
        return linha, None, None, None
    if cod not in cvu_map or estagio in estagios_preservar:
        return linha, None, None, None

    novo = cvu_map[cod]
    antigo = float(s[CT_CVU_SLICES[0][0]:CT_CVU_SLICES[0][1]])
    fmt = f"{novo:>10.2f}"
    if len(fmt) != 10:
        raise ErroAlteracao(f"[ERRO] CVU {novo} do código {cod} não cabe em 10 colunas.")
    nova = s
    for ini, fim in CT_CVU_SLICES:
        nova = nova[:ini] + fmt + nova[fim:]
    if nova == s:
        return linha, cod, antigo, novo
    return nova + linha[len(s):], cod, antigo, novo

