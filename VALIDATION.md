# Validation record

Date: 2026-09-15

## Passed

- 17 Python tests: 12 unit/workflow/provider-contract tests and 5 database integration tests.
- 2 React UI tests.
- Vite production build.
- Python source compilation and Compose YAML parsing.
- Running FastAPI + React browser flow: L002 retrieved, four cited risks shown, Enhanced Manual Review recommended, explicit approval controls displayed, approval recorded, case created, completed run restored after browser refresh.
- Repeatable HTTP demo script with `--approve`: passed; repeating approval returned the same case ID.
- Failure injection immediately after case creation: retry resumed from the persisted LangGraph checkpoint and reused the existing case.
- Early approval rejected, declined case creation produced no case, conflicting repeated decisions rejected, repeated ingestion left exactly six policy chunks.

## Runtime used here

Python 3.13, Node 24, and PGlite PostgreSQL/pgvector through a local TCP socket. SQL schemas, JSONB, pgvector similarity queries, and the PostgreSQL LangGraph checkpointer were exercised. The optional test runtime is in `devtools/`. Default deterministic demo providers were used; Bedrock request shapes were tested with a fake client.

## Not verified here

- Docker image builds, Docker networking, and native PostgreSQL 17 execution: Docker is not installed/on the command path in this environment. Compose configuration was authored and parsed but not executed.
- Real Bedrock Claude/Titan inference: no model ID or AWS credentials were supplied. Configure `.env` and re-ingest in Bedrock mode to test against your account.
- Native PostgreSQL concurrency under simultaneous requests. PGlite multiplexes connections and is suitable here only for serial local smoke tests.

There is one upstream Starlette/AnyIO deprecation warning in the Python test client; the tests pass.

## Local preview

The preview was started at http://127.0.0.1:5173 with the API at http://127.0.0.1:8000 and the optional test database at port 55432. These are local development processes. Use the README to restart them or to run the intended Docker Compose stack.

## Live AWS follow-up

- Titan Text Embeddings V2 invoked successfully with the updated credentials and returned 1,024 dimensions.
- The direct Claude Haiku 4.5 model ID rejected on-demand invocation. The account lists an active US inference profile, `us.anthropic.claude-haiku-4-5-20251001-v1:0`; `.env` now uses it.
- Invocation through that profile is blocked by AWS: the IAM principal lacks the Marketplace actions required to enable model access (`aws-marketplace:ViewSubscriptions` and `aws-marketplace:Subscribe`). No Marketplace subscription was created.
- AI_MODE remains demo and the existing demo embeddings remain intact until Claude model access is enabled. The local database URL now points to the running test database on port 55432.

## Live Bedrock token validation — successful

A subsequent short-term Bedrock token resolved the access blocker above. The running backend now uses AI_MODE=bedrock and the US Claude Haiku 4.5 inference profile. All six policy sections were re-embedded with Titan Text Embeddings V2 (1,024 dimensions) and stored in pgvector.

The HTTP acceptance script passed against the running backend: L002 received Enhanced Manual Review with four cited risks, paused with no case before approval, and created case `1f5813be-19ce-4f83-bc42-94cdf6f4cfbe` after the test's explicit approval. Repeated approval reused the same case. Database records and the frontend proxy health endpoint were independently checked.

Claude search planning and assessment explanation were real Bedrock calls. The database remains the local PGlite/pgvector runtime; Docker/native PostgreSQL validation remains outstanding. Replace the token and restart the backend when it expires.
