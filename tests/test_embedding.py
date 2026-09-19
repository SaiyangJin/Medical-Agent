#DEMO：把清洗好的数据插入向量化数据库，test方法，没有父子块，就是全量插入
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
#引入向量数据库操作包
from langchain_postgres import PGVector

ROOT = Path(__file__).resolve().parents[2]

if __name__ == '__main__':
    # 1，加载环境变量(解析出本文件路径，然后获取决定路径，往上进一级,拼贴.env获取到env文件)
    load_dotenv(ROOT / '.env')
    # 2. 创建向量化模型
    embeddingModel = OpenAIEmbeddings(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                                      model="qwen3.7-text-embedding",
                                      api_key=os.environ.get("DASHSCOPE_API_KEY"),check_embedding_ctx_length=False)
    #3，把清理好的数据插入向量化数据库
    #3.1制造数据库对象
    pg_vector = PGVector(embeddingModel,connection="postgresql+psycopg://root:123456@localhost:5432/postgres", collection_name="disease-embedding-test", use_jsonb=True)
    #3.2打开文件
    with open(ROOT / 'data' / 'cleaned'/'full.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            #转化为字典
            lineDic = json.loads(line)
            #插入向量数据库需要文本，附加数据（疾病名，修订版本，父块id），自定义的id
            texts = pg_vector.add_texts(texts=[lineDic["text"]], metadatas=[{"disease":lineDic["disease"], "revision":lineDic["revision"]}],
                                        ids=[lineDic["id"]])
            print(texts)
            break

