import { ref } from 'vue'

const batchType = ref(localStorage.getItem('lastBatchType') || null)

export function useBatch() {
  function selectBatch(type) {
    batchType.value = type
    localStorage.setItem('lastBatchType', type)
  }

  function resetBatch() {
    batchType.value = null
    localStorage.removeItem('lastBatchType')
    localStorage.removeItem('lastBatchNumber')
  }

  return {
    batchType,
    selectBatch,
    resetBatch
  }
}
