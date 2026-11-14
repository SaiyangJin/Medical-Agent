import asyncio
import traceback
from pathlib import Path
import datetime

from sqlalchemy.dialects.mysql import insert

from src.langgraph_demo.init_redis import redis_template
from src.langgraph_demo.trace_table_init import request_table, trace_table
from src.parent_child_chunk.init_model import engine
import json
import uuid
from src.langgraph_demo.content_retrieve_graph import graph, trace_list
ROOT = Path(__file__).resolve().parents[2]
CASES_PATH=ROOT/"data"/"test"/"cases.jsonl"
CASES_SINGLE_PATH=ROOT/"data"/"test"/"cases_1.jsonl"
CASES_1_PATH=ROOT/"data"/"test"/"cases_level1.jsonl"
CASES_TEST_PATH=ROOT/"data"/"test"/"cases_test.jsonl"
CASES_2_PATH=ROOT/"data"/"test"/"cases_level2.jsonl"
CASES_3_PATH=ROOT/"data"/"test"/"cases_level3.jsonl"
CASES_4_PATH=ROOT/"data"/"test"/"cases_level4.jsonl"
CASES_SCORE_PATH=ROOT/"data"/"test"/"cases_score.jsonl"
# CASES_PATH=ROOT/"data"/"test"/"make_up_disease.jsonl"


async def  cases_test(cases_path:Path):
    #预操作：把redis清空
    redis_template.flushall()

    #1先生成uuid
    # trace_id = str(uuid.uuid4())
    #问问题(⚠这里面传的参数会被维护在state里边)

    ###测试：跑一波测试用例，检测最终生成的链路和引用例，和期待的链路的引用是否一致，根据cases.jsonl
    run_id=uuid.uuid4()
    with open(cases_path,"r",encoding="UTF-8") as f:
        for line in f:
            line=line.strip()#把行末的换行符去掉，看看是否为空行
            if not line: continue
            bad_case_reason=""
            line_dict=json.loads(line)
            question = line_dict["question"]
            expect = line_dict["expect"]

            rank=-1
            trace_id = str(uuid.uuid4())
            #打印出引用的info和status，和期待的status(expect)和info
            try:
                #调用llm获取到最终的结果
                start_time = datetime.datetime.now()

                # 编辑配置：传入线程id
                thread_id=str(uuid.uuid4())
                # config={"configurable":{"thread_id":thread_id}}

                # 传入当前线程的Config，这样就可以启动断点重放了
                state=await graph.ainvoke({"question": question, "trace_id": trace_id})

                #先判断status是否一致，不一致直接标记bad-case。
                question_type=line_dict.get("type")

                #==========================这一块就是进行Cases判断的了==========================
                #统一判断部分
                #判断回答状态
                if state["answer_status"] != expect:
                    bad_case_reason += f"实际的回答状态{state['answer_status']}和期待的回答状态{expect}不一致\n"

                #特异性判断部分
                #如果有expect_disease一栏，判断疾病在不在资料里，顺便判断出第几位
                expect_disease = line_dict.get("expect_disease")
                if expect_disease:
                    finally_res = state.get("finally_res", [])
                    if finally_res:
                        #如果有finally_res，那就开始判断expect_disease在哪里
                        for index,one in enumerate(finally_res):
                            if one["disease"]== expect_disease:
                                rank=index
                                break
                if question_type=="normal" and rank==-1:
                    #找不到对应疾病，标记bad-case
                    bad_case_reason += f"没有检索到期待疾病{expect_disease}\n"
                if question_type== "knowledge_graph":
                    #t1知识图谱类型
                    #t1.1先判断expect_disease在不在资料里面
                    # expect_disease = line_dict.get("expect_disease")
                    expect_graph_doc_num = line_dict.get("expect_graph_doc_num")
                    #然后需要判断期待病症在不在graph资料结果里边
                    disease_list = set([i["disease"] for i in state.get("graph_res", [])])
                    if len(disease_list)<expect_graph_doc_num:
                        bad_case_reason += f"知识图谱检索资料结果数{len(disease_list)}量少于期待数{expect_graph_doc_num}个\n"
                    # if expect_disease and expect_disease not in disease_list:
                    #     bad_case_reason += f"期待的病症{expect_disease}不在知识图谱查到的资料里边;\n"
                if question_type== "fast_answer":
                    #t2快速回答类型
                    #t2.0再跑一遍，这次要使用缓存了
                    state_again=await graph.ainvoke({"question": question, "trace_id": str(uuid.uuid4())})
                    #t2.1判断是否跑了大模型
                    if state_again.get("use_llm", False):
                        bad_case_reason += f"调用了大模型，但Fast_Answer类型期待不使用大模型\n"
                    #t2.2判断是否有回答
                    if not state_again.get("fast_answer", ""):
                        bad_case_reason += f"fast_answer为空,缓存没有命中！\n"
                #===========================判断结束=========================================
            except Exception as e:

                end_time = datetime.datetime.now()
                print(f"请求错误!traceid为: {state['trace_id']} ,问题:{question}")
                with engine.begin() as conn:
                    conn.execute(insert(request_table),{
                        "type":line_dict.get("type"),
                        "question":question,
                        "passed": False,#系统错误
                        "trace_id":trace_id,#一次请求一个trace_id
                        "run_id": run_id,#这批的id，用于统计通过率
                        "citation_status": None,#引用状态,有"NO_CITATION,NORMAL_CITATION,ERROR_CITATION"
                        "fail_reason": traceback.format_exc(),
                        "rank":rank,#如果是-1，那就说明没有找到对应疾病
                        "create_time": start_time,
                        "end_time": end_time,
                        "cost_time":(end_time-start_time).total_seconds(),
                        "is_system_error": True
                    })
                continue
            finally:
                with engine.begin() as conn:
                    conn.execute(insert(trace_table),trace_list)
                    #注意清理，否则会越来越多。
                    trace_list.clear()
            # 现在，要么过，要么就是bad——case
            with engine.begin() as conn:
                end_time = datetime.datetime.now()
                conn.execute(insert(request_table),{
                    "type":line_dict.get("type"),
                    "question":state["question"],
                    "passed": bad_case_reason=="",#不是bad_case才能通过
                    "trace_id":trace_id,#一次请求一个trace_id
                    "run_id": run_id,#这批的id，用于统计通过率
                    "citation_status": state.get("citation_status",None),#引用状态,有"NO_CITATION,NORMAL_CITATION,ERROR_CITATION"
                    "fail_reason":  bad_case_reason,
                    "rank":rank,#如果是-1，那就说明没有找到对应疾病
                    "create_time": start_time,
                    "end_time": end_time,
                    "cost_time":(end_time-start_time).total_seconds(),
                    #嗯，如果是系统错误，那就是"系统错误"，如果是bad_case那就输入bad_case_reason
                    "is_system_error": False
                })

if __name__ == '__main__':
    # asyncio.run(cases_test(CASES_SINGLE_PATH))
    # asyncio.run(cases_test(CASES_SINGLE_PATH)) #启动事件循环，就是启动异步调用
    # asyncio.run(cases_test(CASES_PATH))
    # asyncio.run(cases_test(CASES_2_PATH))
    asyncio.run(cases_test(CASES_4_PATH))
    # asyncio.run(cases_test(CASES_SCORE_PATH))

