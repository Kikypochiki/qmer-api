from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables. Prefer a project-root .env.local when available so
# FastAPI (running from the fastapi/ folder) can access the same credentials
# used by the Next.js app during local development.
root_env = Path(__file__).resolve().parents[1] / '.env.local'
if root_env.exists():
    load_dotenv(root_env)
else:
    load_dotenv()

from routes.predict import router as predict_router
from routes.push import router as push_router
from routes.trends import router as trends_router

app = FastAPI(title="QMeR+ Backend Service", version="1.0.0")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("VALIDATION ERROR:", exc.errors())
    print("BODY:", exc.body)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict_router, prefix="/api")
app.include_router(push_router, prefix="/api")
app.include_router(trends_router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "QMeR+ AI (Gemini)", "version": "1.0.0"}
