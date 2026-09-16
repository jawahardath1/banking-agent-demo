import logging
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from .config import settings
from .db import Store
from .graph import build_graph
from .providers import Providers

logger = logging.getLogger(__name__)


@contextmanager
def checkpoint_saver():
    # Disable server-side prepared statements for compatibility with SQL proxies.
    with psycopg.connect(settings.database_url, autocommit=True, prepare_threshold=None, row_factory=dict_row) as conn:
        yield PostgresSaver(conn)



def execute(run_id, initial=None):
    store = Store()
    try:
        with store.lock(run_id):
            run = store.read(run_id)
            if run["status"] in ("COMPLETED", "DECLINED"):
                return
            with checkpoint_saver() as saver:
                graph = build_graph(store, Providers(), saver)
                config = {"configurable": {"thread_id": run_id}}
                snapshot = graph.get_state(config)
                if snapshot.values:
                    if snapshot.next == ("approve",) and run["decision"] is not None:
                        argument = Command(resume=run["decision"]["approved"])
                    else:
                        argument = None
                else:
                    argument = initial or {"run_id":run_id,"application_id":run["application_id"],"request":"Review against all synthetic policies"}
                graph.invoke(argument, config)
                state = graph.get_state(config)
                store.status(run_id, "AWAITING_APPROVAL" if state.next else "COMPLETED" if state.values.get("case_id") else "DECLINED")
    except Exception:
        logger.exception("Review %s failed",run_id)
        store.status(run_id,"FAILED","Review failed. Check backend logs and configuration, then retry this run.")


def setup_checkpoints():
    with checkpoint_saver() as saver:
        saver.setup()
