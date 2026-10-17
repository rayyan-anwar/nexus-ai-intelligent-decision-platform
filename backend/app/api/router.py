from fastapi import APIRouter

from . import routes_analysis, routes_core, routes_datasets, routes_experiments, routes_models

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(routes_core.public)
api_router.include_router(routes_core.router)
api_router.include_router(routes_datasets.router)
api_router.include_router(routes_experiments.router)
api_router.include_router(routes_models.router)
api_router.include_router(routes_analysis.router)
