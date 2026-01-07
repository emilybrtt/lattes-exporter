from __future__ import annotations

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.services.automation import ACCREDITATION_RULES, CVAutomation

load_dotenv()


app = Flask(__name__)
CORS(app)
app.config["JSON_SORT_KEYS"] = False

automation_service = CVAutomation()


@app.get("/")
def list_faculty():
    """Lista todos os docentes com os dados consolidados em JSON."""
    profiles = automation_service.fetch_all_profiles()
    return jsonify({"total": len(profiles), "result": profiles})


@app.get("/<int:faculty_id>")
def get_faculty(faculty_id: int):
    """Retorna o JSON de um docente específico pelo identificador numérico."""
    profile = automation_service.fetch_profile(str(faculty_id))
    if profile is None:
        return jsonify({"error": "Docente não encontrado"}), 404
    return jsonify(profile)


@app.post("/export")
def export_faculty():
    """Gera o DOCX/JSON de um docente conforme a acreditação informada."""
    payload = request.get_json(force=False, silent=True) or {}
    faculty_id = payload.get("id") or payload.get("faculty_id") or request.args.get("id")
    accreditation = payload.get("accreditation") or request.args.get("accreditation")

    if not faculty_id:
        return jsonify({"error": "Parâmetro 'id' é obrigatório"}), 400

    if not accreditation:
        return jsonify({"error": "Parâmetro 'accreditation' é obrigatório"}), 400

    try:
        metadata = automation_service.run(accreditation, [str(faculty_id)])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not metadata:
        return jsonify({"error": "Nenhum artefato gerado para o docente solicitado"}), 404

    return jsonify(metadata[0])


@app.get("/automation/status")
def automation_status():
    return jsonify(
        {
            "accreditations": sorted(ACCREDITATION_RULES.keys()),
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
