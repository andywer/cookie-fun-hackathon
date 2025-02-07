from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, create_engine, func, select
from sqlalchemy.orm import Mapped, Session, declarative_base, relationship


storage_path = Path(__file__).parent.parent.parent / "storage"
db_path = storage_path / "cookiefun.sqlite"

Base = declarative_base()


def open_cookiefun_db():
    """
    Open the cookiefun database and create the tables if they don't exist.

    :return: A session to the database.

    Example:
    ```python
    with open_cookiefun_db() as session:
        session.add(IngestionRunRecord(created_at=datetime.now()))
        session.commit()
    ```
    """
    engine = create_engine(f"sqlite:///{db_path.absolute()}")

    Base.metadata.create_all(engine)
    return Session(engine)


class IngestionRunRecord(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = Column(Integer, primary_key=True)
    created_at: Mapped[datetime] = Column(DateTime, default=func.now())
    delta_interval_time: Mapped[str] = Column(String)

    agents: Mapped[List['HistoricAgentRecord']] = relationship(back_populates="ingestion_run")
    batch_analyses: Mapped[List['BatchAnalysisRecord']] = relationship(back_populates="ingestion_run")

    @property
    def is_finished(self) -> bool:
        return self.created_at < datetime.now() - timedelta(minutes=1)

    def eagerly_load_all(self):
        for agent in self.agents:
            # This is a hack to eagerly load the ingestion_run relationship backwards, too
            _ = agent.ingestion_run


class HistoricAgentRecord(Base):
    __tablename__ = "historic_agent_records"

    id: Mapped[int] = Column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = Column(Integer, ForeignKey("ingestion_runs.id"))
    agent_name: Mapped[str] = Column(String)
    created_at: Mapped[datetime] = Column(DateTime, default=func.now())
    data: Mapped[dict] = Column(JSON)

    ingestion_run: Mapped[IngestionRunRecord] = relationship(back_populates="agents")

    @classmethod
    def get_by_twitter_handle(cls, session: Session, twitter_handle: str) -> 'HistoricAgentRecord | None':
        query = select(cls).where(func.json_extract(cls.data, '$.twitterUsernames[0]') == twitter_handle)
        query = query.order_by(cls.ingestion_run_id.desc()).limit(1)
        return session.execute(query).scalar_one_or_none()


class BatchAnalysisRecord(Base):
    __tablename__ = "batch_analysis_records"

    id: Mapped[int] = Column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = Column(Integer, ForeignKey("ingestion_runs.id"))
    input_agent_ids: Mapped[str] = Column(String)
    created_at: Mapped[datetime] = Column(DateTime, default=func.now())
    analysis_type: Mapped[str] = Column(String)
    analysis: Mapped[str] = Column(String)
    top_agent_ids: Mapped[List[int]] = Column(JSON)
    meta: Mapped[dict] = Column(JSON, default={})

    ingestion_run: Mapped[IngestionRunRecord] = relationship(back_populates="batch_analyses")

    @staticmethod
    def serialize_agent_ids(agent_ids: List[int]) -> str:
        return ",".join([str(id) for id in sorted(agent_ids)])

    @classmethod
    def query(cls, session: Session, analysis_type: str, run_id: int, input_agent_ids: str) -> 'BatchAnalysisRecord | None':
        query = select(cls).where(cls.ingestion_run_id == run_id, cls.input_agent_ids == input_agent_ids, cls.analysis_type == analysis_type).order_by(cls.created_at.desc())
        return session.execute(query).scalars().first()

    def eagerly_load_all(self):
        self.ingestion_run.eagerly_load_all()
