import io
import os
import sqlite3
import sys
import tempfile
import unittest
from importlib import import_module, reload
from pathlib import Path

from backend.core import config, database
import backend.services.automation as automation_module


class ApiEndpointTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = Path(self._tmpdir.name) / "api.sqlite3"

        self._previous_database_url = os.environ.get("DATABASE_URL")
        self._previous_service_uri = os.environ.get("SERVICE_URI")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path.as_posix()}"
        os.environ.pop("SERVICE_URI", None)

        self._previous_env = os.environ.get("LATTES_SQLITE_PATH")
        os.environ["LATTES_SQLITE_PATH"] = str(self.db_path)
        config.reset_database_caches()

        self._original_data_dir = database.DATA_DIR
        database.DATA_DIR = Path(self._tmpdir.name)

        self._original_specs = database.CSV_SPECS
        self.sample_spec = {
            "filename": "test_table.csv",
            "table": "test_table",
            "skip_rows": 0,
            "merge_strategy": "replace",
            "aliases": ["test_alias"],
        }
        database.CSV_SPECS = [self.sample_spec]

        self._original_maps = (database._TABLE_BY_KEY, database._TABLE_BY_ALIAS)
        database._TABLE_BY_KEY, database._TABLE_BY_ALIAS = database._build_alias_lookup()

        dataset_path = database.DATA_DIR / self.sample_spec["filename"]
        dataset_path.write_text("id,name\n", encoding="utf-8")

        reload(automation_module)
        if "app" in sys.modules:
            self.app_module = reload(sys.modules["app"])
        else:
            self.app_module = import_module("app")
        self.client = self.app_module.app.test_client()
        if hasattr(self.app_module, "automation_service"):
            self.app_module.automation_service.invalidate_cache()

        self.addCleanup(self._cleanup_environment)

    def _cleanup_environment(self) -> None:
        if self._previous_env is None:
            os.environ.pop("LATTES_SQLITE_PATH", None)
        else:
            os.environ["LATTES_SQLITE_PATH"] = self._previous_env
        if self._previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._previous_database_url
        if self._previous_service_uri is None:
            os.environ.pop("SERVICE_URI", None)
        else:
            os.environ["SERVICE_URI"] = self._previous_service_uri
        database.CSV_SPECS = self._original_specs
        database.DATA_DIR = self._original_data_dir
        database._TABLE_BY_KEY, database._TABLE_BY_ALIAS = self._original_maps
        config.reset_database_caches()
        if hasattr(self.app_module, "automation_service"):
            self.app_module.automation_service.invalidate_cache()


class TablesUploadEndpointTests(ApiEndpointTestCase):
    def test_upload_succeeds_with_valid_payload(self) -> None:
        response = self.client.post(
            "/tables/test_table/upload",
            data={"file": (io.BytesIO(b"id,name\n1,Ana\n"), "payload.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("table"), "test_table")
        self.assertEqual(payload.get("rows"), 1)
        self.assertEqual(payload.get("columns"), ["id", "name"])

        with sqlite3.connect(self.db_path) as conn:
            rows = list(conn.execute('SELECT id, name FROM "test_table" ORDER BY id'))
        self.assertEqual(rows, [("1", "Ana")])

    def test_upload_rejects_unexpected_columns(self) -> None:
        response = self.client.post(
            "/tables/test_table/upload",
            data={"file": (io.BytesIO(b"id,extra\n1,X\n"), "payload.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json() or {}
        self.assertIn("Colunas", payload.get("error", ""))


class SummaryEndpointTests(ApiEndpointTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed_database()
        self.app_module.automation_service.invalidate_cache()

    def _seed_database(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE base_de_dados_docente (
                    id TEXT,
                    nome_padrao TEXT,
                    area TEXT,
                    nova_area TEXT,
                    unid_acad TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO base_de_dados_docente (id, nome_padrao, area, nova_area, unid_acad) VALUES (?, ?, ?, ?, ?)",
                [
                    ("1", "Jane Doe", "FIN", "Finance", "M&E"),
                    ("2", "John Roe", "ECO", "Economics", "LAW"),
                ],
            )

            conn.execute(
                """
                CREATE TABLE alocacao_2026_1_reldetalhe (
                    nome_completo TEXT,
                    disciplina TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO alocacao_2026_1_reldetalhe (nome_completo, disciplina) VALUES (?, ?)",
                ("Jane Doe", "Advanced Finance"),
            )

            conn.execute(
                """
                CREATE TABLE alocacao_26_1 (
                    disciplina TEXT,
                    aacsb TEXT,
                    equis TEXT,
                    amba TEXT,
                    abet TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO alocacao_26_1 (disciplina, aacsb, equis, amba, abet) VALUES (?, ?, ?, ?, ?)",
                ("Advanced Finance", "SIM", "SIM", "NAO", "NAO"),
            )

            conn.execute(
                """
                CREATE TABLE faculty_photos (
                    faculty_id TEXT PRIMARY KEY,
                    image BLOB,
                    mime_type TEXT,
                    filename TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO faculty_photos (faculty_id, image, mime_type, filename, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("1", b"photo-bytes", "image/png", "photo.png", "2025-01-01T00:00:00Z"),
            )
            conn.commit()

    def test_summary_defaults_to_allocated_only(self) -> None:
        response = self.client.get("/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("total"), 1)
        self.assertEqual(payload.get("page"), 1)
        self.assertEqual(payload.get("pages"), 1)
        result = payload.get("result", [])
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry.get("id"), "1")
        self.assertEqual(entry.get("name"), "Jane Doe")
        self.assertTrue(entry.get("has_allocation"))
        self.assertTrue(entry.get("has_photo"))
        self.assertEqual(entry.get("accreditations"), ["AACSB", "EQUIS"])
        self.assertEqual(entry.get("area"), "Finance")

    def test_summary_includes_unallocated_when_requested(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM alocacao_26_1")
            conn.commit()
        self.app_module.automation_service.invalidate_cache()

        response = self.client.get("/summary?allocated_only=0")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("total"), 2)
        ids = {entry.get("id") for entry in payload.get("result", [])}
        self.assertSetEqual(ids, {"1", "2"})
        john = next(entry for entry in payload["result"] if entry["id"] == "2")
        self.assertFalse(john.get("has_allocation"))
        self.assertFalse(john.get("has_photo"))

    def test_summary_filters_by_accreditation_and_clamps_page(self) -> None:
        response = self.client.get("/summary?accreditation=EQUIS&per_page=1&page=5")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("total"), 1)
        self.assertEqual(payload.get("per_page"), 1)
        self.assertEqual(payload.get("pages"), 1)
        self.assertEqual(payload.get("page"), 1)
        self.assertEqual(len(payload.get("result", [])), 1)
        entry = payload["result"][0]
        self.assertEqual(entry.get("id"), "1")
        self.assertIn("EQUIS", entry.get("accreditations", []))


if __name__ == "__main__":
    unittest.main()
