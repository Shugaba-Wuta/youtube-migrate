from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Owner(Base):
    __tablename__ = "owner"
    user_id = Column(String, primary_key=True, unique=True, nullable=False, index=True)
    created_at = Column(String, default=datetime.now().astimezone().isoformat())

    def __repr__(self):
        return f"Owner<'user_id': {self.user_id}, 'created_at': {self.created_at}>"

    def __str__(self):
        return self.__repr__()


class Playlist(Base):
    __tablename__ = "playlists"
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    user_id = Column(String, ForeignKey("owner.user_id", ondelete="CASCADE"))
    playlist_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default=None)
    privacy_status = Column(String, nullable=False)
    default_lang = Column(String)
    uploaded_at = Column(String, default=datetime.now().astimezone().isoformat())
    playlist_items = relationship(
        "PlaylistItem", backref="in_same_playlist", lazy="subquery"
    )

    def __repr__(self):
        return f"Playlist<'id': {self.id} 'user_id': {self.user_id}, 'playlist_id': {self.playlist_id}, 'title': {self.title}, 'description': {self.description}, 'privacy_status': {self.privacy_status}>"

    def __str__(self):
        return self.__repr__()


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    originating_playlist_id = Column(
        String, ForeignKey("playlists.playlist_id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(String, ForeignKey("owner.user_id"))
    destination_playlist_id = Column(String, nullable=True, default=None)
    updated_id = Column(Boolean, default=False)
    position = Column(Integer)
    note = Column(Text, default="")
    resource_id = Column(String, nullable=False)
    resource_kind = Column(String, nullable=False)
    title = Column(String, nullable=False)
    uploaded_at = Column(String, default=datetime.now().astimezone().isoformat())
    # relationship from Playlist creates a new attribute 'in_same_playlist'

    def __repr__(self):
        return f"PlaylistItem<'id': {self.id}, 'originating_playlist_id': {self.originating_playlist_id}, 'destination_playlist_id': {self.destination_playlist_id}, 'update_id': {self.updated_id},  'position': {self.position}>"

    def __str__(self):
        return self.__repr__()
