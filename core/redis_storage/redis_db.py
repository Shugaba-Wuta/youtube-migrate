import redis
import os
import json
from dotenv import load_dotenv
from database.memory_db import ThreadSafeSingleton


load_dotenv()


class RedisTemp(metaclass=ThreadSafeSingleton):
    def __init__(self):
        RedisTemp.host = os.environ.get("REDIS_STORAGE_HOST")
        RedisTemp.port = os.environ.get("REDIS_STORAGE_PORT")
        RedisTemp.password = os.environ.get("REDIS_STORAGE_PASSWORD")
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
        cls.db.expire(key, 100_001)

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
        cls.db.expire(key, 100_001)

    @classmethod
    def get_playlist_migrate_statuses(cls, user_id):
        key = f"{user_id.strip()}:playlist-item:migration-status"
        value = cls.db.lrange(key, 0, -1)
        return json.loads(value)


redis_db = RedisTemp()
