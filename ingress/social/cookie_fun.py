import asyncio
import os
from typing import List, Literal

from pydantic import BaseModel
import aiohttp

from app.storage.cookie_fun import HistoricAgentRecord, IngestionRunRecord, open_cookiefun_db


class Contract(BaseModel):
    chain: int
    contractAddress: str


class BestTweet(BaseModel):
    tweetUrl: str
    tweetAuthorProfileImageUrl: str
    tweetAuthorDisplayName: str
    smartEngagementPoints: int
    impressionsCount: int


class AgentDetails(BaseModel):
    agentName: str
    contracts: List[Contract]
    twitterUsernames: List[str]
    mindshare: float
    mindshareDeltaPercent: float
    mindshareDeltaPercent: float
    marketCap: float
    marketCapDeltaPercent: float
    price: float
    priceDeltaPercent: float
    liquidity: float
    volume24Hours: float
    volume24HoursDeltaPercent: float
    holdersCount: float
    holdersCountDeltaPercent: float
    averageImpressionsCount: float
    averageImpressionsCountDeltaPercent: float
    averageEngagementsCount: float
    averageEngagementsCountDeltaPercent: float
    followersCount: int
    smartFollowersCount: int
    topTweets: List[BestTweet]


class CookieFunAPI:
    BASE_URL = "https://api.cookie.fun/v2/"

    def __init__(self, api_key: str):
        self.headers = {
            "x-api-key": api_key,
        }

    async def fetch_page(self, page: int, limit: int = 15, interval: Literal["_3Days", "_7Days"] = "_3Days") -> List[AgentDetails]:
        """Fetch a page of projects from the Cookie Fun API."""
        params = {
            "interval": interval,
            "page": page,
            "pageSize": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.BASE_URL + "agents/agentsPaged",
                params=params,
                headers=self.headers,
            ) as response:
                if response.status != 200:
                    raise ValueError(f"API request failed with status {response.status}")

                data = await response.json()
                # The API returns a list with a single item containing the actual response
                if not data or 'ok' not in data or 'data' not in data['ok'] or not isinstance(data['ok']['data'], list):
                    raise ValueError("Invalid API response format")

                return [AgentDetails(**item) for item in data['ok']['data']]


class CookieFunIngestion:
    def get_ingestion_run_by_id(self, run_id: str) -> IngestionRunRecord | None:
        from sqlalchemy import select

        with open_cookiefun_db() as session:
            result = session.get(IngestionRunRecord, run_id)
            # Ensure projects are loaded before session closes
            if result:
                result.eagerly_load_all()
            return result

    def get_last_ingestion_run(self) -> IngestionRunRecord | None:
        from sqlalchemy import select

        with open_cookiefun_db() as session:
            query = select(IngestionRunRecord).order_by(IngestionRunRecord.created_at.desc()).limit(1)
            result = session.execute(query).scalar_one_or_none()
            # Ensure projects are loaded before session closes
            if result:
                result.eagerly_load_all()
            return result

    async def ingest(
        self,
        api: CookieFunAPI = CookieFunAPI(os.getenv("COOKIE_FUN_API_KEY")),
        max_pages: int = 15,
        page_size: int = 25,
        sleep_time: float = 0.5,
        delta_interval: Literal["_3Days", "_7Days"] = "_3Days",
    ) -> IngestionRunRecord:
        with open_cookiefun_db() as session:
            ingestion_run = IngestionRunRecord(delta_interval_time=delta_interval)
            session.add(ingestion_run)
            session.commit()
            session.refresh(ingestion_run)

        for page in range(1, max_pages):
            agents = await api.fetch_page(page=page, limit=page_size, interval=delta_interval)

            with open_cookiefun_db() as session:
                for agent in agents:
                    # Use model_dump with datetime handling
                    record = HistoricAgentRecord(
                        ingestion_run_id=ingestion_run.id,
                        agent_name=agent.agentName,
                        data=agent.model_dump(mode='json')
                    )
                    session.add(record)
                session.commit()

            if len(agents) < page_size:
                break

            await asyncio.sleep(sleep_time)

        with open_cookiefun_db() as session:
            ingestion_run = session.get(IngestionRunRecord, ingestion_run.id)
            ingestion_run.eagerly_load_all()
            return ingestion_run
