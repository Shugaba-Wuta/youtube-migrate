from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert
from typing import List
import asyncio
from database.in_memory_db_models import *
from fastapi import Request, HTTPException, Depends
from database.in_memory_db import memory_db as db, InMemoryDatabase
import frontend.models as models


def setup_mem_db(db=db):
    return db


async def get_owner(session: AsyncSession, user_id: str):
    stmt = select(Owner).where(Owner.user_id == user_id)
    async with session:
        result = await session.execute(stmt)
    return result.scalar()


async def create_user_id(session: AsyncSession, user_id):
    record_exists = await get_owner(session, user_id)
    if record_exists:
        return record_exists
    async with session:
        owner = Owner(user_id=user_id)
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
    return owner


async def get_playlist_from_mem_db(
    session: AsyncSession, playlist_id: str, user_id: str
):
    stmt = (
        select(Playlist)
        .where(Playlist.user_id == user_id)
        .where(Playlist.playlist_id == playlist_id)
    )
    async with session:
        result = await session.execute(stmt)
    return result.first()


async def batch_insert_playlist(
    session: AsyncSession, playlist_model_list: List[models.Playlist]
):
    playlist_orm_list = []
    for playlist_model in playlist_model_list:
        playlist_exists = await get_playlist_from_mem_db(
            session, playlist_model.playlist_id, playlist_model.user_id
        )
        if not playlist_exists:
            playlist_orm_list.append(Playlist(**playlist_model.dict(exclude_none=True)))
    async with session:
        session.add_all(playlist_orm_list)
        await session.commit()


async def get_unique_playlist_item(session: AsyncSession, playlist_id, resource_id):
    stmt = (
        select(PlaylistItem)
        .where(PlaylistItem.originating_playlist_id == playlist_id)
        .where(PlaylistItem.resource_id == resource_id)
    )
    async with session:
        result = await session.execute(stmt)
    return result.first()


async def batch_insert_playlist_items_into_mem_db(
    session: AsyncSession, playlist_item_list: List[models.PlaylistItem]
):
    for playlist_item in playlist_item_list:
        playlist_item_exists = await get_unique_playlist_item(
            session,
            playlist_item.originating_playlist_id,
            playlist_item.resource_id,
        )
        if playlist_item_exists:
            continue
        async with session:
            playlist_item_orm = PlaylistItem(**playlist_item.dict(exclude_none=True))
            session.add(playlist_item_orm)
            await session.commit()
            await session.refresh(playlist_item_orm)


async def get_updated_user_playlist_items(user_id: str, db: AsyncSession):
    async with db:
        result = (
            (
                await db.execute(
                    select(PlaylistItem)
                    .where(PlaylistItem.user_id == user_id)
                    .where(PlaylistItem.updated_id == True)
                )
            )
            .scalars()
            .all()
        )
        return result


async def get_all_user_playlist(db: AsyncSession, user_id: str):
    stmt = select(Playlist).where(Playlist.user_id == user_id)
    async with db:
        result = (await db.execute(stmt)).scalars().all()
        return result


async def batch_update_destination_id_for_playlist_items(
    user_id: str,
    originating_playlist_id: str,
    destination_playlist_id: str,
):

    db = setup_mem_db()
    await (db.setup())
    db: AsyncSession = db.get_session()
    update_destination_id_stmt = (
        update(PlaylistItem)
        .where(PlaylistItem.user_id == user_id)
        .where(PlaylistItem.originating_playlist_id == originating_playlist_id)
        .values(destination_playlist_id=destination_playlist_id, updated_id=True)
    )
    async with db:
        await db.execute(update_destination_id_stmt)
        await db.commit()
        await db.close()
