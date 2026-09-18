import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


if __name__=='__main__':
    #1，加载环境变量(解析出本文件路径，然后获取决定路径，往上进一级,拼贴.env获取到env文件)
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    #已经进入到os.env里面了,可以直接拿

    #2，导入ChatOpenAi类，创建大模型对象
    qwenModel = ChatOpenAI(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                           model="qwen3.8-max", api_key=os.environ.get("DASHSCOPE_API_KEY"))
    #3，调用对象的invoke函数，获取到结果
    invoke = qwenModel.invoke("你好")
    print(invoke)


