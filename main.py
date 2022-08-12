from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv
import os
load_dotenv(".env")

import pre
from frontend.crud import app



# if __name__ == "__main__":
# # A custom way of starting the server.
# # ACtivated by runnning this file as a regular python script
#     uvicorn.run("main:app")
