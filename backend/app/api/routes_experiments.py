from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from ..core.errors import Unprocessable
from ..db.models import Experiment
from ..ml.report import render_html_report
from ..schemas.api import ExperimentCreate, ExperimentOut
from ..services.datasets import get_dataset
from ..services.experiments import create_experiment, get_experiment, require_summary
from .deps import IdPath, SessionDep, SettingsDep, UserDep, get_jobs, get_principal

router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(get_principal)])

REPORT_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


def _scalars(d: dict) -> dict:
    return {k: v for k, v in d.items() if isinstance(v, (int, float)) or v is None}


@router.post("", response_model=ExperimentOut, status_code=202, summary="Start a training experiment (runs in the background)")
def start_experiment(body: ExperimentCreate, request: Request, db: SessionDep, settings: SettingsDep, user: UserDep) -> Experiment:
    return create_experiment(db, settings, get_jobs(request), body.model_dump(), actor=user.name)


@router.get("", response_model=list[ExperimentOut], summary="List experiments")
def list_experiments(db: SessionDep, dataset_id: str | None = Query(None, pattern=r"^[A-Za-z0-9_\-]{1,40}$")) -> list[Experiment]:
    stmt = select(Experiment).order_by(Experiment.created_at.desc())
    if dataset_id:
        stmt = stmt.where(Experiment.dataset_id == dataset_id)
    return list(db.scalars(stmt.limit(200)).all())


@router.get("/compare", summary="Side-by-side comparison of finished experiments")
def compare(db: SessionDep, ids: Annotated[str, Query(description="Comma-separated experiment ids (2-6)")]) -> dict:
    wanted = [i for i in ids.split(",") if i]
    if not 2 <= len(wanted) <= 6:
        raise Unprocessable("Provide between 2 and 6 experiment ids.", code="bad_ids")
    rows = []
    for exp_id in wanted:
        exp = get_experiment(db, exp_id)
        s = require_summary(exp)
        selected = next(c for c in s["candidates"] if c["selected"])
        rows.append({
            "experiment_id": exp.id,
            "dataset_id": exp.dataset_id,
            "target": s["target"],
            "task": s["task"],
            "selected_model": s["selected_model"],
            "primary_metric": s["primary_metric"],
            "validation": _scalars(selected["validation"]),
            "test": _scalars(s["test_metrics"]),
            "baseline_test": _scalars(s["baseline"]["test"]),
            "seed": s["seed"],
            "rows_used": s["rows_used"],
            "candidates": [{"name": c["name"], "validation": _scalars(c["validation"])} for c in s["candidates"]],
        })
    notes = []
    if len({r["task"] for r in rows}) > 1 or len({r["target"] for r in rows}) > 1:
        notes.append("These experiments predict different targets or tasks; their metrics are not directly comparable.")
    return {"experiments": rows, "notes": notes}


@router.get("/{experiment_id}", response_model=ExperimentOut)
def read_experiment(experiment_id: IdPath, db: SessionDep) -> Experiment:
    return get_experiment(db, experiment_id)


@router.get("/{experiment_id}/metrics", summary="Full evaluation results of a finished experiment")
def experiment_metrics(experiment_id: IdPath, db: SessionDep) -> dict:
    return require_summary(get_experiment(db, experiment_id))


@router.get("/{experiment_id}/report", response_class=HTMLResponse, summary="Self-contained HTML report")
def experiment_report(experiment_id: IdPath, db: SessionDep, download: bool = False) -> HTMLResponse:
    exp = get_experiment(db, experiment_id)
    summary = require_summary(exp)
    ds = get_dataset(db, exp.dataset_id)
    html = render_html_report({"id": exp.id}, summary, dataset_name=ds.name)
    headers = dict(REPORT_HEADERS)
    if download:
        headers["Content-Disposition"] = f'attachment; filename="nexus-report-{exp.id}.html"'
    return HTMLResponse(html, headers=headers)
