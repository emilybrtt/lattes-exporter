from __future__ import annotations

import mimetypes
from io import BytesIO
from math import ceil

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

from backend.core.database import (
    fetch_faculty_photo,
    reload_table_from_upload,
    store_faculty_photo,
)
from backend.services.automation import CVAutomation

load_dotenv()


app = Flask(__name__)
CORS(app)
app.config["JSON_SORT_KEYS"] = False

automation_service = CVAutomation()

MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.get("/")
def list_faculty():
    """Lista todos os docentes com os dados consolidados em JSON """
    profiles = automation_service.fetch_all_profiles()
    return jsonify({"total": len(profiles), "result": profiles})


@app.get("/summary")
def list_faculty_summary():
    """Lista dados essenciais (id, nome, área e unidade) com suporte a paginação."""

    raw_page = request.args.get("page", default=1, type=int) or 1
    raw_per_page = request.args.get("per_page", default=50, type=int) or 50
    allocated_only_raw = request.args.get("allocated_only")
    accreditation_filters = [
        item.strip()
        for item in request.args.getlist("accreditation")
        if isinstance(item, str) and item.strip()
    ]

    page = max(raw_page, 1)
    per_page = min(max(raw_per_page, 1), 50)
    offset = (page - 1) * per_page

    if allocated_only_raw is None:
        allocated_only = True
    else:
        normalized_allocated = allocated_only_raw.strip().lower()
        allocated_only = normalized_allocated not in {"0", "false", "no", "nao", "não"}

    try:
        summaries, total = automation_service.fetch_profiles_summary(
            offset=offset,
            limit=per_page,
            allocated_only=allocated_only,
            accreditations=accreditation_filters,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    page_count = ceil(total / per_page) if total and per_page else 0

    if total and page > page_count:
        page = page_count
        offset = (page - 1) * per_page
        summaries, total = automation_service.fetch_profiles_summary(
            offset=offset,
            limit=per_page,
            allocated_only=allocated_only,
            accreditations=accreditation_filters,
        )
    elif total == 0:
        page = 1

    return jsonify(
        {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": page_count,
            "result": summaries,
        }
    )


@app.get("/<int:faculty_id>")
def get_faculty(faculty_id: int):
    """Retorna o JSON de um docente específico pelo identificador numérico """
    profile = automation_service.fetch_profile(str(faculty_id))
    if profile is None:
        return jsonify({"error": "Docente não encontrado"}), 404
    photo_info = profile.get("photo") if isinstance(profile, dict) else None
    if isinstance(photo_info, dict) and photo_info.get("available"):
        photo_info["url"] = url_for("download_faculty_photo", faculty_id=faculty_id, _external=True)
    return jsonify(profile)


@app.post("/export")
@app.post("/export/<int:faculty_id>")
def export_faculty(faculty_id: int | None = None):
    """Gera o artefato do docente no formato informado (docx ou pdf)."""

    payload = request.get_json(force=False, silent=True) or {}
    payload_id = payload.get("id") or payload.get("faculty_id") or request.args.get("id")

    if faculty_id is None and payload_id is None:
        return jsonify({"error": "Parâmetro 'id' é obrigatório"}), 400

    if faculty_id is not None and payload_id is not None and str(payload_id) != str(faculty_id):
        return jsonify({"error": "Identificadores divergentes entre URL e payload"}), 400

    resolved_id = str(faculty_id if faculty_id is not None else payload_id)

    export_format = (request.args.get("format") or "docx").strip().lower()
    if export_format not in {"docx", "pdf"}:
        return jsonify({"error": "Formato inválido. Utilize 'docx' ou 'pdf'."}), 400

    include_photo_raw = (
        payload.get("include_photo")
        if isinstance(payload, dict)
        else None
    )
    if include_photo_raw is None:
        include_photo_raw = request.args.get("include_photo")

    include_photo = True
    if include_photo_raw is not None:
        include_photo = str(include_photo_raw).strip().lower() not in {"0", "false", "no", "nao", "não"}

    try:
        metadata = automation_service.export_artifact(
            resolved_id,
            export_format,
            include_photo=include_photo,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if metadata is None:
        return jsonify({"error": "Docente não encontrado"}), 404

    for key in ("docx_path", "pdf_path"):
        artifact_path = metadata.get(key)
        if artifact_path:
            metadata[key.replace("_path", "_url")] = url_for(
                "download_artifact",
                resource=artifact_path,
                _external=True,
            )

    return jsonify(metadata)


@app.post("/faculty/<int:faculty_id>/photo")
def upload_faculty_photo(faculty_id: int):
    file_storage = request.files.get("photo")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "Envie uma imagem no campo 'photo'."}), 400

    content = file_storage.read()
    if not content:
        return jsonify({"error": "Arquivo vazio."}), 400
    if len(content) > MAX_PHOTO_SIZE:
        return jsonify({"error": "A imagem deve ter no máximo 5 MB."}), 400

    mime_type = (file_storage.mimetype or "").lower()
    if not mime_type or mime_type not in ALLOWED_PHOTO_MIME_TYPES:
        guessed = mimetypes.guess_type(file_storage.filename)[0]
        if guessed not in ALLOWED_PHOTO_MIME_TYPES:
            return jsonify({"error": "Formato não suportado. Envie PNG, JPEG ou WebP."}), 400
        mime_type = guessed or "image/jpeg"

    safe_name = secure_filename(file_storage.filename) or f"photo_{faculty_id}"

    try:
        metadata = store_faculty_photo(
            str(faculty_id),
            content=content,
            mime_type=mime_type,
            filename=safe_name,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Falha ao armazenar foto do docente %s: %s", faculty_id, exc)
        return jsonify({"error": "Falha interna ao salvar a foto."}), 500

    metadata["faculty_id"] = str(faculty_id)
    metadata["message"] = "Foto atualizada com sucesso."
    automation_service.invalidate_cache()
    return jsonify(metadata)


@app.get("/faculty/<int:faculty_id>/photo")
def download_faculty_photo(faculty_id: int):
    record = fetch_faculty_photo(str(faculty_id))
    if record is None:
        return jsonify({"error": "Foto não encontrada."}), 404

    image_bytes = record.get("image")
    if not image_bytes:
        return jsonify({"error": "Foto não encontrada."}), 404

    stream = BytesIO(image_bytes)
    stream.seek(0)
    mime_type = record.get("mime_type") or "image/jpeg"
    filename = record.get("filename") or f"faculty_{faculty_id}.jpg"

    return send_file(stream, mimetype=mime_type, download_name=filename)


@app.get("/artifacts/<path:resource>")
def download_artifact(resource: str):
    base_dir = automation_service.output_root.resolve()
    target_path = (base_dir / resource).resolve()

    try:
        target_path.relative_to(base_dir)
    except ValueError:
        abort(404)

    if not target_path.exists() or not target_path.is_file():
        abort(404)

    return send_file(target_path, as_attachment=True, download_name=target_path.name)


@app.get("/automation/status")
def automation_status():
    try:
        output_dirs = sorted(
            entry.name for entry in automation_service.output_root.iterdir() if entry.is_dir()
        )
    except FileNotFoundError:
        output_dirs = []
    return jsonify(
        {
            "accreditations": output_dirs,
            "output_dir": str(automation_service.output_root),
        }
    )


@app.post("/automation/run")
def automation_run():
    payload = request.get_json(force=True, silent=True) or {}
    accreditation = payload.get("accreditation")
    faculty_ids = payload.get("faculty_ids")

    if not accreditation:
        return jsonify({"error": "Missing accreditation"}), 400

    try:
        metadata = automation_service.run(accreditation, faculty_ids)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"generated": len(metadata), "artifacts": metadata})


@app.post("/tables/<string:table_key>/upload")
def upload_table(table_key: str):
    """Carrega manualmente uma tabela suportada com base em um arquivo enviado."""

    file_storage = request.files.get("file")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "Envie um arquivo no campo 'file'."}), 400

    safe_name = secure_filename(file_storage.filename) or file_storage.filename

    try:
        payload = file_storage.read()
        result = reload_table_from_upload(table_key, payload, filename=safe_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Falha ao carregar tabela %s: %s", table_key, exc)
        return jsonify({"error": "Falha interna ao processar o arquivo."}), 500

    automation_service.invalidate_cache()
    response = {
        "message": "Tabela carregada com sucesso.",
        "table": result["table"],
        "rows": result["rows"],
        "columns": result["columns"],
        "source": result["source"],
    }
    return jsonify(response), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
