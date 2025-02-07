from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, create_engine, func, select
from sqlalchemy.orm import Mapped, Session, declarative_base, relationship


storage_path = Path(__file__).parent.parent.parent / "storage"
db_path = storage_path / "agent_output_analyses.sqlite"

Base = declarative_base()


def open_agent_output_analyses_db():
    """
    Open the agent output analyses database and create the tables if they don't exist.

    :return: A session to the database.

    Example:
    ```python
    with open_agent_output_analyses_db() as session:
        session.add(AgentOutputAnalysisRecord(created_at=datetime.now()))
        session.commit()
    ```
    """
    engine = create_engine(f"sqlite:///{db_path.absolute()}")

    Base.metadata.create_all(engine)
    return Session(engine)


class AgentOutputAnalysisRecord(Base):
    __tablename__ = "agent_output_analyses"

    id: Mapped[int] = Column(Integer, primary_key=True)
    created_at: Mapped[datetime] = Column(DateTime, default=func.now())

    source_url: Mapped[str] = Column(String)
    analysis: Mapped[str] = Column(String)
    meta: Mapped[dict] = Column(JSON, default={})
