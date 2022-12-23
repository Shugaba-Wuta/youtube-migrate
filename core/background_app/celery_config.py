from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()


celery_app = Celery(
    "yt-migrate",
    broker=os.environ.get("CELERY_BROKER_URL"),
    backend=os.environ.get("CELERY_RESULT_BACKEND"),
    include=["tasks"],
)

if __name__ == "__main__":
    worker = celery_app.Worker(include=["tasks"])
    worker.start()
