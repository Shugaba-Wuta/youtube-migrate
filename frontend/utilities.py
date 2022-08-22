"""
This file contains the helper functions for the path operations. 
"""
# Fastapi and related packages
from re import A
import re
from typing import Any
from fastapi import HTTPException, Query, Request

# Other packages
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
import jwt
import json
import google.oauth2.credentials
from googleapiclient.discovery import build, Resource
import httpx
from googleapiclient.errors import HttpError

# Local imports
from .models import CompleteGoogleCredential, GoogleCredential, Token

GOOGLE_AUTH_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/youtube",
]
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
GOOGLE_CLIENT_SECRET = client_config["web"]["client_secret"]
GOOGLE_API_MAX_RESULTS = 50
POSSIBLE_REDIRECTS = ["subscriptions/fetch", "subscriptions/post", ""]


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY vairable is None")


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
    """Recieves request.session as a dict session. Returns the email and profile_picture url."""
    email, profile_picture = session.get("user_info", (None, None))
    return email, profile_picture
    

async def is_token_valid(token):
    try:
        await decode_user_token(token)
    except Exception:
        return False
    return True


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


async def get_user_email_info(token):
    PROFILE_URL = "https://www.googleapis.com/oauth2/v2/userinfo?access_token="
    async with httpx.AsyncClient() as client:
        request_user_info = await client.get(PROFILE_URL + token)
    if request_user_info.status_code == 200:
        user_info = request_user_info.json()
        return (user_info.get("email", None), user_info.get("picture", None))
    else:
        return (None, None)
async def retire_token(token:str): 
    credentials = await decode_user_token(token.strip())
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": credentials.get("token")},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )


async def post_user_subscription(build, comma_separated_subscriptions: str):  # -> tuple(dict, int):
    """Posts subscription(s) to a youtube channel. Returns the summary of encountered errors if any and the total number of subscriptions initially called."""
    index = 0
    all_failed_report:list[dict] = []
    successful_operations:list[str] = []
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
            add_subscription_request = build.subscriptions().insert(
                part="snippet",
                body=subscription_resource,
            )
            add_subscription_request.execute()
        except HttpError as exc:
            #Transform reason like `subscriptionforbidden` to `Subscription Forbidden` for frontend rendering.
            reason_failed:str = exc.error_details[0]["reason"]
            unconcan_reason:list[str]= [x.title() for x in re.findall("[a-zA-Z][^A-Z]*", reason_failed)]
            failed_report = {"failure_reason": " ".join(unconcan_reason), "resource_id": subscriptions[index]}
            all_failed_report.append(failed_report)
        except Exception as exc:
            raise HTTPException(
                status_code=501, detail={"msg": "Failed to add subscription."}
            )
        else: 
            successful_operations.append(subscriptions[index])

        index += 1
    return all_failed_report,successful_operations


async def start_google_flow(request: Request, redirect: str) -> Any:
    """Starts the Google flow and returns the redirect url"""
    if not await (is_redirect_url_valid(redirect)):
        raise HTTPException(status_code=422, detail={"msg": "Unprocessable Entity."})
    flow = Flow.from_client_secrets_file("client_secret.json", scopes=GOOGLE_AUTH_SCOPE)
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI + f"?redirect={redirect}"
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    request.session["state"] = state
    return auth_url
