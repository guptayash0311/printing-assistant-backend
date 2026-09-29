from fastapi import APIRouter

from app.api.routes import admin, auth, public, shop

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(shop.router)
api_router.include_router(admin.router)
