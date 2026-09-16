import operator
import re

REQUIRED = {"PL-01", "PL-02", "CR-01", "CR-02", "IV-01", "IV-02"}
FIELDS = {"amount", "term_months", "credit_score", "dti_percent", "income_verified", "employment_months"}
OPERATORS = {"gt": operator.gt, "lt": operator.lt, "eq": operator.eq}


def get_loan_application(store, application_id):
    if not re.fullmatch(r"L[0-9]{3}", application_id):
        raise ValueError("Use an application ID such as L002")
    return store.application(application_id)


def search_bank_policies(store, provider, query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
        raise ValueError("Search query must be 1-500 characters")
    results = store.search(provider.embed(query), provider.embedding_id, limit=12)
    if {x["chunk_id"] for x in results} != REQUIRED:
        raise ValueError("Policy coverage is incomplete or embeddings use a different mode. Run ingestion before reviewing.")
    return results


def evaluate(application, policies):
    checks = []
    for chunk in sorted(policies, key=lambda c: c["chunk_id"]):
        rule = chunk["rule"]
        if rule["field"] not in FIELDS or rule["operator"] not in OPERATORS:
            raise ValueError("Unsupported policy rule")
        actual = application[rule["field"]]
        triggered = OPERATORS[rule["operator"]](actual, rule["value"])
        checks.append({"citation_id": chunk["chunk_id"], "field": rule["field"], "actual": actual,
                       "operator": rule["operator"], "threshold": rule["value"], "requires_review": triggered,
                       "source": chunk["source"], "page": chunk["page"], "excerpt": chunk["content"],
                       "content_hash": chunk["content_hash"]})
    risks = [c for c in checks if c["requires_review"]]
    return {"recommendation": "Enhanced Manual Review" if risks else "Standard Manual Review",
            "checks": checks, "risks": risks,
            "next_action": "Collect two recent pay slips and an employer verification letter; check employment continuity; route to a credit reviewer." if not application["income_verified"] else "Route the assessment to a human credit reviewer.",
            "notice": "Synthetic policy assessment only. This does not approve or decline a loan."}


def create_review_case(store, run_id, application_id, assessment):
    # No caller-supplied approval flag. Store requires an actual saved human decision.
    return store.create_case(run_id, application_id, assessment)
