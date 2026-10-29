"""HTTP routes."""
from fastapi import APIRouter

from app.api.routes import auth, health, jobs, review, uploads, webhooks, workspace

api_router = APIRouter(prefix="/api")
api_router.include_router(jobs.router)
api_router.include_router(uploads.router)
api_router.include_router(review.router)
api_router.include_router(webhooks.router)
api_router.include_router(workspace.router)
api_router.include_router(auth.router)

root_router = APIRouter()
root_router.include_router(health.router)