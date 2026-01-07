from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document

from backend.core.config import OUTPUT_DIR, sqlite_path

logger = logging.getLogger("cv_automation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


ACCREDITATION_RULES = {
    "AACSB": {
        "version": "2025.1",
        "experience_years": 5,
        "max_experience": 8,
        "summary_limit": 1,
    },
    "EQUIS": {
        "version": "2025.1",
        "experience_years": 6,
        "max_experience": 10,
        "summary_limit": 1,
    },
    "AMBA": {
        "version": "2025.1",
        "experience_years": 5,
        "max_experience": 6,
        "summary_limit": 1,
    },
    "ABET": {
        "version": "2025.1",
        "experience_years": 7,
        "max_experience": 10,
        "summary_limit": 1,
    },
}

TEMPLATE_VERSION = "2025.01"


@dataclass
class EducationRecord:
    degree: str | None
    institution: str | None
    year: str | None
    country: str | None


@dataclass
class ExperienceEntry:
    role: str | None
    organization: str | None
    city: str | None
    country: str | None
    category: str | None
    start: datetime | None
    end: datetime | None

    def is_within_window(self, years: int, reference: datetime) -> bool:
        if self.start is None and self.end is None:
            return False
        cutoff = reference - timedelta(days=years * 365)
        effective_end = self.end or reference
        return effective_end >= cutoff


@dataclass
class ProductionEntry:
    year: str | None
    title: str | None
    production_type: str | None
    nature: str | None
    classification: str | None
    peer_review: str | None
    status_savi: str | None
    status_biblioteca: str | None
    evidence_source: str | None
    lattes_info: str | None

@dataclass
class FacultyProfile:
    faculty_id: str
    name: str
    email: str | None
    area: str | None
    specialization: str | None
    unit: str | None
    career: str | None
    career_en: str | None
    core_status: str | None
    vertente: str | None
    regime: str | None
    vinculo: str | None
    qualification_summary: str | None
    engagement_description: str | None
    admission_date: datetime | None
    highest_degree: str | None
    time_mission: str | None
    fte: str | None
    teaching_load: str | None
    executive_education_load: str | None
    title_valid_brazil: str | None
    accreditation_flag: str | None
    allocation_tag: str | None
    scholar_profile: str | None
    scopus_profile: str | None
    orcid: str | None
    lattes: str | None
    linkedin: str | None
    personal_site: str | None
    experience_summary: str | None
    international_experience: str | None
    education: list[EducationRecord]
    experiences: list[ExperienceEntry]
    productions: list[ProductionEntry]
    phd_title: str | None
    phd_institution: str | None
    phd_year: str | None
    phd_country: str | None
    masters_title: str | None
    masters_institution: str | None
    masters_year: str | None
    masters_country: str | None

    def to_serializable(self) -> dict:
        return {
            "faculty": {
                "id": self.faculty_id,
                "name": self.name,
                "email": self.email,
                "area": self.area,
                "specialization": self.specialization,
                "unit": self.unit,
                "career": self.career,
                "career_en": self.career_en,
                "core_status": self.core_status,
                "vertente": self.vertente,
                "regime": self.regime,
                "vinculo": self.vinculo,
                "qualification_summary": self.qualification_summary,
                "engagement_description": self.engagement_description,
                "admission_date": _format_date(self.admission_date),
                "highest_degree": self.highest_degree,
                "time_mission": self.time_mission,
                "fte": self.fte,
                "teaching_load": self.teaching_load,
                "executive_education_load": self.executive_education_load,
                "title_valid_brazil": self.title_valid_brazil,
                "aacsb_flag": self.accreditation_flag,
                "allocation": self.allocation_tag,
                "phd": {
                    "title": self.phd_title,
                    "institution": self.phd_institution,
                    "year": self.phd_year,
                    "country": self.phd_country,
                },
                "masters": {
                    "title": self.masters_title,
                    "institution": self.masters_institution,
                    "year": self.masters_year,
                    "country": self.masters_country,
                },
                "scholar": self.scholar_profile,
                "scopus": self.scopus_profile,
                "orcid": self.orcid,
                "lattes": self.lattes,
                "linkedin": self.linkedin,
                "personal_site": self.personal_site,
                "experience_summary": self.experience_summary,
                "international_experience": self.international_experience,
            },
            "education": [asdict(record) for record in self.education],
            "experience": [
                {
                    "role": entry.role,
                    "organization": entry.organization,
                    "city": entry.city,
                    "country": entry.country,
                    "category": entry.category,
                    "start": _format_date(entry.start),
                    "end": _format_date(entry.end),
                }
                for entry in self.experiences
            ],
            "production": [
                {
                    "year": entry.year,
                    "title": entry.title,
                    "type": entry.production_type,
                    "nature": entry.nature,
                    "classification": entry.classification,
                    "peer_review": entry.peer_review,
                    "status_savi": entry.status_savi,
                    "status_biblioteca": entry.status_biblioteca,
                    "evidence_source": entry.evidence_source,
                    "lattes_info": entry.lattes_info,
                }
                for entry in self.productions
            ],
        }
class CVAutomation:
    def __init__(self, output_root: Path = OUTPUT_DIR):
        self.db_path = sqlite_path()
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self, accreditation: str, faculty_ids: Sequence[str] | None = None) -> list[dict]:
        accreditation_key = accreditation.strip().upper()
        if accreditation_key not in ACCREDITATION_RULES:
            raise ValueError(f"Unsupported accreditation type: {accreditation}")

        rules = ACCREDITATION_RULES[accreditation_key]
        planned_ids = list(faculty_ids) if faculty_ids else self._fetch_all_ids()
        logger.info("Starting automation for %s with %d faculty", accreditation_key, len(planned_ids))

        metadata: list[dict] = []
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        accreditation_dir = self.output_root / accreditation_key.lower()
        accreditation_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for faculty_id in planned_ids:
                try:
                    profile = self._build_profile(conn, faculty_id)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to assemble data for faculty %s: %s", faculty_id, exc)
                    continue

                if profile is None:
                    logger.warning("Skipping faculty %s: no base record found", faculty_id)
                    continue

                filtered_experience = self._filter_experience(profile.experiences, rules)
                summarized_production = self._summarize_production(profile.productions, rules)
                limited_profile = replace(
                    profile,
                    experiences=filtered_experience,
                    productions=summarized_production,
                )

                docx_path = accreditation_dir / f"{faculty_id}_{_slugify(profile.name)}.docx"
                json_path = accreditation_dir / f"{faculty_id}_{_slugify(profile.name)}.json"

                try:
                    self._generate_document(limited_profile, accreditation_key, docx_path)
                    self._write_json(limited_profile, json_path)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to render CV for faculty %s: %s", faculty_id, exc)
                    continue

                metadata.append(
                    {
                        "faculty_id": faculty_id,
                        "name": profile.name,
                        "accreditation": accreditation_key,
                        "rule_version": rules["version"],
                        "template_version": TEMPLATE_VERSION,
                        "docx_path": str(docx_path.relative_to(self.output_root)),
                        "json_path": str(json_path.relative_to(self.output_root)),
                        "generated_at": timestamp,
                    }
                )
                logger.info("Generated CV for %s (%s)", profile.name, faculty_id)

        if metadata:
            log_path = accreditation_dir / f"run_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
            log_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            logger.info("Run summary written to %s", log_path)
        else:
            logger.warning("No CVs generated for %s", accreditation_key)

        return metadata

    def fetch_profile(self, faculty_id: str) -> dict | None:
        """Retorna o dicionário serializável de um docente específico."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                profile = self._build_profile(conn, faculty_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Falha ao recuperar dados do docente %s: %s",
                    faculty_id,
                    exc,
                )
                return None

        if profile is None:
            return None

        return profile.to_serializable()

    def fetch_all_profiles(self) -> list[dict]:
        """Retorna todos os docentes como uma lista de dicionários serializáveis."""
        faculty_ids = self._fetch_all_ids()
        if not faculty_ids:
            return []

        results: list[dict] = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for faculty_id in faculty_ids:
                try:
                    profile = self._build_profile(conn, faculty_id)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Falha ao recuperar dados do docente %s: %s",
                        faculty_id,
                        exc,
                    )
                    continue

                if profile is None:
                    continue

                results.append(profile.to_serializable())

        return results

    def _fetch_all_ids(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM base_de_dados_docente")
            return [str(row[0]) for row in cursor.fetchall()]

    def _build_profile(self, conn: sqlite3.Connection, faculty_id: str) -> FacultyProfile | None:
        faculty_row = conn.execute(
            """
            SELECT
                id,
                nome_padrao,
                email,
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
            FROM base_de_dados_docente
            WHERE id = ?
            """,
            (faculty_id,),
        ).fetchone()

        if faculty_row is None:
            return None

        experiences = list(self._load_experience(conn, faculty_row["id"]))
        education = _build_education_records(faculty_row)
        try:
            productions = list(self._load_production(conn, faculty_row["nome_padrao"]))
        except sqlite3.Error as exc:
            logger.warning(
                "Skipping production data for %s due to database error: %s",
                faculty_row["nome_padrao"],
                exc,
            )
            productions = []

        return FacultyProfile(
            faculty_id=str(faculty_row["id"]),
            name=faculty_row["nome_padrao"],
            email=faculty_row["email"],
            area=faculty_row["area"],
            specialization=faculty_row["nova_area"],
            unit=faculty_row["unid_acad"],
            career=faculty_row["carreira"],
            career_en=faculty_row["carreira_en"],
            core_status=faculty_row["core_non_core"],
            vertente=faculty_row["vertente"],
            regime=faculty_row["regime"],
            vinculo=faculty_row["v_nculo"],
            qualification_summary=faculty_row["qualif_descricao_2026_2027"],
            engagement_description=faculty_row["engajamento_descricao"],
            admission_date=_parse_date(faculty_row["admissao"]),
            highest_degree=faculty_row["tit_maxima"],
            time_mission=faculty_row["time_mission"],
            fte=faculty_row["fte"],
            teaching_load=faculty_row["ch_total_ano_vigente"],
            executive_education_load=faculty_row["ch_ed_ex_ano_vigente"],
            title_valid_brazil=faculty_row["titulo_valido_brasil"],
            accreditation_flag=faculty_row["aacsb_2025"],
            allocation_tag=faculty_row["aloca_o_2025"],
            scholar_profile=faculty_row["scholar"],
            scopus_profile=faculty_row["scopus"],
            orcid=faculty_row["orcid"],
            lattes=faculty_row["lattes"],
            linkedin=faculty_row["linkedin"],
            personal_site=faculty_row["site_pessoal"],
            experience_summary=faculty_row["exp_prof"],
            international_experience=faculty_row["exp_int"],
            phd_title=faculty_row["t_dout_en"],
            phd_institution=faculty_row["t_dout_ies"],
            phd_year=faculty_row["t_dout_ano"],
            phd_country=faculty_row["t_dout_pais_en"],
            masters_title=faculty_row["t_mestrado_en"],
            masters_institution=faculty_row["t_mestrado_ies"],
            masters_year=faculty_row["t_mestrado_ano"],
            masters_country=faculty_row["t_mestrado_pais_en"],
            education=education,
            experiences=experiences,
            productions=productions,
        )

    def _load_experience(self, conn: sqlite3.Connection, faculty_id: str) -> Iterable[ExperienceEntry]:
        cursor = conn.execute(
            """
            SELECT
                cargo_role,
                empresa_company,
                cidade_city,
                pa_s_country,
                categoria_prof_res_tch,
                in_cio,
                fim,
                idioma
            FROM docentes_experiencia_profissional
            WHERE id = ?
            ORDER BY in_cio DESC
            """,
            (faculty_id,),
        )

        for row in cursor.fetchall():
            language = (row["idioma"] or "").strip().upper()
            if language and language != "EN":
                continue
            yield ExperienceEntry(
                role=row["cargo_role"],
                organization=row["empresa_company"],
                city=row["cidade_city"],
                country=row["pa_s_country"],
                category=row["categoria_prof_res_tch"],
                start=_parse_date(row["in_cio"]),
                end=_parse_date(row["fim"]),
            )

    def _filter_experience(self, experiences: Iterable[ExperienceEntry], rules: dict) -> list[ExperienceEntry]:
        reference = datetime.utcnow()
        filtered = [exp for exp in experiences if exp.is_within_window(rules["experience_years"], reference)]
        return filtered[: rules["max_experience"]]

    def _summarize_production(self, productions: Iterable[ProductionEntry], rules: dict) -> list[ProductionEntry]:
        try:
            requested_limit = int(rules.get("summary_limit", 5))
        except (TypeError, ValueError):
            requested_limit = 5
        limit = max(requested_limit, 5)
        filtered = [prod for prod in productions if prod.title]
        return filtered[:limit]

    def _load_production(self, conn: sqlite3.Connection, faculty_name: str) -> Iterable[ProductionEntry]:
        cursor = conn.execute(
            """
            SELECT
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
            FROM docentes_producao
            WHERE professor = ?
            ORDER BY ano DESC, t_tulo
            """,
            (faculty_name,),
        )

        for row in cursor.fetchall():
            yield ProductionEntry(
                year=row["ano"],
                title=row["t_tulo"],
                production_type=row["tipo"],
                nature=row["ve_culo_ou_natureza"],
                classification=row["classifica_o"],
                peer_review=row["revis_o"],
                status_savi=row["status_savi"],
                status_biblioteca=row["status_biblioteca"],
                evidence_source=row["fonte_da_evid_ncia"],
                lattes_info=row["informa_o_cv_lattes"],
            )

    def _generate_document(self, profile: FacultyProfile, accreditation: str, destination: Path) -> None:
        document = Document()
        document.add_heading(profile.name, level=0)

        document.add_heading("Faculty Overview", level=1)
        overview_table = document.add_table(rows=1, cols=2)
        overview_table.style = "Light Grid Accent 1"
        _append_table_rows(
            overview_table,
            [
                ("Accreditation", accreditation),
                ("Career Track (EN)", profile.career_en),
                ("Career Track", profile.career),
                ("Specialization", profile.specialization),
                ("Unit", profile.unit),
                ("Core/Non-core", profile.core_status),
                ("Vertente", profile.vertente),
                ("Regime", profile.regime),
                ("Vínculo", profile.vinculo),
                ("Admission Date", _format_date(profile.admission_date)),
                ("Highest Degree", profile.highest_degree),
            ],
        )

        document.add_heading("Contact & Profiles", level=1)
        contacts_table = document.add_table(rows=1, cols=2)
        contacts_table.style = "Light Grid"
        _append_table_rows(
            contacts_table,
            [
                ("Email", profile.email),
                ("ORCID", profile.orcid),
                ("Scholar", profile.scholar_profile),
                ("Scopus", profile.scopus_profile),
                ("Lattes", profile.lattes),
                ("LinkedIn", profile.linkedin),
                ("Website", profile.personal_site),
            ],
        )

        document.add_heading("Accreditation Snapshot", level=1)
        accreditation_table = document.add_table(rows=1, cols=2)
        accreditation_table.style = "Light List Accent 2"
        _append_table_rows(
            accreditation_table,
            [
                ("Rule Version", ACCREDITATION_RULES[accreditation]["version"]),
                ("Template Version", TEMPLATE_VERSION),
                ("Time Mission", profile.time_mission),
                ("FTE", profile.fte),
                ("Teaching Load (hrs)", profile.teaching_load),
                ("Exec Ed Load (hrs)", profile.executive_education_load),
                ("Professional Experience Summary", profile.experience_summary),
                ("International Experience", profile.international_experience),
                ("Title Valid Brazil", profile.title_valid_brazil),
                ("Accreditation Flag", profile.accreditation_flag),
                ("Allocation", profile.allocation_tag),
            ],
        )

        if profile.qualification_summary:
            document.add_heading("Qualification Summary", level=1)
            document.add_paragraph(profile.qualification_summary)

        if profile.engagement_description:
            document.add_heading("Engagement", level=1)
            document.add_paragraph(profile.engagement_description)

        document.add_heading("Education", level=1)
        if profile.education:
            for record in profile.education:
                parts = [record.degree]
                if record.institution:
                    parts.append(record.institution)
                if record.country:
                    parts.append(record.country)
                if record.year:
                    parts.append(str(record.year))
                document.add_paragraph(" | ".join(parts), style="List Bullet")
        else:
            document.add_paragraph("No education records available.")

        document.add_heading("Academic Production", level=1)
        if profile.productions:
            for entry in profile.productions:
                bullet = document.add_paragraph(style="List Bullet")
                headline_parts = []
                if entry.year:
                    headline_parts.append(str(entry.year))
                if entry.title:
                    headline_parts.append(entry.title)
                bullet.add_run(" – ".join(headline_parts) if headline_parts else "Production item")

                detail_parts = []
                if entry.production_type:
                    detail_parts.append(entry.production_type)
                if entry.nature:
                    detail_parts.append(entry.nature)
                if entry.classification:
                    detail_parts.append(f"Classification: {entry.classification}")
                if entry.peer_review:
                    detail_parts.append(f"Peer review: {entry.peer_review}")
                if detail_parts:
                    bullet.add_run(f" ({'; '.join(detail_parts)})")

                evidence_parts = []
                if entry.status_savi:
                    evidence_parts.append(f"SAVI: {entry.status_savi}")
                if entry.status_biblioteca:
                    evidence_parts.append(f"Library: {entry.status_biblioteca}")
                if entry.evidence_source:
                    evidence_parts.append(f"Evidence: {entry.evidence_source}")
                if entry.lattes_info:
                    evidence_parts.append(f"Lattes: {entry.lattes_info}")
                if evidence_parts:
                    bullet.add_run(f" – {'; '.join(evidence_parts)}")
        else:
            document.add_paragraph("No academic production records available.")

        document.add_heading("Professional Experience", level=1)
        if profile.experiences:
            for entry in profile.experiences:
                segment = [entry.role, entry.organization]
                location = ", ".join(part for part in [entry.city, entry.country] if part)
                if location:
                    segment.append(location)
                timeline = f"{_format_date(entry.start) or 'N/A'} – {_format_date(entry.end) or 'Present'}"
                segment.append(timeline)
                if entry.category:
                    segment.append(entry.category)
                document.add_paragraph(" | ".join(segment), style="List Bullet")
        else:
            document.add_paragraph("No recent experience records available.")

        document.core_properties.author = "CV Automation"
        document.core_properties.subject = f"{accreditation} summarized CV"
        document.core_properties.keywords = [accreditation, TEMPLATE_VERSION]

        destination.parent.mkdir(parents=True, exist_ok=True)
        document.save(destination)

    def _write_json(self, profile: FacultyProfile, destination: Path) -> None:
        destination.write_text(json.dumps(profile.to_serializable(), indent=2), encoding="utf-8")


def _append_table_rows(table, rows: list[tuple[str, str | None]]) -> None:
    for index, (label, value) in enumerate(rows):
        if index == 0 and len(table.rows) == 1 and not table.rows[0].cells[0].text:
            row = table.rows[0]
        else:
            row = table.add_row()
        row.cells[0].text = label
        row.cells[1].text = str(value).strip() if value and str(value).strip() else "Not provided"


def _build_education_records(row: sqlite3.Row) -> list[EducationRecord]:
    education: list[EducationRecord] = []
    if row["t_dout_en"]:
        education.append(
            EducationRecord(
                degree=row["t_dout_en"],
                institution=row["t_dout_ies"],
                year=row["t_dout_ano"],
                country=row["t_dout_pais_en"],
            )
        )
    if row["t_mestrado_en"]:
        education.append(
            EducationRecord(
                degree=row["t_mestrado_en"],
                institution=row["t_mestrado_ies"],
                year=row["t_mestrado_ano"],
                country=row["t_mestrado_pais_en"],
            )
        )
    if row["tit_maxima"] and not education:
        education.append(
            EducationRecord(
                degree=row["tit_maxima"],
                institution=None,
                year=None,
                country=None,
            )
        )
    return education


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if not text or text.upper() in {"SEM INFORMAÇÃO", "SEM INFORMACAO", "NSA"}:
        return None

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%b %Y")


def _slugify(text: str) -> str:
    safe = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "faculty"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate summarized accreditation CVs")
    parser.add_argument("--accreditation", required=True, choices=sorted(ACCREDITATION_RULES.keys()))
    parser.add_argument("--faculty", nargs="*", help="Optional list of faculty IDs to process")
    args = parser.parse_args()

    automation = CVAutomation()
    result = automation.run(args.accreditation, args.faculty)
    logger.info("Completed automation with %d CVs", len(result))


if __name__ == "__main__":
    main()
