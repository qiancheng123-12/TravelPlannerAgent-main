<template>
  <div class="result-container">
    <!-- 头部 -->
    <div class="header">
      <el-button @click="$router.push('/')" text>
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </el-button>
      <h1>📋 行程规划结果</h1>
      <div class="header-actions">
        <el-button type="success" :disabled="!tripPlan" @click="openHandoffDialog">
          <el-icon><Position /></el-icon>
          前往平台预订
        </el-button>
        <el-button :disabled="!tripStore.sessionId" @click="openBookingDialog">
          <el-icon><House /></el-icon>
          模拟交易流程
        </el-button>
        <el-button type="primary" @click="handleExportPDF">
          <el-icon><Download /></el-icon>
          导出PDF
        </el-button>
        <el-button @click="handleReset">
          <el-icon><Refresh /></el-icon>
          重新规划
        </el-button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="!tripPlan" class="empty-state">
      <el-empty description="暂无行程数据">
        <el-button type="primary" @click="$router.push('/')">开始规划</el-button>
      </el-empty>
    </div>

    <!-- 行程内容 -->
    <div v-else class="content">
      <!-- 概览卡片 -->
      <el-card class="overview-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Location /></el-icon>
            <span>行程概览</span>
          </div>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="出发地">{{ tripPlan.origin || '未记录' }}</el-descriptions-item>
          <el-descriptions-item label="目的地">{{ tripPlan.city }}</el-descriptions-item>
          <el-descriptions-item label="出行人数">{{ tripPlan.guests || 1 }}人</el-descriptions-item>
          <el-descriptions-item label="出发日期">{{ tripPlan.start_date }}</el-descriptions-item>
          <el-descriptions-item label="返回日期">{{ tripPlan.end_date }}</el-descriptions-item>
          <el-descriptions-item label="行程天数">{{ tripPlan.days?.length || 0 }}天</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- RAG 检索依据 -->
      <el-card v-if="tripStore.ragSources.length" class="rag-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Reading /></el-icon>
            <span>RAG 检索依据</span>
          </div>
        </template>
        <div class="rag-sources">
          <el-tag
            v-for="source in tripStore.ragSources"
            :key="source"
            type="success"
            effect="plain"
          >
            {{ source }}
          </el-tag>
        </div>
      </el-card>

      <!-- 地图展示 -->
      <el-card class="map-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><MapLocation /></el-icon>
            <span>景点地图</span>
          </div>
        </template>
        <div id="map-container" class="map-container"></div>
      </el-card>

      <!-- 每日行程 -->
      <el-card class="itinerary-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Calendar /></el-icon>
            <span>每日行程</span>
          </div>
        </template>
        <el-collapse v-model="activeDays">
          <el-collapse-item
            v-for="(day, index) in tripPlan.days"
            :key="index"
            :name="index"
          >
            <template #title>
              <div class="day-title">
                <el-tag type="primary">第{{ day.day_index + 1 }}天</el-tag>
                <span class="day-date">{{ day.date }}</span>
                <span class="day-theme">{{ day.description }}</span>
              </div>
            </template>

            <!-- 景点列表 -->
            <el-timeline>
              <el-timeline-item
                v-for="(attraction, attrIndex) in day.attractions"
                :key="attrIndex"
                placement="top"
              >
                <el-card class="spot-card">
                  <div class="spot-header">
                    <h4>{{ attraction.name }}</h4>
                    <el-tag v-if="attraction.category" size="small">{{ attraction.category }}</el-tag>
                  </div>
                  <div class="spot-info">
                    <p v-if="attraction.description">{{ attraction.description }}</p>
                    <div class="spot-details">
                      <span v-if="attraction.visit_duration">
                        <el-icon><Clock /></el-icon>
                        游玩时长: {{ attraction.visit_duration }}分钟
                      </span>
                      <span v-if="attraction.ticket_price">
                        <el-icon><Ticket /></el-icon>
                        门票: ¥{{ attraction.ticket_price }}
                      </span>
                    </div>
                    <div class="spot-address">
                      <el-icon><Location /></el-icon>
                      {{ attraction.address }}
                    </div>
                  </div>
                </el-card>
              </el-timeline-item>
            </el-timeline>

            <!-- 餐饮推荐 -->
            <div v-if="day.meals && day.meals.length > 0" class="dining-section">
              <h4><el-icon><Food /></el-icon> 餐饮推荐</h4>
              <el-row :gutter="12">
                <el-col v-for="(meal, mealIndex) in day.meals" :key="mealIndex" :span="8">
                  <el-card shadow="hover" class="meal-card">
                    <div class="meal-type">{{ meal.type === 'breakfast' ? '早餐' : meal.type === 'lunch' ? '午餐' : '晚餐' }}</div>
                    <div class="meal-name">{{ meal.name }}</div>
                    <div class="meal-cuisine">{{ meal.description }}</div>
                    <div v-if="meal.estimated_cost" class="meal-price">预估: ¥{{ meal.estimated_cost }}</div>
                  </el-card>
                </el-col>
              </el-row>
            </div>

            <!-- 住宿信息 -->
            <div v-if="day.hotel" class="accommodation-section">
              <h4><el-icon><House /></el-icon> 住宿安排</h4>
              <el-card shadow="hover">
                <div class="hotel-info">
                  <div class="hotel-name">{{ day.hotel.name }}</div>
                  <div class="hotel-details">
                    <span v-if="day.hotel.type">{{ day.hotel.type }}</span>
                    <span v-if="day.hotel.price_range">{{ day.hotel.price_range }}</span>
                    <span v-if="day.hotel.rating">
                      <el-icon><Star /></el-icon>
                      {{ day.hotel.rating }}
                    </span>
                  </div>
                  <div v-if="day.hotel.address" class="hotel-address">
                    <el-icon><Location /></el-icon>
                    {{ day.hotel.address }}
                  </div>
                </div>
              </el-card>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <!-- 总预算 -->
      <el-card v-if="tripPlan.budget" class="budget-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Wallet /></el-icon>
            <span>预算估算</span>
          </div>
        </template>
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="景点门票" :value="tripPlan.budget.total_attractions" suffix="元" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="住宿费用" :value="tripPlan.budget.total_hotels" suffix="元" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="餐饮费用" :value="tripPlan.budget.total_meals" suffix="元" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="交通费用" :value="tripPlan.budget.total_transportation" suffix="元" />
          </el-col>
        </el-row>
        <el-divider />
        <el-statistic
          title="总预算"
          :value="tripPlan.budget.total"
          suffix="元"
          class="total-budget"
        />
      </el-card>

      <!-- 总体建议 -->
      <el-card v-if="tripPlan.overall_suggestions" class="tips-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <el-icon><Warning /></el-icon>
            <span>旅行建议</span>
          </div>
        </template>
        <p style="line-height: 1.8; color: #606266;">{{ tripPlan.overall_suggestions }}</p>
      </el-card>
    </div>

    <!-- 人工审核对话框 -->
    <el-dialog v-model="showReviewDialog" title="行程确认" width="600px">
      <div class="review-content">
        <el-alert
          title="请确认您的行程安排"
          type="warning"
          description="AI已为您生成行程规划，请仔细核对后确认。"
          :closable="false"
          show-icon
        />
        <div class="review-actions">
          <el-input
            v-model="reviewComment"
            type="textarea"
            :rows="3"
            placeholder="如有修改意见，请在此输入..."
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="handleReject">重新规划</el-button>
        <el-button type="primary" @click="handleApprove">确认行程</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showHandoffDialog" title="第三方平台预订交接" width="640px">
      <el-alert
        title="本系统不会在飞猪或携程创建订单"
        description="平台按钮只打开官方酒店入口，不会把整段说明当成搜索词。请在平台内填写目的地和日期，并核对实时价格、库存及退改规则。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-descriptions :column="1" border style="margin-top: 18px">
        <el-descriptions-item label="目的地">{{ tripPlan?.city }}</el-descriptions-item>
        <el-descriptions-item label="入住日期">{{ tripPlan?.start_date }}</el-descriptions-item>
        <el-descriptions-item label="离店日期">{{ bookingCheckOutDate }}</el-descriptions-item>
        <el-descriptions-item label="推荐酒店">{{ handoffHotelName || '请在平台内选择酒店' }}</el-descriptions-item>
      </el-descriptions>
      <div class="handoff-copy">
        <el-input :model-value="bookingHandoffText" type="textarea" :rows="4" readonly />
        <el-button @click="copyBookingHandoff">复制预订信息</el-button>
        <el-button @click="copyHotelSearchKeyword">复制酒店搜索词</el-button>
      </div>
      <template #footer>
        <el-button @click="showHandoffDialog = false">取消</el-button>
        <el-button @click="openBookingPlatform('fliggy')">打开飞猪酒店页</el-button>
        <el-button type="primary" @click="openBookingPlatform('ctrip')">打开携程酒店页</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showBookingDialog" title="模拟交易流程（技术演示，不会真实扣款）" width="680px">
      <el-alert
        title="该功能只用于验证报价、锁单、幂等和确认状态机，不代表飞猪或携程真实订单。"
        type="info"
        :closable="false"
        show-icon
      />
      <div v-if="!bookingResult" style="margin-top: 18px">
        <el-radio-group v-model="selectedOfferId" class="offer-list">
          <el-radio v-for="offer in bookingOffers" :key="offer.offer_id" :label="offer.offer_id" border>
            {{ offer.hotel_name }} · {{ offer.room_name }} · ¥{{ offer.total_price }}
          </el-radio>
        </el-radio-group>
        <el-form label-width="90px" style="margin-top: 18px">
          <el-form-item label="入住人"><el-input v-model="guestName" /></el-form-item>
          <el-form-item label="联系电话"><el-input v-model="contactPhone" /></el-form-item>
        </el-form>
        <el-button v-if="!holdId" type="primary" :loading="bookingLoading" @click="handleHoldBooking">锁定报价</el-button>
        <template v-else>
          <el-alert :title="holdMessage" type="warning" :closable="false" />
          <el-checkbox v-model="bookingConfirmed" style="margin: 16px 0">我已核对价格、日期与入住人，并确认创建沙箱订单</el-checkbox>
          <div><el-button type="success" :disabled="!bookingConfirmed" :loading="bookingLoading" @click="handleConfirmBooking">确认模拟预订</el-button></div>
        </template>
      </div>
      <el-result v-else icon="success" title="沙箱订单已确认" :sub-title="`确认码：${bookingResult}`" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import {
  ArrowLeft, Download, Refresh, Location, MapLocation, Calendar,
  Clock, Ticket, Star, Food, House, Wallet, Warning, Reading, Position
} from '@element-plus/icons-vue'
import { useTripStore } from '@/stores/trip'
import { approveTripPlan, rejectTripPlan, getBookingQuotes, holdBooking, confirmBooking } from '@/services/api'
import type { BookingOffer } from '@/types'

const router = useRouter()
const tripStore = useTripStore()

const tripPlan = ref(tripStore.tripPlan)
const activeDays = ref<number[]>([0])
const showReviewDialog = ref(false)
const reviewComment = ref('')
const mapInstance = ref<any>(null)
const mapLoaded = ref(false)
const showBookingDialog = ref(false)
const showHandoffDialog = ref(false)
const bookingOffers = ref<BookingOffer[]>([])
const selectedOfferId = ref('')
const guestName = ref('')
const contactPhone = ref('')
const holdId = ref('')
const holdMessage = ref('')
const bookingConfirmed = ref(false)
const bookingLoading = ref(false)
const bookingResult = ref('')

const handoffHotelName = computed(() =>
  tripPlan.value?.days.find(day => day.hotel)?.hotel?.name || ''
)

// 行程结束日等于入住日时，酒店预订至少需要一晚，因此将离店日顺延一天。
const bookingCheckOutDate = computed(() => {
  if (!tripPlan.value) return ''
  const checkIn = dayjs(tripPlan.value.start_date)
  const tripEnd = dayjs(tripPlan.value.end_date)
  return (tripEnd.isAfter(checkIn) ? tripEnd : checkIn.add(1, 'day')).format('YYYY-MM-DD')
})

const hotelSearchKeyword = computed(() =>
  [tripPlan.value?.city, handoffHotelName.value].filter(Boolean).join(' ')
)

const bookingHandoffText = computed(() => {
  if (!tripPlan.value) return ''
  return [
    `目的地：${tripPlan.value.city}`,
    `入住日期：${tripPlan.value.start_date}`,
    `离店日期：${bookingCheckOutDate.value}`,
    `推荐酒店：${handoffHotelName.value || '待选择'}`,
    '请在第三方平台核对实时价格、库存和退改规则。'
  ].join('\n')
})

function openHandoffDialog() {
  showHandoffDialog.value = true
}

async function copyBookingHandoff(showMessage = true) {
  try {
    await navigator.clipboard.writeText(bookingHandoffText.value)
    if (showMessage) ElMessage.success('预订信息已复制')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = bookingHandoffText.value
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    if (showMessage) ElMessage.success('预订信息已复制')
  }
}

async function copyHotelSearchKeyword() {
  const text = hotelSearchKeyword.value || tripPlan.value?.city || ''
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  ElMessage.success(`已复制搜索词：${text}`)
}

function openBookingPlatform(platform: 'fliggy' | 'ctrip') {
  const officialUrls = {
    fliggy: 'https://www.fliggy.com/',
    ctrip: 'https://hotels.ctrip.com/hotels'
  }
  window.open(officialUrls[platform], '_blank', 'noopener,noreferrer')
  ElMessage.info('已打开官方酒店页，请手动填写目的地、入住日期和离店日期')
}

async function openBookingDialog() {
  if (!tripPlan.value || !tripStore.sessionId) return
  showBookingDialog.value = true
  bookingLoading.value = true
  try {
    const firstHotel = tripPlan.value.days.find(day => day.hotel)?.hotel
    const result = await getBookingQuotes({
      session_id: tripStore.sessionId,
      city: tripPlan.value.city,
      check_in: tripPlan.value.start_date,
      check_out: bookingCheckOutDate.value,
      guests: tripPlan.value.guests || 1,
      hotel_name: firstHotel?.name
    })
    bookingOffers.value = result.offers
    selectedOfferId.value = result.offers[0]?.offer_id || ''
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || 'OTA 报价失败')
  } finally {
    bookingLoading.value = false
  }
}

async function handleHoldBooking() {
  if (!tripStore.sessionId || !selectedOfferId.value || !guestName.value || !contactPhone.value) {
    ElMessage.warning('请选择报价并填写入住人与联系电话')
    return
  }
  bookingLoading.value = true
  try {
    const result = await holdBooking({
      session_id: tripStore.sessionId,
      offer_id: selectedOfferId.value,
      guest_name: guestName.value,
      contact_phone: contactPhone.value
    })
    holdId.value = result.hold.hold_id
    holdMessage.value = result.hold.confirmation_message
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '锁单失败')
  } finally {
    bookingLoading.value = false
  }
}

async function handleConfirmBooking() {
  if (!tripStore.sessionId || !holdId.value || !bookingConfirmed.value) return
  bookingLoading.value = true
  try {
    const result = await confirmBooking({
      session_id: tripStore.sessionId,
      hold_id: holdId.value,
      user_confirmed: true
    })
    bookingResult.value = result.booking.confirmation_code || 'SANDBOX-CONFIRMED'
    ElMessage.success(result.booking.message)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '确认失败')
  } finally {
    bookingLoading.value = false
  }
}

// 初始化地图
async function initMap() {
  if (!tripPlan.value?.city) {
    console.log('[Map] 没有城市信息，跳过地图初始化')
    return
  }

  console.log('[Map] 开始初始化地图，城市:', tripPlan.value.city)

  await nextTick()

  const container = document.getElementById('map-container')
  if (!container) {
    console.error('[Map] 找不到地图容器')
    return
  }

  console.log('[Map] 地图容器已找到, offsetWidth:', container.offsetWidth, 'offsetHeight:', container.offsetHeight)

  const amapKey = import.meta.env.VITE_AMAP_KEY
  console.log('[Map] 高德地图 Key:', amapKey ? amapKey.substring(0, 8) + '...' : '未配置')

  if (!amapKey) {
    console.error('[Map] 高德地图 API Key 未配置')
    return
  }

  try {
    // 动态加载高德地图
    const AMap = (window as any).AMap
    if (!AMap) {
      console.log('[Map] 加载高德地图脚本...')
      const script = document.createElement('script')
      // 使用1.4版本，更稳定，不需要安全密钥
      script.src = `https://webapi.amap.com/maps?v=1.4.15&key=${amapKey}&plugin=AMap.Geocoder,AMap.Scale,AMap.ToolBar`
      script.onload = () => {
        console.log('[Map] 高德地图脚本加载成功')
        mapLoaded.value = true
        // 等待DOM更新后创建地图
        setTimeout(() => createMap(), 100)
      }
      script.onerror = (e) => {
        console.error('[Map] 高德地图脚本加载失败:', e)
      }
      document.head.appendChild(script)
    } else {
      console.log('[Map] 高德地图已存在')
      mapLoaded.value = true
      createMap()
    }
  } catch (error) {
    console.error('[Map] 地图初始化失败:', error)
  }
}

function createMap() {
  const AMap = (window as any).AMap
  if (!AMap) {
    console.error('[Map] AMap 未定义')
    return
  }

  if (!tripPlan.value) {
    console.error('[Map] tripPlan 未定义')
    return
  }

  const currentPlan = tripPlan.value

  console.log('[Map] 创建地图实例...')
  console.log('[Map] tripPlan数据:', JSON.stringify(tripPlan.value, null, 2))

  // 先获取城市坐标，然后创建地图
  const city = currentPlan.city
  console.log('[Map] 目标城市:', city)

  const geocoder = new AMap.Geocoder()

  // 先获取城市坐标
  geocoder.getLocation(city, (status: string, result: any) => {
    console.log('[Map] 地理编码结果:', status, result)

    let cityCenter = [116.397428, 39.90923] // 默认北京

    if (status === 'complete' && result.geocodes && result.geocodes.length > 0) {
      const location = result.geocodes[0].location
      cityCenter = [location.lng, location.lat]
      console.log('[Map] 城市中心坐标:', cityCenter)
    } else {
      console.warn('[Map] 未找到城市坐标，使用默认值')
    }

    // 创建地图实例 - 使用城市中心坐标
    const map = new AMap.Map('map-container', {
      resizeEnable: true,
      zoom: 12,
      center: cityCenter
    })

    // 添加地图控件
    AMap.plugin(['AMap.Scale', 'AMap.ToolBar'], function() {
      map.addControl(new AMap.Scale())
      map.addControl(new AMap.ToolBar())
    })

    mapInstance.value = map
    console.log('[Map] 地图实例创建成功，中心点:', cityCenter)

    // 收集所有景点坐标
    const markers: any[] = []
    console.log('[Map] 遍历景点数据...')

    currentPlan.days.forEach((day: any, dayIndex: number) => {
      console.log(`[Map] 第${dayIndex + 1}天景点:`, day.attractions)
      day.attractions?.forEach((attraction: any, attrIndex: number) => {
        console.log(`[Map] 景点[${attrIndex}]:`, attraction.name, 'location:', attraction.location)
        if (attraction.location) {
          const lng = attraction.location.longitude || attraction.location.lng
          const lat = attraction.location.latitude || attraction.location.lat

          console.log(`[Map] 坐标: lng=${lng}, lat=${lat}`)

          if (lng && lat && lng !== 0 && lat !== 0) {
            console.log(`[Map] 添加标记: ${attraction.name} (${lng}, ${lat})`)

            // 创建标记
            const marker = new AMap.Marker({
              position: [lng, lat],
              title: attraction.name
            })

            // 添加点击事件显示名称
            marker.on('click', () => {
              const infoWindow = new AMap.InfoWindow({
                content: `<div style="padding:10px;"><strong>${attraction.name}</strong><br/>${attraction.address || ''}</div>`,
                offset: new AMap.Pixel(0, -30)
              })
              infoWindow.open(map, marker.getPosition())
            })

            markers.push(marker)
            map.add(marker)
          } else {
            console.warn(`[Map] 景点 ${attraction.name} 坐标无效`)
          }
        } else {
          console.warn(`[Map] 景点 ${attraction.name} 没有location字段`)
        }
      })
    })

    console.log('[Map] 共添加', markers.length, '个标记')

    // 如果有标记，自适应显示
    if (markers.length > 0) {
      map.setFitView(markers)
      console.log('[Map] 已调整视野以显示所有标记')
    }
  })
}

// 导出PDF
async function handleExportPDF() {
  ElMessage.info('正在生成PDF...')

  try {
    // 使用 html2canvas 和 jspdf
    const html2canvas = (await import('html2canvas')).default
    const { jsPDF } = await import('jspdf')

    const element = document.querySelector('.content') as HTMLElement
    if (!element) return

    const canvas = await html2canvas(element, {
      scale: 2,
      useCORS: true,
      logging: false
    })

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF('p', 'mm', 'a4')
    const imgWidth = 210
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    pdf.addImage(imgData, 'PNG', 0, 0, imgWidth, imgHeight)
    pdf.save(`${tripPlan.value?.city}旅行计划.pdf`)

    ElMessage.success('PDF导出成功')
  } catch (error) {
    console.error('PDF导出失败:', error)
    ElMessage.error('PDF导出失败')
  }
}

// 重新规划
function handleReset() {
  tripStore.reset()
  router.push('/')
}

// 确认行程
async function handleApprove() {
  if (!tripStore.sessionId) return

  try {
    await approveTripPlan(tripStore.sessionId, reviewComment.value)
    tripStore.setStatus('completed')
    tripStore.setNeedHumanReview(false)
    ElMessage.success('行程已确认')
    showReviewDialog.value = false
  } catch (error) {
    ElMessage.error('确认失败')
  }
}

// 拒绝行程
async function handleReject() {
  if (!tripStore.sessionId) return

  try {
    await rejectTripPlan(tripStore.sessionId, reviewComment.value)
    tripStore.setStatus('failed')
    tripStore.setNeedHumanReview(false)
    ElMessage.info('正在重新规划...')
    showReviewDialog.value = false
    router.push('/')
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

onMounted(() => {
  console.log('[Result] onMounted')
  console.log('[Result] tripStore.needHumanReview:', tripStore.needHumanReview)
  console.log('[Result] tripPlan.value:', tripPlan.value)

  if (tripStore.needHumanReview) {
    showReviewDialog.value = true
  }

  // 延迟初始化地图，确保 DOM 已渲染
  setTimeout(() => {
    if (tripPlan.value) {
      console.log('[Result] 开始初始化地图')
      initMap()
    } else {
      console.log('[Result] 没有 tripPlan，跳过地图初始化')
    }
  }, 300)  // 增加延迟时间
})
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: #f5f7fa;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.header h1 {
  font-size: 24px;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.map-container {
  width: 100%;
  height: 400px;
  border-radius: 8px;
  background-color: #f5f5f5;
}

.rag-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.day-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.day-date {
  color: #909399;
  font-size: 14px;
}

.day-theme {
  font-weight: 500;
}

.weather-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: #f0f9ff;
  border-radius: 4px;
  margin-bottom: 16px;
}

.spot-card {
  margin-bottom: 10px;
}

.spot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.spot-header h4 {
  margin: 0;
}

.spot-info p {
  color: #606266;
  margin-bottom: 8px;
}

.spot-details {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 13px;
}

.spot-details span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.spot-tips {
  margin-top: 8px;
  padding: 8px;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 13px;
  color: #e6a23c;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dining-section, .accommodation-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.dining-section h4, .accommodation-section h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.meal-card {
  text-align: center;
}

.meal-type {
  font-size: 12px;
  color: #909399;
}

.meal-name {
  font-weight: 600;
  margin: 4px 0;
}

.meal-cuisine {
  font-size: 13px;
  color: #606266;
}

.meal-price {
  font-size: 12px;
  color: #f56c6c;
  margin-top: 4px;
}

.hotel-info {
  padding: 10px;
}

.hotel-name {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 8px;
}

.hotel-details {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 8px;
}

.hotel-address {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #606266;
  font-size: 13px;
}

.budget-card .el-row {
  text-align: center;
}

.total-budget {
  text-align: center;
}

.total-budget :deep(.el-statistic__number) {
  font-size: 32px;
  color: #409eff;
}

.review-content {
  padding: 20px 0;
}

.review-actions {
  margin-top: 20px;
}

.handoff-copy {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.handoff-copy .el-input {
  flex: 1;
}

.offer-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
