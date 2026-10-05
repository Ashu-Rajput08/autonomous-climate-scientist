from pathlib import Path
import os

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_PATH = Path(os.getenv("CLIMATE_DATA_PATH", PROJECT_ROOT / "open-meteo-21.97N78.98E696m.csv"))
TIMEZONE = "Asia/Kolkata"
MODEL_NAME = os.getenv("CLIMATE_AGENT_MODEL", "gpt-4o-mini")
