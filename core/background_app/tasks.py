# from __future__ import absolute_import

from .celery_config import celery_app
import time
import backoff


@celery_app.task(name="first_app_task_inner")
def first_task() -> str:
    time.sleep(15)
    print("\n\n\n\n\n\n\n\nfirst app task called!\n\n\n\n\n\n")
    return "completed!!"


@celery_app.task(name="add_playlist_to_account")
@backoff.on_exception(
    backoff.expo, exception=[Exception], max_tries=5, on_success=lambda x: x
)
async def add_playlists_to_account():
    pass
