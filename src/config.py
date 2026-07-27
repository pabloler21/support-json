"""Configuración del proyecto: carga variables de entorno y expone constantes.

Este módulo NO crea clientes ni ejecuta lógica: solo lee valores. Así puede
importarse desde cualquier parte (incluidos los tests) sin necesitar una API key.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # Cargar variables de entorno desde el archivo .env

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = os.getenv("MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "100"))

# Precios en USD por cada 1M de tokens (gpt-4o-mini).
# Input y output se cobran distinto, por eso van separados: metrics.py necesita
# los dos para calcular estimated_cost_usd.
INPUT_COST_PER_1M_TOKENS = float(os.getenv("INPUT_COST_PER_1M_TOKENS", "0.15"))
OUTPUT_COST_PER_1M_TOKENS = float(os.getenv("OUTPUT_COST_PER_1M_TOKENS", "0.60"))
