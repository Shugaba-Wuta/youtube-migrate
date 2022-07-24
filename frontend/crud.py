# Fastapi and related packages
import profile
from sys import excepthook
from time import time
from fastapi import (
    Cookie,
    FastAPI,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

# from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from starlette.middleware.sessions import SessionMiddleware


# Other packages
import sass
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
import jwt
import json
import google.oauth2.credentials
from googleapiclient.discovery import build, Resource
import httpx
import base64

# # Local imports
from frontend.models import (
    GoogleCredential,
    CompleteGoogleCredential,
    Token,
    BasicUserInfo,
    UserInfo,
)

# Configuring app
load_dotenv()


app = FastAPI()


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
POSSIBLE_REDIRECTS = ["fetch", "post", ""]


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY vairable is None")

app.add_middleware(SessionMiddleware, secret_key=SESSIONMIDDLEWARE_SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=20)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5333"],
#     allow_credentials=True,
#     allow_methods=[
#         "GET",
#         "POST",
#         "OPTIONS",
#     ],  # include additional methods as per the application demand
#     allow_headers=[
#         "Access-Control-Allow-Headers",
#         "Content-Type",
#         "Authorization",
#         "Access-Control-Allow-Origin",
#     ],
# )


templates = Jinja2Templates(directory=f"{BASE_PATH}/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Setting up Sass to modify bootstrap variables
sass.compile(dirname=("frontend/static/sass", "frontend/static/css"))

# Inititiating OAUTH
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/", scheme_name="JWT")
# Declaring constants


###UTILITY FUNCTIONS ###
##
#


async def make_jwt_from_credential(credential: CompleteGoogleCredential):
    partial_credential = GoogleCredential(**credential.dict())
    jwt_credential: Token = jwt.encode(
        payload=partial_credential.dict(), key=JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
    )
    return jwt_credential


async def decode_user_token(token: Token):
    if token is None:
        raise ValueError("Token Cannot be None!")
    try:
        decoded_token = jwt.decode(
            token, key=JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
    except jwt.exceptions.DecodeError as e:
        raise e
    # jwt.exceptions.DecodeError("TOKEN could not be decoded")
    except Exception:
        # TODO: Log this error
        raise Exception()
    return decoded_token


async def is_redirect_url_valid(redirect_url):
    return redirect_url in POSSIBLE_REDIRECTS


async def is_token_valid(token):
    try:
        decode_user_token(token)
    except Exception:
        return False
    return True


async def get_authenticated_build(decoded_token):
    _credentials = CompleteGoogleCredential(
        **decoded_token, client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET
    )
    dict_credentials = _credentials.dict()
    # change dict_credentials.get("expiry") from str to datetime
    expiry = dict_credentials.get("expiry")
    new_expiry = datetime.strptime(expiry, r"%Y-%m-%dT%H:%M:%S.%fZ")
    dict_credentials["expiry"] = new_expiry
    credentials = google.oauth2.credentials.Credentials(**dict_credentials)
    _build = build(
        serviceName=YOUTUBE_API_SERVICE,
        version=API_VERSION,
        credentials=credentials,
    )
    return _build


async def get_all_user_subscription(build):
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


async def start_google_flow(request: Request, redirect: str):
    if not (is_redirect_url_valid(redirect)):
        # For development purposes.
        raise Exception("Redirect is invalid!!!\n\n")
        redirect = ""
    flow = Flow.from_client_secrets_file("client_secret.json", scopes=GOOGLE_AUTH_SCOPE)
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI + f"?redirect={redirect}"
    auth_url, state = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    request.session["state"] = state
    if redirect == "post":
        return RedirectResponse(url=auth_url)
    return auth_url


def show(*args) -> None:
    print("#" * 25 + str(*args) + "#" * 25)
    return


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_info = request.session.get("user_info", (None, None))
    email, profile_picture = None, None
    if user_info != (None, None):
        email = user_info[0]
        profile_picture = user_info[1]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "email": email, "profile_picture": profile_picture},
    )


@app.get("/login")
async def login_with_google(
    request: Request, redirect: str, logged_in: bool = Query(default=False)
):
    token = request.session.get("token", None)
    token_is_valid = is_token_valid(token)
    if logged_in and token_is_valid:
        return RedirectResponse(url=redirect)
    auth_url = await start_google_flow(request, redirect)
    response = RedirectResponse(url=auth_url)
    return response


@app.get("/token", response_class=RedirectResponse)
async def get_permission(request: Request, redirect: str | None = None):
    state = request.session.get("state", None)
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["https://www.googleapis.com/auth/youtube"],
        state=state,
    )
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI + f"?redirect={redirect}"
    auth_url = request.url
    try:
        flow.fetch_token(authorization_response=str(auth_url))
    except OAuth2Error:
        return RedirectResponse(url="/error")
    credentials = flow.credentials
    json_credentials = json.loads(credentials.to_json())
    jwt_token = await make_jwt_from_credential(
        credential=CompleteGoogleCredential(**json_credentials)
    )
    user_info = await get_user_email_info(credentials.token)
    if user_info != (None, None):
        request.session["user_info"] = user_info
    request.session["token"] = jwt_token

    redirect = request.session.get("redirect", None)
    if redirect == "post":
        return credentials
    return RedirectResponse(url=f"/handle-token?jwt_token={jwt_token}")


@app.get("/handle-token", response_class=HTMLResponse)
def redirect_to_handle_token_page(
    request: Request, jwt_token: str, redirect: str | None = None
):
    request.session["token"] = jwt_token
    if not is_redirect_url_valid(redirect):
        return RedirectResponse(url="/login?redirect=fetch")
    elif redirect in POSSIBLE_REDIRECTS:
        return templates.TemplateResponse(
            "handle-token.html",
            {"request": request, "token": jwt_token, "redirect": redirect},
        )

    else:
        # For development purposes.
        # TODO #2 Redirect to error page
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Bad parameter: redirect"
        )


@app.get("/fetch")  # , response_class=HTMLResponse)
async def fetch_all_subscriptions(request: Request):
    token = request.session.get("token", None)
    if token is None:
        return RedirectResponse(url="/login")
    decoded_token = await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    subscriptions = await get_all_user_subscription(build)
    user_info = request.session.get("user_info", (None, None))
    email, profile_picture = None, None
    if user_info != (None, None):
        email = user_info[0]
        profile_picture = user_info[1]
    # return subscriptions
    return templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "subscriptions": subscriptions,
            "email": email,
            "profile_picture": profile_picture,
        },
    )


@app.post("/post", response_class=HTMLResponse)
async def post_all_subscriptions(request: Request, subscriptions: dict | None = None):
    """Get credentials for the destination account."""
    token = request.session.get("token", None)
    if token is None:
        # log into new account.
        await start_google_flow(request, "post")
        return RedirectResponse(url="/login?redirect=post")

    # return templates.TemplateResponse("successful-migration.html", {"request": request})


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request, redirect: str | None = None):
    """Revokes token and then clears all stored session data."""
    token: str = request.session.get("token", None)
    if token:
        credentials = await decode_user_token(token.strip())
        async with httpx.AsyncClient() as client:
            client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": credentials.get("token")},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )

    request.session.clear()
    if redirect == "post":
        return RedirectResponse(url="/post")
    else:
        return templates.TemplateResponse("index.html", {"request": request})


@app.get("/error", response_class=HTMLResponse)
async def redirect_to_error_page_with_status_code(request: Request):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "error": {"error_code": 404, "details": "You are not currently signed in"},
        },
    )
