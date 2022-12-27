from .redis_config import redis_db
import json


async def store_playlist_redis_db(user_id: str, playlist_list):
    key = user_id.strip() + ":playlist"
    value = json.dumps(playlist_list)
    redis_db.set(key, value, ex=24 * 60 * 60)


async def retrieve_playlist_redis_db(user_id: str) -> dict:
    key = user_id.strip() + ":playlist"
    value = redis_db.get(key)
    return json.loads(value)


async def store_playlist_items_redis_db(user_id: str, playlist_items: dict):
    key = user_id.strip() + ":playlist-items"
    value = json.dumps(playlist_items)
    redis_db.rpush(key, value)


async def retrieve_all_playlist_items_redis_db(user_id: str):
    key = user_id.strip() + ":playlist-items"
    value = redis_db.lrange(key, 0, -1)
    return json.loads(value)


def record_playlist_migrate_status(user_id, playlist_id, message):
    key = f"{user_id.strip()}:playlist:migration-status"
    value = json.dumps({playlist_id: message})
    redis_db.rpush(key, value)
    redis_db.expire(key, 100_001)


def get_all_playlist_migrate_status(user_id):
    key = f"{user_id.strip()}:playlist:migration-status"
    value = redis_db.lrange(key, 0, -1)
    return json.loads(value)


def record_playlist_item_migrate_status(user_id, playlist_item_id, message):
    key = f"{user_id.strip()}:playlist-item:migration-status"
    value = json.dumps({playlist_item_id: message})
    redis_db.rpush(key, value)
    redis_db.expire(key, 100_001)


def get_all_playlist_migrate_status(user_id):
    key = f"{user_id.strip()}:playlist-item:migration-status"
    value = redis_db.lrange(key, 0, -1)
    return json.loads(value)
