"""Estudo = uma rodada sobre os decks de uma pasta ``Estudos/<ID>/`` (o mesmo JSON
que a API vai receber).

Pastas fixas (ver README):

    Estudos/<ID>/<deck>/        decks de entrada (NW202610, DC202610-sem1 ...)
    Arquivos CVU/               CSVs de CVU
    saidas/                     resultado (criada automaticamente)

O **mes-alvo** de cada deck vem do nome da pasta do deck (``NW202610`` -> 2026-10;
``DC202610-sem1`` -> 2026-10). Assim todos os decks do estudo sao lidos de uma vez,
mesmo de meses diferentes.

    {
      "estudo": "1",
      "externos": {},                                (opcional; sobrepoe os padroes)
      "decks": [
        {"deck": "Estudos/1/NW202610",               (relativo a raiz do projeto ou absoluto)
         "mes_alvo": "2026-10",                      (opcional; senao vem do nome da pasta)
         "alteracoes": ["rolagem_modif", "cvu_clast"],   (ordem de execucao; escolha do usuario)
         "params": {"cvu_clast": {"modo": "ambos"}}}
      ]
    }

Cada rodada gera:

    saidas/<ID>_<AAAAMMDD_HHMMSS>/
        <nome do deck>/     deck alterado (so arquivos do deck; NEWAVE/DECOMP sao sensiveis a extras)
        estudo.json         a "receita" da rodada (pode ser rodada de novo)
        log_rodada.json     plano, resultados, avisos e mensagens de cada deck
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import orquestrador
from .core.deck import Deck, DeckInvalido, carregar_deck

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_ESTUDOS = RAIZ_PROJETO / "Estudos"
PASTA_CVU = RAIZ_PROJETO / "Arquivos CVU"
RAIZ_SAIDAS = RAIZ_PROJETO / "saidas"

# AAAAMM no nome da pasta, com separador opcional (NW202610, DC202610-sem1, NW_2026_10)
_MES_NO_NOME = re.compile(r"(?<!\d)(20\d{2})[_-]?(0[1-9]|1[0-2])(?!\d)")


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


def formatar_mes(mes_ano: tuple[int, int] | None) -> str | None:
    return None if mes_ano is None else f"{mes_ano[1]}-{mes_ano[0]:02d}"


def mes_alvo_do_nome(nome: str) -> tuple[int, int] | None:
    """Mes-alvo lido do nome da pasta do deck. NW202610 -> (10, 2026)."""
    m = _MES_NO_NOME.search(nome)
    return (int(m.group(2)), int(m.group(1))) if m else None


def resolver(caminho: str | Path) -> Path:
    """Caminho relativo e' relativo a raiz do projeto (nao ao diretorio atual)."""
    p = Path(caminho)
    return p if p.is_absolute() else RAIZ_PROJETO / p


# --- descoberta -------------------------------------------------------------

@dataclass
class DeckEncontrado:
    pasta: Path
    deck: Deck
    mes_alvo: tuple[int, int] | None


def listar_estudos(raiz: Path = PASTA_ESTUDOS) -> list[str]:
    if not Path(raiz).is_dir():
        return []
    return sorted(p.name for p in Path(raiz).iterdir() if p.is_dir())


def descobrir_decks(pasta_estudo: Path) -> tuple[list[DeckEncontrado], list[str]]:
    """Decks (NEWAVE/DECOMP) dentro de ``Estudos/<ID>/`` e nomes de subpastas ignoradas."""
    encontrados, ignoradas = [], []
    for p in sorted(Path(pasta_estudo).iterdir()):
        if not p.is_dir():
            continue
        try:
            deck = carregar_deck(p)
        except DeckInvalido:
            ignoradas.append(p.name)
            continue
        encontrados.append(DeckEncontrado(p, deck, mes_alvo_do_nome(p.name)))
    return encontrados, ignoradas


def externos_padrao(pasta_deck: Path, mes_alvo: tuple[int, int] | None,
                    pasta_cvu: Path = PASTA_CVU) -> dict[str, str]:
    """Arquivos externos em locais fixos:
    - CSVs de CVU: pasta ``Arquivos CVU/``;
    - planilha GTMIN CCEE: ``GTMIN_CCEE_<MM><AAAA>.xlsx`` (do mes-alvo) na pasta do deck ou na
      do estudo; se nao houver o do mes-alvo, usa a unica ``GTMIN_CCEE_*.xlsx`` encontrada.
    """
    externos: dict[str, str] = {}
    if Path(pasta_cvu).is_dir():
        externos["cvu_dir"] = str(pasta_cvu)
    for pasta in (Path(pasta_deck), Path(pasta_deck).parent):
        candidatos = sorted(p for p in pasta.glob("*.xlsx") if p.name.upper().startswith("GTMIN_CCEE_"))
        if mes_alvo:
            do_mes = [p for p in candidatos if p.stem.upper() == f"GTMIN_CCEE_{mes_alvo[0]:02d}{mes_alvo[1]}"]
            if do_mes:
                candidatos = do_mes
        if len(candidatos) == 1:
            externos["gtmin_ccee_xlsx"] = str(candidatos[0])
            break
    return externos


# --- arquivo de estudo ------------------------------------------------------

def validar(estudo: dict) -> None:
    decks = estudo.get("decks")
    if not decks:
        raise EstudoInvalido("estudo sem 'decks'")
    for d in decks:
        if not d.get("deck"):
            raise EstudoInvalido("deck sem 'deck' (caminho)")
        if not d.get("alteracoes"):
            raise EstudoInvalido(f"deck {d['deck']!r} sem 'alteracoes'")
        parse_mes_alvo(d.get("mes_alvo"))


def carregar_estudo(caminho: Path | str) -> dict:
    estudo = json.loads(Path(caminho).read_text(encoding="utf-8"))
    validar(estudo)
    return estudo


def salvar_estudo(estudo: dict, caminho: Path) -> None:
    Path(caminho).write_text(json.dumps(estudo, ensure_ascii=False, indent=2), encoding="utf-8")


# --- execucao ---------------------------------------------------------------

class _ColetorDeMensagens(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.mensagens: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensagens.append(record.getMessage())


@dataclass
class ResultadoDeck:
    deck: str
    mes_alvo: tuple[int, int] | None
    plano: list = field(default_factory=list)
    resultados: list = field(default_factory=list)
    erro: str | None = None


@dataclass
class ResultadoEstudo:
    pasta: Path
    decks: list[ResultadoDeck]

    @property
    def status(self) -> str:
        erros = sum(1 for d in self.decks if d.erro)
        return "ok" if not erros else ("erro" if erros == len(self.decks) else "parcial")


def _pasta_rodada(estudo: dict, raiz: Path, agora: datetime) -> Path:
    return Path(raiz) / f"{estudo.get('estudo') or 'estudo'}_{agora.strftime('%Y%m%d_%H%M%S')}"


def rodar_estudo(estudo: dict, raiz_saidas: Path = RAIZ_SAIDAS, agora: datetime | None = None,
                 pasta_cvu: Path = PASTA_CVU) -> ResultadoEstudo:
    """Executa todos os decks do estudo, um apos o outro, cada um na sua copia.

    Uma falha em um deck nao impede os demais: o erro fica registrado no
    log_rodada.json (status "parcial" ou "erro") e em ``ResultadoDeck.erro``.
    """
    validar(estudo)
    agora = agora or datetime.now()
    pasta_rodada = _pasta_rodada(estudo, raiz_saidas, agora)
    pasta_rodada.mkdir(parents=True, exist_ok=False)
    salvar_estudo(estudo, pasta_rodada / "estudo.json")

    coletor = _ColetorDeMensagens()
    logger = logging.getLogger("rodadas")
    nivel_antes = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(coletor)

    resultados: list[ResultadoDeck] = []
    log_decks: list[dict] = []
    try:
        for entrada in estudo["decks"]:
            pasta_deck = resolver(entrada["deck"])
            mes_alvo = parse_mes_alvo(entrada.get("mes_alvo")) or mes_alvo_do_nome(pasta_deck.name)
            res = ResultadoDeck(pasta_deck.name, mes_alvo)
            coletor.mensagens = []
            try:
                externos = {**externos_padrao(pasta_deck, mes_alvo, pasta_cvu), **(estudo.get("externos") or {}),
                            **(entrada.get("externos") or {})}
                res.plano, res.resultados = orquestrador.rodar(
                    pasta_deck, pasta_rodada / pasta_deck.name, mes_alvo,
                    escolhidas=list(entrada["alteracoes"]), params=entrada.get("params") or {},
                    dados_externos=externos)
            except Exception as e:  # noqa: BLE001 - registrado no log; os outros decks continuam
                res.erro = f"{type(e).__name__}: {e}"
            resultados.append(res)
            log_decks.append({
                "deck": res.deck, "mes_alvo": formatar_mes(mes_alvo),
                "status": "erro" if res.erro else "ok", "erro": res.erro,
                "plano": [vars(p) for p in res.plano], "resultados": [vars(r) for r in res.resultados],
                "mensagens": coletor.mensagens})
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel_antes)
        resultado = ResultadoEstudo(pasta_rodada, resultados)
        (pasta_rodada / "log_rodada.json").write_text(json.dumps(
            {"iniciado_em": agora.isoformat(timespec="seconds"), "status": resultado.status,
             "estudo": estudo, "decks": log_decks}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
    return resultado
