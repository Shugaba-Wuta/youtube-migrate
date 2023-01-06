import redis
import os
import json
from typing import List, Optional
from core import models
from dotenv import load_dotenv
from database.memory_db import ThreadSafeSingleton


load_dotenv()


class RedisTemp(metaclass=ThreadSafeSingleton):
    def __init__(self):
        RedisTemp.host = os.environ.get("REDIS_STORAGE_HOST")
        RedisTemp.port = os.environ.get("REDIS_STORAGE_PORT")
        RedisTemp.password = os.environ.get("REDIS_STORAGE_PASSWORD")
        RedisTemp.expire_time_delta = 100_001
        RedisTemp.setup()

    @classmethod
    def setup(cls):
        assert (
            cls.host and cls.port and cls.password
        ), "Missing Redis Storage environment variables"
        cls.db = redis.Redis(host=cls.host, port=cls.port, password=cls.password)

    @classmethod
    def store_playlist_migrate_status(
        cls, user_id: str, playlist_id: str, playlist_title: str, migration_status: str
    ) -> None:
        key = f"{user_id.strip()}:playlist:migration-status"
        value = json.dumps(
            {playlist_id: {"status": migration_status, "title": playlist_title}}
        )
        cls.db.lpush(key, value)
        cls.db.expire(key, cls.expire_time_delta)

    @classmethod
    def get_playlist_migrate_statuses(cls, user_id: str):
        key = f"{user_id.strip()}:playlist:migration-status"
        value = cls.db.lrange(key, 0, -1)
        return json.loads(value)

    @classmethod
    def store_playlist_item_migrate_status(
        cls,
        user_id: str,
        playlist_id: str,
        playlist_title: str,
        playlist_item_id: str,
        playlist_item_title: str,
        migration_status: str,
    ):
        key = f"{user_id.strip()}:playlist-item:migration-status"
        value = json.dumps(
            {
                playlist_item_id: {
                    "playlist_id": playlist_id,
                    "playlist_title": playlist_title,
                    "playlist_item_title": playlist_item_title,
                    "status": migration_status,
                }
            }
        )
        cls.db.lpush(key, value)
        cls.db.expire(key, cls.expire_time_delta)

    @classmethod
    def get_playlist_migrate_statuses(cls, user_id):
        key = f"{user_id.strip()}:playlist-item:migration-status"
        value = cls.db.lrange(key, 0, -1)
        return json.loads(value)

    @classmethod
    def store_playlist_items_redis_db(
        cls, user_id: str, playlist_items: List[models.PlaylistItem], playlist_id: str
    ) -> None:
        key = f"{user_id.strip()}:playlist-items"
        value = {playlist_id: json.dumps([item.dict() for item in playlist_items])}
        cls.db.hmset(key, value)
        cls.db.expire(key, cls.expire_time_delta)

    @classmethod
    def get_playlist_items_redis_db(
        cls, user_id: str, playlist_id: str
    ) -> List[models.PlaylistItem]:
        """Retrieves playlist item from Redis storage"""
        key = f"{user_id.strip()}:playlist-items"
        value = cls.db.hget(key, playlist_id)
        if value:
            return [models.PlaylistItem(**item) for item in json.loads(value)]
        return []


redis_db = RedisTemp()
