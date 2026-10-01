import datetime
from sqlalchemy import select

from src.langgraph_demo.init_redis import redis_template
from src.parent_child_chunk.insert_parent_child_ import disease_parent_chuck_table
import re
import json
import traceback
from sqlalchemy.dialects.mysql import insert
from src.service.user_chat_table_init import user_chat_request_table
from src.parent_child_chunk.init_model import engine

import time
from src.data_graph.neo4j_init import neo4j_driver
import uuid
from src.langgraph_demo.langgraph_demo_graph_constant import (
    NORMAL_CITATION, ERROR_CITATION, NO_CITATION,
    ANSWER_STATUS_NORMAL, ANSWER_STATUS_REFUSE,
    NODE_SAFETY_CHECK, NODE_DANGER_HANDLER,
    NODE_RETRIEVE_KEYWORD, NODE_RETRIEVE_EMBEDDING,
    NODE_HANDLE_RETRIEVE_RES, NODE_SEND_TO_LLM,
    NODE_VALIDATE_REFERENCE, NODE_POST_GUARDRAIL, NODE_REFUSE_ANSWER, ANSWER_STATUS_DANGER, danger_word_list,
    NODE_RETRIEVE_GRAPH, disease_list,  NODE_FAST_ANSWER_HANDLER, NODE_FAST_ANSWER_JUDGER,
)
from src.parent_child_chunk.content_retrieve import retrieve_by_keyword, retrieve_by_embedding, \
    get_doc_with_score_by_parent_id_list, retrieve_by_knowledge_graph
from langchain_core.prompts import ChatPromptTemplate
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from src.parent_child_chunk.init_model import qwenModel
from src.langgraph_demo.trace_table_init import request_table, trace_table

certainty_replace_list=[
    ("您确诊为","您的情况可能显示"),
    ("你确诊为","你的情况可能显示"),
    ("您得了","您的情况可能显示"),
    ("你得了","你的情况可能显示")
]
MEDICAL_DISCLAIMER="本回答由AI生成,仅供参考,不代表专业医疗意见。"
random_uuid=""
trace_list=[]

TABLE=["肌肉萎缩", "肌肉无力", "吞咽困难", "肌肉痉挛", "肌肉僵硬", "构音障碍", "步态异常", "精细运动障碍", "反射亢进", "肌肉颤动", "情绪失控", "咀嚼困难", "呼吸困难", "眼球运动障碍", "认知障碍", "疼痛", "抑郁", "睡眠障碍", "便秘", "流涎"]

class State(TypedDict):
    question: str
    embedding_res: list
    keyword_res: list
    graph_res: list
    finally_res: list #合并去重过滤之后的最终结果
    answer: str
    info: str
    file_nos:list
    citation_status: str
    retry_count: int
    is_danger: bool
    danger_situation_list: list
    trace_id: str
    answer_status:str #有"danger"，"normal"，"refuse"三种状态
    fast_answer:str #fast_answer对应的结果
    redis_key:str #redis的key
    use_llm:bool #是否使用了大模型

#装饰器，记录节点耗时
#因为graph药求传入的是一个函数，你这只是把fn替换成了time_recorder_wrapper，框架该传入state还是传入了state，包了一层而已
def node_wrapper(fn):
    def time_recorder_wrapper(state):
        start_time=datetime.datetime.now()
        error=None
        trace_id = state.get("trace_id")
        result=None
        try:
            result=fn(state)
        except Exception as e:
            error=str(traceback.format_exc())
            raise Exception(error)
        finally:
            end_time = datetime.datetime.now()
            #两个相减是duration类，所以要提取出秒数
            # print(f"方法:{fn.__name__} 耗时: {(end_time - start_time).total_seconds()} 秒")
            document = {"node_name": fn.__name__,
                        "result": result,
                        "trace_id": trace_id,
                        "error": error,
                        "start_time": start_time,
                        "end_time": end_time,
                        "question": state.get("question",""),
                        "cost_time": (end_time - start_time).total_seconds(),  # 时间类型相减
                        "is_deleted": False
                        }
            trace_list.append(document)
        return result
    return time_recorder_wrapper

#第一条链路:关键词检索
def retrieve_by_keyword_node(state:State):
    return {"keyword_res":retrieve_by_keyword(state['question'])}

#第二条链路:向量检索
def retrieve_by_embedding_node(state:State):
    return {"embedding_res":retrieve_by_embedding(state['question'],10)}

#第三条链路:知识图谱检索
def retrieve_by_knowledge_graph_node(state:State):
    return {"graph_res": retrieve_by_knowledge_graph(state["question"])}


#依据获取到的doc获取该证据的分数
def get_score(doc,question:str)->int:
    if doc["disease"] in question:
        return 0
    return 1
#处理检索结果,去重,拼贴info
def handle_retrieve_res(state:State):
    #1,取出两个返回的结果
    embedding_res = state['embedding_res']
    keyword_res = state['keyword_res']
    graph_res = state['graph_res']
    question=state["question"]
    nos = []
    embedding_ids=set()
    #2,制作去重id集合
    for embedding_re in embedding_res:
        embedding_ids.add(embedding_re["id"])


    #TODO这边还需要取一个最小的score
    #3，列表推导式把keyword中在embedding_res中的元素过滤掉，只留下特异性元素，性能更加
    keyword_res=[keyword for keyword in keyword_res if keyword["id"] not in embedding_ids]
    keyword_ids=[]
    for keyword_re in keyword_res:
        keyword_ids.append(keyword_re["id"])

    # print("去重后的资料为：", keyword_res)

    list_all = embedding_res + keyword_res
    #4，根据疾病打分重排
    list_all.sort(key=lambda doc:(get_score(doc,question),doc["score"] if doc.get("score") else 0.999))

    graph_res=[one_graph for one_graph in graph_res if one_graph["id"] not in embedding_ids and one_graph["id"] not in keyword_ids]

    list_all=graph_res+list_all

    # print("去重后的资料为：", list_all)
    # 5,拼贴文本
    info=""

    for index,text in enumerate(list_all):
        #拼  贴带换行，结构化的资料语句
        nos.append(index+1)
        info+=f"\n\n[{index+1}]:【{text['disease']}-{text['title']}】{text['text']}\n\n"
    return {"keyword_res":keyword_res,"info":info,"finally_res":list_all,"file_nos":nos}

#检查用户危急情况的函数
def safety_check(state:State):
    question = state['question']
    #维护危险词列表
    temp_danger_situation_list=[]
    for danger_word in danger_word_list:
        if danger_word in question:
            temp_danger_situation_list.append(danger_word)
    #判断是否包含危险词，如果包含则返回危险情况列表
    if len(temp_danger_situation_list)!=0:
        return {
            "is_danger": True,
            "danger_situation_list": temp_danger_situation_list
        }
    else:
        #检查的时候重置危险情况列表
        return {"is_danger": False, "danger_situation_list": []}
#安全检查完之后，转发的函数
def safety_check_router(state:State):
    if state.get("is_danger", False):
        return NODE_DANGER_HANDLER
    else:
        return [NODE_RETRIEVE_KEYWORD, NODE_RETRIEVE_EMBEDDING, NODE_RETRIEVE_GRAPH]
#安全检查出危险情况之后，调用的函数
def danger_situation_handler(state:State):
    return {"answer": "您描述的情况是危险情况，需要紧急处理，请立即就医。","answer_status":ANSWER_STATUS_DANGER}

#定义系统提示词，发送给大模型，取得结果
def send_to_llm(state:State):
    # raise Exception("安全检查错误")

    info = state['info']
    question = state['question']

    #1，定义系统提示词
    SYSTEM_PROMPT = """
    1,身份介绍：你是一个医疗咨询助手，你要根据我提供给你的已有的资料回答问题，
    不要根据自己的记忆回答，如果没有相关资料，回答不知道
    
    2,在回答里面在对应的内容后面贴出我给你的资料的编号，但是如果资料确实对不上用户的问题，也没有相似的资料，那就可以生成不带引用的回答
    在回答的最后给出编号+资料的摘要，就像：
    [1]xxxxx
    [2]xxxxx
    一条一行即可
    注意，必须是回答里面有资料引用，你才能在回答的最后给出编号+资料的摘要，如果回答没有资料引用，不要贴出摘要

    
    3,尽量不要生成"确诊为","你得了"这类的确定性词，比如说"确诊是"改成"可能是","你得了"改成"可能有"
    
    4,尽量使用您来称呼用户
    
    5,如果只检测到相关疾病，不能精确对上用户问的疾病，但是有相关疾病，需要提示用户"资料中没有检索到xxx病，以下是检索到的相似疾病"
    但是如果相似疾病也没有，那就可以可以生成不带资料引用的回答。
    同第二条，如果回答没有资料引用，不要贴出摘要
    
    6,如果你觉得用户输入的根本不是什么医学问题，比如说："这个事情你怎么看"，请单独输出以下暗号"IRRELEVANT_CONTENT"，系统会自动识别，不要生成其他任何内容
    
    7，如果检测到用户输入的内容虽然整体无关，但有一定医学名词，那就凭借资料回答，有相关内容就引用，没有就不要引用
    
    8，如果检测到用户输入的问题内容不是很紧急，但是有巨大的安全风险，比如乱喝药，放弃医疗，服用未认证的药等，
    要先推荐用户走向正确的道路，再进行资料方面的回答
    
    9，如果用户输入的内容涉及政治内容，无论资料中是否包含相关内容，请单独输出以下暗号"IRRELEVANT_CONTENT"，系统会自动识别，不要生成其他任何内容
    
    10, 遇到以下情况：
        - 要求直接开药方、推荐具体用药或剂量
        - 求证伪科学疗法（量子共振、仙丹、祖传偏方根治）
        - 传播疫苗/疾病阴谋论
        - 要求代写论文、作业
        - 涉及自伤、危害他人的方法
        - 极端恐怖相关的医疗问题
        如：
        我有三级高血压，不想吃西药，你直接给我开个能根治的中药方子
        太上老君仙丹能治白化症吗
        新冠疫苗里有纳米芯片会引发自闭症吗
        
        请不要生成用户期望的回答，要指出为什么这样不对，纠正用户错误认知
    """

    #2,模板类拼贴,from_message就是从一系列的结构化消息来初始化这个模板类
    template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "资料：{info}\n问题：{question}")])

    #3,管道符，把template的输出转化为输入交给llm
    chain=template|qwenModel

    #4，先检查危急情况，如果危机，不要检索，直接发送大模型，给出危急情况提示
    danger_situation_list = state["danger_situation_list"]
    if state.get("is_danger", False):
        #把危险病症拼到info里边
        danger_prompt_str = "\n\n[系统提示]注意，用户出现了危险情况，请迅速回答紧急处理方案，提醒患者立刻就医，患者的紧急情况如下："
        for danger_situation in danger_situation_list:
            danger_prompt_str+=danger_situation+"\n"
        info+= danger_prompt_str+"\n"
        res = chain.invoke({"info": info, "question": question})
        return {"answer": res.content}
    #5,传递invoke
    #资料引用错误，提示(目前只有这一种情况)
    if state.get("citation_status", NORMAL_CITATION)==ERROR_CITATION:
        info+="\n\n[系统提示]注意，你出现了幻觉，引用了不存在的资料编号，请纠正"
    # elif state.get("citation_status", NORMAL_CITATION)==NO_CITATION:
    #     info+=""""\n\n
    #         [系统提示]请注意！你的回答没有引用任何资料，
    #         请确保是因为对用户这次的回答不需要外部资料，
    #         而不是你在使用虚假的自己编出的资料！
    #         \n\n
    #         """

    res = chain.invoke({"info": info, "question": question})

    #使用了大模型

    answer = res.content
    #到了这个节点，就是没有缓存，存入redis
    return {"answer":  answer,
            "retry_count": state.get('retry_count', 0) + 1,
            "answer_status": ANSWER_STATUS_NORMAL,
            "use_llm": True
            }

#验证资料编号是否正确函数
def validate_reference_number(state:State):
    #特殊情况，如果患者是危险情况，可以免去检查，直接宣布NORMAL
    if state.get("is_danger", False):
        return {"citation_status": NORMAL_CITATION}

    text = state['answer']
    nos = state["file_nos"]
    nums = re.findall(r"\[(\d+)\]", text)

    # print("======================找到的编号如下", set(nums))
    # print("======================正确的编号如下", set(nos))
    #如果nums编号数组为空，说明没有引用任何编号，需要打上标记

    if text== "IRRELEVANT_CONTENT":
        return {"citation_status": NO_CITATION}
    if set([str(num) for num in set(nums)]) <= set([str(num) for num in set(nos)]):
        #如果是子集，就说明正常
        return {"citation_status": NORMAL_CITATION}
    else:
        #否则错误，维护错误状态机
        return {"citation_status": ERROR_CITATION}

#后置guardrail，在回答末尾加上医疗免责声明，并把一些敏感词替换掉（如"您得了"---"你可能是"）
def post_guardrail(state:State):
    answer = state['answer']
    #替换敏感词
    for certainty_replace in certainty_replace_list:
        answer=answer.replace(certainty_replace[0],certainty_replace[1])
    #医疗免责声明
    answer += f"\n {MEDICAL_DISCLAIMER}\n"
    # print("最终答案：", answer)

    #FastAnswer缓存，只有正常引用的回答才可以进缓存
    if state.get("redis_key") and state.get("citation_status") == NORMAL_CITATION:
        redis_template.set(state["redis_key"], answer)

    return {"answer": answer}

#检验error函数，如果error==ERROR_CITATION，那就返回END,如果不是，那就返回CONTINUE导到下一个节点
def validate_reference_number_router(state:State):
    status = state.get("citation_status", ERROR_CITATION)
    if status == NO_CITATION:
        return NODE_REFUSE_ANSWER
    if status == ERROR_CITATION:
        if state.get('retry_count', 0) >= 3:
            return NODE_POST_GUARDRAIL
        return NODE_SEND_TO_LLM
    else:
        return NODE_POST_GUARDRAIL

def refuse_answer_handler(state:State):
    return {"answer": "本问题超出了我的能力范围"
        ,"answer_status":ANSWER_STATUS_REFUSE}

#工具函数，判断问题有没有关键词
def abstract_question_keyword(question: str):
    # 1，去掉问题空白和句末的标点
    question = question.strip().rstrip("? . ! ！？")
    # 2，看看是否endwith("是什么","是啥","是怎么回事","是什么情况","是什么病","啥病","是怎么个事")
    if question.endswith(("是什么", "是啥", "是怎么回事", "是什么情况", "是什么病", "啥病", "是怎么个事")):
        return "定义"
    # 3，看看是否startswith("介绍一下","讲讲","介绍","给我详细介绍")
    if question.startswith(("介绍一下", "讲讲", "介绍", "给我详细介绍")):
        return "定义"
    # 4，如果有就return "定义"
    # 5，没有就return None
    return None

def abstract_disease_keyword(question: str):
    question = question.strip().rstrip("? . ! ！？")
    res=[]
    for disease in disease_list:
        if disease in question:
            res.append(disease)
    #如没有,或者多个疾病，算复杂问题，交给LLM
    return None if len(res)!=1 else res[0]

#判断问题是否需要fast_answer
def fast_answer_judger(state:State):
    question = state['question']
    #先提取问题的病和问法
    disease = abstract_disease_keyword(question)
    question_type = abstract_question_keyword(question)
    #如果一个空，说明不能走缓存了
    if not disease or not question_type:
        return None
    #拼贴redis的key
    #如果不存在此key或者值不存在，发给大模型
    redis_key = f"fast:{disease}:{question_type}"
    if not redis_template.exists(redis_key) or not redis_template.get(redis_key):
        return {"redis_key":redis_key}
    #如果存在，维护一个fast_answer
    return {"fast_answer": redis_template.get(redis_key),"redis_key":redis_key}

def fast_answer_router(state:State):
    if state.get("fast_answer", None):
        #如果有fast_answer，走NODE_FAST_ANSWER
        return NODE_FAST_ANSWER_HANDLER
    return NODE_SEND_TO_LLM

#如果要快速回答,要给answer生成一些什么
def fast_answer_handler(state:State):
    return {"answer": state["fast_answer"],"answer_status":ANSWER_STATUS_NORMAL}


#整个建图流程：
# 1，根据START创建图
graph = StateGraph(State)
#2，增加所有节点
graph.add_node(NODE_RETRIEVE_KEYWORD,    node_wrapper(retrieve_by_keyword_node))
graph.add_node(NODE_RETRIEVE_EMBEDDING,  node_wrapper(retrieve_by_embedding_node))
graph.add_node(NODE_RETRIEVE_GRAPH,      node_wrapper(retrieve_by_knowledge_graph_node))
graph.add_node(NODE_SEND_TO_LLM,         node_wrapper(send_to_llm))
graph.add_node(NODE_SAFETY_CHECK,        node_wrapper(safety_check))
graph.add_node(NODE_HANDLE_RETRIEVE_RES, node_wrapper(handle_retrieve_res))
graph.add_node(NODE_VALIDATE_REFERENCE,  node_wrapper(validate_reference_number))
graph.add_node(NODE_POST_GUARDRAIL,      node_wrapper(post_guardrail))
graph.add_node(NODE_DANGER_HANDLER,      node_wrapper(danger_situation_handler))
graph.add_node(NODE_REFUSE_ANSWER,       node_wrapper(refuse_answer_handler))
graph.add_node(NODE_FAST_ANSWER_HANDLER, node_wrapper(fast_answer_handler))
graph.add_node(NODE_FAST_ANSWER_JUDGER, node_wrapper(fast_answer_judger))
#3，增加所有边
#紧急情况检查优先
graph.add_edge(START, NODE_SAFETY_CHECK)
#如果安全检查有问题，到danger_situation_handler处理
#如果安全检查没有问题，到retrieve_by_keyword_node和retrieve_by_embedding_node
graph.add_conditional_edges(NODE_SAFETY_CHECK, safety_check_router)
graph.add_edge(NODE_DANGER_HANDLER, NODE_POST_GUARDRAIL)
#4，尾部连接
graph.add_edge(NODE_RETRIEVE_KEYWORD,    NODE_HANDLE_RETRIEVE_RES)
graph.add_edge(NODE_RETRIEVE_EMBEDDING,  NODE_HANDLE_RETRIEVE_RES)
graph.add_edge(NODE_RETRIEVE_GRAPH,      NODE_HANDLE_RETRIEVE_RES)

graph.add_edge(NODE_HANDLE_RETRIEVE_RES, NODE_FAST_ANSWER_JUDGER)
graph.add_conditional_edges(NODE_FAST_ANSWER_JUDGER, fast_answer_router)

graph.add_edge(NODE_SEND_TO_LLM,         NODE_VALIDATE_REFERENCE)

#如果资料编号有错误，send_to_llm，如果资料编号没有错误，到post_guardrail处理,如果没有引用编号，拒绝回答
graph.add_conditional_edges(NODE_VALIDATE_REFERENCE, validate_reference_number_router)
graph.add_edge(NODE_REFUSE_ANSWER, NODE_POST_GUARDRAIL)
graph.add_edge(NODE_FAST_ANSWER_HANDLER, END)
graph.add_edge(NODE_POST_GUARDRAIL, END)
#5,编译
graph=graph.compile()


if __name__ == '__main__':
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    answer=""
    question="菊池病是什么"
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
        print(f"请求错误!traceid为: {trace_id} ,问题:{question},错误信息:{e}+{traceback.format_exc()}")
    finally:
        with engine.begin() as conn:
            conn.execute(insert(trace_table),trace_list)
            trace_list.clear()
    with engine.begin() as conn:
        conn.execute(insert(user_chat_request_table),{
            "question":question,
            "trace_id":trace_id,#一次请求一个trace_id
            "answer": answer,
            "cost_time": time.time() - start_time,
            "is_system_error": False
        })
        print(f"请求成功!traceid为: {trace_id} ,问题:{question},答案:{answer}")



