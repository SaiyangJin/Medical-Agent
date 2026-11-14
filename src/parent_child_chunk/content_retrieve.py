import time
from typing import Any
from collections import defaultdict
import jieba
import rank_bm25
from sqlalchemy import Table, MetaData
import datetime
from sqlalchemy import select

from src.langgraph_demo.langgraph_demo_graph_constant import whole_symptoms_list
from src.parent_child_chunk.content_retrieve_constant import ABSTRACT_SYMPTOM_PROMPT
from src.parent_child_chunk.insert_parent_child_ import disease_parent_chuck_table

import json

from src.parent_child_chunk.init_model import engine, pg_vector

import time
from src.data_graph.neo4j_init import neo4j_driver
from src.parent_child_chunk.init_model import qwenModel

#这个函数用来测试从问题检索到字块再检索到父块的过程
#k的含义是，根据问题，返回k个最相关的子块
def retrieve_by_embedding(question:str,k=5)->list:
    embedding_limit_number=1
    #1，根据问题查找子块，返回distance得分，越小越相关
    search_res = pg_vector.similarity_search_with_score(question, k)
    #2，字块解析出父id和score，放入对应的set
    best_score_parent_ids_dict:dict[str,float]={}
    for search_re,score in search_res:
        #2.1取到父id
        if score>embedding_limit_number:
            continue
        parent_id = search_re.metadata['parent_id']
        #2.2找到对应list的父块,如果不在里面，直接加入
        if not parent_id in  best_score_parent_ids_dict.keys():
            best_score_parent_ids_dict[parent_id]=score
        else:
            #2.3如果在里面，比较score，如果score更小，加入到里面
            if score<best_score_parent_ids_dict[parent_id]:
                best_score_parent_ids_dict[parent_id]=score
    parent_ids = list(best_score_parent_ids_dict.keys())
    parent_ids.sort(key=lambda one:best_score_parent_ids_dict[one])
    #3,best_score_parent_ids_dict字典依据score来排,越小越靠前
    #4,传入dict，通过数据库查询父块
    docs = find_parent_chuck_by_parent_ids(best_score_parent_ids_dict)
    return docs

#关键词检索到父块的函数，根据bm2.5的排名，确定最终的父块
def retrieve_by_keyword(question:str)-> list:
    keyword_limit_number=1
    langchain_pg_embedding_table = Table('langchain_pg_embedding', MetaData(), autoload_with=engine)
    #分好的关键词列表，用于建立倒排索引
    child_chunk_documents=[]
    #父id列表（和关键词一一对应）
    child_chunk_parentids_res=[]
    #1.1查出所有子块数据
    select_statement = select(langchain_pg_embedding_table.c.id, langchain_pg_embedding_table.c.document,
                              langchain_pg_embedding_table.c.cmetadata)
    with engine.begin() as connect:
        res = connect.execute(select_statement).mappings()
    #1.2处理子块数据列表，保存到结果集（一个是分好的关键词，一个是对应的metadata，要根据关键词分出的id，回查metadata）
    for one_res in res.all():
        #1.2.1子块的文本数据和metadata
        document = one_res["document"]
        metadata = one_res["cmetadata"]["parent_id"]
        #1.2.2把子块切割好
        child_chunk_documents.append(jieba.lcut(document))
        child_chunk_parentids_res.append(metadata)
    #2，关键词检索逻辑，最终制作出parent_id_score映射表
    #2.1，用切割好的子块列表建索引(倒排索引)
    bm25 = rank_bm25.BM25Okapi(child_chunk_documents)
    #2.2，然后根据问题切分打分
    #2.3，返回结果列表
    scores = bm25.get_scores(jieba.lcut(question))
    #2.4立刻制作parent_id_score列表，防止下标错误，后续排名能瞬间取出parent_id
    parent_id_score_list=[]
    for index,score in list(enumerate(scores)):
        parent_id_score_list.append((child_chunk_parentids_res[index],score))

    parent_ids=set()
    #3，处理parent_id_score列表，获取到最终的结果
    #3.1过滤score太小的
    parent_id_score_list_temp = list(filter(lambda one:one[1]>keyword_limit_number,list(parent_id_score_list)))
    #3.2按照score排序
    parent_id_score_list_temp.sort(key=lambda one: one[1], reverse=True)
    #3.3取parentids，直到parentids满10个
    for parent_id_score in parent_id_score_list_temp:
        if len(parent_ids)>=10:
            break
        parent_ids.add(parent_id_score[0])

    return find_parent_chuck_by_parent_ids(list(parent_ids))

#知識图谱检索，根据问题空的症状表现--病名--父块ids--
#传入的symptoms_list_in_question是问题中的症状词列表，如果有symptoms_list_in_question就不用走llm
def retrieve_by_knowledge_graph(question:str,symptoms_list_in_question:list=None)->list:
    disease_count_dict=defaultdict(int)
    #判断list是否为none，如果是none，走老检索逻辑不然就直接使用
    if symptoms_list_in_question is None:
        # 1,先通过llm提取出用户问题的症状
        # 1.1编写提示词
        SYSTEM_PROMPT = ("请在如下用户的问题中提取出症状:" +"\n" + question + "\n"
                         +"""
            注意,提取的症状只能按照如下的表来提取,提取的症状需要在下面找到对应意思的词,输出找到的词,返回格式是这样的json:["症状1","症状2"]
            如果没有任何症状，返回[]
            输出纯文本即可，不要输出其他内容，系统会解析
            列表如下:
            """ +','.join(whole_symptoms_list))

        res = qwenModel.invoke(SYSTEM_PROMPT)

        #提取到的症状如[{"text":"头昏沉沉的","symptom":"头晕"}]
        res_list = json.loads(res.content)
        symptoms_list_in_question=list(set(res_list))
    if not symptoms_list_in_question:
        return []

    #2,通过neo4j图数据库检索到病名
    neo4j_diseases_res = neo4j_driver.execute_query(
        "MATCH (n:DISEASE )-[p:HAS_SYMPTOM]->(m:SYMPTOM) where m.name in $symptoms_list return n.name as name,count(m) as hit order by hit desc ",
        symptoms_list=symptoms_list_in_question).records
    #

    #返回一个字典，在neo4j结果直接取病名，然后计数加hit，得到病名-统计表
    disease_count_dict={neo4j_diseases_re["name"]:neo4j_diseases_re["hit"] for neo4j_diseases_re in neo4j_diseases_res}
    disease_list = list(disease_count_dict.keys())
    #如果数据库内没有匹配的病，那就返回none
    if not disease_list:
        return []
    #3,通过病名查询出父块资料的ids(注意，一个病名有多个父块)
    with (engine.begin() as connect):

        parent_id_list = connect.execute(select(disease_parent_chuck_table.c.id)
                                         .where(disease_parent_chuck_table.c.disease.in_(disease_list))
                                         ).scalars().all()

    #4,有了disease_list，获取到对应的父块资料的，但是由于一个病只能有一条父块上桌，所以需要比出这个病的最小score的doc

    disease_doc_dict={}#key是病，val是score
    disease_id_dict={}#存ids
    #{"中风1":0.434，“中风2”:0.32}
    lists = get_doc_with_score_by_parent_id_list(parent_id_list, question)
    #lists内容是:[[“id”,"disease","title","text","revision","score"]]
    # lists.sort(key=lambda d: d["score"])
    for doc in lists:
        #如果doc的score小于dict中的score
        if doc["score"]<disease_doc_dict.get(doc["disease"],99999999.0):
            disease_doc_dict[doc["disease"]]=doc["score"]
            disease_id_dict[doc["disease"]]=doc["id"]
    #取出最终的父块(带score)
    res_doc_list = [doc for doc in lists if doc["id"] in list(disease_id_dict.values())]

    #5，排序，第一层是病名统计数，第二层是score
    res_doc_list.sort(key=lambda res_doc:(-disease_count_dict[res_doc["disease"]],res_doc["score"]))


    return res_doc_list

#传入父块ids，单父块找到 对应子块们和问题匹配的最小score 作为 父块的score
def get_doc_with_score_by_parent_id_list(parent_id_list: list[Any], question: str) -> list:
    #没有父块资料，返回none
    if not parent_id_list:
        return []
    # 根据parent_id_list查询对应的子块向量得分（要最小的得分）
    # 这边k要设置很大哦，限制了返回几个字段
    search_res_list = pg_vector.similarity_search_with_score(question, k=10000, filter={
        "parent_id": {
            "$in": parent_id_list
        }
    })
    # 里面是元组，[Document[id,metadata,page-content],score]
    """
        (Document(id='Q4198677-0-0',
    metadata={
        'title': '介绍',
        'disease': '糖尿病并发症',
        'revision': 91938652,
        'parent_id': 'Q4198677-0'
    },
    page_content='糖尿病并发症-介绍: xxx'),
    0.41879749298095703),
    """
    # 4,解析search_res,制作为一个dict，key是parent_id，value是最小的score（因为要做最小值判断，所以不直接用列表表达式）
    parent_id_score_dict = {}
    # 4.1循环遍历search_res（元组遍历更方便）
    for search_res, score in search_res_list:
        # 4.2拿到metadata的parent_id，
        parent_id = dict(search_res)["metadata"]["parent_id"]
        # 仅当parent不存在，或者原本的score比这个score大的时候，赋值score
        parent_id_score_dict[parent_id] = score if parent_id_score_dict.get(parent_id) is None else min(score,
                                                                                                        parent_id_score_dict.get(
                                                                                                            parent_id))
    # print(parent_id_score_dict)=={'Q4198677-0': 0.41879749298095703, 'Q12202-5': 0.6046279966831207, 'Q2711291-4': 0.6915164177705987}
    # 4.2调用相应函数组装带score的父块数据
    return find_parent_chuck_by_parent_id_scores(parent_id_score_dict)

#通过ParentIds和score获取到数据库查询对应的父块
def find_parent_chuck_by_parent_id_scores(best_score_parent_ids:dict)->list:
    #1,先将dict的key转换为list，批量查询父块。
    with (engine.begin() as conn):
        execute_res = conn.execute(
            select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.id.in_(best_score_parent_ids.keys()))
        ).mappings()
    res=[]
    #2,根据父块id来查找best_score_parent_ids对应的score，加入到dict里面,返回结果
    for execute_re in execute_res:
        execute_re_dict = dict(execute_re)
        execute_re_dict["score"]=best_score_parent_ids[execute_re["id"]] if execute_re["id"] in best_score_parent_ids else 0.99
        res.append(execute_re_dict)
    return res

#通过ParentIds到数据库查询对应的父块，同时按照传入的parentids顺序排序
def find_parent_chuck_by_parent_ids(parent_ids) -> list:
    #1,给parentids贴顺序号
    id_index_dict_list = {id: index for index, id in enumerate(parent_ids)}

    #2,执行查询
    with (engine.begin() as conn):
        execute_res = conn.execute(
            select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.id.in_(parent_ids))
        ).mappings()
        res=[]
        for execute_re in execute_res:
            #因为返回的是row-mapping对象，需要转化为py的dict
            res.append(dict(execute_re))
    # 3,按照传入顺序排序
    res.sort(key=lambda re:id_index_dict_list[re["id"]])
    return res

if __name__ == '__main__':
    # retrieve_by_keyword("我怎么脑子发涨，浑身无力的呀！")
    retrieve_by_knowledge_graph("我怎么脑子发涨，浑身无力的呀！")