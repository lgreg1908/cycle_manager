from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.root import router as root_router
from app.api.admin import router as admin_router
from app.api.cycles import router as cycles_router
from app.api.assignments import router as assignments_router
from app.api.evaluations import router as evaluations_router
from app.api.audit import router as audit_router
from app.api.forms import router as forms_router
from app.api.employees import router as employees_router

app = FastAPI(title="HR Cycle Manager")

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(root_router)  
app.include_router(health_router)
app.include_router(me_router)
app.include_router(admin_router)
app.include_router(cycles_router)
app.include_router(assignments_router)
app.include_router(evaluations_router)
app.include_router(audit_router)
app.include_router(forms_router)
app.include_router(employees_router)
