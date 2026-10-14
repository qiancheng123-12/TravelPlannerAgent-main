import axios from 'axios'
import type {
  TripRequest,
  TripPlanResponse,
  StreamingResponse,
  ChatMessage,
  ChatResponse,
  UserFeedback,
  TripStatus,
  MemoryProfile,
  MemoryFact,
  MemoryTripDetail
} from '@/types'
import type { BookingOffer } from '@/types'
import { getOrCreateUserId } from '@/utils/identity'

// 开发环境使用代理，生产环境使用完整 URL
const API_BASE_URL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:18080')

console.log('API_BASE_URL:', API_BASE_URL || '使用代理')

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5分钟
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - 添加调试日志
apiClient.interceptors.request.use(
  (config) => {
    console.log(
      'API Request:',
      config.method?.toUpperCase(),
      `${config.baseURL ?? ''}${config.url ?? ''}`,
      config.data
    )
    return config
  },
  (error) => {
    console.error('API Request Error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器 - 添加调试日志
apiClient.interceptors.response.use(
  (response) => {
    console.log('API Response:', response.status, response.data)
    return response
  },
  (error) => {
    console.error('API Response Error:', error.response?.status, error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// ===========================================
// 旅行规划 API
// ===========================================

/**
 * 创建旅行计划（同步）
 */
export async function createTripPlan(request: TripRequest): Promise<TripPlanResponse> {
  const response = await apiClient.post('/api/trip/plan', {
    ...request,
    user_id: request.user_id || getOrCreateUserId()
  })
  return response.data
}

/**
 * 创建旅行计划（流式）
 */
export async function createTripPlanStream(
  request: TripRequest,
  onMessage: (data: StreamingResponse) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): Promise<void> {
  const baseUrl = import.meta.env.DEV ? '' : API_BASE_URL
  const response = await fetch(`${baseUrl}/api/trip/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...request,
      user_id: request.user_id || getOrCreateUserId()
    })
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) return

  const decoder = new TextDecoder()

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const text = decoder.decode(value)
      const lines = text.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6)) as StreamingResponse
            onMessage(data)
          } catch (e) {
            console.error('Failed to parse SSE data:', e)
          }
        }
      }
    }
  } catch (error) {
    onError(error as Error)
  } finally {
    onComplete()
  }
}

/**
 * 提交用户反馈
 */
export async function submitFeedback(feedback: UserFeedback): Promise<{
  success: boolean
  message: string
  status: TripStatus
  data?: TripPlanResponse['data']
  need_human_review?: boolean
}> {
  const response = await apiClient.post('/api/trip/feedback', feedback)
  return response.data
}

/**
 * 批准行程计划
 */
export async function approveTripPlan(sessionId: string, comment?: string) {
  return submitFeedback({
    session_id: sessionId,
    action: 'approve',
    comment
  })
}

/**
 * 拒绝行程计划
 */
export async function rejectTripPlan(sessionId: string, comment?: string) {
  return submitFeedback({
    session_id: sessionId,
    action: 'reject',
    comment
  })
}

/**
 * 获取旅行计划状态
 */
export async function getTripStatus(sessionId: string): Promise<{
  session_id: string
  status: string
  current_node: string
  steps: unknown[]
  errors: string[]
}> {
  const response = await apiClient.get(`/api/trip/status/${sessionId}`)
  return response.data
}

/**
 * 获取旅行计划结果
 */
export async function getTripResult(sessionId: string): Promise<TripPlanResponse> {
  const response = await apiClient.get<TripPlanResponse>(`/api/trip/result/${sessionId}`)
  return response.data
}

// ===========================================
// 多轮对话 API
// ===========================================

/**
 * 发送聊天消息
 */
export async function sendChatMessage(request: ChatMessage): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>('/api/chat/message', request)
  return response.data
}

/**
 * 获取对话历史
 */
export async function getChatHistory(sessionId: string, userId: string): Promise<{
  session_id: string
  history: Array<{ role: string; content: string }>
}> {
  const response = await apiClient.get(`/api/chat/history/${sessionId}`, {
    params: { user_id: userId }
  })
  return response.data
}

/**
 * 清空对话历史
 */
export async function clearChatHistory(sessionId: string, userId: string): Promise<{ success: boolean }> {
  const response = await apiClient.delete(`/api/chat/history/${sessionId}`, {
    params: { user_id: userId }
  })
  return response.data
}

// ===========================================
// 长期记忆 API
// ===========================================

export async function getMemoryProfile(userId: string): Promise<MemoryProfile> {
  const response = await apiClient.get<MemoryProfile>(`/api/memory/profile/${userId}`)
  return response.data
}

export async function setMemoryEnabled(userId: string, enabled: boolean): Promise<void> {
  await apiClient.patch(`/api/memory/profile/${userId}/settings`, { enabled })
}

export async function updateMemoryFact(
  userId: string,
  memoryId: string,
  value: unknown,
  summary?: string
): Promise<MemoryFact> {
  const response = await apiClient.patch(`/api/memory/profile/${userId}/facts/${memoryId}`, {
    value,
    summary
  })
  return response.data.fact
}

export async function deleteMemoryFact(userId: string, memoryId: string): Promise<void> {
  await apiClient.delete(`/api/memory/profile/${userId}/facts/${memoryId}`)
}

export async function clearMemoryProfile(userId: string): Promise<void> {
  await apiClient.delete(`/api/memory/profile/${userId}`)
}

export async function getMemoryTrip(userId: string, tripId: string): Promise<MemoryTripDetail> {
  const response = await apiClient.get<MemoryTripDetail>(
    `/api/memory/profile/${userId}/trips/${tripId}`
  )
  return response.data
}

export async function deleteMemoryTrip(userId: string, tripId: string): Promise<void> {
  await apiClient.delete(`/api/memory/profile/${userId}/trips/${tripId}`)
}

export async function saveMemoryTrip(
  userId: string,
  sessionId: string,
  plan: MemoryTripDetail['plan']
): Promise<void> {
  await apiClient.post(`/api/memory/profile/${userId}/trips`, {
    session_id: sessionId,
    plan
  })
}

export async function importLegacyMemoryTrips(userId: string): Promise<{
  success: boolean
  imported: number
  skipped: number
  trips: MemoryProfile['trips']
}> {
  const response = await apiClient.post(`/api/memory/profile/${userId}/trips/import-legacy`)
  return response.data
}

// ===========================================
// 地图服务 API
// ===========================================

/**
 * 搜索 POI
 */
export async function searchPOI(keywords: string, city: string): Promise<{ success: boolean; data: unknown[] }> {
  const response = await apiClient.get('/api/map/poi', { params: { keywords, city } })
  return response.data
}

/**
 * 获取天气
 */
export async function getWeather(city: string): Promise<{ success: boolean; data: unknown[] }> {
  const response = await apiClient.get('/api/map/weather', { params: { city } })
  return response.data
}

/**
 * 获取静态地图图片
 */
export function getStaticMapUrl(city: string, markers?: string): string {
  const baseUrl = import.meta.env.DEV ? '' : API_BASE_URL
  let url = `${baseUrl}/api/map/staticmap?city=${encodeURIComponent(city)}`
  if (markers) {
    url += `&markers=${encodeURIComponent(markers)}`
  }
  return url
}

// ===========================================
// 系统配置 API
// ===========================================

/**
 * 获取可用的 LLM 提供商
 */
export async function getLLMProviders(): Promise<{
  current: string
  available: Array<{ name: string; model: string }>
}> {
  const response = await apiClient.get('/api/config/llm-providers')
  return response.data
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await apiClient.get('/health')
  return response.data
}

// ===========================================
// RAG 文档 ETL 与 OTA 沙箱
// ===========================================

export async function uploadKnowledgeDocument(file: File): Promise<{
  document_id: string
  filename: string
  chunks: number
  characters: number
  pages: number
  native_pages: number
  ocr_pages: number
  extraction_mode: 'native' | 'ocr' | 'hybrid'
  average_ocr_confidence: number | null
}> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post('/api/knowledge/documents', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return response.data
}

export async function getBookingQuotes(payload: {
  session_id: string; city: string; check_in: string; check_out: string;
  guests: number; hotel_name?: string; max_price?: number
}): Promise<{ mode: string; offers: BookingOffer[] }> {
  const response = await apiClient.post('/api/booking/quotes', payload)
  return response.data
}

export async function holdBooking(payload: {
  session_id: string; offer_id: string; guest_name: string; contact_phone: string
}): Promise<{ hold: { hold_id: string; confirmation_message: string }; requires_confirmation: boolean }> {
  const response = await apiClient.post('/api/booking/holds', payload)
  return response.data
}

export async function confirmBooking(payload: {
  session_id: string; hold_id: string; user_confirmed: boolean
}): Promise<{ booking: { status: string; confirmation_code?: string; message: string } }> {
  const response = await apiClient.post('/api/booking/confirm', payload)
  return response.data
}

export default apiClient
