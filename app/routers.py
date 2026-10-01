import json

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import db, Feedback, Message, Persona, Session, User
from . import service
from .config import get_config_public, update_config, settings as app_settings
from .llm import LLMError, list_models, reset_client

router = APIRouter(prefix="/api")


class ConfigIn(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = None
    retries: Optional[int] = None
    feedback_every_n: Optional[int] = None


@router.get("/config")
def get_config():
    return get_config_public()


@router.post("/config")
def set_config(body: ConfigIn):
    reset_client()
    try:
        return update_config(
            base_url=body.base_url or app_settings.NVIDIA_API_BASE_URL,
            api_key=body.api_key or "",
            model=body.model or app_settings.NVIDIA_MODEL,
            timeout=body.timeout or app_settings.LLM_TIMEOUT,
            retries=body.retries if body.retries is not None else app_settings.LLM_RETRIES,
            feedback_every_n=body.feedback_every_n if body.feedback_every_n is not None else app_settings.FEEDBACK_EVERY_N,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/models")
def get_models():
    try:
        return {"models": list_models()}
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/config/test")
def test_config():
    """用当前配置发一条最小 LLM 请求，验证 key 和模型可用。"""
    from .llm import ask

    try:
        result = ask("你只输出一个 JSON 对象：{\"ok\": true}。",
                     [{"role": "user", "content": "ping"}], temperature=0.1)
        return {"ok": True, "raw": result[:200]}
    except LLMError as e:
        raise HTTPException(502, str(e))


class PersonaIn(BaseModel):
    name: str
    age_group: str
    gender: str
    occupation: str
    relation: str
    tone: str
    humor: Optional[str] = None
    style: Optional[str] = None  # 沟通风格
    background: str
    expertise: List[str] = []
    profile: Optional[dict] = None  # 详细资料，按 人员身份字段.md 分组（自由结构）


class UserIn(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    work_context: Optional[str] = None
    emotional_context: Optional[str] = None
    life_context: Optional[str] = None


class SessionIn(BaseModel):
    persona_id: int
    mode: str  # mood / personality / chat / soul
    user_id: Optional[int] = None
    scene: Optional[str] = None  # 本次对话场景，如「朋友介绍来问睡眠问题」


class MessageIn(BaseModel):
    content: str


class GuessIn(BaseModel):
    state_id: int
    guess: dict


@router.get("/personas")
def list_personas():
    s = db()
    try:
        rows = s.query(Persona).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "age_group": r.age_group,
                "gender": r.gender,
                "occupation": r.occupation,
                "relation": r.relation,
                "tone": r.tone,
                "humor": r.humor,
                "style": r.style,
                "background": r.background,
                "expertise": r.expertise_list(),
                "profile": json.loads(r.profile_json) if r.profile_json else None,
            }
            for r in rows
        ]
    finally:
        s.close()


@router.post("/personas")
def create_persona(body: PersonaIn):
    s = db()
    try:
        p = Persona(
            name=body.name,
            age_group=body.age_group,
            gender=body.gender,
            occupation=body.occupation,
            relation=body.relation,
            tone=body.tone,
            humor=body.humor,
            style=body.style,
            background=body.background,
            expertise=json.dumps(body.expertise, ensure_ascii=False),
            profile_json=json.dumps(body.profile, ensure_ascii=False, indent=2) if body.profile else None,
        )
        s.add(p)
        s.commit()
        s.refresh(p)
        return {"id": p.id, "name": p.name}
    finally:
        s.close()


@router.put("/personas/{pid}")
def update_persona(pid: int, body: PersonaIn):
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        for field in ("name", "age_group", "gender", "occupation", "relation", "tone", "humor", "style", "background"):
            setattr(p, field, getattr(body, field))
        p.expertise = json.dumps(body.expertise, ensure_ascii=False)
        p.profile_json = json.dumps(body.profile, ensure_ascii=False, indent=2) if body.profile else None
        s.commit()
        return {"id": p.id, "name": p.name}
    finally:
        s.close()


@router.delete("/personas/{pid}")
def delete_persona(pid: int):
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        s.delete(p)
        s.commit()
        return {"deleted": pid}
    finally:
        s.close()


@router.get("/users")
def list_users():
    s = db()
    try:
        rows = s.query(User).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "timezone": r.timezone,
                "work_context": r.work_context,
                "emotional_context": r.emotional_context,
                "life_context": r.life_context,
            }
            for r in rows
        ]
    finally:
        s.close()


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn):
    s = db()
    try:
        u = s.get(User, uid)
        if u is None:
            raise HTTPException(404, "用户不存在")
        for field in ("name", "timezone", "work_context", "emotional_context", "life_context"):
            val = getattr(body, field)
            if val is not None:
                setattr(u, field, val)
        s.commit()
        return {"id": u.id, "name": u.name}
    finally:
        s.close()


@router.get("/users/{uid}/memories")
def list_user_memories(uid: int):
    from .database import UserMemory
    s = db()
    try:
        rows = s.query(UserMemory).filter(UserMemory.user_id == uid).order_by(UserMemory.id.desc()).limit(50).all()
        return [{"id": r.id, "fact": r.fact, "source_session": r.source_session, "created_at": str(r.created_at)} for r in rows]
    finally:
        s.close()


class SkillIn(BaseModel):
    name: str
    source: Optional[str] = None
    triggers: List[str] = []
    do: str
    dont: Optional[str] = None


@router.get("/skills")
def list_skills():
    from .database import Skill as SkillModel
    s = db()
    try:
        rows = s.query(SkillModel).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "source": r.source,
                "triggers": json.loads(r.triggers or "[]"),
                "do": r.do,
                "dont": r.dont,
            }
            for r in rows
        ]
    finally:
        s.close()


@router.post("/skills")
def create_skill(body: SkillIn):
    from .database import Skill as SkillModel
    s = db()
    try:
        sk = SkillModel(
            name=body.name,
            source=body.source,
            triggers=json.dumps(body.triggers, ensure_ascii=False),
            do=body.do,
            dont=body.dont,
        )
        s.add(sk)
        s.commit()
        s.refresh(sk)
        return {"id": sk.id, "name": sk.name}
    finally:
        s.close()


@router.delete("/skills/{skid}")
def delete_skill(skid: int):
    from .database import Skill as SkillModel
    s = db()
    try:
        sk = s.get(SkillModel, skid)
        if sk is None:
            raise HTTPException(404, "skill 不存在")
        s.delete(sk)
        s.commit()
        return {"deleted": skid}
    finally:
        s.close()


@router.post("/sessions")
def create_session(body: SessionIn):
    try:
        return service.create_session(body.user_id, body.persona_id, body.mode, scene=body.scene)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sessions")
def list_sessions():
    s = db()
    try:
        rows = s.query(Session).order_by(Session.id.desc()).limit(100).all()
        return [
            {
                "id": r.id,
                "persona_id": r.persona_id,
                "mode": r.mode,
                "status": r.status,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    finally:
        s.close()


@router.get("/sessions/{sid}")
def get_session(sid: int):
    s = db()
    try:
        r = s.get(Session, sid)
        if r is None:
            raise HTTPException(404, "会话不存在")
        msgs = s.query(Message).filter(Message.session_id == sid).order_by(Message.id).all()
        return {
            "id": r.id,
            "persona_id": r.persona_id,
            "mode": r.mode,
            "status": r.status,
            "messages": [{"id": m.id, "role": m.role, "content": m.content} for m in msgs],
        }
    finally:
        s.close()


@router.post("/sessions/{sid}/messages")
def post_message(sid: int, body: MessageIn):
    try:
        return service.send_message(sid, body.content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/sessions/{sid}/guess")
def post_guess(sid: int, body: GuessIn):
    try:
        return service.submit_guess(sid, body.state_id, body.guess)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/sessions/{sid}/soul-question")
def post_soul_question(sid: int):
    try:
        return service.ask_soul_question(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/sessions/{sid}/nudge")
def post_nudge(sid: int):
    try:
        return service.nudge(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.post("/sessions/{sid}/coach")
def post_coach(sid: int):
    try:
        return service.coach_pause(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.get("/scenarios/random")
def random_scenario():
    try:
        return service.random_scene()
    except LLMError as e:
        raise HTTPException(502, str(e))


@router.get("/sessions/{sid}/feedback")
def get_feedback(sid: int):
    s = db()
    try:
        rows = s.query(Feedback).filter(Feedback.session_id == sid).order_by(Feedback.id).all()
        return [
            {
                "message_id": r.message_id,
                "total": r.total,
                "empathy": r.empathy,
                "clarity": r.clarity,
                "timing": r.timing,
                "respect": r.respect,
                "boundary": r.boundary,
                "comment": r.comment,
            }
            for r in rows
        ]
    finally:
        s.close()


@router.post("/sessions/{sid}/end")
def post_end_session(sid: int):
    try:
        return service.end_session(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sessions/{sid}/summary")
def post_summary(sid: int):
    try:
        return service.get_summary(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))
