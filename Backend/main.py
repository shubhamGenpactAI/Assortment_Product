"""
main.py — FastAPI entry point
Run from the backend/ directory:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers.forecast      import router as forecast_router
from .routers.general       import router as general_router
from .routers.new_sku       import router as new_sku_router
from .routers.decision_hub  import router as decision_hub_router
from .routers.agents        import router as agents_router

app = FastAPI(
    title="Category Growth API",
    description="Serves all dashboard data for the Category Growth app.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(forecast_router,      prefix="/api/forecast",      tags=["Forecast"])
app.include_router(general_router,       prefix="/api",               tags=["General"])
app.include_router(new_sku_router,       prefix="/api/new-sku",       tags=["New SKU Intelligence"])
app.include_router(decision_hub_router,  prefix="/api/decision-hub",  tags=["Decision Hub"])
app.include_router(agents_router,        prefix="/api/agents",         tags=["Agents"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI Backend!"}
