<script setup>
import { ref, computed, nextTick } from 'vue'
import { getStreamChatApi } from '../api/chat.js'

// ================= 会话管理 =================
// 每个会话：{ id, title, messages }
const sessions = ref([])
const activeId = ref('')

const activeSession = computed(() =>
  sessions.value.find(s => s.id === activeId.value)
)
const messages = computed(() => activeSession.value?.messages ?? [])

// 空状态时的示例问题，点一下直接发送
const examples = [
  '帕金森氏症有哪些早期表现？',
  '我最近老睡不着，白天还心慌，怎么回事',
  '中風和脑积水都会引起认知障碍，有什么区别',
]

function createSession() {
  const s = {
    id: crypto.randomUUID(),   // 同时作为后端的 session_id
    title: '新对话',
    messages: [],
  }
  sessions.value.unshift(s)
  activeId.value = s.id
  return s
}

function switchSession(id) {
  activeId.value = id
  scrollToBottom()
}

// ================= 聊天 =================
const input = ref('')
const loading = ref(false)
const listRef = ref(null)
let controller = null

// 首次进入先建一个空会话
createSession()

async function send(text) {
  const q = (text ?? input.value).trim()
  if (!q || loading.value) return

  const session = activeSession.value
  if (!session) return

  // 每轮新 thread_id（checkpointer 用）；session.id 是会话级（Redis 历史用）
  const threadId = crypto.randomUUID()

  // 第一轮用问题当会话标题
  if (session.title === '新对话') {
    session.title = q.length > 18 ? q.slice(0, 18) + '…' : q
  }

  session.messages.push({ role: 'user', content: q })
  input.value = ''
  loading.value = true
  controller = new AbortController()
  scrollToBottom()

  // index 提到 try 外面：catch 里处理"已停止"时还要用它
  let index = -1
  try {
    session.messages.push({ role: 'ai', content: '', threadId, question: q })
    index = session.messages.length - 1

    let finalAnswer = ''
    for await (const {event, data} of getStreamChatApi(
      q, threadId, controller.signal, "/api/chat", session.id,
    )) {
      if (event === "done") {
        finalAnswer = data
      } else {
        session.messages[index].content += data
      }
    }
    if (finalAnswer) {
      session.messages[index].content = finalAnswer
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      // 用户点了停止：保留已生成的内容，标记为可重试
      if (index >= 0) {
        session.messages[index].content += '\n\n（已停止）'
        session.messages[index].stopped = true
      }
    } else {
      console.log(e)
      // 拦截器已经弹过气泡了，这里只补个占位，免得用户以为卡死
      session.messages.push({ role: 'ai', content: '（请求失败，请看上方提示）' })
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
async function retry(msg) {
  const session = activeSession.value
  if (!msg?.threadId || !msg?.question || !session || loading.value) return

  msg.content = ''
  msg.stopped = false
  loading.value = true
  controller = new AbortController()
  scrollToBottom()

  try {
    let finalAnswer = ''
    for await (const {event, data} of getStreamChatApi(
      msg.question, msg.threadId, controller.signal, "/api/retry", session.id,
    )) {
      if (event === "done") {
        finalAnswer = data
      } else {
        msg.content += data
      }
    }
    if (finalAnswer) {
      msg.content = finalAnswer
    }
  } catch (e) {
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
  <div class="h-screen flex bg-slate-50">

    <!-- 侧边栏：会话列表 -->
    <aside class="w-60 shrink-0 border-r border-slate-200 bg-white flex flex-col">
      <div class="p-3 border-b border-slate-100">
        <el-button type="primary" class="w-full" @click="createSession">
          ＋ 新建对话
        </el-button>
      </div>
      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <div
          v-for="s in sessions"
          :key="s.id"
          @click="switchSession(s.id)"
          class="px-3 py-2 rounded-lg text-sm cursor-pointer truncate transition-colors"
          :class="s.id === activeId
            ? 'bg-blue-50 text-blue-700 font-medium'
            : 'text-slate-600 hover:bg-slate-100'"
        >
          {{ s.title }}
        </div>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="flex-1 flex flex-col min-w-0">

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
          <template v-for="m in messages" :key="m">
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
              <el-button size="small" @click="retry(m)">重试</el-button>
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
  </div>
</template>
