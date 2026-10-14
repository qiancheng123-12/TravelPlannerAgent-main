<template>
  <div class="home-container">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>

    <!-- 头部 -->
    <header class="header">
      <nav class="nav-bar">
        <a class="brand" href="#" aria-label="远游首页">
          <span class="brand-mark"><el-icon><Location /></el-icon></span>
          <span>远游 <small>AI TRAVEL</small></span>
        </a>
        <div class="nav-actions">
          <el-button
            v-if="tripStore.tripPlan"
            class="chat-entry"
            round
            @click="router.push('/result')"
          >📍 当前行程</el-button>
          <el-button class="chat-entry" round @click="router.push('/memory#trips')">
            📋 历史行程
          </el-button>
          <el-button class="chat-entry" round @click="router.push('/memory')">
            🧠 我的记忆
          </el-button>
          <el-button class="chat-entry" round @click="router.push('/chat')">
            <el-icon><ChatDotRound /></el-icon>
            对话规划
          </el-button>
        </div>
      </nav>

      <div class="hero-copy">
        <span class="eyebrow">YOUR NEXT STORY STARTS HERE</span>
        <h1>把想去的地方，<br><em>变成一段好旅程。</em></h1>
        <p>告诉我们目的地与偏好，多位 AI 旅行顾问会一起为你整理路线、住宿与预算。</p>
        <div class="hero-meta">
          <span><b>01</b> 填写旅行期待</span>
          <i></i>
          <span><b>02</b> AI 协同规划</span>
          <i></i>
          <span><b>03</b> 收获专属行程</span>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-content" :class="{ 'has-progress': isLoading || steps.length > 0 }">
      <!-- 左侧：表单输入 -->
      <el-card class="form-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="section-number">01</span>
            <div>
              <span>定制你的行程</span>
              <small>几个简单选项，让计划更懂你</small>
            </div>
          </div>
        </template>

        <el-form :model="formData" label-position="top" @submit.prevent="handleSubmit">
          <!-- 城市和日期 -->
          <el-row :gutter="20">
            <el-col :span="6">
              <el-form-item label="出发地" required>
                <el-input v-model="formData.origin" placeholder="例如：宁波">
                  <template #prefix>
                    <el-icon><Position /></el-icon>
                  </template>
                </el-input>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="目的地城市" required>
                <el-input v-model="formData.city" placeholder="例如：北京、上海、成都">
                  <template #prefix>
                    <el-icon><Location /></el-icon>
                  </template>
                </el-input>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="出发日期" required>
                <el-date-picker
                  v-model="formData.start_date"
                  type="date"
                  placeholder="选择日期"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="返回日期" required>
                <el-date-picker
                  v-model="formData.end_date"
                  type="date"
                  placeholder="选择日期"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 旅行天数显示 -->
          <el-alert
            v-if="travelDays > 0"
            :title="`共 ${travelDays} 天行程`"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 20px"
          />

          <!-- 偏好设置 -->
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="交通方式">
                <el-select v-model="formData.transportation" style="width: 100%">
                  <el-option label="🚇 公共交通" value="公共交通" />
                  <el-option label="🚗 自驾" value="自驾" />
                  <el-option label="🚶 步行" value="步行" />
                  <el-option label="🔀 混合" value="混合" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="住宿偏好">
                <el-select v-model="formData.accommodation" style="width: 100%">
                  <el-option label="💰 经济型酒店" value="经济型酒店" />
                  <el-option label="🏨 舒适型酒店" value="舒适型酒店" />
                  <el-option label="⭐ 豪华酒店" value="豪华酒店" />
                  <el-option label="🏡 民宿" value="民宿" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="出行人数">
                <el-input-number v-model="formData.guests" :min="1" :max="20" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 旅行偏好 -->
          <el-form-item label="旅行偏好">
            <el-checkbox-group v-model="formData.preferences">
              <el-checkbox label="历史文化" border>🏛️ 历史文化</el-checkbox>
              <el-checkbox label="自然风光" border>🏞️ 自然风光</el-checkbox>
              <el-checkbox label="美食" border>🍜 美食</el-checkbox>
              <el-checkbox label="购物" border>🛍️ 购物</el-checkbox>
              <el-checkbox label="艺术" border>🎨 艺术</el-checkbox>
              <el-checkbox label="休闲" border>☕ 休闲</el-checkbox>
            </el-checkbox-group>
          </el-form-item>

          <!-- 额外要求 -->
          <el-form-item label="额外要求">
            <el-input
              v-model="formData.free_text_input"
              type="textarea"
              :rows="3"
              placeholder="请输入您的额外要求，例如：想去看升旗、需要无障碍设施..."
            />
          </el-form-item>

          <!-- 预算设置 -->
          <el-form-item label="预算范围">
            <div class="budget-slider-container">
              <el-slider
                v-model="formData.budget"
                range
                :min="500"
                :max="10000"
                :step="100"
                :format-tooltip="(val: number) => `¥${val}`"
              />
              <div class="budget-display">
                <el-tag type="success">¥{{ formData.budget[0] }}</el-tag>
                <span> - </span>
                <el-tag type="warning">¥{{ formData.budget[1] }}</el-tag>
                <span class="budget-label">（{{ budgetLevel }}）</span>
              </div>
            </div>
          </el-form-item>

          <!-- LLM 选择 -->
          <el-form-item label="AI 模型">
            <el-radio-group v-model="formData.llm_provider">
              <el-radio label="deepseek">DeepSeek</el-radio>
              <el-radio label="aliyun">阿里云百炼</el-radio>
            </el-radio-group>
          </el-form-item>

          <!-- 提交按钮 -->
          <el-form-item>
            <el-button
              v-if="!isLoading"
              type="primary"
              size="large"
              @click="handleSubmit"
              style="width: 100%"
            >
              <el-icon><Promotion /></el-icon>
              开始规划行程
            </el-button>
            <el-button
              v-else
              type="danger"
              size="large"
              @click="handleStop"
              style="width: 100%"
            >
              <el-icon><Close /></el-icon>
              终止规划
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 右侧：执行进度 -->
      <el-card v-if="isLoading || steps.length > 0" class="progress-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Loading /></el-icon>
            <span>Agent 执行进度</span>
          </div>
        </template>

        <el-timeline>
          <el-timeline-item
            v-for="(step, index) in steps"
            :key="index"
            :type="getStepType(step.status)"
            :title="step.node"
          >
            <div class="step-content">
              <div class="step-header">
                <span class="step-name">{{ getNodeName(step.node) }}</span>
                <el-tag :type="getStepType(step.status)" size="small">
                  {{ step.status }}
                </el-tag>
              </div>
              <div v-if="step.message" class="step-message">
                {{ step.message }}
              </div>
              <div v-if="step.error" class="step-error">
                <el-icon><WarningFilled /></el-icon>
                {{ step.error }}
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>

        <!-- 当前状态提示 -->
        <div v-if="isLoading && currentMessage" class="current-status">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ currentMessage }}</span>
        </div>

        <el-progress
          v-if="isLoading"
          :percentage="progress"
          :status="progressStatus"
          :stroke-width="10"
          style="margin-top: 20px"
        />
      </el-card>
    </main>

    <!-- 底部链接 -->
    <footer class="footer">LANGGRAPH MULTI-AGENT · MADE FOR CURIOUS TRAVELLERS</footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Location, Promotion, Loading, WarningFilled, ChatDotRound, Close, Position } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import { useTripStore } from '@/stores/trip'
import type { TripRequest, AgentStep } from '@/types'
import { getOrCreateUserId } from '@/utils/identity'

const router = useRouter()
const tripStore = useTripStore()

const formData = ref<TripRequest>({
  user_id: getOrCreateUserId(),
  city: '',
  origin: '',
  guests: 1,
  start_date: '',
  end_date: '',
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: '',
  llm_provider: 'deepseek',
  budget: [1000, 3000] as [number, number]
})

const isLoading = ref(false)
const isStopped = ref(false)
const steps = ref<AgentStep[]>([])
const progress = ref(0)
const currentStep = ref('')
const currentMessage = ref('')
const abortController = ref<AbortController | null>(null)

// 计算旅行天数
const travelDays = computed(() => {
  if (formData.value.start_date && formData.value.end_date) {
    const start = dayjs(formData.value.start_date)
    const end = dayjs(formData.value.end_date)
    const days = end.diff(start, 'day') + 1
    return days > 0 ? days : 0
  }
  return 0
})

// 预算等级
const budgetLevel = computed(() => {
  const max = formData.value.budget[1]
  if (max <= 1500) return '经济出行'
  if (max <= 3000) return '舒适旅行'
  if (max <= 5000) return '品质游玩'
  if (max <= 8000) return '高端体验'
  return '奢华之旅'
})

// 监听日期变化
watch(travelDays, (days) => {
  formData.value.travel_days = days
})

// 进度状态
const progressStatus = computed(() => {
  if (progress.value >= 100) return 'success'
  if (progress.value >= 80) return 'warning'
  return ''
})

// 获取步骤类型
function getStepType(status: string): 'primary' | 'success' | 'danger' | 'info' {
  switch (status) {
    case 'completed': return 'success'
    case 'running': return 'primary'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

// 获取节点名称
function getNodeName(node: string): string {
  const names: Record<string, string> = {
    'init': '🚀 初始化',
    'poi_search': '🔍 景点搜索',
    'weather': '🌤️ 天气查询',
    'hotel': '🏨 酒店推荐',
    'rag_retrieve': '📚 RAG 知识检索',
    'planner': '📋 行程规划',
    'human_review': '👤 等待审核',
    'complete': '✅ 完成',
    'stopped': '⏹️ 已终止',
    'error': '❌ 错误'
  }
  return names[node] || node
}

// 提交表单
async function handleSubmit() {
  if (!formData.value.origin || !formData.value.city || !formData.value.start_date || !formData.value.end_date) {
    ElMessage.warning('请填写完整信息')
    return
  }

  isLoading.value = true
  isStopped.value = false
  steps.value = []
  progress.value = 0
  currentStep.value = '正在准备...'
  currentMessage.value = '正在初始化...'

  const sessionId = `session_${Date.now()}`
  tripStore.setSessionId(sessionId)

  // 创建 AbortController 用于取消请求
  abortController.value = new AbortController()

  try {
    // 使用流式API获取实时反馈
    const baseUrl = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:18080')
    const response = await fetch(`${baseUrl}/api/trip/plan/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...formData.value,
        session_id: sessionId
      }),
      signal: abortController.value.signal
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('无法读取响应流')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      if (isStopped.value) {
        reader.cancel()
        break
      }

      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            handleStreamEvent(data)
          } catch (e) {
            console.error('Failed to parse SSE data:', e)
          }
        }
      }
    }

    // 处理剩余的buffer
    if (buffer.startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.slice(6))
        handleStreamEvent(data)
      } catch (e) {
        console.error('Failed to parse remaining SSE data:', e)
      }
    }

  } catch (error: any) {
    if (error.name === 'AbortError') {
      ElMessage.info('已终止规划')
      steps.value.push({ node: 'stopped', status: 'failed', message: '用户终止' })
    } else {
      console.error('[Home] 请求错误:', error)
      ElMessage.error(error.message || '请求失败')
      tripStore.addError(error.message)
      steps.value.push({ node: 'error', status: 'failed', error: error.message })
    }
  } finally {
    isLoading.value = false
    abortController.value = null
  }
}

// 处理流式事件
function handleStreamEvent(data: any) {
  console.log('[Home] 收到事件:', data)

  // 更新当前消息
  if (data.message) {
    currentMessage.value = data.message
  }

  // 更新步骤列表
  if (data.node) {
    // 新节点开始时，结束此前仍显示 running 的节点（例如初始化）。
    steps.value = steps.value.map((item) => (
      item.status === 'running' && item.node !== data.node
        ? { ...item, status: 'completed' }
        : item
    ))

    const existingIndex = steps.value.findIndex(s => s.node === data.node)
    const step: AgentStep = {
      node: data.node,
      status: data.status,
      message: data.message,
      data: data.data
    }

    if (existingIndex >= 0) {
      steps.value[existingIndex] = step
    } else {
      steps.value.push(step)
    }

    // 工作流主要里程碑：初始化、Supervisor、4类工具、规划、校验。
    // Agent 的工具顺序是动态的，不能用后端固定 step 编号直接覆盖百分比。
    const completedNodes = new Set(
      steps.value
        .filter(item => item.status === 'completed')
        .map(item => item.node)
    ).size
    const hasRunningNode = steps.value.some(item => item.status === 'running')
    const milestoneProgress = Math.min(
      90,
      Math.round(((completedNodes + (hasRunningNode ? 0.35 : 0)) / 8) * 90)
    )
    const backendProgress = data.step ? Math.min(Number(data.step) * 10, 90) : 0
    // 进度只能单调递增，Supervisor 循环回到 step=1 时不能回退。
    progress.value = Math.max(progress.value, milestoneProgress, backendProgress)
  }

  // 处理完成
  if (data.node === 'complete' && data.status === 'completed') {
    progress.value = 100

    if (data.data?.itinerary) {
      tripStore.setTripPlan(data.data.itinerary as any)
      tripStore.setStatus('completed')
      tripStore.setNeedHumanReview(false)

      ElMessage.success('行程规划完成！')

      setTimeout(() => {
        router.push('/result')
      }, 500)
    }
  }

  // LangGraph 在人工审核 interrupt 处暂停，展示草稿并跳转审核页
  if (data.node === 'human_review' && data.status === 'need_confirm') {
    progress.value = 100
    if (data.data?.itinerary) {
      tripStore.setTripPlan(data.data.itinerary)
      tripStore.setStatus('need_confirm')
      tripStore.setNeedHumanReview(true)
      tripStore.setRagSources(data.data?.rag_sources || [])
      ElMessage.success('行程草稿已生成，请审核')
      setTimeout(() => router.push('/result'), 500)
    }
  }

  if (data.node === 'rag_retrieve' && Array.isArray(data.data?.sources)) {
    tripStore.setRagSources(data.data.sources)
  }

  // 处理错误
  if (data.status === 'failed' || data.node === 'error') {
    ElMessage.error(data.message || '规划失败')
  }
}

// 终止规划
function handleStop() {
  if (abortController.value) {
    isStopped.value = true
    abortController.value.abort()
  }
}
</script>

<style scoped>
.home-container {
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  background: #f3efe6;
  padding: 0 28px 28px;
  color: #173b36;
}

.header {
  position: relative;
  z-index: 1;
  max-width: 1180px;
  margin: 0 auto;
}

.nav-bar {
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(23, 59, 54, .16);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #173b36;
  text-decoration: none;
  font-family: Georgia, 'Noto Serif SC', serif;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: .08em;
}

.brand small {
  display: block;
  margin-top: 2px;
  color: #7d8b79;
  font-family: Arial, sans-serif;
  font-size: 8px;
  letter-spacing: .24em;
}

.brand-mark {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50% 50% 50% 10px;
  background: #e45b3c;
  color: white;
  transform: rotate(-8deg);
}

.brand-mark .el-icon { transform: rotate(8deg); }

.chat-entry {
  border-color: rgba(23, 59, 54, .22);
  background: rgba(255, 255, 255, .42);
  color: #173b36;
}

.nav-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-actions :deep(.el-button + .el-button) { margin-left: 0; }

.hero-copy {
  max-width: 790px;
  padding: 68px 0 54px;
}

.eyebrow {
  color: #e45b3c;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .22em;
}

.header h1 {
  margin: 16px 0 18px;
  font-family: Georgia, 'Noto Serif SC', 'Songti SC', serif;
  font-size: clamp(42px, 6vw, 76px);
  line-height: 1.08;
  font-weight: 500;
  letter-spacing: -.04em;
}

.header h1 em {
  color: #e45b3c;
  font-weight: 500;
}

.header p {
  max-width: 620px;
  color: #66756f;
  font-size: 16px;
  line-height: 1.8;
}

.hero-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 30px;
  color: #66756f;
  font-size: 12px;
}

.hero-meta b { color: #173b36; margin-right: 5px; }
.hero-meta i { width: 38px; height: 1px; background: #c7c6b8; }

.ambient {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
}

.ambient-one {
  width: 390px;
  height: 390px;
  top: 95px;
  right: -95px;
  border: 70px solid rgba(229, 168, 67, .2);
}

.ambient-two {
  width: 170px;
  height: 170px;
  top: 210px;
  right: 210px;
  background: rgba(74, 128, 110, .12);
}

.main-content {
  position: relative;
  z-index: 2;
  max-width: 1200px;
  margin: 0 auto;
}

.main-content.has-progress {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  align-items: start;
  gap: 24px;
}

@media (max-width: 900px) {
  .nav-bar { height: auto; min-height: 70px; padding: 12px 0; gap: 12px; }
  .nav-actions { gap: 6px; }
  .nav-actions .el-button { padding: 8px 12px; }
  .main-content.has-progress {
    grid-template-columns: 1fr;
  }
}

.form-card, .progress-card {
  border: 1px solid rgba(23, 59, 54, .1);
  border-radius: 24px;
  box-shadow: 0 24px 70px rgba(50, 61, 45, .1);
  background: rgba(255, 253, 248, .92);
}

.form-card :deep(.el-card__header),
.progress-card :deep(.el-card__header) {
  padding: 24px 28px;
  border-bottom-color: #e9e4d8;
}

.form-card :deep(.el-card__body) { padding: 28px; }

.form-card :deep(.el-form-item__label) {
  color: #294c46;
  font-weight: 650;
}

.form-card :deep(.el-input__wrapper),
.form-card :deep(.el-select__wrapper),
.form-card :deep(.el-textarea__inner) {
  border-radius: 10px;
  box-shadow: 0 0 0 1px #dcd8cc inset;
  background: #faf8f2;
}

.form-card :deep(.el-checkbox.is-bordered) { border-radius: 999px; }
.form-card :deep(.el-checkbox.is-checked) { background: #edf3ed; border-color: #507c6e; }
.form-card :deep(.el-button--primary) {
  height: 52px;
  border: 0;
  border-radius: 12px;
  background: #e45b3c;
  font-weight: 700;
  letter-spacing: .08em;
  box-shadow: 0 10px 25px rgba(228, 91, 60, .24);
}

.form-card :deep(.el-slider) { --el-slider-main-bg-color: #e45b3c; }
.form-card :deep(.el-radio__input.is-checked .el-radio__inner) { background: #507c6e; border-color: #507c6e; }
.form-card :deep(.el-radio__input.is-checked + .el-radio__label) { color: #294c46; }

.section-number {
  color: #e45b3c;
  font-family: Georgia, serif;
  font-size: 28px;
  font-style: italic;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.card-header > div { display: flex; flex-direction: column; }
.card-header small { margin-top: 4px; color: #8a928b; font-size: 12px; font-weight: 400; }

.step-content {
  padding: 8px 0;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.step-name {
  font-weight: 500;
}

.step-error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.step-message {
  color: #606266;
  font-size: 13px;
  margin-top: 4px;
}

.current-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #edf3ed;
  border-radius: 8px;
  color: #416c5e;
  font-size: 14px;
  margin-top: 12px;
}

.current-status .el-icon {
  font-size: 16px;
}

.budget-slider-container {
  width: 100%;
}

.budget-display {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  justify-content: center;
}

.budget-label {
  color: #909399;
  font-size: 13px;
}

.footer {
  text-align: center;
  margin-top: 30px;
  color: #8a928b;
  font-size: 10px;
  letter-spacing: .16em;
}

@media (max-width: 700px) {
  .home-container { padding: 0 14px 20px; }
  .nav-bar { height: 70px; }
  .hero-copy { padding: 46px 4px 36px; }
  .header h1 { font-size: 42px; }
  .hero-meta { align-items: flex-start; gap: 8px; }
  .hero-meta i { width: 14px; margin-top: 8px; }
  .form-card :deep(.el-card__body) { padding: 20px; }
  .form-card :deep(.el-col-12),
  .form-card :deep(.el-col-6) { max-width: 100%; flex: 0 0 100%; }
  .ambient-one { right: -260px; }
}
</style>
