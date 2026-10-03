import json
from datetime import datetime

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import db, Feedback, Message, Persona, Session, Skill, User
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
    age_group: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    relation: Optional[str] = None
    tone: Optional[str] = None
    humor: Optional[str] = None
    style: Optional[str] = None
    background: Optional[str] = None
    expertise: List[str] = []
    profile: Optional[dict] = None  # 详细资料，按 人员身份字段.md 分组（自由结构）
    soul: Optional[str] = None  # 上传的 .md 人物资料，赋予角色"灵魂"


class ExtractIn(BaseModel):
    content: str


@router.post("/personas/extract")
def extract_persona_profile(body: ExtractIn):
    """从文件文本抽取人物资料，回填到表单（只填拿得到字段，拿不到留空）。"""
    from .llm import ask_json

    text = (body.content or "").strip()
    if not text:
        raise HTTPException(400, "内容为空")
    if len(text) > 50000:
        raise HTTPException(400, "内容过长（>5 万字），请精简后再传")
    system = (
        "你是「人物资料抽取器」。用户在创建一个虚拟角色，给了一份关于这个人物的资料文件"
        "（可能是人物设定、书籍摘录、传记等）。你要从中抽取能直接填进角色表单的信息。\n"
        "规则：\n"
        "1. 只填资料里明确写到的，拿不准或没有的字段一律留 null，不要编造；\n"
        "2. text 类字段填简短内容（50 字内），expertise 最多 6 项；\n"
        "3. profile 按分组给出，分组名必须原样使用，只给有内容的组，组内只给有值的字段：\n"
        "   - 基础身份: 学历、工作年限、收入水平、城市地区\n"
        "   - 家庭背景: 婚姻状态、子女、父母、家庭关系、家庭压力、家教氛围\n"
        "   - 性格: 内外向、表达方式、思维、情绪、主动性、决策风格、敏感度\n"
        "   - 人品 / 价值观（各填 高 / 中 / 低）: 诚信、责任心、边界感、同理心、占有欲、公平感、面子观、忠诚度（各填 高/中/低）\n"
        "   - 知识 / 能力: 术语水平、生活经验、表达能力、学习意愿（各填 高/中/低）\n"
        "4. 返回 JSON 对象，字段：name、age（数字或 null）、gender、occupation、relation、"
        "tone、style、humor、background、expertise、profile。"
    )
    result = ask_json(system, [{"role": "user", "content": text}], temperature=0.2)
    # 收敛到表单能接受的形状（分组键与设置页保存的 profile 结构一致）
    prof_in = result.get("profile") or {}
    profile = {}
    for group, keys in {
        "基础身份": ["学历", "工作年限", "收入水平", "城市地区"],
        "家庭背景": ["婚姻状态", "子女", "父母", "家庭关系", "家庭压力", "家教氛围"],
        "性格": ["内外向", "表达方式", "思维", "情绪", "主动性", "决策风格", "敏感度"],
        "人品 / 价值观": ["诚信", "责任心", "边界感", "同理心", "占有欲", "公平感", "面子观", "忠诚度"],
        "知识 / 能力": ["术语水平", "生活经验", "表达能力", "学习意愿"],
    }.items():
        got = prof_in.get(group) or {}
        if not isinstance(got, dict):
            continue
        kept = {k: str(v) for k, v in got.items() if k in keys and v not in (None, "", "null", "未知")}
        if kept:
            profile[group] = kept
    exp = result.get("expertise") or []
    exp = [str(x) for x in exp if str(x).strip()][:6] if isinstance(exp, list) else []
    return {
        "name": result.get("name"),
        "age": str(result.get("age")) if result.get("age") is not None else None,
        "gender": result.get("gender"),
        "occupation": result.get("occupation"),
        "relation": result.get("relation"),
        "tone": result.get("tone"),
        "style": result.get("style"),
        "humor": result.get("humor"),
        "background": result.get("background"),
        "expertise": exp,
        "profile": profile or None,
    }


class SoulIn(BaseModel):
    content: str
    filename: Optional[str] = ""


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


class SessionSkillsIn(BaseModel):
    skill_ids: List[int] = []  # 空数组 = 恢复自动路由


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
                "soul": r.soul,
                "soul_chars": len(r.soul or ""),
                "materials_count": len(json.loads(r.materials_json) if r.materials_json else []),
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
            soul=body.soul,
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


@router.post("/personas/{pid}/soul")
def upload_soul(pid: int, body: SoulIn):
    """上传 .md 人物资料，赋予角色灵魂。"""
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        text = (body.content or "").strip()
        if not text:
            raise HTTPException(400, "文件内容为空")
        if len(text) > 20000:
            raise HTTPException(400, "内容过长（>2 万字），请精简后再传")
        p.soul = text
        s.commit()
        return {"id": pid, "soul_chars": len(text), "filename": body.filename}
    finally:
        s.close()


class MaterialIn(BaseModel):
    filename: str
    content: str


@router.get("/personas/{pid}/materials")
def list_materials(pid: int):
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        mats = json.loads(p.materials_json) if p.materials_json else []
        return [
            {"index": i, "filename": m.get("filename", ""), "chars": len(m.get("content", ""))}
            for i, m in enumerate(mats)
        ]
    finally:
        s.close()


@router.post("/personas/{pid}/materials")
def upload_material(pid: int, body: MaterialIn):
    """追加一份资料文件（txt/md/json/csv 原文）到角色。"""
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        text = (body.content or "").strip()
        if not text:
            raise HTTPException(400, "文件内容为空")
        if len(text) > 50000:
            raise HTTPException(400, "单个文件超过 5 万字，请精简后再传")
        mats = json.loads(p.materials_json) if p.materials_json else []
        mats.append(
            {
                "filename": body.filename or "资料",
                "content": text,
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        p.materials_json = json.dumps(mats, ensure_ascii=False)
        s.commit()
        return {"id": pid, "materials": len(mats), "filename": body.filename}
    finally:
        s.close()


@router.delete("/personas/{pid}/materials/{idx}")
def delete_material(pid: int, idx: int):
    s = db()
    try:
        p = s.get(Persona, pid)
        if p is None:
            raise HTTPException(404, "身份不存在")
        mats = json.loads(p.materials_json) if p.materials_json else []
        if idx < 0 or idx >= len(mats):
            raise HTTPException(404, "资料不存在")
        removed = mats.pop(idx)
        p.materials_json = json.dumps(mats, ensure_ascii=False)
        s.commit()
        return {"deleted": removed.get("filename"), "materials": len(mats)}
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
def list_sessions(page: int = 1, per_page: int = 10, status: Optional[str] = None):
    s = db()
    try:
        per_page = max(1, min(per_page, 100))
        page = max(1, page)
        q = s.query(Session)
        if status:
            q = q.filter(Session.status == status)
        total = q.count()
        rows = (
            q.order_by(Session.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "persona_id": r.persona_id,
                    "mode": r.mode,
                    "status": r.status,
                    "scene": r.scene,
                    "created_at": str(r.created_at),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    finally:
        s.close()


@router.get("/sessions/{sid}")
def get_session(sid: int):
    s = db()
    try:
        r = s.get(Session, sid)
        if r is None:
            raise HTTPException(404, "会话不存在")
        skill_ids = json.loads(r.skill_ids or "[]") or []
        msgs = s.query(Message).filter(Message.session_id == sid).order_by(Message.id).all()
        return {
            "id": r.id,
            "persona_id": r.persona_id,
            "mode": r.mode,
            "status": r.status,
            "skill_ids": skill_ids,
            "messages": [{"id": m.id, "role": m.role, "content": m.content} for m in msgs],
        }
    finally:
        s.close()


@router.delete("/sessions/{sid}")
def delete_session(sid: int):
    try:
        return service.delete_session(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sessions/{sid}/skills")
def set_session_skills(sid: int, body: SessionSkillsIn):
    s = db()
    try:
        sess = s.get(Session, sid)
        if sess is None:
            raise HTTPException(404, "会话不存在")
        valid_ids = [r.id for r in s.query(Skill).all()] if body.skill_ids else []
        unknown = [i for i in body.skill_ids if i not in valid_ids]
        if unknown:
            raise HTTPException(400, f"skill 不存在：{unknown}")
        sess.skill_ids = json.dumps([int(i) for i in body.skill_ids], ensure_ascii=False)
        s.commit()
        return {"skill_ids": [int(i) for i in body.skill_ids]}
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
