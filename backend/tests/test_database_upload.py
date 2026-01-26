import os
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import pandas as pd

from backend.core import config, database


class ReloadTableUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp_dir.cleanup)
        self.base_path = Path(self.temp_dir.name)
        self.db_path = self.base_path / "test.sqlite3"

        self.sample_spec = {
            "filename": "test_table.csv",
            "table": "test_table",
            "skip_rows": 0,
            "aliases": ["test_alias"],
        }

        self.original_env = os.environ.get("LATTES_SQLITE_PATH")
        self.previous_database_url = os.environ.get("DATABASE_URL")
        self.previous_service_uri = os.environ.get("SERVICE_URI")
        self.original_csv_specs = database.CSV_SPECS
        self.original_data_dir = database.DATA_DIR
        self.original_maps = (database._TABLE_BY_KEY, database._TABLE_BY_ALIAS)

        canonical = "ID,Name\n1,Alpha\n"
        canonical_path = self.base_path / self.sample_spec["filename"]
        canonical_path.write_text(canonical, encoding="utf-8")

        os.environ["LATTES_SQLITE_PATH"] = str(self.db_path)
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path.as_posix()}"
        os.environ.pop("SERVICE_URI", None)
        config.reset_database_caches()
        database.CSV_SPECS = [self.sample_spec]
        database.DATA_DIR = self.base_path
        database._TABLE_BY_KEY, database._TABLE_BY_ALIAS = database._build_alias_lookup()

    def tearDown(self) -> None:
        if self.original_env is None:
            os.environ.pop("LATTES_SQLITE_PATH", None)
        else:
            os.environ["LATTES_SQLITE_PATH"] = self.original_env
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        if self.previous_service_uri is None:
            os.environ.pop("SERVICE_URI", None)
        else:
            os.environ["SERVICE_URI"] = self.previous_service_uri

        config.reset_database_caches()
        database.CSV_SPECS = self.original_csv_specs
        database.DATA_DIR = self.original_data_dir
        database._TABLE_BY_KEY, database._TABLE_BY_ALIAS = self.original_maps

    def _fetch_rows(self) -> list[tuple[str, ...]]:
        with sqlite3.connect(self.db_path) as conn:
            return list(
                conn.execute(f'SELECT * FROM "{self.sample_spec["table"]}" ORDER BY rowid')
            )

    def test_upload_inserts_rows_and_merges_updates(self) -> None:
        payload = "ID,Name\n1,Ana\n2,Bia\n".encode("utf-8")
        result = database.reload_table_from_upload(
            self.sample_spec["table"],
            payload,
            filename="upload.csv",
        )

        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["columns"], ["id", "name"])
        self.assertEqual(self._fetch_rows(), [("1", "Ana"), ("2", "Bia")])

        second_payload = "ID,Name\n2,Bela\n3,Caue\n".encode("utf-8")
        second = database.reload_table_from_upload(
            self.sample_spec["table"],
            second_payload,
            filename="upload.csv",
        )

        self.assertEqual(second["rows"], 4)
        self.assertEqual(second["added"], 2)
        rows = self._fetch_rows()
        self.assertIn(("2", "Bela"), rows)
        self.assertIn(("3", "Caue"), rows)

    def test_upload_rejects_missing_columns(self) -> None:
        payload = "ID\n1\n".encode("utf-8")
        with self.assertRaises(ValueError) as ctx:
            database.reload_table_from_upload(
                self.sample_spec["table"],
                payload,
                filename="missing.csv",
            )
        self.assertIn("Colunas", str(ctx.exception))

    def test_upload_rejects_unexpected_columns(self) -> None:
        payload = "ID,Name,Other\n1,Ana,X\n".encode("utf-8")
        with self.assertRaises(ValueError) as ctx:
            database.reload_table_from_upload(
                self.sample_spec["table"],
                payload,
                filename="extra.csv",
            )
        self.assertIn("reconhecidas", str(ctx.exception))

    def test_upload_rejects_empty_file(self) -> None:
        with self.assertRaises(ValueError):
            database.reload_table_from_upload(
                self.sample_spec["table"],
                b"",
                filename="empty.csv",
            )

    def test_upload_rejects_wrong_extension(self) -> None:
        payload = "ID,Name\n1,Ana\n".encode("utf-8")
        with self.assertRaises(ValueError):
            database.reload_table_from_upload(
                self.sample_spec["table"],
                payload,
                filename="invalid.txt",
            )

    def test_upload_handles_semicolon_delimiter(self) -> None:
        payload = "ID;Name\n4;Semi\n".encode("utf-8")
        outcome = database.reload_table_from_upload(
            self.sample_spec["table"],
            payload,
            filename="semi.csv",
        )
        self.assertEqual(outcome["rows"], 1)
        self.assertEqual(self._fetch_rows(), [("4", "Semi")])

    def test_upload_accepts_xlsx_input(self) -> None:
        buffer = BytesIO()
        pd.DataFrame([["5", "Excel"]], columns=["ID", "Name"]).to_excel(
            buffer,
            index=False,
        )
        outcome = database.reload_table_from_upload(
            self.sample_spec["table"],
            buffer.getvalue(),
            filename="upload.xlsx",
        )
        self.assertEqual(outcome["rows"], 1)
        self.assertEqual(self._fetch_rows(), [("5", "Excel")])

    def test_upload_accepts_alias_lookup(self) -> None:
        payload = "ID,Name\n1,Alias\n".encode("utf-8")
        result = database.reload_table_from_upload(
            "test_alias",
            payload,
            filename="alias.csv",
        )
        self.assertEqual(result["table"], self.sample_spec["table"])
        self.assertEqual(self._fetch_rows(), [("1", "Alias")])

    def test_unknown_table_key_is_rejected(self) -> None:
        payload = "ID,Name\n1,Ana\n".encode("utf-8")
        with self.assertRaises(ValueError) as ctx:
            database.reload_table_from_upload(
                "unknown",
                payload,
                filename="bad.csv",
            )
        self.assertIn("Tabela", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
