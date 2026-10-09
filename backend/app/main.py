import logging

from backend.app.api.v1.endpoints import campaigns, dashboard, prospects, workflows
from backend.app.config import settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Agentic sales intelligence: research, qualify, critique, and route opportunities for human approval.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": settings.PROJECT_NAME,
        "api": settings.API_V1_STR,
        "health": "/health",
        "docs": "/docs",
    }


app.include_router(campaigns.router, prefix=f"{settings.API_V1_STR}/campaigns", tags=["campaigns"])
app.include_router(prospects.router, prefix=f"{settings.API_V1_STR}/prospects", tags=["prospects"])
app.include_router(
    workflows.router, prefix=f"{settings.API_V1_STR}/workflow-runs", tags=["workflows"]
)
app.include_router(dashboard.router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["dashboard"])
