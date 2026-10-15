<script setup>
import { ref, nextTick } from 'vue'
import {chatApi, getStreamChatApi} from '../api/chat.js'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const listRef = ref(null)

// 空状态时的示例问题，点一下直接发送
const examples = [
  '帕金森氏症有哪些早期表现？',
  '我最近老睡不着，白天还心慌，怎么回事',
  '中風和脑积水都会引起认知障碍，有什么区别',
]

async function send(text) {
  const q = (text ?? input.value).trim()
  if (!q || loading.value) return

  messages.value.push({ role: 'user', content: q })
  input.value = ''
  loading.value = true
  scrollToBottom()

  try {
    let text = ''
    messages.value.push({ role: 'ai', content: text })
    //然後想要修改的话，那就必须修改messages列表里面的东西了
    let index = messages.value.length - 1
    for await (const {event,data} of getStreamChatApi(q)){
      // console.log("本次事件",event,"本次data",data)
      console.log("本次事件",event,"本次data",data)
      if(event==="done"){
        text=data
      }
      else{
        messages.value[index].content+=data
      }
    }
  } catch (e){
    console.log(e)
    // 拦截器已经弹过气泡了，这里只补个占位，免得用户以为卡死
    messages.value.push({ role: 'ai', content: '（请求失败，请看上方提示）' })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

// Enter 发送，Shift+Enter 换行
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
</script>

<template>
  <div class="h-screen flex flex-col bg-slate-50">

    <!-- 顶部 -->
    <header class="shrink-0 border-b border-slate-200 bg-white px-6 py-3">
      <div class="max-w-3xl mx-auto flex items-center gap-2">
        <span class="text-lg font-semibold text-slate-800">医疗知识图谱问答助手</span>
        <span class="text-xs text-slate-400 bg-slate-100 rounded px-2 py-0.5">RAG · 实验性</span>
      </div>
    </header>

    <!-- 消息区 -->
    <main ref="listRef" class="flex-1 overflow-y-auto px-6 py-6">
      <div class="max-w-3xl mx-auto space-y-5">

        <!-- 空状态 -->
        <div v-if="!messages.length" class="pt-16 text-center">
          <p class="text-slate-400 mb-6">描述你的症状，或问某个疾病</p>
          <div class="flex flex-col items-center gap-2">
            <button
              v-for="q in examples"
              :key="q"
              @click="send(q)"
              class="text-sm text-slate-600 bg-white border border-slate-200 rounded-full
                     px-4 py-2 hover:border-blue-400 hover:text-blue-600 transition-colors"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <!-- 消息气泡 -->
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="flex"
          :class="m.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[80%] rounded-2xl px-4 py-3 whitespace-pre-wrap leading-relaxed"
            :class="m.role === 'user'
              ? 'bg-blue-600 text-white'
              : 'bg-white text-slate-800 border border-slate-200'"
          >
            {{ m.content }}
          </div>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="flex justify-start">
          <div class="bg-white border border-slate-200 rounded-2xl px-4 py-3
                      text-slate-400 text-sm">
            思考中…（首次可能要 40 秒）
          </div>
        </div>

      </div>
    </main>

    <!-- 输入区 -->
    <footer class="shrink-0 border-t border-slate-200 bg-white px-6 py-4">
      <div class="max-w-3xl mx-auto">
        <div class="flex gap-3 items-end">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            :disabled="loading"
            placeholder="描述你的症状，或问某个疾病…（Enter 发送，Shift+Enter 换行）"
            @keydown="onKeydown"
          />
          <el-button type="primary" size="large" :loading="loading" @click="send()">
            发送
          </el-button>
        </div>
        <p class="mt-2 text-xs text-slate-400 text-center">
          本回答由 AI 生成，仅供参考，不能替代专业医疗诊断。
        </p>
      </div>
    </footer>

  </div>
</template>
