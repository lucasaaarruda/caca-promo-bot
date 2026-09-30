"""Rodízio justo entre canais: cada canal tem a sua cota de consultas por rodada.

Sem isso, um canal grande (30 categorias) empurra um pequeno (1 categoria) para o fim da fila e ele só
seria consultado a cada 3 rodadas. Aqui, o pequeno é consultado TODA rodada e o grande gira no resto."""

_indices: dict[tuple, int] = {}


def repartir(tamanhos: list[int], orcamento: int) -> list[int]:
    """Quanto cada grupo consulta por rodada: divide o orçamento por igual; o que sobra de um grupo
    pequeno vai para os grandes. Ex.: tamanhos [30, 1], orçamento 12 -> [11, 1]."""
    quotas = [0] * len(tamanhos)
    abertos = list(range(len(tamanhos)))
    while abertos and orcamento > 0:
        cota = max(1, orcamento // len(abertos))
        ainda = []
        deu_algo = False
        for i in abertos:
            dar = min(cota, tamanhos[i] - quotas[i], orcamento)
            if dar > 0:
                quotas[i] += dar
                orcamento -= dar
                deu_algo = True
            if quotas[i] < tamanhos[i]:
                ainda.append(i)
        if not deu_algo:
            break
        abertos = ainda
    return quotas


def escolher(listas: list[list], orcamento: int, namespace: str) -> list:
    """Itens da rodada: de cada lista, a fatia da sua cota, girando a cada chamada (com volta ao início).
    Itens repetidos entre listas aparecem uma vez só."""
    quotas = repartir([len(lista) for lista in listas], orcamento)
    saida, vistos = [], set()
    for i, (lista, quota) in enumerate(zip(listas, quotas)):
        if quota <= 0:
            continue
        chave = (namespace, i)
        inicio = _indices.get(chave, 0) % len(lista)
        _indices[chave] = inicio + quota
        for item in (lista + lista)[inicio:inicio + quota]:
            if item not in vistos:
                vistos.add(item)
                saida.append(item)
    return saida
