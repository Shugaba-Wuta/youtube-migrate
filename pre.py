import os
from dotenv import load_dotenv
import json

load_dotenv()
client_secret = os.environ.get("CLIENT_SECRET", None)
if client_secret is not None:
    with open("client_secret.json", "w") as secret:
        secret.write(client_secret)
else:
    raise NotImplemented("Please provide CLIENT SECRET in environment variables file.")
