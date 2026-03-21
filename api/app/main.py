from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes.routing import router as routing_router

app = FastAPI(
    title="Perth PSP-Priority Cycling Router",
    description="A cycling route planner that maximises Principal Shared Path (PSP) usage in Perth, WA",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routing_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def web_app():
    """Serve the lightweight local MVP web client."""
    return FileResponse("app/static/index.html")
