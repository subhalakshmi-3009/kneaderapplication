<template>
  <div class="dashboard">

    <!-- FIRST SCREEN: select batch type -->
    <div class="batch-panel" v-if="!batchType">
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
      <h2>Enter Batch Number for {{ batchType.toUpperCase() }}</h2>
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

    <!-- PRESCANNING PANEL -->
    <div class="prescan-panel" v-if="workorder && workorder.steps">
      <h2>{{ selectedBatch ? selectedBatch.name : workorder.name }}</h2>

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
            <!-- First row of step -->
            <tr>
              <td :rowspan="step.items.length">{{ stepIndex + 1 }}</td>
              <td>{{ step.items[0].item_id }}</td>

              <!-- Mixing Time -->
              <td :rowspan="step.items.length">
                <!-- Freeze at 0 once this step is finished OR when process is complete -->
                <span v-if="status.process_state === 'PROCESS_COMPLETE' ||
                            status.current_step_index > stepIndex ||
                            (status.current_step_index === stepIndex && status.mixing_time_remaining === 0)">
                  0s
                </span>

                <!-- Current step: show live countdown or paused time -->
                <span v-else-if="status.current_step_index === stepIndex &&
                                (status.process_state === 'MIXING' || status.process_state === 'ABORTED')">
                  {{ status.mixing_time_remaining }}s
                </span>

                <!-- Future step -->
                <span v-else>
                  {{ formatMixTime(step.mix_time_sec) }}
                </span>
              </td>

              <!-- Prescan -->
              <td>
                <span v-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'SCANNED'" style="color: green;">
                  SCANNED
                </span>
                <span v-else-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'PENDING'" >
                  PENDING
                </span>
                <span v-else-if="getItemStatus(step.items[0].item_id).toUpperCase() === 'DONE'" style="color: gray; font-weight: bold;">
                  DONE
                </span>
                <span v-else>
                  {{ getItemStatus(step.items[0].item_id).toUpperCase() }}
                </span>
              </td>

              <!-- Live Status -->
              <td>
                <!-- If this is the NEXT step and some items already scanned while mixing -->
                <span v-if="stepIndex === status.current_step_index + 1 && step.items[0].live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
                  SCANNED
                </span>
                <!-- Normal flow -->
                <span v-else-if="step.items[0].live_status === 'READY_TO_LOAD'" style="color: blue; ">
                  READY TO LOAD
                </span>
                <span v-else-if="step.items[0].live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
                  SCANNED
                </span>
                <span v-else-if="step.items[0].live_status === 'MIXING'" style="color: green; font-weight: bold;">
                  MIXING
                </span>
                <span v-else-if="step.items[0].live_status === 'DONE'" style="color: gray; font-weight: bold;">
                  DONE
                </span>
                <span v-else>
                  {{ (step.items[0].live_status || 'WAITING').toUpperCase() }}
                </span>
              </td>
            </tr>

            <!-- Remaining items -->
            <tr v-for="item in step.items.slice(1)" :key="item.item_id">
              <td>{{ item.item_id }}</td>

              <!-- Prescan -->
              <td>
                <span v-if="getItemStatus(item.item_id).toUpperCase() === 'SCANNED'" style="color: green;">
                  SCANNED
                </span>
                <span v-else-if="getItemStatus(item.item_id).toUpperCase() === 'PENDING'" >
                  PENDING
                </span>
                <span v-else-if="getItemStatus(item.item_id).toUpperCase() === 'DONE'" style="color: gray; font-weight: bold;">
                  DONE
                </span>
                <span v-else>
                  {{ getItemStatus(item.item_id).toUpperCase() }}
                </span>
              </td>

              <!-- Live Status -->
              <td>
                <!-- Allow future step items to show SCANNED while current is mixing -->
                <span v-if="stepIndex === status.current_step_index + 1 && item.live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
                  SCANNED
                </span>
                <!-- Normal flow -->
                <span v-else-if="item.live_status === 'READY_TO_LOAD'" style="color: blue; ">
                  READY TO LOAD
                </span>
                <span v-else-if="item.live_status === 'SCANNED'" style="color: orange; font-weight: bold;">
                  SCANNED
                </span>
                <span v-else-if="item.live_status === 'MIXING'" style="color: green; font-weight: bold;">
                  MIXING
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

        <!-- Abort / Resume Buttons -->
        <div class="control-buttons" style="margin-top: 1rem; text-align: center;">
          <!-- Abort button -->
          <button
            v-if="['MIXING', 'WAITING_FOR_ITEMS', 'READY_TO_LOAD'].includes(status.process_state)"
            @click="abortProcess"
            class="btn btn-danger"
          >
            Abort
          </button>

          <!-- Resume button -->
          <button
            v-if="status.process_state === 'ABORTED'"
            @click="resumeProcess"
            class="btn btn-success"
          >
            Resume
          </button>
        </div>
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
  prescanItem
} from '@/api'

export default {
  name: 'Dashboard',
  data() {
    return {
      batchType: null,  // "master" or "compound"
      showPrescanCompletePopup: false,
      showCompletionPopup: false,

      showConfirmPopup: false,
      batches: [],
      enteredBatchNumber: '',
      selectedBatch: null,
      workorder: null,
      showBatchSelection: true,
      showPrescanning: false,
      prescanResults: {}, 
      
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
    console.log('Mounted, showBatchSelection:', this.showBatchSelection);
    await this.loadBatches();
    await this.loadWorkorders();
    this.startPolling();
    this.$nextTick(() => {
      if (this.$refs.batchInput) this.$refs.batchInput.focus();
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
    prescanComplete(newVal) {
      if (newVal) {
        this.initiateAutoTransition();
      }
    }
  },
  methods: {
    selectBatchType(type) {
  this.batchType = type;       // "master" or "compound"
  this.showBatchSelection = true;
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
    
  getStatusMessage() {
    // Guard: if no steps yet, just return empty string
  if (!this.workorder || !this.workorder.steps) {
    return '';
  }
  const currentStage = this.status.current_step_index + 1;
  const nextStage = currentStage + 1;
    switch (this.status.process_state) {
      case 'IDLE': return 'Prescan';
      case 'PRESCANNING':
      return 'Prescanning in progress'
      case 'PROCESS_COMPLETE': return '✅ Process Complete!';
      case 'WAITING_FOR_ITEMS': return `Enter the item code for Stage ${currentStage}`;
      case 'MIXING':
      
      if (
        this.workorder &&
        this.status.current_step_index < this.workorder.steps.length - 1
      ) {
        return  `Mixing Stage ${currentStage}, scan Stage ${nextStage} items`;
      } else {
        return `Mixing Stage ${currentStage}`;
      }
      //case 'WAITING_FOR_LID_CLOSE': return 'Waiting for lid to close';
      case 'WAITING_FOR_MOTOR_START': return 'Waiting for motor to start';
      case 'ABORTED': return ' Process Aborted. Click Resume to continue';
      default: return '';
    }
  },


   

    // Load a batch by manual entry
    // Load a batch by manual entry
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
      this.workorder = response.workorder;
      this.selectedBatch = { batch_number: bn, name: response.workorder.name || bn };
      this.showBatchSelection = false;
      this.showPrescanning = true;
      this.prescanComplete = false;
      this.scannedItems = [];
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
          return item.prescan_status.toLowerCase();
        }
      }
    }
    return 'pending';
  }

  // After prescan is complete, freeze prescan column as "done"
  if (this.status.prescan_complete) {
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
}

        this.scanResult = result;
        this.barcode = '';
        this.$nextTick(() => { if (this.$refs.barcodeInput) this.$refs.barcodeInput.focus(); });
      } catch (error) {
        console.error('Failed to prescan item:', error);
        this.scanResult = { status: 'error', message: 'Scan failed: ' + (error.response?.data?.error || error.message) };
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
   // ⬇️ Add this log here, before calling the API
  console.log("Sending scan:", this.barcode.trim());

  try {
    // 
    const result = await scanItem(this.barcode.trim());

    if (result.error) {
      this.scanResult = { status: 'error', message: 'Scan failed: ' + result.error };
    } else {
      const stepIndex = this.status.current_step_index;
      const isMixing = this.status.process_state === 'MIXING';

      // 
      let allowedStepIndexes = isMixing ? [stepIndex + 1] : [stepIndex];

      const allowedItems = allowedStepIndexes.flatMap(
        idx => this.workorder.steps[idx]?.items.map(i => i.item_id) || []
      );

      // Check if scanned item belongs to allowed items
      if (!allowedItems.includes(this.barcode.trim())) {
        this.scanResult = { status: 'error', message: 'Invalid item for this stage' };
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
}

.prescan-table th,
.prescan-table td {
  border: 1px solid #ccc;
  padding: 8px;
  font-size: 0.95rem;
}

.prescan-table th {
  background-color: #f8f9fa;
  font-weight: bold;
}

.prescan-table td {
  background-color: #fff;
}

.prescan-table tr:nth-child(even) td {
  background-color: #fdfdfd;
}

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
  border-radius: 8px;
  text-align: center;
  max-width: 400px;
  width: 100%;
  box-shadow: 0 2px 10px rgba(0,0,0,0.3);
}


.status-line {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  text-align: center;
  background-color: #d4edda;   /* light green */
  color: #155724;              /* dark green text */
  border: 1px solid #c3e6cb;   /* green border */
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
}
::v-deep(.blinking-highlight) {
  background-color: yellow;
  animation: blinking 1s infinite;
}

@keyframes blinking {
  0% { background-color: yellow; }
  50% { background-color: transparent; }
  100% { background-color: yellow; }
}


.btn-debug { background-color:#6c757d; color:white; padding:0.25rem 0.5rem; border:none; border-radius:4px; font-size:0.8rem; margin-top:1rem; }
</style>