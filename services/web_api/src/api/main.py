from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src.api.db.session import init_db
from src.api.routers.admin import router as admin_router
from src.api.routers.auth import router as auth_router
from src.api.routers.relational import router as relational_router
from src.api.routers.student import router as student_router
from src.api.routers.tts import router as tts_router
from src.api.security.middleware import JWTRoleMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        from src.api.db.session import get_db_session
        from src.api.db.seed import seed_database
        with get_db_session() as db:
            seed_database(db)
    except Exception as exc:
        import logging
        logging.getLogger("main").warning("Startup seed notice: %s", exc)
    yield


app = FastAPI(
    title="UKVI Credibility Interview System",
    description="FastAPI Web & SSR Portal Service for UK Academic Credibility Voice Engine",
    version="2.0.0",
    lifespan=lifespan,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Enforce JWT Role isolation and cross-site restriction across all requests
app.add_middleware(JWTRoleMiddleware)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "")
    is_html_request = "text/html" in accept and not request.url.path.startswith(("/relational", "/auth/api", "/student/api"))

    if exc.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN) and is_html_request:
        encoded_detail = quote(str(exc.detail))
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            response = RedirectResponse(
                url=f"/auth/login?error={encoded_detail}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
            response.delete_cookie(key="access_token")
            return response
        else:
            role = getattr(request.state, "role", None)
            fallback_url = "/admin" if role == "admin" else "/student"
            return RedirectResponse(
                url=f"{fallback_url}?error={encoded_detail}",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


app.include_router(auth_router)
app.include_router(relational_router)
app.include_router(admin_router)
app.include_router(student_router)
app.include_router(tts_router, prefix="/api")


@app.get("/")
def index(request: Request):
    role = getattr(request.state, "role", None)
    if role == "admin":
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    elif role == "student":
        return RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

