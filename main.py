from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv
import os
load_dotenv(".env")


environ = os.environ.get("ONLINE", False) 
client_secret = os.environ.get("CLIENT_SECRET", None)
if environ and client_secret is not None: 
  with open("client_secret.json", "w") as secret: 
    secret.write(client_secret)

from frontend.crud import app



if __name__ == "__main__":
# A custom way of starting the server.
# ACtivated by runnning this file as a regular python script
    uvicorn.run("main:app")
