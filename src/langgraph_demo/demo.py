from typing import TypedDict

from langgraph.graph import StateGraph,START,END

class State(TypedDict):
    question: str
    docs: list
    answer: str
def fake_search(state:State):
    return {"docs":[f"检索到：{state['question']}"]}
def fake_generate(state:State):
    return {"answer":f"基于{len(state['docs'])}"}
def safety_check(state:State):
    if state['question']== "胸痛":
        return {"answer":"及时就医。"}
    return {}
def router(state:State):
    return "end" if state.get("answer") else "generate"
#3,拼图
builder = StateGraph(State)
builder.add_node("search",fake_search)
builder.add_node("generate",fake_generate)
builder.add_node("safe_check",safety_check)
builder.add_edge(START,"search")
builder.add_edge("search","safe_check")
builder.add_conditional_edges("safe_check",router,{"end":END,"generate":"generate"})
builder.add_edge("generate",END)
graph = builder.compile()

print(graph.invoke({"question": "缺氧"}))
print("————————————————————————————————————————————————")
print(graph.invoke({"question": "胸痛"}))