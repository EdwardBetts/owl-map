"""Database."""

from datetime import datetime

import flask
import sqlalchemy
from sqlalchemy import create_engine, func
from sqlalchemy.engine import reflection
from sqlalchemy.orm import scoped_session, sessionmaker

session: sqlalchemy.orm.scoping.scoped_session = scoped_session(sessionmaker())

timeout = 20_000  # 20 seconds


def init_db(db_url: str, echo: bool = False) -> None:
    """Initialise database."""
    session.configure(bind=get_engine(db_url, echo=echo))


def get_engine(db_url: str, echo: bool = False) -> sqlalchemy.engine.base.Engine:
    """Create an engine object."""
    return create_engine(
        db_url,
        pool_recycle=3600,
        echo=echo,
        connect_args={
            "options": f"-c lock_timeout={timeout} -c statement_timeout={timeout}"
        },
    )


def get_tables() -> list[str]:
    """Get a list of table names."""
    tables: list[str] = reflection.Inspector.from_engine(session.bind).get_table_names()
    return tables


def init_app(app: flask.app.Flask, echo: bool = False) -> None:
    """Initialise database connection within flask app."""
    db_url = app.config["DB_URL"]
    session.configure(bind=get_engine(db_url, echo=echo))

    @app.teardown_appcontext
    def shutdown_session(exception: BaseException | None = None) -> None:
        session.remove()


def now_utc() -> sqlalchemy.sql.functions.Function[datetime]:
    """Now with UTC timezone."""
    return func.timezone("utc", func.now())
