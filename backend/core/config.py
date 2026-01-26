"""Configuração centralizada de caminhos, variáveis de ambiente e engine SQLAlchemy."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EXPORT_ROOT = PROJECT_ROOT / "backend" / "exports"
TEMPLATE_DIR = EXPORT_ROOT / "templates"
OUTPUT_DIR = EXPORT_ROOT / "output"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)


def env_str(name: str, default: str | None = None) -> str | None:
	"""Obtém uma variável de ambiente como string, retornando o padrão quando ausente."""
	return os.getenv(name, default)


@lru_cache(maxsize=1)
def sqlite_path() -> Path:
	"""Resolve o caminho absoluto do banco SQLite, permitindo sobrescrita via variável."""
	custom = env_str("LATTES_SQLITE_PATH")
	if custom:
		return Path(custom).expanduser().resolve()
	return (DATA_DIR / "lattes.sqlite3").resolve()


def _normalize_database_url(raw: str) -> str:
	"""Garante que URLs Postgres utilizem o driver psycopg ao montar a string de conexão."""
	value = raw.strip()
	if value.startswith("postgresql+psycopg://"):
		return value
	if value.startswith("postgresql://"):
		return "postgresql+psycopg://" + value[len("postgresql://") :]
	if value.startswith("postgres://"):
		return "postgresql+psycopg://" + value[len("postgres://") :]
	return value


@lru_cache(maxsize=1)
def database_url() -> str:
	"""Retorna a URL de conexão ativa, priorizando variáveis e caindo para SQLite."""
	override = env_str("DATABASE_URL") or env_str("SERVICE_URI")
	if override:
		return _normalize_database_url(override)
	default_path = sqlite_path()
	return f"sqlite:///{default_path.as_posix()}"


@lru_cache(maxsize=1)
def database_engine() -> Engine:
	"""Instancia o engine SQLAlchemy compartilhado com parâmetros seguros para SQLite."""
	url = database_url()
	connect_args: dict[str, object] = {}
	if url.startswith("sqlite:"):
		connect_args["check_same_thread"] = False
	return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def reset_database_caches() -> None:
	"""Limpa caches para forçar a reavaliação de caminhos e engine em tempo de execução."""
	sqlite_path.cache_clear()
	database_url.cache_clear()
	database_engine.cache_clear()

