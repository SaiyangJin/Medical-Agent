#第一段爬虫程序,测试从wiki爬出资料文献，并进行简单清理

import httpx
import re

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
    #必须在普通链接[[A|B]]之前处理，否则会被误当成正文链接，
    #留下 "thumb|说明" 这种垃圾碎片
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


if __name__ == "__main__":
    client = httpx.Client(headers={"User-Agent": "test/0.1"}, timeout=httpx.Timeout(60.0))
    res = client.get(url="https://zh.wikipedia.org/w/rest.php/v1/page/糖尿病")
    raw = res.json()["source"]

    cleaned = clean_wikitext(raw)
    print(f"清洗前 {len(raw)} 字符 -> 清洗后 {len(cleaned)} 字符")
    print(cleaned[:800])

    client.close()
