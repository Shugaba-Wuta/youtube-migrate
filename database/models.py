from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class UserLogin(Base):
    __tablename__ = "user_login"
    id = Column(Integer, autoincrement=True, primary_key=True)
    email = Column(String, ForeignKey("users.email"))
    login_datetime = Column(DateTime, default=datetime.now)
    logout_datetime = Column(DateTime, default=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, autoincrement=True)
    email = Column(String, index=True, unique=True, primary_key=True)
    # number_of_login = Column(Integer, default=0)

    reviews = relationship("Review", back_populates="reviewer")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    satisfaction_level = Column(String, nullable=False)
    review = Column(Text, nullable=False)
    review_datetime = Column(DateTime, default=datetime.now)
    reviewer_email = Column(String, ForeignKey("users.email"))

    reviewer = relationship("User", back_populates="reviews")
