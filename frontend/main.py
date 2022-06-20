# Fastapi and related packages
from fastapi import Depends, FastAPI, Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Other packages
import sass
from pathlib import Path

# Google API Client
import googleapiclient


BASE_PATH = Path(__file__).parent.resolve()


frontend = FastAPI()


templates = Jinja2Templates(directory=f"{BASE_PATH}/templates")

frontend.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Setting up Sass
sass.compile(dirname=("frontend/static/sass", "frontend/static/css"))


async def get_gmail_account():
    return "String I love you Jesus"


@frontend.get("/", response_class=HTMLResponse)
def index(request: Request, d=Depends(get_gmail_account)):
    # response: Response = request
    return templates.TemplateResponse("index.html", {"request": request, "data": d})


@frontend.get("/migrate", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("subscription.html", {"request": request})


@frontend.get("/successful", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("successful-migration.html", {"request": request})


@frontend.get("/unsuccessful", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("failed-migration.html", {"request": request})


@frontend.get("/review", response_class=HTMLResponse)
def process_review(request: Request):
    return templates.TemplateResponse("successful-migration.html", {"request": request})
