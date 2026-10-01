import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import router as api_router
from .llm import LLMError

init_db()

app = FastAPI(title="情商口才训练工具", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.exception_handler(LLMError)
async def llm_error_handler(request, exc: LLMError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
