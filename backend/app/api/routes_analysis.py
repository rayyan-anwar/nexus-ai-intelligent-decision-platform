from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool

from ..core.errors import Unprocessable
from ..ml.anomaly import anomaly_table, detect_anomalies
from ..ml.drift import DriftConfig, analyze_drift
from ..ml.ingest import to_safe_csv
from ..schemas.api import AnomalyRequest, DriftRequest
from ..services.datasets import dataset_frame, get_dataset, require_columns
from .deps import SessionDep, SettingsDep, get_principal

router = APIRouter(tags=["analysis"], dependencies=[Depends(get_principal)])


@router.post("/anomalies/detect", summary="Detect unusual records with Isolation Forest")
async def detect(body: AnomalyRequest, db: SessionDep, settings: SettingsDep) -> dict:
    ds = get_dataset(db, body.dataset_id)
    require_columns(ds, body.columns)
    df = dataset_frame(settings, ds)
    result = await run_in_threadpool(
        lambda: detect_anomalies(df, sensitivity=body.sensitivity, seed=body.seed, columns=body.columns, max_rows=body.max_rows)
    )
    if not body.include_scores:
        result.pop("scores")
    return result


@router.post("/anomalies/export", summary="Download flagged records as CSV", response_class=Response)
async def export_anomalies(body: AnomalyRequest, db: SessionDep, settings: SettingsDep) -> Response:
    ds = get_dataset(db, body.dataset_id)
    require_columns(ds, body.columns)
    df = dataset_frame(settings, ds)

    def work() -> str:
        result = detect_anomalies(df, sensitivity=body.sensitivity, seed=body.seed, columns=body.columns)
        return to_safe_csv(anomaly_table(df, result))

    text = await run_in_threadpool(work)
    return Response(text, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nexus-anomalies.csv"', "Cache-Control": "no-store"})


@router.post("/drift/analyze", summary="Compare a new dataset against a reference dataset")
async def drift(body: DriftRequest, db: SessionDep, settings: SettingsDep) -> dict:
    ref, cur = get_dataset(db, body.reference_dataset_id), get_dataset(db, body.current_dataset_id)
    require_columns(ref, body.columns)
    ref_df, cur_df = dataset_frame(settings, ref), dataset_frame(settings, cur)
    cfg = DriftConfig(**body.thresholds.model_dump())
    try:
        cfg.validate()
    except ValueError as exc:  # defence in depth; the schema already enforces this
        raise Unprocessable(str(exc), code="invalid_thresholds") from exc
    return await run_in_threadpool(lambda: analyze_drift(ref_df, cur_df, cfg, body.columns))
