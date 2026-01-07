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
