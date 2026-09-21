"""Registro das alteracoes disponiveis.

Para adicionar uma alteracao:

1. Criar um modulo em ``rodadas/alteracoes/`` com uma funcao
   ``executar(ctx: Contexto, params: dict) -> Resultado``.
2. Registrar com ``@registrar(nome=..., descricao=..., modelos=(...))``.
   Opcionalmente informar ``aplicavel``: funcao ``(ctx) -> (bool, motivo)``
   que diz se a alteracao tem efeito para aquele estudo. As regras apenas
   SUGEREM; quem decide e' o usuario (ver ``orquestrador.montar_plano``).
3. Importar o modulo em ``rodadas/alteracoes/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..core.deck import Deck


class ErroAlteracao(Exception):
    """Erro esperado de uma alteracao (entrada faltando, arquivo fora do padrao...).
    Substitui os ``sys.exit`` dos scripts originais."""


@dataclass
class Contexto:
    """Tudo que uma alteracao precisa saber. Nunca caminhos soltos."""
    deck: Deck                       # deck de TRABALHO (copia; nunca o original)
    mes_alvo: tuple[int, int] | None = None   # (mes, ano)
    dados_externos: dict[str, str] = field(default_factory=dict)  # CSVs, xlsx...


@dataclass
class Resultado:
    alteracao: str
    alterou: bool
    resumo: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


Aplicavel = Callable[[Contexto], tuple[bool, str]]
Executar = Callable[[Contexto, dict], Resultado]


@dataclass
class Parametro:
    """Descreve uma entrada da alteracao (usada pelo menu e, no futuro, pelo catalogo da API).

    tipo: "texto", "opcao" (uma de ``opcoes``), "bool", "lista_int", "pasta" ou "arquivo".
    ``externo``: se informado, o valor vai para ``Contexto.dados_externos[externo]``
    (arquivos que nao fazem parte do deck) em vez de ``params[nome]``.
    ``perguntar``: False = o menu nao pergunta (valor vem do padrao ou e' descoberto sozinho).
    """
    nome: str
    pergunta: str
    tipo: str = "texto"
    opcoes: tuple[str, ...] = ()
    padrao: object = None
    obrigatorio: bool = False
    externo: str | None = None
    perguntar: bool = True


@dataclass
class Alteracao:
    nome: str
    descricao: str
    modelos: tuple[str, ...]         # ("newave",), ("decomp",) ou ambos
    executar: Executar
    aplicavel: Aplicavel | None = None
    parametros: tuple[Parametro, ...] = ()


REGISTRO: dict[str, Alteracao] = {}


def _sempre(_ctx: Contexto) -> tuple[bool, str]:
    return True, "sem regra de aplicabilidade"


def registrar(nome: str, descricao: str, modelos: tuple[str, ...],
              aplicavel: Aplicavel | None = None, parametros: tuple[Parametro, ...] = ()):
    def decorador(fn: Executar) -> Executar:
        if nome in REGISTRO:
            raise ValueError(f"ja existe alteracao registrada com o nome {nome!r}")
        REGISTRO[nome] = Alteracao(nome, descricao, modelos, fn, aplicavel, parametros)
        return fn
    return decorador


def avaliar_aplicabilidade(alt: Alteracao, ctx: Contexto) -> tuple[bool, str]:
    if ctx.deck.tipo not in alt.modelos:
        return False, f"nao se aplica a decks {ctx.deck.tipo}"
    return (alt.aplicavel or _sempre)(ctx)
