import json
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import pipeline

load_dotenv(Path(__file__).parent.parent / ".env")

ROOT = Path(__file__).parent
UPLOADS = ROOT / "uploads"
FIXTURE = ROOT.parent / "schema" / "fixtures" / "case_study.json"

app = FastAPI(title="Since engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# model_id -> report (in memory for the hackathon)
REPORTS: dict[str, dict] = {"case-study": json.loads(FIXTURE.read_text())}


@app.get("/models")
def list_models():
    return [
        {
            "model_id": r["model_id"],
            "filename": r["filename"],
            "built_on": r["built_on"],
            "stale": sum(1 for c in r["constants"] if c["check"] and c["check"]["status"] == "stale"),
            "constants": len(r["constants"]),
        }
        for r in REPORTS.values()
    ]


@app.get("/models/{model_id}")
def get_model(model_id: str):
    if model_id not in REPORTS:
        raise HTTPException(404)
    return REPORTS[model_id]


@app.post("/models")
async def upload_model(file: UploadFile, built_on: str):
    UPLOADS.mkdir(exist_ok=True)
    model_id = uuid.uuid4().hex[:8]
    path = UPLOADS / f"{model_id}.xlsx"
    path.write_bytes(await file.read())
    REPORTS[model_id] = pipeline.run(path, model_id=model_id, filename=file.filename, built_on=built_on)
    return {"model_id": model_id}
