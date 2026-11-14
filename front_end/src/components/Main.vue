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

// 当前请求的中止控制器；只有生成中才不为 null
let controller = null

async function send(text) {
  const q = (text ?? input.value).trim()
  if (!q || loading.value) return

  // 每次新对话生成一个新 thread_id；重试时可以复用消息里存的那个
  const threadId = crypto.randomUUID()

  messages.value.push({ role: 'user', content: q })
  input.value = ''
  loading.value = true
  controller = new AbortController()
  scrollToBottom()

  // index 提到 try 外面：catch 里处理"已停止"时还要用它
  let index = -1
  try {
    messages.value.push({ role: 'ai', content: '', threadId, question: q })
    //然後想要修改的话，那就必须修改messages列表里面的东西了
    index = messages.value.length - 1

    let finalAnswer = ''
    for await (const {event,data} of getStreamChatApi(q, threadId, controller.signal)){
      if(event==="done"){
        finalAnswer = data
      } else {
        messages.value[index].content += data
      }
    }
    if(finalAnswer){
      messages.value[index].content = finalAnswer
    }
  } catch (e){
    if (e.name === 'AbortError') {
      // 用户点了停止：保留已生成的内容，标记为可重试
      if (index >= 0) {
        messages.value[index].content += '\n\n（已停止）'
        messages.value[index].stopped = true
      }
    } else {
      console.log(e)
      // 拦截器已经弹过气泡了，这里只补个占位，免得用户以为卡死
      messages.value.push({ role: 'ai', content: '（请求失败，请看上方提示）' })
    }
  } finally {
    controller = null
    loading.value = false
    scrollToBottom()
  }
}

// 停止生成：中断 fetch，后端会收到连接断开，图在最后一个完成的节点处停下
function stop() {
  controller?.abort()
}

// 重试：用同一个 thread_id 调 /retry，后端从最后一个完成的节点继续
async function retry(index) {
  const msg = messages.value[index]
  if (!msg?.threadId || !msg?.question || loading.value) return

  msg.content = ''
  msg.stopped = false
  loading.value = true
  controller = new AbortController()
  scrollToBottom()

  try {
    let finalAnswer = ''
    for await (const {event,data} of getStreamChatApi(msg.question, msg.threadId, controller.signal, "/api/retry")){
      if(event==="done"){
        finalAnswer = data
      } else {
        msg.content += data
      }
    }
    if(finalAnswer){
      msg.content = finalAnswer
    }
  } catch (e){
    if (e.name === 'AbortError') {
      msg.content += '\n\n（已停止）'
      msg.stopped = true
    } else {
      console.log(e)
      msg.content += '\n\n（重试失败）'
    }
  } finally {
    controller = null
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
        <template v-for="(m, i) in messages" :key="i">
          <div
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
          <!-- 只有被手动停止的回答才显示重试 -->
          <div v-if="m.role === 'ai' && m.stopped" class="flex justify-start -mt-3">
            <el-button size="small" @click="retry(i)">重试</el-button>
          </div>
        </template>

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
          <el-button v-if="loading" type="danger" size="large" @click="stop">
            停止
          </el-button>
          <el-button v-else type="primary" size="large" @click="send()">
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
