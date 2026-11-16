"""会话历史存取：Redis List，按 user_id + session_id 隔离。

和 checkpointer 的分工：
  - checkpointer 存「图执行到哪一步」（thread_id 索引）
  - 这里存「聊过什么」（session_id 索引），用来拼进 prompt

key：chat:history:{user_id}:{session_id}
每条：{"role": "user"|"assistant", "content": "..."}
"""

from __future__ import annotations

import json

from src.langgraph_demo.init_redis import redis_template

MAX_TURNS = 5           # 保留最近 5 轮（用户 + AI 共 10 条）
TTL_SECONDS = 30 * 60   # 30 分钟不说话就过期


def _key(user_id: str, session_id: str) -> str:
    return f"chat:history:{user_id}:{session_id}"


def load_history(user_id: str, session_id: str) -> list[dict]:
    """按时间顺序返回历史消息；Redis 异常时返回空列表，不影响主流程。"""
    if not session_id:
        return []
    try:
        raw = redis_template.lrange(_key(user_id, session_id), 0, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        return []


def append_turn(user_id: str, session_id: str, question: str, answer: str) -> None:
    """追加本轮问答，裁剪到最近 MAX_TURNS 轮，并刷新 TTL。"""
    if not session_id or not answer:
        return
    try:
        key = _key(user_id, session_id)
        redis_template.rpush(
            key, json.dumps({"role": "user", "content": question}, ensure_ascii=False)
        )
        redis_template.rpush(
            key, json.dumps({"role": "assistant", "content": answer}, ensure_ascii=False)
        )
        redis_template.ltrim(key, -MAX_TURNS * 2, -1)
        redis_template.expire(key, TTL_SECONDS)
    except Exception:
        pass  # 历史写失败不影响本次回答
