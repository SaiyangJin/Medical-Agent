#基本服务：提供问题咨询服务
#对应的技术栈：FastApi，就是让这个py变成了一个服务
from contextlib import asynccontextmanager

#导入FastApi核心包
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.dialects.mysql import insert

from src.langgraph_demo.indicator_test import indicator_test
from src.langgraph_demo.trace_table_init import request_table, trace_table
from src.service.user_chat_table_init import user_chat_request_table
from src.parent_child_chunk.init_model import engine
from pathlib import Path
import time
import uuid
from src.langgraph_demo.content_retrieve_graph import graph, trace_list

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH=ROOT/"data"/"test"/"cases.jsonl"

#创建一个DTO
class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    code: int
    msg: str
    data: dict


#生命周期
@asynccontextmanager
async def lifespan(app:FastAPI):
    #启动
    res = indicator_test(CASES_PATH)
    if res:
        error_text = "测试没有通过,具体信息如下:"
        for err_text in res:
            error_text+='\n'+err_text+'\n'
        raise SystemExit(error_text)
    yield
    #关闭时


#创建一个应用
app = FastAPI(lifespan=lifespan)



#主逻辑函数
@app.post("/chat",response_model=AskResponse)
def chat(askRequest:AskRequest):
    trace_id = str(uuid.uuid4())
    question = askRequest.question
    start_time = time.time()
    answer=""
    try:
        state=graph.invoke({"question": question, "trace_id": trace_id})
        answer=state["answer"]
    except Exception as e:
        #报错返回500
        with engine.begin() as conn:
            conn.execute(insert(user_chat_request_table),{
                "question":question,
                "trace_id":trace_id,#一次请求一个trace_id
                "answer": answer,
                "cost_time": time.time() - start_time,
                "is_system_error": True
            })
        return AskResponse(code=500, msg="系统错误", data={})
    finally:
        with engine.begin() as conn:
            conn.execute(insert(trace_table),trace_list)
            trace_list.clear()
        # 现在，要么过，要么就是bad——case
    with engine.begin() as conn:
        conn.execute(insert(user_chat_request_table),{
            "question":question,
            "trace_id":trace_id,#一次请求一个trace_id
            "answer": answer,
            "cost_time": time.time() - start_time,
            "is_system_error": False
        })
    return AskResponse(code=200, msg="", data={"answer":answer})


