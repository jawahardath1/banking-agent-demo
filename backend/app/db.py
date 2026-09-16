import uuid
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import settings


class Store:
    @contextmanager
    def connection(self):
        with psycopg.connect(settings.database_url, row_factory=dict_row, prepare_threshold=None) as conn:
            yield conn

    def application(self, application_id):
        with self.connection() as conn:
            row = conn.execute("SELECT a.*, c.name, c.credit_score, c.annual_income, c.dti_percent::float8, c.employment_months, c.income_verified FROM loan_applications a JOIN customers c USING(customer_id) WHERE application_id=%s", (application_id,)).fetchone()
        if not row:
            raise LookupError("Application not found")
        return row

    def search(self, vector, embedding_id, limit=12):
        # A tiny demo corpus: retrieve all six required sections, ranked by cosine distance.
        # A real corpus needs version/applicability filtering and a coverage strategy.
        with self.connection() as conn:
            return conn.execute("SELECT chunk_id,source,page,content,rule,content_hash,1-(embedding <=> %s::vector) AS similarity FROM policy_chunks WHERE embedding_model=%s ORDER BY embedding <=> %s::vector LIMIT %s", (str(vector), embedding_id, str(vector), limit)).fetchall()

    def event(self, run_id, step, detail):
        with self.connection() as conn:
            conn.execute("INSERT INTO run_events(run_id,step,detail) VALUES (%s,%s,%s)", (run_id,step,Jsonb(detail)))

    def new_run(self, application_id):
        run_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("INSERT INTO review_runs(run_id,application_id) VALUES (%s,%s)", (run_id,application_id))
        return run_id

    def status(self, run_id, status, error=None):
        with self.connection() as conn:
            conn.execute("UPDATE review_runs SET status=%s,error=%s WHERE run_id=%s", (status,error,run_id))

    def read(self, run_id):
        with self.connection() as conn:
            run = conn.execute("SELECT * FROM review_runs WHERE run_id=%s", (run_id,)).fetchone()
            if not run:
                raise LookupError("Review not found")
            run["events"] = conn.execute("SELECT event_id,step,detail,created_at FROM run_events WHERE run_id=%s ORDER BY event_id", (run_id,)).fetchall()
            run["case"] = conn.execute("SELECT * FROM review_cases WHERE run_id=%s", (run_id,)).fetchone()
            run["decision"] = conn.execute("SELECT approved,reviewer,decided_at FROM review_decisions WHERE run_id=%s", (run_id,)).fetchone()
        return run

    def decide(self, run_id, approved, reviewer):
        with self.connection() as conn:
            run = conn.execute("SELECT status FROM review_runs WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
            if not run:
                raise LookupError("Review not found")
            old = conn.execute("SELECT approved FROM review_decisions WHERE run_id=%s", (run_id,)).fetchone()
            if old:
                if old["approved"] != approved:
                    raise ValueError("A different decision has already been recorded")
                return False
            if run["status"] != "AWAITING_APPROVAL":
                raise ValueError("Review is not awaiting approval")
            conn.execute("INSERT INTO review_decisions(run_id,approved,reviewer) VALUES (%s,%s,%s)", (run_id,approved,reviewer))
            conn.execute("UPDATE review_runs SET status='RUNNING',error=NULL WHERE run_id=%s", (run_id,))
        return True

    def create_case(self, run_id, application_id, assessment):
        with self.connection() as conn:
            decision = conn.execute("SELECT d.approved,d.reviewer,r.application_id FROM review_decisions d JOIN review_runs r USING(run_id) WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
            if not decision or not decision["approved"] or decision["application_id"] != application_id:
                raise PermissionError("Recorded human approval for this application is required")
            row = conn.execute("INSERT INTO review_cases(case_id,run_id,application_id,recommendation,assessment,reviewer) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET run_id=EXCLUDED.run_id RETURNING case_id", (str(uuid.uuid4()),run_id,application_id,assessment["recommendation"],Jsonb(assessment),decision["reviewer"])).fetchone()
        return str(row["case_id"])

    @contextmanager
    def lock(self, run_id):
        # Session advisory lock serializes each run, including across API processes.
        with self.connection() as conn:
            conn.autocommit = True
            conn.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (run_id,))
            try:
                yield
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (run_id,))
