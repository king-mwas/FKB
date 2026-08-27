from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from webapp.backend.auth import password_ok
from webapp.backend.templates import templates

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_form(request: Request):
    if request.session.get("authed"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(request: Request, password: str = Form("")):
    if not password_ok(password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Incorrect password."},
            status_code=401)
    # New session id on login so a cookie captured before authenticating
    # can't be replayed as an authenticated one.
    request.session.clear()
    request.session["authed"] = True
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
