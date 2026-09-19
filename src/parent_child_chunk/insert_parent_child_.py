#把父子插入数据库的脚本

#导入json字符串转化对象包
import json
#导入环境变量包
import os
from dotenv import load_dotenv
#导入路径操作类
from pathlib import Path
#引入向量数据库操作包
from langchain_postgres import PGVector
from langchain_core.documents import Document
#导入向量模型类
from langchain_openai import OpenAIEmbeddings
#导入sql操作类
from sqlalchemy import insert, Table, MetaData,create_engine,select

#当前的根路径
ROOT = Path(__file__).resolve().parents[2]
#父块路径
PARENT_PATH = ROOT / 'data' / 'chunk' / 'parent.jsonl'
#字块路径
CHILD_PATH = ROOT / 'data' / 'chunk' / 'child.jsonl'
#操作表需要的定义容器
meta_data = MetaData()
#链接引擎
DATA_BASE_URL = "postgresql+psycopg://root:123456@localhost:5432/postgres"
engine = create_engine(DATA_BASE_URL)

#加载环境变量
load_dotenv(ROOT / '.env')
#创建向量化模型
embeddingModel = OpenAIEmbeddings(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                                  model="qwen3.7-text-embedding",
                                  api_key=os.environ.get("DASHSCOPE_API_KEY")
                                  ,check_embedding_ctx_length=False
                                  ,chunk_size=20)#单次请求最多20次
#制造向量数据库操作对象
pg_vector = PGVector(embeddingModel,
                     connection=DATA_BASE_URL,
                     collection_name="disease-child-chuck",
                     use_jsonb=True,
                     # pre_delete_collection=True #插入之前先删表的元素（开发阶段）
                     )
#打开文件开始构建父Chunk



#定义表对象
disease_parent_chuck_table = Table("disease_parent_chuck", meta_data, autoload_with=engine)

#这个函数用来测试从问题检索到字块再检索到父块的过程
def find(question:str,k=5):
    #1，根据问题查找子块
    search_res = pg_vector.similarity_search(question, k)
    #2，字块解析出父id，放入set
    parent_ids=set()
    for search_re in search_res:
        #2.1取到父id
        parent_id = search_re.metadata['parent_id']
        parent_ids.add(parent_id)
    #3，sql查询父块，注意加mapping才能形成字典模式,才能按名字去取
    with engine.begin() as conn:
        execute_res = conn.execute(
            select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.id.in_(parent_ids))).mappings()
    #4，解析结果
    return execute_res




if __name__ == '__main__':
    #1,删除旧数据
    with engine.begin() as connection:
        connection.execute(disease_parent_chuck_table.delete())
    #2，定义父块json列表
    parent_chunk_list = []
    #3，开始构建父块
    with open(PARENT_PATH, 'r', encoding='utf-8') as f:
        #现在开始管理数据库连接事务，这个with-as是自动管理事务的逻辑，报错会自动回滚。
        for parent_chunk in f:
            #文件取出父块
            parent_chunk_json = json.loads(parent_chunk)
            #父块json列表添加父块json
            parent_chunk_list.append(parent_chunk_json)
            #但是数据量太大，也要做个截断，到1000条提交一次之类的

                #批量插入，解决性能问题
            if len(parent_chunk_list)>=1000:
                with engine.begin() as connection:
                     connection.execute(insert(disease_parent_chuck_table),parent_chunk_list)
                parent_chunk_list=[]
        #engine是连接池，connect是单个连接，这边自动维护不需要手动销毁/提交链接对象了
        with engine.begin() as connection:
            #独立处理剩下的块表
             connection.execute(insert(disease_parent_chuck_table),parent_chunk_list)
            #用with engine.begin() as connection:那个语法，会自动commit事务

    child_chunk_list = []
    #2，打开文件开始构建子Chunk
    #处理字块的时候不需要考虑事务，因为模块帮我们处理好了

    with open(CHILD_PATH, 'r', encoding='utf-8') as f:
        for child_chuck in f:
            #把line的文本拿出备用(一line就是一个疾病，然后需要对文本进行切割为大小块)
            child_chuck_json = json.loads(child_chuck)
            child_chunk_list.append(Document(page_content=child_chuck_json["disease"]+"-"+child_chuck_json["title"]+":"+child_chuck_json["text"]
                                              ,metadata={
                                                "disease":child_chuck_json["disease"],
                                                "revision":child_chuck_json["revision"],
                                                "title":child_chuck_json["title"],
                                                "parent_id":child_chuck_json["parent_id"],
                                              },id=child_chuck_json["id"]))
            #到达1000条，批量插入一次
            if len(child_chunk_list)>=1000:
                pg_vector.add_documents(child_chunk_list,ids=[child.id for child in child_chunk_list])
                child_chunk_list=[]
        #插入剩余的数据
        pg_vector.add_documents(child_chunk_list,ids=[child.id for child in child_chunk_list])