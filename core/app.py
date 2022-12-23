# Fastapi and related packages
from fastapi import (
    FastAPI,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

# Other packages
import os
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
import json
from typing import Union, Optional
from sqlalchemy.orm import Session
from googleapiclient.errors import *
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

# # Local imports
from core.models import (
    CompleteGoogleCredential,
)
from .config import templates

from core.utilities import (
    is_token_valid,
    start_google_flow,
    make_jwt_from_credential,
    is_redirect_url_valid,
    get_user_email_info,
    get_email_and_picture_from_session,
    retire_token,
)
from .subscriptions import subscription_router
from .playlists import playlists_router

# Imports from database
from database import (
    database,
    models,
    main as db_main,
)
from database.database import get_db
from database.in_memory_db import memory_db


models.Base.metadata.create_all(bind=database.engine)
app = FastAPI(docs_url=None, redoc_url=None)


@app.on_event("startup")
async def setup_db():
    await memory_db.setup()


app.include_router(subscription_router)
app.include_router(playlists_router)


SESSIONMIDDLEWARE_SECRET_KEY = os.environ.get("MIDDLEWARE_SECRET_KEY")
GOOGLE_AUTH_REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5333/token")


if SESSIONMIDDLEWARE_SECRET_KEY is None:
    raise ValueError("Set the API_KEY variable is None")
app.mount("/static", StaticFiles(directory="core/static"), name="static")
# Adding middlewares to app
app.add_middleware(SessionMiddleware, secret_key=SESSIONMIDDLEWARE_SECRET_KEY)
app.add_middleware(GZipMiddleware, minimum_size=20)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#
###ADDING ALL EXCEPTIONS TO APP
#
# class based exceptions
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


@app.exception_handler(Exception)
async def generic_response(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 404,
            "msg": "Encountered an error, while processing request. Kindly Logout and start again.",
        },
    )


# error code based exceptions.
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
        {"request": request, "status_code": 422, "msg": "Unprocessable Entity"},
    )


@app.exception_handler(405)
async def handle_405_exceptions(request, exc):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "status_code": 405, "msg": "Method not Allowed"},
    )


##ROOT URL OPERATIONS
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(memory_db.get_session)):

    email, profile_picture = await get_email_and_picture_from_session(request.session)
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
    request.session["redirect"] = redirect
    response = RedirectResponse(url=auth_url)
    return response


@app.get("/token", response_class=RedirectResponse)
async def get_permission(request: Request, db: Session = Depends(get_db)):
    state = request.session.get("state", None)
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["https://www.googleapis.com/auth/youtube"],
        state=state,
    )
    flow.redirect_uri = GOOGLE_AUTH_REDIRECT_URI  # + f"?redirect={redirect}"
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
            status_code=422,
            detail={"msg": "Encountered unprocessable response while logging user in."},
        )
    credentials = flow.credentials
    json_credentials = json.loads(credentials.to_json())
    jwt_token = await make_jwt_from_credential(
        credential=CompleteGoogleCredential(**json_credentials)
    )
    user_info = await get_user_email_info(credentials.token)
    if all(user_info):
        request.session["user_info"] = user_info
        email = user_info[0]
        db_main.store_user_login(db, email=email)
        db_main.store_user(db, email=email)
    request.session["token"] = jwt_token
    redirect = request.session.get("redirect", "")
    request.session.pop("redirect", None)
    return RedirectResponse(
        url=f"/handle-token?jwt_token={jwt_token}&redirect={redirect}"
    )


@app.get("/handle-token", response_class=HTMLResponse)
async def redirect_to_handle_token_page(
    request: Request, jwt_token: str, redirect: Union[str, None] = None
):
    request.session["token"] = jwt_token
    valid_url = await is_redirect_url_valid(redirect)
    if not valid_url:
        return RedirectResponse(url="/")
        # Can create log for invalid url
    if redirect == "subscriptions/migrate":
        request.session["can-migrate"] = True
    return templates.TemplateResponse(
        "handle-token.html",
        {"request": request, "token": jwt_token, "redirect": redirect},
    )


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request, redirect: str = ""):
    """Revokes token and then clears all stored session data."""
    token: str = request.session.get("token", False)
    subscription_id = request.session.get("subscription-list-id") or "khbjbkbjb"
    subscriptions = os.environ.get(subscription_id, False)
    user_id = request.session.get("user-id", False)
    if token:
        await retire_token(token)
    request.session.clear()
    if redirect == "subscriptions/migrate" and subscriptions:
        request.session["subscription-list-id"] = subscription_id
        request.session["destination-account-logged-in"] = True
        res = templates.TemplateResponse(
            "delete-session-logout.html",
            {"request": request, "redirect": "login?redirect=subscriptions/migrate"},
        )
        return res
    elif redirect == "playlists/migrated" and user_id:
        request.session["user-id"] = user_id
        res = templates.TemplateResponse(
            "delete-session-logout.html",
            {"request": request, "redirect": "login?redirect=playlists/migrated"},
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
    email, profile_picture = await get_email_and_picture_from_session(request.session)
    db_main.store_user_review(
        db=db, review_radio=review_radio, review_text=review_text, email=email
    )
    return templates.TemplateResponse(
        "completed-review.html",
        {
            "request": request,
            "email": email,
            "profile_picture": profile_picture,
        },
    )


@app.get("/privacy")
async def privacy_page(request: Request):
    email, profile_picture = await get_email_and_picture_from_session(request.session)
    return templates.TemplateResponse(
        "privacy.html",
        {"request": request, "email": email, "profile_picture": profile_picture},
    )


@app.get("/playlist")
async def playlist_wip(request: Request):
    return templates.TemplateResponse(
        "playlists.html",
        {
            "request": request,
            "module": "playlists",
            "operation": "op",
            "playlists": "playlists",
            "email": "email",
            "profile_picture": "profile_picture",
        },
    )


@app.get("/test")
async def test_celery_functionality():
    from core.background_app.tasks import first_task

    print(first_task.delay)
    called_func = first_task.delay()
    return JSONResponse({"success": "bla bla", "id": called_func.id}, status_code=200)
