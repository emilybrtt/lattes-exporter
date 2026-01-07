from __future__ import annotations

from dotenv import load_dotenv
from flask import Flask, jsonify, request
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
def export_faculty():
    """Gera o DOCX de um docente conforme a acreditação informada """
    payload = request.get_json(force=False, silent=True) or {}
    faculty_id = payload.get("id") or payload.get("faculty_id") or request.args.get("id")

    if not faculty_id:
        return jsonify({"error": "Parâmetro 'id' é obrigatório"}), 400

    try:
        metadata = automation_service.export_doc(str(faculty_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if metadata is None:
        return jsonify({"error": "Docente não encontrado"}), 404

    return jsonify(metadata)


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
