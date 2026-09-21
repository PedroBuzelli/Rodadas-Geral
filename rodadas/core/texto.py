"""Leitura e escrita de arquivos de texto do deck preservando codificacao
e terminador de linha originais (os decks misturam ASCII, ISO-8859 e UTF-8,
com CRLF ou LF)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ArquivoTexto:
    linhas: list[str]      # sem terminador
    encoding: str
    eol: str               # "\r\n" ou "\n"
    termina_com_eol: bool


def detectar_encoding(dados: bytes) -> str:
    try:
        dados.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def ler(caminho: Path) -> ArquivoTexto:
    dados = Path(caminho).read_bytes()
    encoding = detectar_encoding(dados)
    conteudo = dados.decode(encoding)
    eol = "\r\n" if "\r\n" in conteudo else "\n"
    linhas = conteudo.split(eol)
    termina = bool(linhas) and linhas[-1] == ""
    if termina:
        linhas = linhas[:-1]
    return ArquivoTexto(linhas, encoding, eol, termina)


def gravar(caminho: Path, arq: ArquivoTexto) -> None:
    conteudo = arq.eol.join(arq.linhas) + (arq.eol if arq.termina_com_eol else "")
    Path(caminho).write_bytes(conteudo.encode(arq.encoding))
