from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.auth import router as auth_router
from routes.observations import router as obs_router
from routes.goals import router as goals_router
from routes.dashboard import router as dashboard_router
from routes.reviews import router as reviews_router
from routes.messages import router as messages_router
from routes.pipeline import router as pipeline_router

app = FastAPI(
    title="EduTrack API",
    description="AI-Powered Teacher Performance Intelligence System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(obs_router)
app.include_router(goals_router)
app.include_router(dashboard_router)
app.include_router(reviews_router)
app.include_router(messages_router)
app.include_router(pipeline_router)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "EduTrack API",
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    return {"message": "EduTrack API is running"}