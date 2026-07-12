import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

RAW_CONNECTION_STRING = os.getenv("DATABASE_URL")


def _to_psycopg_url(url: str) -> str:
    # PostgresSaver talks to Postgres via raw psycopg, not SQLAlchemy — it needs a plain "postgresql://" URL, not SQLAlchemy's "postgresql+psycopg://" dialect syntax.
    return url.replace("postgresql+psycopg://", "postgresql://")


_pool: ConnectionPool | None = None
_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    # Long-lived checkpointer backed by a connection pool — safe to reuse across every agent.invoke() call for the life of the app.
    global _pool, _checkpointer
    if _checkpointer is None:
        _pool = ConnectionPool(
            conninfo=_to_psycopg_url(RAW_CONNECTION_STRING),
            kwargs={"autocommit": True, "row_factory": dict_row},
            max_size=10,
            open=True,
        )
        _checkpointer = PostgresSaver(_pool)
    return _checkpointer


def init_checkpoint_tables():
    # Run this ONCE (e.g. in setup_db.py) before your app goes live. .setup() creates the checkpoint tables only if they don't already exist — safe to call again later, it won't wipe existing conversation history.
    with PostgresSaver.from_conn_string(_to_psycopg_url(RAW_CONNECTION_STRING)) as checkpointer:
        checkpointer.setup()