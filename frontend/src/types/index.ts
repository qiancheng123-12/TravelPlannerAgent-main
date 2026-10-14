// TypeScript 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface POI {
  id: string
  name: string
  address: string
  location: Location
  category?: string
  rating?: number
  tel?: string
  ticket_price?: number
  visit_duration?: number
  description?: string
  image_url?: string
  city?: string
}

export interface Weather {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number | string
  night_temp: number | string
  wind_direction: string
  wind_power: string
  city?: string
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  type: string
  estimated_cost?: number
  city?: string
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner'
  name: string
  address?: string
  description?: string
  estimated_cost?: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  ticket_price?: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface TripPlan {
  city: string
  origin: string
  guests: number
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: Weather[]
  overall_suggestions: string
  budget?: Budget
}

export interface TripRequest {
  session_id?: string
  user_id?: string
  city: string
  origin: string
  guests: number
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input?: string
  llm_provider?: string
  budget: [number, number]
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
  status: TripStatus
  session_id?: string
  need_human_review?: boolean
  rag_sources?: string[]
}

export type TripStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'need_confirm'

export interface AgentStep {
  node: string
  status: string
  message?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  duration_ms?: number
  error?: string
  data?: Record<string, unknown>
}

export interface StreamingResponse {
  session_id: string
  step: number
  node: string
  status: TripStatus
  message: string
  data?: Record<string, unknown>
  thought?: string
  steps: AgentStep[]
}

export interface ChatMessage {
  session_id: string
  user_id: string
  message: string
  message_type?: string
  llm_provider?: string
}

export interface ChatResponse {
  session_id: string
  user_id: string
  response: string
  trip_plan?: TripPlan
  intent: string
  slots: Record<string, unknown>
  missing_slots: string[]
  quick_replies: string[]
  status: string
  agent_trace: Array<Record<string, unknown>>
}

export interface BookingOffer {
  offer_id: string
  provider: string
  hotel_name: string
  room_name: string
  check_in: string
  check_out: string
  guests: number
  currency: string
  total_price: number
  refundable: boolean
  expires_at: string
}

export interface UserFeedback {
  session_id: string
  action: 'approve' | 'modify' | 'reject'
  modifications?: Record<string, unknown>
  comment?: string
}

export interface LLMProvider {
  name: string
  model: string
}

export interface MemoryFact {
  memory_id: string
  key: string
  category: string
  value: unknown
  summary: string
  confidence: number
  source_session_id?: string
  created_at: string
  updated_at: string
}

export interface MemoryTrip {
  trip_id: string
  session_id: string
  city: string
  start_date?: string
  end_date?: string
  updated_at: string
}

export interface MemoryTripDetail extends MemoryTrip {
  plan: TripPlan
}

export interface MemoryProfile {
  user_id: string
  enabled: boolean
  facts: MemoryFact[]
  trips: MemoryTrip[]
}
