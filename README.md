# DemoBank Loan Review Agent

A synthetic banking PoC that connects a React interface, FastAPI, a persistent LangGraph workflow, AWS Bedrock Claude, Titan embeddings, and PostgreSQL with pgvector.

**Acceptance scenario:** Review L002 → retrieve Mary Jones’s synthetic application → retrieve all applicable policy sections → recommend **Enhanced Manual Review** with citations → pause for a human decision → create exactly one review case after approval.

## Start with Docker Compose

Prerequisite: Docker Desktop (or Docker Engine with Compose), with the Docker engine running.

```sh
cp .env.example .env
# PowerShell alternative: Copy-Item .env.example .env
docker compose up --build -d
```

Open **http://localhost:5173**. API documentation is at **http://localhost:8000/docs**.

The database initializes schema and seed data on first startup. A one-shot ingestion service chunks and embeds the policies before the backend starts. The first image build requires internet access. Default `AI_MODE=demo` needs no AWS account and uses deterministic local embeddings and explanations. It still runs the actual LangGraph flow and PostgreSQL/pgvector queries.

```sh
python scripts/demo.py
# Reads the assessment, then asks you to type APPROVE.
# For an explicitly authorized, repeatable acceptance test:
python scripts/demo.py --approve
```

Each invocation creates a new review run. Repeating approval for the same run returns the same case. Declining records the decision without creating a case.

```sh
docker compose logs backend ingest
docker compose down
```

`down` preserves the database volume. To re-ingest edited policies, stop the API while rebuilding the corpus:

```sh
docker compose stop backend
docker compose run --rm ingest
docker compose up -d backend frontend
```

## Enable AWS Bedrock

Set the following in `.env`:

```dotenv
AI_MODE=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=<your enabled Claude model or inference profile ID/ARN>
EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
AWS_ACCESS_KEY_ID=<temporary access key>
AWS_SECRET_ACCESS_KEY=<temporary secret>
AWS_SESSION_TOKEN=<temporary session token>
```

Alternatively, set `AWS_BEARER_TOKEN_BEDROCK` in `.env` to your short-term Bedrock API token. The installed Boto3 runtime reads it automatically. Keep it in `.env` only, never in frontend code or Git. When the token expires, replace it and restart the backend; unchanged Titan policy embeddings do not need to be regenerated. Use `us.anthropic.claude-haiku-4-5-20251001-v1:0` for the US Claude Haiku 4.5 inference profile verified in this PoC.

Use an enabled Claude model supporting Converse tool use and forced tool choice. The identifier depends on your account and region, so the example deliberately leaves it blank. The runtime requires `bedrock:InvokeModel` for Claude and Titan, plus any required inference-profile model resources. Inference incurs AWS charges. The app sends only bundled synthetic policy/application content.

For local Python execution, Boto3 also supports your normal AWS credential chain, including profiles or roles. Docker does not inherit host profiles automatically; use the explicit temporary environment credentials above or configure a read-only AWS credentials mount yourself. Never commit `.env`.

Restart and re-ingest after changing `AI_MODE` or the embedding model. Demo and Bedrock vectors must never be mixed. Retrieval filters by embedding identity and fails closed if the complete corpus is unavailable.

```sh
docker compose stop backend
docker compose run --rm ingest
docker compose up -d --force-recreate backend frontend
```

A Bedrock failure is visible as a failed review; it never silently switches to demo mode. Retry resumes from saved graph state after configuration or connectivity is fixed.

## What the agent does

```mermaid
flowchart LR
  A[Review request] --> B[get_loan_application]
  B --> C[Claude plans policy search]
  C --> D[search_bank_policies / pgvector]
  D --> E[Policy checks + Claude explanation]
  E --> F[LangGraph interrupt]
  F -->|Human approves| G[create_review_case]
  F -->|Human declines| H[Record decision only]
```

This is a **bounded agent workflow**. Claude plans the search query and explains the evidence. The graph enforces required retrieval and approval steps. Explicit rules carried by the synthetic policy documents determine the recommendation; model prose cannot authorize a database write or override a policy check. The user message selects one application; the review always covers all six demo policy checks.

The three database tools expose fixed, parameterized operations. There is no arbitrary SQL tool, `eval`, model-generated SQL, or model-selectable database table. `create_review_case` independently checks the saved human approval and application ID. A unique run ID constraint makes case creation idempotent even if the workflow replays after a crash.

LangGraph checkpoints, execution events, human decisions, and review cases are persisted in PostgreSQL. The UI polls durable execution events and exposes each tool’s result, plus source excerpts and page numbers. The last run survives a browser refresh. Failed jobs can be retried from checkpoints. On a backend restart, unfinished background jobs are marked for explicit retry.

## Synthetic policy documents

The three authoritative documents live in `backend/documents/`:

- `personal-loan-policy.json`: loan amount and term.
- `credit-risk-policy.json`: credit score and debt-to-income ratio.
- `income-verification-policy.json`: verified income and employment tenure.

They are deliberately authored as paginated JSON, with readable prose and a machine-readable rule per section. `documents/policies.md` is a human-readable rendition. Page numbers are the authored logical pages, not inferred PDF pages. This PoC does not include arbitrary PDF parsing or OCR.

Ingestion chunks at section boundaries, preserving each whole rule, source filename, page, stable citation ID, and a SHA-256 version/section hash. Sections are bounded to 3,000 characters. Titan V2 returns normalized 1,024-dimensional vectors. Ingestion embeds first and atomically replaces the six-section corpus, so an embedding failure leaves the existing corpus intact. Re-ingestion cannot create duplicate chunks. For this tiny corpus, retrieval ranks all six applicable rules by cosine similarity; it is deliberately exhaustive to avoid missing a required rule. It uses an exact vector scan, which is appropriate for six rows.

| Check | L002 | Synthetic policy | Result |
|---|---:|---|---|
| Amount | $45,000 | Review above $50,000 [PL-01] | Pass |
| Term | 60 months | Review above 60 months [PL-02] | Pass |
| Credit score | 630 | Review below 660 [CR-01] | Review |
| DTI | 42% | Review above 40% [CR-02] | Review |
| Verified income | No | Review when unverified [IV-01] | Review |
| Employment | 8 months | Review below 12 months [IV-02] | Review |

L001 and L003 satisfy all six checks and receive **Standard Manual Review**. No flow approves or declines the underlying loan, and loan status remains PENDING.

## Local development

Python 3.13 and Node 24 are the tested local runtimes. Use an initialized PostgreSQL 17 instance with pgvector, or start just the database with `docker compose up -d db`.

```sh
python -m venv .venv
# Activate .venv with your platform’s activation command.
pip install -r backend/requirements.lock.txt
python scripts/init_db.py
# Set PYTHONPATH=backend, using your shell's environment syntax.
python -m app.ingest
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

PowerShell environment syntax: `$env:PYTHONPATH='backend'`. The Vite development server proxies `/api` to `127.0.0.1:8000`. Docker uses Nginx for the same-origin proxy.

### Optional local test runtime without Docker

The `devtools` folder provides a pinned PGlite/pgvector socket runtime used for this build's local validation. PGlite runs PostgreSQL in WebAssembly and multiplexes connections; it is not a substitute for validating native PostgreSQL concurrency or Docker networking. Use one review at a time with this fallback.

```sh
npm ci --prefix devtools
npm start --prefix devtools
```

Then follow the local Python setup above with `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable`. In PowerShell:

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable'
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe scripts/init_db.py
.\.venv\Scripts\python.exe -m app.ingest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Local test data lives under ignored `.local/pgdata`. Keep `DATABASE_URL` pointed at the matching runtime when running database tests.

## Tests

```sh
python -m pytest -m "not integration" -q
cd frontend
npm ci
npm test
npm run build
```

For the database suite, initialize the schema and set `RUN_DB_TESTS=1` and `DATABASE_URL` to a disposable **demo** database, then run `python -m pytest -q` from the repository root. Integration tests insert synthetic reviews and re-ingest the six policies. They test actual SQL, vector retrieval, checkpoint resume, approval, rejection, and repeated decisions. Unit tests also cover policy boundaries, incomplete retrieval, constrained IDs, approval bypass, and Bedrock request contracts with a fake client. UI tests verify approval is a separate action and errors are readable.

The checked-in dependency locks capture the installed Python and npm versions. `requirements.txt` documents allowed direct dependency ranges; `requirements.lock.txt` is used by Docker.

## API

- `GET /api/health`: DB health, AI mode, ingestion identity/count.
- `GET /api/applications/L002`: synthetic structured data.
- `POST /api/reviews` with `{ "message": "Review L002" }`: start a run.
- `GET /api/reviews/{run_id}`: status, events, decision, and case.
- `POST /api/reviews/{run_id}/decision` with `{ "approved": true, "reviewer": "Demo Reviewer" }`.
- `POST /api/reviews/{run_id}/retry`: resume a failed run.

## Scope and deployment limits

This is a localhost demo with synthetic data. It has no authentication; the reviewer name is an audit label, not a verified identity. Bindings are loopback-only. Run one backend process; jobs use local background execution rather than a production queue. Do not expose it to a network or use it for real lending. A production system would need identity and authorization, policy governance/version applicability, a job queue, operational monitoring, least-privilege database roles, and a reviewed credit decision process.

The graph fixes mandatory steps rather than exposing an open-ended tool loop. Generated explanatory prose is labeled as a summary; the cited checks are authoritative. An existing assessment keeps its original application snapshot and policy excerpts through approval. To review changed data or policies, start a fresh run.

## Reference APIs

- [LangGraph interrupt and resume](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [PostgreSQL checkpointer](https://reference.langchain.com/python/langgraph/checkpoint/postgres)
- [AWS Bedrock Converse](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html)
- [Titan embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html)

See `VALIDATION.md` for what was actually exercised in the build environment.
