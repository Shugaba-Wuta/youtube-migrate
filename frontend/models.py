from pydantic import BaseModel
from typing import Union, List


class User(BaseModel):
    email: str

    class Config:
        orm_mode = True


class UserLogin(User):
    pass


class UserInfo(User):
    id: int
    picture: str
    verified_email: bool
    name: str
    given_name: str
    family_name: Union[str , None] = None
    locale: Union[str , None] = None
    hd: Union[str , None]= None


class Review(BaseModel):
    reviewer_email: str
    review: str
    satisfaction_level: str

    class Config:
        orm_mode = True


class GoogleCredential(BaseModel):
    token: str
    refresh_token: str
    token_uri: str
    expiry: str
    scopes: List[str] = ["https://www.googleapis.com/auth/youtube"]


class CompleteGoogleCredential(GoogleCredential):
    client_id: str
    client_secret: str


class Token(BaseModel):
    token: str
