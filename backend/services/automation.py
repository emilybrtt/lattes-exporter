from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.shared import Pt, Inches, RGBColor
import docx.oxml      

from backend.core.config import OUTPUT_DIR, sqlite_path

logger = logging.getLogger("cv_automation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Estruturas de dados -------------------------------------------------------


@dataclass
class EducationRecord:
    """Guarda um curso ou diploma do docente."""
    degree: str | None
    institution: str | None
    year: str | None
    country: str | None


@dataclass
class ExperienceEntry:
    """Registra uma experiência profissional relevante."""
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
    """Resume uma produção acadêmica que vai para o CV."""
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
    """Reúne todas as informações consolidadas de um docente."""
    faculty_id: str
    name: str
    email: str | None
    nationality: str | None
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
        """Transforma o perfil em um dicionário pronto para JSON."""
        return {
            "faculty": {
                "id": self.faculty_id,
                "name": self.name,
                "email": self.email,
                "nationality": self.nationality,
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
        """Configura caminho do banco e da pasta de saída."""
        self.db_path = sqlite_path()
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def run(self, accreditation: str, faculty_ids: Sequence[str] | None = None) -> list[dict]:
        """Cria os arquivos da acreditação pedida."""
        accreditation_key = accreditation.strip().upper()
        if not accreditation_key:
            raise ValueError("Accreditation must not be empty")
        planned_ids = list(faculty_ids) if faculty_ids else self._fetch_all_ids()
        logger.info("Starting automation for %s with %d faculty", accreditation_key, len(planned_ids))

        metadata: list[dict] = []
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        accreditation_dir = self.output_root / accreditation_key.lower()
        accreditation_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for faculty_id in planned_ids:
                # Monta os dados completos do docente direto do banco.
                try:
                    profile = self._build_profile(conn, faculty_id)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to assemble data for faculty %s: %s", faculty_id, exc)
                    continue

                if profile is None:
                    logger.warning("Skipping faculty %s: no base record found", faculty_id)
                    continue

                limited_profile = profile

                docx_path = accreditation_dir / f"{faculty_id}_{_slugify(profile.name)}.docx"
                json_path = accreditation_dir / f"{faculty_id}_{_slugify(profile.name)}.json"

                try:
                    self._generate_document(limited_profile, docx_path)
                    self._write_json(limited_profile, json_path)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to render CV for faculty %s: %s", faculty_id, exc)
                    continue

                metadata.append(
                    {
                        "faculty_id": faculty_id,
                        "name": profile.name,
                        "accreditation": accreditation_key,
                        "docx_path": docx_path.relative_to(self.output_root).as_posix(),
                        "json_path": json_path.relative_to(self.output_root).as_posix(),
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
        """Busca um docente pelo id e devolve os dados prontos para JSON."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                # Reaproveita a lógica interna para compor o perfil.
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
        """Devolve todos os docentes com os dados já formatados."""
        faculty_ids = self._fetch_all_ids()
        if not faculty_ids:
            return []

        results: list[dict] = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for faculty_id in faculty_ids:
                # Continua mesmo se um docente gerar erro.
                try:
                    # Evita travar a exportação quando um registro falha.
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

    def export_doc(self, faculty_id: str) -> dict | None:
        """Gera apenas o DOCX para um docente específico."""

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            profile = self._build_profile(conn, faculty_id)

        if profile is None:
            return None

        limited_profile = profile

        docx_path = self.output_root / f"{faculty_id}_{_slugify(profile.name)}.docx"
        docx_path.parent.mkdir(parents=True, exist_ok=True)
        self._generate_document(limited_profile, docx_path)

        metadata = {
            "faculty_id": faculty_id,
            "name": profile.name,
            "docx_path": docx_path.relative_to(self.output_root).as_posix(),
        }

        return metadata

    def _fetch_all_ids(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM base_de_dados_docente")
            return [str(row[0]) for row in cursor.fetchall()]

    def _build_profile(self, conn: sqlite3.Connection, faculty_id: str) -> FacultyProfile | None:
        """Lê todas as colunas necessárias para gerar um perfil completo."""
        faculty_row = conn.execute(
            """
            SELECT
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
            FROM base_de_dados_docente
            WHERE id = ?
            """,
            (faculty_id,),
        ).fetchone()

        if faculty_row is None:
            return None

        # Carrega listas auxiliares (experiência, educação, produção).
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
            nationality=faculty_row["nacionalidade"],
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
        """Filtra experiências do docente que estejam em inglês."""
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

    def _load_production(self, conn: sqlite3.Connection, faculty_name: str) -> Iterable[ProductionEntry]:
        """Busca produções acadêmicas ordenadas por ano."""
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

    # ========== Formatação do documento .docx ===========
    def _format_header(self, document, profile: FacultyProfile):
        """Monta cabeçalho com informações básicas do docente."""
        name_para = document.add_paragraph(profile.name)
        name_para.alignment = 1  
        name_run = name_para.runs[0]
        name_run.font.name = 'Times New Roman'
        name_run.font.size = Pt(14)
        name_run.font.bold = True
        name_para.paragraph_format.space_after = Pt(3)
        
        # Institution
        inst_para = document.add_paragraph("Insper Instituto de Ensino e Pesquisa")
        inst_para.alignment = 1  
        inst_para.runs[0].font.name = 'Times New Roman'
        inst_para.runs[0].font.size = Pt(12)
        inst_para.runs[0].font.bold = True
        inst_para.paragraph_format.space_after = Pt(2)
        
        # Position
        pos_para = document.add_paragraph(profile.career_en or profile.career)
        pos_para.alignment = 1  
        pos_para.runs[0].font.name = 'Times New Roman'
        pos_para.runs[0].font.size = Pt(12)
        pos_para.runs[0].font.bold = True
        pos_para.paragraph_format.space_after = Pt(2)
        
        # Area
        area_para = document.add_paragraph(_format_area(profile.area or ""))
        area_para.alignment = 1  
        area_para.runs[0].font.name = 'Times New Roman'
        area_para.runs[0].font.size = Pt(12)
        area_para.runs[0].font.bold = True
        area_para.paragraph_format.space_after = Pt(2)
        
        # Email
        email_para = document.add_paragraph(profile.email)
        email_para.alignment = 1  
        email_para.runs[0].font.name = 'Times New Roman'
        email_para.runs[0].font.size = Pt(12)
        email_para.runs[0].font.bold = True
        email_para.paragraph_format.space_after = Pt(2)
        
        # Admission date
        if profile.admission_date:
            formatted_date = _format_date(profile.admission_date)
            adm_para = document.add_paragraph(f"Admission: {formatted_date}")
            adm_para.alignment = 1  
            adm_para.runs[0].font.name = 'Times New Roman'
            adm_para.runs[0].font.size = Pt(12)
            adm_para.runs[0].font.bold = True
            adm_para.paragraph_format.space_after = Pt(2)
        
        # Lattes URL
        if profile.lattes:
            lattes_para = document.add_paragraph(profile.lattes)
            lattes_para.alignment = 1  
            lattes_para.runs[0].font.name = 'Times New Roman'
            lattes_para.runs[0].font.size = Pt(12)
            lattes_para.runs[0].font.bold = False
            lattes_para.paragraph_format.space_after = Pt(12)
        
        # Academic Unit and Nationality
        dict_units={
            'M&E': "Management and Economics",
            'LAW': "Law",
            'ENG&CC': "Engineering and Computer Science",
        }
        unit_text = f"Academic Unit: {dict_units.get(profile.unit, profile.unit)}"
        nationality_text = f"Nationality: {profile.nationality}"

        # Specialization/Area e Nationality na mesma linha
        if profile.unit or profile.nationality:
            # Criar tabela com 1 linha e 2 colunas
            table = document.add_table(rows=1, cols=2)
            table.alignment = 0  # Alinhamento à esquerda
            
            # Remover bordas da tabela
            for row in table.rows:
                for cell in row.cells:
                    cell._element.get_or_add_tcPr().append(
                        docx.oxml.parse_xml(r'<w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:top w:val="none"/><w:left w:val="none"/><w:bottom w:val="none"/><w:right w:val="none"/></w:tcBorders>')
                    )
            
            # Célula esquerda - Especialização
            left_cell = table.rows[0].cells[0]
            if profile.specialization:
                left_para = left_cell.paragraphs[0]
                run_left = left_para.add_run(unit_text)
                run_left.font.name = 'Times New Roman'
                run_left.font.size = Pt(12)
            
            # Célula direita - Nacionalidade
            right_cell = table.rows[0].cells[1]
            if profile.nationality:
                right_para = right_cell.paragraphs[0]
                right_para.alignment = 2
                run_right = right_para.add_run(nationality_text)
                run_right.font.name = 'Times New Roman'
                run_right.font.size = Pt(12)
            
            # Espaçamento após a tabela
            table.rows[0].height = Pt(14)

    # =========================================================================
    # MÉTODOS AUXILIARES DE FORMATAÇÃO E LAYOUT
    # =========================================================================

    def _add_section_header(self, document, text: str):
        """Adiciona um cabeçalho H1 com a formatação específica (Borda inferior)."""
        heading = document.add_heading(text, level=1)
        
        # Formatação do Texto
        if heading.runs:
            run = heading.runs[0]
        else:
            run = heading.add_run()
            
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0, 0, 0)
        run._element.rPr.rFonts.set(docx.oxml.ns.qn('w:eastAsia'), 'Times New Roman')
        
        # Espaçamento
        heading.paragraph_format.space_after = Pt(6)
        heading.paragraph_format.space_before = Pt(12)
        
        # Borda Inferior (XML Injection)
        p_pr = heading._element.get_or_add_pPr()
        p_borders = docx.oxml.parse_xml(
            r'<w:pBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            r'<w:bottom w:val="single" w:sz="4" w:space="1" w:color="000000"/>'
            r'</w:pBorders>'
        )
        p_pr.append(p_borders)
        return heading

    def _add_subheader(self, document, text: str):
        """Adiciona subtítulo simples (apenas negrito, sem borda)."""
        p = document.add_paragraph()
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        run.font.bold = True
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(6)

    def _create_layout_table(self, document):
        """Cria a tabela base de 2 colunas para layout de data/conteúdo."""
        table = document.add_table(rows=0, cols=2)
        table.autofit = False
        table.columns[0].width = Inches(0.85)
        table.columns[1].width = Inches(5.65)
        return table

    def _add_layout_row(self, table, left_text: str, right_text: str):
        """Adiciona uma linha formatada à tabela e remove as bordas."""
        row = table.add_row()
        
        # Coluna 1: Data/Ano
        row.cells[0].text = left_text
        if row.cells[0].paragraphs[0].runs:
            run = row.cells[0].paragraphs[0].runs[0]
            run.font.name = 'Times New Roman'
            run.font.size = Pt(11)

        # Coluna 2: Conteúdo
        row.cells[1].text = right_text
        if row.cells[1].paragraphs[0].runs:
            run = row.cells[1].paragraphs[0].runs[0]
            run.font.name = 'Times New Roman'
            run.font.size = Pt(11)

        # Remove bordas da célula (XML Injection)
        for cell in row.cells:
            tc_pr = cell._element.get_or_add_tcPr()
            tc_borders = docx.oxml.parse_xml(
                r'<w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                r'<w:top w:val="none"/>'
                r'<w:left w:val="none"/>'
                r'<w:bottom w:val="none"/>'
                r'<w:right w:val="none"/>'
                r'</w:tcBorders>'
            )
            tc_pr.append(tc_borders)

    def _generate_document(
        self,
        profile: FacultyProfile,
        destination: Path,
    ) -> None:
        
        document = Document()  # Cria documento vazio para montar o CV.
        
        # Ajuste global de margens se necessário
        # section = document.sections[0]
        # section.left_margin = Inches(1.0)
        # section.right_margin = Inches(1.0)

        self._format_header(document, profile)

        # ========== EDUCATION ==========
        
        if profile.education:
            self._add_section_header(document, "EDUCATION")
            
            table = self._create_layout_table(document)
            table.columns[0].width = Inches(0.7)  # Mantendo a largura específica usada anteriormente

            for record in profile.education:
                year_text = str(record.year).strip() if record.year else ""
                
                parts = []
                if record.degree: parts.append(record.degree)
                if record.institution: parts.append(record.institution)
                if record.country: parts.append(record.country)
                full_text = ", ".join(parts)
                
                self._add_layout_row(table, year_text, full_text)

            document.add_paragraph().paragraph_format.space_after = Pt(6)
            
            
        # ========== PROFESSIONAL EXPERIENCE ==========
        
        prof_exps = [e for e in profile.experiences if e.category == 'Professional']
        
        if prof_exps:
            self._add_section_header(document, "PROFESSIONAL EXPERIENCE")
            self._add_subheader(document, "Professional experience")
            
            table = self._create_layout_table(document)
            
            for exp in prof_exps:
                date_str = ""
                if exp.start:
                    year_start = exp.start.year
                    if not exp.end:
                        date_str = f"Since {year_start}"
                    else:
                        year_end = exp.end.year
                        date_str = f"{year_start}-{year_end}"
                
                parts = [p for p in [exp.role, exp.organization] if p]
                desc_str = " - ".join(parts)
                if exp.country:
                    desc_str += f", {exp.country}"
                
                self._add_layout_row(table, date_str, desc_str)
            
            document.add_paragraph().paragraph_format.space_after = Pt(6)


        # ========== RESEARCH ACTIVITIES ==========
        
        res_exps = [e for e in profile.experiences if e.category == 'Research']
        
        if res_exps:
            self._add_section_header(document, "RESEARCH ACTIVITIES")
            self._add_subheader(document, "Research Activities & Institutional Contribution")
            
            table = self._create_layout_table(document)
            
            for exp in res_exps:
                date_str = ""
                if exp.start:
                    if not exp.end:
                        date_str = f"Since {exp.start.year}"
                    else:
                        date_str = f"{exp.start.year}-{exp.end.year}"
                
                desc_str = f"{exp.role} - {exp.organization}"
                self._add_layout_row(table, date_str, desc_str)

            document.add_paragraph().paragraph_format.space_after = Pt(6)


        # ========== TEACHING EXPERIENCE ==========
        acad_exps = [e for e in profile.experiences if e.category == 'Academic']
        
        if acad_exps:
            self._add_section_header(document, "TEACHING EXPERIENCE")
            self._add_subheader(document, "Teaching Experience")
            
            table = self._create_layout_table(document)
            
            for exp in acad_exps:
                date_str = ""
                if exp.start:
                    if not exp.end:
                        date_str = f"Since {exp.start.year}"
                    else:
                        date_str = f"{exp.start.year}-{exp.end.year}"
                
                parts = [p for p in [exp.role, exp.organization] if p]
                desc_str = ", ".join(parts)
                if exp.country:
                    desc_str += f", {exp.country}"
                    
                self._add_layout_row(table, date_str, desc_str)
            
            document.add_paragraph().paragraph_format.space_after = Pt(6)


        # ========== INTELLECTUAL CONTRIBUTIONS ==========

        if profile.productions:
            self._add_section_header(document, "INTELLECTUAL CONTRIBUTIONS")
            
            grouped_prod = {}
            for prod in profile.productions:
                p_type = prod.production_type or "Other Productions"
                # Ajuste de categorias baseado em palavras-chave comuns
                if "Artigos" in p_type or "journal" in (prod.nature or "").lower():
                    p_type = "Peer-reviewed Articles"
                elif "Capítulo" in p_type or "Chapter" in p_type:
                    p_type = "Book Chapters"
                
                if p_type not in grouped_prod:
                    grouped_prod[p_type] = []
                grouped_prod[p_type].append(prod)

            priority_order = ["Peer-reviewed Articles", "Book Chapters", "Books", "Other Productions"]
            sorted_keys = sorted(grouped_prod.keys(), key=lambda k: priority_order.index(k) if k in priority_order else 99)

            for p_type in sorted_keys:
                self._add_subheader(document, p_type)
                
                items = grouped_prod[p_type]
                # Ordenar por ano decrescente
                items.sort(key=lambda x: x.year or "0", reverse=True)
                
                for idx, item in enumerate(items, 1):
                    p = document.add_paragraph()
                    p.paragraph_format.space_after = Pt(4)
                    
                    # 1. Número
                    run_num = p.add_run(f"{idx}. ")
                    run_num.font.name = 'Times New Roman'
                    run_num.font.size = Pt(11)
                    
                    # Título
                    run_title = p.add_run(f"{item.title or ''} ")
                    run_title.font.name = 'Times New Roman'
                    run_title.font.size = Pt(11)
                    
                    # (Ano)
                    if item.year:
                        run_year = p.add_run(f"({item.year}). ")
                        run_year.font.name = 'Times New Roman'
                        run_year.font.size = Pt(11)
                    
                    # Natureza / Journal
                    if item.nature:
                        run_nature = p.add_run(f"{item.nature}.")
                        run_nature.font.name = 'Times New Roman'
                        run_nature.font.size = Pt(11)
                        run_nature.font.italic = True

        # Metadados do documento
        document.core_properties.author = "CV Automation"
        document.core_properties.subject = f"{profile.name} CV"
        
        document.save(destination)

    def _write_json(self, profile: FacultyProfile, destination: Path) -> None:
        destination.write_text(json.dumps(profile.to_serializable(), indent=2), encoding="utf-8")


def _append_table_rows(table, rows: list[tuple[str, str | None]]) -> None:
    """Ajuda a preencher tabelas simples sem repetir código."""
    for index, (label, value) in enumerate(rows):
        if index == 0 and len(table.rows) == 1 and not table.rows[0].cells[0].text:
            row = table.rows[0]
        else:
            row = table.add_row()
        row.cells[0].text = label
        row.cells[1].text = str(value).strip() if value and str(value).strip() else ""


def _build_education_records(row: sqlite3.Row) -> list[EducationRecord]:
    """Monta lista com as titulações mais relevantes do docente."""
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
    """Converte textos de data em objetos datetime tratados."""
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
    """Formata datas no padrão "Mes Ano" esperado pelo relatório."""
    if value is None:
        return None
    return value.strftime("%b %Y")


def _slugify(text: str) -> str:
    """Gera um identificador seguro para nomes de arquivo."""
    safe = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "faculty"

dict_areas={
'FIN': "Finance",
'MGT': "Management",
'QTM': "Quantitative Methods",
'NSA': "No Specific Area",
'LEG': "Legal Studies",
'ECO': "Economics",
'MKT': "Marketing",
'ACC': "Accounting",
'ITO': "IT and Operations",
}

def _format_area(text: str) -> str:
    """Traduz códigos de área para descrições amigáveis."""
    safe = ""
    for c in text.strip():
        c.upper()
        safe+=c
    return dict_areas.get(safe, text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate summarized accreditation CVs")
    parser.add_argument("--accreditation", required=True)
    parser.add_argument("--faculty", nargs="*", help="Optional list of faculty IDs to process")
    args = parser.parse_args()

    automation = CVAutomation()
    result = automation.run(args.accreditation, args.faculty)
    logger.info("Completed automation with %d CVs", len(result))


if __name__ == "__main__":
    main()