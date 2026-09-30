from dataclasses import dataclass


@dataclass
class Oferta:
    plataforma: str            # "mercadolivre" | "shopee" | "amazon"
    id_produto: str
    titulo: str
    url_afiliado: str          # vazio até o link de afiliado ser gerado
    url_produto: str = ""
    preco: float | None = None
    preco_original: float | None = None
    desconto_pct: int | None = None
    imagem: str | None = None
    extra: str | None = None   # avaliação, frete grátis, "no Pix" etc.
    nota: float | None = None  # avaliação média (0-5), quando a fonte informa
    vendas: int | None = None  # unidades vendidas, quando a fonte informa
    cupom: str | None = None   # código de cupom a digitar (informado por você no conversor)
    mais_vendido: bool = False # veio da lista de mais vendidos da categoria (API do ML)
    categoria: str | None = None  # categoria de origem no ML (id), quando a fonte informa

    @property
    def uid(self) -> str:
        return f"{self.plataforma}:{self.id_produto}"

    @property
    def desconto(self) -> int | None:
        if self.desconto_pct:
            return self.desconto_pct
        if self.preco and self.preco_original and self.preco_original > self.preco:
            return round(100 * (1 - self.preco / self.preco_original))
        return None
