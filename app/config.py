import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    NVIDIA_API_BASE_URL = os.getenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_RETRIES = int(os.getenv("LLM_RETRIES", "1"))
    FEEDBACK_EVERY_N = int(os.getenv("FEEDBACK_EVERY_N", "1"))
    COACH_EVERY_N = int(os.getenv("COACH_EVERY_N", "5"))
    DB_PATH = os.getenv("DB_PATH", "xl.db")


settings = Settings()


def get_config_public() -> dict:
    key = settings.NVIDIA_API_KEY
    return {
        "base_url": settings.NVIDIA_API_BASE_URL,
        "key_masked": (key[:8] + "…" + key[-4:]) if len(key) > 12 else ("（未配置）" if not key else "****"),
        "model": settings.NVIDIA_MODEL,
        "timeout": settings.LLM_TIMEOUT,
        "retries": settings.LLM_RETRIES,
        "feedback_every_n": settings.FEEDBACK_EVERY_N,
    }


def update_config(base_url: str, api_key: str, model: str,
                  timeout: int, retries: int, feedback_every_n: int) -> dict:
    settings.NVIDIA_API_BASE_URL = base_url
    settings.NVIDIA_MODEL = model
    settings.LLM_TIMEOUT = timeout
    settings.LLM_RETRIES = retries
    settings.FEEDBACK_EVERY_N = feedback_every_n
    if api_key:  # 留空 = 保持当前 key
        settings.NVIDIA_API_KEY = api_key
    _persist_env()
    import app.llm
    app.llm.reset_client()
    return get_config_public()


def _persist_env():
    """把当前运行时配置写回 .env，重启后不丢。"""
    import pathlib

    p = pathlib.Path(".env")
    vals = {
        "NVIDIA_API_BASE_URL": settings.NVIDIA_API_BASE_URL,
        "NVIDIA_API_KEY": settings.NVIDIA_API_KEY,
        "NVIDIA_MODEL": settings.NVIDIA_MODEL,
        "LLM_TIMEOUT": str(settings.LLM_TIMEOUT),
        "LLM_RETRIES": str(settings.LLM_RETRIES),
        "FEEDBACK_EVERY_N": str(settings.FEEDBACK_EVERY_N),
    }
    kept = []
    if p.exists():
        for ln in p.read_text().splitlines():
            key = ln.split("=", 1)[0].strip()
            if key not in vals and ln.strip() and not ln.startswith("#"):
                kept.append(ln.rstrip())
    lines = [f"{k}={v}" for k, v in vals.items()] + kept
    p.write_text("\n".join(lines) + "\n")
