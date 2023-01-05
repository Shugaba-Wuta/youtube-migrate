import threading
from typing import Optional, Any, Dict, List
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from database.memory_db_models import Base
from dotenv import load_dotenv
import os
from datetime import datetime
import database.memory_db_models as orm
from core.logs.logger_config import logger
from fastapi.exceptions import HTTPException
from core import models


load_dotenv()


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
    def __init__(self, sql_echo) -> None:
        self.setup(sql_echo)

    @classmethod
    def setup(cls, sql_echo=False) -> None:
        MEM_DB_ENGINE = os.environ.get("MEM_DB_URI")
        assert MEM_DB_ENGINE, "MEM_DB_URI is not set"
        cls.engine = create_engine(MEM_DB_ENGINE, echo=sql_echo)
        cls.session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def get_session(cls) -> Session:
        """Get a sync session connection for manipulating data"""
        assert cls.session, f"Please run {cls}.setup()"
        return cls.session()

    @classmethod
    def get_engine(cls) -> Engine:
        return cls.engine

    @classmethod
    def get_owner(cls, user_id: str) -> Optional[models.Owner]:
        session: Session = cls.get_session()
        with session:
            return session.query(orm.Owner).filter_by(user_id=user_id).first()

    @classmethod
    def store_owner(cls, user_id: str) -> models.Owner:
        """Adds user to `owner`'s table"""
        session: Session = cls.get_session()
        user = cls.get_owner(user_id)
        if user:
            return models.Owner.from_orm(user)
        try:
            user = orm.Owner(
                user_id=user_id, created_at=datetime.now().astimezone().isoformat()
            )
            session.add(user)
            session.commit()
        except Exception as E:
            logger.exception("Attempted creating a new `Owner`", {"user_id": user_id})
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.1"
                },
            )
        finally:
            session.close()

        return models.Owner.from_orm(cls.get_owner(user_id))

    @classmethod
    def get_playlist(cls, playlist_id: str, user_id: str) -> models.Playlist:
        """Retrieves a single `Playlist` matching the provided `user_id` and `playlist_id`"""
        session: Session = cls.get_session()
        with session:
            playlist = (
                session.query(orm.Playlist)
                .filter_by(playlist_id=playlist_id, user_id=user_id)
                .first()
            )
            return models.Playlist.from_orm(playlist)

    @classmethod
    def get_playlists(cls, user_id: str) -> List[models.Playlist]:
        """Retrieves all `Playlist` matching the provided `user_id`"""
        session: Session = cls.get_session()
        with session:
            _ = session.query(orm.Playlist).filter_by(user_id=user_id).all()
            playlists = [models.Playlist.from_orm(i) for i in _]
            return playlists

    @classmethod
    def store_playlist(cls, playlist_model: models.Playlist) -> None:
        """Stores a single playlist into `MemDB`"""
        session: Session = cls.get_session()
        try:
            session.add(orm.Playlist(**playlist_model.dict(exclude_none=True)))
            session.commit()
        except:
            logger.exception(
                "Attempted storing Playlist", {"playlist_model": playlist_model}
            )
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.2"
                },
            )
        finally:
            session.close()

    @classmethod
    def store_playlists(cls, playlist_models: List[models.Playlist]) -> None:
        """Stores multiple playlists into DB"""

        session: Session = cls.get_session()
        try:
            model = [orm.Playlist(**i.dict(exclude_none=True)) for i in playlist_models]
            session.add_all(model)
            session.commit()
        except:
            logger.exception(
                "Attempted storing Playlists", {"playlist_models": playlist_models}
            )
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.3"
                },
            )
        finally:
            session.close()

    @classmethod
    def get_playlist_item(
        cls, playlist_id: str, resource_id: str
    ) -> models.PlaylistItem:
        """Retrieves a playlist-item from MemDB"""
        session = cls.get_session()
        with session:
            playlist_item = (
                session.query(orm.PlaylistItem)
                .filter_by(playlist_id=playlist_id, resource_id=resource_id)
                .first()
            )
            return models.PlaylistItem.from_orm(playlist_item)

    @classmethod
    def get_playlist_items(cls, user_id: str) -> List[models.PlaylistItem]:
        """Retrieves multiple playlists that match the given `user_id`"""
        session = cls.get_session()
        with session:
            _ = session.query(orm.PlaylistItem).filter_by(user_id=user_id).all()
            result = [models.PlaylistItem.from_orm(i) for i in _]
            return result

    @classmethod
    def store_playlist_item(cls, playlist_item: models.PlaylistItem) -> None:
        """Stores a single playlist item in MemDB"""
        session = cls.get_session()
        try:
            session.add(orm.PlaylistItem(**playlist_item.dict()))
            session.commit()
        except:
            logger.exception(
                "Attempted to store playlist-item but failed.",
                {"playlist-item": playlist_item},
            )
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.4"
                },
            )
        finally:
            session.close()

    @classmethod
    def store_playlist_items(cls, playlist_items: List[models.PlaylistItem]) -> None:
        """Stores multiple playlist-items into `MemDB`"""
        session = cls.get_session()
        try:
            model = [
                orm.PlaylistItem(**i.dict(exclude_none=True)) for i in playlist_items
            ]
            session.add_all(model)
            session.commit()
        except:
            logger.exception(
                "Attempted to store playlist-items but failed.",
                {"playlist-item": playlist_items},
            )
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.5"
                },
            )
        finally:
            session.close()

    @classmethod
    def update_playlist_item_destination_ids(
        cls,
        user_id: str,
        old_id: str,
        new_id: str,
    ) -> None:
        """Updates the destination-id field of playlist-item"""
        session = cls.get_session()
        try:
            session.query(orm.PlaylistItem).filter_by(
                user_id=user_id, originating_playlist_id=old_id
            ).update({orm.PlaylistItem.destination_playlist_id: new_id})
            session.commit()
        except:
            logger.exception(
                "Attempted to update destination_id for playlist-item but failed.",
                {
                    "playlist-item": old_id,
                    "user-id": user_id,
                    "originating-playlist-id": old_id,
                    "destination-playlist-id": new_id,
                },
            )
            raise HTTPException(
                500,
                detail={
                    "msg": "Encountered an Error while processing your request, please restart the process.6"
                },
            )
        finally:
            session.close()

    def __str__(cls) -> str:
        return f"(MemDB) => engine: {cls.get_engine()}"

    def __repr__(cls) -> str:
        return cls.__str__()


# Set the sql_echo to false when deployed
echo: bool = os.environ.get("ENVIRON", False) == "PRODUCTION"
mem_db = MemDB(echo)
