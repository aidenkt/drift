import copy
import logging
import threading
import uuid
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import pipeline
from checks import label as labeler, news

load_dotenv(Path(__file__).parent.parent / ".env")

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
UPLOADS = ROOT / "uploads"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(title="Since engine")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"]
)

# model_id -> report (in memory for the hackathon)
REPORTS: dict[str, dict] = {}
# held for every read and write of REPORTS and of a report: a background thread fills each one in after upload
LOCK = threading.Lock()


@app.get("/models")
def list_models():
    with LOCK:
        return [
            {
                "model_id": r["model_id"],
                "filename": r["filename"],
                "built_on": r["built_on"],
                "status": r.get("status", "done"),
                "stale": sum(1 for c in r["constants"] if c["check"] and c["check"]["status"] == "stale"),
                "constants": len(r["constants"]),
            }
            for r in REPORTS.values()
        ]


@app.get("/models/{model_id}")
def get_model(model_id: str):
    with LOCK:
        if model_id not in REPORTS:
            raise HTTPException(404)
        return JSONResponse(REPORTS[model_id])  # serialised here, under the lock: a snapshot


@app.get("/models/{model_id}/file")
def get_file(model_id: str):
    """The workbook as it was uploaded."""
    with LOCK:
        filename = REPORTS[model_id]["filename"] if model_id in REPORTS else None
    if filename is None or not _workbook(model_id).is_file():
        raise HTTPException(404)
    return FileResponse(_workbook(model_id), filename=filename, media_type=XLSX)


@app.post("/models")
def upload_model(file: UploadFile, built_on: str | None = None):
    """Lists the workbook's constants and returns; they are labeled and checked in the background.
    built_on defaults to the date the workbook gives for itself, else today."""
    if built_on:
        try:
            built_on = date.fromisoformat(built_on).isoformat()
        except ValueError:
            raise HTTPException(422, "built_on must be a date, YYYY-MM-DD")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    model_id = uuid.uuid4().hex[:8]
    path = UPLOADS / f"{model_id}.xlsx"
    path.write_bytes(file.file.read())
    try:
        report = pipeline.start(path, model_id=model_id, filename=file.filename or path.name, built_on=built_on or None)
    except Exception:
        log.warning("upload %r is not a readable workbook", file.filename, exc_info=True)
        path.unlink(missing_ok=True)
        raise HTTPException(400, "could not read this file as an Excel workbook (.xlsx)")
    with LOCK:
        REPORTS[model_id] = report
    threading.Thread(target=pipeline.finish, args=(report,), kwargs={"lock": LOCK}, daemon=True).start()
    return {"model_id": model_id}


@app.put("/models/{model_id}/file")
def replace_model(model_id: str, file: UploadFile):
    """The workbook after an edit in the browser. Unchanged constants keep their labels and checks; new or
    changed ones are labeled and checked in the background, as after an upload."""
    if model_id == "case-study":
        raise HTTPException(409, "the sample model is not checked again")
    with LOCK:
        previous = REPORTS.get(model_id)
    if previous is None:
        raise HTTPException(404)
    path = _workbook(model_id)
    data = file.file.read()
    staged = path.with_suffix(".next.xlsx")
    staged.write_bytes(data)
    try:
        report = pipeline.start(staged, model_id=model_id, filename=previous["filename"], previous=previous)
    except Exception:
        log.warning("edited workbook for %s is not readable", model_id, exc_info=True)
        staged.unlink(missing_ok=True)
        raise HTTPException(400, "could not read this file as an Excel workbook (.xlsx)")
    staged.replace(path)
    pipeline.remember(model_id, path)
    with LOCK:
        REPORTS[model_id] = report  # a check still running on the old report finishes into nothing
    threading.Thread(target=pipeline.finish, args=(report,), kwargs={"lock": LOCK}, daemon=True).start()
    return {"model_id": model_id, "changed": sum(c.get("stage") != "done" for c in report["constants"])}


class LabelEdit(BaseModel):
    cell: str
    literal_index: int | None = None
    label: str | None = None
    role: str | None = None  # market | lever | internal | unit


@app.patch("/models/{model_id}/constants")
def edit_constant(model_id: str, edit: LabelEdit):
    """User confirms or corrects a label; the constant is checked again and its impact recalculated."""
    with LOCK:
        report = REPORTS.get(model_id)
        if report is None:
            raise HTTPException(404)
        if report.get("status") == "checking":
            raise HTTPException(409, "this model is still being checked; edit it once its status is done")
        matches = [
            c for c in report["constants"]
            if c["cell"] == edit.cell and (edit.literal_index is None or c.get("literal_index") == edit.literal_index)
        ]
        if len(matches) != 1:
            raise HTTPException(404 if not matches else 409, "pass literal_index to pick one literal in this formula")
        if edit.role is not None and edit.role not in labeler.ROLES:
            raise HTTPException(422, f"role must be one of {labeler.ROLES}")
        c = matches[0]
        draft = copy.deepcopy(c)  # edited and checked outside the lock, then swapped in

    if edit.label:
        draft["label"] = edit.label
    if edit.role:
        draft["role"] = edit.role
    role = draft.get("role", "market" if draft.get("driver") else "internal")
    draft["driver"] = labeler.slug(draft["label"]) if role == "market" else None
    draft["label_source"] = "user"
    draft["confirmed"] = True
    if role == "market":
        if edit.label:
            draft["search"] = [draft["label"]]
        # measured before the check so it can reason from which way, and how far, the outputs move
        draft["sensitivity"] = pipeline.sensitivity(report, draft, path=_workbook(model_id))
        draft["check"] = news.check(draft, report["built_on"], report["checked_on"])
    else:
        draft["check"] = None

    with LOCK:
        c.update(draft)
        pipeline.refresh(report, c, path=_workbook(model_id))
        return JSONResponse(c)


def _workbook(model_id: str) -> Path:
    return UPLOADS / f"{model_id}.xlsx"
