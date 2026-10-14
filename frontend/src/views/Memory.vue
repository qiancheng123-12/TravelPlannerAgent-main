<template>
  <div class="memory-page">
    <header class="page-header">
      <div>
        <div class="eyebrow">{{ isTripView ? 'TRIP HISTORY' : 'LONG-TERM MEMORY' }}</div>
        <h1>{{ isTripView ? '📋 历史行程' : '🧠 我的记忆' }}</h1>
        <p>{{ isTripView ? '查看、恢复或删除过去生成的完整旅行方案。' : '查看、修改或删除助手跨对话保存的旅行偏好。' }}</p>
      </div>
      <el-button @click="router.push('/chat')">返回对话</el-button>
    </header>

    <el-alert
      v-if="!isTripView"
      title="助手只保存旅行偏好，不应保存身份证、银行卡、密码、API Key或支付信息。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-card v-if="!isTripView" class="settings-card" shadow="never">
      <div class="setting-row">
        <div>
          <strong>长期记忆</strong>
          <p>关闭后不再抽取或召回偏好，已有记忆仍可在下方管理。</p>
        </div>
        <el-switch
          v-model="enabled"
          :loading="savingSetting"
          active-text="已开启"
          inactive-text="已关闭"
          @change="handleToggle"
        />
      </div>
    </el-card>

    <section v-if="!isTripView" id="memories" class="section">
      <div class="section-title">
        <div>
          <h2>用户画像</h2>
          <span>SQLite持久化，阿里云Embedding + Chroma语义召回</span>
        </div>
        <el-button
          type="danger"
          plain
          :disabled="!profile.facts.length"
          @click="handleClear"
        >清空长期记忆</el-button>
      </div>

      <el-skeleton v-if="loading" :rows="4" animated />
      <el-empty v-else-if="!profile.facts.length" description="还没有长期记忆。在对话中表达旅行偏好后会显示在这里。" />
      <div v-else class="memory-grid">
        <el-card v-for="fact in profile.facts" :key="fact.memory_id" shadow="hover" class="memory-card">
          <div class="fact-header">
            <el-tag effect="plain">{{ fact.category }}</el-tag>
            <span>{{ Math.round(fact.confidence * 100) }}% 置信度</span>
          </div>
          <h3>{{ fact.summary }}</h3>
          <div class="fact-value">{{ formatValue(fact.value) }}</div>
          <div class="fact-footer">
            <span>更新于 {{ formatDate(fact.updated_at) }}</span>
            <div>
              <el-button size="small" text type="primary" @click="openEdit(fact)">修改</el-button>
              <el-button size="small" text type="danger" @click="handleDelete(fact)">删除</el-button>
            </div>
          </div>
        </el-card>
      </div>
    </section>

    <section v-else id="trips" class="section">
      <div class="section-title">
        <div>
          <h2>历史行程</h2>
          <span>由聊天或表单成功生成的行程摘要</span>
        </div>
        <el-button
          type="primary"
          plain
          :loading="importingLegacy"
          :disabled="Boolean(loadError)"
          @click="handleImportLegacy"
        >导入旧版行程</el-button>
      </div>
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
      <el-empty v-else-if="!loading && !profile.trips.length" description="暂无历史行程" />
      <el-table v-else :data="profile.trips" stripe>
        <el-table-column prop="city" label="目的地" />
        <el-table-column prop="start_date" label="出发日期" />
        <el-table-column prop="end_date" label="结束日期" />
        <el-table-column label="更新时间">
          <template #default="scope">{{ formatDate(scope.row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="scope">
            <el-button
              size="small"
              type="primary"
              :loading="viewingTripId === scope.row.trip_id"
              @click="handleViewTrip(scope.row)"
            >查看详情</el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :loading="deletingTripId === scope.row.trip_id"
              @click="handleDeleteTrip(scope.row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-if="!isTripView" v-model="editVisible" title="修改记忆" width="520px">
      <el-form label-position="top">
        <el-form-item label="记忆内容（支持文本或JSON）">
          <el-input v-model="editValue" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="显示摘要">
          <el-input v-model="editSummary" maxlength="300" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingFact" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { MemoryFact, MemoryProfile, MemoryTrip } from '@/types'
import { useChatStore } from '@/stores/chat'
import { useTripStore } from '@/stores/trip'
import {
  clearMemoryProfile,
  deleteMemoryFact,
  deleteMemoryTrip,
  getMemoryProfile,
  getMemoryTrip,
  importLegacyMemoryTrips,
  setMemoryEnabled,
  updateMemoryFact
} from '@/services/api'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const tripStore = useTripStore()
const isTripView = computed(() => route.hash === '#trips')
const loading = ref(true)
const savingSetting = ref(false)
const savingFact = ref(false)
const enabled = ref(true)
const editVisible = ref(false)
const editingId = ref('')
const editValue = ref('')
const editSummary = ref('')
const viewingTripId = ref('')
const deletingTripId = ref('')
const importingLegacy = ref(false)
const loadError = ref('')
const profile = reactive<MemoryProfile>({
  user_id: chatStore.userId,
  enabled: true,
  facts: [],
  trips: []
})

async function loadProfile() {
  loading.value = true
  loadError.value = ''
  try {
    const result = await getMemoryProfile(chatStore.userId)
    Object.assign(profile, result)
    enabled.value = result.enabled
  } catch (error: any) {
    loadError.value = error.response?.status === 404
      ? '当前后端尚未加载历史行程接口。请完全关闭旧后端进程并重新运行 backend/run.py；仅刷新网页不会更新后端。'
      : (error.response?.data?.detail || '读取历史行程失败，请检查后端是否正常运行。')
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function handleToggle(value: string | number | boolean) {
  savingSetting.value = true
  try {
    await setMemoryEnabled(chatStore.userId, Boolean(value))
    ElMessage.success(Boolean(value) ? '长期记忆已开启' : '长期记忆已关闭')
  } catch {
    enabled.value = !Boolean(value)
    ElMessage.error('设置保存失败')
  } finally {
    savingSetting.value = false
  }
}

function openEdit(fact: MemoryFact) {
  editingId.value = fact.memory_id
  editValue.value = typeof fact.value === 'string' ? fact.value : JSON.stringify(fact.value, null, 2)
  editSummary.value = fact.summary
  editVisible.value = true
}

async function handleSave() {
  if (!editValue.value.trim()) return
  savingFact.value = true
  try {
    let value: unknown = editValue.value.trim()
    try { value = JSON.parse(editValue.value) } catch { /* 普通文本保持字符串 */ }
    await updateMemoryFact(chatStore.userId, editingId.value, value, editSummary.value.trim())
    editVisible.value = false
    ElMessage.success('记忆已更新')
    await loadProfile()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '修改失败')
  } finally {
    savingFact.value = false
  }
}

async function handleDelete(fact: MemoryFact) {
  await ElMessageBox.confirm(`确定删除“${fact.summary}”吗？`, '删除记忆', { type: 'warning' })
  await deleteMemoryFact(chatStore.userId, fact.memory_id)
  ElMessage.success('已删除')
  await loadProfile()
}

async function handleClear() {
  await ElMessageBox.confirm('将删除全部长期旅行偏好，但不会删除历史行程和聊天记录。', '清空长期记忆', {
    type: 'warning',
    confirmButtonText: '确认清空'
  })
  await clearMemoryProfile(chatStore.userId)
  ElMessage.success('长期记忆已清空')
  await loadProfile()
}

async function handleViewTrip(trip: MemoryTrip) {
  viewingTripId.value = trip.trip_id
  try {
    const detail = await getMemoryTrip(chatStore.userId, trip.trip_id)
    tripStore.reset()
    tripStore.setSessionId(detail.session_id)
    tripStore.setTripPlan(detail.plan)
    tripStore.setStatus('completed')
    tripStore.setNeedHumanReview(false)
    await router.push('/result')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '读取历史行程失败')
  } finally {
    viewingTripId.value = ''
  }
}

async function handleDeleteTrip(trip: MemoryTrip) {
  try {
    await ElMessageBox.confirm(
      `确定删除“${trip.city} ${trip.start_date || ''}”这条历史行程吗？聊天记录不会被删除。`,
      '删除历史行程',
      { type: 'warning' }
    )
    deletingTripId.value = trip.trip_id
    await deleteMemoryTrip(chatStore.userId, trip.trip_id)
    profile.trips = profile.trips.filter((item) => item.trip_id !== trip.trip_id)
    ElMessage.success('历史行程已删除')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.response?.data?.detail || '删除历史行程失败')
    }
  } finally {
    deletingTripId.value = ''
  }
}

async function handleImportLegacy() {
  importingLegacy.value = true
  try {
    const result = await importLegacyMemoryTrips(chatStore.userId)
    profile.trips = result.trips
    if (result.imported) {
      ElMessage.success(`已导入 ${result.imported} 个旧版行程${result.skipped ? `，跳过 ${result.skipped} 个无效文件` : ''}`)
    } else {
      ElMessage.info('没有找到可导入的旧版完整行程')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '导入旧版行程失败，请确认后端已重启')
  } finally {
    importingLegacy.value = false
  }
}

function formatValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

function formatDate(value: string): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

onMounted(async () => {
  await loadProfile()
  if (route.hash === '#trips') {
    await nextTick()
    document.getElementById('trips')?.scrollIntoView({ behavior: 'smooth' })
  }
})
</script>

<style scoped>
.memory-page { min-height: 100vh; padding: 36px max(24px, 7vw); background: #f5f7fa; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.eyebrow { color: #409eff; font-size: 12px; font-weight: 700; letter-spacing: 1.5px; }
h1 { margin: 6px 0 8px; color: #173b36; }
.page-header p, .setting-row p, .section-title span { color: #7d8793; }
.settings-card { margin: 18px 0 28px; }
.setting-row { display: flex; justify-content: space-between; align-items: center; gap: 24px; }
.setting-row p { margin-top: 6px; font-size: 13px; }
.section { margin-top: 30px; }
.section-title { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 14px; }
.section-title h2 { margin-bottom: 5px; color: #173b36; }
.section-title span { font-size: 13px; }
.memory-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.memory-card h3 { margin: 14px 0 10px; font-size: 16px; }
.fact-header, .fact-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.fact-header span, .fact-footer span { color: #909399; font-size: 12px; }
.fact-value { min-height: 42px; padding: 10px; white-space: pre-wrap; word-break: break-word; border-radius: 7px; background: #f6f8fa; color: #59636e; font-size: 13px; }
.fact-footer { margin-top: 12px; }
@media (max-width: 640px) {
  .memory-page { padding: 20px 14px; }
  .page-header, .section-title, .setting-row { align-items: stretch; flex-direction: column; gap: 12px; }
}
</style>
