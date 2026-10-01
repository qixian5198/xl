import json
import time
from typing import List

from openai import OpenAI

from .config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.NVIDIA_API_BASE_URL,
            api_key=settings.NVIDIA_API_KEY,
            timeout=settings.LLM_TIMEOUT,
        )
    return _client


def reset_client():
    global _client
    _client = None


def list_models() -> List[str]:
    """从 NIM 拉可用模型列表（走当前 key），失败抛 LLMError。"""
    try:
        resp = get_client().models.list()
        return [m.id for m in resp.data]
    except Exception as e:
        raise LLMError(f"拉取模型列表失败: {e}")


def ask(system: str, messages: List[dict], temperature: float = 0.7, max_tokens: int = 600) -> str:
    """统一 LLM 入口，返回模型原始文本。失败抛 LLMError。"""
    last_err = None
    for attempt in range(settings.LLM_RETRIES + 1):
        try:
            resp = get_client().chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            msg = str(e)
            # NIM worker 限流（503）：退避等待，越往后等越久
            backoff = 8 * (attempt + 1) if ("503" in msg or "529" in msg) else 2
            time.sleep(backoff)
    raise LLMError(f"LLM 调用失败（已重试 {settings.LLM_RETRIES} 次）: {last_err}")


def ask_json(system: str, messages: List[dict], temperature: float = 0.7) -> dict:
    """要求模型返回单个 JSON 对象，解析失败重试一次。"""
    from .prompts import JSON_FORMAT_RULE

    sys_with_json = system + "\n\n" + JSON_FORMAT_RULE
    raw = ask(sys_with_json, messages, temperature=temperature)
    try:
        return parse_json(raw)
    except ValueError:
        retry_msgs = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "上面的输出不是合法 JSON，请只重新输出一个合法 JSON 对象，不要解释。"},
        ]
        raw2 = ask(sys_with_json, retry_msgs, temperature=0.3)
        return parse_json(raw2)


def parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("LLM 输出中未找到 JSON")
    depth = 0
    for i, ch in enumerate(text[start:]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : start + i + 1]
                return json.loads(candidate)
    raise ValueError("JSON 解析失败: " + raw[:200])


class LLMError(Exception):
    pass
