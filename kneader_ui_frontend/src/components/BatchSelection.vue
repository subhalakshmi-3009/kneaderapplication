<template>
  <div
    class="batch-panel"
    v-if="!batchType && status.process_state === 'IDLE'"
  >
    <div class="batch-header">
      <h2>Select Batch Type</h2>
      <button @click="onLogout" class="btn btn-warning">
        Logout
      </button>
    </div>

    <div class="batch-options">
      <div class="batch-option" @click="selectBatchType('master')">
        MASTER BATCH
      </div>
      <div class="batch-option" @click="selectBatchType('compound')">
        COMPOUND BATCH
      </div>
    </div>
  </div>
</template>
<script setup>
import { useAuth } from '@/composables/useAuth'

const emit = defineEmits(['selected'])

const props = defineProps({
  status: { type: Object, required: true },
  batchType: { type: String, default: null }
})

const { logout } = useAuth()

const selectBatchType = (type) => {
  localStorage.setItem('lastBatchType', type)
  emit('selected', type)
}

const onLogout = () => {
  logout()
}
</script>

<style scoped>
/* PAGE POSITIONING */
.batch-panel {
  background: white;
  border-radius: 14px;
  padding: 2.5rem 3rem;

  /* THIS IS THE KEY DIFFERENCE */
  width: 700px;
  max-width: 90%;

  /* CENTER HORIZONTALLY */
  margin: 4rem auto;

  /* CARD FEEL */
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
}

/* HEADER ROW */
.batch-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2.5rem;
}

/* LOGOUT BUTTON (clean) */
.batch-header .btn {
  padding: 0.4rem 1rem;
  font-size: 0.9rem;
}

/* OPTIONS CONTAINER */
.batch-options {
  display: flex;
  justify-content: center;
  gap: 40px;
}

/* OPTION CARDS */
.batch-option {
  border: 2px solid #007bff;
  border-radius: 12px;
  padding: 2.5rem 2rem;

  width: 200px;
  height: 140px;

  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;

  font-size: 1.2rem;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
}

.batch-option:hover {
  background-color: #007bff;
  color: white;
  transform: translateY(-4px);
}
/* WARNING-STYLE LOGOUT BUTTON */
.btn-warning {
  background-color: #ffc107;       /* Bootstrap warning yellow */
  color: #000;
  border: 1px solid #e0a800;
  border-radius: 6px;

  padding: 0.45rem 1.2rem;
  font-size: 0.95rem;
  font-weight: 600;

  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-warning:hover {
  background-color: #e0a800;
}

.btn-warning:active {
  transform: scale(0.97);
}



</style>
