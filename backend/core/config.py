import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EXPORT_ROOT = PROJECT_ROOT / "backend" / "exports"
TEMPLATE_DIR = EXPORT_ROOT / "templates"
OUTPUT_DIR = EXPORT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def env_str(name: str, default: str | None = None) -> str | None:
	return os.getenv(name, default)


@lru_cache(maxsize=1)
def sqlite_path() -> Path:
	custom = env_str("LATTES_SQLITE_PATH")
	if custom:
		return Path(custom).expanduser().resolve()
	return (DATA_DIR / "lattes.sqlite3").resolve()

