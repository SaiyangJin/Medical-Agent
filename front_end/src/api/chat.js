import {axiosInstance} from "../axios/axios.js";

export const chatApi=async(question, threadId = crypto.randomUUID())=>{
    return await axiosInstance.post("/api/chat", {
        "question": question,
        "thread_id": threadId
    })
}


export async function* getStreamChatApi(question, threadId = crypto.randomUUID(), signal, endpoint = "/api/chat", sessionId = "") {
    //应该是在抓取数据
    const res =await fetch(endpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            "question": question,
            "thread_id": threadId,
            "session_id": sessionId   // 整个会话固定，后端用它读写 Redis 历史
        }),
        signal,   // AbortController 的中止信号，调用 controller.abort() 会中断这次请求
    });
    const textDecoder = new TextDecoder();
    const reader = res.body.getReader();
    let buffer = "";
    //开始循环读取数据,直到done
    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        // stream:true 防止中文多字节字符跨 chunk 被切成乱码
        buffer += textDecoder.decode(value, { stream: true });

        let idx;
        //获取的文本段按照 "\n\n" 分割
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            yield parseOneMessage(raw);
        }
    }
    if (buffer.trim()) yield parseOneMessage(buffer);
}

const parseOneMessage=(message)=>{
    let data=""
    let event="token"
    //先把message每一行遍历出来
    for (const chunk of message.split("\n")){
        //如果一行以data开头，那就直接把后面的数据赋值给data
        if(chunk.startsWith("data: ")){
            //提取出子串，slice(开始位置，结束位置)
             data += JSON.parse(chunk.slice(6));
        }else if(chunk.startsWith("event: ")){
            // "event: " 是 7 个字符（含冒号后的空格），slice(6) 会切出 " done"
            event = chunk.slice(7);
        }
    }
    return {event,data}
}