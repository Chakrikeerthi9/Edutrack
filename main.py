from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.auth import router as auth_router

app = FastAPI(
    title="EduTrack API",
    description="AI-Powered Teacher Performance Intelligence System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

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