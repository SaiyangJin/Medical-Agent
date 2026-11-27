package com.saiyangjin.github.javaservice.client;

import com.saiyangjin.github.javaservice.dto.AskRequest;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;
import reactor.core.publisher.Flux;

/**
 * RestClient客户端
 */
@HttpExchange
public interface PyAgentStreamClient {

    @PostExchange("/test")
    String test();

    @PostExchange(value = "/chat",contentType = MediaType.APPLICATION_JSON_VALUE,accept = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> chat(@RequestBody AskRequest askRequest);
}