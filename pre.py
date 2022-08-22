import os 
from dotenv import load_dotenv

load_dotenv()
ONLINE = os.environ.get("ONLINE", False) 
client_secret = os.environ.get("CLIENT_SECRET", None)
if ONLINE and client_secret is not None: 
  with open("client_secret.json", "w") as secret: 
    secret.write(client_secret)
