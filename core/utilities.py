"""
This file contains the helper functions for the path operations.
"""
# FastAPI and related packages
from fastapi import HTTPException, Request, Depends

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
import asyncio
from googleapiclient.errors import HttpError
from uuid import uuid4
from pydantic import BaseModel
import backoff


# Local imports
from .models import CompleteGoogleCredential, GoogleCredential, Token
from database.in_memory_db_models import Owner, Playlist, PlaylistItem
from database.in_memory_db_main import *
from database.in_memory_db import memory_db as db
import core.models as models
from core.background_app.celery_config import celery_app

GOOGLE_AUTH_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/youtube",
]
DELIMITER = "*" * 5
MAX_BATCH_REQUEST = 1000
YOUTUBE_API_SERVICE = "youtube"
API_VERSION = "v3"
GOOGLE_AUTH_REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5333/token")
SESSIONMIDDLEWARE_SECRET_KEY = os.environ.get("MIDDLEWARE_SECRET_KEY")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM")
BASE_PATH = Path(__file__).parent.resolve()
with open("client_secret.json", "r") as json_file:
    client_config = json.load(json_file)
GOOGLE_CLIENT_ID = client_config["web"]["client_id"]
GOOGLE_CLIENT_SECRET = client_config["web"].get("client_secret", None)
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


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY variable is None")


async def make_jwt_from_credential(credential: CompleteGoogleCredential):
    partial_credential = GoogleCredential(**credential.dict())
    jwt_credential: Token = jwt.encode(
        payload=partial_credential.dict(), key=JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
    )
    return jwt_credential


async def decode_user_token(token: Token):
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


async def is_redirect_url_valid(redirect_url):
    return redirect_url in POSSIBLE_REDIRECTS


async def get_email_and_picture_from_session(session: dict):
    """Receives request.session as a dict session. Returns the email and profile_picture url."""
    email, profile_picture = session.get("user_info", (None, None))
    return email, profile_picture


async def is_token_valid(token):
    try:
        await decode_user_token(token)
    except Exception:
        return False
    return True


async def get_gapi_build(request: Request):
    token = request.session.get("token", False)
    if not await is_token_valid(token):
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )

    decoded_token = await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    return build


async def get_authenticated_build(decoded_token):
    _credentials = CompleteGoogleCredential(
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


async def make_resource_owner(
    request: Request, db: AsyncSession = Depends(db.get_session)
) -> Owner:
    user_uuid = request.session.get("user-id", False)
    if not user_uuid:
        user_uuid = uuid4().hex
        request.session["user-id"] = user_uuid
        user = await create_user_id(db, user_uuid)
        return models.Owner(user_id=user.user_id, created_at=user.created_at)
    owner: Owner = await get_owner(db, user_uuid)
    return models.Owner(user_id=owner.user_id, created_at=owner.created_at)


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
    credentials = await decode_user_token(token.strip())
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


async def start_google_flow(request: Request, redirect: str) -> Any:
    """Starts the Google flow and returns the redirect url"""
    if not await (is_redirect_url_valid(redirect)):
        raise HTTPException(status_code=422, detail={"msg": "Unprocessable Entity."})
    flow = Flow.from_client_secrets_file("client_secret.json", scopes=GOOGLE_AUTH_SCOPE)
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI  #  + f"?redirect={redirect}"
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    request.session["state"] = state
    return auth_url


async def get_all_user_playlists_from_gapi(build) -> dict:
    """Fetches playlist resource from YouTube Account (preferably the old YouTube)"""
    playlists: Resource = build.playlists().list(
        part="snippet,status,contentDetails",
        mine=True,
        maxResults=GOOGLE_API_MAX_RESULTS,
    )
    try:
        result = playlists.execute()
    except Exception as exc:
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
            raise HTTPException(
                status_code=404, detail={"msg": "Unable to fetch playlists items."}
            )

        response["items"].extend(new_response["items"])
        next_page_token = new_response.get("nextPageToken", False)
    ##Store playlistItem in database.
    # async def store_playlist_item()

    for playlist_item in response["items"]:
        item = models.PlaylistItem(
            originating_playlist_id=playlist_model.playlist_id,
            position=playlist_item["snippet"]["position"],
            note=playlist_item["contentDetails"].get("note", None),
            user_id=playlist_model.user_id,
            resource_id=playlist_item["snippet"]["resourceId"]["videoId"],
            resource_kind=playlist_item["snippet"]["resourceId"]["kind"],
        )

        playlist_item_list.append(item)
    return playlist_item_list


async def update_destination_id_for_playlist_items(
    request_id: str, response, exception=None
):
    if exception:
        raise exception
    destination_playlist_id = response["id"]
    user_id, originating_playlist_id = request_id.split(DELIMITER)
    await batch_update_destination_id_for_playlist_items(
        user_id, originating_playlist_id, destination_playlist_id
    )


async def create_playlist_gapi2(build, playlist_model_list: List[models.Playlist]):
    for playlist_model in playlist_model_list:
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
                build.playlists().insert(part="snippet,id,status", body=body).execute()
            )
        except HttpError as google_exc:
            raise google_exc
        except Exception as other_exc:
            raise other_exc
        else:
            request_id = playlist_model.user_id + DELIMITER + playlist_model.playlist_id
            await update_destination_id_for_playlist_items(request_id, response)


@celery_app.task("create identical Playlist")
@backoff.on_exception(backoff.expo, [HTTPException], max_tries=10)
async def create_playlist_gapi(build, playlist_model_list: List[models.Playlist]):
    for i, playlist_model in enumerate(playlist_model_list):
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
        except HttpError as g_exc:
            raise g_exc
        # except Exception as exc:
        #     print(exc)
        #     raise HTTPException(
        #         status_code=404,
        #         detail={"msg": f"Unable to create all playlists"},
        #     )

        else:
            request_id = playlist_model.user_id + DELIMITER + playlist_model.playlist_id
            await update_destination_id_for_playlist_items(request_id, response)


async def add_playlist_items_to_gapi(
    build, playlist_item_list: List[models.PlaylistItem]
):
    for playlist_item in playlist_item_list:
        body = {
            "snippet": {
                "playlistId": playlist_item.destination_playlist_id,
                "resourceId": {
                    "kind": playlist_item.resource_kind,
                    "videoId": playlist_item.resource_id,
                },
                "position": playlist_item.position,
            },
            "contentDetails": {"note": playlist_item.note},
        }

        try:
            response = (
                build.playlistItems()
                .insert(part="snippet,contentDetails", body=body)
                .execute()
            )

        except HttpError as gexc:
            print(gexc)
            response = None
        except Exception as exc:
            print(exc)
            raise HTTPException(
                status_code=500, detail={"msg": "Unable to migrate playlist items."}
            )
        else:
            print(f"Playlist insertion is complete! ")
            # create_playlist_item_callback(response=response)


async def convert_model_list_to_json(list_of_models: BaseModel) -> dict:
    """Converts a  list of models to a list of dictionary representing the models"""
    return [model.dict() for model in list_of_models]
