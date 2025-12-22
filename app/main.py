from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.root import router as root_router
from app.api.admin import router as admin_router
from app.api.cycles import router as cycles_router
from app.api.assignments import router as assignments_router

app = FastAPI(title="HR Cycle Manager")

app.include_router(root_router)  
app.include_router(health_router)
app.include_router(me_router)
app.include_router(admin_router)
app.include_router(cycles_router)
app.include_router(assignments_router)
