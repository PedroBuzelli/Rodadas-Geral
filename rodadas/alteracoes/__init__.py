"""Alteracoes disponiveis. Cada modulo importado aqui se registra sozinho.

Os modulos ``_*_original`` guardam a logica portada dos scripts originais
(prepara-deck, att-cvu, ONS-to-CCEE) e nao se registram.
"""

from .registro import REGISTRO, Alteracao, Contexto, ErroAlteracao, Parametro, Resultado, registrar

# Ordem de importacao = ordem padrao sugerida (rolagem -> CVU -> conversao).
from . import rolagem, cvu, ons_ccee  # noqa: E402,F401

__all__ = ["REGISTRO", "Alteracao", "Contexto", "ErroAlteracao", "Parametro", "Resultado", "registrar"]
