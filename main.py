"""Ponto de entrada local. A futura API chama as mesmas funcoes de
``rodadas.orquestrador``.

    python main.py                      (menu interativo - uso local)
    python main.py estudo estudo.json   (repete uma rodada salva)
    python main.py listar
    python main.py inspecionar --deck "decks exemplo/NW202609"
    python main.py plano   --deck ... --mes-alvo 2026-10 [--aplicar a b] [--pular x] [--forcar y]
    python main.py rodar   --deck ... --saida ... --mes-alvo 2026-10 [--aplicar a b] [--simular]
                           [--externo cvu_dir=...] [--param cvu_clast.modo=ambos]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from rodadas import orquestrador
from rodadas.alteracoes import REGISTRO, Contexto
from rodadas.core import mes_base
from rodadas.core.deck import DeckInvalido, carregar_deck
from rodadas.core.dger import ler_dger


def _mes_alvo(texto: str | None) -> tuple[int, int] | None:
    if not texto:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", texto)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise SystemExit(f"--mes-alvo invalido: {texto!r} (use AAAA-MM)")
    return int(m.group(2)), int(m.group(1))


def _fmt(d: tuple[int, int] | None) -> str:
    return "-" if d is None else f"{d[0]:02d}/{d[1]}"


def cmd_listar(_args) -> None:
    if not REGISTRO:
        print("Nenhuma alteracao registrada ainda.")
    for alt in REGISTRO.values():
        print(f"{alt.nome:<28} [{'/'.join(alt.modelos)}]  {alt.descricao}")


def cmd_inspecionar(args) -> None:
    deck = carregar_deck(args.deck)
    print(f"Pasta : {deck.pasta}\nTipo  : {deck.tipo}")
    if deck.tipo == "decomp":
        print(f"Revisao: {deck.revisao}")
    for papel, caminho in deck.arquivos.items():
        print(f"  {papel:<9} -> {caminho.name}")
    if deck.tem("dger"):
        d = ler_dger(deck.caminho("dger"))
        print(f"\ndger.dat: '{d.titulo}'\n  inicio do estudo: {d.mes_inicio:02d}/{d.ano_inicio}"
              f"  | origem: {d.origem}")
        oficial = (d.mes_inicio, d.ano_inicio)
        print("\nMes-base deduzido por arquivo (deve coincidir com o dger.dat):")
        for papel, fn in (("expt", mes_base.mes_base_expt), ("modif", mes_base.mes_base_modif),
                          ("clast", mes_base.mes_base_clast)):
            if deck.tem(papel):
                base = fn(deck.caminho(papel))
                marca = "ok" if base == oficial else "DIVERGE"
                print(f"  {papel:<6} {_fmt(base)}  {marca}")


def _pares(itens: list[str] | None, rotulo: str) -> list[tuple[str, str]]:
    pares = []
    for item in itens or []:
        if "=" not in item:
            raise ValueError(f"{rotulo} invalido: {item!r} (use chave=valor)")
        chave, valor = item.split("=", 1)
        pares.append((chave.strip(), valor.strip()))
    return pares


def _externos(args) -> dict[str, str]:
    return dict(_pares(args.externo, "--externo"))


def _params(args) -> dict[str, dict]:
    """--param alteracao.chave=valor  (valor: numero, true/false ou lista a,b,c)."""
    params: dict[str, dict] = {}
    for chave, valor in _pares(args.param, "--param"):
        if "." not in chave:
            raise ValueError(f"--param invalido: {chave!r} (use alteracao.chave=valor)")
        alteracao, campo = chave.split(".", 1)
        if valor.lower() in ("true", "false"):
            v = valor.lower() == "true"
        elif re.fullmatch(r"-?\d+", valor):
            v = int(valor)
        elif "," in valor:
            v = [int(x) if re.fullmatch(r"-?\d+", x.strip()) else x.strip() for x in valor.split(",")]
        else:
            v = valor
        params.setdefault(alteracao, {})[campo] = v
    return params


def _contexto(args) -> Contexto:
    return Contexto(carregar_deck(args.deck), _mes_alvo(args.mes_alvo), _externos(args))


def _imprimir_plano(plano) -> None:
    for i, p in enumerate(plano, 1):
        print(f"{i}. [{'APLICAR' if p.executar else 'pular  '}] {p.nome} - {p.motivo}")


def cmd_plano(args) -> None:
    _imprimir_plano(orquestrador.montar_plano(_contexto(args), args.aplicar, args.forcar, args.pular))


def cmd_estudo(args) -> None:
    from rodadas import estudo
    pasta, plano, resultados = estudo.rodar_estudo(estudo.carregar_estudo(args.arquivo))
    _imprimir_plano(plano)
    for r in resultados:
        print(f"-> {r.alteracao}: {'alterou' if r.alterou else 'sem alteracao'}")
        for aviso in r.avisos:
            print(f"   aviso: {aviso}")
    print(f"\nDeck alterado e log em: {pasta}")


def cmd_rodar(args) -> None:
    plano, resultados = orquestrador.rodar(
        Path(args.deck), Path(args.saida), _mes_alvo(args.mes_alvo),
        args.aplicar, args.forcar, args.pular, _params(args), _externos(args), simular=args.simular)
    _imprimir_plano(plano)
    for r in resultados:
        print(f"-> {r.alteracao}: {'alterou' if r.alterou else 'sem alteracao'} {r.resumo}")
        for aviso in r.avisos:
            print(f"   aviso: {aviso}")
    if not args.simular:
        print(f"\nDeck alterado em: {args.saida}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # sem argumentos: menu interativo
        from rodadas.menu import executar_menu
        executar_menu()
        return 0
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar", help="lista as alteracoes disponiveis").set_defaults(fn=cmd_listar)
    s = sub.add_parser("estudo", help="roda um estudo salvo (estudo.json); saida em saidas/")
    s.add_argument("arquivo")
    s.set_defaults(fn=cmd_estudo)

    s = sub.add_parser("inspecionar", help="identifica o deck e confere o mes-base")
    s.add_argument("--deck", required=True)
    s.set_defaults(fn=cmd_inspecionar)

    for nome, fn in (("plano", cmd_plano), ("rodar", cmd_rodar)):
        s = sub.add_parser(nome)
        s.add_argument("--deck", required=True)
        s.add_argument("--mes-alvo", help="AAAA-MM")
        s.add_argument("--aplicar", nargs="*", default=None, help="so estas, nesta ordem")
        s.add_argument("--forcar", nargs="*", default=None)
        s.add_argument("--pular", nargs="*", default=None)
        s.add_argument("--externo", action="append", metavar="CHAVE=CAMINHO",
                       help="arquivo externo (ex.: cvu_dir=..., gtmin_ccee_xlsx=...); repetivel")
        s.add_argument("--param", action="append", metavar="ALTERACAO.CHAVE=VALOR",
                       help="parametro de uma alteracao (ex.: cvu_clast.modo=ambos); repetivel")
        if nome == "rodar":
            s.add_argument("--saida", required=True, help="pasta nova (copia alterada do deck)")
            s.add_argument("--simular", action="store_true", help="mostra o que faria, sem gravar")
        s.set_defaults(fn=fn)

    args = p.parse_args(argv)
    if args.cmd == "rodar":
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        args.fn(args)
    except (DeckInvalido, KeyError, FileExistsError, ValueError, OSError) as e:
        print(f"[ERRO] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
