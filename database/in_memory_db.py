import threading
from typing import AsyncIterator, Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from database.in_memory_db_models import Base

SQLITE_ASYNC_URL_PREFIX = "sqlite+aiosqlite:///"
MEMORY_LOCATION_START = "file:"
MEMORY_LOCATION_END = "?mode=memory&cache=shared&uri=true"


class InMemoryDatabase:
    """
    Async in-memory SQLite DB
    """

    def __init__(self, sql_echo: bool = False):
        self.sql_echo = sql_echo
        # self._sync_memory_engine: Optional[Engine] = None
        self._async_memory_engine: Optional[AsyncEngine] = None
        self._async_sessionmaker: Optional[sessionmaker] = None

    async def setup(self, filename: str = "in_memorydb.db"):
        """
        Creates an async session and memory qengine, for the in-memory database.
        """
        in_memory_url = MEMORY_LOCATION_START + filename + MEMORY_LOCATION_END
        self._async_memory_engine = create_async_engine(
            url=SQLITE_ASYNC_URL_PREFIX + in_memory_url, echo=self.sql_echo
        )
        self._async_sessionmaker = sessionmaker(
            self._async_memory_engine, class_=AsyncSession
        )
        # async with self._async_memory_engine.begin() as conn:
        #     await conn.run_sync(Base.metadata.drop_all)
        async with self._async_memory_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def get_engine(self) -> AsyncEngine:
        assert self._async_memory_engine, "No engine. Run setup() first."
        return self._async_memory_engine

    def get_session(self) -> AsyncSession:
        assert self._async_sessionmaker, "No sessionmaker. Run setup() first."
        return self._async_sessionmaker()

    async def __call__(self) -> AsyncIterator[AsyncSession]:
        """Used by FastAPI Depends"""
        # self.setup(filename)
        async with self._async_sessionmaker() as session:
            yield session


class ThreadSafeSingleton(type):
    _instances = {}
    _singleton_locks: Dict[Any, threading.Lock] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            if cls not in cls._singleton_locks:
                cls._singleton_locks[cls] = threading.Lock()
            with cls._singleton_locks[cls]:
                if cls not in cls._instances:
                    cls._instances[cls] = super(ThreadSafeSingleton, cls).__call__(
                        *args, **kwargs
                    )
        return cls._instances[cls]


class MemDB(metaclass=ThreadSafeSingleton):
    def __init__(self) -> None:
        self.setup()

    @classmethod
    def setup(cls):
        return "Setup function"

    @classmethod
    def get_session(cls):
        pass

    @classmethod
    def get_engine(cls):
        pass

    def __str__(cls) -> str:
        return f"(MemDB) => {[prop for prop in vars(cls).items()]}"

    def __repr__(cls) -> str:
        return cls.__str__()


memory_db = InMemoryDatabase(sql_echo=False)
