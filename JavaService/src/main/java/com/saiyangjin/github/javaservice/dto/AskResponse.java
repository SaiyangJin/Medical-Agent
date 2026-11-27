package com.saiyangjin.github.javaservice.dto;

import java.util.Map;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;

@Data
public class AskResponse {
    private int code;
    private String msg;
    private Map<String, Object> data;
}