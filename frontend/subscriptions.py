"""
This file defines all /subscription/* operations. It is mounted to app @ frontend/crud.py
"""
import json
from fastapi import APIRouter, Request, Body, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from typing import Union
import urllib.parse


from frontend.utilities import (
    get_all_user_subscription,
    get_authenticated_build,
    decode_user_token,
    migrate_user_subscription,
    get_email_and_picture_from_session,
    delete_subscriptions,
)
from .config import templates
import os
json

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "LOL JOKES,  ON YOU")


subscription_router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@subscription_router.post("/migrate", response_class=HTMLResponse)
async def migrate_all_subscriptions(
    request: Request, subscriptions: Union[str, None] = Body(default=None)
):
    """Get credentials for the destination account and add sunscriptions"""
    destination_account_logged_in = request.session.get(
        "destination-account-logged-in", False
    )
    can_migrate = request.session.get("can-migrate", False)
    token = request.session.get("token", False)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"msg": "Unauthorized. Ensure you are logged in. "},
        )
    if can_migrate and destination_account_logged_in and token:
        """Token, can_migrate and destination_account_logged_in are all set.
        Can_migrate session var determines if the subscriptions can be added.
        It is set in the /handle-token"""
        decoded_token = await decode_user_token(token)
        build = await get_authenticated_build(decoded_token)
        subscriptions = request.session.get("subscription-list")
        failed_operations, successful_operations = await migrate_user_subscription(
            build, subscriptions
        )
        total_ops = len(failed_operations) + len(successful_operations)
        email, profile_picture = await get_email_and_picture_from_session(
            request.session
        )
        """Cleaning up session on server after completing `migrate_user_subscription()`"""
        request.session.pop("subscriptions-list", None)
        request.session.pop("can-migrate", None)
        request.session.pop("destination-account-logged-in", None)
        return templates.TemplateResponse(
            "successful-operation.html",
            {
                "request": request,
                "email": email,
                "profile_picture": profile_picture,
                "failed_operations": failed_operations,
                "number_of_failed_operations": len(failed_operations),
                "total_operations": total_ops,
                "successful_operations": successful_operations,
                "entity": "Subscriptions",
                "GOOGLE_API_KEY": GOOGLE_API_KEY,
            },
        )

    if not destination_account_logged_in:
        """The user has not signed into the destination account.
        The session data destination_account_logged_in is set only in /logout"""
        if subscriptions.startswith("subscriptions="):
            subscriptions = subscriptions.replace(
                "subscriptions=", ""
            )  # removeprefix("subscriptions=")
        request.session["subscription-list"] = urllib.parse.unquote(subscriptions)
        return RedirectResponse(
            url=f"/logout?redirect=subscriptions/migrate",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url="/login?redirect=subscriptions/fetch", status_code=status.HTTP_303_SEE_OTHER
    )


@subscription_router.get("/fetch", response_class=HTMLResponse)
async def fetch_all_subscriptions(request: Request, op:str="migrate"):
    token = request.session.get("token", None)
    if token is None:
        """Making a request to /subscriptions/fetch without having session stored"""
        raise HTTPException(
            status_code=401, detail={"msg": "Unauthorized. Ensure you are logged in"}
        )
    decoded_token = await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    try:
        subscriptions = await get_all_user_subscription(build)
    except HTTPException:
        raise HTTPException(
            status_code=404, detail={"msg": "Could not fetch subscriptions."}
        )
    email, profile_picture = await get_email_and_picture_from_session(request.session)
    return templates.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "module": "subscriptions",
            "operation":op,
            "subscriptions": subscriptions,
            "email": email,
            "profile_picture": profile_picture,
        },
    )


@subscription_router.post("/unsubscribe", response_class=HTMLResponse)
async def migrate_all_subscriptions(
    request: Request, subscriptions: str = Body(default=None)
):  
    subscriptions=urllib.parse.unquote(subscriptions)
    token = request.session.get("token", False)
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"msg": "Unauthorized. Ensure you are logged in. "},
        )
    if subscriptions.startswith("subscriptions="):
        # removes prefix("subscriptions=")
        comma_sep_subscription_string = subscriptions.replace("subscriptions=", "")
        decoded_token =await decode_user_token(token)
    build = await get_authenticated_build(decoded_token)
    failed_operations, successful_operations= await delete_subscriptions(
            build, comma_sep_subscription_string  )
    total_ops = len(failed_operations) + len(successful_operations)
    email, profile_picture = await get_email_and_picture_from_session(request.session)
    return templates.TemplateResponse(
        "successful-operation.html",
        {
            "request": request,
            "email": email,
            "profile_picture": profile_picture,
            "failed_operations": failed_operations,
            "number_of_failed_operations": len(failed_operations),
            "total_operations": total_ops,
            "successful_operations": successful_operations,
            "entity": "Subscriptions",
            "GOOGLE_API_KEY": GOOGLE_API_KEY,
        },
    )
    # request.session["subscription-list"] = urllib.parse.unquote(subscriptions)
