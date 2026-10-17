from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from ..core.errors import PayloadTooLarge
from ..db.models import ModelRecord
from ..ml.explain import explain_instance, global_importance
from ..ml.ingest import load_csv_bytes, to_safe_csv
from ..ml.pipeline import predict_records, predictions_frame
from ..schemas.api import LocalExplainRequest, ModelOut, PredictRequest
from ..services.models import delete_model, get_bundle, get_model, record_csv_prediction, record_prediction
from .deps import IdPath, SessionDep, SettingsDep, UserDep, get_principal

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(get_principal)])


def _out(m: ModelRecord) -> ModelOut:
    summary = m.experiment.summary_json or {}
    spec = summary.get("primary_metric") or {}
    score = (summary.get("test_metrics") or {}).get(spec.get("name"))
    return ModelOut(id=m.id, experiment_id=m.experiment_id, name=m.name, task=m.task, target=m.target, created_at=m.created_at,
                    primary_metric=spec.get("name"), test_score=score)


@router.get("", response_model=list[ModelOut], summary="List trained models")
def list_models(db: SessionDep) -> list[ModelOut]:
    return [_out(m) for m in db.scalars(select(ModelRecord).order_by(ModelRecord.created_at.desc()).limit(200)).all()]


@router.get("/{model_id}", summary="Model details, including the input schema for building forms")
def read_model(model_id: IdPath, db: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    m = get_model(db, model_id)
    bundle = get_bundle(settings, m)
    return {
        **_out(m).model_dump(mode="json"),
        "schema": bundle.schema.to_dict(),
        "interval": bundle.metadata.get("interval"),
        "classes": bundle.metadata["classes"],
        "positive_label": bundle.metadata["positive_label"],
    }


@router.post("/{model_id}/predict", summary="Predict for one or more records")
def predict(model_id: IdPath, body: PredictRequest, db: SessionDep, settings: SettingsDep, user: UserDep) -> dict[str, Any]:
    m = get_model(db, model_id)
    result = predict_records(get_bundle(settings, m), body.records)
    record_prediction(db, m, body.records, result, user.name)
    return result


@router.post("/{model_id}/predict/csv", summary="Predict for every row of an uploaded CSV and return a CSV", response_class=Response)
async def predict_csv(model_id: IdPath, db: SessionDep, settings: SettingsDep, user: UserDep, file: Annotated[UploadFile, File()]) -> Response:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLarge("The file exceeds the upload limit.", code="file_too_large")

    def work() -> str:
        m = get_model(db, model_id)
        df = load_csv_bytes(content, max_bytes=settings.max_upload_bytes, max_rows=settings.max_rows, max_cols=settings.max_cols)
        out = predictions_frame(get_bundle(settings, m), df, max_records=settings.max_rows)
        record_csv_prediction(db, m, content, out, user.name)
        return to_safe_csv(out)

    csv_text = await run_in_threadpool(work)
    return Response(csv_text, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="nexus-predictions.csv"', "Cache-Control": "no-store"})


@router.get("/{model_id}/explanations", summary="Global feature importance with interpretation and warnings")
def global_explanations(model_id: IdPath, db: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    m = get_model(db, model_id)
    return global_importance(get_bundle(settings, m), m.experiment.summary_json)


@router.post("/{model_id}/explanations/local", summary="Explain one prediction (Monte-Carlo Shapley)")
def local_explanation(model_id: IdPath, body: LocalExplainRequest, db: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    m = get_model(db, model_id)
    return explain_instance(get_bundle(settings, m), body.record, target_class=body.target_class, n_permutations=body.n_permutations, seed=body.seed)


@router.delete("/{model_id}", status_code=204, summary="Delete a model and its artifact")
def remove_model(model_id: IdPath, db: SessionDep, settings: SettingsDep, user: UserDep) -> None:
    delete_model(db, settings, get_model(db, model_id), user.name)
