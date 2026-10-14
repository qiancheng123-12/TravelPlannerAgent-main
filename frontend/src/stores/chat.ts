import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getOrCreateUserId, getSavedSessionId, saveSessionId } from '@/utils/identity'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export const useChatStore = defineStore('chat', () => {
  const userId = ref<string>(getOrCreateUserId())
  const sessionId = ref<string>(getSavedSessionId())
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)

  const hasMessages = computed(() => messages.value.length > 0)

  function setSessionId(id: string) {
    sessionId.value = id
    saveSessionId(id)
  }

  function addMessage(role: 'user' | 'assistant', content: string) {
    messages.value.push({
      role,
      content,
      timestamp: new Date()
    })
  }

  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function clearMessages() {
    messages.value = []
  }

  function replaceMessages(history: Array<{ role: string; content: string }>) {
    messages.value = history.map((message) => ({
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      timestamp: new Date()
    }))
  }

  function reset() {
    sessionId.value = ''
    saveSessionId('')
    messages.value = []
    isLoading.value = false
  }

  return {
    userId,
    sessionId,
    messages,
    isLoading,
    hasMessages,
    setSessionId,
    addMessage,
    setLoading,
    clearMessages,
    replaceMessages,
    reset
  }
})
