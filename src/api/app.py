from fastapi import FastAPI

from src.api.routes import router


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
        router
    )

    return app


app = create_app()
