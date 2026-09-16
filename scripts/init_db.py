from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.db import Store
from app.service import setup_checkpoints
root=Path(__file__).resolve().parents[1]
with Store().connection() as conn:
    conn.execute((root/"database/schema.sql").read_text(),prepare=False)
    conn.execute((root/"database/seed.sql").read_text(),prepare=False)
setup_checkpoints()
print("Schema and synthetic seed data initialized")
