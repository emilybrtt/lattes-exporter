import csv
import re
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

import pandas as pd

from .config import DATA_DIR, sqlite_path

load_dotenv() # Carrega variáveis de ambiente
DB_PATH = sqlite_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

connection: sqlite3.Connection | None = None 
cursor: sqlite3.Cursor | None = None

# Lista qual arquivo CSV deve alimentar qual tabela no SQLite
CSV_SPECS = (
    {
        "filename": "base-de-dados-docente.csv",
        "table": "base_de_dados_docente",
        "skip_rows": 0,
    },
    {
        "filename": "docentes-experiencia-profissional.csv",
        "table": "docentes_experiencia_profissional",
        "skip_rows": 0,
    },
    {
        "filename": "producao_docentes_detalhado.csv",
        "table": "docentes_producao",
        "skip_rows": 1, # linha de metadados
    },
    {
        "filename": "alocacao_2026_1_reldetalhe.csv",
        "table": "alocacao_2026_1_reldetalhe",
        "skip_rows": 1,
        "aliases": [
            "alocacao_detalhe",
            "alocacao_relatorio",
            "alocacao_reldetalhe",
        ],
    },
    {
        "filename": "alocacao_26_1.csv",
        "table": "alocacao_26_1",
        "skip_rows": 0,
        "aliases": [
            "alocacao",
            "alocacao_matriz",
            "alocacao_selos",
        ],
    },
)

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx"}

def _build_alias_lookup() -> tuple[dict[str, dict], dict[str, dict]]:
    table_map: dict[str, dict] = {}
    alias_map: dict[str, dict] = {}
    for spec in CSV_SPECS:
        normalized_table = spec["table"].lower()
        table_map[normalized_table] = spec

        base_alias = spec["filename"].split(".")[0].replace("-", "_").lower()
        alias_map[base_alias] = spec

        for alias in spec.get("aliases", []):
            if not isinstance(alias, str):
                continue
            normalized_alias = alias.strip().lower().replace("-", "_")
            if not normalized_alias:
                continue
            alias_map.setdefault(normalized_alias, spec)

    return table_map, alias_map


_TABLE_BY_KEY, _TABLE_BY_ALIAS = _build_alias_lookup()


def _resolve_table_spec(raw_key: str) -> dict:
    """Resolves table metadata for uploads, accepting table or filename aliases."""
    normalized = (raw_key or "").strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("Tabela não informada.")
    spec = _TABLE_BY_KEY.get(normalized) or _TABLE_BY_ALIAS.get(normalized)
    if spec is None:
        valid = sorted(item["table"] for item in CSV_SPECS)
        raise ValueError(f"Tabela inválida. Utilize uma destas: {', '.join(valid)}.")
    return spec


def _prepare_rows(frame: pd.DataFrame) -> Iterable[tuple[str, ...]]:
    """Converts a dataframe to a sequence of UTF-8 safe string tuples."""
    cleaned = frame.fillna("")
    for row in cleaned.itertuples(index=False, name=None):
        yield tuple("" if value is None else str(value) for value in row)


def _read_csv_flexible(raw_bytes: bytes, skip_rows: int) -> pd.DataFrame:
    """Attempts to parse CSV bytes handling common delimiters automatically."""

    def _try_read(**kwargs: object) -> pd.DataFrame:
        stream = BytesIO(raw_bytes)
        return pd.read_csv(
            stream,
            skiprows=skip_rows,
            dtype=str,
            keep_default_na=False,
            **kwargs,
        )

    errors: list[str] = []

    try:
        frame = _try_read()
        if frame.shape[1] == 1:
            header = frame.columns[0]
            sample_text = "".join(frame.iloc[:3, 0].astype(str)) if not frame.empty else ""
            if any(delim in header or delim in sample_text for delim in (";", "\t", "|")):
                raise ValueError("single column with embedded delimiters")
        return frame
    except Exception as error:  # noqa: BLE001
        errors.append(f"default: {error}")

    for sep in (";", "\t", "|", ","):
        try:
            frame = _try_read(sep=sep)
            if frame.shape[1] == 1:
                continue
            return frame
        except Exception as error:  # noqa: BLE001
            errors.append(f"sep='{sep}': {error}")

    try:
        frame = _try_read(sep=None, engine="python")
        if frame.shape[1] > 1:
            return frame
    except Exception as error:  # noqa: BLE001
        errors.append(f"auto: {error}")

    raise ValueError(
        "Não foi possível ler o arquivo CSV com os delimitadores suportados. "
        + " | ".join(errors)
    )


def reload_table_from_upload(table_key: str, file_bytes: bytes, *, filename: str) -> dict:
    """Replaces one of the configured tables with data coming from CSV or XLSX uploads."""
    if not file_bytes:
        raise ValueError("Arquivo vazio.")

    spec = _resolve_table_spec(table_key)
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Formato não suportado. Envie um CSV ou XLSX.")

    skip_rows = spec.get("skip_rows", 0)

    try:
        if extension == ".csv":
            frame = _read_csv_flexible(file_bytes, skip_rows)
        else:
            buffer = BytesIO(file_bytes)
            frame = pd.read_excel(buffer, skiprows=skip_rows, dtype=str, engine="openpyxl")
    except Exception as error:  # noqa: BLE001
        raise ValueError(f"Falha ao ler o arquivo: {error}") from error

    columns = _sanitize_columns([str(column) for column in frame.columns])
    if not columns:
        raise ValueError("Nenhuma coluna foi encontrada no arquivo enviado.")

    frame.columns = columns
    rows = list(_prepare_rows(frame))

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        columns_sql = ", ".join(f'"{column}" TEXT' for column in columns)
        cur.execute(f'DROP TABLE IF EXISTS "{spec["table"]}"')
        cur.execute(f'CREATE TABLE "{spec["table"]}" ({columns_sql})')

        if rows:
            placeholders = ", ".join("?" for _ in columns)
            columns_list = ", ".join(f'"{column}"' for column in columns)
            cur.executemany(
                f'INSERT INTO "{spec["table"]}" ({columns_list}) VALUES ({placeholders})',
                rows,
            )

        conn.commit()

    return {
        "table": spec["table"],
        "rows": len(rows),
        "columns": columns,
        "source": filename,
    }


def _sanitize_columns(headers: list[str]) -> list[str]:
    """Transforma os nomes das colunas em identificadores simples para o SQLite."""
    cleaned = []
    seen: set[str] = set()
    for index, header in enumerate(headers):
        name = re.sub(r"[^0-9a-zA-Z]+", "_", header.strip().lower())
        name = name.strip("_") or f"column_{index + 1}"
        if name[0].isdigit():
            name = f"col_{name}"
        base = name
        counter = 1
        while name in seen:
            counter += 1
            name = f"{base}_{counter}"
        seen.add(name)
        cleaned.append(name)
    return cleaned


def _load_csv_into_table(
    cur: sqlite3.Cursor, csv_path: Path, table_name: str, skip_rows: int = 0
) -> None:
	"""Lê um CSV e insere seu conteúdo na tabela informada, pulando linhas extras se preciso."""
	if not csv_path.exists():
		print(f"Error loading {csv_path.name}: file not found.")
		return

	with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as handle:
		reader = csv.reader(handle)
		for _ in range(skip_rows):
			skipped = next(reader, None)
			if skipped is None:
				print(f"Error loading {csv_path.name}: unexpected end of file.")
				return

		headers = next(reader, None)
		if not headers:
			print(f"Error loading {csv_path.name}: empty file.")
			return

		columns = _sanitize_columns(headers)
		columns_sql = ", ".join(f'"{column}" TEXT' for column in columns)
		cur.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_sql})')

		cur.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1')
		if cur.fetchone():
			print(f"{table_name} already has data; skipping import.")
			return

		rows = []
		for row in reader:
			values = list(row[: len(columns)])
			if len(values) < len(columns):
				values.extend([""] * (len(columns) - len(values)))
			rows.append(values)

		if not rows:
			print(f"No rows found in {csv_path.name}.")
			return

		placeholders = ", ".join("?" for _ in columns)
		columns_list = ", ".join(f'"{column}"' for column in columns)
		cur.executemany(
			f'INSERT INTO "{table_name}" ({columns_list}) VALUES ({placeholders})',
			rows,
		)
		print(f"Inserted {len(rows)} rows into {table_name}.")


def initialize_database() -> None:
    """Carrega todos os CSVs configurados usando uma transação por arquivo"""
    if connection is None or cursor is None:
        print("Database connection is not available.")
        return

    for spec in CSV_SPECS:
        csv_path = DATA_DIR / spec["filename"]
        table_name = spec["table"]
        skip_rows = spec.get("skip_rows", 0)
        try:
            _load_csv_into_table(cursor, csv_path, table_name, skip_rows=skip_rows)
            connection.commit()
        except Exception as error:  # noqa: BLE001
            connection.rollback()
            print(f"Error loading {spec['filename']}: {error}")


try:
    """ Conexão com o banco de dados """
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    print(f"Connected to SQLite database at {DB_PATH}.")
    initialize_database()
except sqlite3.Error as error:
    print(f"SQLite connection error: {error}")
    connection = None
    cursor = None
