import asyncio
import time
import traceback
import uuid

from sqlalchemy import insert

from src.langgraph_demo.content_retrieve_graph import graph, trace_list
from src.langgraph_demo.trace_table_init import trace_table
from src.parent_child_chunk.init_model import engine
from src.service.user_chat_table_init import user_chat_request_table

async def  langgraph():
    # 发送问题
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    answer = ""
    question = "有点晕晕的！"
    # question = "出了好多血"
    # question = "谈谈114514"
    try:
        async for ev in  graph.astream_events(input={"question": question, "trace_id": trace_id}, version="v2"):
            if ev["event"]=="on_chat_model_stream":
                if ev["data"]["chunk"].content:
                    print(ev["data"]["chunk"].content,end="",flush=True)
    except Exception as e:
        # 报错返回500
        with engine.begin() as conn:
            conn.execute(insert(user_chat_request_table), {
                "question": question,
                "trace_id": trace_id,  # 一次请求一个trace_id
                "answer": answer,
                "cost_time": time.time() - start_time,
                "is_system_error": True
            })
        print(f"请求错误!traceid为: {trace_id} ,问题:{question},错误信息:{e}+{traceback.format_exc()}")
    finally:
        with engine.begin() as conn:
            conn.execute(insert(trace_table), trace_list)
            trace_list.clear()
    with engine.begin() as conn:
        conn.execute(insert(user_chat_request_table), {
            "question": question,
            "trace_id": trace_id,  # 一次请求一个trace_id
            "answer": answer,
            "cost_time": time.time() - start_time,
            "is_system_error": False
        })
        print(f"请求成功!traceid为: {trace_id} ,问题:{question},答案:{answer}")

if __name__ == '__main__':
    asyncio.run(langgraph())