<template>
  <div class="dashboard">

    <!-- FIRST SCREEN: select batch type -->
    <div class="batch-panel" v-if="!batchType && status.process_state === 'IDLE'">
      <h2>Select Batch Type</h2>
      <div style="display:flex; gap:20px; justify-content:center; margin-top:1rem;">
        <div class="batch-option" @click="selectBatchType('master')">
          MASTER BATCH
        </div>
        <div class="batch-option" @click="selectBatchType('compound')">
          COMPOUND BATCH
        </div>
      </div>
    </div>

    <!-- SECOND SCREEN: enter batch number -->
<div class="batch-panel" v-else-if="showBatchSelection">
  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
    <h2 style="margin: 0;">Enter Batch Number for {{ batchType }}</h2>
    <button 
       @click="showCancelConfirmation = true"  
      class="btn btn-warning" 
      style="padding: 0.5rem 1rem;"
    >
      Cancel
    </button>
  </div>
  
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
</div>
<!-- Cancel Confirmation Dialog for Batch Selection -->
<div class="confirmation-dialog" v-if="showCancelConfirmation">
  <div class="dialog-content">
    <h3>Confirm Cancel</h3>
    <p>Are you sure you want to cancel batch selection?</p>
    <div style="display:flex; gap:10px; justify-content:center; margin-top:1rem;">
      <button @click="confirmCancelBatchSelection" class="btn btn-warning">Yes, Cancel</button>
      <button @click="cancelCancelBatchSelection" class="btn btn-primary">No, Continue</button>
    </div>
  </div>
</div>
    

    <!-- PRESCANNING PANEL -->
    <div class="prescan-panel" v-if="workorder && workorder.steps">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
  <h2 style="margin: 0;">{{ selectedBatch ? selectedBatch.name : workorder.name }}</h2>
  <button 
    v-if="showCancelButton" 
    @click="showCancelProcessConfirmation = true" 
    class="btn btn-warning" 
    :disabled="isCancelDisabled"
    style="padding: 0.5rem 1rem;"
  >
    Cancel
  </button>
</div>

<!-- Cancel Confirmation Dialog for Process -->
<div class="confirmation-dialog" v-if="showCancelProcessConfirmation">
  <div class="dialog-content">
    <h3>Confirm Cancel</h3>
    <p>Are you sure you want to cancel the process?</p>
    <div style="display:flex; gap:10px; justify-content:center; margin-top:1rem;">
      <button @click="confirmCancelProcess" class="btn btn-warning">Yes, Cancel</button>
      <button @click="cancelCancelProcess" class="btn btn-primary">No, Continue</button>
    </div>
  </div>
</div>

      <!-- Status line -->
      <div class="status-line">
        {{ getStatusMessage() }}
      </div>
       
      <!-- Excel-style prescan table -->
      <table class="prescan-table">
        <thead>
          <tr>
            <th>Stage No.</th>
            <th>Item</th>
            <th>Mixing Time</th>
            <th>Prescan</th>
            <th>Live Status</th>
          </tr>
        </thead>
        <tbody>
  <template v-for="(step, stepIndex) in status.steps" :key="step.step_id || stepIndex">
    <tr :class="{ 'blinking-highlight': isNextStep(stepIndex) }">
      <td :rowspan="step.items.length">{{ stepIndex + 1 }}</td>
      <td>{{ step.items[0].item_id }}</td>

      <td :rowspan="step.items.length">
        <span v-if="status.current_step_index === stepIndex &&
                      (status.process_state === 'MIXING' || status.process_state === 'ABORTED')">
          {{ status.mixing_time_remaining }}s
        </span>
        <span v-else>
          {{ formatMixTime(step.mix_time_sec) }}
        </span>
      </td>

      <td>
        <span v-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'SCANNED'" style="color: green;">
          SCANNED
        </span>
        <span v-else-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'PENDING'" >
          PENDING
        </span>
        <span v-else-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'DONE'" 
        :style="{ color: status.process_state === 'PRESCANNING' ? 'green' : 'gray', fontWeight: 'bold' }">
    DONE
  </span>
        <span v-else>
          {{ getItemStatus(step.items[0].item_id).toUpperCase() }}
        </span>
      </td>

      <td>
        <span v-if="stepIndex === status.current_step_index + 1 && step.items[0].live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
          SCANNED
        </span>
        <span v-else-if="step.items[0].live_status === 'READY_TO_LOAD'" style="color: blue; ">
          READY TO LOAD
        </span>
        <span v-else-if="step.items[0].live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
          SCANNED
        </span>
        <span v-else-if="step.items[0].live_status === 'MIXING'" style="color: green; font-weight: bold;">
          MIXING
        </span>
        <span v-else-if="step.items[0].live_status === 'ABORTED'" style="color: red; font-weight: bold;">
          ABORTED
        </span>
        <span v-else-if="step.items[0].live_status === 'DONE'" style="color: gray; font-weight: bold;">
          DONE
        </span>
        <span v-else>
          {{ (step.items[0].live_status || 'WAITING').toUpperCase() }}
        </span>
      </td>
    </tr>

    <tr v-for="item in step.items.slice(1)" :key="item.item_id" :class="{ 'blinking-highlight': isNextStep(stepIndex) }">
      <td>{{ item.item_id }}</td>

      <td>
        <span v-if="getItemStatus(item.item_id).toUpperCase() === 'SCANNED'" style="color: green;">
          SCANNED
        </span>
        <span v-else-if="getItemStatus(item.item_id).toUpperCase() === 'PENDING'" >
          PENDING
        </span>
        <span v-else-if="getItemStatus(item.item_id).toUpperCase() === 'DONE'" 
        :style="{ color: status.process_state === 'PRESCANNING' ? 'green' : 'gray', fontWeight: 'bold' }">
    DONE
  </span>
        <span v-else>
          {{ getItemStatus(item.item_id).toUpperCase() }}
        </span>
      </td>

      <td>
        <span v-if="stepIndex === status.current_step_index + 1 && item.live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
          SCANNED
        </span>
        <span v-else-if="item.live_status === 'READY_TO_LOAD'" style="color: blue; ">
          READY TO LOAD
        </span>
        <span v-else-if="item.live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
          SCANNED
        </span>
        <span v-else-if="item.live_status === 'MIXING'" style="color: green; font-weight: bold;">
          MIXING
        </span>
        <span v-else-if="item.live_status === 'ABORTED'" style="color: red; font-weight: bold;">
              ABORTED
            </span>
        
        <span v-else-if="item.live_status === 'DONE'" style="color: gray; font-weight: bold;">
          DONE
        </span>
        <span v-else>
          {{ (item.live_status || 'WAITING').toUpperCase() }}
        </span>
      </td>
    </tr>
  </template>
</tbody>
      </table>

      <!-- Scanner Panel -->
      <div class="scanner-panel">
        <!-- Prescan Input -->
        <div v-if="status.process_state === 'PRESCANNING'">
          <h3>Scan Item (Prescan)</h3>
          <input
            type="text"
            v-model="barcode"
            placeholder="Scan item barcode (prescan)"
            @keyup.enter="handlePrescan"
            ref="barcodeInput"
          />
        </div>

        <!-- Actual Scan Input -->
        <div v-else-if="status.process_state === 'WAITING_FOR_ITEMS' || status.process_state === 'MIXING'">
          <h3>Scan Item (Actual)</h3>
          <input
            type="text"
            v-model="barcode"
            placeholder="Scan item barcode (actual)"
            @keyup.enter="handleScan"
            ref="barcodeInput"
          />
        </div>
       



       <!-- Abort / Resume / Complete Abort Buttons -->
<div class="control-buttons" style="margin-top: 1rem; text-align: center;">
  <!-- Simple Abort button that triggers confirmation -->
  <button
    v-if="['MIXING'].includes(status.process_state)"
    @click="abortProcess"
    class="btn btn-danger"
  >
    Abort
  </button>

  <!-- After aborted: show Resume + Complete Abort -->
  <div v-if="status.process_state === 'ABORTED'" style="display:flex; gap:10px; justify-content:center;">
    <button @click="resumeProcess" class="btn btn-success">
      Resume
    </button>
    <button @click="completeAbortProcess" class="btn btn-warning">
      Stop the process
    </button>
  </div>
</div>

      </div>
    </div>
    <!-- Wrong Stage Item Dialog -->
<div class="confirmation-dialog" v-if="showWrongStagePopup">
  <div class="dialog-content">
    <h3>Wrong Stage Item!</h3>
    <p>{{ wrongStageMessage }}</p>
    <button @click="closeWrongStagePopup" class="btn btn-primary">OK</button>
  </div>
</div>
 <!-- Add the new Early Scanning Wrong Item Dialog -->
    <div class="confirmation-dialog" v-if="showEarlyScanningWrongItemPopup">
      <div class="dialog-content">
        <h3>Wrong Item for Next Stage!</h3>
        <p>{{ earlyScanningWrongItemMessage }}</p>
        <button @click="closeEarlyScanningWrongItemPopup" class="btn btn-primary">OK</button>
      </div>
    </div>
<div class="confirmation-dialog" v-if="showDuplicateScanPopup">
  <div class="dialog-content">
    <h3>Duplicate Scanning!</h3>
    <p>{{ duplicateScanMessage }}</p>
    <button @click="closeDuplicateScanPopup" class="btn btn-primary">OK</button>
  </div>
</div>


    <!-- Confirmation Dialog -->
    <div class="confirmation-dialog" v-if="showPrescanCompletePopup">
      <div class="dialog-content">
        <h3>Pre-scanning Complete!</h3>
        <p>All items have been scanned successfully.</p>
        <button @click="confirmPrescan" class="btn btn-primary">OK</button>
      </div>
    </div>
    <!-- Wrong Item Scanned Dialog -->
<div class="confirmation-dialog" v-if="showWrongItemPopup">
  <div class="dialog-content">
    <h3>Wrong Item Scanned!</h3>
    <p>{{ wrongItemMessage }}</p>
    <button @click="closeWrongItemPopup" class="btn btn-primary">OK</button>
  </div>
</div>
<!-- Abort Confirmation Dialog -->
<div class="confirmation-dialog" v-if="showAbortConfirmationPopup">
  <div class="dialog-content">
    <h3>Confirm Abort</h3>
    <p>Are you sure you want to abort the process?</p>
    <div style="display:flex; gap:10px; justify-content:center; margin-top:1rem;">
      <button @click="confirmAbort" class="btn btn-danger">Yes, Abort</button>
      <button @click="cancelAbort" class="btn btn-primary">No, Continue</button>
    </div>
  </div>
</div>

    <!-- Process Complete Dialog -->
    <div class="completion-popup" v-if="showCompletionPopup">
      <div class="popup-content">
        <h3>Process Complete!</h3>
        <button @click="handleCompletionOk" class="btn btn-primary">OK</button>
      </div>
    </div>

  </div>
</template>
<script>
import {
  getStatus,
  scanItem,
  abortProcess,
  resetController,
  resetProcess,
  getWorkorders,
  checkTransitions,
  resumeProcess,
  getBatches,
  loadWorkorder,
  confirmPrescanAPI,
  confirmCompletion,
  prescanItem,
  completeAbortProcess,
   cancelProcess 
} from '@/api'

export default {
  name: 'Dashboard',
  data() {
    return {
      showCancelConfirmation: false,
      showCancelProcessConfirmation: false,
      showEarlyScanningWrongItemPopup: false,
      earlyScanningWrongItemMessage: '',
      showAbortConfirmationPopup: false,
      batchType: null,  // "master" or "compound"
      showPrescanCompletePopup: false,
      showCompletionPopup: false,
      showWrongItemPopup: false,
      wrongItemMessage: '',
      showWrongStagePopup: false,
    wrongStageMessage: '',
      showConfirmPopup: false,
      batches: [],
      enteredBatchNumber: '',
      selectedBatch: null,
      workorder: null,
      showBatchSelection: true,
      showPrescanning: false,
      prescanResults: {}, 
      showDuplicateScanPopup: false,
      duplicateScanMessage: '',
      prescanComplete: false,
      actualScanning: false,
      mixing: false,
      mixingTimer: 0,
      mixingInterval: null,
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
      showingCompletion: false,
      autoTransitionTimeout: null
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
   // Show cancel button only during first stage waiting/ready states and prescan
showCancelButton() {
  const showStates = [
    'PRESCANNING', 
    'PRESCAN_COMPLETE', 
    'IDLE'
  ];
  
  // For WAITING_FOR_ITEMS and READY_TO_LOAD, only show during first stage (stage 1)
  if (['WAITING_FOR_ITEMS', 'READY_TO_LOAD'].includes(this.status.process_state)) {
    return this.status.current_step_index === 0; // Only stage 1 (index 0)
  }
  
  return this.showBatchSelection || showStates.includes(this.status.process_state);
},

// Enable cancel button - only during first stage waiting/ready and prescan states
isCancelDisabled() {
  // Always enable during prescan states
  if (['PRESCANNING', 'PRESCAN_COMPLETE', 'IDLE'].includes(this.status.process_state)) {
    return false;
  }
  
  // For WAITING_FOR_ITEMS and READY_TO_LOAD, only enable during first stage
  if (['WAITING_FOR_ITEMS', 'READY_TO_LOAD'].includes(this.status.process_state)) {
    // For first stage, always enable cancel (regardless of scan status)
    if (this.status.current_step_index === 0) {
      return false; // Always enable cancel during stage 1
    }
    // For other stages, disable cancel
    return true;
  }
  
  // Disable during all other processing states
  const disabledStates = [
    'MIXING', 
    'ABORTED',
    'WAITING_FOR_LID_CLOSE',
    'WAITING_FOR_MOTOR_START',
    'PROCESS_COMPLETE'
  ];
  return disabledStates.includes(this.status.process_state);
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
    },
    blinkingStageIndex() {
    if (this.status.process_state === 'MIXING') {
      return this.status.current_step_index + 1;
    }
    return -1;
  }
  },
  async mounted() {
  console.log('Mounted, checking backend state');
  
  // Restore saved batch type and batch number from localStorage
  const savedType = localStorage.getItem('lastBatchType');
  const savedBatch = localStorage.getItem('lastBatchNumber');
  
  if (savedType) {
    this.batchType = savedType;
    console.log("Restored saved batch type:", savedType);
  }
  
  if (savedBatch) {
    this.enteredBatchNumber = savedBatch;
    console.log("Restored saved batch number:", savedBatch);
  }
  
  try {
    const statusResp = await getStatus();
    console.log("Backend status on reload:", statusResp);

    // Sync frontend UI to backend state
    this.status = statusResp;
    
    // Only set workorder if backend has steps and we don't already have one
    if (statusResp.steps?.length && !this.workorder) {
      this.workorder = { 
        name: statusResp.workorder_name, 
        steps: statusResp.steps 
      };
    }

    // Restore batch type from backend if available, otherwise keep from localStorage
    this.batchType = statusResp.workorder_type || this.batchType;

    // 🔥 CRITICAL: Determine which screen to show based on state
    if (statusResp.process_state === 'IDLE') {
      // If we have a batch type but no active workorder, show batch number entry screen
      if (this.batchType && !this.workorder) {
        this.showBatchSelection = true;
        this.showPrescanning = false;
        console.log("Showing batch number entry screen (reload with batch type)");
      } 
      // If we have a workorder, show the prescanning screen
      else if (this.workorder) {
        this.showBatchSelection = false;
        this.showPrescanning = true;
        console.log("Showing prescanning screen (reload with workorder)");
      }
      // Otherwise show batch type selection
      else {
        this.showBatchSelection = false;
        this.showPrescanning = false;
        console.log("Showing batch type selection screen (fresh start)");
      }
    } else {
      // If backend is in any other state, show the appropriate screen
      this.showBatchSelection = false;
      this.showPrescanning = true;
      console.log("Backend has active process, showing prescanning screen");
    }

  } catch (err) {
    console.error("Error checking controller state:", err);
    // On error, fall back to showing batch selection if we have a batch type
    if (this.batchType) {
      this.showBatchSelection = true;
      this.showPrescanning = false;
    }
  }

  console.log('Mounted state - showBatchSelection:', this.showBatchSelection, 
              'batchType:', this.batchType, 
              'enteredBatchNumber:', this.enteredBatchNumber,
              'workorder:', this.workorder);

  // Load batches/workorders for selection
  await this.loadBatches();
  await this.loadWorkorders();
  this.startPolling();

  this.$nextTick(() => {
    if (this.showBatchSelection && this.$refs.batchInput) {
      this.$refs.batchInput.focus();
    } else if (this.showPrescanning && this.$refs.barcodeInput) {
      this.$refs.barcodeInput.focus();
    }
  });
},
  beforeUnmount() {
    if (this.autoTransitionTimeout) {
      clearTimeout(this.autoTransitionTimeout);
    }
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
    },
    enteredBatchNumber(newVal) {
    if (newVal.trim() !== '') {
      localStorage.setItem('lastBatchNumber', newVal.trim());
    }
  },
    prescanComplete(newVal) {
      if (newVal) {
        this.initiateAutoTransition();
      }
    }
  },
  methods: {
    // Show confirmation popup instead of direct cancellation
  showCancelConfirmationPopup() {
    this.showCancelConfirmation = true;
  },// User confirms cancellation
  confirmCancelBatchSelection() {
  console.log("User confirmed batch selection cancellation");
  
  // Reset frontend state
  this.batchType = null;
  this.enteredBatchNumber = '';
  this.selectedBatch = null;
  this.workorder = null;
  this.scannedItems = [];
  
  // Remove localStorage
  localStorage.removeItem('lastBatchType');
  localStorage.removeItem('lastBatchNumber');
  
  // Update screen state
  this.showBatchSelection = false;
  this.showPrescanning = false;
  this.showCancelConfirmation = false;
  
  console.log("Batch selection cancelled - back to batch type selection");
},

  // User chooses to continue (No button)
  cancelCancelBatchSelection() {
    console.log("User cancelled the cancellation");
    this.showCancelConfirmation = false;
    // Focus back on the input field
    this.$nextTick(() => {
      if (this.$refs.batchInput) this.$refs.batchInput.focus();
    });
  },
confirmCancelProcess() {
    this.showCancelProcessConfirmation = false;
    this.cancelProcess(); // Call your existing cancelProcess method
  },

  cancelCancelProcess() {
    this.showCancelProcessConfirmation = false;
    this.$nextTick(() => {
      if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus();
    });
  },
    isNextStep(stepIndex) {
      if (this.status.process_state !== 'MIXING') return false;
      if (stepIndex !== this.status.current_step_index + 1) return false;
      if (stepIndex >= this.status.steps.length) return false;
      return !this.isStepFullyScanned(stepIndex);
    },
    isStepFullyScanned(stepIndex) {
      const step = this.status.steps[stepIndex];
      if (!step || !step.items) return false;
      return step.items.every(item => item.live_status === 'SCANNED');
    },
    selectBatchType(type) {
  this.batchType = type;  
  localStorage.setItem('lastBatchType', type);     
  this.showBatchSelection = true;
  this.showPrescanning = false;
  
  // Focus on batch input when transitioning to batch number entry
  this.$nextTick(() => {
    if (this.$refs.batchInput) this.$refs.batchInput.focus();
  });
},

    async loadBatches() {
      try {
        const response = await getBatches();
        this.batches = response;
        console.log('Loaded batches:', this.batches);
      } catch (error) {
        console.error('Failed to load batches:', error);
      }
    },
    closeWrongItemPopup() {
    this.showWrongItemPopup = false;
    this.wrongItemMessage = '';
    this.barcode = '';
    this.$nextTick(() => { 
      if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
    });
  },
  getStatusMessage() {
  // Guard: if no steps yet, just return empty string
  if (!this.workorder || !this.workorder.steps) {
    return '';
  }
  const currentStage = this.status.current_step_index + 1;
  const nextStage = currentStage + 1;
  
  switch (this.status.process_state) {
    case 'READY_TO_LOAD':
      return `Add Stage ${currentStage} items to the kneader`;
    
    case 'IDLE': return 'Prescan';
    case 'PRESCANNING': return 'Prescanning in progress';
    case 'PROCESS_COMPLETE': return '✅ Process Complete!';
    
    case 'WAITING_FOR_ITEMS': 
      // Check if current stage has items ready to load
      if (this.isStepReadyToLoad(this.status.current_step_index)) {
        return `Load stage - ${currentStage} items`;
      }
      return `Enter the item code for Stage ${currentStage}`;
      
    case 'MIXING':
      // Check if next stage has items ready to load during mixing
      if (this.isStepReadyToLoad(this.status.current_step_index + 1)) {
        return `Load stage - ${nextStage} items`;
      }
      
      if (this.workorder && this.status.current_step_index < this.workorder.steps.length - 1) {
        return `Mixing Stage ${currentStage}, scan Stage ${nextStage} items`;
      } else {
        return `Mixing Stage ${currentStage}`;
      }
      
    case 'WAITING_FOR_MOTOR_START': return 'Waiting for motor to start';
    case 'ABORTED': return ' Process Aborted. Click Resume to continue';
    default: return '';
  }
},
getRemainingReadyTime() {
  
  
  return '10'; 
},
async loadBatchByNumber() {
  console.log('loadBatchByNumber called with:', this.enteredBatchNumber);
  const bn = (this.enteredBatchNumber || '').trim();
  if (!bn) return;
  try {
    const response = await loadWorkorder({
      batchNumber: bn,
      batchType: this.batchType   
    });
    if (response && response.status === 'error') {
      this.scanResult = { status: 'error', message: response.message || 'Failed to load batch' };
      return;
    }
    if (response && response.workorder) {
      // Clear frontend state
      this.scannedItems = [];
      this.prescanResults = {};
      
      // Set new workorder
      this.workorder = response.workorder;
      this.selectedBatch = { batch_number: bn, name: response.workorder.name || bn };
      
      // Update screen state
      this.showBatchSelection = false;
      this.showPrescanning = true;
      this.prescanComplete = false;
      
      // 🔥 Save batch number to localStorage (already done by watcher, but ensure it's saved)
      localStorage.setItem('lastBatchNumber', bn);
      
      this.$nextTick(() => { 
        if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
      });
    } else {
      this.scanResult = { status: 'error', message: response.message || 'Failed to load workorder' };
    }
  } catch (err) {
    console.error('Failed to load batch:', err);
    this.scanResult = { status: 'error', message: 'Failed to load batch' };
  }
},
async completeAbortProcess() {
  console.log('Complete Abort button clicked');
  try {
    const response = await completeAbortProcess();
    console.log('Complete Abort API response:', response);
    
    if (response && response.status === 'success') {
      console.log('Complete Abort successful, resetting frontend state');
      // Reset frontend state
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
      };
      this.batchType = null;
      localStorage.removeItem('lastBatchType');
      localStorage.removeItem('lastBatchNumber');

      this.showBatchSelection = true;
      this.showPrescanning = false;
      this.workorder = null;
      this.enteredBatchNumber = '';
      this.scannedItems = [];
      
      this.scanResult = { 
        status: 'success', 
        message: 'Process completely aborted and reset to IDLE' 
      };
    } else {
      console.log('Complete Abort failed:', response);
      this.scanResult = { 
        status: 'error', 
        message: response?.message || 'Failed to completely abort' 
      };
    }
  } catch (error) {
    console.error('Complete Abort API call failed:', error);
    this.scanResult = { 
      status: 'error', 
      message: 'Failed to completely abort process' 
    };
  }
},
closeEarlyScanningWrongItemPopup() {
      this.showEarlyScanningWrongItemPopup = false;
      this.earlyScanningWrongItemMessage = '';
      this.barcode = '';
      this.$nextTick(() => { 
        if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
      });
    },
    getItemStatus(itemId) {
  // strictly prescan status only
  if (this.status.prescan_status && this.status.prescan_status.status_by_stage) {
    for (let stage in this.status.prescan_status.status_by_stage) {
      const item = this.status.prescan_status.status_by_stage[stage].items.find(i => i.item_id === itemId);
      if (item) {
        return item.prescan_status.toLowerCase(); // "scanned" / "pending"
      }
    }
  }
  return 'pending';
},



    getActualItemStatus(itemId, stepIndex) {
  if (stepIndex < this.status.current_step_index) return 'done';
  if (stepIndex > this.status.current_step_index) return 'waiting';

  // Inside current step
  if (this.status.scanned_items && this.status.scanned_items.includes(itemId)) {
    return 'done';
  }

  // The next item expected
  const currentItem = this.workorder.steps[this.status.current_step_index]
    .items[this.status.current_item_index];
  if (currentItem && currentItem.item_id === itemId) {
    return 'in-progress';
  }

  return 'waiting';
},
getItemStatus(itemId) {
  if (this.status.process_state === 'PRESCANNING') {
    if (this.status.prescan_status && this.status.prescan_status.status_by_stage) {
      for (let stage in this.status.prescan_status.status_by_stage) {
        const item = this.status.prescan_status.status_by_stage[stage].items.find(i => i.item_id === itemId);
        if (item) {
          // map "scanned" → "done"
          if (item.prescan_status.toLowerCase() === 'scanned') {
            return 'done';
          }
          return item.prescan_status.toLowerCase();
        }
      }
    }
    return 'pending';
  }

  // After prescan confirmed, everything should stay as "done"
  if (this.status.prescan_complete || this.showPrescanCompletePopup === false) {
    return 'done';
  }

  return 'pending';
},

   

    async handlePrescan() {
  if (!this.barcode.trim()) return;
  try {
    const result = await prescanItem(this.barcode.trim());
    if (result && result.status === 'success') {
      this.prescanResults[this.barcode.trim()] = 'done';
      if (!this.scannedItems.includes(this.barcode.trim())) {
        this.scannedItems.push(this.barcode.trim());
      }
      this.markPrescanCompleteIfDone();
      this.scanResult = result;
    } else if (result && result.status === 'error') {
      // Check if it's a duplicate scan error
      if (result.message && result.message.includes('already scanned')) {
        // Show duplicate scan popup
        this.duplicateScanMessage = result.message || 'This item has already been scanned.';
        this.showDuplicateScanPopup = true;
        this.scanResult = null;
      } else {
        // Show wrong item popup
        this.wrongItemMessage = result.message || 'This item does not belong to the current workorder.';
        this.showWrongItemPopup = true;
        this.scanResult = null;
      }
    } else {
      this.scanResult = result;
    }
    
    this.barcode = '';
    this.$nextTick(() => { if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); });
  } catch (error) {
    console.error('Failed to prescan item:', error);
    this.scanResult = { 
      status: 'error', 
      message: 'Scan failed: ' + (error.response?.data?.error || error.message) 
    };
  }
},
// Keep cancelBatchSelection method for batch selection screen
    cancelBatchSelection() {
      console.log("Cancel batch selection clicked");
      
      // Reset frontend state only (no API call needed)
      this.batchType = null;
      this.enteredBatchNumber = '';
      this.selectedBatch = null;
      this.workorder = null;
      this.scannedItems = [];
      
      // Remove localStorage
      localStorage.removeItem('lastBatchType');
      localStorage.removeItem('lastBatchNumber');
      
      // Show first screen (batch type selection)
      this.showBatchSelection = false;
      
      console.log("Batch selection cancelled - back to batch type selection");
    },
async cancelProcess() {
  try {
    console.log("Cancel button clicked");
    const response = await cancelProcess(); // API call

    if (response.status === 'success' && response.data.process_state === 'IDLE') {
      // Reset full UI to initial state
      this.status = response.data;
      this.workorder = null;
      this.batchType = null;
      this.enteredBatchNumber = '';
      this.scannedItems = [];
      this.scanResult = { status: 'success', message: 'Prescan cancelled successfully. System reset to IDLE.' };

      // Hide prescan panel, show batch selection
      this.showPrescanning = false;
      this.showBatchSelection = true;

      // Remove localStorage memory of last batch
      localStorage.removeItem('lastBatchType');
      localStorage.removeItem('lastBatchNumber');

      console.log("UI reset after cancel: back to batch selection");
    } else {
      this.scanResult = { status: 'error', message: response.message || 'Cancel failed' };
    }
  } catch (error) {
    console.error("Cancel API error:", error);
    this.scanResult = { status: 'error', message: 'Cancel action failed' };
  }
},


    initiateAutoTransition() {
      this.barcode = '';
      this.scanResult = { status: 'success', message: 'Pre-scanning complete! Transitioning to mixing process...' };
      this.autoTransitionTimeout = setTimeout(() => {
        this.confirmPrescan();
      }, 2000);
    },

    markPrescanCompleteIfDone() {
  if (this.scannedItemsCount === this.totalItemsCount) {
    // Show popup instead of flipping the whole UI
    this.showPrescanCompletePopup = true;

   

    this.barcode = "";
  }
},
closeWrongStagePopup() {
    this.showWrongStagePopup = false;
    this.wrongStageMessage = '';
    this.barcode = '';
    this.$nextTick(() => { 
      if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
    });
  },
  closeDuplicateScanPopup() {
  this.showDuplicateScanPopup = false;
  this.duplicateScanMessage = '';
  this.barcode = '';
  this.$nextTick(() => { 
    if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
  });
},

    startMixing(seconds) {
      this.mixing = true;
      this.mixingTimer = seconds;
      this.mixingProgress = 0;

      this.mixingInterval = setInterval(() => {
        this.mixingTimer--;
        this.mixingProgress = Math.floor(((seconds - this.mixingTimer) / seconds) * 100);

        if (this.mixingTimer <= 0) {
          clearInterval(this.mixingInterval);
          this.mixing = false;
          this.actualScanning = true;
          this.nextStep();
        }
      }, 1000);
    },

    nextStep() {
      this.currentStepIndex++;
      this.barcode = "";
    },

    async confirmPrescan() {
  try {
    const response = await confirmPrescanAPI();
    if (response && response.status === 'success') {
      
      this.showPrescanCompletePopup = false;

      // force prescan column to "done"
      this.status.prescan_complete = true;

      this.barcode = '';

      
      let attempts = 0;
      while (attempts < 15) {
        await this.updateStatus();
        if (this.status.process_state === 'WAITING_FOR_ITEMS') {
          this.scanResult = {
            status: 'success',
            message: 'Prescanning completed. Scan the items for the stage 1 mixing process'
          };
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
        attempts++;
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

    formatMixTime(seconds) {
      if (!seconds && seconds !== 0) return '—';
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      if (mins > 0) {
        return `${mins}m ${secs}s`;
      }
      return `${secs}s`;
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
      switch (this.status.process_state) {
        case 'MIXING':
          this.$nextTick(() => console.log('Mixing state active'));
          break;
        case 'WAITING_FOR_ITEMS':
          this.$nextTick(() => {
            if (this.$refs.actualBarcodeInput) this.$refs.actualBarcodeInput.focus();
            console.log('Waiting for items, focusing scanner');
          });
          break;
        case 'PRESCANNING':
          this.showPrescanning = true;
          this.updatePrescanProgress();
          this.$nextTick(() => { if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); });
          break;
        default:
          //this.showPrescanning = false;
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
    if (newStatus.process_state === 'PRESCAN_COMPLETE' && !this.showPrescanCompletePopup) {
  this.showPrescanCompletePopup = true;
}


    if (newStatus.process_state === 'WAITING_FOR_ITEMS') {
      this.$nextTick(() => { 
        if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); 
      });
    }

    if (this.showPrescanning && newStatus.process_state === 'WAITING_FOR_ITEMS') {
      this.showPrescanning = true;
    }

    if (newStatus.just_completed || newStatus.process_state === 'PROCESS_COMPLETE') {
      if (!this.showCompletionPopup) {
        console.log("Process complete detected -> showing popup")
        this.showCompletionPopup = true
      }
    }

  } catch (error) {
    console.error('Failed to update status:', error)

    // 
    this.status = {
      ...this.status,  // keep old steps, items, etc.
      error_message: 'Failed to update status'
    }
  }
},
shouldBlink(stepIndex) {
    return stepIndex === this.blinkingStageIndex;
  },

   getStepStatus(stepIndex) {
  // During PRESCANNING → keep using backend prescan_status
  if (this.status.process_state === 'PRESCANNING') {
    if (this.status.prescan_status && this.status.prescan_status.status_by_stage) {
      const stage = this.status.prescan_status.status_by_stage[stepIndex + 1];
      if (stage && stage.live_status) {
        return stage.live_status.toLowerCase();
      }
    }
    return 'waiting';
  }

  // After prescan → drive from actual scanning/mixing state
  if (this.status.process_state === 'WAITING_FOR_ITEMS') {
    if (stepIndex < this.status.current_step_index) {
      return 'done'; // already completed step
    }
    if (stepIndex === this.status.current_step_index) {
      return 'in-progress'; // current step waiting for items
    }
    return 'waiting'; // future steps
  }

  if (this.status.process_state === 'MIXING') {
    if (stepIndex === this.status.current_step_index) {
      return 'mixing';
    }
    if (stepIndex < this.status.current_step_index) {
      return 'done';
    }
    return 'waiting';
  }

  if (this.status.process_state === 'PROCESS_COMPLETE') {
    return 'done';
  }

  return 'waiting';
},
// Check if a specific step has items in READY_TO_LOAD state
isStepReadyToLoad(stepIndex) {
  if (stepIndex < 0 || stepIndex >= this.status.steps.length || !this.status.steps) return false;
  
  const step = this.status.steps[stepIndex];
  if (!step || !step.items || step.items.length === 0) return false;
  
  // Check if all items in the step are READY_TO_LOAD
  return step.items.every(item => item.live_status === 'READY_TO_LOAD');
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
  console.log("Sending scan:", this.barcode.trim());

  try {
    const result = await scanItem(this.barcode.trim());

    if (result.error) {
      this.scanResult = { status: 'error', message: 'Scan failed: ' + result.error };
    } else if (result.status === 'fail') {
      // Show wrong stage popup
      if (
          result.message && 
          (result.message.includes('does not belong to this stage') || 
          result.message.includes('does not belong to this or next step'))
        ) {
          // Check if this is early scanning (mixing state)
          if (this.status.process_state === 'MIXING') {
            const nextStageNumber = this.status.current_step_index + 2;
            this.earlyScanningWrongItemMessage = `This item does not belong to Stage ${nextStageNumber}. Please scan the correct item for the next stage.`;
            this.showEarlyScanningWrongItemPopup = true;
          } else {
            this.wrongStageMessage = "Item does not belong to this stage";
            this.showWrongStagePopup = true;
          }
          this.scanResult = null;
          this.barcode = '';
        } else {
          this.scanResult = { status: 'error', message: result.message };
        }
      }else {
      // Success case
      const stepIndex = this.status.current_step_index;
      const isMixing = this.status.process_state === 'MIXING';

      let allowedStepIndexes = isMixing ? [stepIndex + 1] : [stepIndex];

      const allowedItems = allowedStepIndexes.flatMap(
        idx => this.workorder.steps[idx]?.items.map(i => i.item_id) || []
      );

      // Check if scanned item belongs to allowed items
      if (!allowedItems.includes(this.barcode.trim())) {
        // Check if this is early scanning (mixing state)
        if (isMixing) {
          const nextStageNumber = this.status.current_step_index + 2;
          this.earlyScanningWrongItemMessage = `Invalid item for Stage ${nextStageNumber}`;
          this.showEarlyScanningWrongItemPopup = true;
        } else {
          this.wrongStageMessage = 'Invalid item for this stage';
          this.showWrongStagePopup = true;
        }
        this.scanResult = null;
        this.barcode = '';
        return;
      }

      // Success
      this.scanResult = result;
      if (result.status === 'success') {
        this.barcode = '';
        this.$nextTick(() => {
          if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus();
        });
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
    this.showAbortConfirmationPopup = true;
  },

  // Add new methods for confirmation handling
  async confirmAbort() {
    try {
      this.showAbortConfirmationPopup = false;
      // Call the actual abort API
      await abortProcess();
      this.scanResult = { 
        status: 'success', 
        message: 'Process aborted successfully' 
      };
    } catch (error) {
      console.error('Failed to abort process:', error);
      this.scanResult = { 
        status: 'error', 
        message: 'Failed to abort process' 
      };
    }
  },

  cancelAbort() {
    this.showAbortConfirmationPopup = false;
    this.scanResult = { 
      status: 'info', 
      message: 'Abort cancelled - process continues' 
    };
  },

    async resumeProcess() {
      try {
        await resumeProcess()
      } catch (error) {
        console.error('Failed to resume process:', error)
      }
    },
    
    confirmProcessComplete() {
  this.showProcessCompletePopup = false;
  this.status.process_state = 'IDLE';
  this.showBatchSelection = true;
  this.showPrescanning = false;
  this.workorder = null;
  this.enteredBatchNumber = '';
},


    pollStatus() {
      this.interval = setInterval(() => {
        getStatus().then(data => {
          console.log('Polled status:', data);
          this.status = data;
          this.updateUIState();
        }).catch(error => console.error('Polling error:', error));
      }, 1000);
    },

   async handleCompletionOk() {
  try {
    const response = await confirmCompletion()
    if (response.status === 'success') {
      this.showCompletionPopup = false
      this.status = { process_state: 'IDLE' }
      this.batchType = null
      localStorage.removeItem('lastBatchType');
      localStorage.removeItem('lastBatchNumber');
      this.showBatchSelection = true
      this.showPrescanning = false
      this.workorder = null
      this.enteredBatchNumber = ''
    } else {
      console.error("Completion confirm failed:", response.message)
    }
  } catch (err) {
    console.error('Failed to reset process after completion:', err)
  }
}


  }
}
</script>

<style scoped>
/* (kept your CSS) */
/* Add styles for the automatic transition message */
.batch-option {
  border: 2px solid #007bff;
  border-radius: 8px;
  padding: 2rem;
  cursor: pointer;
  font-size: 1.2rem;
  font-weight: bold;
  text-align: center;
  width: 180px;
  transition: 0.2s;
}
.batch-option:hover {
  background-color: #007bff;
  color: white;
  transform: translateY(-3px);
}

.auto-transition-message {
  margin-top: 1rem;
  padding: 1rem;
  background-color: #d4edda;
  color: #155724;
  border-radius: 4px;
  text-align: center;
}
.prescan-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
  text-align: center;
  border: 2px solid #333; /* Add darker outer border */
}

.prescan-table th,
.prescan-table td {
  border: 2px solid #333;
  padding: 10px;
  font-size: 0.95rem;
}

.prescan-table th {
  background-color: #f0f0f0; 
  font-weight: bold;
  color: #333; /* Darker text for better contrast */
}

.prescan-table td {
  background-color: #fff;
}

.prescan-table tr:nth-child(even) td {
   background-color: #f8f8f8;
}

.batch-panel { background-color: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem;border: 2px solid #333; /* Add darker border */ }
.batch-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }
.batch-item { border: 1px solid #ddd; border-radius: 4px; padding: 1rem; cursor: pointer; transition: background-color 0.2s; }
.batch-item:hover { background-color: #f5f5f5; transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
.batch-name { font-weight: bold; margin-bottom: 0.5rem; }
.batch-number { color: #666; font-size: 0.9rem; }
.prescan-panel { background-color: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 1rem;border: 2px solid #333; /* Add darker border */
} 
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
.status-panel { background-color: white; border-radius:8px; padding:1rem; box-shadow:0 2px 4px rgba(0,0,0,0.1);border: 2px solid #333; /* Add darker border */ }
.status-info { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin-bottom:1rem; }
.status-item { display:flex; flex-direction:column; }
.label { font-weight:bold; margin-bottom:0.25rem; color:#666; }
.value { font-size:1.1rem; }
.open { color:#dc3545; }
.closed { color:#28a745; }
.running { color:#28a745; }
.stopped { color:#6c757d; }
.control-buttons { display:flex; gap:0.5rem; }
.btn { padding:0.6rem 1.2rem; border:2px solid transparent; border-radius:6px; cursor:pointer; font-size:1rem;font-weight: 600;
  transition: all 0.3s ease; }
.btn-danger { background-color:#dc3545; color:white;border-color: #c82333; }
.btn-warning { background-color:#ffc107; color:black; }
.scanner-panel { background-color:white; border-radius:8px; padding:1.5rem; box-shadow:0 2px 4px rgba(0,0,0,0.1);border: 1px solid #ccc; /* Add darker border */ }
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
.confirmation-dialog {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display:flex;
  justify-content:center;
  align-items:center;
  z-index:1000;
}
.completion-popup {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(0, 0, 0, 0.5); /* dark overlay */
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.completion-popup .popup-content {
  background: white;
  padding: 2rem;
  border-radius: 10px;
  text-align: center;
  max-width: 400px;
  width: 100%;
  box-shadow: 0 2px 10px rgba(0,0,0,0.3);
  border: 2px solid #333;
}
/* Abort confirmation specific styling */
.confirmation-dialog .dialog-content {
  background: white;
  padding: 2rem;
  border-radius: 10px;
  text-align: center;
  max-width: 400px;
  width: 100%;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  border: 2px solid #dc3545; /* Red border for abort confirmation */
}

.confirmation-dialog h3 {
  color: #dc3545;
  margin-bottom: 1rem;
}

.confirmation-dialog p {
  margin-bottom: 1.5rem;
  font-size: 1.1rem;
}

.confirmation-dialog .btn-danger {
  background-color: #dc3545;
  border-color: #c82333;
  padding: 0.6rem 1.5rem;
}

.confirmation-dialog .btn-primary {
  background-color: #007bff;
  border-color: #0069d9;
  padding: 0.6rem 1.5rem;
}


.status-line {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  text-align: center;
  background-color:#e8f5e8;    /* light green */
  color: #155724;              /* dark green text */
  border: 2px solid #28a745;   /* green border */
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
}

/* Blinking highlight styles - FIXED VERSION */
.blinking-highlight {
  animation: blinking 1s infinite;
}

@keyframes blinking {
  0% { background-color: yellow; }
  50% { background-color: #ffff99; } /* slightly lighter yellow */
  100% { background-color: yellow; }
}

/* Ensure the blinking effect overrides other background colors */
.prescan-table tr.blinking-highlight td {
  animation: blinking 1s infinite !important;
}

.btn-debug { background-color:#6c757d; color:white; padding:0.25rem 0.5rem; border:none; border-radius:4px; font-size:0.8rem; margin-top:1rem; }
</style>