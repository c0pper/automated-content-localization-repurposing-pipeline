"""HTTP routes."""

from fastapi import APIRouter

from app.api.routes import health, jobs, webhooks

api_router = APIRouter(prefix="/api")
api_router.include_router(jobs.router)
api_router.include_router(webhooks.router)

root_router = APIRouter()
root_router.include_router(health.router)
