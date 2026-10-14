const USER_ID_KEY = 'travel_planner_user_id'
const SESSION_ID_KEY = 'travel_planner_chat_session_id'

function newId(prefix: string): string {
  const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`
  return `${prefix}_${value}`
}

export function getOrCreateUserId(): string {
  let userId = localStorage.getItem(USER_ID_KEY)
  if (!userId) {
    userId = newId('user')
    localStorage.setItem(USER_ID_KEY, userId)
  }
  return userId
}

export function getSavedSessionId(): string {
  return localStorage.getItem(SESSION_ID_KEY) || ''
}

export function saveSessionId(sessionId: string): void {
  if (sessionId) localStorage.setItem(SESSION_ID_KEY, sessionId)
  else localStorage.removeItem(SESSION_ID_KEY)
}

export function createSessionId(): string {
  return newId('chat')
}
