from fastapi import APIRouter

from app.api.v1.endpoints import example, health, hello

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(hello.router, tags=["Hello"])
api_router.include_router(example.router, tags=["Example"])
