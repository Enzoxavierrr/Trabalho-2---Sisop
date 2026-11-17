# -*- coding: utf-8 -*-
"""
Módulo M1 — cache de blocos (buffer cache).

Referência: Silberschatz, 9ª ed., 13.4.3 (Caching) e 12.6 (Efficiency and Performance) — pesquisa.

Implementem CacheLRU e CacheFIFO com a interface abaixo. O simulador de E/S chama:

    ler(bloco) -> bool
        True se o bloco está na cache (acerto). Num acerto, a LRU atualiza a recência;
        a FIFO não muda nada.
    inserir(bloco) -> list[int]
        Chamado depois de uma falta de leitura, quando o bloco chega do disco. Se a cache
        estiver cheia, expulsa uma vítima (LRU: a usada há mais tempo; FIFO: a que entrou
        primeiro). Devolve os blocos SUJOS expulsos, que o simulador vai gravar no disco.
    escrever(bloco) -> list[int]
        Escrita do usuário. Coloca (ou atualiza) o bloco na cache e devolve a lista de blocos
        que precisam ser gravados no disco AGORA:
          write-through: o próprio bloco (+ sujos expulsos, que não existem nesta política);
          write-back:    só os blocos sujos expulsos; o bloco escrito fica marcado como sujo.
        Uma escrita conta como acesso para a LRU.
    sincronizar() -> list[int]
        Gravação periódica (a cada INTERVALO_SYNC_MS): devolve todos os blocos sujos e os
        marca como limpos.
    sujos() -> int
        Quantos blocos estão sujos agora (usado para medir a perda numa queda de energia).

Política de escrita: 'write-through' ou 'write-back'.
"""


from collections import OrderedDict


class Cache:
    nome = "?"

    def __init__(self, capacidade, escrita="write-back"):
        if escrita not in ("write-through", "write-back"):
            raise ValueError("escrita deve ser 'write-through' ou 'write-back'")
        self.capacidade = capacidade
        self.escrita = escrita

    def ler(self, bloco):
        raise NotImplementedError

    def inserir(self, bloco):
        raise NotImplementedError

    def escrever(self, bloco):
        raise NotImplementedError

    def sincronizar(self):
        raise NotImplementedError

    def sujos(self):
        raise NotImplementedError


class _CacheOrdenada(Cache):
    """Base comum: um OrderedDict bloco -> sujo, com a vítima sempre na ponta esquerda.
    LRU e FIFO só diferem em atualizar (ou não) a ordem quando o bloco é usado de novo."""
    atualiza_recencia = False

    def __init__(self, capacidade, escrita="write-back"):
        super().__init__(capacidade, escrita)
        self._blocos = OrderedDict()          # bloco -> True se sujo

    def _usar(self, bloco):
        if self.atualiza_recencia:
            self._blocos.move_to_end(bloco)

    def _colocar(self, bloco, sujo):
        """Põe um bloco novo, expulsando se estiver cheia. Devolve os sujos expulsos."""
        expulsos = []
        if self.capacidade <= 0:
            return expulsos
        while len(self._blocos) >= self.capacidade:
            vitima, estava_sujo = self._blocos.popitem(last=False)
            if estava_sujo:
                expulsos.append(vitima)
        self._blocos[bloco] = sujo
        return expulsos

    def ler(self, bloco):
        if bloco in self._blocos:
            self._usar(bloco)
            return True
        return False

    def inserir(self, bloco):
        if bloco in self._blocos:
            return []
        return self._colocar(bloco, False)

    def escrever(self, bloco):
        write_back = self.escrita == "write-back"
        if bloco in self._blocos:
            self._blocos[bloco] = write_back or self._blocos[bloco]
            self._usar(bloco)
            expulsos = []
        else:
            expulsos = self._colocar(bloco, write_back)
        if write_back:
            if self.capacidade <= 0:
                return [bloco]             # sem cache, a escrita vai direto ao disco
            return expulsos
        return [bloco] + expulsos

    def sincronizar(self):
        sujos = [b for b, sujo in self._blocos.items() if sujo]
        for b in sujos:
            self._blocos[b] = False
        return sujos

    def sujos(self):
        return sum(1 for sujo in self._blocos.values() if sujo)


class CacheLRU(_CacheOrdenada):
    """Expulsa o bloco usado há mais tempo: acertos e escritas atualizam a recência."""
    nome = "LRU"
    atualiza_recencia = True


class CacheFIFO(_CacheOrdenada):
    """Expulsa o bloco que entrou primeiro: usar o bloco de novo não muda a ordem."""
    nome = "FIFO"
    atualiza_recencia = False


CACHES = {"LRU": CacheLRU, "FIFO": CacheFIFO}


def criar_cache(nome, capacidade, escrita):
    try:
        return CACHES[nome](capacidade, escrita)
    except KeyError:
        raise ValueError("cache desconhecida: %s" % nome)
