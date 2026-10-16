#测试事实完整率的py文件,就是标准答案在答案中有多少是命中的
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "test" / "completeness.jsonl"

from ragas import SingleTurnSample, EvaluationDataset, evaluate, RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import faithfulness,FactualCorrectness
from src.parent_child_chunk.init_model import qwenModel, embeddingModel, engine, backupQwenModel

#测试构建一个测试数据集
samples=[]

def strip_reference_block(text):
    m = re.search(r"\n\s*\[\d+\]", text)
    if not m:
        return text
    return text[:m.start()]

with open(PATH,"r",encoding="utf-8") as f:
    #读取jsonl文件，completeness的Sample对象
    for line in f:
        line_dict = json.loads(line)
        samples.append(SingleTurnSample(
            response=strip_reference_block(line_dict["response"]),
            user_input=line_dict["user_input"],
            reference=line_dict["reference"]
        ))


#构建一个测试对象
dataset = EvaluationDataset(samples)

#运行评测g,传入测试对象，传入llm
e = evaluate(dataset=dataset
             ,llm=LangchainLLMWrapper(qwenModel)
             ,embeddings=embeddingModel#向量模型，暂时不需要
             ,raise_exceptions=True#抛出异常
             ,show_progress=True#展示检索进度条
             ,metrics=[FactualCorrectness()])

print(e.to_pandas())