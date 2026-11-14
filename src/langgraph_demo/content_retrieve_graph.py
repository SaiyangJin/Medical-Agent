import datetime
import inspect
import pypinyin
import re
import traceback

from langgraph.types import RetryPolicy
from pydantic import BaseModel
from src.langgraph_demo.init_redis import redis_template
from src.parent_child_chunk.content_retrieve_constant import ABSTRACT_SYMPTOM_PROMPT
from langchain_core.runnables import RunnableConfig
from src.langgraph_demo.init_logging import logger
from src.langgraph_demo.langgraph_demo_graph_constant import (
    NORMAL_CITATION, ERROR_CITATION, NO_CITATION,
    ANSWER_STATUS_NORMAL, ANSWER_STATUS_REFUSE,
    NODE_DANGER_HANDLER,
    NODE_RETRIEVE_KEYWORD, NODE_RETRIEVE_EMBEDDING,
    NODE_HANDLE_RETRIEVE_RES, NODE_SEND_TO_LLM,
    NODE_POST_GUARDRAIL, NODE_REFUSE_ANSWER, ANSWER_STATUS_DANGER,
    NODE_RETRIEVE_GRAPH, NODE_FAST_ANSWER_HANDLER, NODE_FAST_ANSWER_JUDGER, NODE_VALIDATE_ANSWER,
    disease_list, NODE_INPUT_GREATER, common_disease_dict, alias_transport_white_list, whole_symptoms_list,
    NODE_INPUT_PRE_HANDLE
)
from src.parent_child_chunk.content_retrieve import retrieve_by_keyword, retrieve_by_embedding, retrieve_by_knowledge_graph
from langchain_core.prompts import ChatPromptTemplate
from typing import TypedDict, Literal, cast
from langgraph.graph import StateGraph,START,END
from src.parent_child_chunk.init_model import qwenModel, DATA_BASE_URL

#======================================预定义常量=======================================

#改进LLM生成的回答需要的替换Map
certainty_replace_list=[
    ("您确诊为","您的情况可能显示"),
    ("你确诊为","你的情况可能显示"),
    ("您得了","您的情况可能显示"),
    ("你得了","你的情况可能显示")
]

MEDICAL_DISCLAIMER="本回答由AI生成,仅供参考,不代表专业医疗意见。"

random_uuid=""

trace_list=[]

#=======================================LangGraph=======================================

#LangGraph图流程进行的时候所需要的变量都放在这里管理
class State(TypedDict):
    question: str
    changed_question: str
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
    standard_top_level: int
    symptoms_list_in_question:list
    text_symptom_dict_list:list
    embedding_retrieval_status:bool
    keyword_retrieval_status:bool
    graph_retrieval_status:bool
    refuse_answer:str
    danger_answer:str
    input_pre_handle_label:str
    input_pre_handle_reason:str


#具体节点函数外面包一层函数，用于实现同异步函数分流、节点记录耗时、异常降级
def node_wrapper(fn,fallback=None):
    # 定义异步函数
    # send_to_llm 节点就是异步函数，因为里面调用了流式的Api方便外面获取流式回答交给前端
    async def async_wrapper(state,config=None):

        start_time=datetime.datetime.now()
        error=None
        trace_id = state.get("trace_id")
        result=None

        try:
            #执行fn方法
            if len(inspect.signature(fn).parameters)>=2:
                result=await fn(state,config)
            else:
                result=await fn(state)

        except Exception as ex:
            #如果fn执行过程中出现异常，就记录下来
            error=str(traceback.format_exc())
            #如果有补偿函数，就调用补偿函数，异常降级
            if fallback:
                result= fallback(state)
            #如果没有，则说明异常不能降级，抛出系统错误
            else:
                raise ex

        finally:
            #无论成功失败：都要把本机调用fn记录保存下来，加入trace_list，方便可视化链路排查问题
            end_time = datetime.datetime.now()
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


    # 定义同步函数
    def wrapper(state):
        start_time=datetime.datetime.now()
        error=None
        trace_id = state.get("trace_id")
        result=None
        try:
            result=fn(state)
        except Exception as ex:
            #这个节点异常，如果有补偿函数，就调用补偿函数，异常降级
            if fallback:
                return fallback(state)
            #如果没有，则说明异常不能降级，抛出系统错误
            else:
                error=str(traceback.format_exc())
                raise ex
        finally:
            #无论成功失败：都要把本机调用fn记录保存下来，加入trace_list，方便可视化链路排查问题

            end_time = datetime.datetime.now()
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


    #依据函数是同步异步返回对应的包装函数
    if inspect.iscoroutinefunction(fn):
        return async_wrapper
    else:
        return wrapper


#结构化输出类，规定llm输出的内容要按照如下模式，这边用于预处理函数的时候需要llm产出本次信息标签、理由、文本症状字典列表、危险答案
class OutputStructure(BaseModel):
    #指定标签，说明这个信息是什么类型的
    label:Literal["danger","irrelevant","normal"]
    #理由，如果是拒答、无关，那就填空
    reason:str
    #文本症状字典列表，如果是正常填充
    text_symptom_dict_list:list
    #危险答案，危险情况填充
    danger_answer:str


#安全检查出危险情况之后，调用的函数
def danger_situation_handler(state:State):
    return {"answer": state["danger_answer"],"answer_status":ANSWER_STATUS_DANGER}

#输入预处理函数(节点)，主要是判断问题类型，提取出句中症状和文本症状对应表
def input_pre_handle(state:State):
    symptoms_list_in_question=[]

    #判断症状词是否为空，因为这个症状列表是从neo4j数据库获取的，不能保证neo4j状态
    if whole_symptoms_list:
        #调用大模型获取结果
        SYSTEM_PROMPT = (ABSTRACT_SYMPTOM_PROMPT + "\n以下是症状列表:\n"+','.join(whole_symptoms_list)
                         +"\n"+"\n以下是用户问题\n"+state["question"])
        #设置本模型要结构化输出
        StructuredQwenModel = qwenModel.with_structured_output(OutputStructure)

        #把类型投射到模型调用的结果，让结果获得类型，就是方便ide取获取字段，其实就是套一层皮，不保证返回的真的是OutputStructure
        res = cast(OutputStructure, StructuredQwenModel.invoke(SYSTEM_PROMPT))
        #正常结果如下:["label":'','reason':''。。。。]

        #取出数据
        label = res.label
        reason = res.reason
        print(f"本条评判{label}的原因是{reason}")
        danger_answer = res.danger_answer
        text_symptom_dict_list = res.text_symptom_dict_list

        #用text_symptom_dict_list提取出句中症状
        if  text_symptom_dict_list:
            symptoms_list_in_question=list(set([one_dict["symptom"] for one_dict in text_symptom_dict_list]))

        #根据不同的标签返回不同的结果
        if label== "normal":
            #正常结果：返回症状表、文本症状对应表和标签
            return {"symptoms_list_in_question": symptoms_list_in_question
                , "text_symptom_dict_list": text_symptom_dict_list
                ,"input_pre_handle_label":label}

        if label== "danger":
            #危险结果：返回标签、危险答案、确认危险、更改危险状态
            return {"input_pre_handle_label":label
                ,"answer_status":ANSWER_STATUS_DANGER
                ,"danger_answer":danger_answer
                ,"is_danger": True,}

        if label== "irrelevant":
            #无关结果：返回标签和理由和预制回答
            return {"input_pre_handle_label":label
                ,"answer_status":ANSWER_STATUS_REFUSE
                ,"refuse_answer":"本问题超出了我的能力范围"}

    #如果症状表为空，就返回空症状表，因为neo4j失效了
    return {"symptoms_list_in_question": []
                , "text_symptom_dict_list": []
                ,"input_pre_handle_label":"normal"}



#输入预处理 路由函数，根据输入预处理的标签，返回对应的节点
def input_pre_handle_router(state:State):
    label = state["input_pre_handle_label"]

    if label== "normal":
        #如果label是normal，就返回输入优化节点
        return NODE_INPUT_GREATER
    if label== "danger":
        #如果label是danger，就返回危险情况处理节点
        return NODE_DANGER_HANDLER
    if label== "irrelevant":
        #如果label是irrelevant，就返回无关处理节点
        return NODE_REFUSE_ANSWER
    #如果label是其他，就直接结束
    return END


#输入优化节点,试着优化用户发送的信息，输出优化后的问题
def input_greater(state:State):

    #==============================PART 0 预处理======================================

    question = state['question']

    #有一些固定的提示词如【别名，俗称，。。。】这类就不做改写处理了
    for alias in alias_transport_white_list:
        if alias in question:
            return {"changed_question":question}

    #如果问题长度太小，不值得做什么纠正，跳过
    if len(question)<2:
        return {"changed_question":question}

    #因为替换相同拼音的病名需要挨个循环匹配，需要确定匹配多少次，所以需要确定匹配的上限，这边就取最长的病名长度为窗口上限
    lens = max([len(key) for key in common_disease_dict.keys()])
    #因为病名最大值就是20
    # standard_top_level=lens if lens>11 else 11
    standard_top_level=lens
    #检查问题在不在alias转化白名单里面，如在，那就跳过PART2别名病名转化

    #=============================PART1 拼音纠正&别名病名转化================================
    pinyin_disease_replace_list=[] #拼音和病名替换列表
    alias_disease_replace_list=[] #别名和病名替换列表

    # 查询我们资料库中(neo4j)存储的所有病名，转化为对应的拼音-病名字典。
    pinyin_disease_map={}
    for disease in disease_list:
        pinyin_disease_map["".join(pypinyin.lazy_pinyin(disease))]=disease

    #top_level就是窗口上限，防止系统错误，question上限是len(question)，上限是standard_top_level
    changed_question=question

    top_level=standard_top_level if len(question)>standard_top_level else len(question)
    #- 每次窗口把问题都扫一遍，如果发现了病表中有完全一样的，那就记录起止位置和问题
    for i in range(top_level+1,0,-1):
        for j in range(0,len(question)-i):
            #获取窗口起止，获取窗口值
            window_start=j
            window_end=i+j
            word=question[window_start:window_end+1]
            #拼音化，和列表匹配
            word_pinyin="".join(pypinyin.lazy_pinyin(word))
            #如果在列表中，在mao中保存位置和替换的词
            if word_pinyin in pinyin_disease_map.keys() and word not in disease_list:
                # print(f"匹配到起点为{window_start}，终点为{window_end}的词{word}拼音和资料中的病名{pinyin_disease_map[word_pinyin]}一致，替换")
                pinyin_disease_replace_list.append((window_start,window_end,pinyin_disease_map[word_pinyin]))

            #进行别名病名转化，如果word在别名表中，要替换为专业病名
            if word in common_disease_dict.keys() and word not in disease_list:
                # print(f"匹配到起点为{window_start}，终点为{window_end}的词{word}在俗称表中，替换")
                alias_disease_replace_list.append((word,common_disease_dict[word]))

    #- 把原始字符串按照dict进行替换，变成新生成的字符串儿
    for start,end,disease_name in pinyin_disease_replace_list:
        changed_question= changed_question[:start] + disease_name + changed_question[end + 1:]
    for old_word,new_word in alias_disease_replace_list:
        changed_question= changed_question.replace(old_word,new_word)
    #ij都是有效的下标

    #=============================PART2 症状词-专业名词转化================================

    text_symptom_dict_list=state["text_symptom_dict_list"]

    #如果res有结果那就狠狠的开始替换原文,并获取问题中的症状列表
    if  text_symptom_dict_list:
        #替换原文，替换为专业的症状词
        for text_symptom_dict in text_symptom_dict_list:
            if text_symptom_dict["text"]:
                changed_question=changed_question.replace(text_symptom_dict["text"],text_symptom_dict["symptom"])

    return {"changed_question":changed_question}

# 第一条链路:关键词检索
def retrieve_by_keyword_node(state:State):
    return {"keyword_res":retrieve_by_keyword(state['changed_question']),"keyword_retrieval_status":True}

# 第二条链路:向量检索
def retrieve_by_embedding_node(state:State):
    
    return {"embedding_res":retrieve_by_embedding(state['changed_question'],10),"embedding_retrieval_status":True}

# 第三条链路:知识图谱检索
def retrieve_by_knowledge_graph_node(state:State):
    
    return {"graph_res": retrieve_by_knowledge_graph(state["changed_question"],state.get("symptoms_list_in_question",None)),"graph_retrieval_status":True}


#依据获取到的doc获取该证据的分数
def get_score(doc,question:str)->int:
    if doc["disease"] in question:
        return 0
    return 1

#处理检索结果,去重,拼贴info
def handle_retrieve_res(state:State):
    #0,如果三路都挂，直接维护一个refuse_answer
    if not state.get("embedding_retrieval_status", True) and not state.get("keyword_retrieval_status",True) and not state.get("graph_retrieval_status",True):
        return {"refuse_answer":"系统超时，请稍后再试","keyword_res":[],"graph_res":[],"info":"","finally_res":[],"file_nos":[]}

    #1,取出两个返回的结果
    embedding_res = state['embedding_res']
    keyword_res = state['keyword_res']
    graph_res = state['graph_res']
    changed_question=state["changed_question"]
    nos = []
    embedding_ids=set()

    #2,制作去重id集合
    for embedding_re in embedding_res:
        embedding_ids.add(embedding_re["id"])

    #TODO这边还需要取一个最小的score

    #3，列表推导式把keyword中在embedding_res中的元素过滤掉，只留下特异性元素，性能更加
    temp_keyword_res=[keyword for keyword in keyword_res if keyword["id"] not in embedding_ids]
    keyword_ids=[]
    for keyword_re in temp_keyword_res:
        keyword_ids.append(keyword_re["id"])

    temp_graph_res=[one_graph for one_graph in graph_res if one_graph["id"] not in embedding_ids and one_graph["id"] not in keyword_ids]
    list_all = embedding_res + temp_keyword_res + temp_graph_res

    #4，docs列表
    for doc in list_all:
        #4.1取出doc的id
        doc_id = doc["id"]
        #4.2求出三路对应的排名,在各路的检索结果里找id等于本id的
        embedding_rank = next((rank for rank, doc in enumerate(embedding_res) if doc["id"] == doc_id), -1)
        keyword_rank = next((rank for rank, doc in enumerate(keyword_res) if doc["id"] == doc_id), -1)
        graph_rank = next((rank for rank, doc in enumerate(graph_res) if doc["id"] == doc_id), -1)
        #4.3根据rrf公司算出rrf分数(60是经验值，直接使用)
        res=0.0
        if embedding_rank!=-1:
            res+=1/(embedding_rank+60)
        if keyword_rank!=-1:
            res+=1/(keyword_rank+60)
        if graph_rank!=-1:
            res+=1/(graph_rank+60)
        doc["rrf_score"]=res

    #4，根据疾病打分重排
    list_all.sort(key=lambda one:(get_score(one, changed_question), -one["rrf_score"] if one.get("rrf_score") else 1))

    # print("去重后的资料为：", list_all)
    # 5,拼贴文本
    info=""

    for index,text in enumerate(list_all):
        #拼  贴带换行，结构化的资料语句
        nos.append(index+1)
        info+=f"\n\n[{index+1}]:【{text['disease']}-{text['title']}】{text['text']}\n\n"
    return {"keyword_res":temp_keyword_res,"graph_res":graph_res,"info":info,"finally_res":list_all,"file_nos":nos}

#定义系统提示词，发送给大模型，取得结果
async def send_to_llm(state:State, runnableConfig:RunnableConfig):
    # raise Exception("安全检查错误")
    info = state['info']
    changed_question = state['changed_question']

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
    
    6,贴出的摘要只能是回答中引用了的！而且要按从小到大依次排好
        
    7，如果检测到用户输入的内容虽然整体无关，但有一定医学名词，那就凭借资料回答，有相关内容就引用，没有就不要引用
    
    8，如果检测到用户输入的问题内容不是很紧急，但是有巨大的安全风险，比如乱喝药，放弃医疗，服用未认证的药等，
    要先推荐用户走向正确的道路，再进行资料方面的回答
    
    9, 遇到以下情况：
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

    #2,模板类拼贴,from_message就是从一系列的结构化消息来初始化这个模板类，指定给llm发送的信息类型
    template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "资料：{info}\n问题：{changed_question}")])

    #3,管道符，把template的输出转化为输入交给llm
    chain=template|qwenModel

    #4,传递invoke
    #资料引用错误，提示(目前只有这一种情况)
    if state.get("citation_status", NORMAL_CITATION)==ERROR_CITATION:
        info+="\n\n[系统提示]注意，你出现了幻觉，引用了不存在的资料编号，请纠正"

    #5，如果retry_count==0，那就走流式，如果retry_count!=0，那就走非流式
    if not state.get('retry_count', 0):
        res_buffer=[]
        #chain才能传入dict，因为chain能填入占位符，普通model只能传个字符串了
        async_res = chain.astream({"info": info, "changed_question": changed_question}, config=runnableConfig)
        #相当于在每次都await等待res
        async for res in async_res:
            if res.content:
                res_buffer+=res.content
        #使用了大模型
        answer = "".join(res_buffer)
    else:
        answer = await chain.ainvoke({"info": info, "changed_question": changed_question}, config=runnableConfig)

    #到了这个节点，就是没有缓存，存入redis
    return {"answer":  answer,
            "retry_count": state.get('retry_count', 0) + 1,
            "answer_status": ANSWER_STATUS_NORMAL,
            "use_llm": True
            }

#验证llm回答的可靠性
def validate_answer(state:State):
    #特殊情况，如果患者是危险情况，可以免去检查，直接宣布NORMAL

    text = state['answer']
    nos = state["file_nos"]
    nums = re.findall(r"\[(\d+)\]", text)

    # print("======================找到的编号如下", set(nums))
    # print("======================正确的编号如下", set(nos))
    #如果nums编号数组为空，说明没有引用任何编号，需要打上标记
    if not nums:
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
    answer += f"\n\n {MEDICAL_DISCLAIMER}\n"
    # print("最终答案：", answer)

    #FastAnswer缓存，只有正常引用的回答才可以进缓存
    if state.get("redis_key") and state.get("citation_status") == NORMAL_CITATION:
        try:
            redis_template.set(state["redis_key"], answer)
        except Exception as e:
            logger.error("FastAnswer缓存操作出错,错误信息:%s",traceback.format_exc())

    return {"answer": answer}

#检验error函数，如果error==ERROR_CITATION，那就返回END,如果不是，那就返回CONTINUE导到下一个节点
def validate_answer_router(state:State):
    citation_status = state.get("citation_status", ERROR_CITATION)
    if citation_status == NO_CITATION:
        return NODE_POST_GUARDRAIL
    elif citation_status == ERROR_CITATION:
        if state.get('retry_count', 0) >= 3:
            return NODE_POST_GUARDRAIL
        return NODE_SEND_TO_LLM
    else:
        return NODE_POST_GUARDRAIL

def refuse_answer_handler(state:State):
    return {"answer": state["refuse_answer"],"answer_status":ANSWER_STATUS_REFUSE}

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
    #先提取问题的病和问法
    disease = abstract_disease_keyword(state['question'])
    question_type = abstract_question_keyword(state['question'])
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
    return NODE_INPUT_PRE_HANDLE

#处理完结果的路由，如果三路都挂，那就拒答
def res_handle_router(state:State):
    if state.get("refuse_answer", None):
        return NODE_REFUSE_ANSWER
    return NODE_SEND_TO_LLM


#如果要快速回答,要给answer生成一些什么
def fast_answer_handler(state:State):
    return {"answer": state["fast_answer"],"answer_status":ANSWER_STATUS_NORMAL}

#================================异常降级：补偿函数区=================================
def input_pre_handle_fall_back(state:State):
    logger.error("输入预处理函数出错,错误信息:%s",traceback.format_exc())
    return {"symptoms_list_in_question": [], "text_symptom_dict_list": []}

def input_greater_fall_back(state:State):
    logger.error("输入优化节点出错,错误信息:%s",traceback.format_exc())
    return {"changed_question":state["question"]}

def embedding_fall_back(state:State):
    logger.error("向量检索节点出错,错误信息:%s",traceback.format_exc())
    return {"embedding_retrieval_status":False,"embedding_res":[]}

def keyword_fall_back(state:State):
    logger.error("关键词检索节点出错,错误信息:%s",traceback.format_exc())
    return {"keyword_retrieval_status":False,"keyword_res":[]}

def graph_fall_back(state:State):
    logger.error("知识图谱检索节点出错,错误信息:%s",traceback.format_exc())
    return {"graph_retrieval_status":False,"graph_res":[]}

def fast_answer_fall_back(state:State):
    logger.error("快速回答节点出错,错误信息:%s",traceback.format_exc())
    return {"fast_answer": None,"redis_key":None}



#整个建图流程：
# 1，根据START创建图
graph = StateGraph(State)
#2，增加所有节点

#制定超时策略
standardRetryPolicy = RetryPolicy(max_attempts=3,
                     initial_interval=2.0,  # 每次间隔
                     backoff_factor=2,  # 间隔惩罚倍数
                     retry_on=(TimeoutError, ConnectionError)
                     )

graph.add_node(NODE_RETRIEVE_KEYWORD,    node_wrapper(retrieve_by_keyword_node,keyword_fall_back))
graph.add_node(NODE_RETRIEVE_EMBEDDING,  node_wrapper(retrieve_by_embedding_node,embedding_fall_back))
graph.add_node(NODE_RETRIEVE_GRAPH,      node_wrapper(retrieve_by_knowledge_graph_node,graph_fall_back))
graph.add_node(NODE_SEND_TO_LLM,         node_wrapper(send_to_llm),retry_policy=standardRetryPolicy)
graph.add_node(NODE_HANDLE_RETRIEVE_RES, node_wrapper(handle_retrieve_res),retry_policy=standardRetryPolicy)
graph.add_node(NODE_VALIDATE_ANSWER,  node_wrapper(validate_answer),retry_policy=standardRetryPolicy)
graph.add_node(NODE_POST_GUARDRAIL,      node_wrapper(post_guardrail),retry_policy=standardRetryPolicy)
graph.add_node(NODE_DANGER_HANDLER,      node_wrapper(danger_situation_handler),retry_policy=standardRetryPolicy)
graph.add_node(NODE_REFUSE_ANSWER,       node_wrapper(refuse_answer_handler),retry_policy=standardRetryPolicy)
graph.add_node(NODE_FAST_ANSWER_HANDLER, node_wrapper(fast_answer_handler),retry_policy=standardRetryPolicy )
graph.add_node(NODE_FAST_ANSWER_JUDGER, node_wrapper(fast_answer_judger,fast_answer_fall_back))
graph.add_node(NODE_INPUT_GREATER, node_wrapper(input_greater,input_greater_fall_back))
graph.add_node(NODE_INPUT_PRE_HANDLE, node_wrapper(input_pre_handle,input_pre_handle_fall_back))

#3，增加所有边
#紧急情况检查优先
graph.add_edge(START, NODE_FAST_ANSWER_JUDGER)
#如果安全检查有问题，到danger_situation_handler处理
#如果安全检查没有问题，到retrieve_by_keyword_node和retrieve_by_embedding_node
graph.add_conditional_edges(NODE_FAST_ANSWER_JUDGER, fast_answer_router)

# graph.add_edge(NODE_INPUT_PRE_HANDLE,NODE_INPUT_GREATER)
graph.add_conditional_edges(NODE_INPUT_PRE_HANDLE,input_pre_handle_router)
#4，尾部连接
graph.add_edge(NODE_INPUT_GREATER,NODE_RETRIEVE_KEYWORD)
graph.add_edge(NODE_INPUT_GREATER,NODE_RETRIEVE_EMBEDDING)
graph.add_edge(NODE_INPUT_GREATER,NODE_RETRIEVE_GRAPH)
graph.add_edge(NODE_RETRIEVE_KEYWORD,    NODE_HANDLE_RETRIEVE_RES)
graph.add_edge(NODE_RETRIEVE_EMBEDDING,  NODE_HANDLE_RETRIEVE_RES)
graph.add_edge(NODE_RETRIEVE_GRAPH,      NODE_HANDLE_RETRIEVE_RES)

graph.add_conditional_edges(NODE_HANDLE_RETRIEVE_RES, res_handle_router)
graph.add_edge(NODE_SEND_TO_LLM,         NODE_VALIDATE_ANSWER)

#如果资料编号有错误，send_to_llm，如果资料编号没有错误，到post_guardrail处理,如果没有引用编号，拒绝回答
graph.add_conditional_edges(NODE_VALIDATE_ANSWER, validate_answer_router)
graph.add_edge(NODE_REFUSE_ANSWER, NODE_POST_GUARDRAIL)
graph.add_edge(NODE_DANGER_HANDLER, NODE_POST_GUARDRAIL)
graph.add_edge(NODE_FAST_ANSWER_HANDLER, END)
graph.add_edge(NODE_POST_GUARDRAIL, END)

builder=graph #未编译的图
graph=graph.compile()




