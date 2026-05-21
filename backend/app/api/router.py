"""Main API router aggregator."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.channels import router as channels_router
from app.api.posts import router as posts_router
from app.api.carousels import router as carousels_router
from app.api.images import router as images_router
from app.api.categories import router as categories_router
from app.api.users import router as users_router
from app.api.scrape import router as scrape_router
from app.api.elements import router as elements_router
from app.api.templates import router as templates_router
from app.api.settings import router as settings_router
from app.api.cta import router as cta_router
from app.api.fonts import router as fonts_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(channels_router)
api_router.include_router(posts_router)
api_router.include_router(carousels_router)
api_router.include_router(images_router)
api_router.include_router(categories_router)
api_router.include_router(users_router)
api_router.include_router(scrape_router)
api_router.include_router(elements_router)
api_router.include_router(templates_router)
api_router.include_router(settings_router)
api_router.include_router(cta_router)
api_router.include_router(fonts_router)
