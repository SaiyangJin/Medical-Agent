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
        let idx;2
        buffer = buffer.replace(/\r\n/g, '\n')
        //因为网络块是按照 "\r\n\r\n" 分的，获取的文本段按照 "\r\n\r\n" 分割
        console.log("buffer",buffer,buffer.indexOf("\n\n"))
        while ((idx = buffer.indexOf("\n\n")) !== -1) {

            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 4);
            yield parseOneMessage(raw);
        }
    }
    if (buffer.trim()) yield parseOneMessage(buffer);
}

// 单个sse网络块："event:done \n data:你 \n data:好" 这是需要解析的
const parseOneMessage=(message)=>{
    const dataLines = []
    let event="token"
    //先把message每一行遍历出来

    for (let chunk of message.split("\n")){
        //你用了框架，所以靠的/r/n分隔，/r去掉
        if (chunk.endsWith('\r')) chunk = chunk.slice(0, -1)
        //如果一行以data开头，说明是数据，追加最终列表
        if(chunk.startsWith("data: ")){
            dataLines.push(chunk.slice(5).replace(/^ /, ""));// 切片 5 而不是 6：SSE 允许 "data:xxx" 无空格，这里只去掉一个协议空格
        }else if(chunk.startsWith("event: ")){
            // "event: " 是 7 个字符（含冒号后的空格），slice(6) 会切出 " done"
            event = chunk.slice(6).trim();
        }
    }
    return {event,data: dataLines.join("\n")}
}