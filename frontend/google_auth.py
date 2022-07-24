from imp import reload
from platform import release
from fastapi import FastAPI, Depends, Response, Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2AuthorizationCodeBearer
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow
import os
import dotenv
import uvicorn


app = FastAPI()
app.add_middleware(SessionMiddleware)

oauth2_scheme = OAuth2AuthorizationCodeBearer("/oauth", "/token")


async def get_user(token: Depends(oauth2_scheme)):
    return token


@app.get("", response_class=HTMLResponse)
async def index():
    return "<a href='/login'>Login</a>"


@app.get("/login/")
async def login(token=Depends(get_user)):
    return token


@app.get("/oauth")
async def oauth_flow(request: Request):
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["openid", "https://www.googleapis.com/auth/youtube"],
    )
    auth_url, state = flow.authorization_url()
    request.session["state"] = state

    return auth_url


app.get("/token/")


async def fetch_token(request: Request):
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["openid", "https://www.googleapis.com/auth/youtube"],
    )

    flow.redirect_uri("http://localhost:5333/token")
    credentials = flow.credentials
    return {
        "access_token": credentials.token,
        "token_type": "bearer",
    }


if __name__ == "__main__":
    dotenv.load_dotenv()
    uvicorn.run("google_auth:app", reload=True, port=5333)
