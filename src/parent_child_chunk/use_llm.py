#用来测试模型的调用

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
#导入自定义检索模块
from src.parent_child_chunk.insert_parent_child_ import find
#自定义提示词模版类，拼贴提示词
from langchain_core.prompts import ChatPromptTemplate
import json
#加载环境变量(解析出本文件路径，然后获取决定路径，往上进一级,拼贴.env获取到env文件)
load_dotenv(Path(__file__).resolve().parents[2] / '.env')
#已经进入到os.env里面了,可以直接拿

#导入ChatOpenAi类，创建大模型对象
qwenModel = ChatOpenAI(base_url="https://ws-8v7hg43jappdrllz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                       model="qwen3.8-max", api_key=os.environ.get("DASHSCOPE_API_KEY"))

#方法：输出原始(标题-qid)的元组
def dirty_data_clean():
    with open("data/raw/pages.jsonl", encoding="utf-8") as f:
        titles = [(json.loads(line)["title"],json.loads(line)["qid"]) for line in f if line.strip()]
        print(titles)


#方法：使用模型
def use_model(question:str):

    text_list = find(question, 1)
    #1，定义系统提示词
    SYSTEM_PROMPT = "你是一个医疗咨询助手，你要根据我提供给你的已有的资料回答问题，不要根据自己的记忆回答，如果没有相关资料，回答不知道"
    #2,模板类拼贴,from_message就是从一系列的结构化消息来初始化这个模板类
    template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "资料：{info}\n问题：{question}")])
    #3,管道符，把template的输出转化为输入交给llm
    chain=template|qwenModel
    #4.1,调用对象的invoke函数，获取到资料结果集
    #4.2,拼贴资料语句
    info=""
    for text in text_list:
        #拼贴带换行，结构化的资料语句
        info+=f"\n\n【{text['disease']}-{text['title']}】{text['text']}\n\n"
    #5,传递invoke
    print(
        info
    )
    res = chain.invoke({"info": info, "question": question})
    print(res)

if __name__=='__main__':
    use_model("腦血管事故")


