<template>
  <div class="dashboard">

    <!-- INITIAL: only batch-number entry screen -->
    <div class="batch-panel" v-if="showBatchSelection">
      <h2>Enter Batch Number</h2>
      <div class="batch-input" style="display:flex; gap:8px; align-items:center;">
        <input
          type="text"
          v-model="enteredBatchNumber"
          placeholder="Type batch number and press Enter or Load"
          @keyup.enter="loadBatchByNumber"
          ref="batchInput"
          style="flex:1; padding:0.6rem; font-size:1rem;"
        />
        <button @click="loadBatchByNumber" class="btn">Load</button>
      </div>
      <p style="margin-top:0.5rem; color:#666; font-size:0.95rem;">
        After loading a valid batch, prescanning screen will open.
      </p>
    </div>

    <!-- PRESCANNING PANEL -->
    <div class="prescan-panel" v-if="showPrescanning && workorder">
      <h2>Pre-scanning: {{ selectedBatch ? selectedBatch.name : workorder.name }}</h2>

      <div class="prescan-status">
        <div class="progress">
          <div class="progress-bar" :style="{ width: prescanProgress + '%' }"></div>
          <span class="progress-text">{{ scannedItemsCount }} / {{ totalItemsCount }} items scanned</span>
        </div>
      </div>

      <div class="items-list">
        <div v-for="(step, idx) in workorder.steps" :key="step.step_id || idx">
          <h3>Step {{ idx + 1 }}</h3>
          <div
            v-for="item in step.items"
            :key="item.item_id"
            :class="['item', getItemStatus(item.item_id)]"
          >
            <span class="item-name">{{ item.name }}</span>
            <span class="item-id">{{ item.item_id }}</span>
            <span class="status-indicator" :class="getItemStatus(item.item_id)">{{ getItemStatus(item.item_id) }}</span>
          </div>
        </div>
      </div>

      <!-- Prescan-only scanner -->
      <div class="scanner-panel">
        <h3>Scan Item (Prescan)</h3>
        <div class="scanner-input">
          <input
            type="text"
            v-model="barcode"
            placeholder="Scan item barcode (prescan)"
            @keyup.enter="handlePrescan"
            ref="barcodeInput"
          />
        </div>

        <div v-if="scanResult" :class="['scan-result', scanResult.status]">
          {{ scanResult.message }}
        </div>
      </div>

      <!-- Confirmation Dialog -->
      <div class="confirmation-dialog" v-if="prescanComplete">
        <div class="dialog-content">
          <h3>Pre-scanning Complete!</h3>
          <p>All items have been scanned successfully.</p>
          <button @click="confirmPrescan" class="btn btn-primary">OK — Start Mixing</button>
        </div>
      </div>
    </div>

    <div class="status-panel" v-if="!showBatchSelection && !showPrescanning && status.process_state !== 'IDLE'">
      <h2>System Status</h2>
      <div class="status-info">
        <div class="status-item">
          <span class="label">Workorder ID:</span>
          <span class="value">{{ status.workorder_id }}</span>
        </div>
        <div class="status-item">
          <span class="label">Process State:</span>
          <span class="value">{{ status.process_state }}</span>
        </div>
        <div class="status-item">
          <span class="label">Current Stage:</span>
          <span class="value">{{ status.current_step_index + 1 }} of {{ status.total_steps }}</span>
        </div>
        <div class="status-item">
          <span class="label">Lid Status:</span>
          <span :class="['value', status.lid_open ? 'open' : 'closed']">
            {{ status.lid_open ? 'Open' : 'Closed' }}
          </span>
        </div>
        <div class="status-item">
          <span class="label">Motor Status:</span>
          <span :class="['value', status.motor_running ? 'running' : 'stopped']">
            {{ status.motor_running ? 'Running' : 'Stopped' }}
          </span>
        </div>
        <div class="status-item" v-if="status.process_state === 'MIXING'">
          <span class="label">Time Remaining:</span>
          <span class="value">{{ formatTime(status.mixing_time_remaining) }}</span>
        </div>
        <div class="status-item" v-if="status.process_state === 'ABORTED'">
          <span class="label">Paused Time Remaining:</span>
          <span class="value">{{ formatTime(status.mixing_time_remaining) }}</span>
        </div>
      </div>

      <div class="control-buttons">
        <button v-if="status.process_state === 'MIXING'" @click="abortProcess" class="btn btn-danger">Abort</button>
        <button v-if="status.process_state === 'ABORTED'" @click="resumeProcess" class="btn btn-warning">Resume</button>
        <button v-if="status.process_state === 'PROCESS_COMPLETE'" @click="resetController" class="btn btn-primary">Reset</button>
      </div>
      
      <!-- Progress bar for mixing -->
      <div v-if="status.process_state === 'MIXING'" class="mixing-progress">
        <div class="progress">
          <div class="progress-bar" :style="{ width: mixingProgress + '%' }"></div>
          <span class="progress-text">Mixing: {{ mixingProgress }}% complete</span>
        </div>
      </div>
    </div>
    <div class="scanner-panel" v-if="!showBatchSelection && !showPrescanning" 
         :class="{ centered: status.process_state === 'IDLE' || status.process_state === 'PROCESS_COMPLETE' }">
      <h3>Enter Item Code</h3>
      <div class="scanner-input">
        <input
          type="text"
          v-model="barcode"
          placeholder="Type item code and press Enter"
          @keyup.enter="handleScan"
          ref="barcodeInput"
          :disabled="!canScan"
        />
      </div>

      <div v-if="scanResult" :class="['scan-result', scanResult.status]">
        {{ scanResult.message }}
      </div>

      <div v-if="status.process_state === 'IDLE'" class="idle-message">
        <p>Load a workorder to begin</p>
      </div>
      <div v-if="status.process_state === 'PROCESS_COMPLETE'" class="idle-message">
        <div class="completion-message"><p><strong>Process Complete!</strong></p></div>
      </div>
      <div v-if="status.process_state === 'WAITING_FOR_ITEMS'" class="waiting-message">
        <p>Enter the next item code for the current stage</p>
      </div>
      <div v-if="status.process_state === 'MIXING'" class="waiting-message">
        <p>Mixing in progress - please wait</p>
      </div>
      <div v-if="status.process_state === 'WAITING_FOR_LID_CLOSE'" class="waiting-message">
        <p>Waiting for lid to close</p>
      </div>
      <div v-if="status.process_state === 'WAITING_FOR_MOTOR_START'" class="waiting-message">
        <p>Waiting for motor to start</p>
      </div>
    </div>


    <!-- Debug Info -->
    <div class="debug-info" v-if="debugMode">
      <h3>Debug Information</h3>
      <p>Current State: {{ status.process_state }}</p>
      <p>Barcode: {{ barcode }}</p>
      <p>Last Result: {{ scanResult }}</p>
      <p>Workorder: {{ workorder ? workorder.workorder_id : 'None' }}</p>
      <button @click="debugMode = !debugMode">Hide Debug</button>
    </div>
    <button v-else @click="debugMode = true" class="btn-debug">Show Debug</button>
  </div>
</template>

<script>
import {
  getStatus,
  scanItem,
  abortProcess,
  resetController,
  getWorkorders,
  checkTransitions,
  resumeProcess,
  getBatches,
  loadWorkorder,
  confirmPrescanAPI,
  prescanItem
} from '@/api'

export default {
  name: 'Dashboard',
  data() {
    return {
      showConfirmPopup: false,
      batches: [],
      enteredBatchNumber: '',
      selectedBatch: null,
      workorder: null,
      showBatchSelection: true,
      showPrescanning: false,
      prescanComplete: false,
      scannedItems: [],
      status: {
        process_state: 'IDLE',
        lid_open: true,
        motor_running: false,
        current_step_index: -1,
        current_item_index: -1,
        mixing_time_remaining: 0,
        error_message: '',
        workorder_id: null,
        total_steps: 0
      },
      workorders: [],
      currentWorkorder: null,
      barcode: '',
      scanResult: null,
      debugMode: false,
      statusInterval: null,
      transitionInterval: null,
      showingCompletion: false
    }
  },
  computed: {
    scannedItemsCount() {
      return this.scannedItems.length;
    },
    currentStepItems() {
    if (this.status.steps && this.status.current_step_index < this.status.steps.length) {
      return this.status.steps[this.status.current_step_index].items || [];
    }
    return [];
  },

    totalItemsCount() {
      if (!this.workorder || !this.workorder.steps) return 0;
      return this.workorder.steps.reduce((total, step) => total + (step.items ? step.items.length : 0), 0);
    },
    prescanProgress() {
      if (this.totalItemsCount === 0) return 0;
      return Math.round((this.scannedItemsCount / this.totalItemsCount) * 100);
    },
     canScan() {
    return this.status.process_state === 'WAITING_FOR_ITEMS' || 
           this.status.process_state === 'PRESCANNING';
  }
  },
  async mounted() {
    await this.loadBatches();
    await this.loadWorkorders();
    this.startStatusPolling() 
    this.startPolling();
    this.$nextTick(() => {
      if (this.$refs.batchInput) this.$refs.batchInput.focus();
    });
  },
  beforeUnmount() {
    this.stopPolling();
  },
  watch: {
    'status.process_state'(newState) {
      if (newState === 'PROCESS_COMPLETE') {
        this.showingCompletion = true;
        this.scanResult = null;
        this.barcode = '';
        setTimeout(() => { this.showingCompletion = false; }, 5000);
      } else if (newState === 'IDLE') {
        this.scanResult = null;
        this.barcode = '';
      }
    }
  },
  methods: {
    async loadBatches() {
      try {
        const response = await getBatches();
        this.batches = response;
        console.log('Loaded batches:', this.batches);
      } catch (error) {
        console.error('Failed to load batches:', error);
      }
    },

    // Load a batch by manual entry
    async loadBatchByNumber() {
  const bn = (this.enteredBatchNumber || '').trim();
  alert (bn)
  if (!bn) return;
  try {
    const response = await loadWorkorder(bn);
    
    // Check if response has error status
    if (response && response.status === 'error') {
      this.scanResult = { status: 'error', message: response.message || 'Failed to load batch' };
      return;
    }
    
    // Handle success case
    if (response && response.workorder) {
      this.selectedBatch = { batch_number: bn, name: response.workorder.name || bn };
      this.workorder = response.workorder;
      this.showBatchSelection = false;
      this.showPrescanning = true;
      this.prescanComplete = false;
      this.scannedItems = [];
      this.$nextTick(() => { 
        if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
      });
    } else {
      this.scanResult = { 
        status: 'error', 
        message: response.message || 'Failed to load workorder' 
      };
    }
  } catch (err) {
    console.error('Failed to load batch:', err);
    this.scanResult = { status: 'error', message: 'Failed to load batch' };
  }
},
getActualItemStatus(itemId) {
    // Logic to check if scanned; you may need to track scanned items from status or API
    // For example, assume status has a 'scanned_items' array
    return this.status.scanned_items && this.status.scanned_items.includes(itemId) ? 'scanned' : 'pending';
  },
    getItemStatus(itemId) {
      return this.scannedItems.includes(itemId) ? 'scanned' : 'pending';
    },

    // PRESCAN scanner (calls prescanItem API)
    async handlePrescan() {
      if (!this.barcode.trim()) return;
      try {
        // call prescan endpoint
        const result = await prescanItem(this.barcode.trim());
        // result expected { status: 'success'|'fail'|'error', message: '...', prescan_status: {...} }
        if (result && result.status === 'success') {
          if (!this.scannedItems.includes(this.barcode.trim())) {
            this.scannedItems.push(this.barcode.trim());
          }
          if (this.scannedItemsCount === this.totalItemsCount) {
            this.prescanComplete = true;
          }
        }
        this.scanResult = result;
        this.barcode = '';
        this.$nextTick(() => { if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); });
      } catch (error) {
        console.error('Failed to prescan item:', error);
        this.scanResult = { status: 'error', message: 'Scan failed: ' + (error.response?.data?.error || error.message) };
      }
    },

  async confirmPrescan() {
  try {
    alert("confirming prescan")
    const response = await confirmPrescanAPI();
    if (response && response.status === 'success') {
      this.showPrescanning = false;
      this.pollStatus();
      this.prescanComplete = true;
      this.showBatchSelection = false;
      this.barcode = '';
      
      // Poll status 3 times to ensure transition
      let attempts = 0;
      while (attempts < 15) {
        await this.updateStatus();
        if (this.status.process_state === 'WAITING_FOR_ITEMS') {
          this.scanResult = { status: 'success', message: 'Prescanning completed. Scan the items for the stage 1 mixing process' };
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s
        attempts++;
      }
      if (this.status.process_state !== 'WAITING_FOR_ITEMS') {
        this.scanResult = { status: 'error', message: 'State transition failed; still in PRESCANNING' };
        this.showPrescanning = true; // Revert UI
      }
    } else {
      const msg = (response && response.message) || 'Failed to confirm pre-scan';
      this.scanResult = { status: 'error', message: msg };
    }
  } catch (err) {
    console.error('Failed to confirm pre-scan:', err);
    this.scanResult = { status: 'error', message: 'Failed to confirm pre-scan' };
  }
},
    formatTime(seconds) {
      const mins = Math.floor(seconds / 60)
      const secs = seconds % 60
      return `${mins}:${secs.toString().padStart(2, '0')}`
    },

    async loadWorkorders() {
      try {
        const response = await getWorkorders()
        this.workorders = response.workorders || response
        console.log('Loaded workorders:', this.workorders)
      } catch (error) {
        console.error('Failed to load workorders:', error)
      }
    },
    updateUIState() {
      // Handle state-specific UI updates
      switch (this.status.process_state) {
        case 'MIXING':
          this.$nextTick(() => console.log('Mixing state active')); // Debug
          break;
        case 'WAITING_FOR_ITEMS':
          this.$nextTick(() => {
            if (this.$refs.actualBarcodeInput) this.$refs.actualBarcodeInput.focus();
            console.log('Waiting for items, focusing scanner'); // Debug
          });
          break;
        case 'PRESCANNING':
          this.showPrescanning = true;
          this.updatePrescanProgress();
          this.$nextTick(() => { if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); });
          break;
        default:
          this.showPrescanning = false;
      }
    },
  


    async checkAndTriggerTransitions() {
      try {
        if (this.status.process_state === 'WAITING_FOR_LID_CLOSE' ||
            this.status.process_state === 'WAITING_FOR_MOTOR_START') {
          const result = await checkTransitions()
          if (result && result.status === 'success') {
            await this.updateStatus()
          }
        }
      } catch (error) {
        console.error('Transition check failed:', error)
      }
    },

    async updateStatus() {
  try {
    const newStatus = await getStatus()
    this.status = newStatus
    
    // Handle state-specific UI updates
    if (newStatus.process_state === 'WAITING_FOR_ITEMS') {
      this.$nextTick(() => { 
        if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
      });
    }
    
    // If we've moved from prescanning to waiting for items, update UI
    if (this.showPrescanning && newStatus.process_state === 'WAITING_FOR_ITEMS') {
      this.showPrescanning = false;
    }
    
    // If process is complete, show completion message
    if (newStatus.process_state === 'PROCESS_COMPLETE') {
      this.showingCompletion = true;
      setTimeout(() => { this.showingCompletion = false; }, 5000);
    }
  } catch (error) {
    console.error('Failed to update status:', error)
    this.status = {
      process_state: 'IDLE',
      lid_open: true,
      motor_running: false,
      current_step_index: -1,
      current_item_index: -1,
      mixing_time_remaining: 0,
      error_message: '',
      workorder_id: null,
      total_steps: 0
    }
  }
},

    startPolling() {
      this.statusInterval = setInterval(this.updateStatus, 1000)
      this.transitionInterval = setInterval(this.checkAndTriggerTransitions, 2000)
    },

    stopPolling() {
      if (this.statusInterval) { clearInterval(this.statusInterval); this.statusInterval = null; }
      if (this.transitionInterval) { clearInterval(this.transitionInterval); this.transitionInterval = null; }
    },

    async handleScan() {
  if (!this.barcode.trim()) return;

  try {
    const result = await scanItem(this.barcode.trim());
    
    if (result.error) {
      this.scanResult = { status: 'error', message: 'Scan failed: ' + result.error };
    } else {
      this.scanResult = result;
      if (result.status === 'success') {
        this.barcode = '';
        this.$nextTick(() => {
          if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus();
        });
        
        // Update status after successful scan
        await this.updateStatus();
      }
    }
  } catch (error) {
    console.error('Failed to scan item:', error);
    this.scanResult = {
      status: 'error',
      message: 'Scan failed: ' + (error.response?.data?.error || error.message)
    };
  }
},

    async abortProcess() {
      try {
        await abortProcess()
      } catch (error) {
        console.error('Failed to abort process:', error)
      }
    },
    async resumeProcess() {
      try {
        await resumeProcess()
      } catch (error) {
        console.error('Failed to resume process:', error)
      }
    },
    pollStatus() {
  this.interval = setInterval(() => {
    getStatus().then(data => {
      console.log('Polled status:', data); // Add this for debugging
      this.status = data;
      this.updateUIState();
    }).catch(error => console.error('Polling error:', error));
  }, 1000);
},

    async resetController() {
      try {
        await resetController()
        this.currentWorkorder = null
        this.scannedItems = []
        this.barcode = ''
        this.scanResult = null
        this.showBatchSelection = true
        this.showPrescanning = false
        this.$nextTick(() => { if (this.$refs.batchInput) this.$refs.batchInput.focus(); })
      } catch (error) {
        console.error('Failed to reset controller:', error)
      }
    }
  }
}
</script>

<style scoped>
/* (kept your CSS) */
.batch-panel { background-color: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem; }
.batch-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }
.batch-item { border: 1px solid #ddd; border-radius: 4px; padding: 1rem; cursor: pointer; transition: background-color 0.2s; }
.batch-item:hover { background-color: #f5f5f5; transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
.batch-name { font-weight: bold; margin-bottom: 0.5rem; }
.batch-number { color: #666; font-size: 0.9rem; }
.prescan-panel { background-color: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem; }
.progress { height: 20px; background-color: #f5f5f5; border-radius: 4px; margin-bottom: 1rem; position: relative; }
.progress-bar { height: 100%; background-color: #28a745; border-radius: 4px; transition: width 0.3s; }
.progress-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #333; font-weight: bold; }
.items-list { margin-bottom: 1.5rem; }
.items-list h3 { margin-top: 1rem; margin-bottom: 0.5rem; }
.item { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; border-bottom: 1px solid #eee; }
.item.scanned { background-color: #d4edda; }
.item.pending { background-color: #fff3cd; }
.item-name { font-weight: bold; }
.item-id { color: #666; font-size: 0.9rem; }
.status-indicator { font-weight: bold; }
.status-indicator.scanned { color: #28a745; }
.status-indicator.pending { color: #ffc107; }
.confirmation-dialog { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0, 0, 0, 0.5); display:flex; justify-content:center; align-items:center; z-index:1000; }
.dialog-content { background-color: white; padding: 2rem; border-radius: 8px; text-align:center; max-width: 400px; width: 100%; }
.dashboard { display:flex; flex-direction:column; gap:1rem; max-width:600px; margin:0 auto; padding:1rem; }
.status-panel { background-color: white; border-radius:8px; padding:1rem; box-shadow:0 2px 4px rgba(0,0,0,0.1); }
.status-info { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin-bottom:1rem; }
.status-item { display:flex; flex-direction:column; }
.label { font-weight:bold; margin-bottom:0.25rem; color:#666; }
.value { font-size:1.1rem; }
.open { color:#dc3545; }
.closed { color:#28a745; }
.running { color:#28a745; }
.stopped { color:#6c757d; }
.control-buttons { display:flex; gap:0.5rem; }
.btn { padding:0.5rem 1rem; border:none; border-radius:4px; cursor:pointer; font-size:1rem; }
.btn-danger { background-color:#dc3545; color:white; }
.btn-warning { background-color:#ffc107; color:black; }
.scanner-panel { background-color:white; border-radius:8px; padding:1.5rem; box-shadow:0 2px 4px rgba(0,0,0,0.1); }
.scanner-panel.centered { text-align:center; }
.scanner-input { margin-bottom:1rem; }
.scanner-input input { width:100%; padding:0.75rem; border:2px solid #ddd; border-radius:4px; font-size:1.1rem; text-align:center; }
.scanner-input input:focus { border-color:#007bff; outline:none; }
.scanner-input input:disabled { background-color:#f5f5f5; cursor:not-allowed; }
.scan-result { padding:0.75rem; border-radius:4px; text-align:center; font-weight:bold; margin-bottom:1rem; }
.scan-result.success { background-color:#d4edda; color:#155724; border:1px solid #c3e6cb; }
.scan-result.fail { background-color:#f8d7da; color:#721c24; border:1px solid #f5c6cb; }
.scan-result.error { background-color:#fff3cd; color:#856404; border:1px solid #ffeeba; }
.idle-message, .waiting-message { margin-top:1rem; color:#6c757d; font-style:italic; text-align:center; }
.debug-info { background-color:#f8f9fa; border:1px solid #dee2e6; border-radius:4px; padding:1rem; margin-top:1rem; }
.debug-info h3 { margin-top:0; color:#6c757d; }
.btn-debug { background-color:#6c757d; color:white; padding:0.25rem 0.5rem; border:none; border-radius:4px; font-size:0.8rem; margin-top:1rem; }
</style>