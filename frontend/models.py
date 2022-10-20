from datetime import datetime
import enum
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
    family_name: Union[str, None] = None
    locale: Union[str, None] = None
    hd: Union[str, None] = None


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


class Owner(BaseModel):
    user_id: str
    created_at: Union[datetime, None] = None


class PlaylistItem(BaseModel):
    id: Union[int, None] = None
    user_id: str
    originating_playlist_id: str
    destination_playlist_id: Union[str, None] = None
    updated_id: bool = False
    position: int
    note: Union[str, None] = None
    resource_id: str
    resource_kind: str


class PrivacyStatusList(str, enum.Enum):
    private: str = "private"
    unlisted: str = "unlisted"
    public: str = "public"


class Playlist(BaseModel):
    id: Union[int, None] = None
    user_id: str
    playlist_id: str
    title: str
    description: Union[str, None] = None
    privacy_status: PrivacyStatusList
    default_lang: Union[str, None] = None

    class Config:
        use_enum_values = True
