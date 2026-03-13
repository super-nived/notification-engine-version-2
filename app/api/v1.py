from fastapi import APIRouter

from app.features.rules.router import router as rules_router

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(rules_router)
