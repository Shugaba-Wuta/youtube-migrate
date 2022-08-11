import os 
from dotenv import load_dotenv

load_dotenv()
environ = os.environ.get("ONLINE", False) 
client_secret = os.environ.get("CLIENT_SECRET", None)
if environ and client_secret is not None: 
  with open("client_secret.json", "w") as secret: 
    secret.write(client_secret)
