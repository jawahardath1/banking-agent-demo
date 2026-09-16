import re
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, StrictBool
from .config import settings
from .db import Store
from .service import execute, setup_checkpoints
from .tools import get_loan_application


@asynccontextmanager
async def lifespan(app):
    setup_checkpoints()
    # Work is durable, but interrupted local background jobs require explicit retry.
    with Store().connection() as conn:
        conn.execute("UPDATE review_runs SET status='FAILED', error='Backend restarted. Retry to continue from the saved checkpoint.' WHERE status='RUNNING'")
    yield


app = FastAPI(title="DemoBank Loan Review", lifespan=lifespan)


class ReviewRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class DecisionRequest(BaseModel):
    approved: StrictBool
    reviewer: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")


@app.get("/api/health")
def health():
    with Store().connection() as conn:
        conn.execute("SELECT 1")
        rows = conn.execute("SELECT embedding_model,count(*) AS count FROM policy_chunks GROUP BY embedding_model").fetchall()
    return {"status":"ok","mode":settings.ai_mode,"policies":rows}


@app.get("/api/applications/{application_id}")
def application(application_id: str):
    try:
        return get_loan_application(Store(),application_id)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc


@app.post("/api/reviews",status_code=202)
def review(body: ReviewRequest, background: BackgroundTasks):
    ids = set(re.findall(r"\bL[0-9]{3}\b",body.message.upper()))
    if len(ids) != 1:
        raise HTTPException(422,"Include exactly one application ID, such as L002")
    application_id = ids.pop()
    application(application_id)
    run_id = Store().new_run(application_id)
    background.add_task(execute,run_id,{"run_id":run_id,"application_id":application_id,"request":body.message})
    return {"run_id":run_id}


@app.get("/api/reviews/{run_id}")
def read_review(run_id: UUID):
    try:
        return Store().read(str(run_id))
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc


@app.post("/api/reviews/{run_id}/decision",status_code=202)
def decision(run_id: UUID, body: DecisionRequest, background: BackgroundTasks):
    try:
        Store().decide(str(run_id),body.approved,body.reviewer.strip())
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    background.add_task(execute,str(run_id))
    return {"run_id":str(run_id),"approved":body.approved}


@app.post("/api/reviews/{run_id}/retry",status_code=202)
def retry(run_id: UUID, background: BackgroundTasks):
    run = read_review(run_id)
    if run["status"] != "FAILED":
        raise HTTPException(409,"Only failed runs can be retried")
    Store().status(str(run_id),"RUNNING")
    background.add_task(execute,str(run_id))
    return {"run_id":str(run_id)}
