# from __future__ import absolute_import

from celery_config import celery_app
import time


@celery_app.task(name="first_app_task_inner")
def first_task() -> str:
    time.sleep(15)
    print("first app task called!")
    return "completed!!"
