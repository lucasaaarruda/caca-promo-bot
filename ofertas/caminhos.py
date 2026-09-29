"""Caminhos do projeto. Módulo sem dependências, para config/db/canais/nichos não formarem ciclo de import."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("OFERTAS_DATA_DIR") or BASE_DIR / "data")  # override: testes e ensaios
DATA_DIR.mkdir(parents=True, exist_ok=True)
