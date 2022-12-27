import redis
import os


redis_db = redis.Redis(
    host=os.environ.get("REDIS_STORAGE_HOST"),
    port=os.environ.get("REDIS_STORAGE_PORT"),
    password=os.environ.get("REDIS_STORAGE_PASSWORD"),

)

redis.Redis()