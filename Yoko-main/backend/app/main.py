import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.health import router as health_router

load_dotenv()

app = FastAPI(title="Yoko API", version="0.1.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
