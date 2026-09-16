import hashlib
import json
from pathlib import Path
from psycopg.types.json import Jsonb
from .config import settings
from .db import Store
from .providers import Providers


def chunks(directory):
    seen = set()
    for path in sorted(Path(directory).glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("synthetic") is not True:
            raise ValueError("Only synthetic policies are allowed")
        for page in document["pages"]:
            for section in page["sections"]:
                # Section-aware chunking preserves each rule and its page boundary.
                chunk_id = section["id"]
                if chunk_id in seen or not 1 <= len(section["text"]) <= 3000:
                    raise ValueError("Duplicate ID or invalid section size")
                seen.add(chunk_id)
                content = section["text"]
                yield {"chunk_id": chunk_id, "source": path.name, "page": page["page"], "content": content,
                       "rule": section["rule"], "content_hash": hashlib.sha256(json.dumps({"version":document["version"],"section":section}, sort_keys=True).encode()).hexdigest()}


def ingest():
    provider, store = Providers(), Store()
    records = list(chunks(settings.documents_dir))
    if {x["chunk_id"] for x in records} != {"PL-01","PL-02","CR-01","CR-02","IV-01","IV-02"}:
        raise ValueError("The complete six-section demo policy set is required")
    # Embed before the transaction so a Bedrock failure leaves the old corpus intact.
    vectors = [provider.embed(x["content"]) for x in records]
    with store.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(71001)")
        conn.execute("DELETE FROM policy_chunks")
        for chunk, vector in zip(records, vectors):
            conn.execute("INSERT INTO policy_chunks(chunk_id,source,page,content,rule,content_hash,embedding_model,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                (chunk["chunk_id"],chunk["source"],chunk["page"],chunk["content"],Jsonb(chunk["rule"]),chunk["content_hash"],provider.embedding_id,str(vector)))
    print(f"Ingested {len(records)} policy sections with {provider.embedding_id}")


if __name__ == "__main__":
    ingest()
