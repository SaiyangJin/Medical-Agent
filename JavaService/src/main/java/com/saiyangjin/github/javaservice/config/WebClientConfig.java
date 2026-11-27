package com.saiyangjin.github.javaservice.config;

import com.saiyangjin.github.javaservice.client.PyAgentStreamClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
public class WebClientConfig {

    @Bean
    public WebClient pyWebClient() {
        return WebClient.builder().baseUrl("http://127.0.0.1:8080").build();
    }
    @Bean
    public PyAgentStreamClient pyAgentClient(WebClient webClient){
        //代理实现类
        return HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(webClient))
                .build()
                .createClient(PyAgentStreamClient.class);
    }

}
