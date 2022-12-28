from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()


celery_app = Celery(
    "yt-migrate",
    broker=os.environ.get("CELERY_BROKER_URL"),
    backend=os.environ.get("CELERY_RESULT_BACKEND"),
    include=["core.background_app.tasks", "core.utilities"],
)
celery_app.conf.update(
    accept_content=["pickle", "json"], result_accept_content=["pickle", "json"]
)

# celery_app.autodiscover_tasks(packages=["core.background_app"])
# celery -A core.celery_app worker -l INFO

if __name__ == "__main__":
    raise Exception("This module should not be executed directly")
