from content_retrieve_graph import retrieve_by_keyword,retrieve_by_embedding,retrieve_by_knowledge_graph

if __name__ == '__main__':
    question = "患者无法正常辨别某些颜色，最常见的是红绿色觉异常。多数为先天性遗传，因视锥细胞中的感光色素缺失或功能异常所致，男性发病率显著高于女性"


    graph_res = retrieve_by_knowledge_graph(
        question)
    graph_res.sort(key=lambda one:one["score"])



    embed_res = retrieve_by_embedding(
        question)
    embed_res.sort(key=lambda one:one["score"])




    keyword_res = retrieve_by_keyword(
        question)
    keyword_res.sort(key=lambda one:one["score"])

    print(f"以下是问题:{question}的三路召回结果，本问题偏向于:知识图谱路线")
    print("知识图谱路线:",[res["score"] for res in graph_res])
    print("向量检索路线:",[res["score"] for res in embed_res])
    print("关键词检索路线",[res["score"] for res in keyword_res])

