"""Estudo = descricao de uma rodada (o mesmo JSON que a API vai receber).

    {
      "deck": "decks exemplo/NW202609",
      "mes_alvo": "2026-10",                       (opcional)
      "alteracoes": ["rolagem_modif", "cvu_clast"],  (ordem de execucao; escolha do usuario)
      "externos": {"cvu_dir": "Arquivos CVU"},       (arquivos que nao estao no deck)
      "params": {"cvu_clast": {"modo": "ambos"}}     (parametros de cada alteracao)
    }

Cada rodada gera uma pasta em ``saidas/`` (dentro do projeto, fora do Git):

    saidas/<AAAAMMDD_HHMMSS>_<deck>[_<mes-alvo>]/
        <nome do deck>/     deck alterado (so arquivos do deck; o NEWAVE/DECOMP e' sensivel a extras)
        estudo.json         a "receita" desta rodada (pode ser rodada de novo)
        log_rodada.json     plano, resultados, avisos e mensagens
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from . import orquestrador
from .alteracoes import Contexto
from .core.deck import carregar_deck

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
RAIZ_SAIDAS = RAIZ_PROJETO / "saidas"


class EstudoInvalido(ValueError):
    pass


def parse_mes_alvo(texto: str | None) -> tuple[int, int] | None:
    """'AAAA-MM' -> (mes, ano)."""
    if not texto:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", str(texto).strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise EstudoInvalido(f"mes_alvo invalido: {texto!r} (use AAAA-MM)")
    return int(m.group(2)), int(m.group(1))


def validar(estudo: dict) -> None:
    if not estudo.get("deck"):
        raise EstudoInvalido("estudo sem 'deck'")
    if not estudo.get("alteracoes"):
        raise EstudoInvalido("estudo sem 'alteracoes'")
    parse_mes_alvo(estudo.get("mes_alvo"))


def carregar_estudo(caminho: Path | str) -> dict:
    estudo = json.loads(Path(caminho).read_text(encoding="utf-8"))
    validar(estudo)
    return estudo


def salvar_estudo(estudo: dict, caminho: Path) -> None:
    Path(caminho).write_text(json.dumps(estudo, ensure_ascii=False, indent=2), encoding="utf-8")


def _pasta_rodada(estudo: dict, raiz: Path, agora: datetime) -> Path:
    nome_deck = Path(estudo["deck"]).name
    partes = [agora.strftime("%Y%m%d_%H%M%S"), nome_deck]
    if estudo.get("mes_alvo"):
        partes.append(str(estudo["mes_alvo"]))
    return Path(raiz) / "_".join(partes)


class _ColetorDeMensagens(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.mensagens: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensagens.append(record.getMessage())


def rodar_estudo(estudo: dict, raiz_saidas: Path = RAIZ_SAIDAS, agora: datetime | None = None):
    """Executa o estudo. Devolve (pasta_da_rodada, plano, resultados).

    O log_rodada.json e' gravado mesmo se uma alteracao falhar (status "erro");
    a excecao e' relancada depois.
    """
    validar(estudo)
    agora = agora or datetime.now()
    pasta_rodada = _pasta_rodada(estudo, raiz_saidas, agora)
    pasta_rodada.mkdir(parents=True, exist_ok=False)
    saida_deck = pasta_rodada / Path(estudo["deck"]).name
    salvar_estudo(estudo, pasta_rodada / "estudo.json")

    coletor = _ColetorDeMensagens()
    logger = logging.getLogger("rodadas")
    nivel_antes = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(coletor)

    log: dict = {"iniciado_em": agora.isoformat(timespec="seconds"), "status": "ok",
                 "estudo": estudo, "plano": [], "resultados": [], "erro": None}
    plano, resultados, erro = [], [], None
    try:
        plano, resultados = orquestrador.rodar(
            Path(estudo["deck"]), saida_deck, parse_mes_alvo(estudo.get("mes_alvo")),
            escolhidas=list(estudo["alteracoes"]), params=estudo.get("params") or {},
            dados_externos=estudo.get("externos") or {})
    except Exception as e:  # noqa: BLE001 - registrado no log e relancado
        erro = e
        log["status"] = "erro"
        log["erro"] = f"{type(e).__name__}: {e}"
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel_antes)
        log["plano"] = [vars(p) for p in plano]
        log["resultados"] = [vars(r) for r in resultados]
        log["mensagens"] = coletor.mensagens
        (pasta_rodada / "log_rodada.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if erro is not None:
        raise erro
    return pasta_rodada, plano, resultados


def contexto_para_sugestao(estudo_parcial: dict) -> Contexto:
    """Contexto so para o plano sugerido (menu); nao altera nada."""
    return Contexto(carregar_deck(estudo_parcial["deck"]), parse_mes_alvo(estudo_parcial.get("mes_alvo")),
                    dict(estudo_parcial.get("externos") or {}))
