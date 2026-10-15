#测试让ai结构化输出
from typing import Literal

from pydantic import BaseModel

from src.parent_child_chunk.init_model import qwenModel

#定义结构化类(用pydantic加强检验)

class OutputStructure(BaseModel):
    label:Literal["danger","irrelevant","normal"]
    #理由，如果是拒答、无关、为什么
    reason:str


structured_llm = qwenModel.with_structured_output(OutputStructure)
invoke = structured_llm.invoke("經濟局勢怎麽樣")

print(invoke.label)
print(invoke.reason)



