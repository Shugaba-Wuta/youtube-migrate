from sqlalchemy.orm import Session
from database.models import Review, User, UserLogin


def store_user_review(db: Session, review_radio: str, review_text: str, email: str):
    if not user_in_db(db, email=email):
        store_user(db=db, email=email)
    review: Review = Review(
        review=review_text, satisfaction_level=review_radio, reviewer_email=email
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def store_user_login(db: Session, email: str):
    user_login = UserLogin(email=email)
    if not user_in_db(db, email=email):
        store_user(db, email=email)
    db.add(user_login)
    db.commit()
    db.refresh(user_login)
    return user_login


def store_user(db: Session, email: str):
    db_user = get_user(db, email=email)
    if db_user:
        return db_user
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, email: str):
    user = db.query(User).filter(User.email == email).first()
    return user


def user_in_db(db: Session, email: str) -> bool:
    user = get_user(db, email)
    return True if user else False
