import csv
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from .config import DATA_DIR, database_engine, sqlite_path

load_dotenv() # Carrega variáveis de ambiente


def _engine():
    """Cria o engine e garante que a pasta do SQLite exista quando necessário."""
    engine = database_engine()
    if engine.dialect.name == "sqlite":
        sqlite_path().parent.mkdir(parents=True, exist_ok=True)
    return engine

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
        "strict_columns": False,
        "merge_strategy": "replace",
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
        "strict_columns": False,
        "merge_strategy": "replace",
        "aliases": [
            "alocacao",
            "alocacao_matriz",
            "alocacao_selos",
        ],
    },
)

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx"}
PHOTO_TABLE = "faculty_photos"


def _normalize_resource_name(name: str) -> str:
    """Normaliza nomes de arquivos para comparação insensível a formato."""
    return re.sub(r"[^0-9a-zA-Z]+", "", name).lower()


def _resolve_dataset_file(spec: dict) -> Path | None:
    """Localiza o arquivo configurado mesmo que o nome possua variações."""
    configured = DATA_DIR / spec["filename"]
    if configured.exists():
        return configured

    target_key = _normalize_resource_name(spec["filename"])
    for candidate in DATA_DIR.iterdir():
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
            continue
        if _normalize_resource_name(candidate.name) == target_key:
            return candidate
    return None

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
    """Resolve a configuração da tabela a partir do nome ou de apelidos aceitos."""
    normalized = (raw_key or "").strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("Tabela não informada.")
    spec = _TABLE_BY_KEY.get(normalized) or _TABLE_BY_ALIAS.get(normalized)
    if spec is None:
        valid = sorted(item["table"] for item in CSV_SPECS)
        raise ValueError(f"Tabela inválida. Utilize uma destas: {', '.join(valid)}.")
    return spec


def _load_expected_columns(spec: dict) -> list[str]:
    """Carrega nomes de colunas esperados tomando o CSV/XLSX padrão como referência."""
    data_path = _resolve_dataset_file(spec)
    if data_path is None:
        return []

    skip_rows = spec.get("skip_rows", 0)
    try:
        if data_path.suffix.lower() == ".csv":
            with data_path.open(mode="r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                for _ in range(skip_rows):
                    next(reader, None)
                headers = next(reader, None)
        else:
            frame = pd.read_excel(
                data_path,
                skiprows=skip_rows,
                dtype=str,
                engine="openpyxl",
                nrows=0,
            )
            headers = list(frame.columns)
    except Exception:  # noqa: BLE001
        return []

    if not headers:
        return []

    return _sanitize_columns([str(header) for header in headers])


def _prepare_rows(frame: pd.DataFrame) -> Iterable[tuple[str, ...]]:
    """Converte um DataFrame em tuplas de strings seguras para armazenamento."""
    cleaned = frame.fillna("")
    for row in cleaned.itertuples(index=False, name=None):
        yield tuple("" if value is None else str(value) for value in row)


def _read_csv_flexible(raw_bytes: bytes, skip_rows: int) -> pd.DataFrame:
    """Tenta interpretar um CSV detectando automaticamente delimitadores usuais."""

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


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier}"'


def _insert_rows(conn: Connection, table_name: str, columns: list[str], rows: list[tuple[str, ...]]) -> None:
    """Executa inserções em lote preservando a ordem das colunas sanitizadas."""
    if not rows:
        return
    param_names = [f"p{index}" for index in range(len(columns))]
    placeholders = ", ".join(f":{name}" for name in param_names)
    columns_sql = ", ".join(_quote_identifier(column) for column in columns)
    statement = text(
        f'INSERT INTO {_quote_identifier(table_name)} ({columns_sql}) VALUES ({placeholders})'
    )
    payload = [
        {param_names[index]: row[index] for index in range(len(columns))}
        for row in rows
    ]
    conn.execute(statement, payload)


def reload_table_from_upload(table_key: str, file_bytes: bytes, *, filename: str) -> dict:
    """Substitui a tabela configurada pelos dados enviados em CSV ou XLSX."""
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

    existing_frame: pd.DataFrame | None = None
    existing_columns: list[str] = []

    table_identifier = spec["table"]
    merge_strategy = spec.get("merge_strategy", "append").lower()
    enforce_schema = spec.get("strict_columns", True)

    engine = _engine()

    with engine.connect() as conn:
        try:
            existing_frame = pd.read_sql_query(
                text(f'SELECT * FROM {_quote_identifier(table_identifier)}'),
                conn,
            )
            if not existing_frame.empty:
                existing_frame = existing_frame.fillna("").astype(str)
            existing_columns = list(existing_frame.columns)
        except SQLAlchemyError:
            existing_frame = None
            existing_columns = []

    if merge_strategy == "replace":
        existing_frame = None
        existing_columns = []

    expected_columns = existing_columns or _load_expected_columns(spec)

    if expected_columns and enforce_schema:
        uploaded_set = set(columns)
        expected_set = set(expected_columns)
        missing = sorted(expected_set - uploaded_set)
        unexpected = sorted(uploaded_set - expected_set)
        if missing or unexpected:
            problems: list[str] = []
            if missing:
                problems.append("faltando: " + ", ".join(missing))
            if unexpected:
                problems.append("não reconhecidas: " + ", ".join(unexpected))
            details = "; ".join(problems)
            raise ValueError(
                "Colunas inválidas para a tabela "
                + spec["table"]
                + (f" ({details})." if details else ".")
            )
        ordered_columns = expected_columns
    else:
        ordered_columns = columns

    frame = frame.reindex(columns=ordered_columns, fill_value="")

    if existing_frame is not None:
        existing_frame = existing_frame.reindex(columns=ordered_columns, fill_value="")

    merged_upload = frame

    combined = (
        pd.concat([existing_frame, merged_upload], ignore_index=True) if existing_frame is not None else merged_upload
    )

    if not combined.empty:
        combined = combined.fillna("")
        combined = combined.drop_duplicates(keep="last")

    merged_rows = [
        tuple("" if value is None else str(value) for value in row)
        for row in combined.itertuples(index=False, name=None)
    ]

    with engine.begin() as conn:
        columns_sql = ", ".join(f'{_quote_identifier(column)} TEXT' for column in ordered_columns)
        conn.execute(text(f'DROP TABLE IF EXISTS {_quote_identifier(table_identifier)}'))
        conn.execute(text(f'CREATE TABLE {_quote_identifier(table_identifier)} ({columns_sql})'))
        _insert_rows(conn, table_identifier, ordered_columns, merged_rows)

    previous_count = len(existing_frame) if existing_frame is not None else 0
    return {
        "table": spec["table"],
        "rows": len(merged_rows),
        "columns": ordered_columns,
        "source": filename,
        "added": max(len(merged_rows) - previous_count, 0),
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
    conn: Connection, csv_path: Path, table_name: str, skip_rows: int = 0
) -> None:
    """Lê um CSV/XLSX e insere seu conteúdo na tabela informada, lidando com delimitadores flexíveis."""
    if not csv_path.exists():
        print(f"Error loading {csv_path.name}: file not found.")
        return

    extension = csv_path.suffix.lower()
    try:
        if extension == ".csv":
            frame = _read_csv_flexible(csv_path.read_bytes(), skip_rows)
        elif extension in {".xlsx", ".xls", ".xlsm"}:
            frame = pd.read_excel(
                csv_path,
                skiprows=skip_rows,
                dtype=str,
                engine="openpyxl",
            )
        else:
            print(f"Error loading {csv_path.name}: unsupported file extension {extension}.")
            return
    except Exception as error:  # noqa: BLE001
        print(f"Error loading {csv_path.name}: {error}")
        return

    if frame.empty:
        print(f"No rows found in {csv_path.name}.")
        return

    columns = _sanitize_columns([str(column) for column in frame.columns])
    frame.columns = columns

    columns_sql = ", ".join(f'{_quote_identifier(column)} TEXT' for column in columns)
    conn.execute(text(f'CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} ({columns_sql})'))

    if conn.execute(text(f'SELECT 1 FROM {_quote_identifier(table_name)} LIMIT 1')).first():
        print(f"{table_name} already has data; skipping import.")
        return

    prepared = frame.fillna("")
    rows = [
        tuple(str(value) for value in record)
        for record in prepared.itertuples(index=False, name=None)
    ]

    if not rows:
        print(f"No rows found in {csv_path.name}.")
        return

    _insert_rows(conn, table_name, columns, rows)
    print(f"Inserted {len(rows)} rows into {table_name}.")


def initialize_database() -> None:
    """Carrega todos os CSVs configurados usando uma transação por arquivo"""
    engine = _engine()

    for spec in CSV_SPECS:
        csv_path = _resolve_dataset_file(spec)
        if csv_path is None:
            print(f"Error loading {spec['filename']}: file not found.")
            continue
        table_name = spec["table"]
        skip_rows = spec.get("skip_rows", 0)
        try:
            with engine.begin() as conn:
                _load_csv_into_table(conn, csv_path, table_name, skip_rows=skip_rows)
        except Exception as error:  # noqa: BLE001
            print(f"Error loading {spec['filename']}: {error}")


def _ensure_photo_table(conn: Connection) -> None:
    binary_type = "BYTEA" if conn.dialect.name != "sqlite" else "BLOB"
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_quote_identifier(PHOTO_TABLE)} (
                faculty_id TEXT PRIMARY KEY,
                image {binary_type} NOT NULL,
                mime_type TEXT,
                filename TEXT,
                updated_at TEXT
            )
            """
        )
    )


def store_faculty_photo(
    faculty_id: str,
    *,
    content: bytes,
    mime_type: str,
    filename: str,
) -> dict:
    if not faculty_id or not faculty_id.strip():
        raise ValueError("Identificador do docente é obrigatório.")
    if not content:
        raise ValueError("Imagem vazia.")

    normalized_id = faculty_id.strip()
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    engine = _engine()

    with engine.begin() as conn:
        _ensure_photo_table(conn)
        conn.execute(
            text(
                f"""
                INSERT INTO {_quote_identifier(PHOTO_TABLE)} (faculty_id, image, mime_type, filename, updated_at)
                VALUES (:faculty_id, :image, :mime_type, :filename, :updated_at)
                ON CONFLICT (faculty_id) DO UPDATE SET
                    image = EXCLUDED.image,
                    mime_type = EXCLUDED.mime_type,
                    filename = EXCLUDED.filename,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "faculty_id": normalized_id,
                "image": content,
                "mime_type": mime_type,
                "filename": filename,
                "updated_at": timestamp,
            },
        )

    return {
        "faculty_id": normalized_id,
        "mime_type": mime_type,
        "filename": filename,
        "updated_at": timestamp,
    }


def fetch_faculty_photo(faculty_id: str) -> dict | None:
    if not faculty_id or not faculty_id.strip():
        return None

    normalized_id = faculty_id.strip()
    engine = _engine()

    with engine.connect() as conn:
        try:
            _ensure_photo_table(conn)
        except SQLAlchemyError:
            return None
        row = conn.execute(
            text(
                f"""
                SELECT faculty_id, image, mime_type, filename, updated_at
                FROM {_quote_identifier(PHOTO_TABLE)}
                WHERE faculty_id = :faculty_id
                """
            ),
            {"faculty_id": normalized_id},
        ).mappings().first()
    if row is None:
        return None
    image_value = row.get("image")
    image_bytes = bytes(image_value) if image_value is not None else None
    return {
        "faculty_id": row.get("faculty_id"),
        "image": image_bytes,
        "mime_type": row.get("mime_type"),
        "filename": row.get("filename"),
        "updated_at": row.get("updated_at"),
    }


if __name__ == "__main__":
	initialize_database()
