import time

from sqlalchemy.engine.result import MappingResult
from sqlalchemy import select
from src.parent_child_chunk.init_model import engine, pg_vector
from src.parent_child_chunk.insert_parent_child_ import disease_parent_chuck_table
import jieba
import rank_bm25
from sqlalchemy import Table, MetaData



#这个函数用来测试从问题检索到字块再检索到父块的过程
def retrieve_by_embedding(question:str,k=5)->list:
    embedding_limit_number=1
    #1，根据问题查找子块
    search_res = pg_vector.similarity_search_with_score(question, k)
    #2，字块解析出父id，放入set
    parent_ids=set()
    for search_re,score in search_res:
        #2.1取到父id
        if score>embedding_limit_number:
            continue
        parent_id = search_re.metadata['parent_id']
        parent_ids.add(parent_id)
    #3，sql查询父块，注意加mapping才能形成字典模式,才能按名字去取
    return find_parent_chuck_by_parent_id(parent_ids)

def retrieve_by_keyword(question:str)-> list:
    # start_time = time.time()

    keyword_limit_number=1
    langchain_pg_embedding_table = Table('langchain_pg_embedding', MetaData(), autoload_with=engine)
    child_chunk_keyword_res=[]
    child_chunk_parent_id_res=[]
    #1.1用小select定义一张表变成大Select，然后才能执行查询的api
    select_statement = select(langchain_pg_embedding_table.c.id, langchain_pg_embedding_table.c.document,
                              langchain_pg_embedding_table.c.cmetadata)
    #1.2查询按列查询，查到一个数据列表
    with engine.begin() as connect:
        res = connect.execute(select_statement).mappings()
    #1.3处理数据列表，保存到结果集（一个是分好的关键词，一个是对应的metadata，要根据关键词分出的id，回查metadata）
    for one_res in res.all():
        #1.3.1子块的文本数据和metadata
        document = one_res["document"]
        metadata = one_res["cmetadata"]
        #1.3.2存储一条数据处理后结果
        child_chunk_keyword_res.append(jieba.lcut(document))
        child_chunk_parent_id_res.append(metadata)
    #2，问题分词，bm25打分
    #2.1，用你建好的块列表建索引(倒排索引)
    bm25 = rank_bm25.BM25Okapi(child_chunk_keyword_res)
    #2.2，然后根据问题切分打分
    scores = bm25.get_scores(jieba.lcut(question))
    #2.3，返回结果列表
    #2.3.1先number化scores，获取下标,然后调用数组的排序方法，然后翻转，形成从大到小的下标数组
    #TODO 这个5还要测。
    score_index_list = list(filter(lambda one:one[1]>keyword_limit_number,list(enumerate(scores))))
    score_index_list.sort(key=lambda entry: entry[1], reverse=True)
    #2.3.1获取五个最相关的子块的下标
    #parentid数据
    parent_id_list=[]
    for e in score_index_list[:5]:
        index_in_chuck = e[0]
        #json.load是文件转json，json.loads是字符串转字典
        parent_id_list.append(child_chunk_parent_id_res[index_in_chuck]["parent_id"])
    # end_time = time.time()
    # print("关键词检索耗时：", end_time - start_time, "秒")
    return find_parent_chuck_by_parent_id(parent_id_list)


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
    retrieve_by_keyword("糖尿病是什么")
    # print("向量搜索",retireve_by_embedding("CVI是什么").all())
    # print("关键词搜索",keyword_search("CVI是什么").all())