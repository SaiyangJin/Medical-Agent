#用来测试模型的调用

#导入自定义检索模块
from src.parent_child_chunk.content_retrieve import retrieve_by_embedding,retrieve_by_keyword
#自定义提示词模版类，拼贴提示词
from langchain_core.prompts import ChatPromptTemplate
import json

from src.parent_child_chunk.init_model import qwenModel


#已经进入到os.env里面了,可以直接拿

#导入ChatOpenAi类，创建大模型对象


#方法：输出原始(标题-qid)的元组
def dirty_data_clean():
    with open("data/raw/pages.jsonl", encoding="utf-8") as f:
        titles = [(json.loads(line)["title"],json.loads(line)["qid"]) for line in f if line.strip()]
        print(titles)


#方法：使用模型
def use_model(question:str):
    embedding_res = retrieve_by_embedding(question, 5).all()
    keyword_res = retrieve_by_keyword(question).all()
    print("本次向量检索的资料是：", embedding_res)
    print("本次关键字检索的资料是：", keyword_res)
    #0,检索去重
    duplicate_id=set()
    for embedding_re in embedding_res:
        duplicate_id.add(embedding_re["id"])
    # keyword_res=filter(lambda  keyword_re:keyword_re["id"] not in duplicate_id,keyword_res)
    #0.1列表推导式去重，性能更加
    keyword_res=[keyword for keyword in keyword_res if keyword["id"] not in duplicate_id]
    #1，定义系统提示词
    SYSTEM_PROMPT = "你是一个医疗咨询助手，你要根据我提供给你的已有的资料回答问题，不要根据自己的记忆回答，如果没有相关资料，回答不知道"
    #2,模板类拼贴,from_message就是从一系列的结构化消息来初始化这个模板类
    template = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "资料：{info}\n问题：{question}")])
    #3,管道符，把template的输出转化为输入交给llm
    chain=template|qwenModel
    #4.1,调用对象的invoke函数，获取到资料结果集
    #4.2,拼贴资料语句
    info=""
    list_all = embedding_res + keyword_res
    print("去重后的资料为：", list_all)
    for text in list_all:
        #拼  贴带换行，结构化的资料语句
        info+=f"\n\n【{text['disease']}-{text['title']}】{text['text']}\n\n"
    #5,传  递invoke
    res = chain.invoke({"info": info, "question": question})
    print(res)

if __name__=='__main__':
    use_model("糖尿病是什么")


