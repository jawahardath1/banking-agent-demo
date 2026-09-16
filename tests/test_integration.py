import os
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.db import Store
from app.ingest import ingest
from app.main import app
from app.tools import create_review_case

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",reason="Set RUN_DB_TESTS=1 with an initialized demo database")]


def test_postgres_end_to_end_approval_and_idempotency():
    ingest()
    with TestClient(app) as client:
        response=client.post("/api/reviews",json={"message":"Review application L002 against lending policies"})
        assert response.status_code==202
        id=response.json()["run_id"]
        run=client.get(f"/api/reviews/{id}").json()
        assert run["status"]=="AWAITING_APPROVAL",run
        assert run["case"] is None
        with pytest.raises(PermissionError): create_review_case(Store(),id,"L002",{})
        assessment=next(e["detail"] for e in run["events"] if e["step"]=="evaluate_application")
        assert assessment["recommendation"]=="Enhanced Manual Review"
        assert len(assessment["risks"])==4
        # Startup with a new app client simulates reload after the interrupt.
    with TestClient(app) as client:
        decision={"approved":True,"reviewer":"Integration Reviewer"}
        assert client.post(f"/api/reviews/{id}/decision",json=decision).status_code==202
        assert client.post(f"/api/reviews/{id}/decision",json=decision).status_code==202
        result=client.get(f"/api/reviews/{id}").json()
        assert result["status"]=="COMPLETED",result
        assert result["case"]["assessment"]==assessment
        assert client.post(f"/api/reviews/{id}/decision",json={**decision,"approved":False}).status_code==409
        with Store().connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM review_cases WHERE run_id=%s",(id,)).fetchone()["n"]==1


def test_reject_and_bad_requests():
    with TestClient(app) as client:
        assert client.post("/api/reviews",json={"message":"Review L001 and L002"}).status_code==422
        assert client.post("/api/reviews",json={"message":"Review L999"}).status_code==404
        id=client.post("/api/reviews",json={"message":"Review L002"}).json()["run_id"]
        assert client.post(f"/api/reviews/{id}/decision",json={"approved":"yes","reviewer":"X"}).status_code==422
        assert client.post(f"/api/reviews/{id}/decision",json={"approved":True,"reviewer":"   "}).status_code==422
        assert client.post(f"/api/reviews/{id}/decision",json={"approved":False,"reviewer":"Tester"}).status_code==202
        run=client.get(f"/api/reviews/{id}").json()
        assert run["status"]=="DECLINED" and run["case"] is None


def test_repeat_ingestion_replaces_without_duplicates():
    ingest(); ingest()
    with Store().connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM policy_chunks").fetchone()["n"]==6


def test_retry_after_case_commit_does_not_duplicate(monkeypatch):
    original = Store.event
    fail_once = [True]
    def event(self, run_id, step, detail):
        if step == "create_review_case" and fail_once[0]:
            fail_once[0] = False
            raise RuntimeError("Injected failure after case commit")
        return original(self,run_id,step,detail)
    monkeypatch.setattr(Store,"event",event)
    with TestClient(app) as client:
        id=client.post("/api/reviews",json={"message":"Review L002"}).json()["run_id"]
        client.post(f"/api/reviews/{id}/decision",json={"approved":True,"reviewer":"Recovery Test"})
        failed=client.get(f"/api/reviews/{id}").json()
        assert failed["status"]=="FAILED" and failed["case"]
        assert client.post(f"/api/reviews/{id}/retry",json={}).status_code==202
        recovered=client.get(f"/api/reviews/{id}").json()
        assert recovered["status"]=="COMPLETED"
        assert recovered["case"]["case_id"]==failed["case"]["case_id"]


def test_approval_before_assessment_is_rejected():
    id=Store().new_run("L002")
    try:
        with pytest.raises(ValueError,match="not awaiting"):
            Store().decide(id,True,"Early Reviewer")
    finally:
        Store().status(id,"FAILED","Intentional early-approval test")
