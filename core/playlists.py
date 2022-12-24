from fastapi import (
    APIRouter,
    Response,
    Request,
    HTTPException,
    Form,
    Body,
    Depends,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Dict, List, Union
from sqlalchemy.ext.asyncio import AsyncSession
import json


from .utilities import (
    create_playlist_gapi,
    get_authenticated_build,
    decode_user_token,
    make_resource_owner,
    is_token_valid,
    get_email_and_picture_from_session,
    get_all_user_playlists_from_gapi,
    fetch_all_playlist_items_from_gapi,
    get_gapi_build,
    add_playlist_items_to_gapi,
    convert_model_list_to_json,
)
from database.in_memory_db_models import Playlist, Owner, PlaylistItem
from database.in_memory_db import InMemoryDatabase
from database.in_memory_db_main import *
from .config import templates
from database.in_memory_db import memory_db as db
import core.models as models
from redis_storage.main import *


playlists_router = APIRouter(prefix="/playlists", tags=["playlists"])


@playlists_router.get("/fetch")
async def fetch_all_playlists_on_authorized_account(
    request: Request, op: str = "migrate"
):
    token = request.session.get("token", False)
    if not await is_token_valid(token):
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )
    decoded_token = await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    playlists = await get_all_user_playlists_from_gapi(build)
    email, profile_picture = await get_email_and_picture_from_session(request.session)
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
    request: Request,
    playlists: Union[str, None] = Form(default=None),
    db: AsyncSession = Depends(db.get_session),
    owner: models.Owner = Depends(make_resource_owner),
    build=Depends(get_gapi_build),
):
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
    # Async SQLite storage
    await batch_insert_playlist(db, playlist_model_list)
    # Redis storage
    await store_playlist_redis_db(owner.user_id, json_playlists)

    #
    # Stage 2: Fetch all playlist_items for each playlist resource and persist
    #
    for playlist_model in playlist_model_list:
        playlist_items: List[
            models.PlaylistItem
        ] = await fetch_all_playlist_items_from_gapi(
            build=build, playlist_model=playlist_model
        )
        # Using the aiosqlite model to store selected playlist items
        await batch_insert_playlist_items_into_mem_db(db, playlist_items)
        playlist_items_dict = await convert_model_list_to_json(playlist_items)
        # Using redis to store the selected playlist items
        await store_playlist_items_redis_db(owner.user_id, playlist_items_dict)
    return RedirectResponse(
        url="/logout?redirect=playlists/migrated", status_code=status.HTTP_303_SEE_OTHER
    )


@playlists_router.get("/migrated")
async def after_signing_into_destination_acct(
    request: Request,
    db: AsyncSession = Depends(db.get_session),
    user: models.Owner = Depends(make_resource_owner),
    build=Depends(get_gapi_build),
):
    """Add playlist ad playlist_items to the new YouTube account"""
    user_id: str = user.user_id
    if not user_id:
        raise HTTPException(
            status_code=404, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )
    playlists: List[Playlist] = await get_all_user_playlist(db, user_id)
    playlists_redis_db: List[Playlist] = await retrieve_playlist_redis_db(user_id)

    playlist_model_list: List[models.Playlist] = [
        models.Playlist(
            id=playlist.id,
            user_id=playlist.user_id,
            playlist_id=playlist.playlist_id,
            title=playlist.title,
            description=playlist.description,
            privacy_status=playlist.privacy_status,
            default_lang=playlist.default_lang,
        )
        for playlist in playlists
    ]
    await create_playlist_gapi(build, playlist_model_list=playlist_model_list)

    playlist_items: List[PlaylistItem] = await get_updated_user_playlist_items(
        user_id, db
    )

    playlist_item_model_list: List[models.PlaylistItem] = [
        models.PlaylistItem(
            id=playlist_item.id,
            user_id=user_id,
            originating_playlist_id=playlist_item.originating_playlist_id,
            destination_playlist_id=playlist_item.destination_playlist_id,
            updated_id=playlist_item.updated_id,
            position=playlist_item.position,
            note=playlist_item.note,
            resource_id=playlist_item.resource_id,
            resource_kind=playlist_item.resource_kind,
        )
        for playlist_item in playlist_items
    ]
    await add_playlist_items_to_gapi(build, playlist_item_model_list)
    return {
        "playlists": len(playlists),
        "playlist_item_model_list": len(playlist_item_model_list),
        "playlist_items": len(playlist_items),
        "user_id": user_id,
    }