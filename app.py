from __future__ import annotations

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file, url_for
from flask_cors import CORS

from backend.services.automation import CVAutomation

load_dotenv()


app = Flask(__name__)
CORS(app)
app.config["JSON_SORT_KEYS"] = False

automation_service = CVAutomation()


@app.get("/")
def list_faculty():
    """Lista todos os docentes com os dados consolidados em JSON """
    profiles = automation_service.fetch_all_profiles()
    return jsonify({"total": len(profiles), "result": profiles})


@app.get("/<int:faculty_id>")
def get_faculty(faculty_id: int):
    """Retorna o JSON de um docente específico pelo identificador numérico """
    profile = automation_service.fetch_profile(str(faculty_id))
    if profile is None:
        return jsonify({"error": "Docente não encontrado"}), 404
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

    try:
        metadata = automation_service.export_artifact(resolved_id, export_format)
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
