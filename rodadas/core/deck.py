"""Identificacao de um deck: tipo (NEWAVE/DECOMP) e localizacao dos arquivos.

Nenhuma alteracao mexe em caminho ou nome de arquivo: pede ao ``Deck``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import texto

# papel do arquivo -> (inicio do rotulo em arquivos.dat, nome padrao)
_PAPEIS_NEWAVE = {
    "dger": ("DADOS GERAIS", "dger.dat"),
    "modif": ("ALTERACAO DADOS USINAS HIDRO", "modif.dat"),
    "clast": ("DADOS DAS CLASSES TERMICAS", "clast.dat"),
    "expt": ("ARQUIVO DE EXPANSAO TERMICA", "expt.dat"),
}


class DeckInvalido(Exception):
    pass


def _achar(pasta: Path, nome: str) -> Path | None:
    """Procura ``nome`` na pasta ignorando maiusculas (Linux e' case-sensitive)."""
    alvo = nome.strip().lower()
    if not alvo:
        return None
    for p in pasta.iterdir():
        if p.is_file() and p.name.lower() == alvo:
            return p
    return None


@dataclass
class Deck:
    pasta: Path
    tipo: str                                   # "newave" ou "decomp"
    arquivos: dict[str, Path] = field(default_factory=dict)  # papel -> caminho
    revisao: str | None = None                  # so DECOMP: sufixo (ex.: "rv0")

    def caminho(self, papel: str) -> Path:
        if papel not in self.arquivos:
            raise DeckInvalido(f"arquivo {papel!r} nao encontrado no deck {self.pasta}")
        return self.arquivos[papel]

    def tem(self, papel: str) -> bool:
        return papel in self.arquivos


def _ler_arquivos_dat(caminho: Path) -> dict[str, str]:
    """arquivos.dat: linhas 'ROTULO : NOME'."""
    mapa: dict[str, str] = {}
    for linha in texto.ler(caminho).linhas:
        if ":" in linha:
            rotulo, nome = linha.split(":", 1)
            mapa[rotulo.strip().upper()] = nome.strip()
    return mapa


def _primeira_linha(caminho: Path) -> str:
    linhas = [l.strip() for l in texto.ler(caminho).linhas if l.strip()]
    return linhas[0] if linhas else ""


def _carregar_newave(pasta: Path, arq_dat: Path) -> Deck:
    mapa = _ler_arquivos_dat(arq_dat)
    deck = Deck(pasta=pasta, tipo="newave")
    for papel, (rotulo, padrao) in _PAPEIS_NEWAVE.items():
        nome = next((n for r, n in mapa.items() if r.startswith(rotulo)), padrao)
        achado = _achar(pasta, nome)
        if achado:
            deck.arquivos[papel] = achado
    deck.arquivos["arquivos"] = arq_dat
    return deck


def _carregar_decomp(pasta: Path, revisao: str) -> Deck:
    deck = Deck(pasta=pasta, tipo="decomp", revisao=revisao)
    dadger = _achar(pasta, f"dadger.{revisao}")
    if dadger:
        deck.arquivos["dadger"] = dadger
    return deck


def carregar_deck(pasta: Path | str) -> Deck:
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise DeckInvalido(f"pasta do deck nao encontrada: {pasta}")
    caso = _achar(pasta, "caso.dat")
    if caso is None:
        raise DeckInvalido(f"caso.dat nao encontrado em {pasta}")

    conteudo = _primeira_linha(caso)

    # NEWAVE: caso.dat aponta para o arquivo de nomes (ex.: ARQUIVOS.DAT)
    arq_dat = _achar(pasta, conteudo)
    if arq_dat is not None and arq_dat.suffix.lower() == ".dat":
        return _carregar_newave(pasta, arq_dat)

    # DECOMP: caso.dat traz o sufixo da revisao (ex.: rv0)
    if conteudo and _achar(pasta, f"dadger.{conteudo}") is not None:
        return _carregar_decomp(pasta, conteudo)

    raise DeckInvalido(f"nao foi possivel identificar se {pasta} e' NEWAVE ou DECOMP")
