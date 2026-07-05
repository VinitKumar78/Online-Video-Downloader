"""
app/services/job_store.py
---------------------------
Thread-safe in-memory store for download job state.

Each download runs in a background thread (see downloader.py), so multiple
threads read/write job state concurrently. A plain dict would be subject to
race conditions under concurrent requests; wrapping access with a lock and a
small typed model keeps state consistent and keeps route code from ever
touching a raw dict.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Optional


class JobStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.RUNNING
    progress: str = "0%"
    filename: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class JobStore:
    """In-memory, thread-safe registry of download jobs."""

    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def all_jobs(self):
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


# A single shared instance for the whole application (simple, adequate for
# a single-process dev server; would move to Redis for a multi-worker
# production deployment).
job_store = JobStore()
