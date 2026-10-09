from langchain_core.messages import AIMessage

from src.parent_child_chunk.init_model import qwenModel
import json
from pathlib import Path

from src.data_graph.neo4j_init import neo4j_driver

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "data" / "chunk" / "parent.jsonl"
ABSTRACT_OUTPUT_PATH = ROOT / "data" / "graph" / "abstract_output.jsonl"

AFTER_HANDLE_DATA_PATH = ROOT / "data" / "graph" / "after_handle.jsonl"
def save_abstracted_data():
    #拿到抽取的数据
    with open(AFTER_HANDLE_DATA_PATH,'r',encoding="utf-8") as f:
        disease_symptom_dict=json.loads(f.read())[0]

    #把res1.content解析成列表数据结构,取出疾病-症状字典{"病1":[("症状1","相关句子1"),("症状2","相关句子2")]}

    #展开字典，拍平，变成[{"disease":病1,"symptom":"症状1"},{disease:病1,symptom:"症状2"}]
    disease_symptom_list=[]
    #PY:默认只迭代键
    for disease in disease_symptom_dict:
        #extend是追加,会把list做成一个个dict追加进入
        disease_symptom_list.extend([{"disease":disease,"symptom":symptom[0],"quote":symptom[1]} for symptom in disease_symptom_dict[disease]])
    #存入neo4j数据结构
    neo4j_driver.execute_query("""unwind $disease_symptom_list as disease_symptom
merge (n:DISEASE {name:disease_symptom["disease"]})
merge (m:SYMPTOM {name:disease_symptom["symptom"]})
merge (n)-[p:HAS_SYMPTOM {quote:disease_symptom["quote"]}]->(m)""", disease_symptom_list=disease_symptom_list)
    # print(res.count())

ABSTRACT_PROMPT = """
    
    下面我会给你一些按照[疾病][标题]正文的格式的医学段落,请在谈及‘症状’、‘临床表现’等的段落中抽取症状和和对应的依据句子。\n如果发现段落描述的是历史，研究，人文等内容的，请跳过。
    
    如遇到不是症状的词语，不要提取
    如下不要提取：
        失智症、重性抑郁障碍、焦虑症、额颞叶痴呆   ← 是【共病/并发症】，不是症状
        自主神经系统功能异常                    ← 是【类别】，不是症状
        运动神经元退化                          ← 是【病理机制】，不是症状。
    
    有一些症状过于宽泛，比如：焦虑，抑郁，恐惧；它们连接着无数个病，这种不值得作为症状参考的词不要提取
    
    不要抽取病名本身包含的词
    
    映射表只收录"真正做了同义合并"的情况。
    如果原文词和标准词只差繁简（如 腹泻/腹瀉、疲劳/疲勞），不要收录 —— 那是无效条目。
    归一化后的标准词统一用简体中文。
    
    
    
    你会得到一个结果，这个结果最好是这样的格式： 帕金森氏症:[["肌肉无力","帕金森氏症患者会肌肉无力"],["齿轮型僵硬","帕金森氏症还会导致齿轮型僵硬"]] , xxxxx:[["xxx","xxx"],["xxx","xxx"]]    
    
    然后这个结果里面，多个症状可能对应一个意思，你需要把这些意思相近的词都整合成一个词。
    》比如说，"肌肉變得軟弱","肌肉無力","肌肉无力","運動迟缓"都要转化为一个统一的词:"肌肉无力"
    注意，合并粒度需要以这个提取的症状要能对应多个病为准。
    比如：「齿轮型僵硬」只连帕金森一个病，永远不跨病共享，图谱就白建了。
    
    同时还需要输出一份映射表，如：
    {
        "肌肉无力":["肌肉變得軟弱","肌肉無力","肌肉无力","運動迟缓"]
    }
    映射表需要根据下文规定的格式，放到输出结果里面
    
    另外，合并的时候，如果你根据病理知识，不确定这两个词能不能合并，你要想用户问的时候，这两个词会不会被用户混为一谈，如果会，就合并，如果不会，那就不要合并
    
    然后经上述映射的结果如下面的格式：
    {
    "病1":[["症状1","相关句子1"],["症状2","相关句子2"]],
    "病2":[["症状1","相关句子1"],["症状2","相关句子2"]]
    }，
    其中症状是转化后的统一的词。
    
    最终输出的时候，按照这样的格式输出
    [{这里是疾病：症状部分},{这里是映射表部分}]
    输出纯文本即可，不要输出我规定以外的其他内容，顺序要和我写的一致,系统需要解析
    
    
    ===参考示例===
    输入：
    [帕金森氏症][运动障碍]患者常表现为肌肉變得軟弱、齿轮型僵硬。
    [肌萎缩侧索硬化][早期症状]早期可见肌肉软弱、吞咽困难。
    
    输出：
    [{"帕金森氏症":[["肌肉无力","患者常表现为肌肉變得軟弱、齿轮型僵硬。"],["齿轮型僵硬","患者常表现为肌肉變得軟弱、齿轮型僵硬。"]],"肌萎缩侧索硬化":[["肌肉无力","早期可见肌肉软弱、吞咽困难。"],["吞咽困难","早期可见肌肉软弱、吞咽困难。"]]},{"肌肉无力":["肌肉變得軟弱","肌肉软弱"],"齿轮型僵硬":["齿轮型僵硬"],"吞咽困难":["吞咽困难"]}]
    ===示例结束===
    
    注意：输出结果必须是合法的json格式，不用换行，输出在一行即可
    
    好了，医学段落如下：
    """

def abstract() :
    # with engine.begin() as conn:
    #     diseases=["肌萎缩侧索硬化","脊髓性肌肉萎縮症","重症肌無力","帕金森氏症"]
        # diseases = ["肌萎缩侧索硬化"]

    # with engine.begin() as conn:
    #     res = conn.execute(
    #         select(disease_parent_chuck_table).where(disease_parent_chuck_table.c.disease.in_(diseases))).all()
    # info = ""
    # # row是rowMapping对象
    # info += "\n".join(["[" + row.disease + "]" + "[" + row.title + "]" + row.text for row in res])

    jsonLines=[]
    info=""

    with open(SOURCE_PATH,'r',encoding='utf-8') as f:
        count=0
        for line in f:
            count+=1
            if count%20==0:
                prompt_info = ABSTRACT_PROMPT + info
                res = qwenModel.invoke(prompt_info)
                #每20次读取写入一次文件
                with open(ABSTRACT_OUTPUT_PATH,'a',encoding='utf-8') as f1:
                    f1.write(res.content+"\n")
                    info = ""

                print(f"=====================已经完成{count}个文件=====================")
            jsonLine = json.loads(line)
            #1.3去除垃圾数据
            jsonLines.append(jsonLine)
            info += "\n"+"[" + jsonLine['disease'] + "]" + "[" + jsonLine['title'] + "]" + jsonLine['text']
    prompt_info = ABSTRACT_PROMPT + info
    res = qwenModel.invoke(prompt_info)
    #每20次读取写入一次文件
    with open(ABSTRACT_OUTPUT_PATH,'a',encoding='utf-8') as f1:
        f1.write(res.content)

    # info += "\n".join(["["+row['disease']+"]"+"["+row['title'] + "]" + row['text'] for row in jsonLines])

    # 拼贴info，就是把row.title做标题和row.text作为文本拼贴起来
    # return res

if __name__ == '__main__':
    # abstract()
    save_abstracted_data()