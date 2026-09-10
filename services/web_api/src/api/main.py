from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src.api.db.session import init_db
from src.api.routers.admin import router as admin_router
from src.api.routers.auth import router as auth_router
from src.api.routers.relational import router as relational_router
from src.api.routers.student import router as student_router

app = FastAPI(
    title="UKVI Credibility Interview System",
    description="FastAPI Web & SSR Portal Service for UK Academic Credibility Voice Engine",
    version="2.0.0",
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(auth_router)
app.include_router(relational_router)
app.include_router(admin_router)
app.include_router(student_router)


@app.get("/")
def index(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/auth/login")
    return RedirectResponse(url="/student")
