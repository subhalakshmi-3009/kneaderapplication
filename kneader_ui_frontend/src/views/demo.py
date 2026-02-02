<template>
  <div class="dashboard">
  
<!-- ============ LOGIN SCREEN ============ -->
<div
  v-if="!token"
  class="login-container"
>
  <div class="login-card">
    <!-- Simple Header -->
    <div class="login-header">
      
      <h1 class="login-subtitle">Login to start the process</h1>
    </div>

    <!-- Login Form -->
    <div class="login-form">
      <!-- Username Field -->
      <div class="input-group">
        <label for="username" class="input-label">
          Username
        </label>
        <input
          id="username"
          v-model="username"
          type="text"
          placeholder="Enter your username"
          class="form-input"
          @keyup.enter="login"
        />
      </div>

      <!-- Password Field with Toggle -->
      <div class="input-group">
        <label for="password" class="input-label">
          Password
        </label>
        <div class="password-input-container">
          <input
            id="password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="Enter your password"
            class="form-input password-input"
            @keyup.enter="login"
          />
          <button 
            type="button" 
            class="password-toggle"
            @click="showPassword = !showPassword"
          >
            <span v-if="showPassword" class="toggle-text">Hide</span>
            <span v-else class="toggle-text">Show</span>
          </button>
        </div>
      </div>

      <!-- Login Button -->
      <div class="button-container">
        <button
          @click="login"
          class="login-button"
          :class="{ 'login-button-disabled': !username || !password }"
          :disabled="!username || !password"
        >
          Login
        </button>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="error-message">
        <p class="error-text">{{ error }}</p>
      </div>
    </div>
  </div>
</div>
    <!-- FIRST SCREEN: select batch type -->
     <div v-else>
  <div class="batch-panel" v-if="!batchType && status.process_state === 'IDLE'">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
      <h2 style="margin: 0;">Select Batch Type</h2>
      <button @click="logout" class="btn btn-warning">Logout</button>
    </div>
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
 <template v-for="(step, stepIndex) in (workorder?.steps || [])" :key="step.step_id || stepIndex">

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
  <span
    v-if="getItemStatus(step.items[0].item_id) === 'done'"
    style="color: green; font-weight: bold;"
  >
    DONE
  </span>

  <span v-else>
    PENDING
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
  <span
    v-if="getItemStatus(item.item_id) === 'done'"
    style="color: green; font-weight: bold;"
  >
    DONE
  </span>

  <span v-else>
    PENDING
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
                <div v-if="!actualScanning">
            <h3>Scan Item (Prescan)</h3>
            <input
              type="text"
              v-model="barcode"
              placeholder="Scan item barcode (prescan)"
              @keyup.enter="handlePrescan"
              ref="barcodeInput"
            />
          </div>



        <div v-else-if="actualScanning">
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
<!-- Save Workorder Popup  -->
<div class="confirmation-dialog" v-if="showSavePopup">
  <div class="dialog-content">
    <h3>Save Workorder</h3>
    <p>The process is complete. Would you like to save this workorder?</p>
    <div style="display:flex; gap:10px; justify-content:center; margin-top:1rem;">
      <button @click="handleSaveWorkorder" class="btn btn-success">SAVE</button>
      
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
</div>
</template>
<script>
import {
  login,
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
  saveWorkorder,
  completeAbortProcess,
   cancelProcess 
} from '@/api'

export default {
  name: 'Dashboard',
  data() {
    return {
    username: "",
      password: "",
      showPassword: false,
      token: localStorage.getItem("token")||null,
      showLogin: !localStorage.getItem("token"),
      error: "",
      kneaderStatus: {},
      showSavePopup: false,
      showCancelConfirmation: false,
      showCancelProcessConfirmation: false,
      showEarlyScanningWrongItemPopup: false,
      earlyScanningWrongItemMessage: '',
      showAbortConfirmationPopup: false,
      batchType: null,  // "master" or "compound"
      showPrescanCompletePopup: false,
      showCompletionPopup: false,
      prescanAwaitingConfirmation: false,
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
      sessionId: null,

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
      autoTransitionTimeout: null,

      hasShownSavePopup: false,
      hasShownCompletionPopup: false
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
  this.token = localStorage.getItem("token");
  
  // Only proceed if user is logged in
  if (!this.token) {
    console.log("No token found, staying on login screen");
    //this.showLogin = true;
    return;
  }
  
  // Test the token first
  try {
    console.log("Testing token validity...");
    await getStatus();
    //const testResponse = await getStatus();
    console.log("Token is valid, proceeding...");
    //this.showLogin = false;
  } catch (error) {
    console.error("Token validation failed:", error);
    if (error.message.includes('401') || error.message.includes('Missing Authorization')) {
      console.log("Token invalid or expired, forcing logout");
      this.logout();
      return;
    }
  }
  
  // Rest of your mounted() code...
  const savedType = localStorage.getItem('lastBatchType');
  const savedBatch = localStorage.getItem('lastBatchNumber');
  
  if (savedType) {
    this.batchType = savedType;
  }
  
  if (savedBatch) {
    this.enteredBatchNumber = savedBatch;
  }
  
  try {
    const statusResp = await getStatus();
    this.status = statusResp;
    
    // convert "120 secs" → 120
function parseSeconds(mixingTime) {
  if (mixingTime == null) return null;
  if (typeof mixingTime === 'number') return Math.floor(mixingTime);
  const m = String(mixingTime).match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

if (!this.workorder) {

  // CASE 1: backend already returns workorder-style steps
  if (statusResp.steps?.length) {
    this.workorder = {
      name: statusResp.workorder_name,
      steps: statusResp.steps
    };
  }

  // CASE 2: backend returns sequence_steps (your current format)
  else if (statusResp.sequence_steps?.length) {
    const steps = statusResp.sequence_steps.map((s, idx) => ({
      step_id: idx + 1,
      mix_time_sec: parseSeconds(s.mixing_time),
      items: (s.items || []).map(it => ({
        item_id: String(it),
        name: null,
        required_weight: null
      }))
    }));

    this.workorder = {
      name: statusResp.workorder_name || `Workorder ${statusResp.batch_no || ''}`,
      steps
    };
  }
}


    this.batchType = statusResp.workorder_type || this.batchType;

    if (statusResp.process_state === 'IDLE') {
      if (this.batchType && !this.workorder) {
        this.showBatchSelection = true;
        this.showPrescanning = false;
      } else if (this.workorder) {
        this.showBatchSelection = false;
        this.showPrescanning = true;
      } else {
        this.showBatchSelection = false;
        this.showPrescanning = false;
      }
    } else {
      this.showBatchSelection = false;
      this.showPrescanning = true;
    }

  } catch (err) {
    console.error("Error checking controller state:", err);
    if (err.response && (err.response.status === 401 || err.response.status === 422)) {
      this.logout();
      return;
    }
    if (this.batchType) {
      this.showBatchSelection = true;
      this.showPrescanning = false;
    }
  }

  // Load data with error handling
  try {
    await this.loadBatches();
  } catch (err) {
    console.error('Failed to load batches:', err);
  }
  
  try {
    await this.loadWorkorders();
  } catch (err) {
    console.error('Failed to load workorders:', err);
  }
  
  if (this.token) {
    this.startPolling();
  }

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
    // ✅ ONLY show popup
    this.showPrescanCompletePopup = true;
    this.prescanAwaitingConfirmation = true;

    // ❌ DO NOT auto-confirm
    // this.initiateAutoTransition();
  }
}

  },
  methods: {
  async login() {
  this.error = "";
  try {
    const res = await login(this.username, this.password);
    console.log("Login response:", res);

    if (res.token) {
      // Save token and switch to main app
      localStorage.setItem("token", res.token);
      this.token = res.token;
      
      console.log("Token stored in localStorage:", localStorage.getItem("token"));
      console.log("Token length:", res.token.length);

      // Hide login and go to batch selection
      this.showBatchSelection = false;
      this.batchType = null;
      this.status = { process_state: "IDLE" };

      // ✅ START POLLING AFTER LOGIN
      this.startPolling();

      // ✅ Force a status check to update the UI
      try {
        await this.updateStatus();
      } catch (err) {
        console.error("Initial status check failed:", err);
      }

      console.log("✅ Login successful — moving to batch type selection");
      console.log("Current state - showBatchSelection:", this.showBatchSelection);
      console.log("Current state - showPrescanning:", this.showPrescanning);
      console.log("Current state - batchType:", this.batchType);
      
    } else {
      this.error = "Invalid ERPNext credentials";
    }
  } catch (err) {
    console.error("Login error:", err);
    this.error = "Login failed. Please check your credentials.";
  }
},
  logout() {
  console.log("Logging out...");
  
  // Clear all localStorage items
  localStorage.removeItem("token");
  localStorage.removeItem('lastBatchType');
  localStorage.removeItem('lastBatchNumber');
  
  // Reset all component state
  this.token = null;
  this.username = "";
  this.password = "";
  this.error = "";
  this.batchType = null;
  this.enteredBatchNumber = '';
  this.selectedBatch = null;
  this.workorder = null;
  this.showBatchSelection = false;
  this.showPrescanning = false;
  this.scannedItems = [];
  
  // Reset status
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
  
  // ✅ STOP POLLING PROPERLY
  this.stopPolling();
  
  console.log("Logout successful - returned to login screen");
},
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

  // 🔁 New batch: reset completion popups & flags
  this.showSavePopup = false;
  this.showCompletionPopup = false;
  this.hasShownSavePopup = false;
  this.hasShownCompletionPopup = false;

  try {
    // <-- send payload the backend expects
    const response = await loadWorkorder({ batch_no: bn });
    

    console.log('[DEBUG] loadWorkorder response:', response);
    // ✅ Store session ID for prescan
    this.sessionId = response.session_id;
    console.log("Session ID:", this.sessionId);

    if (!this.sessionId) {
      this.scanResult = { status: 'error', message: 'Session ID not received' };
      return;
    }

    // unify error handling (old style or new style)
    if (response && (response.error || response.status === 'error')) {
      const msg = response.error || response.message || 'Failed to load batch';
      this.scanResult = { status: 'error', message: msg };
      return;
    }

    // --- Unified success handling: accept either workorder OR sequence_steps ---
    if (response && response.workorder) {
      // backend already returned a workorder shape
      this.scannedItems = [];
      this.prescanResults = {};
      this.workorder = response.workorder;
      const returnedBatch = response.batch_number || bn;
      this.selectedBatch = { batch_number: returnedBatch, name: response.workorder.name || returnedBatch };
    }
    else if (response && response.sequence_steps) {
      // backend returned sequence_steps — convert to workorder.steps
      function parseSeconds(mixingTime) {
        if (mixingTime == null) return null;
        if (typeof mixingTime === 'number') return Math.floor(mixingTime);
        const m = String(mixingTime).match(/(\d+)/);
        return m ? parseInt(m[1], 10) : null;
      }

      const steps = (response.sequence_steps || []).map((s, idx) => ({
        step_id: idx + 1,
        mix_time_sec: parseSeconds(s.mixing_time),
        items: (s.items || []).map(it => ({ item_id: String(it), name: null, required_weight: null }))
      }));

      // apply into UI state exactly like existing flow
      this.scannedItems = [];
      this.prescanResults = {};
      this.workorder = { name: response.workorder?.name || `Workorder ${response.batch_no || bn}`, steps };
      
  // ✅ CRITICAL FIX — initialize prescan status
  this.workorder.steps.forEach(step => {
    step.items.forEach(item => {
      this.prescanResults[item.item_id] = 'pending';
    });
  });
      this.selectedBatch = {
    batch_number: bn,
    name: this.workorder.name
  };
}

    else {
      // Unexpected response shape or error
      const msg = response && (response.message || response.error) ? (response.message || response.error) : 'Failed to load workorder';
      this.scanResult = { status: 'error', message: msg };
      return;
    }

    // Continue the existing UI flow after successful load
    this.showBatchSelection = false;
    this.showPrescanning = true;
    this.prescanComplete = false;

    // Save batch number to localStorage
    localStorage.setItem('lastBatchNumber', this.selectedBatch.batch_number || bn);

    // ✅ FORCE STATUS UPDATE TO GET LATEST DATA
    await this.updateStatus();

    this.$nextTick(() => {
      if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus();
    });

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
 getItemStatus(itemCode) {
  return this.prescanResults[itemCode] || 'pending';
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
//getItemStatus(itemId) {
  //if (this.status.process_state === 'PRESCANNING') {
    //if (this.status.prescan_status && this.status.prescan_status.status_by_stage) {
      //for (let stage in this.status.prescan_status.status_by_stage) {
        //const item = this.status.prescan_status.status_by_stage[stage].items.find(i => i.item_id === itemId);
        //if (item) {
          // map "scanned" → "done"
          //if (item.prescan_status.toLowerCase() === 'scanned') {
            //return 'done';
          //}
          //return item.prescan_status.toLowerCase();
        //}
      //}
    //}
    //return 'pending';
  //}

  // After prescan confirmed, everything should stay as "done"
  //if (this.status.prescan_complete || this.showPrescanCompletePopup === false) {
    //return 'done';
  //}

  //return 'pending';
//},

   
async handlePrescan() {
  if (!this.barcode.trim()) return;

  if (!this.sessionId) {
    this.scanResult = {
      status: 'error',
      message: 'Session not initialized. Please load batch first.'
    };
    return;
  }

  try {
    const result = await prescanItem(
      this.barcode.trim(),
      this.sessionId
    );

    if (result && result.status === 'success') {
      this.prescanResults[result.item_code] = 'done';
      this.scanResult = result;

      // ✅ THIS IS THE KEY FIX
      if (result.prescan_complete === true) {
        this.prescanComplete = true;
        this.prescanAwaitingConfirmation = true;
        this.showPrescanCompletePopup = true;
        return;
      }
    }
    else if (result && result.status === 'error') {
      if (result.message?.includes('already scanned')) {
        this.duplicateScanMessage = result.message;
        this.showDuplicateScanPopup = true;
        this.scanResult = null;
      } else {
        this.wrongItemMessage = result.message;
        this.showWrongItemPopup = true;
        this.scanResult = null;
      }
    }
    else {
      this.scanResult = result;
    }

    this.barcode = '';
    this.$nextTick(() => this.$refs.barcodeInput?.focus());

  } catch (error) {
    console.error('Failed to prescan item:', error);
    this.scanResult = {
      status: 'error',
      message: 'Scan failed: ' + (error.response?.data?.error || error.message)
    };
  }
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
  // UI ONLY — no backend calls here
  this.barcode = '';
  this.scanResult = {
    status: 'success',
    message: 'Pre-scanning complete! Please confirm to start mixing process.'
  };

  // ❌ DO NOT auto-call confirmPrescan
  if (this.autoTransitionTimeout) {
    clearTimeout(this.autoTransitionTimeout);
    this.autoTransitionTimeout = null;
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
    const response = await confirmPrescanAPI({ session_id: this.sessionId });
    if (response && response.status === 'success') {
      this.prescanAwaitingConfirmation = false;
      
      this.showPrescanCompletePopup = false;

      // 🔄 SWITCH MODE HERE
      this.prescanComplete = true;
      this.actualScanning = true;
      this.showPrescanning = false;

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

    // FIX: Add safety check to prevent premature completion detection
    if (newStatus.just_completed || newStatus.process_state === 'PROCESS_COMPLETE') {
      // Only show save popup if we're actually on the last step
      const isLastStep = newStatus.current_step_index >= newStatus.total_steps - 1;
      const allStepsDone = newStatus.steps && newStatus.steps.every(step => 
        step.items.every(item => item.live_status === 'DONE')
      );
      
      if (!this.hasShownSavePopup && isLastStep && allStepsDone) {
            console.log("Process complete detected -> showing SAVE popup (once per batch)");
            this.showSavePopup = true;
            this.hasShownSavePopup = true;   // 
          }
        }


  } catch (error) {
    console.error('Failed to update status:', error)
    this.status = {
      ...this.status,
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
    async handleSaveWorkorder() {
  try {
    const response = await saveWorkorder();
    if (response.status === 'success') {
      console.log('Workorder saved successfully:', response.message);
      this.scanResult = { status: 'success', message: 'Workorder saved successfully!' };
      this.showSavePopup = false;
      this.showCompletionPopup = true;
      this.hasShownCompletionPopup = true;
    } else {
      console.warn('Failed to save workorder:', response.message);
      this.scanResult = { status: 'error', message: response.message || 'Failed to save workorder' };
      // Don't proceed to completion popup if save failed
    }
  } catch (err) {
    console.error('Save workorder API failed:', err);
    this.scanResult = { status: 'error', message: 'Error saving workorder' };
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
      this.hasShownSavePopup = false
      this.hasShownCompletionPopup = false
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
