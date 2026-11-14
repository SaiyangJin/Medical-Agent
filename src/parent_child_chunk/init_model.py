#导入环境变量包
import asyncio
import os


from pathlib import Path
from dotenv import load_dotenv
#导入路径操作类
#引入向量数据库操作包
from langchain_postgres import PGVector
#导入向量模型类
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
#导入sql操作类
from sqlalchemy import (create_engine)

ROOT = Path(__file__).resolve().parents[2]
#链接引擎
DATA_BASE_URL = "postgresql+psycopg://root:123456@localhost:5432/postgres"
engine = create_engine(DATA_BASE_URL)



#加载环境变量
load_dotenv(ROOT / '.env')
#创建向量化模型
embeddingModel = OpenAIEmbeddings(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                                  model="qwen3.7-text-embedding-flash",
                                  api_key=os.environ.get("DASHSCOPE_API_KEY")
                                  ,check_embedding_ctx_length=False
                                  ,chunk_size=10#单次请求最多20次
                                  ,timeout=300)
#制造向量数据库操作对象
pg_vector = PGVector(embeddingModel,
                     connection=DATA_BASE_URL,
                     collection_name="disease_child_chuck",
                     use_jsonb=True,
                     # pre_delete_collection=True #插入之前先删表的元素（开发阶段）
                     )
#创建大语言模型
qwenModel = ChatOpenAI(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                       model="kimi-k3.1-pro", api_key=os.environ.get("DASHSCOPE_API_KEY"),timeout=300000)
backupQwenModel = ChatOpenAI(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                       model="kimi-k3.1-pro", api_key=os.environ.get("DASHSCOPE_API_KEY"),timeout=300000)

async def stream():
    async for chuck in qwenModel.astream("菊池病是什么"):
        print(chuck.content,end="")
if __name__ == '__main__':
    asyncio.run(stream())
