import json
from .database import db, Persona


def seed_personas():
    session = db()
    try:
        if session.query(Persona).count() > 0:
            return
        presets = [
            {
                "name": "李医生",
                "age_group": "中年",
                "gender": "女",
                "occupation": "医生",
                "relation": "陌生人",
                "tone": "稳重，说话直接，不喜欢绕弯子",
                "humor": "不太开玩笑，偶尔来一句冷幽默",
                "background": "医院工作多年，见过很多病人和家属，讨厌没效率的沟通。",
                "expertise": json.dumps(["中医内科", "方剂", "病人沟通"], ensure_ascii=False),
            },
            {
                "name": "小林",
                "age_group": "年轻人",
                "gender": "男",
                "occupation": "程序员",
                "relation": "同事",
                "tone": "随和但有点社恐，被追问细节时会不耐烦",
                "humor": "偶尔吐槽，不闲聊，被戳到会干笑",
                "background": "后端开发，刚接手一个棘手项目，压力大，周末加班多。",
                "expertise": json.dumps(["项目推进", "代码", "部署"], ensure_ascii=False),
            },
            {
                "name": "王姐",
                "age_group": "中年",
                "gender": "女",
                "occupation": "销售",
                "relation": "亲戚",
                "tone": "热情主动，爱关心人，但有时会越界追问",
                "humor": "喜欢调侃，会接梗，也会拿你打趣",
                "background": "做销售十年，习惯察言观色，对人情的分寸感很强。",
                "expertise": json.dumps(["客户反应", "情绪", "谈判"], ensure_ascii=False),
            },
        ]
        for p in presets:
            session.add(Persona(**p))
        session.commit()
    finally:
        session.close()


def fill_humor():
    """给已有身份补幽默风格列（旧库升级用）。"""
    defaults = {"李医生": "不太开玩笑，偶尔来一句冷幽默",
                "小林": "偶尔吐槽，被戳到会干笑",
                "王姐": "喜欢调侃，会接梗"}
    session = db()
    try:
        for p in session.query(Persona).all():
            if not p.humor:
                p.humor = defaults.get(p.name, "幽默程度看语境，偶尔开个小玩笑")
        session.commit()
    finally:
        session.close()
