from fastapi import APIRouter, Response, Request, HTTPException
from fastapi.responses import JSONResponse

from .utilities import (
    get_authenticated_build,
    decode_user_token,
    is_token_valid,
    get_email_and_picture_from_session,
    get_all_user_playlists,
)
from .config import templates

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
    playlists = await get_all_user_playlists(build)
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


@playlists_router.get("/migrate", response_class=JSONResponse)
async def migrate_playlists_to_another_account(playlists: str):
    return {}
