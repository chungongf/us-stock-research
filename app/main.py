import asyncio
import secrets
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from . import config, llm, pipeline

app = FastAPI(title="US Stock Research")
security = HTTPBasic(auto_error=False)
STATIC = Path(__file__).parent / "static"

JOBS: "OrderedDict[str, dict]" = OrderedDict()
MAX_JOBS_KEPT = 50
_slots = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
_tasks: set[asyncio.Task] = set()


def auth(creds: HTTPBasicCredentials | None = Depends(security)):
    if not config.APP_PASSWORD:
        return
    if creds is None or not secrets.compare_digest(creds.password.encode(), config.APP_PASSWORD.encode()):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})


class RunRequest(BaseModel):
    filters: str = config.DEFAULTS["filters"]
    order: str = config.DEFAULTS["order"]
    tickers: str = config.DEFAULTS["tickers"]
    userCriteria: str = config.DEFAULTS["userCriteria"]
    maxStocksToEvaluate: int = config.DEFAULTS["maxStocksToEvaluate"]
    horizonYears: int = config.DEFAULTS["horizonYears"]
    minConviction: int = config.DEFAULTS["minConviction"]
    maxDocChars: int = config.DEFAULTS["maxDocChars"]


async def _run_job(job_id: str, cfg: dict):
    job = JOBS[job_id]

    def log(msg: str):
        job["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")

    async with _slots:
        job["status"] = "running"
        try:
            job["result"] = await pipeline.run(cfg, log)
            job["status"] = "done"
        except Exception as e:
            log(f"ERROR: {e}")
            job["status"] = "error"
            job["error"] = str(e)
        job["finishedAt"] = time.time()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", dependencies=[Depends(auth)])
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/defaults", dependencies=[Depends(auth)])
def defaults():
    return {**config.DEFAULTS, "llm": llm.provider_label(), "secConfigured": bool(config.SEC_USER_AGENT)}


@app.post("/api/run", dependencies=[Depends(auth)])
async def run(req: RunRequest):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"id": job_id, "status": "queued", "config": req.model_dump(), "log": [],
                    "result": None, "error": None, "createdAt": time.time(), "finishedAt": None}
    while len(JOBS) > MAX_JOBS_KEPT:
        JOBS.popitem(last=False)
    task = asyncio.create_task(_run_job(job_id, req.model_dump()))
    _tasks.add(task)  # keep a reference so the task isn't garbage-collected mid-run
    task.add_done_callback(_tasks.discard)
    return {"id": job_id}


@app.get("/api/jobs/{job_id}", dependencies=[Depends(auth)])
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found (jobs are kept in memory and reset on redeploy).")
    return JOBS[job_id]


@app.get("/api/jobs", dependencies=[Depends(auth)])
def jobs():
    return [{k: j[k] for k in ("id", "status", "createdAt")} | {"result": (j["result"] or {}).get("result")}
            for j in reversed(JOBS.values())]
