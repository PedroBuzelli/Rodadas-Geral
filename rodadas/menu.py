"""Menu interativo (uso local). Pergunta e monta o estudo; a execucao e' a mesma
da API (``estudo.rodar_estudo``). Ao final a "receita" fica salva na pasta da rodada.

``entrada``/``saida`` podem ser trocadas (por padrao, teclado e tela).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import estudo as est
from .alteracoes import REGISTRO, Parametro
from .alteracoes.registro import avaliar_aplicabilidade
from .core.deck import DeckInvalido, carregar_deck
from .core.dger import ler_dger

CONFIG_LOCAL = est.RAIZ_PROJETO / "config" / "local.json"


def carregar_config(caminho: Path = CONFIG_LOCAL) -> dict:
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_config(config: dict, caminho: Path = CONFIG_LOCAL) -> None:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _limpo(texto: str) -> str:
    return texto.strip().strip('"').strip("'").strip()


class Menu:
    def __init__(self, entrada: Callable[[str], str] = input, saida: Callable[[str], None] = print,
                 raiz_saidas: Path = est.RAIZ_SAIDAS, config_path: Path = CONFIG_LOCAL):
        self.entrada, self.saida = entrada, saida
        self.raiz_saidas, self.config_path = raiz_saidas, config_path

    # -- perguntas ----------------------------------------------------------
    def _perguntar(self, texto: str, padrao=None) -> str:
        sufixo = f" [{padrao}]" if padrao not in (None, "", []) else ""
        resposta = _limpo(self.entrada(f"{texto}{sufixo}: "))
        return resposta if resposta else ("" if padrao is None else str(padrao))

    def _sim_nao(self, texto: str, padrao: bool = False) -> bool:
        resp = self._perguntar(f"{texto} (s/n)", "s" if padrao else "n").lower()
        return resp.startswith("s")

    def _valor(self, p: Parametro, atual):
        """Pergunta um parametro; devolve o valor (None = nao informado)."""
        padrao = atual if atual not in (None, "") else p.padrao
        while True:
            if p.tipo == "opcao":
                for i, o in enumerate(p.opcoes, 1):
                    self.saida(f"   {i}) {o}")
                r = self._perguntar(p.pergunta, padrao)
                r = p.opcoes[int(r) - 1] if r.isdigit() and 1 <= int(r) <= len(p.opcoes) else r
                if r in p.opcoes:
                    return r
                self.saida("   Opcao invalida.")
                continue
            if p.tipo == "bool":
                return self._sim_nao(p.pergunta, bool(padrao))
            if p.tipo == "lista_int":
                r = self._perguntar(p.pergunta, padrao)
                try:
                    return [int(x) for x in r.replace(",", " ").split()] if r and r != "[]" else []
                except ValueError:
                    self.saida("   Use apenas numeros.")
                    continue
            r = self._perguntar(p.pergunta, padrao)
            if not r:
                if p.obrigatorio:
                    self.saida("   Campo obrigatorio.")
                    continue
                return None
            if p.tipo == "pasta" and not Path(r).is_dir():
                self.saida(f"   Pasta nao encontrada: {r}")
                continue
            if p.tipo == "arquivo" and not Path(r).is_file():
                self.saida(f"   Arquivo nao encontrado: {r}")
                continue
            return r

    # -- fluxo --------------------------------------------------------------
    def _escolher_deck(self):
        while True:
            caminho = self._perguntar("Pasta do deck (Enter para sair)")
            if not caminho:
                return None, None
            try:
                return caminho, carregar_deck(caminho)
            except DeckInvalido as e:
                self.saida(f"   {e}")

    def _mostrar_deck(self, deck) -> None:
        self.saida(f"\nDeck {deck.tipo.upper()} identificado: {deck.pasta.name}")
        if deck.tem("dger"):
            d = ler_dger(deck.caminho("dger"))
            self.saida(f"   inicio do estudo {d.mes_inicio:02d}/{d.ano_inicio} | origem {d.origem.upper()} | '{d.titulo}'")
        elif deck.revisao:
            self.saida(f"   revisao {deck.revisao}")

    def _escolher_mes(self):
        while True:
            texto = self._perguntar("Mes-alvo AAAA-MM (Enter = nenhum)")
            try:
                est.parse_mes_alvo(texto)
                return texto or None
            except est.EstudoInvalido as e:
                self.saida(f"   {e}")

    def _escolher_alteracoes(self, estudo: dict, deck) -> list[str]:
        disponiveis = [a for a in REGISTRO.values() if deck.tipo in a.modelos]
        ctx = est.contexto_para_sugestao(estudo)
        sugeridas = {a.nome: avaliar_aplicabilidade(a, ctx) for a in disponiveis}
        self.saida("\nAlteracoes disponiveis para este deck:")
        for i, a in enumerate(disponiveis, 1):
            aplica, motivo = sugeridas[a.nome]
            marca = "SUGERIDA" if aplica else "nao sugerida"
            self.saida(f"  {i}) {a.nome} - {a.descricao}\n       [{marca}] {motivo}")
        padrao = " ".join(str(i) for i, a in enumerate(disponiveis, 1) if sugeridas[a.nome][0])
        while True:
            r = self._perguntar("Quais aplicar? Numeros na ordem desejada (Enter = as sugeridas)", padrao)
            try:
                idx = [int(x) for x in r.replace(",", " ").split()]
                if idx and all(1 <= i <= len(disponiveis) for i in idx) and len(set(idx)) == len(idx):
                    return [disponiveis[i - 1].nome for i in idx]
            except ValueError:
                pass
            if not r:
                return []
            self.saida("   Escolha invalida (use os numeros da lista, sem repetir).")

    def _coletar_parametros(self, escolhidas: list[str], estudo: dict, config: dict) -> None:
        externos, params = estudo["externos"], estudo["params"]
        salvar: dict[str, str] = {}
        for nome in escolhidas:
            alt = REGISTRO[nome]
            if not alt.parametros:
                continue
            self.saida(f"\n-- {nome}")
            for p in alt.parametros:
                if p.externo and p.externo in externos:
                    continue  # ja perguntado em outra alteracao
                atual = config.get(p.externo) if p.externo else None
                valor = self._valor(p, atual)
                if valor is None:
                    continue
                if p.externo:
                    externos[p.externo] = valor
                    if p.lembrar and valor != config.get(p.externo):
                        salvar[p.externo] = valor
                else:
                    params.setdefault(nome, {})[p.nome] = valor
        if salvar and self._sim_nao("\nGuardar essa(s) pasta(s) como padrao neste computador?", True):
            salvar_config({**config, **salvar}, self.config_path)
            self.saida("   Guardado em config/local.json")

    def _resumo(self, estudo: dict) -> None:
        self.saida("\n=== Resumo da rodada ===")
        self.saida(f"Deck     : {estudo['deck']}")
        self.saida(f"Mes-alvo : {estudo.get('mes_alvo') or '-'}")
        self.saida("Ordem    : " + " -> ".join(estudo["alteracoes"]))
        for k, v in estudo["externos"].items():
            self.saida(f"Externo  : {k} = {v}")
        for nome, ps in estudo["params"].items():
            self.saida(f"Params   : {nome} {ps}")

    def executar(self):
        """Roda uma rodada. Devolve a pasta da rodada ou None se cancelada/falhou."""
        config = carregar_config(self.config_path)
        self.saida("=== Rodadas-Geral ===")
        caminho, deck = self._escolher_deck()
        if deck is None:
            return None
        self._mostrar_deck(deck)
        estudo = {"deck": caminho, "mes_alvo": self._escolher_mes(), "alteracoes": [],
                  "externos": {}, "params": {}}
        # externos ja guardados entram so na sugestao (nao no estudo)
        estudo_sugestao = {**estudo, "externos": {k: v for k, v in config.items()}}
        estudo["alteracoes"] = self._escolher_alteracoes(estudo_sugestao, deck)
        if not estudo["alteracoes"]:
            self.saida("Nenhuma alteracao escolhida. Nada foi feito.")
            return None
        self._coletar_parametros(estudo["alteracoes"], estudo, config)
        self._resumo(estudo)
        if not self._sim_nao("\nExecutar agora?", True):
            self.saida("Cancelado.")
            return None
        try:
            pasta, plano, resultados = est.rodar_estudo(estudo, self.raiz_saidas)
        except Exception as e:  # noqa: BLE001 - mostra ao usuario; detalhes no log_rodada.json
            self.saida(f"\n[ERRO] {e}\nO log da tentativa ficou em {self.raiz_saidas}")
            return None
        self.saida("\n=== Resultado ===")
        for r in resultados:
            self.saida(f"{'ALTEROU ' if r.alterou else 'sem alteracao'} {r.alteracao}")
            for aviso in r.avisos:
                self.saida(f"     aviso: {aviso}")
        self.saida(f"\nDeck alterado e log em: {pasta}")
        self.saida("Para repetir esta rodada: python main.py estudo \"" + str(pasta / "estudo.json") + "\"")
        return pasta


def executar_menu() -> None:
    Menu().executar()
