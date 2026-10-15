import {axiosInstance} from "../axios/axios.js";

export const chatApi=async(question)=>{
    return await axiosInstance.post("/api/chat", {
        "question": question
    })
}


export async function* getStreamChatApi(question) {
    const res =await fetch("/api/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            "question": question
        })
    });
    //文本编码器
    const textDecoder = new TextDecoder();
    //读取器
    const reader = res.body.getReader();
    //一直读取流，直到结束
    let text = ""
    while (true) {
        //读取到res里面的done标识(reader.read())，和value值
        const {done, value} = await reader.read()//异步读，卡住，但是可以去做别的事情
        //如果done了，直接break
        if (done) {
            break
        }
        //不然就不断添加text,yield返回这个值

        yield parseOneMessage(textDecoder.decode(value))
    }
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
            event = chunk.slice(6);
        }
    }
    return {event,data}
}