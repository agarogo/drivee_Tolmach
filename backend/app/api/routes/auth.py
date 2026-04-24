from app.api.common import *


router = APIRouter(tags=["Auth"])


@router.post("/auth/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректный email")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Пользователь уже существует")
    user = User(
        email=email,
        full_name=payload.full_name or email.split("@", 1)[0],
        password_hash=hash_password(payload.password),
        role="user",
        preferences={"theme": "dark"},
    )
    db.add(user)
    await db.flush()
    bundle = await create_session_bundle(db, user=user, device_hint=_device_hint(request))
    apply_session_cookies(response, bundle)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=to_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if needs_password_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.utcnow()
    bundle = await create_session_bundle(db, user=user, device_hint=_device_hint(request))
    apply_session_cookies(response, bundle)
    await db.commit()
    return AuthResponse(user=to_user_out(user))


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LogoutResponse:
    await revoke_session(db, request.cookies.get(settings.session_cookie_name))
    await db.commit()
    clear_session_cookies(response)
    return LogoutResponse(ok=True)


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)
