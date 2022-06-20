from fastapi import FastAPI
import uvicorn


from frontend.main import frontend

app = FastAPI()

app.mount("/", frontend)


if __name__ == "__main__":
    # A custom way of starting the server.
    # ACtivated by runnning this file as a regular python script
    uvicorn.run("main:app", reload=True, port=5333, host="127.0.0.10")
