#基本服务：提供问题咨询服务
#对应的技术栈：FastApi，就是让这个py变成了一个服务
from contextlib import asynccontextmanager
from fastapi import Request
from fastapi.responses import JSONResponse
import json


#导入FastApi核心包
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel
from sqlalchemy.dialects.mysql import insert
from starlette.responses import StreamingResponse

from src.langgraph_demo.indicator_test import indicator_test
from src.langgraph_demo.trace_table_init import request_table, trace_table
from src.service.user_chat_table_init import user_chat_request_table
from src.parent_child_chunk.init_model import engine
from pathlib import Path
import time
import uuid

from src.langgraph_demo.content_retrieve_graph import  trace_list, DB_URI,builder

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH=ROOT/"data"/"test"/"cases.jsonl"

#创建一个DTO
class AskRequest(BaseModel):
    question: str
    thread_id: str #前端生成，一个对话一个thread_id

class RetryRequest(BaseModel):
    question: str
    thread_id: str #前端生成，一个对话一个thread_id

class AskResponse(BaseModel):
    code: int
    msg: str
    data: dict


#本声明周期完成两件事情，一是指标测试，二是构建graph
@asynccontextmanager #执行声明周期的注解
async def lifespan(app:FastAPI):
    #先进行指标测试，通过才让启动
    res = indicator_test()
    if res:
        #测试没有通过
        error_text = "测试没有通过,具体信息如下:"
        for err_text in res:
            error_text+='\n'+err_text+'\n'
        raise SystemExit(error_text)

    #测试通过，开始构建graph
    pool = AsyncConnectionPool(conninfo=DB_URI, max_size=10, open=False) # 创建一个数据库连接池，先别开，后面手动开

    await pool.open()
    checkpointer = AsyncPostgresSaver(pool) #checkPointer用这个池读写PG
    await checkpointer.setup()

    #开始编译graph为真正的异步图,存入app.state,这是随应用存活的生命周期，即取即用
    app.state.graph=builder.compile(checkpointer=checkpointer)

    yield #yield是一个边界，上面的启动时，下面的关闭时

    await pool.close()



#依据生命周期，创建一个应用

app = FastAPI(lifespan=lifespan)

@app.exception_handler(Exception)
async def all_exception_handler(request:Request,exc:Exception):
    print("异常捕获",JSONResponse(status_code=200,content={"code":500,"msg":"系统异常","data":{}}))
    return JSONResponse(status_code=200,content={"code":500,"msg":"系统异常","data":{}})

#主逻辑函数


@app.post("/chat",response_model=AskResponse)
def chat(askRequest:AskRequest):
    # return AskResponse(code=200, msg="", data={"answer":answer})
    return StreamingResponse(generate_object(askRequest),media_type="text/event-stream")

@app.post("/retry",response_model=AskResponse)
def chat(retryRequest:RetryRequest):
    # return AskResponse(code=200, msg="", data={"answer":answer})
    return StreamingResponse(generate_object_retry(retryRequest),media_type="text/event-stream")


async def generate_object_retry(retryRequest: RetryRequest):
    question = retryRequest.question
    thread_id = retryRequest.thread_id
    config={"configurable":{"thread_id": thread_id}} # 前端生成，一个对话一个thread_id,这是配置

    start_time = time.time()
    answer = ""
    final_answer=""
    try:
        #启动图的同时，监听里面的事件，这边监听一个流式块和一个最终答案，顺便传入一个config配置，config配置的东西就是线程id，用于标记本次请求，然后下一次可以恢复本次请求
        async for ev in app.state.graph.astream_events(None, version="v2",config=config):
            if ev["event"] == "on_chat_model_stream":
                if ev["data"]["chunk"].content:
                    yield f"data: {json.dumps(ev['data']['chunk'].content,ensure_ascii=False)}\n\n"
            elif ev["event"]=="on_chain_end":
                if "data" in ev:
                    if "output" in ev["data"]:
                        if isinstance(ev["data"]["output"], dict) and "answer" in ev["data"]["output"]:
                            final_answer = ev["data"]["output"]  ["answer"]
                # if "answer" in ev["data"]["output"]:
                #     final_answer = ev["data"]["output"]["answer"]
        print("final_answer:",final_answer)
        if final_answer:
            yield f"event: done\ndata: {json.dumps(final_answer,ensure_ascii=False)}\n\n"
    except Exception as e:
        # 报错返回500
        with engine.begin() as conn:
            conn.execute(insert(user_chat_request_table), {
                "question": question,
                "trace_id": thread_id,  # 一次请求一个trace_id
                "answer": answer,
                "cost_time": time.time() - start_time,
                "is_system_error": True
            })
        raise
    finally:
        with engine.begin() as conn:
            conn.execute(insert(trace_table), trace_list)
            trace_list.clear()
        # 现在，要么过，要么就是bad——case
    with engine.begin() as conn:
        conn.execute(insert(user_chat_request_table), {
            "question": question,
            "trace_id": thread_id,  # 一次请求一个trace_id
            "answer": answer,
            "cost_time": time.time() - start_time,
            "is_system_error": False
        })



async def generate_object(askRequest: AskRequest):
    question = askRequest.question
    thread_id=askRequest.thread_id
    config={"configurable":{"thread_id":thread_id}} # 前端生成，一个对话一个thread_id,这是配置

    start_time = time.time()
    answer = ""
    final_answer=""
    try:
        #启动图的同时，监听里面的事件，这边监听一个流式块和一个最终答案，顺便传入一个config配置，config配置的东西就是线程id，用于标记本次请求，然后下一次可以恢复本次请求
        async for ev in app.state.graph.astream_events(input={"question": question, "trace_id": thread_id}, version="v2",config=config):
            if ev["event"] == "on_chat_model_stream":
                if ev["data"]["chunk"].content:
                    yield f"data: {json.dumps(ev['data']['chunk'].content,ensure_ascii=False)}\n\n"
            elif ev["event"]=="on_chain_end":
                if "data" in ev:
                    if "output" in ev["data"]:
                        if isinstance(ev["data"]["output"], dict) and "answer" in ev["data"]["output"]:
                            final_answer = ev["data"]["output"]["answer"]
                # if "answer" in ev["data"]["output"]:
                #     final_answer = ev["data"]["output"]["answer"]
        print("final_answer:",final_answer)
        if final_answer:
            yield f"event: done\ndata: {json.dumps(final_answer,ensure_ascii=False)}\n\n"
    except Exception as e:
        # 报错返回500
        with engine.begin() as conn:
            conn.execute(insert(user_chat_request_table), {
                "question": question,
                "trace_id": thread_id,  # 一次请求一个trace_id
                "answer": answer,
                "cost_time": time.time() - start_time,
                "is_system_error": True
            })
        raise
    finally:
        with engine.begin() as conn:
            conn.execute(insert(trace_table), trace_list)
            trace_list.clear()
        # 现在，要么过，要么就是bad——case
    with engine.begin() as conn:
        conn.execute(insert(user_chat_request_table), {
            "question": question,
            "trace_id": thread_id,  # 一次请求一个trace_id
            "answer": answer,
            "cost_time": time.time() - start_time,
            "is_system_error": False
        })


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8080)

    #试着取出流事件，然后打印


