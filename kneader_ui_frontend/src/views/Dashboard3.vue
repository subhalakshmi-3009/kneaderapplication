<template>
  <div class="login-page">
    <LoginCard v-if="!token" />
     <!-- BATCH SELECTION -->
    <BatchSelection
      v-else-if="!batchType"
      :status="status"
      @selected="onBatchSelected"
    />

    <BatchNumberEntry
  v-else-if="batchType && showBatchSelection"
  :batchType="batchType"
  @loaded="onBatchLoaded"
  @cancel="onBatchCancelled"
/>
    <PrescanPanel
  v-if="workorder && showPrescanning"
  :workorder="workorder"
  :status="status"
   @refresh-status="fetchStatus"
   @duplicate-scan="onDuplicateScan"
   @prescan-complete="showPrescanCompletePopup = true"
   @wrong-stage="showWrongStagePopup"
  @early-scan="showEarlyScanPopup"
/>


<div class="confirmation-dialog" v-if="showDuplicateScanPopup">
  <div class="dialog-content">
    <h3>Duplicate Scanning!</h3>
    <p>{{ duplicateScanMessage }}</p>
    <button
      class="btn btn-primary"
      @click="closeDuplicateScanPopup"
    >
      OK
    </button>
  </div>
</div>

<div class="confirmation-dialog" v-if="showPrescanCompletePopup">
  <div class="dialog-content">
    <h3>Pre-scanning Complete!</h3>
    <p>All items have been scanned successfully.</p>
    <button @click="confirmPrescan" class="btn btn-primary">
      OK
    </button>
  </div>
</div>



  </div>
  
</template>

<script setup>
import { ref, watch, onMounted,nextTick } from 'vue'
import { onUnmounted } from 'vue'
import LoginCard from '@/components/LoginCard.vue'
import BatchSelection from '@/components/BatchSelection.vue'
import BatchNumberEntry from '@/components/BatchNumberEntry.vue'
import PrescanPanel from '@/components/PrescanPanel.vue'
import { useAuth } from '@/composables/useAuth'
import { confirmPrescanAPI,getStatus } from '@/api'

const { token } = useAuth()

const batchType = ref(null)
const showBatchSelection = ref(false)

const status = ref({ process_state: 'IDLE' })

const workorder = ref(null)
const showPrescanning = ref(false)

const showDuplicateScanPopup = ref(false)
const duplicateScanMessage = ref('')
const showPrescanCompletePopup = ref(false)
const barcode = ref('')
const barcodeInput = ref(null)
const onDuplicateScan = (message) => {
  duplicateScanMessage.value = message || 'This item was already scanned.'
  showDuplicateScanPopup.value = true
}
const prescanPopupShown = ref(false)

let readyTimeout = null
let mixingInterval = null



/* 🔹 Restore workflow ONLY if token exists */
onMounted(() => {
  if (token.value) {
    const savedType = localStorage.getItem('lastBatchType')
    if (savedType) {
      batchType.value = savedType
      showBatchSelection.value = true
    }
  }
})

/* 🔹 Reset workflow when token disappears */
watch(token, (newToken) => {
  if (!newToken) {
    batchType.value = null
    showBatchSelection.value = false
    showPrescanning.value = false
    workorder.value = null
    localStorage.removeItem('lastBatchType')
    localStorage.removeItem('lastBatchNumber')
  }
})


watch(
  () => status.value.process_state,
  (newState) => {
    if (newState === 'PRESCAN_COMPLETE') {
      showPrescanCompletePopup.value = true
    }
  }
)

watch(
  () => status.value.process_state,
  (newState, oldState) => {
    console.log('STATE CHANGE:', oldState, '→', newState)

    if (newState === 'READY_TO_LOAD') {
      startReadyDelay()
    }

    if (newState === 'MIXING') {
      startMixingTimer()
    }
  }
)


const onBatchSelected = (type) => {
  batchType.value = type
  showBatchSelection.value = true 
  localStorage.setItem('lastBatchType', type)
}

const onBatchLoaded = async (response) => {
  console.log('Batch loaded response:', response)

  // ✅ convert backend sequence_steps → UI-friendly steps
  if (response.sequence_steps) {
    workorder.value = {
      name: response.final_item || 'Workorder',
      steps: response.sequence_steps.map((s, index) => ({
        step_id: index + 1,
        mix_time_sec: Number(s.mixing_time),
        items: s.items.map(item => ({
          item_id: String(item),
          live_status: 'WAITING'
        }))
      }))
    }
  } 
  else if (response.workorder) {
    workorder.value = response.workorder
  } 
  else {
    console.error('Invalid batch response', response)
    return
  }
  // 2️⃣ FETCH REAL STATUS FROM BACKEND  ✅✅✅
  try {
    const latestStatus = await getStatus()
    status.value = latestStatus
  } catch (err) {
    console.error('Failed to fetch status', err)
  }

  // 3️⃣ Show prescan screen
  showBatchSelection.value = false
  showPrescanning.value = true
}


/* when user cancels batch entry */
const onBatchCancelled = () => {
  batchType.value = null
  showBatchSelection.value = false
  showPrescanning.value = false
  workorder.value = null
}

const closeDuplicateScanPopup = () => {
  showDuplicateScanPopup.value = false
  duplicateScanMessage.value = ''
  barcode.value = ''

  nextTick(() => {
    barcodeInput.value?.focus()
  })
}

const confirmPrescan = async () => {
  try {
    // Call API (even if it returns "fail")
    await confirmPrescanAPI()

    // 🔑 ALWAYS fetch latest controller state
    const latest = await getStatus()
    status.value = latest

    // 🔑 CLOSE POPUP if prescanning is over
    if (latest.process_state !== 'PRESCANNING') {
      showPrescanCompletePopup.value = false
    }

  } catch (e) {
    console.error('Confirm prescan failed', e)

    // Even on error → recheck status
    const latest = await getStatus()
    status.value = latest

    if (latest.process_state !== 'PRESCANNING') {
      showPrescanCompletePopup.value = false
    }
  }
}
const startReadyDelay = () => {
  clearTimeout(readyTimeout)

  readyTimeout = setTimeout(() => {
    // backend should move state to MIXING
    fetchStatus()
  }, 10000) // 10 seconds
}
const startMixingTimer = () => {
  clearInterval(mixingInterval)

  if (!status.value.mixing_time_remaining) return

  mixingInterval = setInterval(() => {
    if (status.value.mixing_time_remaining > 0) {
      status.value.mixing_time_remaining--
    } else {
      clearInterval(mixingInterval)
      fetchStatus() // backend will move to next stage
    }
  }, 1000)
}
onUnmounted(() => {
  clearTimeout(readyTimeout)
  clearInterval(mixingInterval)
})





const fetchStatus = async () => {
  try {
    const latest = await getStatus()
    status.value = latest
  } catch (e) {
    console.error('Failed to fetch status', e)
  }
}
</script>

<style scoped>
.confirmation-dialog {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-content {
  background-color: white;
  padding: 2rem;
  border-radius: 8px;
  text-align: center;
  max-width: 400px;
  width: 100%;
}

.confirmation-dialog .btn-primary {
  background-color: #007bff;
  border-color: #0069d9;
  padding: 0.6rem 1.5rem;
}
</style>
