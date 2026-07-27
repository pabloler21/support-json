from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # Cargar variables de entorno desde el archivo .env

MODEL = os.getenv("MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 100))
OPEN_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPEN_API_KEY)

