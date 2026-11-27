package com.saiyangjin.github.javaservice.service;

import com.saiyangjin.github.javaservice.client.PyAgentStreamClient;
import com.saiyangjin.github.javaservice.dto.AskRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.Disposable;
import reactor.core.scheduler.Schedulers;

import java.io.IOException;

@Service
@RequiredArgsConstructor
public class ChatService {
    private final PyAgentStreamClient pyAgentStreamClient;
    public String test() {
        return pyAgentStreamClient.test();
    }

    public SseEmitter chat(AskRequest askRequest) {
        //建立SseEmitter，设置超时时间为0，不结束
        SseEmitter emitter = new SseEmitter(0L);
        //接下来调用接口，建立流式，然后转发数据
        Disposable disposable = pyAgentStreamClient.chat(askRequest)
                .publishOn(Schedulers.boundedElastic())   // 别在 Netty 线程里做阻塞写
                .subscribe(
                        event -> {
                            if (event.data() == null) return;
                            //构建sseEmitter然后发送回去
                            try {
                                SseEmitter.SseEventBuilder builder = SseEmitter.event().data(event.data());
                                if (event.event() != null) {
                                    builder.name(event.event());
                                }
                                emitter.send(builder);
                            } catch (IOException e) {
                                emitter.completeWithError(e);
                            }
                        },
                        emitter::completeWithError //错误方法回调
                        , emitter::complete //正常结束方法回调
                );
        //前段断开sseemiiter，py接口也要断开
        emitter.onCompletion(disposable::dispose);
        emitter.onTimeout(disposable::dispose);
        emitter.onError(t->disposable.dispose());
        return emitter;
    //订阅，就开始接收推送了,设置正常退出和报错都要停止emitter

    }
}
