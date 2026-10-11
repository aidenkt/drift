import json
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pipeline
from checks import label as labeler, news

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


class LabelEdit(BaseModel):
    cell: str
    literal_index: int | None = None
    label: str | None = None
    role: str | None = None  # market | lever | internal | unit


@app.patch("/models/{model_id}/constants")
def edit_constant(model_id: str, edit: LabelEdit):
    """User confirms or corrects a label; the constant is checked again."""
    report = REPORTS.get(model_id)
    if report is None:
        raise HTTPException(404)
    matches = [
        c for c in report["constants"]
        if c["cell"] == edit.cell and (edit.literal_index is None or c.get("literal_index") == edit.literal_index)
    ]
    if len(matches) != 1:
        raise HTTPException(404 if not matches else 409, "pass literal_index to pick one literal in this formula")
    if edit.role is not None and edit.role not in labeler.ROLES:
        raise HTTPException(422, f"role must be one of {labeler.ROLES}")
    c = matches[0]
    if edit.label:
        c["label"] = edit.label
    if edit.role:
        c["role"] = edit.role
    role = c.get("role", "market" if c.get("driver") else "internal")
    c["driver"] = labeler.slug(c["label"]) if role == "market" else None
    c["label_source"] = "user"
    c["confirmed"] = True
    if role == "market":
        if edit.label:
            c["search"] = [c["label"]]
        c["check"] = news.check(c, report["built_on"], report["checked_on"])
    else:
        c["check"] = None
    # TODO(graph): recompute with impact.deltas once wb and graph are kept per model_id
    c["impact"] = []
    return c
