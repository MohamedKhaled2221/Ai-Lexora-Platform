from fastapi import FastAPI

from src.api.ai_routes import (
    router as ai_router,
)
from src.api.routes import (
    router as system_router,
)


def create_app() -> FastAPI:
    """
    Create and configure the AI-Lexora FastAPI application.
    """

    app = FastAPI(
        title="AI-Lexora API",
        version="0.1.0",
        description=(
            "Local multilingual legal "
            "intelligence API"
        ),
    )
    app.include_router(
        system_router
    )
    
    app.include_router(
        ai_router
    )

    

    return app


app = create_app()
