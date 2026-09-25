import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.ratelimit import limit_auth
from app.services import plaid_service

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# bcrypt only uses the first 72 bytes of a password.
_BCRYPT_MAX_BYTES = 72
# Compared against when the email is unknown so login time doesn't reveal which emails exist.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


# ---------- Schemas ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordConfirmation(BaseModel):
    password: str = Field(max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


# ---------- Helpers ----------

def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode())
    except ValueError:  # malformed hash
        return False


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise credentials_error

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


# ---------- Routes ----------

@router.post(
    "/register", response_model=TokenResponse, status_code=201, dependencies=[Depends(limit_auth)]
)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=email, hashed_password=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(limit_auth)])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username.lower()).first()
    password_ok = verify_password(form.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


def _require_password(user: User, password: str) -> None:
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Incorrect password")


@router.post("/change-password", status_code=204, dependencies=[Depends(limit_auth)])
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_password(current_user, body.current_password)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Choose a different password")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()


@router.post("/delete-account", status_code=204, dependencies=[Depends(limit_auth)])
def delete_account(
    body: PasswordConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete the user and everything stored for them, after re-checking the password.

    Bank connections are revoked at Plaid first (best effort: a failure there must not stop
    the user from deleting their data).
    """
    _require_password(current_user, body.password)
    for item in current_user.plaid_items:
        try:
            plaid_service.remove_item(item.access_token)
        except Exception as exc:  # PlaidError, or a network failure
            logger.warning("Could not revoke Plaid item %s during account deletion: %s", item.id, exc)
    db.delete(current_user)
    db.commit()
