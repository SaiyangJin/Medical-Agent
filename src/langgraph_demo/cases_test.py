from pathlib import Path
import datetime

from sqlalchemy.dialects.mysql import insert

from src.langgraph_demo.trace_table_init import request_table, trace_table
from src.parent_child_chunk.init_model import engine
import json
import uuid
from src.langgraph_demo.content_retrieve_graph import graph, trace_list
ROOT = Path(__file__).resolve().parents[2]
CASES_PATH=ROOT/"data"/"test"/"cases.jsonl"
CASES_1_PATH=ROOT/"data"/"test"/"cases_level1.jsonl"
CASES_2_PATH=ROOT/"data"/"test"/"cases_level2.jsonl"
CASES_3_PATH=ROOT/"data"/"test"/"cases_level3.jsonl"
CASES_4_PATH=ROOT/"data"/"test"/"cases_level4.jsonl"
# CASES_PATH=ROOT/"data"/"test"/"make_up_disease.jsonl"
def cases_test(cases_path:Path):
    #1先生成uuid
    trace_id = str(uuid.uuid4())
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
            expect_answer_status = line_dict["expect"]
            expect_disease = line_dict.get("expect_disease")
            #打印出引用的info和status，和期待的status(expect)和info
            try:
                #调用llm获取到最终的结果
                start_time = datetime.datetime.now()
                state=graph.invoke({"question": question, "trace_id": str(uuid.uuid4())})
                end_time = datetime.datetime.now()
                #先判断status是否一致，不一致直接标记bad-case。
                if state["answer_status"] != expect_answer_status:
                    bad_case_reason += f"实际的回答状态{state['answer_status']}和期待的回答状态{expect_answer_status}不一致\n"
                #然后如果status==“normal”，需要判断期待病症在不在info里边，如果不在，标记bad-case
                if expect_disease is not None and state["answer_status"] == "normal" and expect_disease not in set([i["disease"] for i in state.get("embedding_res", [])+state.get("keyword_res", [])]):
                    bad_case_reason += f"期待的病症{expect_disease}不在查到的资料里边\n"
            except Exception as e:
                end_time = datetime.datetime.now()
                print(f"请求错误!traceid为: {trace_id} ,问题:{question}")
                with engine.begin() as conn:
                    conn.execute(insert(request_table),{
                        "question":question,
                        "passed": False,#系统错误
                        "trace_id":trace_id,#一次请求一个trace_id
                        "run_id": run_id,#这批的id，用于统计通过率
                        "fail_reason": "系统错误,请查看详细执行链路",
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
                conn.execute(insert(request_table),{
                    "question":state["question"],
                    "passed": bad_case_reason=="",#不是bad_case才能通过
                    "trace_id":state["trace_id"],#一次请求一个trace_id
                    "run_id": run_id,#这批的id，用于统计通过率
                    "fail_reason":  bad_case_reason,
                    "create_time": start_time,
                    "end_time": end_time,
                    "cost_time":(end_time-start_time).total_seconds(),
                    #嗯，如果是系统错误，那就是"系统错误"，如果是bad_case那就输入bad_case_reason
                    "is_system_error": False
                })
if __name__ == '__main__':
    cases_test(CASES_PATH)
    # cases_test(CASES_4_PATH)
