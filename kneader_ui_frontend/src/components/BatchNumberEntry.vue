<template>
  <!-- Batch number entry -->
  <div class="batch-panel">
    <div class="batch-header">
      <h2>Enter Batch Number for {{ batchType }}</h2>
      <button class="btn btn-warning" @click="showCancelConfirmation = true">
        Cancel
      </button>
    </div>

    <div class="batch-input">
      <input
        ref="batchInput"
        type="text"
        v-model="enteredBatchNumber"
        placeholder="Type batch number and press Enter or Load"
        @keyup.enter="onLoad"
      />
      <button class="btn btn-load" @click="onLoad">Load</button>
    </div>
  </div>

  <!-- Cancel confirmation -->
  <div class="confirmation-dialog" v-if="showCancelConfirmation">
    <div class="dialog-content">
      <h3>Confirm Cancel</h3>
      <p>Are you sure you want to cancel batch selection?</p>

      <div class="dialog-actions">
        <button class="btn btn-warning" @click="confirmCancel">
          Yes, Cancel
        </button>
        <button class="btn btn-primary" @click="cancelCancel">
          No, Continue
        </button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { loadWorkorder } from '@/api'

const emit = defineEmits(['loaded', 'cancel'])

const props = defineProps({
  batchType: { type: String, required: true }
})

const enteredBatchNumber = ref(localStorage.getItem('lastBatchNumber') || '')
const showCancelConfirmation = ref(false)
const batchInput = ref(null)

onMounted(() => {
  nextTick(() => {
    batchInput.value?.focus()
  })
})

const onLoad = async () => {
  const bn = enteredBatchNumber.value.trim()
  if (!bn) return

  const response = await loadWorkorder({ batch_no: bn })
  if (response?.error || response?.status === 'error') return

  localStorage.setItem('lastBatchNumber', bn)
  emit('loaded', response)
}

const confirmCancel = () => {
  localStorage.removeItem('lastBatchType')
  localStorage.removeItem('lastBatchNumber')

  enteredBatchNumber.value = ''
  showCancelConfirmation.value = false

  emit('cancel')
}

const cancelCancel = () => {
  showCancelConfirmation.value = false
  nextTick(() => batchInput.value?.focus())
}
</script>
<style scoped>

.btn {
  border-radius: 8px;
}
.batch-panel {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  border: 2px solid #333;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  max-width:650px;
  margin:2rem auto;
}

.batch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.batch-input {
  display: flex;
  gap: 8px;
  align-items: center;
  max-width:500px;
}

.batch-input input {
  flex: 1;
  padding: 0.6rem;
  font-size: 1rem;
}

.btn-warning {
  background-color: #ffc107;
  border: 1px solid #e0a800;
  color: #000;
  font-weight: 700;
  font-size: 1.05rem;
  padding: 0.5rem 1.2rem;
}

.btn-warning:hover {
  background-color: #e0a800;
}

.btn-load {
  background-color: #6c757d;
  border: 1px solid #5a6268;
  color: white;
  font-size: 1.05rem;        /* slightly bigger text */
  padding: 0.65rem 1.4rem;   /* bigger button */
  font-weight: 600;
}

.btn-load:hover {
  background-color: #5a6268;
}

/* confirmation dialog */
.confirmation-dialog {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-content {
  background: white;
  padding: 2rem;
  border-radius: 8px;
  text-align: center;
  max-width: 400px;
  width: 100%;
  border: 2px solid #333;
}

.dialog-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 1rem;
}

.dialog-actions .btn-primary {
  background-color: #28a745;  /* 🟢 Green */
  color: white;
   padding: 0.7rem 2rem; 
}

.dialog-actions .btn-primary:hover {
  background-color: #218838;
}
</style>
