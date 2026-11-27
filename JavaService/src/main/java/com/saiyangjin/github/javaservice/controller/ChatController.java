package com.saiyangjin.github.javaservice.controller;

import com.saiyangjin.github.javaservice.dto.AskRequest;
import com.saiyangjin.github.javaservice.dto.AskResponse;
import com.saiyangjin.github.javaservice.service.ChatService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequiredArgsConstructor
public class ChatController {
    private final ChatService chatService;
    @PostMapping("/test")
    public String test() {
        return chatService.test();
    }

    /**
     * 调用py对话接口
     */
    @PostMapping("/chat")
    public SseEmitter chat(@RequestBody AskRequest askRequest) {
        return chatService.chat(askRequest);
    }
}
