<template>
  <div class="prescan-panel" v-if="workorder?.steps?.length">

    <!-- HEADER -->
    <div class="panel-header">
      <h2>{{ workorder.name }}</h2>
    </div>

    <!-- STATUS LINE -->
    <div class="status-line">
      {{ statusMessage }}
    </div>

    <!-- TABLE -->
    <table class="prescan-table">
      <thead>
        <tr>
          <th>Stage</th>
          <th>Item Code</th>
          <th>Mixing Time</th>
          <th>Prescan</th>
          <th>Live Status</th>
        </tr>
      </thead>

      <tbody>
        <template v-for="(step, stepIndex) in displaySteps":key="stepIndex">
          <tr v-for="(item, itemIndex) in step.items" :key="item.item_id">
            <td v-if="itemIndex === 0" :rowspan="step.items.length">
              {{ stepIndex + 1 }}
            </td>

            <td>{{ item.item_id }}</td>

            <td v-if="itemIndex === 0" :rowspan="step.items.length">
              {{ formatMixTime(
                props.status.process_state === 'MIXING' &&
                props.status.current_step_index === stepIndex

                  ? props.status.mixing_time_remaining
                  : step.mix_time_sec
              ) }}
            </td>


            <!-- PRESCAN -->
            <td>
              <span
                :class="{
                  green: prescanStatus(item.item_id) === 'DONE'
                }"
              >
                {{ prescanStatus(item.item_id) }}
              </span>
            </td>

            <!-- LIVE -->
            <td>
  <span :class="liveClass(getLiveStatus(item))">
    {{ getLiveStatus(item) }}
  </span>
</td>

          </tr>
        </template>
      </tbody>
    </table>

    <div class="scanner-panel">
  <!-- PRESCAN -->
  <div v-if="props.status.process_state === 'PRESCANNING'">
    <h3>Scan Item (Prescan)</h3>
    <input
      type="text"
      v-model="barcode"
      placeholder="Scan item barcode (prescan)"
      @keyup.enter="handlePrescan"
      ref="barcodeInput"
    />
  </div>
  <!-- ACTUAL -->
  <div v-else-if="props.status.process_state === 'WAITING_FOR_ITEMS' || props.status.process_state === 'MIXING'">
    <h3>Scan Item (Actual)</h3>
    <input
      type="text"
      v-model="barcode"
      placeholder="Scan item barcode (actual)"
      @keyup.enter="handleScan"
      ref="barcodeInput"
    />
  </div>
</div>
</div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { scanItem, prescanItem } from '@/api'


const emit = defineEmits([
  'refresh-status',
  'duplicate-scan',
  'wrong-stage',
  'early-scan',
  'prescan-complete'
])



/* ================= PROPS ================= */
const props = defineProps({
  workorder: { type: Object, required: true },
  status: { type: Object, required: true }
})

/* ================= STATE ================= */
const barcode = ref('')
const barcodeInput = ref(null)


/* ================= STATUS MESSAGE ================= */
const statusMessage = computed(() => {
  switch (props.status.process_state) {
    case 'PRESCANNING':
      return 'Prescanning in progress'
    case 'WAITING_FOR_ITEMS':
      return 'Scan items for mixing'
    case 'MIXING':
      return 'Mixing in progress'
    default:
      return ''
  }
})

/* ================= HELPERS ================= */
const formatMixTime = (sec) => {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m ? `${m}m ${s}s` : `${s}s`
}

const prescanStatus = (itemId) => {
  // 1️⃣ If prescan is completed → EVERYTHING IS DONE
  if (props.status.prescan_complete) {
    return 'DONE'
  }
  const prescan = props.status.prescan_status?.status_by_stage || {}

  for (const stage in prescan) {
    const item = prescan[stage].items.find(
      i => String(i.item_id) === String(itemId)
    )

    if (item) {
      // 👇 MAP BACKEND → UI
      if (item.prescan_status === 'SCANNED') {
        return 'DONE'
      }
      return item.prescan_status.toUpperCase()
    }
  }

  return 'PENDING'
}


const liveClass = (state) => {
  return {
    green: state === 'DONE' || state === 'MIXING',
    orange: state === 'SCANNED',
    blue: state === 'READY_TO_LOAD',
    red: state === 'ABORTED'
  }
}
const displaySteps = computed(() => {
  // Use live steps ONLY when they belong to this workorder
  if (
    props.status?.steps?.length &&
    props.status.workorder_id === props.workorder?.name &&
    props.status.process_state !== 'PRESCANNING'
  ) {
    return props.status.steps
  }

  // Otherwise fallback to workorder steps
  if (props.workorder?.steps?.length) {
    return props.workorder.steps
  }

  return []
})

const getLiveStatus = (item) => {
  // During PRESCAN → always show WAITING
  if (props.status.process_state === 'PRESCANNING') {
    return 'WAITING'
  }

  // After prescan → real live status
  return (item.live_status || 'WAITING').toUpperCase()
}





/* ========= PRESCAN ========= */


const handlePrescan = async () => {
  if (!barcode.value.trim()) return

  try {
    const result = await prescanItem(barcode.value.trim())

    if (result?.status === 'success') {
      emit('refresh-status')
      barcode.value = ''
      /*if (result.prescan_complete) {
    emit('prescan-complete')
  }*/
    } 
    else if (result?.status === 'error') {
      // 👇 THIS IS THE KEY PART
      if (result.message?.toLowerCase().includes('already')) {
        emit('duplicate-scan', result.message)
      }
    }
  } catch (err) {
    console.error('Prescan error:', err)
  }

  nextTick(() => barcodeInput.value?.focus())
}



const handleScan = async () => {
  if (!barcode.value.trim()) return

  try {
    const result = await scanItem(barcode.value.trim())

    // ❌ API-level error
    if (result?.error) {
      emit('wrong-stage', result.error)
      barcode.value = ''
      return
    }

    // ❌ Backend rejected scan
    if (result?.status === 'fail') {
      const msg = result.message || ''

      // Early scan during mixing
      if (
        props.status.process_state === 'MIXING' &&
        msg.toLowerCase().includes('next')
      ) {
        emit(
          'early-scan',
          `This item belongs to Stage ${props.status.current_step_index + 2}`
        )
      } else {
        emit('wrong-stage', msg)
      }

      barcode.value = ''
      return
    }

    // ✅ SUCCESS
    if (result?.status === 'success') {
      barcode.value = ''
      emit('refresh-status') // 🔑 THIS replaces updateStatus()
    }

  } catch (err) {
    emit('wrong-stage', err.message || 'Scan failed')
  }
}


</script>

<style scoped>
.prescan-panel {
  background: white;
  border: 2px solid #333;
  border-radius: 10px;
  padding: 1.5rem;
  width:65%;
  justify-content:space-between;
  margin-left:12rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 1rem;
  margin-left: 18rem;
}

.status-line {
  margin-bottom: 3rem;
  padding: 0.75rem;
  background: #e8f5e8;
  border: 2px solid #28a745;
  border-radius: 6px;
  text-align: center;
  font-weight: 600;
  width:80%;
  margin-left:5rem;
  height:50px;
}

.prescan-table {
  width: 80%;
  border-collapse: collapse;
  margin-bottom: 1.5rem;
  margin-left:5rem;
  margin-top:1 rem;
}

.prescan-table th,
.prescan-table td {
  border: 2px solid #333;
  padding: 10px;
  text-align: center;
}

.prescan-table th {
  background: #f0f0f0;
}

.scanner-panel {
  margin-top: 1.5rem;
}

.scanner-panel input {
  width: 100%;
  padding: 0.75rem;
  font-size: 1.1rem;
  border: 2px solid #ccc;
  border-radius: 6px;
}

.confirmation-dialog {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
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


/* COLORS */
.green { color: green; font-weight: bold }
.orange { color: orange; font-weight: bold }
.blue { color: blue; font-weight: bold }
.red { color: red; font-weight: bold }
</style>
