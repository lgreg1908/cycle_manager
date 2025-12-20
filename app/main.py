from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.root import router as root_router

app = FastAPI(title="HR Cycle Manager")

app.include_router(root_router)  
app.include_router(health_router)
app.include_router(me_router)
