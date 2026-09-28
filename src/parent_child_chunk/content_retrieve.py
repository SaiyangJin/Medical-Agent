import time

from sqlalchemy.engine.result import MappingResult
from sqlalchemy import select
from src.parent_child_chunk.init_model import engine, pg_vector
from src.parent_child_chunk.insert_parent_child_ import disease_parent_chuck_table
import jieba
import rank_bm25
from sqlalchemy import Table, MetaData



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
        if not parent_id in best_score_parent_ids_dict.keys():
            best_score_parent_ids_dict[parent_id]=score
        else:
            #2.3如果在里面，比较score，如果score更小，加入到里面
            if score<best_score_parent_ids_dict[parent_id]:
                best_score_parent_ids_dict[parent_id]=score
    #3,传入dict，通过数据库查询父块
    return find_parent_chuck_by_parent_id_scores(best_score_parent_ids_dict)

#关键词检索到父块的函数
def retrieve_by_keyword(question:str)-> list:

    keyword_limit_number=1
    langchain_pg_embedding_table = Table('langchain_pg_embedding', MetaData(), autoload_with=engine)
    #分好的关键词列表，用于建立倒排索引
    child_chunk_keyword_res=[]
    #父id列表（和关键词一一对应）
    child_chunk_metadata_res=[]
    #1.1查出所有子块数据
    select_statement = select(langchain_pg_embedding_table.c.id, langchain_pg_embedding_table.c.document,
                              langchain_pg_embedding_table.c.cmetadata)
    with engine.begin() as connect:
        res = connect.execute(select_statement).mappings()
    #1.2处理子块数据列表，保存到结果集（一个是分好的关键词，一个是对应的metadata，要根据关键词分出的id，回查metadata）
    for one_res in res.all():
        #1.2.1子块的文本数据和metadata
        document = one_res["document"]
        metadata = one_res["cmetadata"]
        #1.2.2把子块切割好
        child_chunk_keyword_res.append(jieba.lcut(document))
        child_chunk_metadata_res.append(metadata)
    #2，关键词检索，返回distance得分，越小越相关
    #2.1，用切割好的子块列表建索引(倒排索引)
    bm25 = rank_bm25.BM25Okapi(child_chunk_keyword_res)
    #2.2，然后根据问题切分打分
    #2.3，返回结果列表
    scores = bm25.get_scores(jieba.lcut(question))
    #2.3.1先number化scores，获取下标,然后调用数组的排序方法，然后翻转，形成从大到小的下标数组
    #TODO 这个5还要测。

    #这边过滤掉关键词匹配度打分小于1的垃圾数据
    #是下标对score的数组（0,5.43），（1,5.23）这类的
    score_index_list = list(filter(lambda one:one[1]>keyword_limit_number,list(enumerate(scores))))
    #把这个数组用score（就是one[1]）进行降序排列
    score_index_list.sort(key=lambda one: one[1], reverse=True)
    #2.3.1获取五个最相关的子块的下标
    #parentid数据
    parent_id_list=[]
    for e in score_index_list[:5]:
        index_in_chuck = e[0]
        #json.load是文件转json，json.loads是字符串转字典
        parent_id_list.append(child_chunk_metadata_res[index_in_chuck]["parent_id"])
    # end_time = time.time()
    # print("关键词检索耗时：", end_time - start_time, "秒")

    #3，根据parent_id_list查询对应的子块向量得分（要最小的得分）
    #这边k要设置很大哦，限制了返回几个字段
    search_res_list = pg_vector.similarity_search_with_score(question,k=10000,filter={
        "parent_id":{
            "$in":parent_id_list
        }
    })
    #里面是元组，[Document[id,metadata,page-content],score]
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
    #4,解析search_res,制作为一个dict，key是parent_id，value是最小的score（因为要做最小值判断，所以不直接用列表表达式）
    parent_id_score_dict = {}
    #4.1循环遍历search_res（元组遍历更方便）
    for search_res,score in search_res_list:
        #4.2拿到metadata的parent_id，
        parent_id=dict(search_res)["metadata"]["parent_id"]
        #仅当parent不存在，或者原本的score比这个score大的时候，赋值score
        parent_id_score_dict[parent_id]=score if parent_id_score_dict.get(parent_id)==None else min(score,parent_id_score_dict.get(parent_id))
    #print(parent_id_score_dict)=={'Q4198677-0': 0.41879749298095703, 'Q12202-5': 0.6046279966831207, 'Q2711291-4': 0.6915164177705987}
    #4.2调用相应函数组装带score的父块数据
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

#通过ParentIds到数据库查询对应的父块
def find_parent_chuck_by_parent_id(parent_ids) -> list:
    with (engine.begin() as conn):
        execute_res = conn.execute(
            select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.id.in_(parent_ids))
        ).mappings()
        res=[]
        for execute_re in execute_res:
            res.append(dict(execute_re))
    # 4，解析结果
    return res

if __name__ == '__main__':
    # retireve_by_embedding("缺氧")
    keyword = retrieve_by_keyword("糖尿病是什么")
    print(keyword)
    # print("向量搜索",retireve_by_embedding("CVI是什么").all())
    # print("关键词搜索",keyword_search("CVI是什么").all())