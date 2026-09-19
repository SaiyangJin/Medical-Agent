#批量清洗真实数据的脚本

#把拉取好的原始数据，一个个遍历，清洗，然后追加到新文件/cleaned/whole.json里面，里面是{"text":"xxxxx"}这样的
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_PATH = ROOT / "data" / "cleaned" / "full.jsonl"
SOURCE_PATH = ROOT / "data" / "raw" / "pages.jsonl"
BLOCK_PATH = ROOT / "data" / "garbage" / "garbage_qid.txt"


# 方法：传入原始内容，返回清洗后的内容
def clean_wikitext(raw: str) -> str:
    """把维基 wikitext 洗成纯文本。

    保留 == 章节标题 ==（后面切块要用），其余标记全清掉。
    """
    # 1. HTML 注释
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    # 2. {{模板}} —— 循环剥皮，每轮只剥最内层，直到没有变化
    while True:
        new = re.sub(r"\{\{[^{}]*}}", "", raw)
        if new == raw:
            break
        raw = new

    # 3. <ref>引用</ref>（内容常跨行，必须 DOTALL）
    raw = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<ref[^>]*/>", "", raw)          # 自闭合的 <ref name="x"/>

    # 4~6. 图片 / 分类 / 跨语言链接
    #      必须在普通链接[[A|B]]之前处理，否则会被误当成正文链接，
    #      留下 "thumb|说明" 这种垃圾碎片
    raw = re.sub(r"\[\[(?:File|Image|文件|檔案):[^\[\]]*]]", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\[\[(?:Category|分类|分類):[^\[\]]*]]", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\[\[[a-z]{2}(?:-[a-z]+)?:[^\[\]]*]]", "", raw)   # 如 [[en:Diabetes]]

    # 7. 外部链接 [http://xxx 显示文字] -> 显示文字
    raw = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", raw)
    raw = re.sub(r"\[https?://\S+\]", "", raw)     # 没有显示文字的，整条删

    # 8~9. 内部链接（顺序不能反：带竖线的必须先跑）
    raw = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", raw)
    raw = re.sub(r"\[\[([^\]]*)\]\]", r"\1", raw)

    # 10. 剩余 HTML 标签（注意收尾的 > ，缺了会吞掉半篇文章）
    raw = re.sub(r"<[^>]+>", "", raw)

    # 11. 表格 {| ... |}
    raw = re.sub(r"\{\|.*?\|\}", "", raw, flags=re.DOTALL)

    # 12. 粗体 / 斜体标记
    raw = raw.replace("'''", "").replace("''", "")

    # 13. HTML 实体
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"')]:
        raw = raw.replace(a, b)

    # 14. 压缩空白
    raw = re.sub(r"[ \t]{2,}", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)

    return raw.strip()


if __name__ == '__main__':
    #放垃圾数据
    block_qids=set([])
    #0，存入垃圾数据id
    with open(BLOCK_PATH,"r",encoding="utf-8") as f:
        for line in f:
            block_qids.add(line.strip())
    #1，循环遍历，先拿到pages.jsonl里边的一个字典
    #1.1开文件,先开写入文件，

    #TARGET_PATHSOURCE_PATH是目录，这样算才对
    with open(TARGET_PATH,"w",encoding='utf-8') as f1:
        with open(SOURCE_PATH,'r',encoding='utf-8') as f:
            for line in f:
                #1.2新建一个json，把属性追加到这个json里边，原始数据要清洗哦

                #line是字符串，要先解析成字典
                jsonLine = json.loads(line)
                #1.3去除垃圾数据
                qid = jsonLine['qid']
                if block_qids and qid in block_qids:
                    continue
                jsonNew={
                    "text":clean_wikitext(jsonLine['wikitext']),
                    "disease":jsonLine['title'],
                    "revision":jsonLine['revision'],
                    "id": qid
                }
                #1.4把json写到jsons里边去
                #jsonNew是字典，转成字符串，注意要禁止ascii，不然中文会出问题
                f1.write(json.dumps(jsonNew,ensure_ascii=False)+"\n")
