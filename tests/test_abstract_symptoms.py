from src.parent_child_chunk.init_model import engine
from src.parent_child_chunk.insert_parent_child_ import disease_parent_chuck_table
from sqlalchemy import select
from src.parent_child_chunk.init_model import qwenModel

def test():
    diseases=["缺氧","失溫症","中風"]

    with engine.begin() as conn:
        res = conn.execute(
            select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.disease.in_(diseases))).all()
    info=""
    for row in res:
        #row是rowMapping对象
        info += "\n".join([row.title + "\n" + row.text for row in res])
    #拼贴info，就是把row.title做标题和row.text作为文本拼贴起来

    res = qwenModel.invoke(
        "下面我会给你一些段落，请在谈及‘症状’、‘临床表现’等的段落中抽取症状。\n如果发现段落描述的是历史，研究，人文等内容的，请跳过。回答只需要一张列表，如['发热','呕吐']这样的，其他不要回答，分疾病回答:\n" + info)
    print(res.content)