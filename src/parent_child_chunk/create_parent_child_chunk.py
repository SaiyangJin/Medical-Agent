#构建父子块的方法

#======================================引入区=====================================
import re
#引入Path类，调用resolve获取自己文件的地址
from pathlib import Path
#引入json模块，处理json数据
import json

#======================================常量区=====================================

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

SOURCE_PATH = DATA / "cleaned" / "full.jsonl"
# SOURCE_PATH = DATA / "cleaned" / "one.jsonl"
# SOURCE_PATH = DATA / "cleaned" / "small.jsonl"
BLOCK_QID_PATH = DATA / "garbage" / "garbage_qid.txt"
BLOCK_TITLE_PATH = DATA / "garbage" / "garbage_title.txt"

CHUNK = DATA / "chunk"
CHUNK.mkdir(exist_ok=True)
#子块目标路径
CHILD_TARGET_PATH = CHUNK / "child.jsonl"
#父块目标路径
PARENT_TARGET_PATH = CHUNK / "parent.jsonl"

#正则模块，一个是按标题分，一个是按句子分

#1,标题分，捕获标题正文，获取到起点和终点
TITLE_REGIX=re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.MULTILINE)
#re.mutiline让^变成字符串每一行的开头和结尾，能逐行扫描

#2,句子分，捕获句子正文，获取到起点和终点
SENTENCE_REGIX = re.compile(r"[^。！？；]+[。！？；]?")
#======================================函数区=====================================

#垃圾定义垃圾标题
block_titles=set([])
#存入垃圾数据id
with open(BLOCK_TITLE_PATH,"r",encoding="utf-8") as garbage_titles:
    for garbage_title in garbage_titles:
        block_titles.add(garbage_title.strip())
print(block_titles)
# 父块切分函数,传入文本和疾病名，返回一个数组，里面是被处理好的大块+疾病名+父id+标题的json
def parent_chunking(text : str,disease : str,qid:str,revision:str)->list:
    #这边指一个text的父块列表
    one_parent_chunks=[]
    matches = list(TITLE_REGIX.finditer(text))
    #无匹配兜底
    if not matches:
        one_parent_chunks.append({
            "text": text[0:len(text)],
            "title": "介绍",
            "id": qid+"-"+str(0),
            "disease": disease,
            "revision": revision,
        })
        return one_parent_chunks
    #前文补充
    one_parent_chunks.append({
        "text": text[0:matches[0].start()],
        "title": "介绍",
        "id": qid+"-"+str(0),
        "disease": disease,
        "revision": revision,
    })
    #1，循环遍历匹配到的标题结果


    for i,match in enumerate(matches):
        #enumerate函数自动维护计数器，就是i变量
        #1.1获取标题title
        match_title = match.group(2)
        #1.2如果是垃圾标题，跳过
        if match_title in block_titles:
            continue
        start = match.start()
        end = match.end()
        #1.3如果下一个i超限了，那就说明这是最后一个标题，最后一个标题的终点，是len(text),整段文本的终点
        if i+1>=len(matches):
            next_start=len(text)
            text1 = text[end:next_start]
            if text1.strip()== "" or text1.strip()== "\n":
                continue
                #去除行首的换行符
            if text1.startswith("\n"):
                text1=text1[1:len(text1)]
            one_parent_chunks.append({
                "text": text1,
                "title": match_title,
                "id": qid+"-"+str(i+1),
                "disease": disease,
                "revision": revision,
            })
            break
        #1.3根据下一个match的起始，和这个match的终点，trip去空格，取出中间的文本，就是一大段父Chunk
        next_start=matches[i+1].start()
        #1.4list[tuple[str,str]]，返回
        text2 = text[end:next_start]
        if text2.strip()== "" or text2.strip()== "\n":
            continue
            #去除行首的换行符
        if text2.startswith("\n"):
            text2=text2[1:len(text2)]
        one_parent_chunks.append({
            "text": text2,
            "title": match_title,
            "id": qid+"-"+str(i+1),
            "disease": disease,
            "revision": revision,
        })
    return one_parent_chunks

# 子块切分函数,传入文本和疾病名，返回一个json数组，json里面是被处理好的小块文本+其他需要保存的数据(id,parentid,disease,title,revision)
def child_chunking(text : str,title:str,disease : str,revision:str,parent_id:str)->list:
    max_length=500
    one_child_chunks=[]

    #1，先按照段落"\n\n"分出对应的段落数组,再交給句子分詞器處理,因为"\n"会分出很多没用的小段
    splits = text.split("\n\n")
    for i,split in enumerate(splits):
        #目前这就是一段。
        #清理文本
        #去除空行
        if split.strip()== "" or split.strip()== "\n":
            continue
        #去除行首的换行符
        if split.startswith("\n"):
            split=split[1:len(split)]
        #1.1如果段落长度大于了max_length,那就交给句子分词器处理
        if len(split)>max_length:
            sentence_str=""
            sentences = SENTENCE_REGIX.finditer(split)
            #1.1.1便利所有的句子，直到句子长度大于max_length，算一段，加入
            for i,sentence in enumerate(list(sentences)):
                sentence_text = sentence.group()
                #如果句子文本是空的，就跳过，因为\n\n情况
                #清理文本
                #去除空行
                if sentence_text.strip()== "" or sentence_text.strip()== "\n":
                    continue
                #去除行首的换行符
                if sentence_text.startswith("\n"):
                    sentence_text=sentence_text[1:len(sentence_text)]
                if len(sentence_str + sentence_text)>max_length:
                    one_child_chunks.append({
                        "text": sentence_str,
                        "title": title,
                        "parent_id": parent_id,
                        "disease": disease,
                        "revision": revision,
                        "id": parent_id+"-"+str(len(one_child_chunks)),
                    })
                    #加入后，新str，句子置空
                    sentence_str=""
                sentence_str+= sentence_text
            #1.1.2遍历完之后，还有一段内容因为没有大于max没有被收割，补上
            if sentence_str!=""or sentence_str!="\n":
                one_child_chunks.append({
                    "text": sentence_str,
                    "title": title,
                    "parent_id": parent_id,
                    "disease": disease,
                    "revision": revision,
                    "id": parent_id+"-"+str(len(one_child_chunks)),
                })
        #1.2如果没超过max_length，直接加入最终结果集即可
        else:
            if split== "" or split=="\n":
                #如果句子文本是空的，就跳过，因为\n\n情况
                continue
            one_child_chunks.append({
                "text": split,
                "title": title,
                "parent_id": parent_id,
                "disease": disease,
                "revision": revision,
                "id": parent_id+"-"+str(len(one_child_chunks)),
            })

    #2，返回最终结果集
    return one_child_chunks


#======================================逻辑区=====================================

if __name__ == '__main__':
    #先拿到full里边的原始文档
    child_chunks=[]
    parent_chunks=[]
    #放垃圾数据
    block_qids=set([])
    #存入垃圾数据id
    with open(BLOCK_QID_PATH,"r",encoding="utf-8") as f:
        for line in f:
            block_qids.add(line.strip())
    with open(SOURCE_PATH,"r",encoding="utf-8") as f:
        for line in f:
            #1,第一个模块，按标题分
            #line是一个疾病json字符串,先转化为json,再获取文本
            #qid去除
            qid = json.loads(line)["id"]
            if block_qids and qid in block_qids:
                continue
            text = json.loads(line)["text"]

            disease = json.loads(line)["disease"]
            revision = json.loads(line)["revision"]
            #2，交给切大块函数（传入文本和disease）返回处理后的结果：一个数组里面是被处理好的大块+疾病名+id
            new_parent_chunks = parent_chunking(text, disease, qid,revision)
            parent_chunks+= new_parent_chunks

            #3,交给切小块函数（传入文本和disease）返回处理后的结果：一个数组里面是被处理好的小块+疾病名+父id+标题等json
            for new_parent_chunk in new_parent_chunks:
                text = new_parent_chunk["text"]
                title = new_parent_chunk["title"]
                parent_id = new_parent_chunk["id"]
                child_chunks+=child_chunking(text,title,disease,revision,parent_id)
            #至此，父子chunks构建完毕


    #4，写入最终文件
    with open(PARENT_TARGET_PATH,"w",encoding="utf-8") as f:
        #4.1遍历大块表
        for parent_chunk in parent_chunks:
            #4.2，拼贴之后写入文件
            f.write(json.dumps(parent_chunk,ensure_ascii=False)+"\n")


    with open(CHILD_TARGET_PATH,"w",encoding="utf-8") as f:
        #4.1遍历小块表
        for child_chunk in child_chunks:
            #4.2，拼贴之后以jsonb写入文件
            f.write(json.dumps(child_chunk,ensure_ascii=False)+"\n")

