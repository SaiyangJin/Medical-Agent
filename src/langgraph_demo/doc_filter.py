from src.parent_child_chunk.content_retrieve import retrieve_by_embedding, retrieve_by_keyword, \
    retrieve_by_knowledge_graph
#根据文本和距离，过滤doc_list的方法

distance_limit=0.5
text_len_limit=20
def filter_docs(doc_list:list):
    doc_list=[doc for doc in doc_list if doc["score"]<distance_limit and len(doc['text'])>text_len_limit]
    print(f"去重之后的docs,总量{len(doc_list)},如下:{[[doc['id'],doc['disease']+'|'+doc['title'],doc['score']] for doc in doc_list]}")



if __name__ == '__main__':
    question="我吞咽困难"
    embedding_res = retrieve_by_embedding(question)
    keyword_res = retrieve_by_keyword(question)
    embedding_ids = set()
    #2,制作去重id集合
    for embedding_re in embedding_res:
        embedding_ids.add(embedding_re["id"])


    #TODO这边还需要取一个最小的score
    #3，列表推导式把keyword中在embedding_res中的元素过滤掉，只留下特异性元素，性能更加
    keyword_res=[keyword for keyword in keyword_res if keyword["id"] not in embedding_ids]
    keyword_ids = set()
    for keyword_re in keyword_res:
        keyword_ids.add(keyword_re["id"])

    # print("去重后的资料为：", keyword_res)

    list_all = embedding_res + keyword_res
    print(f"去重之前的docs,总量{len(list_all)},如下:{[[doc['id'],doc['disease']+'|'+doc['title'],doc['score']] for doc in list_all]}")
    filter_docs(list_all)

