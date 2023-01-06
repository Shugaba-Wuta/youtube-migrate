"""
This file contains the helper functions for the path operations.
"""
# FastAPI and related packages
from fastapi import HTTPException, Request

# Other packages
import re
from typing import Any
from datetime import datetime
import os
from pathlib import Path
from google_auth_oauthlib.flow import Flow
import jwt
from typing import List
import json
import google.oauth2.credentials
from googleapiclient.discovery import build, Resource
import httpx
import ast
from googleapiclient.errors import HttpError
from uuid import uuid4
from pydantic import BaseModel
import backoff
import time
from database.memory_db import mem_db, MemDB
from core.redis_storage.redis_db import redis_db


# Local imports
import core.models as models
from core.background_app.celery_config import celery_app
from core.logs.logger_config import logger


GOOGLE_AUTH_REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5333/token")
SESSIONMIDDLEWARE_SECRET_KEY = os.environ.get("MIDDLEWARE_SECRET_KEY")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM")


DELIMITER = "*" * 5
MAX_BATCH_REQUEST = 1000
YOUTUBE_API_SERVICE = "youtube"
API_VERSION = "v3"
GOOGLE_API_MAX_RESULTS = 50
POSSIBLE_REDIRECTS = [
    "subscriptions/migrate",
    "subscriptions/fetch",
    "subscriptions/fetch?op=migrate",
    "login",
    "",
    "subscriptions/fetch?op=unsubscribe",
    "subscriptions/unsubscribe",
    "playlists/fetch?op=migrate",
    "playlists/fetch?op=delete",
    "playlists/migrated",
]
GOOGLE_AUTH_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/youtube",
]

BASE_PATH = Path(__file__).parent.resolve()
with open("client_secret.json", "r") as json_file:
    client_config = json.load(json_file)
GOOGLE_CLIENT_ID = client_config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = client_config["web"].get("client_secret", None)


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY variable is None")


def make_jwt_from_credential(credential: models.CompleteGoogleCredential) -> str:
    partial_credential = models.GoogleCredential(**credential.dict())
    jwt_credential = jwt.encode(
        payload=partial_credential.dict(), key=JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
    )
    return jwt_credential


def decode_user_token(token: str):
    if token is None:
        raise HTTPException(status_code=404, detail={"msg": "Invalid token"})
    try:
        decoded_token = jwt.decode(
            token, key=JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
    except jwt.exceptions.DecodeError as exc:
        raise HTTPException(status_code=404, detail={"msg": "Invalid token"})
    except jwt.exceptions.InvalidTokenError as exc:
        raise HTTPException(status_code=404, detail={"msg": "Invalid token"})
    except Exception:
        raise HTTPException(status_code=404, detail={"msg": "Invalid token"})
    return decoded_token


def is_redirect_url_valid(redirect_url):
    return redirect_url in POSSIBLE_REDIRECTS


def get_email_and_picture_from_session(session: dict):
    """Receives request.session as a dict session. Returns the email and profile_picture url."""
    email, profile_picture = session.get("user_info", (None, None))
    return email, profile_picture


def is_token_valid(token):
    try:
        decode_user_token(token)
    except Exception:
        return False
    return True


def get_gapi_build(request: Request):
    token = request.session.get("token", False)
    if not is_token_valid(token):
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )

    decoded_token = decode_user_token(token)
    build = get_authenticated_build(decoded_token)
    return build


def get_authenticated_build(decoded_token):
    _credentials = models.CompleteGoogleCredential(
        **decoded_token, client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET
    )
    dict_credentials = _credentials.dict()
    # change dict_credentials.get("expiry") from str to datetime format
    expiry = dict_credentials.get("expiry")
    datetime_expiry = datetime.strptime(expiry, r"%Y-%m-%dT%H:%M:%S.%fZ")
    dict_credentials["expiry"] = datetime_expiry
    credentials = google.oauth2.credentials.Credentials(**dict_credentials)
    _build = build(
        serviceName=YOUTUBE_API_SERVICE,
        version=API_VERSION,
        credentials=credentials,
    )
    return _build


async def get_all_user_subscription(build) -> dict:
    """Fetches all the subscriptions on a youtube account and returns a complex subscription resource"""
    subscriptions: Resource = (
        build.subscriptions()
        .list(
            part="snippet",
            mine=True,
            maxResults=GOOGLE_API_MAX_RESULTS,
            order="alphabetical",
        )
        .execute()
    )

    next_page_token = subscriptions.get("nextPageToken", None)
    while next_page_token is not None:
        # Make another youtube call.
        more_subscriptions = (
            build.subscriptions().list(
                part="snippet",
                mine=True,
                pageToken=next_page_token,
                order="alphabetical",
                maxResults=GOOGLE_API_MAX_RESULTS,
            )
        ).execute()
        next_page_token = more_subscriptions.get("nextPageToken", None)
        subscriptions["items"].extend(more_subscriptions["items"])
    return subscriptions


def make_resource_owner(request: Request) -> models.Owner:
    user_uuid = request.session.get("user-id", False)
    user = mem_db.get_owner(user_uuid)
    if (not user_uuid) or (not user):
        user_uuid = uuid4().hex
        request.session["user-id"] = user_uuid
        user = mem_db.store_owner(user_uuid)
        return user
    return user


async def get_user_email_info(token):
    PROFILE_URL = "https://www.googleapis.com/oauth2/v2/userinfo?access_token="
    async with httpx.AsyncClient() as client:
        request_user_info = await client.get(PROFILE_URL + token)
    if request_user_info.status_code == 200:
        user_info = request_user_info.json()
        return (user_info.get("email", None), user_info.get("picture", None))
    else:
        return (None, None)


async def retire_token(token: str):
    credentials = decode_user_token(token.strip())
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": credentials.get("token")},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )


async def delete_subscriptions(build, comma_separated_subscriptions: str):
    subscriptions = [
        {"sub_id": sub[0], "channel_id": sub[1]}
        for sub in ast.literal_eval(comma_separated_subscriptions)
    ]
    index = 0
    all_failed_report: list[dict] = []
    successful_operations: list[str] = []
    while subscriptions and (len(subscriptions) > index):
        index_sub = subscriptions[index]
        try:
            delete_subscription_request = build.subscriptions().delete(
                id=index_sub.get("sub_id", "1234")
            )
            delete_subscription_request.execute()
        except HttpError as exc:
            logger.warning("Failed to delete subscription", stack_info=True)
            # Transform reason like `subscriptionforbidden` to `Subscription Forbidden` for app rendering.
            reason_failed: str = exc.error_details[0]["reason"]
            unconcan_reason: list[str] = [
                x.title() for x in re.findall("[a-zA-Z][^A-Z]*", reason_failed)
            ]
            failed_report = {
                "failure_reason": " ".join(unconcan_reason),
                "resource_id": index_sub.get("channel_id", "1234"),
            }
            all_failed_report.append(failed_report)
        except Exception as exc:
            logger.exception(
                "Encountered unknown exception while attempting to delete subscription"
            )
            raise HTTPException(
                status_code=501, detail={"msg": "Failed to Unsubscribe subscription."}
            )
        else:
            successful_operations.append(index_sub.get("channel_id", "1234"))

        index += 1
    return all_failed_report, successful_operations


async def migrate_user_subscription(
    build, comma_separated_subscriptions: str
):  # -> tuple(dict, int):
    """Migrates subscription(s) to a youtube channel. Returns the summary of encountered errors if any and the total number of subscriptions initially called."""
    index = 0
    all_failed_report: list[dict] = []
    successful_operations: list[str] = []
    subscriptions = comma_separated_subscriptions.split(",")
    while subscriptions and (len(subscriptions) > index):
        subscription_resource = {
            "snippet": {
                "resourceId": {
                    "kind": "youtube#channel",
                    "channelId": subscriptions[index],
                },
            }
        }
        try:
            delete_subscription_request = build.subscriptions().insert(
                part="snippet",
                body=subscription_resource,
            )
            delete_subscription_request.execute()
        except HttpError as exc:
            # Transform reason like `subscriptionforbidden` to `Subscription Forbidden` for app rendering.
            reason_failed: str = exc.error_details[0]["reason"]
            unconcan_reason: list[str] = [
                x.title() for x in re.findall("[a-zA-Z][^A-Z]*", reason_failed)
            ]
            failed_report = {
                "failure_reason": " ".join(unconcan_reason),
                "resource_id": subscriptions[index],
            }
            all_failed_report.append(failed_report)
        except Exception as exc:
            raise HTTPException(
                status_code=501, detail={"msg": "Failed to add subscription."}
            )
        else:
            successful_operations.append(subscriptions[index])

        index += 1
    return all_failed_report, successful_operations


def start_google_flow(request: Request, redirect: str) -> Any:
    """Starts the Google flow and returns the redirect url"""
    if not is_redirect_url_valid(redirect):
        raise HTTPException(status_code=422, detail={"msg": "Unprocessable Entity."})
    flow = Flow.from_client_secrets_file("client_secret.json", scopes=GOOGLE_AUTH_SCOPE)
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI  #  + f"?redirect={redirect}"
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    request.session["state"] = state
    return auth_url


async def get_all_user_playlists_from_gapi(build) -> dict:
    """Fetches playlist resource from YouTube Account"""
    playlists = build.playlists().list(
        part="snippet,status,contentDetails",
        mine=True,
        maxResults=GOOGLE_API_MAX_RESULTS,
    )
    try:
        result = playlists.execute()
    except Exception as exc:
        logger.exception("Failed to fetch playlist from gapi")
        raise HTTPException(
            status_code=404, detail={"msg": "Unable to fetch playlists."}
        )
    next_page_token = result.get("nextPageToken", False)
    while next_page_token:
        more_playlists: Resource = build.playlists().list(
            part="snippet",
            mine=True,
            pageToken=next_page_token,
            maxResults=GOOGLE_API_MAX_RESULTS,
        )
        result["items"].extend(more_playlists["items"])
        next_page_token = more_playlists("nextPageToken", False)
    return result["items"]


def update_playlist_item_destination_ids(
    playlist_items: List[models.PlaylistItem], playlist_id: str
):
    for item in playlist_items:
        item.originating_playlist_id = playlist_id
    return playlist_items


async def fetch_all_playlist_items_from_gapi(
    build, playlist_model: models.Playlist
) -> List[models.PlaylistItem]:
    playlist_item_list = []
    try:
        response = (
            build.playlistItems()
            .list(
                part="snippet,contentDetails",
                maxResults=GOOGLE_API_MAX_RESULTS,
                playlistId=playlist_model.playlist_id,
            )
            .execute()
        )
    except Exception as exc:
        logger.exception("Failed to fetch playlist-items from gapi")
        raise HTTPException(
            status_code=404, detail={"msg": "Unable to fetch playlists items."}
        )
    next_page_token = response.get("nextPageToken", False)
    while next_page_token:
        try:

            new_response = (
                build.playlistItems()
                .list(
                    part="snippet,contentDetails",
                    maxResults=GOOGLE_API_MAX_RESULTS,
                    playlistId=playlist_model.playlist_id,
                    pageToken=next_page_token,
                )
                .execute()
            )
        except Exception as exc:
            logger.exception("Failed to fetch playlist-items from gapi")
            raise HTTPException(
                status_code=404, detail={"msg": "Unable to fetch playlists items."}
            )

        response["items"].extend(new_response["items"])
        next_page_token = new_response.get("nextPageToken", False)

    for playlist_item in response["items"]:
        item = models.PlaylistItem(
            originating_playlist_id=playlist_model.playlist_id,
            position=playlist_item["snippet"]["position"],
            note=playlist_item["contentDetails"].get("note", None),
            user_id=playlist_model.user_id,
            title=playlist_item["snippet"]["title"],
            resource_id=playlist_item["snippet"]["resourceId"]["videoId"],
            resource_kind=playlist_item["snippet"]["resourceId"]["kind"],
        )

        playlist_item_list.append(item)
    redis_db.store_playlist_items_redis_db(
        playlist_model.user_id, playlist_item_list, playlist_model.playlist_id
    )
    return playlist_item_list


def backoff_playlist_gapi_handler(details: dict):
    logger.debug(
        f"Couldn't add playlist with the following details: {details.get('args')} to gapi because of the following exception:\n{details.get('exception')}"
    )


def give_up_playlist_handler(details: dict):
    logger.exception(
        f"Couldn't add playlist with the following details: {details.get('args'), details.get('kwargs')} to gapi because of the following exception:\n{details.get('exception')}"
    )
    # Get the playlist model and user id from the function signature
    playlist: models.Playlist = (details.get("kwargs", [])).get(
        "playlist_model"
    ) or details.get("args")[1]
    user_id = (
        (details.get("kwargs", [])).get("user_id")
        or details.get("args")[2]
        or playlist.user_id
    )
    redis_db.store_playlist_migrate_status(
        user_id, playlist.playlist_id, playlist.title, "Failed"
    )


def success_playlist_handler(details: dict):
    # Get the playlist model and user id from the function signature
    playlist: models.Playlist = (details.get("kwargs", [])).get(
        "playlist_model"
    ) or details.get("args")[1]
    user_id = (
        (details.get("kwargs", [])).get("user_id")
        or details.get("args")[2]
        or playlist.user_id
    )
    redis_db.store_playlist_migrate_status(
        user_id, playlist.playlist_id, playlist.title, "Succeeded"
    )


@backoff.on_exception(
    backoff.expo,
    [HttpError],
    max_tries=5,
    jitter=backoff.full_jitter,
    on_backoff=backoff_playlist_gapi_handler,
    on_giveup=give_up_playlist_handler,
    on_success=success_playlist_handler,
    base=3,
    factor=5,
)
def create_playlist_gapi(
    build, playlist_model: models.Playlist, user_id, mem_db: MemDB
) -> List[models.PlaylistItem]:
    body = {
        "snippet": {
            "title": playlist_model.title,
            "description": playlist_model.description,
            "defaultLanguage": playlist_model.default_lang,
        },
        "status": {"privacyStatus": playlist_model.privacy_status},
    }
    try:
        response = (
            build.playlists().insert(part="id,snippet,status", body=body).execute()
        )
        new_id = response["id"]

        playlist_items = mem_db.get_playlist_items(user_id)
        print("PLAYLIST ITEMS FROM MEMDB: ", playlist_items)
        playlist_items = redis_db.get_playlist_items_redis_db(
            user_id, playlist_model.playlist_id
        )
        print("PLAYLIST ITEMS FROM REDIS: ", playlist_items)
        updated_playlist_items = update_playlist_item_destination_ids(
            playlist_items, new_id
        )
        return updated_playlist_items
    except HttpError as g_exc:
        raise g_exc
    except Exception as exc:
        logger.exception("python exception", {"playlist-model": playlist_model.dict})
        raise exc


def backoff_playlist_item_gapi_handler(details: dict):
    logger.debug(
        f"Couldn't add playlist-item with the following details: {details.get('args')} to gapi because of the following exception:\n{details.get('exception')}"
    )


def give_up_playlist_item_handler(details: dict):
    logger.exception(
        f"Couldn't add playlist-item with the following details: {details.get('args'), details.get('kwargs')} to gapi because of the following exception:\n{details.get('exception')}"
    )
    # Get the playlist-item model and user id from the function signature
    playlist_item: models.PlaylistItem = (details.get("kwargs", [])).get(
        "playlist_item"
    ) or details.get("args")[1]
    playlist: models.Playlist = (details.get("kwargs", [])).get(
        "playlist_model"
    ) or details.get("args")[2]
    user_id = playlist_item.user_id
    redis_db.store_playlist_item_migrate_status(
        user_id,
        playlist_item.destination_playlist_id,
        playlist.title,
        playlist_item.resource_id,
        playlist_item.title,
        "Failed",
    )


def success_playlist_item_handler(details: dict):
    # Get the playlist-item model and user id from the function signature
    playlist_item: models.PlaylistItem = (details.get("kwargs", [])).get(
        "playlist_item"
    ) or details.get("args")[1]
    playlist: models.Playlist = (details.get("kwargs", [])).get(
        "playlist_model"
    ) or details.get("args")[2]
    user_id = playlist_item.user_id
    redis_db.store_playlist_item_migrate_status(
        user_id,
        playlist_item.destination_playlist_id,
        playlist.title,
        playlist_item.resource_id,
        playlist_item.title,
        "Failed",
    )


@backoff.on_exception(
    backoff.expo,
    (HttpError),
    max_tries=5,
    jitter=backoff.full_jitter,
    on_backoff=backoff_playlist_item_gapi_handler,
    on_giveup=give_up_playlist_item_handler,
    on_success=success_playlist_item_handler,
    base=3,
    factor=5,
)
def add_playlist_items_to_gapi(
    build, playlist_item: models.PlaylistItem, playlist: models.Playlist
):
    body = {
        "snippet": {
            "playlistId": playlist_item.destination_playlist_id,
            "resourceId": {
                "kind": playlist_item.resource_kind,
                "videoId": playlist_item.resource_id,
            },
            "position": playlist_item.position,
        },
        "id": playlist_item.destination_playlist_id,
        "contentDetails": {"note": playlist_item.note},
    }
    print("\n\n\n\nid", playlist_item.destination_playlist_id)

    try:
        response = (
            build.playlistItems()
            .insert(part="snippet,contentDetails,id", body=body)
            .execute()
        )

    except HttpError as gexc:
        print("\n\n\nG Exception \n", gexc)
        raise gexc
    except Exception as exc:
        logger.exception("Python error", {"playlist-item": playlist_item.dict()})
        raise exc
    print("created playlist item", playlist_item)


def convert_model_list_to_json(list_of_models: BaseModel) -> dict:
    """Converts a  list of models to a list of dictionary representing the models"""
    return [model.dict() for model in list_of_models]


def playlist_migration_mail(email, user_id, *args, **kwargs):
    return "Email SENT"


#
# Celery tasks
#


@celery_app.task(name="migrate-playlist", serializer="pickle")
def migrate_playlist_in_background(build, playlist_model_list, email, user_id, db):
    # migrate_playlist(build, playlist_model_list, user_id)
    for playlist_model in playlist_model_list:
        try:
            playlist_items = create_playlist_gapi(build, playlist_model, user_id, db)
            for playlist_item in playlist_items:
                add_playlist_items_to_gapi(build, playlist_item, playlist_model)

        except Exception as e:
            raise e
    email_status = playlist_migration_mail(email, user_id)
    return email_status


@celery_app.task(name="test-creating-db-session", serializer="pickle")
def test_getting_db_session():
    pass


@celery_app.task(name="test-creating-db-session2", serializer="pickle")
def test_getting_db_session2(db):
    print("TESTING CELERY TASK OUTPUT")
    logger.debug("JUST A DEBUG")
    return mem_db.get_owner("1234567890"), "Owner:id:123467890", f"db-id: {id(db)}"
