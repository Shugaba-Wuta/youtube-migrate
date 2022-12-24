from redis_config import redis_db
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
    key_exists = redis_db.exists(key)
    if key_exists:
        redis_db.rpush(key, value)
    else:
        redis_db.lset(key, value)


async def retrieve_all_playlist_items_redis_db(user_id: str):
    key = user_id.strip() + ":playlist-items"
    value = redis_db.lrange(key, 0, -1)
    return json.loads(value)

