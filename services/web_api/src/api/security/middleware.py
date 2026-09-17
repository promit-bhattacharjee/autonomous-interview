import jwt
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from src.api.security.auth import ALGORITHM, JWT_SECRET


class JWTRoleMiddleware(BaseHTTPMiddleware):
    """
    Decodes JWT access tokens and enforces strict cross-site role isolation:
    - Students are strictly restricted from accessing /admin routes.
    - Admins are strictly restricted from accessing /student routes.
    - Root / dynamically routes authenticated users to their dedicated portal.
    - Public /auth routes redirect already authenticated users to their respective home.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Bypass static assets, API docs, and OpenAPI schema
        if path.startswith(("/static", "/docs", "/openapi.json", "/redoc", "/favicon.ico")):
            return await call_next(request)

        token: Optional[str] = request.cookies.get("access_token")
        auth_hdr = request.headers.get("authorization")
        if not token and auth_hdr and auth_hdr.startswith("Bearer "):
            token = auth_hdr.split(" ", 1)[1]

        user_id: Optional[str] = None
        role: Optional[str] = None
        device_id: Optional[str] = None
        is_token_expired = False

        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
                user_id = payload.get("sub")
                role = payload.get("role")
                device_id = payload.get("device_id")
                request.state.user_id = user_id
                request.state.role = role
                request.state.device_id = device_id
                request.state.jwt_payload = payload
            except jwt.ExpiredSignatureError:
                is_token_expired = True
                request.state.user_id = None
                request.state.role = None
                request.state.device_id = None
            except jwt.PyJWTError:
                request.state.user_id = None
                request.state.role = None
                request.state.device_id = None
        else:
            request.state.user_id = None
            request.state.role = None
            request.state.device_id = None

        accept = request.headers.get("accept", "")
        is_html_req = "text/html" in accept and not path.startswith(("/auth/api", "/student/api", "/relational"))

        # 1. Root / routing
        if path == "/":
            if role == "admin":
                return RedirectResponse(url="/admin", status_code=303)
            elif role == "student":
                return RedirectResponse(url="/student", status_code=303)
            else:
                return RedirectResponse(url="/auth/login", status_code=303)

        # 2. Redirect already logged-in users away from /auth/login and /auth/register (GET requests)
        if request.method == "GET" and path in ("/auth/login", "/auth/register"):
            if role == "admin":
                return RedirectResponse(url="/admin", status_code=303)
            elif role == "student":
                return RedirectResponse(url="/student", status_code=303)

        # 3. Admin portal protection & Cross-site restriction
        if path == "/admin" or path.startswith("/admin/"):
            if not user_id:
                if is_html_req:
                    detail = "Session expired. Please log in again." if is_token_expired else "Please log in to access the Admin Portal."
                    res = RedirectResponse(url=f"/auth/login?error={detail}", status_code=303)
                    if is_token_expired:
                        res.delete_cookie(key="access_token")
                    return res
                return JSONResponse(status_code=401, content={"detail": "Authentication required."})

            if role != "admin":
                # Strict Cross-site restriction: Student cannot enter Admin portal
                if is_html_req:
                    return RedirectResponse(url="/student?error=Access+denied+Admin+privileges+required", status_code=303)
                return JSONResponse(status_code=403, content={"detail": "Administrative privileges required."})

        # 4. Student portal protection & Cross-site restriction
        if path == "/student" or path.startswith("/student/"):
            if not user_id:
                if is_html_req:
                    detail = "Session expired. Please log in again." if is_token_expired else "Please log in to access the Student Portal."
                    res = RedirectResponse(url=f"/auth/login?error={detail}", status_code=303)
                    if is_token_expired:
                        res.delete_cookie(key="access_token")
                    return res
                return JSONResponse(status_code=401, content={"detail": "Authentication required."})

            if role != "student":
                # Strict Cross-site restriction: Admin cannot enter Student portal
                if is_html_req:
                    return RedirectResponse(url="/admin?error=Access+denied+Student+portal+is+for+candidates+only", status_code=303)
                return JSONResponse(status_code=403, content={"detail": "Student privileges required."})

        response = await call_next(request)
        return response
