from fastapi import (
    APIRouter,
    Response,
    Request,
    HTTPException,
    Form,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Dict, List, Union
from sqlalchemy.ext.asyncio import AsyncSession
import json


from .utilities import (
    get_authenticated_build,
    decode_user_token,
    make_resource_owner,
    is_token_valid,
    get_email_and_picture_from_session,
    get_all_user_playlists_from_gapi,
    fetch_all_playlist_items_from_gapi,
    get_gapi_build,
    migrate_playlist_in_background,
    test_getting_db_session,
    test_getting_db_session2,
)
from database.memory_db_models import Playlist, Owner, PlaylistItem
from .config import templates

from database.memory_db import mem_db
import core.models as models
from core.redis_storage.main import *


playlists_router = APIRouter(prefix="/playlists", tags=["playlists"])


@playlists_router.get("/fetch")
async def fetch_all_playlists_on_authorized_account(
    request: Request,
    op: str = "migrate",
):
    user: models.Owner = make_resource_owner(request)
    token = request.session.get("token", False)
    print("zhzhzh-" * 100, user)

    if not is_token_valid(token):
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )
    decoded_token = decode_user_token(token)
    build = get_authenticated_build(decoded_token)
    playlists = await get_all_user_playlists_from_gapi(build)
    email, profile_picture = get_email_and_picture_from_session(request.session)
    print(user, end="\n\n\n\n")
    return templates.TemplateResponse(
        "playlists.html",
        {
            "request": request,
            "module": "playlists",
            "operation": op,
            "playlists": playlists,
            "email": email,
            "profile_picture": profile_picture,
        },
    )


@playlists_router.post("/migrate", response_class=RedirectResponse)
async def collate_and_store_all_selected_playlists(
    request: Request, playlists: Union[str, None] = Form(default=None)
):
    owner = make_resource_owner(request)
    build = get_gapi_build(request)
    json_playlists = json.loads(playlists)
    playlist_model_list = [
        models.Playlist(
            user_id=owner.user_id,
            playlist_id=resource["playlistId"],
            title=resource["playlistTitle"],
            description=resource["playlistDescription"],
            privacy_status=resource["privacyStatus"],
            default_lang=resource["playlistDefaultLanguage"],
        )
        for resource in json_playlists
    ]
    mem_db.store_playlists(playlist_model_list)

    # Fetch all playlist_items for each playlist resource and persist in mem_db
    for playlist_model in playlist_model_list:
        playlist_items = await fetch_all_playlist_items_from_gapi(
            build=build, playlist_model=playlist_model
        )
        mem_db.store_playlist_items(playlist_items)
    return RedirectResponse(
        url="/logout?redirect=playlists/migrated", status_code=status.HTTP_303_SEE_OTHER
    )


@playlists_router.get("/migrated")
async def after_signing_into_destination_acct(request: Request):
    """Add playlist ad playlist_items to the new YouTube account"""
    owner = make_resource_owner(request)
    build = get_gapi_build(request)
    user_id: str = owner.user_id
    if not user_id:
        raise HTTPException(
            status_code=404, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )
    playlists = mem_db.get_playlists(user_id)
    email, _ = get_email_and_picture_from_session(request.session)

    # migrate playlists and send email in the background.
    # migrate_playlist_in_background.delay(build, playlists, email, user_id)
    return {"waiting": "count-down"}
