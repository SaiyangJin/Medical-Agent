#测试时间旅行，获取到state，然后本地开始调试，复现BUG，只有时间旅行才能具备本地调试的能力
from src.langgraph_demo.content_retrieve_graph import graph

#传入会话id和节点名称，从此节点名称跑整张图
async def replay_by_node(thread_id,node_name):
    #获取到每个节点的状态历史，传入config标志了thread_id，确定是那个对话的对话历史
    async for s in graph.aget_state_history(config={"configurable":{"thread_id": thread_id}}):
        if node_name in s.next:
            print("当时的状态",s.values)
            try:
                ainvoke =await graph.ainvoke(None, s.config)
            except:
                raise Exception("调用失败！")
            print("返回结果",ainvoke)
            return ainvoke
    raise Exception("未找到相关会话或node_name不存在!")

#测试单个节点，获取到state直接跑对应节点即可（调对应函数）
async def replay_single_node(thread_id):
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)

    q = state.values["changed_question"]
    symptoms = state.values["symptoms_list_in_question"]

    #直接调对应的函数即可，省去



if __name__ == '__main__':
    #复现的就是一个时间旅行拉下来state，然后本地调试，怎么调试就是你的事情了，反正就可以复现当时的BUG了。
    replay_by_node("1be8d6d5-2eb3-477f-99f2-31f68cbec538","")
