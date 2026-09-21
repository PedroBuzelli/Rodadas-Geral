"""Menu interativo (uso local).

Fluxo: escolhe o estudo em ``Estudos/`` -> le todos os decks dele (tipo e mes-alvo
pelo nome da pasta) -> escolhe as alteracoes de cada tipo de deck (NEWAVE e DECOMP
tem alteracoes diferentes) -> confirma -> executa. As pastas sao fixas (ver README);
o menu nao pergunta caminhos.

``entrada``/``saida`` podem ser trocadas (por padrao, teclado e tela).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import estudo as est
from .alteracoes import REGISTRO, Contexto, Parametro
from .alteracoes.registro import avaliar_aplicabilidade
from .core.dger import ler_dger


def _limpo(texto: str) -> str:
    return texto.strip().strip('"').strip("'").strip()


def _fmt_mes(m) -> str:
    return "sem mes no nome" if m is None else f"{m[0]:02d}/{m[1]}"


class Menu:
    def __init__(self, entrada: Callable[[str], str] = input, saida: Callable[[str], None] = print,
                 pasta_estudos: Path = est.PASTA_ESTUDOS, raiz_saidas: Path = est.RAIZ_SAIDAS,
                 pasta_cvu: Path = est.PASTA_CVU):
        self.entrada, self.saida = entrada, saida
        self.pasta_estudos, self.raiz_saidas, self.pasta_cvu = pasta_estudos, raiz_saidas, pasta_cvu

    # -- perguntas ----------------------------------------------------------
    def _perguntar(self, texto: str, padrao=None) -> str:
        sufixo = f" [{padrao}]" if padrao not in (None, "", []) else ""
        resposta = _limpo(self.entrada(f"{texto}{sufixo}: "))
        return resposta if resposta else ("" if padrao is None else str(padrao))

    def _sim_nao(self, texto: str, padrao: bool = False) -> bool:
        return self._perguntar(f"{texto} (s/n)", "s" if padrao else "n").lower().startswith("s")

    def _valor(self, p: Parametro):
        """Pergunta um parametro; devolve o valor (None = nao informado)."""
        while True:
            if p.tipo == "opcao":
                for i, o in enumerate(p.opcoes, 1):
                    self.saida(f"   {i}) {o}")
                r = self._perguntar(p.pergunta, p.padrao)
                r = p.opcoes[int(r) - 1] if r.isdigit() and 1 <= int(r) <= len(p.opcoes) else r
                if r in p.opcoes:
                    return r
                self.saida("   Opcao invalida.")
            elif p.tipo == "bool":
                return self._sim_nao(p.pergunta, bool(p.padrao))
            elif p.tipo == "lista_int":
                r = self._perguntar(p.pergunta, p.padrao)
                try:
                    return [int(x) for x in r.replace(",", " ").split()] if r and r != "[]" else []
                except ValueError:
                    self.saida("   Use apenas numeros.")
            else:
                r = self._perguntar(p.pergunta, p.padrao)
                if r:
                    return r
                if not p.obrigatorio:
                    return None
                self.saida("   Campo obrigatorio.")

    def _numeros(self, texto: str, padrao: str, maximo: int) -> list[int] | None:
        """Le numeros (1..maximo, sem repetir) na ordem digitada. None = nenhum."""
        while True:
            r = self._perguntar(texto, padrao)
            if not r:
                return None
            try:
                idx = [int(x) for x in r.replace(",", " ").split()]
                if idx and all(1 <= i <= maximo for i in idx) and len(set(idx)) == len(idx):
                    return idx
            except ValueError:
                pass
            self.saida("   Escolha invalida (use os numeros da lista, sem repetir).")

    # -- etapas -------------------------------------------------------------
    def _escolher_estudo(self):
        ids = est.listar_estudos(self.pasta_estudos)
        if not ids:
            self.saida(f"Nenhum estudo em {self.pasta_estudos.name}/. "
                       f"Crie {self.pasta_estudos.name}/<ID>/<deck>/ (veja o README).")
            return None
        self.saida("Estudos encontrados: " + ", ".join(ids))
        while True:
            escolha = self._perguntar("ID do estudo (Enter para sair)", ids[0] if len(ids) == 1 else None)
            if not escolha:
                return None
            if escolha in ids:
                return escolha
            self.saida(f"   Estudo {escolha!r} nao encontrado.")

    def _mostrar_decks(self, encontrados, ignoradas) -> None:
        self.saida("\nDecks encontrados:")
        for i, d in enumerate(encontrados, 1):
            info = f"{d.deck.tipo.upper()} | mes-alvo {_fmt_mes(d.mes_alvo)}"
            if d.deck.tem("dger"):
                g = ler_dger(d.deck.caminho("dger"))
                info += f" | inicio no dger {g.mes_inicio:02d}/{g.ano_inicio} | origem {g.origem.upper()}"
            elif d.deck.revisao:
                info += f" | revisao {d.deck.revisao}"
            self.saida(f"  {i}) {d.pasta.name}  [{info}]")
        for nome in ignoradas:
            self.saida(f"  (ignorada, nao e' deck: {nome})")

    def _escolher_decks(self, encontrados):
        if len(encontrados) == 1:
            return list(encontrados)
        idx = self._numeros("Quais decks processar? (Enter = todos)", "", len(encontrados))
        return list(encontrados) if idx is None else [encontrados[i - 1] for i in idx]

    def _sugestoes(self, grupo, alteracoes):
        """{(alteracao, pasta do deck): (sugerida, motivo)}"""
        sug = {}
        for d in grupo:
            ctx = Contexto(d.deck, d.mes_alvo, est.externos_padrao(d.pasta, d.mes_alvo, self.pasta_cvu))
            for a in alteracoes:
                sug[(a.nome, d.pasta.name)] = avaliar_aplicabilidade(a, ctx)
        return sug

    def _configurar_grupo(self, tipo: str, grupo, decks_entrada: list) -> None:
        alteracoes = [a for a in REGISTRO.values() if tipo in a.modelos]
        sug = self._sugestoes(grupo, alteracoes)
        self.saida(f"\n=== Alteracoes para decks {tipo.upper()}: {', '.join(d.pasta.name for d in grupo)} ===")
        for i, a in enumerate(alteracoes, 1):
            self.saida(f"  {i}) {a.nome} - {a.descricao}")
            for d in grupo:
                ok, motivo = sug[(a.nome, d.pasta.name)]
                self.saida(f"       {d.pasta.name}: {'SUGERIDA' if ok else 'nao sugerida'} - {motivo}")
        padrao = " ".join(str(i) for i, a in enumerate(alteracoes, 1)
                          if any(sug[(a.nome, d.pasta.name)][0] for d in grupo))
        idx = self._numeros("Quais aplicar? Numeros na ordem desejada (Enter = as sugeridas)", padrao, len(alteracoes))
        if not idx:
            self.saida(f"   Nenhuma alteracao escolhida para os decks {tipo.upper()}.")
            return
        escolhidas = [alteracoes[i - 1] for i in idx]

        params: dict[str, dict] = {}
        for a in escolhidas:
            perguntas = [p for p in a.parametros if p.perguntar and not p.externo]
            if perguntas:
                self.saida(f"\n-- {a.nome}")
            for p in perguntas:
                v = self._valor(p)
                if v is not None:
                    params.setdefault(a.nome, {})[p.nome] = v

        for d in grupo:
            aplicar = []
            for a in escolhidas:
                ok, motivo = sug[(a.nome, d.pasta.name)]
                if ok or self._sim_nao(
                        f"\n'{a.nome}' nao e' sugerida para {d.pasta.name} ({motivo}). Aplicar mesmo assim?", False):
                    aplicar.append(a.nome)
            if aplicar:
                decks_entrada.append({
                    "deck": self._caminho_relativo(d.pasta), "mes_alvo": est.formatar_mes(d.mes_alvo),
                    "alteracoes": aplicar, "params": {n: params[n] for n in aplicar if n in params}})

    @staticmethod
    def _caminho_relativo(pasta: Path) -> str:
        try:
            return pasta.resolve().relative_to(est.RAIZ_PROJETO.resolve()).as_posix()
        except ValueError:
            return str(pasta)

    def _resumo(self, estudo: dict) -> None:
        self.saida(f"\n=== Resumo da rodada (estudo {estudo['estudo']}) ===")
        for d in estudo["decks"]:
            self.saida(f"{Path(d['deck']).name}  (mes-alvo {d['mes_alvo'] or '-'}): " + " -> ".join(d["alteracoes"]))
            for nome, ps in d["params"].items():
                self.saida(f"     {nome}: {ps}")

    def executar(self):
        """Roda uma rodada. Devolve o ResultadoEstudo ou None se cancelada."""
        self.saida("=== Rodadas-Geral ===")
        estudo_id = self._escolher_estudo()
        if estudo_id is None:
            return None
        encontrados, ignoradas = est.descobrir_decks(self.pasta_estudos / estudo_id)
        if not encontrados:
            self.saida(f"Nenhum deck NEWAVE/DECOMP dentro de {self.pasta_estudos.name}/{estudo_id}/.")
            return None
        self._mostrar_decks(encontrados, ignoradas)
        selecionados = self._escolher_decks(encontrados)

        decks_entrada: list[dict] = []
        for tipo in ("newave", "decomp"):
            grupo = [d for d in selecionados if d.deck.tipo == tipo]
            if grupo:
                self._configurar_grupo(tipo, grupo, decks_entrada)
        if not decks_entrada:
            self.saida("\nNenhuma alteracao a aplicar. Nada foi feito.")
            return None

        estudo = {"estudo": estudo_id, "decks": decks_entrada}
        self._resumo(estudo)
        if not self._sim_nao("\nExecutar agora?", True):
            self.saida("Cancelado.")
            return None
        try:
            resultado = est.rodar_estudo(estudo, self.raiz_saidas, pasta_cvu=self.pasta_cvu)
        except Exception as e:  # noqa: BLE001 - mostra ao usuario
            self.saida(f"\n[ERRO] {e}")
            return None

        self.saida("\n=== Resultado ===")
        for d in resultado.decks:
            self.saida(f"\n{d.deck}:")
            if d.erro:
                self.saida(f"   [ERRO] {d.erro}")
            for r in d.resultados:
                self.saida(f"   {'ALTEROU ' if r.alterou else 'sem alteracao'} {r.alteracao}")
                for aviso in r.avisos:
                    self.saida(f"        aviso: {aviso}")
        self.saida(f"\nDecks alterados e log em: {resultado.pasta}")
        self.saida("Para repetir esta rodada: python main.py estudo \"" + str(resultado.pasta / "estudo.json") + "\"")
        return resultado


def executar_menu() -> None:
    Menu().executar()
