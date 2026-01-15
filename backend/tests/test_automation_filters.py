import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backend.core import config
from backend.services.automation import (
    CVAutomation,
    EXPERIENCE_WINDOW_YEARS,
    PRODUCTION_WINDOW_YEARS,
)


class AutomationFilteringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "automation.sqlite3"
        self.output_dir = Path(self.temp_dir.name) / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.reference_year = datetime.utcnow().year
        self.previous_env = os.environ.get("LATTES_SQLITE_PATH")
        os.environ["LATTES_SQLITE_PATH"] = str(self.db_path)
        config.sqlite_path.cache_clear()

        self._seed_database()
        self.addCleanup(self._restore_environment)

    def _restore_environment(self) -> None:
        if self.previous_env is None:
            os.environ.pop("LATTES_SQLITE_PATH", None)
        else:
            os.environ["LATTES_SQLITE_PATH"] = self.previous_env
        config.sqlite_path.cache_clear()

    def _seed_database(self) -> None:
        recent_experience_start = str(self.reference_year - 1)
        recent_experience_end = str(self.reference_year)
        old_experience_start = str(self.reference_year - EXPERIENCE_WINDOW_YEARS - 3)
        old_experience_end = str(self.reference_year - EXPERIENCE_WINDOW_YEARS - 1)

        recent_production_year = str(self.reference_year - 1)
        old_production_year = str(self.reference_year - PRODUCTION_WINDOW_YEARS - 2)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE base_de_dados_docente (
                    id TEXT PRIMARY KEY,
                    nome_padrao TEXT,
                    email TEXT,
                    nacionalidade TEXT,
                    area TEXT,
                    nova_area TEXT,
                    unid_acad TEXT,
                    carreira TEXT,
                    carreira_en TEXT,
                    core_non_core TEXT,
                    vertente TEXT,
                    regime TEXT,
                    v_nculo TEXT,
                    qualif_descricao_2026_2027 TEXT,
                    engajamento_descricao TEXT,
                    admissao TEXT,
                    tit_maxima TEXT,
                    time_mission TEXT,
                    fte TEXT,
                    ch_total_ano_vigente TEXT,
                    titulo_valido_brasil TEXT,
                    exp_prof TEXT,
                    exp_int TEXT,
                    ch_ed_ex_ano_vigente TEXT,
                    aacsb_2025 TEXT,
                    aloca_o_2025 TEXT,
                    t_dout_en TEXT,
                    t_dout_ies TEXT,
                    t_dout_ano TEXT,
                    t_dout_pais_en TEXT,
                    t_mestrado_en TEXT,
                    t_mestrado_ies TEXT,
                    t_mestrado_ano TEXT,
                    t_mestrado_pais_en TEXT,
                    scholar TEXT,
                    scopus TEXT,
                    orcid TEXT,
                    lattes TEXT,
                    linkedin TEXT,
                    site_pessoal TEXT
                )
                """
            )

            conn.execute(
                """
                INSERT INTO base_de_dados_docente (
                    id,
                    nome_padrao,
                    email,
                    nacionalidade,
                    area,
                    nova_area,
                    unid_acad,
                    carreira,
                    carreira_en,
                    core_non_core,
                    vertente,
                    regime,
                    v_nculo,
                    qualif_descricao_2026_2027,
                    engajamento_descricao,
                    admissao,
                    tit_maxima,
                    time_mission,
                    fte,
                    ch_total_ano_vigente,
                    titulo_valido_brasil,
                    exp_prof,
                    exp_int,
                    ch_ed_ex_ano_vigente,
                    aacsb_2025,
                    aloca_o_2025,
                    t_dout_en,
                    t_dout_ies,
                    t_dout_ano,
                    t_dout_pais_en,
                    t_mestrado_en,
                    t_mestrado_ies,
                    t_mestrado_ano,
                    t_mestrado_pais_en,
                    scholar,
                    scopus,
                    orcid,
                    lattes,
                    linkedin,
                    site_pessoal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "123",
                    "Jane Doe",
                    "jane@example.com",
                    "Brazil",
                    "FIN",
                    "Finance",
                    "M&E",
                    "Professor",
                    "Professor",
                    "Core",
                    "Vertente",
                    "Full",
                    "Permanent",
                    "Qualification",
                    "Engagement",
                    str(self.reference_year - 10),
                    "PhD",
                    "Mission",
                    "1.0",
                    "40",
                    "Yes",
                    "Experience summary",
                    "International",
                    "20",
                    "Y",
                    "Tag",
                    "Doctorate",
                    "Institution",
                    str(self.reference_year - 4),
                    "Country",
                    "Masters",
                    "Institution",
                    str(self.reference_year - 7),
                    "Country",
                    "Scholar",
                    "Scopus",
                    "Orcid",
                    "http://lattes.example/123",
                    "LinkedIn",
                    "Site",
                ),
            )

            conn.execute(
                """
                CREATE TABLE docentes_experiencia_profissional (
                    id TEXT,
                    cargo_role TEXT,
                    empresa_company TEXT,
                    cidade_city TEXT,
                    pa_s_country TEXT,
                    categoria_prof_res_tch TEXT,
                    in_cio TEXT,
                    fim TEXT,
                    idioma TEXT
                )
                """
            )

            conn.executemany(
                """
                INSERT INTO docentes_experiencia_profissional (
                    id,
                    cargo_role,
                    empresa_company,
                    cidade_city,
                    pa_s_country,
                    categoria_prof_res_tch,
                    in_cio,
                    fim,
                    idioma
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "123",
                        "Recent Role",
                        "Recent Org",
                        "Sao Paulo",
                        "Brazil",
                        "Academic",
                        recent_experience_start,
                        recent_experience_end,
                        "EN",
                    ),
                    (
                        "123",
                        "Old Role",
                        "Old Org",
                        "Rio",
                        "Brazil",
                        "Academic",
                        old_experience_start,
                        old_experience_end,
                        "EN",
                    ),
                ],
            )

            conn.execute(
                """
                CREATE TABLE docentes_producao (
                    professor TEXT,
                    ano TEXT,
                    t_tulo TEXT,
                    tipo TEXT,
                    ve_culo_ou_natureza TEXT,
                    classifica_o TEXT,
                    revis_o TEXT,
                    status_savi TEXT,
                    status_biblioteca TEXT,
                    fonte_da_evid_ncia TEXT,
                    informa_o_cv_lattes TEXT
                )
                """
            )

            conn.executemany(
                """
                INSERT INTO docentes_producao (
                    professor,
                    ano,
                    t_tulo,
                    tipo,
                    ve_culo_ou_natureza,
                    classifica_o,
                    revis_o,
                    status_savi,
                    status_biblioteca,
                    fonte_da_evid_ncia,
                    informa_o_cv_lattes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "Jane Doe",
                        recent_production_year,
                        "Recent Publication",
                        "Article",
                        "Journal",
                        "A1",
                        "Yes",
                        "Published",
                        "Library",
                        "Evidence",
                        "Info",
                    ),
                    (
                        "Jane Doe",
                        old_production_year,
                        "Legacy Publication",
                        "Article",
                        "Journal",
                        "B2",
                        "No",
                        "Published",
                        "Library",
                        "Evidence",
                        "Info",
                    ),
                ],
            )
            conn.commit()

    def test_profile_filters_recent_items(self) -> None:
        automation = CVAutomation(output_root=self.output_dir)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = automation._build_profile(conn, "123")

        self.assertIsNotNone(profile)
        self.assertEqual([entry.role for entry in profile.experiences], ["Recent Role"])
        self.assertEqual([entry.title for entry in profile.productions], ["Recent Publication"])


if __name__ == "__main__":
    unittest.main()
