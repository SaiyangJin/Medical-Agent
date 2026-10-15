from src.langgraph_demo.content_retrieve_graph import graph
import uuid
import asyncio
#异步函数：graph以流式运行,这样获取到的ev就是一个个token了，而且需要async异步循环，因为astream是异步输出的
async def stream_test():
    async for ev in graph.astream_events({"question": "菊池病是什么", "trace_id": str(uuid.uuid4())},version="v2"):
        print(ev["event"])
        # data = ev["data"]
        # if "chunk" in data:
        #     print(data["chunk"])
            # if "chunk" in data["chunk"]:
            #     print(data["chunk"]["chunk"])


#测试graph的流式输出
if __name__ == '__main__':
    #运行异步函数还需要asyncio
    asyncio.run(stream_test())

