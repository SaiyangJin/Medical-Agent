package com.saiyangjin.github.javaservice.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;

@Data
public class AskRequest {

    @Schema(description = "The question to ask", example = "你好")
    public String question;

    @Schema(description = "The thread id" ,example = "1234567890")
    @JsonProperty("thread_id") //转化成json的时候使用下划线样式，例如thread_id
    public String threadId;

    @Schema(description = "The session id", example = "0987654321")
    @JsonProperty("session_id") //转化成json的时候使用下划线样式，例如session_id
    public String sessionId;
}

