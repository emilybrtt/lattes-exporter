import csv
import re
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

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
)


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
