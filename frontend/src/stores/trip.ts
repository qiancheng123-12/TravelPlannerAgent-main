import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { TripPlan, AgentStep, TripStatus } from '@/types'

const CURRENT_TRIP_STORAGE_KEY = 'travel_planner_current_trip_v1'

interface PersistedCurrentTrip {
  sessionId: string
  tripPlan: TripPlan
  status: TripStatus
  needHumanReview: boolean
}

function loadPersistedCurrentTrip(): PersistedCurrentTrip | null {
  try {
    const raw = localStorage.getItem(CURRENT_TRIP_STORAGE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as PersistedCurrentTrip
    return value?.sessionId && value?.tripPlan ? value : null
  } catch {
    localStorage.removeItem(CURRENT_TRIP_STORAGE_KEY)
    return null
  }
}

export const useTripStore = defineStore('trip', () => {
  const persisted = loadPersistedCurrentTrip()
  // 状态
  const sessionId = ref<string>(persisted?.sessionId || '')
  const tripPlan = ref<TripPlan | null>(persisted?.tripPlan || null)
  const status = ref<TripStatus>(persisted?.status || 'pending')
  const currentStep = ref<string>('')
  const steps = ref<AgentStep[]>([])
  const errors = ref<string[]>([])
  const needHumanReview = ref(persisted?.needHumanReview || false)
  const ragSources = ref<string[]>([])

  // 计算属性
  const isProcessing = computed(() => status.value === 'processing')
  const isCompleted = computed(() => status.value === 'completed')
  const hasErrors = computed(() => errors.value.length > 0)

  function persistCurrentTrip() {
    if (!sessionId.value || !tripPlan.value) {
      localStorage.removeItem(CURRENT_TRIP_STORAGE_KEY)
      return
    }
    localStorage.setItem(CURRENT_TRIP_STORAGE_KEY, JSON.stringify({
      sessionId: sessionId.value,
      tripPlan: tripPlan.value,
      status: status.value,
      needHumanReview: needHumanReview.value
    }))
  }

  // 方法
  function setSessionId(id: string) {
    sessionId.value = id
    if (tripPlan.value) persistCurrentTrip()
  }

  function setTripPlan(plan: TripPlan | null) {
    tripPlan.value = plan
    persistCurrentTrip()
  }

  function setStatus(newStatus: TripStatus) {
    status.value = newStatus
    persistCurrentTrip()
  }

  function setCurrentStep(step: string) {
    currentStep.value = step
  }

  function addStep(step: AgentStep) {
    steps.value.push(step)
  }

  function setSteps(newSteps: AgentStep[]) {
    steps.value = newSteps
  }

  function addError(error: string) {
    errors.value.push(error)
  }

  function setErrors(newErrors: string[]) {
    errors.value = newErrors
  }

  function setNeedHumanReview(need: boolean) {
    needHumanReview.value = need
    persistCurrentTrip()
  }

  function setRagSources(sources: string[]) {
    ragSources.value = sources
  }

  function reset() {
    sessionId.value = ''
    tripPlan.value = null
    status.value = 'pending'
    currentStep.value = ''
    steps.value = []
    errors.value = []
    needHumanReview.value = false
    ragSources.value = []
    localStorage.removeItem(CURRENT_TRIP_STORAGE_KEY)
  }

  return {
    // 状态
    sessionId,
    tripPlan,
    status,
    currentStep,
    steps,
    errors,
    needHumanReview,
    ragSources,
    // 计算属性
    isProcessing,
    isCompleted,
    hasErrors,
    // 方法
    setSessionId,
    setTripPlan,
    setStatus,
    setCurrentStep,
    addStep,
    setSteps,
    addError,
    setErrors,
    setNeedHumanReview,
    setRagSources,
    reset
  }
})
