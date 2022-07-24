{
    "id": "102736300482635307663",
    "email": "shugaba.wuta@aun.edu.ng",
    "verified_email": True,
    "name": "Shugaba Abraham Wuta",
    "given_name": "Shugaba Abraham",
    "family_name": "Wuta",
    "picture": "https://lh3.googleusercontent.com/a/AItbvml8dY4DvstynOW43JNDN31F87TuD-hjEqCg2LUA=s96-c",
    "locale": "en",
    "hd": "aun.edu.ng",
}
from pydantic import BaseModel
from fastapi import Query


class BasicUserInfo(BaseModel):
    email: str
    picture: str


class UserInfo(BasicUserInfo):
    id: int
    verified_email: bool
    name: str
    given_name: str
    family_name: str | None = None
    locale: str | None = None
    hd: str | None = None


class GoogleCredential(BaseModel):
    token: str
    refresh_token: str
    token_uri: str
    expiry: str
    scopes: list[str] = ["https://www.googleapis.com/auth/youtube"]


class CompleteGoogleCredential(GoogleCredential):
    client_id: str
    client_secret: str


class Token(BaseModel):
    token: str
