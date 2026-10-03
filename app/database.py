from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

engine = create_engine(f"sqlite:///{settings.DB_PATH}", connect_args={"check_same_thread": False})
Base = declarative_base()
db = sessionmaker(bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(Text)
    timezone = Column(Text, default="Asia/Shanghai")
    work_context = Column(Text)
    emotional_context = Column(Text)
    life_context = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class Persona(Base):
    __tablename__ = "personas"
    id = Column(Integer, primary_key=True)
    name = Column(Text)
    age_group = Column(Text)
    gender = Column(Text)
    occupation = Column(Text)
    relation = Column(Text)
    tone = Column(Text)
    humor = Column(Text)  # 幽默/玩笑风格
    background = Column(Text)
    expertise = Column(Text)  # JSON 数组字符串
    style = Column(Text)  # 沟通风格：短句/长篇/爱反问/爱岔开话题/爱讲道理…
    soul = Column(Text)  # 上传的 .md 人物资料，赋予角色"灵魂"
    materials_json = Column(Text)  # 上传的资料文件（txt/md 原文），JSON 数组：[{filename, content, uploaded_at}]
    profile_json = Column(Text)  # 详细资料（家庭/性格/价值观/社交/知识，按 人员身份字段.md 分组）
    config_json = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    def expertise_list(self):
        import json
        try:
            return json.loads(self.expertise or "[]")
        except json.JSONDecodeError:
            return []


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    persona_id = Column(Integer)
    mode = Column(Text)
    status = Column(Text, default="active")
    scene = Column(Text)
    skill_ids = Column(Text)  # 手动指定的 skill 卡 id，JSON 数组；空 = 自动路由
    initial_state_json = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)
    role = Column(Text)
    content = Column(Text)
    metadata_json = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class HiddenState(Base):
    __tablename__ = "hidden_states"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)
    message_id = Column(Integer)
    emotion = Column(Text)
    patience = Column(Text)
    affection = Column(Text)
    distance = Column(Text)
    personality = Column(Text)
    reasoning = Column(Text)
    revealed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class Guess(Base):
    __tablename__ = "guesses"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)
    state_id = Column(Integer)
    guess_json = Column(Text)
    correct = Column(Integer)
    total = Column(Integer)
    analysis = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)
    message_id = Column(Integer)
    total = Column(Integer)
    empathy = Column(Integer)
    clarity = Column(Integer)
    timing = Column(Integer)
    respect = Column(Integer)
    boundary = Column(Integer)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    source = Column(Text)
    triggers = Column(Text)
    examples = Column(Text)
    anti_patterns = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class Skill(Base):
    """一本书蒸馏出的可复用沟通技术卡。"""
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    name = Column(Text)          # 技术名，如「识别控制型沟通」
    source = Column(Text)        # 来源书籍
    triggers = Column(Text)      # JSON 数组：什么情况下该用（场景/弱点描述）
    do = Column(Text)            # 正确做法：该怎么做
    dont = Column(Text)          # 反例：别怎么做
    created_at = Column(DateTime, default=datetime.now)


class CoachComment(Base):
    """暂停点评（跳出角色的教练视角话）。"""
    __tablename__ = "coach_comments"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, index=True)
    turn = Column(Integer)
    comment = Column(Text)
    skill_name = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class UserMemory(Base):
    __tablename__ = "user_memories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    fact = Column(Text)
    source_session = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)


class PersonaMemory(Base):
    """某个角色（身份）视角的对话记忆：我和这个人聊过什么。"""
    __tablename__ = "persona_memories"
    id = Column(Integer, primary_key=True)
    persona_id = Column(Integer, index=True)
    fact = Column(Text)
    source_session = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)


def init_db():
    Base.metadata.create_all(engine)
    _migrate()
    from . import seed
    seed.seed_personas()
    seed.fill_humor()


def _migrate():
    """SQLite 不会自动给已有表加列，这里补齐。"""
    import sqlalchemy as sa

    with engine.connect() as conn:
        def have(table, col):
            rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
            return any(r[1] == col for r in rows)

        if not have("personas", "humor"):
            conn.execute(sa.text("ALTER TABLE personas ADD COLUMN humor TEXT"))
        if not have("personas", "style"):
            conn.execute(sa.text("ALTER TABLE personas ADD COLUMN style TEXT"))
        if not have("personas", "soul"):
            conn.execute(sa.text("ALTER TABLE personas ADD COLUMN soul TEXT"))
        if not have("personas", "materials_json"):
            conn.execute(sa.text("ALTER TABLE personas ADD COLUMN materials_json TEXT"))
        if not have("personas", "profile_json"):
            conn.execute(sa.text("ALTER TABLE personas ADD COLUMN profile_json TEXT"))
        if not have("sessions", "scene"):
            conn.execute(sa.text("ALTER TABLE sessions ADD COLUMN scene TEXT"))
        if not have("sessions", "skill_ids"):
            conn.execute(sa.text("ALTER TABLE sessions ADD COLUMN skill_ids TEXT"))
        conn.commit()
