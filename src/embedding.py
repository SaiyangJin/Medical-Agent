#真正的，开始切割父子Chuck的脚本
#DEMO：把清洗好的数据插入向量化数据库
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
#引入向量数据库操作包
from langchain_postgres import PGVector

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    # 1，加载环境变量(解析出本文件路径，然后获取决定路径，往上进一级,拼贴.env获取到env文件)
    load_dotenv(ROOT / '.env')
    # 2. 创建向量化模型
    embeddingModel = OpenAIEmbeddings(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                                      model="qwen3.7-text-embedding",
                                      api_key=os.environ.get("DASHSCOPE_API_KEY"),check_embedding_ctx_length=False)
    #3，父子块
    #3.1制造数据库对象
    pg_vector = PGVector(embeddingModel,connection="postgresql+psycopg://root:123456@localhost:5432/postgres", collection_name="disease-child-chuck", use_jsonb=True)
    #3.2打开文件开始构建父子Chuck
    with open(ROOT / 'data' / 'cleaned'/'full.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            #把line的文本拿出备用(一line就是一个疾病，然后需要对文本进行切割为大小块)
            lineDic = json.loads(line)
            text = lineDic["text"]
            #先切割为大块

            #转化为字典
            #插入数据库
            texts = pg_vector.add_texts(texts=[lineDic["text"]], metadatas=[{"disease":lineDic["disease"], "revision":lineDic["revision"]}],
                                        ids=[lineDic["id"]])
