"""
This file: 1. Configures `templates` for use by different APIRouter and FastAPI instance(s)
           2. Modifies and loads the default Bootstrap variables to desired application needs. Check frontend/static/css/modification.scss.css to see the compiled Bootstrap. 
"""
from fastapi.templating import Jinja2Templates
import sass
from pathlib import Path

BASE_PATH = Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=f"{BASE_PATH}/templates")
# Setting up Sass to modify bootstrap variables
sass.compile(dirname=("frontend/static/sass", "frontend/static/css"))
