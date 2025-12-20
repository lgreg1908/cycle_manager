from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def root():
    return {
        "name": "HR Platform Backend",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }
