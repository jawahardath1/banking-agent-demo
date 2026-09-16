CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS customers (
 customer_id integer PRIMARY KEY, name text NOT NULL,
 credit_score integer NOT NULL CHECK(credit_score BETWEEN 300 AND 850),
 annual_income integer NOT NULL CHECK(annual_income > 0),
 dti_percent numeric NOT NULL CHECK(dti_percent BETWEEN 0 AND 100),
 employment_months integer NOT NULL CHECK(employment_months >= 0), income_verified boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS loan_applications (
 application_id text PRIMARY KEY, customer_id integer NOT NULL REFERENCES customers,
 amount integer NOT NULL CHECK(amount > 0), term_months integer NOT NULL CHECK(term_months > 0), status text NOT NULL DEFAULT 'PENDING'
);
CREATE TABLE IF NOT EXISTS policy_chunks (
 chunk_id text PRIMARY KEY, source text NOT NULL, page integer NOT NULL CHECK(page > 0),
 content text NOT NULL, rule jsonb NOT NULL, content_hash text NOT NULL,
 embedding_model text NOT NULL, embedding vector(1024) NOT NULL
);
CREATE TABLE IF NOT EXISTS review_runs (
 run_id uuid PRIMARY KEY, application_id text NOT NULL REFERENCES loan_applications,
 status text NOT NULL DEFAULT 'RUNNING', error text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS run_events (
 event_id bigserial PRIMARY KEY, run_id uuid NOT NULL REFERENCES review_runs,
 step text NOT NULL, detail jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS review_decisions (
 run_id uuid PRIMARY KEY REFERENCES review_runs, approved boolean NOT NULL,
 reviewer text NOT NULL, decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS review_cases (
 case_id uuid PRIMARY KEY, run_id uuid NOT NULL UNIQUE REFERENCES review_runs,
 application_id text NOT NULL REFERENCES loan_applications, recommendation text NOT NULL,
 assessment jsonb NOT NULL, reviewer text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
