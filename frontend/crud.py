# Fastapi and related packages
from fastapi import (
    Body,
    FastAPI,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.exceptions import RequestValidationError

# Other packages
import sass
import os
from pathlib import Path
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
import json
import httpx
import urllib.parse
from sqlalchemy.orm import Session
from googleapiclient.errors import *

# # Local imports
from frontend.models import (
    CompleteGoogleCredential,
)
from frontend.utilities import (
    is_token_valid,
    start_google_flow,
    make_jwt_from_credential,
    get_all_user_subscription,
    get_authenticated_build,
    is_redirect_url_valid,
    decode_user_token,
    post_user_subscription,
    get_user_email_info,
)

# Imports from database
from database import database, models, main as db_main
from database.database import get_db

models.Base.metadata.create_all(bind=database.engine)
# Configuring app
load_dotenv()

app = FastAPI()
SESSIONMIDDLEWARE_SECRET_KEY = os.environ.get("MIDDLEWARE_SECRET_KEY")
BASE_PATH = Path(__file__).parent.resolve()
GOOGLE_AUTH_REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5333/token")


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY vairable is None")

app.add_middleware(SessionMiddleware, secret_key=SESSIONMIDDLEWARE_SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=2)


templates = Jinja2Templates(directory=f"{BASE_PATH}/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Setting up Sass to modify bootstrap variables
sass.compile(dirname=("frontend/static/sass", "frontend/static/css"))


@app.exception_handler(HTTPException)
async def handle_all_raised_HTTPEexceptions(request, exc: HTTPException):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": exc.status_code, "msg": exc.detail["msg"]},
    )


@app.exception_handler(RequestValidationError)
async def handle_422_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 422, "msg": "Unprocessable Entity"},
    )


@app.exception_handler(404)
async def handle_404_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 404, "msg": "Resource not Found"},
    )


@app.exception_handler(421)
async def handle_421_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 421, "msg": "Unprocessable Entity"},
    )


@app.exception_handler(422)
async def handle_422_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 422, "msg": "2Unprocessable Entity"},
    )


@app.exception_handler(405)
async def handle_405_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 405, "msg": "Method is not Allowed"},
    )


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
    request: Request,
    redirect: str,
    logged_in: bool = Query(default=False),
):
    token = request.session.get("token", None)
    token_is_valid = await is_token_valid(token)
    if logged_in and token_is_valid:
        return RedirectResponse(url=redirect)
    auth_url = await start_google_flow(request, redirect)
    response = RedirectResponse(url=auth_url)
    return response


@app.get("/token", response_class=RedirectResponse)
async def get_permission(
    request: Request, redirect: str | None = None, db: Session = Depends(get_db)
):
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
        raise HTTPException(
            status_code=502,
            detail={
                "msg": "Could not complete Google flow. Kindly logout and start the process again."
            },
        )
    except Exception:
        raise HTTPException(
            status_code=422, detail={"msg": "Encountered unprocessable response. "}
        )
    credentials = flow.credentials
    json_credentials = json.loads(credentials.to_json())
    jwt_token = await make_jwt_from_credential(
        credential=CompleteGoogleCredential(**json_credentials)
    )
    user_info = await get_user_email_info(credentials.token)
    if user_info != (None, None):
        request.session["user_info"] = user_info
        email = user_info[0]
        db_main.store_user_login(db, email=email)
        db_main.store_user(db, email=email)
    request.session["token"] = jwt_token
    return RedirectResponse(
        url=f"/handle-token?jwt_token={jwt_token}&redirect={redirect}"
    )


@app.get("/handle-token", response_class=HTMLResponse)
async def redirect_to_handle_token_page(
    request: Request, jwt_token: str, redirect: str | None = None
):
    request.session["token"] = jwt_token
    valid_url = await is_redirect_url_valid(redirect)
    if not valid_url:
        return RedirectResponse(url="/")
        # Can create log for invalid url
    if redirect == "subscriptions/post":
        request.session["can-post"] = True
    return templates.TemplateResponse(
        "handle-token.html",
        {"request": request, "token": jwt_token, "redirect": redirect},
    )


@app.get("/subscriptions/fetch", response_class=HTMLResponse)
async def fetch_all_subscriptions(request: Request):
    token = request.session.get("token", None)
    if token is None:
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )  # RedirectResponse(url="/login")
    decoded_token = await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    try:
        subscriptions = await get_all_user_subscription(build)
    except HTTPException:
        raise HTTPException(
            status_code=404, detail={"msg": "Could not fetch subscriptions."}
        )
    user_info = request.session.get("user_info", (None, None))
    email, profile_picture = None, None
    if user_info != (None, None):
        email = user_info[0]
        profile_picture = user_info[1]
    return templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "subscriptions": subscriptions,
            "email": email,
            "profile_picture": profile_picture,
        },
    )


@app.post("/subscriptions/post", response_class=HTMLResponse)
async def post_all_subscriptions(
    request: Request, subscriptions: str | None = Body(default=None)
):
    """Get credentials for the destination account and add sunscriptions"""
    destination_account_logged_in = request.session.get(
        "destination-account-logged-in", False
    )
    can_post = request.session.get("can-post", False)
    token = request.session.get("token", False)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"msg": "Unauthorized. Ensure you are logged in. "},
        )
    if can_post and destination_account_logged_in and token:
        """Token, can_post and destination_account_logged_in are all set.
        Can_post session var determines if the subscriptions can be added.
        It is set in the /handle-token"""
        decoded_token = await decode_user_token(token)
        build = await get_authenticated_build(decoded_token)
        subscriptions = request.session.get("subscription-list")
        failed_migrations, total_sub = await post_user_subscription(
            build, subscriptions
        )
        user_info = request.session.get("user_info", (None, None))
        email, profile_picture = None, None
        if user_info != (None, None):
            email = user_info[0]
            profile_picture = user_info[1]
        request.session["email"] = email
        request.session.pop("subscriptions-list", None)
        request.session.pop("can-post", None)
        request.session.pop("destination-account-logged-in", None)
        return templates.TemplateResponse(
            "successful-migration.html",
            {
                "request": request,
                "email": email,
                "profile_picture": profile_picture,
                "failed_migrations": failed_migrations,
                "number_of_failed_subscriptions": sum(failed_migrations.values()),
                "total_subscriptions": total_sub,
            },
        )

    if not destination_account_logged_in:
        """The user has not signed into the destination account.
        The session data destination_account_logged_in is set only in /logout"""
        if subscriptions.startswith("subscriptions="):
            subscriptions = subscriptions.removeprefix("subscriptions=")
        request.session["subscription-list"] = urllib.parse.unquote(subscriptions)
        return RedirectResponse(
            url=f"/logout?redirect=subscriptions/post",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url="/login?redirect=subscriptions/fetch", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request, redirect: str = ""):
    """Revokes token and then clears all stored session data."""
    token: str = request.session.get("token", False)
    subscriptions = request.session.get("subscription-list", False)
    if token:
        credentials = await decode_user_token(token.strip())
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": credentials.get("token")},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
    request.session.clear()
    if redirect == "subscriptions/post" and subscriptions:
        request.session["subscription-list"] = subscriptions
        request.session["destination-account-logged-in"] = True
        res = templates.TemplateResponse(
            "delete-session-logout.html",
            {"request": request, "redirect": "login?redirect=subscriptions/post"},
        )
        return res
    else:
        return templates.TemplateResponse(
            "delete-session-logout.html",
            {"request": request, "redirect": redirect},
        )


@app.post("/review", response_class=JSONResponse)
async def review_modal(
    request: Request,
    review_radio: str = Form(),
    review_text: str = Form(),
    db: Session = Depends(get_db),
):
    user_info = request.session.get("user_info")
    email = user_info[0]
    db_main.store_user_review(
        db=db, review_radio=review_radio, review_text=review_text, email=email
    )
    return templates.TemplateResponse("completed-review.html", {"request": request})
