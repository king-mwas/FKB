"""
Single shared Jinja2Templates instance for the whole app (main.py + every
router that renders HTML). Template caching is disabled (cache_size=0) —
this app's traffic is a single local user, template reparsing is cheap, and
it sidesteps a Jinja2 LRUCache thread-safety issue seen under concurrent
first-load access from FastAPI's sync-endpoint threadpool.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent  # webapp/
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), cache_size=0, autoescape=True)
templates = Jinja2Templates(env=_env)
