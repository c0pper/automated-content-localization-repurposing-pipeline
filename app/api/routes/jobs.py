"""Job endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ContainerDep
from app.api.schemas import JobAccepted, JobList, JobSubmission
from app.domain.models import Job

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: JobSubmission, container: ContainerDep) -> JobAccepted:
    job = await container.submissions.submit(
        input_url=payload.input_url,
        target_languages=payload.target_languages,
    )
    return JobAccepted(job_id=job.job_id, status=job.status)


@router.get("/jobs", response_model=JobList)
async def list_jobs(container: ContainerDep) -> JobList:
    return JobList(items=await container.repository.list())


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, container: ContainerDep) -> Job:
    job = await container.repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job: {job_id}")
    return job
