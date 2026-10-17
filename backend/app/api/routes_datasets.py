from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select

from ..core.errors import PayloadTooLarge
from ..db.models import Dataset
from ..ml.quality import quality_report
from ..ml.tasks import suggest_targets
from ..schemas.api import DatasetOut
from ..services.datasets import (
    create_dataset,
    create_demo_dataset,
    dataset_frame,
    dataset_preview,
    delete_dataset,
    get_dataset,
)
from .deps import IdPath, SessionDep, SettingsDep, UserDep, get_principal

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(get_principal)])


@router.get("", response_model=list[DatasetOut], summary="List datasets")
def list_datasets(db: SessionDep) -> list[Dataset]:
    return list(db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all())


@router.post("/upload", response_model=DatasetOut, status_code=201, summary="Upload a CSV file")
def upload_dataset(db: SessionDep, settings: SettingsDep, user: UserDep, file: Annotated[UploadFile, File(description="CSV, UTF-8")]) -> Dataset:
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLarge(f"The file exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.", code="file_too_large")
    return create_dataset(db, settings, content, file.filename, actor=user.name)


@router.post("/demo", response_model=DatasetOut, status_code=201, summary="Create a dataset from the bundled SYNTHETIC sample")
def demo_dataset(db: SessionDep, settings: SettingsDep, user: UserDep) -> Dataset:
    return create_demo_dataset(db, settings, actor=user.name)


@router.get("/{dataset_id}", response_model=DatasetOut)
def read_dataset(dataset_id: IdPath, db: SessionDep) -> Dataset:
    return get_dataset(db, dataset_id)


@router.get("/{dataset_id}/profile", summary="Column profile plus suggested target columns")
def dataset_profile(dataset_id: IdPath, db: SessionDep, settings: SettingsDep) -> dict:
    ds = get_dataset(db, dataset_id)
    df = dataset_frame(settings, ds)
    return {
        "dataset": DatasetOut.model_validate(ds).model_dump(mode="json"),
        "profile": ds.profile_json,
        "target_suggestions": suggest_targets(df),
        "note": "Suggested targets are guesses. Confirm the column you actually want to predict.",
    }


@router.get("/{dataset_id}/quality", summary="Data-quality report")
def dataset_quality(dataset_id: IdPath, db: SessionDep, settings: SettingsDep) -> dict:
    ds = get_dataset(db, dataset_id)
    return quality_report(dataset_frame(settings, ds))


@router.get("/{dataset_id}/preview", summary="First rows of the dataset")
def preview(dataset_id: IdPath, db: SessionDep, settings: SettingsDep, rows: Annotated[int, Query(ge=1, le=200)] = 50) -> dict:
    return dataset_preview(dataset_frame(settings, get_dataset(db, dataset_id)), rows)


@router.delete("/{dataset_id}", status_code=204, summary="Delete a dataset and everything derived from it")
def remove_dataset(dataset_id: IdPath, db: SessionDep, settings: SettingsDep, user: UserDep) -> None:
    delete_dataset(db, settings, get_dataset(db, dataset_id), actor=user.name)
