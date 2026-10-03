import json
import re
from typing import Optional

from sqlalchemy import desc

from .config import settings
from .database import (
    db,
    CoachComment,
    Feedback,
    Guess,
    HiddenState,
    Message,
    Persona,
    PersonaMemory,
    Session,
    Skill,
    User,
    UserMemory,
)
from .llm import LLMError, ask_json
from . import prompts


def normalize_state(hs: dict) -> dict:
    """把模型自由输出的状态值归一到合法枚举，避免判断比对永远对不上。

    模型偶尔把 hidden_state 输出成 list（如 [["emotion","平静"],...]）
    或单个字符串，这里先统一转成 dict，转不了就用默认值兜底。
    """
    emotions = ["开心", "烦躁", "焦虑", "失望", "生气", "平静"]
    distances = ["疏远", "正常", "亲近"]

    # 先把输入归一成 dict
    if isinstance(hs, list):
        hs = {
            k: v
            for k, v in hs
            if isinstance(k, str) and isinstance(v, (str, int, float))
        } if all(isinstance(x, (list, tuple)) and len(x) == 2 for x in hs) else {}
    elif not isinstance(hs, dict):
        hs = {}
    hs = {k: v for k, v in hs.items() if v is not None}
    hs.update({k: v for k, v in prompts.DEFAULT_STATE.items() if k not in hs})
    hs = {k: str(v) for k, v in hs.items()}

    def lv(v, default="中"):
        if not v:
            return default
        s = str(v).strip()
        for x in ("高", "中", "低"):
            if x in s:
                return x
        try:
            n = float(s)
        except ValueError:
            return default
        return "低" if n < 4 else ("中" if n <= 7 else "高")

    out = dict(hs)
    e = str(out.get("emotion") or "平静").strip()
    out["emotion"] = next((x for x in emotions if x in e), "平静")
    out["patience"] = lv(out.get("patience"))
    out["affection"] = lv(out.get("affection"))
    d = str(out.get("distance") or "正常").strip()
    out["distance"] = next((x for x in distances if x in d), "正常")
    return out


def _get_user(user_id: Optional[int] = None) -> User:
    s = db()
    try:
        u = s.get(User, user_id) if user_id else s.query(User).first()
        if u is None:
            u = User(name="我")
            s.add(u)
            s.commit()
            s.refresh(u)
        return u
    finally:
        s.close()


def _latest_state(session_id: int) -> dict:
    s = db()
    try:
        row = s.query(HiddenState).filter(HiddenState.session_id == session_id).order_by(desc(HiddenState.id)).first()
        if row:
            state = {
                "emotion": row.emotion,
                "patience": row.patience,
                "affection": row.affection,
                "distance": row.distance,
                "reasoning": row.reasoning,
            }
            if row.personality:
                state["personality"] = row.personality
            return state
        return dict(prompts.DEFAULT_STATE)
    finally:
        s.close()


def _history_msgs(session_id: int, limit: int = 20):
    s = db()
    try:
        rows = (
            s.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.id)
            .all()
        )
        rows = rows[-limit:]
        return [{"role": r.role, "content": r.content} for r in rows]
    finally:
        s.close()


def _recent_facts(user_id: int, limit: int = 8) -> str:
    s = db()
    try:
        rows = (
            s.query(UserMemory)
            .filter(UserMemory.user_id == user_id)
            .order_by(desc(UserMemory.id))
            .limit(limit)
            .all()
        )
        return "\n".join(f"- {r.fact}" for r in rows)
    finally:
        s.close()


def _persona_facts(persona_id: int, limit: int = 8) -> str:
    """这个角色记忆里"我"（用户）的事，只属于该角色，别的角色不知道。"""
    s = db()
    try:
        rows = (
            s.query(PersonaMemory)
            .filter(PersonaMemory.persona_id == persona_id)
            .order_by(desc(PersonaMemory.id))
            .limit(limit)
            .all()
        )
        return "\n".join(f"- {r.fact}" for r in rows)
    finally:
        s.close()


def _skills_by_ids(ids: list) -> list:
    s = db()
    try:
        rows = s.query(Skill).filter(Skill.id.in_(ids)).all()
        out = [
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
        # 保持用户选择顺序
        order = {i: n for n, i in enumerate(ids)}
        out.sort(key=lambda x: order.get(x["id"], 999))
        return out
    finally:
        s.close()


def _skills_for_session(session_id: int, scene: Optional[str], limit: int = 2) -> list:
    """手动指定优先：session.skill_ids 非空就用选中的卡片；否则按场景自动路由。"""
    s = db()
    try:
        sess = s.get(Session, session_id)
        manual = json.loads(sess.skill_ids or "[]") if sess else []
        if isinstance(manual, list) and manual:
            return _skills_by_ids([int(i) for i in manual])
        return _route_skills(session_id, scene, limit)
    finally:
        s.close()


def _route_skills(session_id: int, scene: Optional[str], limit: int = 2) -> list:
    """按当前场景 + 最近暴露的弱点，路由到最相关的 skill 卡（最多 limit 张）。"""
    s = db()
    try:
        rows = s.query(Skill).all()
        if not rows:
            return []
        fb_comments = " ".join(
            f.comment or ""
            for f in s.query(Feedback)
            .filter(Feedback.session_id == session_id)
            .order_by(desc(Feedback.id))
            .limit(6)
            .all()
        )
        text = f"{scene or ''} {fb_comments}"
        scored = []
        for r in rows:
            trigs = json.loads(r.triggers or "[]")
            if not isinstance(trigs, list):
                trigs = [str(trigs)]
            score = sum(1 for t in trigs if t and t in text)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": r.id,
                "name": r.name,
                "source": r.source,
                "triggers": json.loads(r.triggers or "[]"),
                "do": r.do,
                "dont": r.dont,
            }
            for _, r in scored[:limit]
        ]
    finally:
        s.close()


def _all_skills() -> list:
    s = db()
    try:
        rows = s.query(Skill).all()
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


def _coach_skill_block(skills: list) -> str:
    if not skills:
        return ""
    lines = [
        "可参考的沟通技术卡（指出问题时优先关联到对应技术，注明技术名和来源书名）："
    ]
    for sk in skills:
        lines.append(
            f"- {sk['name']}（来源：{sk.get('source') or '未知'}）："
            f"该 {sk.get('do') or ''}；避免 {sk.get('dont') or '生硬回应'}"
        )
    return "\n".join(lines)


def create_session(user_id: Optional[int], persona_id: int, mode: str,
                  scene: Optional[str] = None) -> dict:
    s = db()
    try:
        p = s.get(Persona, persona_id)
        if p is None:
            raise ValueError("身份不存在")
        active = (
            s.query(Session)
            .filter(Session.persona_id == persona_id, Session.status == "active")
            .first()
        )
        if active:
            raise ValueError(
                f"{p.name} 已有一个进行中的会话（#{active.id}），请先结束它，再开新的"
            )
        user = _get_user(user_id)
        sess = Session(user_id=user.id, persona_id=persona_id, mode=mode,
                       scene=scene or None,
                       initial_state_json=json.dumps(prompts.DEFAULT_STATE, ensure_ascii=False))
        s.add(sess)
        s.commit()
        s.refresh(sess)
        return {"id": sess.id, "mode": mode, "persona_id": persona_id,
                "scene": sess.scene, "status": "active", "skill_ids": []}
    finally:
        s.close()


def send_message(session_id: int, content: str) -> dict:
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        if sess.status != "active":
            raise ValueError("会话已结束")
        p = s.get(Persona, sess.persona_id)
        user = s.get(User, sess.user_id)

        user_msg = Message(session_id=session_id, role="user", content=content)
        s.add(user_msg)
        s.commit()
        s.refresh(user_msg)

        # 判断这轮是否该给反馈：chat/soul 每轮都评；mood/personality 每 N 轮评一次
        turn = s.query(Message).filter(
            Message.session_id == session_id,
            Message.role == "user",
            Message.id <= user_msg.id,
        ).count()
        give_feedback = sess.mode in ("chat", "soul") or (turn % max(settings.FEEDBACK_EVERY_N, 1) == 0)

        facts_text = _recent_facts(user.id) if user else ""
        skills = _skills_for_session(session_id, sess.scene)
        sys_prompt = prompts.main_system(
            p, user, sess.mode, _latest_state(session_id),
            scene=sess.scene,
            memory_facts=facts_text or None,
            persona_memory=_persona_facts(p.id),
            skills=skills,
        )
        prompt_extra = "" if give_feedback else "\n\n本轮 feedback 字段输出 null（未到评分轮次）。"
        try:
            result = ask_json(
                sys_prompt + prompt_extra,
                _history_msgs(session_id),
                temperature=0.7,
            )
        except LLMError:
            raise  # 路由层转 502

        reply = str(result.get("assistant_reply", "")).strip()
        assistant_msg = Message(session_id=session_id, role="assistant", content=reply)
        s.add(assistant_msg)
        s.commit()
        s.refresh(assistant_msg)

        # 写隐藏状态（先归一化，模型偶尔会输出数字或自由文本）
        hs = normalize_state(result.get("hidden_state") or {})
        state = HiddenState(
            session_id=session_id,
            message_id=assistant_msg.id,
            emotion=hs["emotion"],
            patience=hs["patience"],
            affection=hs["affection"],
            distance=hs["distance"],
            personality=hs.get("personality"),
            reasoning=hs.get("reasoning"),
        )
        s.add(state)

        # 记忆：用户共享记忆 + 本角色专属记忆，分开入库
        raw_user = result.get("user_facts") or result.get("memory_facts") or []
        if isinstance(raw_user, str):
            raw_user = [x.strip() for x in re.split(r"[;；、,，]", raw_user) if x.strip()]
        if isinstance(raw_user, list):
            existing = {
                r.fact.strip() for r in s.query(UserMemory).filter(UserMemory.user_id == user.id).all()
            }
            for fact in raw_user:
                fact = str(fact).strip()
                if fact and fact not in existing and 2 < len(fact) <= 80:
                    s.add(UserMemory(user_id=user.id, fact=fact, source_session=session_id))

        raw_persona = result.get("persona_facts") or []
        if isinstance(raw_persona, str):
            raw_persona = [x.strip() for x in re.split(r"[;；、,，]", raw_persona) if x.strip()]
        if isinstance(raw_persona, list):
            p_existing = {
                r.fact.strip() for r in s.query(PersonaMemory).filter(PersonaMemory.persona_id == p.id).all()
            }
            for fact in raw_persona:
                fact = str(fact).strip()
                if fact and fact not in p_existing and 2 < len(fact) <= 80:
                    s.add(PersonaMemory(persona_id=p.id, fact=fact, source_session=session_id))

        # 写反馈（模型偶尔把 feedback 输出成字符串，跳过）
        fb = result.get("feedback")
        feedback_row = None
        if isinstance(fb, dict):
            feedback_row = Feedback(
                session_id=session_id,
                message_id=user_msg.id,
                total=int(fb.get("total", 0)),
                empathy=int(fb.get("empathy", 0)),
                clarity=int(fb.get("clarity", 0)),
                timing=int(fb.get("timing", 0)),
                respect=int(fb.get("respect", 0)),
                boundary=int(fb.get("boundary", 0)),
                comment=fb.get("comment", ""),
            )
            s.add(feedback_row)

        s.commit()

        resp = {
            "message_id": assistant_msg.id,
            "state_id": state.id,
            "assistant_message": reply,
            "ask_user_to_guess": sess.mode in ("mood", "personality"),
            "feedback": None,
        }
        if feedback_row:
            resp["feedback"] = {
                "total": feedback_row.total,
                "empathy": feedback_row.empathy,
                "clarity": feedback_row.clarity,
                "timing": feedback_row.timing,
                "respect": feedback_row.respect,
                "boundary": feedback_row.boundary,
                "comment": feedback_row.comment,
            }
        return resp
    finally:
        s.close()


def submit_guess(session_id: int, state_id: int, guess: dict) -> dict:
    s = db()
    try:
        sess = s.get(Session, session_id)
        state = s.get(HiddenState, state_id)
        if sess is None or state is None or state.session_id != session_id:
            raise ValueError("会话或状态不存在")

        dimensions = ["emotion", "patience", "affection", "distance"]
        if sess.mode == "personality" and state.personality:
            dimensions.append("personality")

        actual = {d: getattr(state, d) for d in dimensions}
        correct = sum(1 for d in dimensions if str(guess.get(d, "")).strip() == str(actual[d] or "").strip())

        p = s.get(Persona, sess.persona_id)
        user = s.get(User, sess.user_id)
        ctx = _history_msgs(session_id, limit=12)
        last_user = ctx[-1]["content"] if ctx else ""
        reasoning = state.reasoning or "无明显变化。"

        sys_prompt = prompts.GUESS_SYSTEM + (
            f"\n\n实际状态：{json.dumps(actual, ensure_ascii=False)}\n"
            f"用户当时的最后一句话：{last_user}\n"
            f"当时状态变化原因：{reasoning}"
        )
        result = ask_json(sys_prompt, ctx, temperature=0.3)

        g = Guess(
            session_id=session_id,
            state_id=state_id,
            guess_json=json.dumps(guess, ensure_ascii=False),
            correct=int(result.get("correct", correct)),
            total=len(dimensions),
            analysis=result.get("analysis", ""),
        )
        s.add(g)
        state.revealed = 1
        s.commit()

        return {
            "actual": actual,
            "correct": g.correct,
            "total": g.total,
            "analysis": g.analysis,
        }
    finally:
        s.close()


def ask_soul_question(session_id: int) -> dict:
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        p = s.get(Persona, sess.persona_id)
        user = s.get(User, sess.user_id)
        ctx = _history_msgs(session_id, limit=20)

        from .database import KnowledgeItem
        k_rows = s.query(KnowledgeItem).limit(10).all()
        if k_rows:
            items = "\n".join(
                f"- {k.title}（{k.source}）：示范 {k.examples}；避免 {k.anti_patterns}"
                for k in k_rows
            )
            extra = prompts.KNOWLEDGE_HINT.format(items=items)
        else:
            extra = ""

        skills = _all_skills()[:6]
        skill_extra = _coach_skill_block(skills)

        parts = [
            "以下是用户资料（可引用）：",
            json.dumps(
                {
                    "称呼": user.name,
                    "工作": user.work_context,
                    "情感": user.emotional_context,
                    "生活": user.life_context,
                },
                ensure_ascii=False,
            ),
            f"当前扮演角色：{p.name}（{p.occupation}/{p.relation}）。",
        ]
        sys_prompt = prompts.SOUL_QUESTION_SYSTEM + "\n\n" + "\n".join(parts) + extra + skill_extra

        result = ask_json(sys_prompt, ctx, temperature=0.8)
        questions = result.get("questions", [])
        sources = result.get("sources", [])
        while len(sources) < len(questions):
            sources.append("综合")
        return {"questions": list(zip(questions, sources[: len(questions)]))}
    finally:
        s.close()


def coach_pause(session_id: int) -> dict:
    """暂停点评：跳出角色，以教练口吻点评用户刚才的表现，可引用 skill。"""
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        if sess.status != "active":
            raise ValueError("会话已结束")
        p = s.get(Persona, sess.persona_id)

        turn = s.query(Message).filter(
            Message.session_id == session_id,
            Message.role == "user",
        ).count()

        recent = _history_msgs(session_id, limit=10)
        recent_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
        fbs = (
            s.query(Feedback)
            .filter(Feedback.session_id == session_id)
            .order_by(desc(Feedback.id))
            .limit(3)
            .all()
        )
        fb_digest = "\n".join(f"- {f.comment}（total {f.total}）" for f in fbs if f.comment) or "（无逐轮反馈）"
        skills = _skills_for_session(session_id, sess.scene, limit=3)
        skill_block = _coach_skill_block(skills)

        sys_prompt = (
            prompts.COACH_SYSTEM
            + f"\n\n当前角色：{p.name}；场景：{sess.scene or '未指定'}。\n"
            + f"最近对话（第 {turn} 轮用户发言）：\n" + recent_text + "\n\n"
            + f"最近点评：{fb_digest}\n\n"
            + skill_block
        )
        result = ask_json(sys_prompt, [], temperature=0.4)
        comment = str(result.get("comment") or "").strip()
        if not comment:
            raise ValueError("模型没有生成点评")
        sk_name = str(result.get("skill") or "").strip()
        c = CoachComment(
            session_id=session_id,
            turn=turn,
            comment=comment,
            skill_name=sk_name or None,
        )
        s.add(c)
        s.commit()
        return {
            "turn": turn,
            "comment": comment,
            "skill": sk_name,
            "coach_every_n": settings.COACH_EVERY_N,
        }
    finally:
        s.close()


def random_scene() -> dict:
    """随机生成一个社交场景，用于开会话前选题。"""
    skills = _all_skills()
    skill_hint = (
        "\n参考技术方向（场景要能练到其中一两个）："
        + "；".join(f"{sk['name']}（{ '、'.join((sk.get('triggers') or [])[:3]) }）" for sk in skills[:6])
        if skills
        else ""
    )
    result = ask_json(prompts.SCENE_SYSTEM + skill_hint, [], temperature=0.9)
    return {
        "scene": str(result.get("scene") or "").strip(),
        "persona_hint": str(result.get("persona_hint") or "").strip(),
        "purpose": str(result.get("purpose") or "").strip(),
    }


def end_session(session_id: int) -> dict:
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        sess.status = "ended"
        s.commit()
        return {"id": session_id, "status": "ended"}
    finally:
        s.close()


def delete_session(session_id: int) -> dict:
    """逐条删除一个历史会话及其全部关联数据（消息/状态/判断/反馈/点评）。

    不动 user_memories / persona_memories / skills —— 那些是跨会话的角色与用户记忆。
    """
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        if sess.status == "active":
            raise ValueError("会话还在进行中，请先结束再删除")
        s.query(CoachComment).filter(CoachComment.session_id == session_id).delete()
        s.query(Feedback).filter(Feedback.session_id == session_id).delete()
        s.query(Guess).filter(Guess.session_id == session_id).delete()
        s.query(HiddenState).filter(HiddenState.session_id == session_id).delete()
        s.query(Message).filter(Message.session_id == session_id).delete()
        s.delete(sess)
        s.commit()
        return {"deleted": session_id}
    finally:
        s.close()


def get_summary(session_id: int) -> dict:
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        p = s.get(Persona, sess.persona_id)
        user = s.get(User, sess.user_id)

        msgs = _history_msgs(session_id, limit=100)
        fbs = (
            s.query(Feedback).filter(Feedback.session_id == session_id).order_by(Feedback.id).all()
        )
        gs = s.query(Guess).filter(Guess.session_id == session_id).order_by(Guess.id).all()

        fb_digest = [
            f"第 {f.id} 轮：total={f.total}，comment={f.comment}" for f in fbs
        ]
        guess_digest = [
            f"判断正确率 {g.correct}/{g.total}：{g.analysis}" for g in gs
        ]

        sys_prompt = (
            prompts.SUMMARY_SYSTEM
            + f"\n\n各轮反馈：\n" + ("\n".join(fb_digest) if fb_digest else "（无逐轮反馈）")
            + "\n\n判断结果：\n"
            + ("\n".join(guess_digest) if guess_digest else "（本会话无判断）")
            + "\n\n" + _coach_skill_block(_all_skills()[:6])
        )
        result = ask_json(sys_prompt, msgs, temperature=0.4)

        return {
            "session_id": session_id,
            "total": result.get("total"),
            "stars": result.get("stars"),
            "dims": result.get("dims", {}),
            "framework": result.get("framework", ""),
            "techniques": result.get("techniques", []),
            "highlights": result.get("highlights", []),
            "problems": result.get("problems", []),
            "suggestions": result.get("suggestions", []),
            "next_scenario": result.get("next_scenario", ""),
        }
    finally:
        s.close()


def nudge(session_id: int) -> dict:
    """用户沉默数分钟后，机器人主动搭话。"""
    s = db()
    try:
        sess = s.get(Session, session_id)
        if sess is None:
            raise ValueError("会话不存在")
        if sess.status != "active":
            raise ValueError("会话已结束")
        p = s.get(Persona, sess.persona_id)
        state = _latest_state(session_id)
        ctx = _history_msgs(session_id, limit=10)
        pmem = _persona_facts(p.id)
        extra = ""
        if pmem:
            extra = "\n\n你记得（只有你知道的、之前和用户聊过的）：\n" + pmem

        sys_prompt = (
            prompts.persona_block(p)
            + "\n\n"
            + prompts.state_block(state)
            + "\n\n"
            + prompts.NUDGE_SYSTEM
            + extra
        )
        result = ask_json(sys_prompt, ctx, temperature=0.8)
        text = str(result.get("nudge") or result.get("assistant_reply") or "").strip()
        hint = str(result.get("hint") or "").strip()
        if not text:
            raise ValueError("模型没有生成搭话内容，请稍后再试")

        msg = Message(session_id=session_id, role="assistant", content=text,
                      metadata_json=json.dumps({"kind": "nudge", "hint": hint}, ensure_ascii=False))
        s.add(msg)
        s.commit()
        s.refresh(msg)
        return {"message_id": msg.id, "nudge": text, "hint": hint}
    finally:
        s.close()
