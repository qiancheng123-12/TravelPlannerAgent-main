<template>
  <div class="chat-container">
    <!-- 侧边栏 -->
    <div class="sidebar">
      <div class="sidebar-header">
        <h2>💬 对话模式</h2>
        <el-button text @click="handleNewChat">
          <el-icon><Plus /></el-icon>
          新对话
        </el-button>
      </div>

      <!-- 快捷指令 -->
      <div class="quick-commands">
        <h4>快捷指令</h4>
        <el-button
          v-for="cmd in quickCommands"
          :key="cmd.label"
          size="small"
          @click="handleQuickCommand(cmd.text)"
          style="margin: 4px"
        >
          {{ cmd.label }}
        </el-button>
      </div>

      <!-- 当前会话信息 -->
      <div v-if="chatStore.sessionId" class="session-info">
        <h4>当前会话</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item v-if="currentCity" label="目的地">{{ currentCity }}</el-descriptions-item>
          <el-descriptions-item v-if="currentDates" label="日期">{{ currentDates }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ llmProvider }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 切换链接 -->
      <div class="sidebar-footer">
        <el-button v-if="tripStore.tripPlan" text @click="handleViewDetail">📍 查看当前行程</el-button>
        <el-button text @click="router.push('/memory#trips')">📋 历史行程</el-button>
        <el-button text @click="$router.push('/memory')">🧠 我的记忆</el-button>
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept=".pdf,.docx,.txt,.md"
          :on-change="handleKnowledgeUpload"
        >
          <el-button text :loading="isUploadingKnowledge">📚 上传旅行资料</el-button>
        </el-upload>
        <el-button text @click="$router.push('/')">
          <el-icon><Edit /></el-icon>
          切换到表单模式
        </el-button>
      </div>
    </div>

    <!-- 主聊天区 -->
    <div class="main-chat">
      <!-- 消息列表 -->
      <div ref="messageListRef" class="message-list">
        <div v-if="!chatStore.hasMessages" class="welcome-message">
          <div class="welcome-icon">🌍</div>
          <h2>欢迎使用 LangGraph 智能旅行助手</h2>
          <p>请告诉我您想去哪里旅行，我会为您规划完美的行程。</p>
          <div class="examples">
            <el-card
              v-for="example in examples"
              :key="example"
              shadow="hover"
              class="example-card"
              @click="handleQuickCommand(example)"
            >
              {{ example }}
            </el-card>
          </div>
        </div>

        <div
          v-for="(msg, index) in chatStore.messages"
          :key="index"
          :class="['message', msg.role]"
        >
          <div class="message-avatar">
            <el-avatar v-if="msg.role === 'user'" :size="36">
              <el-icon><User /></el-icon>
            </el-avatar>
            <el-avatar v-else :size="36" style="background: #409eff">
              <el-icon><Service /></el-icon>
            </el-avatar>
          </div>
          <div class="message-content">
            <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
            <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
        </div>

        <!-- 加载动画 -->
        <div v-if="chatStore.isLoading" class="message assistant loading">
          <div class="message-avatar">
            <el-avatar :size="36" style="background: #409eff">
              <el-icon><Service /></el-icon>
            </el-avatar>
          </div>
          <div class="message-content">
            <div class="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <div v-if="quickReplies.length" class="quick-replies">
          <el-tag
            v-for="reply in quickReplies"
            :key="reply"
            effect="plain"
            class="quick-reply"
            @click="handleQuickCommand(reply)"
          >{{ reply }}</el-tag>
        </div>
        <!-- LLM 选择 -->
        <div class="llm-selector">
          <el-radio-group v-model="llmProvider" size="small">
            <el-radio-button label="deepseek">DeepSeek</el-radio-button>
            <el-radio-button label="aliyun">阿里云百炼</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 输入框 -->
        <div class="input-box">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="2"
            :disabled="chatStore.isLoading"
            placeholder="请输入您的旅行需求，例如：帮我规划一个北京三日游..."
            @keydown.enter.ctrl="handleSend"
          />
          <el-button
            type="primary"
            :disabled="!inputMessage.trim() || chatStore.isLoading"
            @click="handleSend"
          >
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>

        <div class="input-hint">
          按 Ctrl + Enter 快速发送
        </div>
      </div>
    </div>

    <!-- 行程预览侧边栏 -->
    <el-drawer
      v-model="showTripDrawer"
      title="行程预览"
      direction="rtl"
      size="40%"
    >
      <div v-if="tripStore.tripPlan" class="trip-preview">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="目的地">{{ tripStore.tripPlan.city }}</el-descriptions-item>
          <el-descriptions-item label="天数">{{ tripStore.tripPlan.days.length }}天</el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <el-button type="primary" @click="handleViewDetail">
          查看完整行程
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Plus, Edit, User, Service, Promotion
} from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { useTripStore } from '@/stores/trip'
import {
  getChatHistory,
  getMemoryProfile,
  getMemoryTrip,
  saveMemoryTrip,
  sendChatMessage,
  uploadKnowledgeDocument
} from '@/services/api'
import { createSessionId } from '@/utils/identity'

const router = useRouter()
const chatStore = useChatStore()
const tripStore = useTripStore()

const inputMessage = ref('')
const llmProvider = ref<'deepseek' | 'aliyun'>('deepseek')
const messageListRef = ref<HTMLElement>()
const showTripDrawer = ref(false)
const quickReplies = ref<string[]>([])
const isUploadingKnowledge = ref(false)

// 快捷指令
const quickCommands = [
  { label: '🏛️ 历史文化', text: '我对历史文化景点感兴趣' },
  { label: '🏞️ 自然风光', text: '我想看自然风光' },
  { label: '🍜 美食之旅', text: '帮我规划一个美食之旅' },
  { label: '💰 省钱攻略', text: '帮我规划一个经济实惠的行程' }
]

// 示例对话
const examples = [
  '帮我规划一个北京三日游，想看故宫和长城',
  '我想去成都玩，喜欢美食和熊猫',
  '上海两日游，预算2000元以内',
  '杭州西湖一日游，自驾出行'
]

// 当前会话信息
const currentCity = computed(() => tripStore.tripPlan?.city || '')
const currentDates = computed(() => {
  if (tripStore.tripPlan?.start_date && tripStore.tripPlan?.end_date) {
    return `${tripStore.tripPlan.start_date} ~ ${tripStore.tripPlan.end_date}`
  }
  return ''
})

// 渲染Markdown
function renderMarkdown(text: string): string {
  // 先转义 HTML，避免 v-html 渲染用户输入中的脚本。
  const escaped = text.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[character] || character))
  return escaped
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

// 格式化时间
function formatTime(date: Date): string {
  return new Date(date).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// 发送消息
async function handleSend() {
  const message = inputMessage.value.trim()
  if (!message || chatStore.isLoading) return

  inputMessage.value = ''
  chatStore.addMessage('user', message)
  chatStore.setLoading(true)
  scrollToBottom()

  try {
    // 创建会话ID
    if (!chatStore.sessionId) {
      const sessionId = createSessionId()
      chatStore.setSessionId(sessionId)
      tripStore.setSessionId(sessionId)
    }

    // 发送消息并获取回复
    const response = await sendChatMessage({
      session_id: chatStore.sessionId,
      user_id: chatStore.userId,
      message,
      llm_provider: llmProvider.value
    })

    chatStore.addMessage('assistant', response.response)
    quickReplies.value = response.quick_replies || []
    scrollToBottom()

    // 如果返回了行程数据，更新store
    if (response.trip_plan) {
      tripStore.setTripPlan(response.trip_plan as any)
      tripStore.setStatus('need_confirm')
      tripStore.setNeedHumanReview(true)
      showTripDrawer.value = true
    }
  } catch (error: any) {
    ElMessage.error(error.message || '发送失败')
    chatStore.addMessage('assistant', '抱歉，我遇到了一些问题，请稍后再试。')
  } finally {
    chatStore.setLoading(false)
  }
}

// 快捷指令
function handleQuickCommand(text: string) {
  inputMessage.value = text
  handleSend()
}

// 新对话
function handleNewChat() {
  chatStore.reset()
  tripStore.reset()
  quickReplies.value = []
  ElMessage.success('已开始新对话')
}

async function handleKnowledgeUpload(uploadFile: any) {
  if (!uploadFile.raw) return
  isUploadingKnowledge.value = true
  try {
    const result = await uploadKnowledgeDocument(uploadFile.raw)
    const extractionDetail = result.ocr_pages > 0
      ? `，OCR 识别 ${result.ocr_pages}/${result.pages} 页`
      : `，原生文字解析 ${result.native_pages || result.pages} 页`
    ElMessage.success(`已入库 ${result.chunks} 个语义片段${extractionDetail}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '知识文档上传失败')
  } finally {
    isUploadingKnowledge.value = false
  }
}

// 查看详情
function handleViewDetail() {
  showTripDrawer.value = false
  router.push('/result')
}

// 监听消息变化
watch(() => chatStore.messages.length, () => {
  scrollToBottom()
})

onMounted(async () => {
  if (chatStore.sessionId) {
    const activeSessionId = chatStore.sessionId
    try {
      const result = await getChatHistory(activeSessionId, chatStore.userId)
      chatStore.replaceMessages(result.history)
      if (tripStore.sessionId && tripStore.sessionId !== activeSessionId) {
        tripStore.reset()
      }
      tripStore.setSessionId(activeSessionId)
    } catch (error) {
      // 会话不存在或属于旧身份时，从新会话开始，不阻断页面使用。
      chatStore.reset()
      tripStore.reset()
    }

    // tripStore 原本只在内存中，页面刷新后需从 SQLite 恢复当前会话最近行程。
    if (chatStore.sessionId && !tripStore.tripPlan) {
      try {
        const profile = await getMemoryProfile(chatStore.userId)
        const latestTrip = profile.trips.find((trip) => trip.session_id === activeSessionId)
        if (latestTrip) {
          const detail = await getMemoryTrip(chatStore.userId, latestTrip.trip_id)
          tripStore.setSessionId(detail.session_id)
          tripStore.setTripPlan(detail.plan)
          tripStore.setStatus('completed')
          tripStore.setNeedHumanReview(false)
        }
      } catch {
        // 记忆接口暂时不可用时保留聊天，不因行程恢复失败清空会话。
      }
    }

    // 旧后端未落库但浏览器仍保留当前行程时，自动补写到新版 SQLite。
    if (tripStore.sessionId && tripStore.tripPlan) {
      try {
        await saveMemoryTrip(chatStore.userId, tripStore.sessionId, tripStore.tripPlan)
      } catch {
        // 自动补写失败不影响继续对话，用户仍可从本地缓存查看当前行程。
      }
    }
  }
  scrollToBottom()
})
</script>

<style scoped>
.chat-container {
  display: flex;
  height: 100vh;
  background: #f5f7fa;
}

.sidebar {
  width: 280px;
  background: white;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  padding: 20px;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.sidebar-header h2 {
  font-size: 18px;
  margin: 0;
}

.quick-commands {
  margin-bottom: 20px;
}

.quick-commands h4 {
  font-size: 14px;
  color: #909399;
  margin-bottom: 10px;
}

.session-info {
  flex: 1;
  overflow: auto;
}

.session-info h4 {
  font-size: 14px;
  color: #909399;
  margin-bottom: 10px;
}

.sidebar-footer {
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
}

.sidebar-footer > .el-button,
.sidebar-footer :deep(.el-upload .el-button) {
  width: 100%;
  margin-left: 0;
  justify-content: flex-start;
}

.main-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
}

.welcome-icon {
  font-size: 64px;
  margin-bottom: 20px;
}

.welcome-message h2 {
  margin-bottom: 10px;
}

.welcome-message p {
  color: #909399;
  margin-bottom: 30px;
}

.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 600px;
}

.example-card {
  cursor: pointer;
  transition: all 0.3s;
}

.example-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  max-width: 800px;
}

.message.user {
  margin-left: auto;
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.message-content {
  flex: 1;
}

.message-text {
  background: white;
  padding: 12px 16px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.message.user .message-text {
  background: #409eff;
  color: white;
}

.message-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.message.user .message-time {
  text-align: right;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #409eff;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.6;
  }
  30% {
    transform: translateY(-10px);
    opacity: 1;
  }
}

.input-area {
  padding: 20px;
  background: white;
  border-top: 1px solid #e4e7ed;
}

.quick-replies {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.quick-reply { cursor: pointer; }

.llm-selector {
  margin-bottom: 12px;
}

.input-box {
  display: flex;
  gap: 12px;
}

.input-box .el-input {
  flex: 1;
}

.input-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.trip-preview {
  padding: 20px;
}
</style>
