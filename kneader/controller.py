# controller.py
import asyncio
import json
import time
import os
import configparser
from typing import Dict, Any, Optional, Set
from Kneader2 import Kneader
from utils.AsyncJsonLogger import AsyncJsonLogger
import config
from gateway_client import AsyncGatewayClient


class KneaderController:
    def __init__(self):
        self._setup_events()
        self._load_config()
        self._initialize_logger()
        self._initialize_gateway()
        self._initialize_kneader()
        self._reset_internal_state()
        self._prescan_data = None
        self.ready_timestamps = {}

    def _setup_events(self):
        self._is_paused = asyncio.Event()
        self._confirm_start_event = asyncio.Event()
        self._is_paused.set()  # Start as not paused
        self._resume_event = asyncio.Event()

    def _load_config(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, 'config.ini')
        config_parser = configparser.ConfigParser()
        config_parser.read(config_path)

        self.config_file_path = config_parser['files']['kneader_json_log_file']
        # self.low_temp_threshold = float(config_parser['temperature_thresholds']['low'])
        # self.high_temp_threshold = float(config_parser['temperature_thresholds']['high'])

    def _initialize_logger(self):
        self.logger = AsyncJsonLogger(self.config_file_path)
        asyncio.create_task(self.logger.start())

    def _initialize_gateway(self):
        self.gateway = AsyncGatewayClient(config.GATEWAY_HOST, config.GATEWAY_PORT, logger=self.logger)
        self.gateway.event_callback = self._handle_gateway_event

    def _initialize_kneader(self):
        self.kneader = Kneader(
            kneader_id=1,
            device_ip=config.GATEWAY_HOST,
            device_id="KNEADER-1",
            logger=self.logger,
            tag_config=None,
            my_tag_configs=[],
            broadcast_callback=None
        )

    def _reset_internal_state(self):
        self.process_state = "IDLE"
        self.workorder = None
        self.current_step_index = 0
        self.current_item_index = 0
        self.error_message = ""
        self.lid_open = 0
        self.motor_running = False
        self.mixing_timer_started = False
        self.mixing_start_timestamp = None
        self.motor_start_failed_alert = False
        self.remaining_mix_time = 0
        self.work_order_task = None
        self.hmi_cmd_queue = asyncio.Queue()
        self._prescan_data = None
        # --- NEW: track scanned items per step globally to avoid local race/visibility issues
        self.scanned_items_by_step = {}
        self._just_completed = False

    def _handle_gateway_event(self, event: Dict[str, Any]):
        if "tag_name" in event and "value" in event:
            if event["tag_name"] == "rd_lid_status_kn1":
                self.lid_open = not event["value"]
            elif event["tag_name"] == "rd_motor_status_kn1":
                self.motor_running = event["value"]

        asyncio.create_task(
            self.logger.log(
                "INFO",
                f"Updated from event: lid_open={self.lid_open}, motor_running={self.motor_running}",
                data=self.get_full_status(),
                is_event=False
            )
        )

    def get_full_status(self) -> Dict[str, Any]:
        status = {
            "process_state": self.process_state,
            "workorder_id": self.workorder.get("workorder_id") if self.workorder else None,
            "workorder_name": self.workorder.get("name") if self.workorder else None,
            "steps": self.workorder.get("steps", []) if self.workorder else [],
            "current_step_index": self.current_step_index,
            "current_item_index": self.current_item_index,
            "total_steps": len(self.workorder.get("steps", [])) if self.workorder else 0,
            "lid_open": self.lid_open,
            "motor_running": self.motor_running,
            "mixing_time_total": 0,
            "mixing_time_remaining": 0,
            "lid_alert_level": "none",
            "error_message": self.error_message,
            "item_add_alert": False,
            "motor_start_failed_alert": self.motor_start_failed_alert,
            "prescan_complete": self.process_state != "PRESCANNING",
        }

        # include prescan status if in PRESCANNING
        if self.process_state == "PRESCANNING" and self._prescan_data:
            status["prescan_status"] = self._get_prescan_status(self._prescan_data)

        # Safe handling of mixing time
        if self.workorder and self.workorder.get("steps"):
            try:
                if 0 <= self.current_step_index < len(self.workorder["steps"]):
                    step_total = int(self.workorder["steps"][self.current_step_index].get("mix_time_sec", 0))
                else:
                    step_total = 0

                status["mixing_time_total"] = step_total

                if self.process_state == "PROCESS_COMPLETE":
                    status["mixing_time_remaining"] = 0

                elif self.process_state == "ABORTED":
                    rem = int(self.remaining_mix_time) if getattr(self, "remaining_mix_time",
                                                                  None) is not None else step_total
                    status["mixing_time_remaining"] = max(0, rem)

                elif self.process_state == "MIXING":
                    if getattr(self, "mixing_timer_started", False) and getattr(self, "mixing_start_timestamp", None):
                        elapsed = time.time() - self.mixing_start_timestamp
                        if getattr(self, "_resumed_from_abort", False) and getattr(self, "remaining_mix_time",
                                                                                   None) and self.remaining_mix_time < step_total:
                            baseline = int(self.remaining_mix_time)
                        else:
                            baseline = step_total
                        rem = max(0, int(baseline - elapsed))
                        status["mixing_time_remaining"] = rem
                    else:
                        baseline = getattr(self, "remaining_mix_time", None)
                        status["mixing_time_remaining"] = int(baseline if baseline is not None else step_total)

                else:
                    baseline = getattr(self, "remaining_mix_time", None)
                    if baseline is not None and baseline != 0:
                        status["mixing_time_remaining"] = int(baseline)
                    else:
                        status["mixing_time_remaining"] = step_total

            except (IndexError, KeyError, TypeError):
                status["mixing_time_total"] = 0
                status["mixing_time_remaining"] = 0

        # Inject live_status into each item
        if self.workorder and self.workorder.get("steps"):
            for s_idx, step in enumerate(status["steps"]):
                for item in step.get("items", []):
                    item_status = "WAITING"
                    scanned_set = self.scanned_items_by_step.get(s_idx, set())

                    # Step already completed
                    if self.current_step_index > s_idx or self.process_state == "PROCESS_COMPLETE":
                        item_status = "DONE"

                    # Current step
                    elif (
                            self.process_state in ("MIXING", "WAITING_FOR_LID_CLOSE", "WAITING_FOR_MOTOR_START")
                            and self.current_step_index == s_idx
                    ):
                        item_status = "MIXING"

                    # Item scanned
                    elif item["item_id"] in scanned_set:
                        if s_idx == self.current_step_index:
                            if self.process_state == "WAITING_FOR_ITEMS":
                                all_scanned = all(
                                    i["item_id"] in scanned_set
                                    for i in self.workorder["steps"][s_idx]["items"]
                                )
                                item_status = "READY_TO_LOAD" if all_scanned else "SCANNED"
                            elif self.process_state == "READY_TO_LOAD":
                                item_status = "READY_TO_LOAD"
                            elif self.process_state == "MIXING":
                                item_status = "MIXING"
                            else:
                                item_status = "SCANNED"

                        elif s_idx == self.current_step_index + 1:
                            # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ Show SCANNED immediately while previous step is mixing
                            if self.process_state == "MIXING":
                                item_status = "SCANNED"
                            else:
                                item_status = "SCANNED"

                        else:
                            item_status = "SCANNED"

                    else:
                        # Next step but not scanned yet
                        if s_idx == self.current_step_index + 1 and self.process_state == "MIXING":
                            item_status = "WAITING"
                        else:
                            item_status = "WAITING"

                    item["live_status"] = item_status

        return status

    def _get_prescan_status(self, prescan_data: Dict[str, Any]) -> Dict[str, Any]:
        status_by_stage = {}

        for item_id, item_info in prescan_data['all_items'].items():
            stage_num = item_info['stage']
            if stage_num not in status_by_stage:
                status_by_stage[stage_num] = {
                    'items': [],
                    'mix_time': self.workorder['steps'][stage_num - 1]['mix_time_sec'] if self.workorder else 0,
                    'live_status': 'WAITING'
                }

            status_by_stage[stage_num]['items'].append({
                'item_id': item_id,
                'name': item_info['name'],
                # 'prescan_status': item_info.get('prescan_status', 'PENDING'),
                'prescan_status': item_info['status'],

                'status': 'WAITING'

            })

        return {
            'total_items': len(prescan_data['all_items']),
            'scanned_count': len(prescan_data['scanned_items']),
            'missing_count': len(prescan_data['missing_items']),
            'status_by_stage': status_by_stage,
            'all_scanned': len(prescan_data['missing_items']) == 0
        }

    async def _ensure_gateway_connection(self):
        """Ensure the gateway is connected before sending commands"""
        if not self.gateway.is_connected:
            await self.logger.log("WARNING", "Gateway not connected, attempting to reconnect",
                                  data=self.get_full_status(), is_event=True)
            try:
                await self.gateway.connect()
                if self.gateway.is_connected:
                    await self.logger.log("INFO", "Gateway reconnected successfully",
                                          data=self.get_full_status(), is_event=True)
                else:
                    raise ConnectionError("Failed to connect to gateway")
            except Exception as e:
                await self.logger.log("ERROR", f"Failed to reconnect to gateway: {e}",
                                      data=self.get_full_status(), is_event=True)
                raise

    async def _process_workorder_step(self, step: Dict[str, Any], step_index: int):
        self.current_step_index = step_index
        self.current_item_index = 0
        await self.logger.log("INFO", f"Starting Step {step_index + 1}", data=self.get_full_status(), is_event=False)

        num_items_to_scan = len(step.get("items", []))
        if num_items_to_scan == 0:
            await self.logger.log("WARNING", f"Step {step_index + 1} has no items, skipping.",
                                  data=self.get_full_status(), is_event=True)
            return True

        scanned_item_ids = self.scanned_items_by_step.setdefault(step_index, set())

        # ✅ If all items for this step were already early scanned → skip waiting, go READY_TO_LOAD
        if len(scanned_item_ids) == num_items_to_scan:
            self.process_state = "READY_TO_LOAD"
            await self.logger.log(
                "INFO",
                f"Step {step_index + 1} already fully scanned (early). Transitioning to READY_TO_LOAD.",
                data=self.get_full_status(),
                is_event=True
            )
            await asyncio.sleep(10)  # same 10s grace period before mixing
            return await self._execute_mixing_process(step_index)

        # Normal path: still waiting for items
        self.process_state = "WAITING_FOR_ITEMS"
        await self.logger.log(
            "INFO",
            f"Ready to accept scans for Step {step_index + 1}",
            data=self.get_full_status(),
            is_event=True
        )

        if len(scanned_item_ids) > 0:
            # Invalid state safety check
            self.process_state = "ERROR"
            self.error_message = "Invalid state: entered WAITING_FOR_ITEMS with pre-scanned items (partial)"
            await self.logger.log("ERROR", self.error_message, data=self.get_full_status(), is_event=True)
            return False

        # Process item scanning for this step
        while len(scanned_item_ids) < num_items_to_scan:
            cmd, future = await self.hmi_cmd_queue.get()
            if cmd["command"] == "scan_item":
                await self._process_scan_item(cmd, future, step, scanned_item_ids)
            else:
                if future:
                    future.set_result(self.get_full_status())

        await self.logger.log("INFO", f"All items scanned for Step {step_index + 1}, moving to lid close",
                              data=self.get_full_status(), is_event=True)
        self.process_state = "READY_TO_LOAD"
        await self.logger.log("INFO", f"All items scanned for Step {step_index + 1}, now READY_TO_LOAD",
                              data=self.get_full_status(), is_event=True)

        await asyncio.sleep(10)
        return await self._execute_mixing_process(step_index)

    async def _process_scan_item(self, cmd, future, step, scanned_item_ids):
        # Extract barcode safely
        raw_data = cmd.get("data") or {}
        barcode = (raw_data.get("barcode") or "").strip()

        # Always log raw input
        await self.logger.log(
            "DEBUG",
            f"Raw scan data received: {raw_data}",
            data=self.get_full_status(),
            is_event=False
        )

        if not barcode:
            resp = {"status": "fail", "message": f"Cannot scan {barcode or None} in state {self.process_state}"}
            if future:
                future.set_result(resp)
            return

        # Log accepted scan request
        await self.logger.log(
            "DEBUG",
            f"Scan request received during {self.process_state} for barcode={barcode}",
            data=self.get_full_status(),
            is_event=False
        )

        # Build valid items for current step
        valid_items = {item["item_id"]: item for item in step.get("items", [])}

        # Also include next step items if MIXING (allow early scanning)
        next_step_index = self.current_step_index + 1
        next_step_items_map = {}
        if (
                self.process_state == "MIXING"
                and self.workorder
                and next_step_index < len(self.workorder.get("steps", []))
        ):
            next_step = self.workorder["steps"][next_step_index]
            next_step_items_map = {item["item_id"]: item for item in next_step.get("items", [])}
            # Merge next-step items into valid set
            valid_items.update({k: v for k, v in next_step_items_map.items() if k not in valid_items})

        if barcode in valid_items:
            # Figure out which step this belongs to
            target_step_index = self.current_step_index
            if barcode in next_step_items_map:
                target_step_index = next_step_index

            scanned_set = self.scanned_items_by_step.setdefault(target_step_index, set())

            if barcode not in scanned_set:
                scanned_set.add(barcode)

                if target_step_index == self.current_step_index:
                    # Normal scan for current step
                    scanned_item_ids.add(barcode)
                    self.current_item_index = len(scanned_item_ids) - 1
                    msg = f"Item {valid_items[barcode].get('name', barcode)} scanned for current step."
                else:
                    # Early scan for next step (only mark SCANNED, don’t advance)
                    if target_step_index not in self.ready_timestamps:
                        self.ready_timestamps[target_step_index] = time.time()
                    msg = f"Item {valid_items[barcode].get('name', barcode)} scanned early for next step."

                scan_response = {
                    "status": "success",
                    "message": msg,
                    "item_id": barcode,
                    "step_index": target_step_index,
                }
                await self.logger.log("INFO", msg, data=self.get_full_status(), is_event=False)
            else:
                scan_response = {"status": "fail", "message": "Item already scanned."}
                await self.logger.log(
                    "WARNING", f"Duplicate scan attempt: {barcode}",
                    data=self.get_full_status(), is_event=False
                )
        else:
            scan_response = {
                "status": "fail",
                "message": f"Scanned item {barcode} does not belong to this or next step."
            }
            await self.logger.log(
                "WARNING",
                f"Invalid scan for this step: {barcode}",
                data=self.get_full_status(),
                is_event=False
            )

        if future:
            future.set_result(scan_response)

    async def _execute_mixing_process(self, step_index: int) -> bool:
        lid_timeout = getattr(config, 'LID_CLOSE_TIMEOUT_SEC', 30.0)

        try:
            await self._ensure_gateway_connection()
            self.process_state = "WAITING_FOR_LID_CLOSE"
            await self.logger.log("INFO", "Closing lid for mixing", data=self.get_full_status(), is_event=True)

            # ... (lid close + motor start code unchanged) ...

            # Start mixing
            self.process_state = "MIXING"
            self.mixing_timer_started = True

            step_total = int(self.workorder["steps"][step_index]["mix_time_sec"])
            if getattr(self, "remaining_mix_time", None) and 0 < self.remaining_mix_time < step_total:
                mix_duration = self.remaining_mix_time
            else:
                mix_duration = step_total
                self.remaining_mix_time = step_total
                self.mixing_start_timestamp = time.time()
                self._resumed_from_abort = False

            await self.logger.log("INFO", f"Mixing started for {mix_duration} seconds",
                                  data=self.get_full_status(), is_event=True)

            # Mixing countdown loop
            mix_end_time = self.mixing_start_timestamp + mix_duration
            last_progress_log = time.time()

            while time.time() < mix_end_time:
                if self.process_state == "ABORTED":
                    remaining = int(mix_end_time - time.time())
                    self.remaining_mix_time = remaining if remaining > 0 else 0
                    self.mixing_timer_started = False
                    self.motor_running = False
                    self._resumed_from_abort = False
                    await self.logger.log("INFO", "Mixing aborted mid-step. Freezing state.",
                                          data=self.get_full_status(), is_event=True)
                    return False

                await self._is_paused.wait()

                current_time = time.time()
                if current_time - last_progress_log >= 1:
                    remaining = int(mix_end_time - current_time)
                    self.remaining_mix_time = remaining if remaining > 0 else 0
                    await self.logger.log("INFO", f"Mixing in progress... {remaining} seconds remaining",
                                          data=self.get_full_status(), is_event=False)
                    last_progress_log = current_time

                await asyncio.sleep(0.2)

            # === Step completed ===
            self.mixing_timer_started = False
            self.remaining_mix_time = 0
            await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
            await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})
            self.motor_running = False

            lid_open_start = time.time()
            while not self.lid_open:
                if time.time() - lid_open_start > lid_timeout:
                    await self.logger.log("WARNING", "Lid failed to open within timeout, but continuing",
                                          data=self.get_full_status(), is_event=True)
                    break
                await asyncio.sleep(0.2)

            # ✅ Mark only THIS step’s items as DONE
            for item in self.workorder["steps"][step_index]["items"]:
                item["live_status"] = "DONE"

            # ✅ Advance to next step or complete
            if self.current_step_index < len(self.workorder["steps"]) - 1:
                self.current_step_index += 1
                next_step = self.workorder["steps"][self.current_step_index]
                scanned_set = self.scanned_items_by_step.get(self.current_step_index, set())
                all_scanned = all(i["item_id"] in scanned_set for i in next_step["items"])

                if all_scanned:
                    self.process_state = "READY_TO_LOAD"
                    await self.logger.log(
                        "INFO",
                        f"Step {step_index + 1} mixing done. Next step already scanned → READY_TO_LOAD",
                        data=self.get_full_status(),
                        is_event=True
                    )
                else:
                    self.process_state = "WAITING_FOR_ITEMS"
                    await self.logger.log(
                        "INFO",
                        f"Step {step_index + 1} mixing done. Waiting for items of next step",
                        data=self.get_full_status(),
                        is_event=True
                    )
            else:
                self.process_state = "PROCESS_COMPLETE"
                await self.logger.log("INFO", f"Mixing for final step {step_index + 1} completed, process complete",
                                      data=self.get_full_status(), is_event=True)

            self._resumed_from_abort = False
            return True

        except Exception as e:
            await self.logger.log("ERROR", f"Error in mixing process: {e}", data=self.get_full_status(), is_event=True)
            try:
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})
            except:
                pass
            raise

    async def _process_workorder(self, initial_barcode: Optional[str] = None):
        try:
            await self.logger.log("INFO", f"Starting workorder: {self.workorder.get('name')}",
                                  data=self.get_full_status(), is_event=False)

            # Reset prescan data as we're starting actual processing
            self._prescan_data = None
            self.process_state = "WAITING_FOR_ITEMS"

            await self.logger.log("INFO", "Starting actual process now.",
                                  data=self.get_full_status(), is_event=True)

            # Process each step in the workorder
            for i, step in enumerate(self.workorder["steps"]):
                success = await self._process_workorder_step(step, i)
                if not success:
                    break




            # If process was aborted, do not mark complete
            if self.process_state == "ABORTED":
                await self.logger.log("INFO", "Workorder aborted mid-process. Waiting for operator to resume.",
                                      data=self.get_full_status(), is_event=True)
                return

            # If we reach here, it means all steps really finished
            self.remaining_mix_time = 0
            self.process_state = "PROCESS_COMPLETE"
            self._just_completed = True
            await self.logger.log("INFO", "Work order has finished successfully.",
                                  data=self.get_full_status(), is_event=False)


        except asyncio.CancelledError:
            await self.logger.log("WARNING", "Work order processing was cancelled",
                                  data=self.get_full_status(), is_event=True)
            raise
        except Exception as e:
            await self.logger.log("ERROR", f"Work order processing failed: {e}",
                                  data=self.get_full_status(), is_event=True)
            self.process_state = "ERROR"
            self.error_message = str(e)
            raise

    async def _monitor_hardware_status(self):
        last_aborted_log = 0
        while True:
            try:
                if not self.gateway.is_connected:
                    await self.gateway.connect()

                if self.gateway.is_connected:
                    # Read lid status
                    res_lid = await self.gateway.send_command({"action": "read", "tag_name": "rd_lid_status_kn1"})
                    if res_lid and "value" in res_lid:
                        self.lid_open = res_lid["value"] is False

                    # Read motor status
                    res_motor = await self.gateway.send_command({"action": "read", "tag_name": "rd_motor_status_kn1"})
                    if res_motor and "value" in res_motor:
                        self.motor_running = res_motor["value"]

                    # Log aborted state periodically
                    if self.process_state == "ABORTED":
                        now = time.time()
                        if now - last_aborted_log >= 2:
                            await self.logger.log("INFO",
                                                  "Workorder is paused (ABORTED state) - waiting for operator action",
                                                  data=self.get_full_status(), is_event=False)
                            last_aborted_log = now

                # Monitor temperature
                """await self._monitor_temperature()"""

            except Exception as e:
                await self.logger.log("ERROR", f"Error in hardware monitor: {e}", data=self.get_full_status(),
                                      is_event=True)

            await asyncio.sleep(1)

    async def _handle_abort_command(self):
        if self.process_state in ("MIXING", "WAITING_FOR_ITEMS"):
            try:
                # Always stop motor and open lid (safe for both states)
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})

                if self.process_state == "MIXING":
                    # Calculate remaining mixing time only if mixing was active
                    if self.mixing_timer_started and self.mixing_start_timestamp:
                        elapsed_time = time.time() - self.mixing_start_timestamp
                        total_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
                        self.remaining_mix_time = max(0, total_mix_time - elapsed_time)

                    # Update state for mixing abort
                    self._is_paused.clear()
                    self.mixing_timer_started = False
                    self.process_state = "ABORTED"
                    self.error_message = "Workorder paused during mixing by operator."

                    await self.logger.log("INFO", "Workorder paused - motor stopped, lid opened, timer paused",
                                          data=self.get_full_status(), is_event=True)

                elif self.process_state == "WAITING_FOR_ITEMS":
                    # No timer involved, just mark aborted
                    self._is_paused.clear()
                    self.mixing_timer_started = False
                    self.remaining_mix_time = 0
                    self.process_state = "ABORTED"
                    self.error_message = "Workorder paused while waiting for items."

                    await self.logger.log("INFO",
                                          "Workorder paused while waiting for items - motor stopped, lid opened",
                                          data=self.get_full_status(), is_event=True)

                return self.get_full_status()

            except Exception as e:
                await self.logger.log("ERROR", f"Failed to pause workorder: {e}", data=self.get_full_status(),
                                      is_event=True)
                self.process_state = "ERROR"
                self.error_message = f"Failed to pause: {str(e)}"
                return self.get_full_status()
        else:
            await self.logger.log("WARNING", f"Abort requested in unsupported state: {self.process_state}",
                                  data=self.get_full_status(), is_event=True)
            return self.get_full_status()

    async def _handle_resume_command(self):
        if self.process_state == "ABORTED":
            try:
                # Case 1: Resume from WAITING_FOR_ITEMS
                if self.remaining_mix_time == 0 and not self.mixing_timer_started:
                    # Just go back to waiting for items
                    self.process_state = "WAITING_FOR_ITEMS"
                    self.error_message = ""
                    self._is_paused.set()
                    self._resume_event.set()

                    await self.logger.log("INFO", "Process resumed successfully from ABORTED state (waiting for items)",
                                          data=self.get_full_status(), is_event=True)
                    return self.get_full_status()

                # Case 2: Resume from MIXING
                # Close lid
                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 1})

                # Wait for lid to close
                lid_timeout = getattr(config, 'LID_CLOSE_TIMEOUT_SEC', 30.0)
                lid_close_start = time.time()
                while self.lid_open:
                    if time.time() - lid_close_start > lid_timeout:
                        raise ValueError("Lid failed to close within timeout")
                    await asyncio.sleep(0.5)

                # Start motor
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 1})

                # Wait for motor to start
                motor_timeout = getattr(config, 'MOTOR_START_TIMEOUT_SEC', 15.0)
                motor_start_ts = time.time()
                while not self.motor_running:
                    if time.time() - motor_start_ts > motor_timeout:
                        self.motor_start_failed_alert = True
                        raise ValueError("Motor failed to start")
                    await asyncio.sleep(0.5)

                # Update state and resume mixing
                self.process_state = "MIXING"
                self.error_message = ""

                # Recalculate start timestamp to account for pause
                total_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
                elapsed_before_pause = total_mix_time - self.remaining_mix_time
                self.mixing_start_timestamp = time.time() - elapsed_before_pause
                self.mixing_timer_started = True

                self._is_paused.set()
                self._resume_event.set()

                await self.logger.log("INFO", "Process resumed successfully from ABORTED state (mixing)",
                                      data=self.get_full_status(), is_event=True)
                return self.get_full_status()

            except Exception as e:
                await self.logger.log("ERROR", f"Resume failed: {e}", data=self.get_full_status(), is_event=True)
                self.process_state = "ERROR"
                self.error_message = f"Resume failed: {str(e)}"
                return {"status": "fail", "message": f"Resume failed: {str(e)}"}
        else:
            return {"status": "fail", "message": "Cannot resume - not in ABORTED state"}

    async def _handle_prescan_item(self, message):
        if self.process_state in ("PRESCANNING", "PRESCAN_COMPLETE"):
            future = asyncio.get_running_loop().create_future()
            mock_cmd = {"command": "prescan_item", "data": message.get("data", {})}
            asyncio.create_task(self._process_prescan_item(mock_cmd, future))
            return await asyncio.wait_for(future, timeout=15.0)
        else:
            return {"status": "fail", "message": f"Prescan not allowed in state {self.process_state}"}

    async def _process_prescan_item(self, cmd, future):
        barcode = cmd["data"].get("barcode", "").strip()

        if not self._prescan_data:
            if future:
                future.set_result({"status": "error", "message": "Prescan data not initialized"})
            return

        if barcode in self._prescan_data['all_items']:
            if barcode not in self._prescan_data['scanned_items']:
                self._prescan_data['scanned_items'].add(barcode)
                self._prescan_data['all_items'][barcode]['status'] = 'SCANNED'

                response = {
                    "status": "success",
                    "message": f"Item {self._prescan_data['all_items'][barcode]['name']} prescanned",
                    "prescan_status": self._get_prescan_status(self._prescan_data)
                }
                await self.logger.log("INFO", f"Item prescanned: {barcode}", data=response, is_event=False)
                # Check if all items are scanned and automatically transition
                prescan_status = self._get_prescan_status(self._prescan_data)
                if prescan_status.get('all_scanned'):
                    # self.process_state = "PRESCAN_COMPLETE"
                    await self.logger.log("INFO",
                                          "All prescan items scanned ",
                                          data=self.get_full_status(), is_event=True)

            else:
                response = {
                    "status": "fail",
                    "message": "Item already prescanned",
                    "prescan_status": self._get_prescan_status(self._prescan_data)
                }
                await self.logger.log("WARNING", f"Duplicate scan: {barcode}", data=response, is_event=False)
        else:
            response = {
                "status": "error",
                "message": "Item does not belong to this workorder",
                "prescan_status": self._get_prescan_status(self._prescan_data)
            }
            await self.logger.log("WARNING", f"Invalid item: {barcode}", data=response, is_event=False)

        if future:
            future.set_result(response)

    async def hmi_client_handler(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                message = json.loads(data.decode())
                command = message.get("command")
                response = None

                # Handle different commands
                if command == "abort":
                    response = await self._handle_abort_command()
                elif command == "resume":
                    response = await self._handle_resume_command()
                elif command in ("reset", "reset_controller"):
                    if self.work_order_task and not self.work_order_task.done():
                        self.work_order_task.cancel()
                    self._reset_internal_state()
                    response = self.get_full_status()
                elif command == "confirm_start":
                    response = await self._handle_confirm_start_command()
                elif command == "load_workorder":
                    response = await self._handle_load_workorder_command(message)
                elif command == "prescan_item":
                    response = await self._handle_prescan_item(message)
                elif command == "scan_item":
                    print(f"got the scan with msg {message}")
                    response = await self._handle_scan_item_command(message)

                elif command == "get_status":
                    response = self.get_full_status()
                elif command == "confirm_completion":
                    self._reset_internal_state()
                    response = self.get_full_status()

                elif command == "write":
                    response = await self._handle_write_command(message)
                else:
                    response = await self._handle_other_command(message)

                # Send response
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except Exception:
            await self.logger.log("WARNING", f"HMI client {peer} disconnected.", data={}, is_event=True)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_confirm_start_command(self):
        if self.process_state in ("PRESCANNING", "PRESCAN_COMPLETE"):
            if self.work_order_task and not self.work_order_task.done():
                return {"status": "fail", "message": "Workorder already running"}
            else:
                # Directly start workorder here
                self.work_order_task = asyncio.create_task(self._process_workorder())
                return {"status": "success", "message": "Prescan confirmed. Starting actual process."}
        else:
            return {"status": "fail", "message": f"Confirm not allowed in state {self.process_state}"}

    async def _handle_load_workorder_command(self, message):
        self.workorder = message["data"]
        self.process_state = "PRESCANNING"

        # Initialize prescan data structure
        self._prescan_data = {
            'all_items': {},
            'scanned_items': set(),
            'missing_items': set()
        }

        # Populate all_items from all steps
        for stage_idx, stage in enumerate(self.workorder['steps'], 1):
            for item in stage['items']:
                self._prescan_data['all_items'][item['item_id']] = {
                    'name': item['name'],
                    'stage': stage_idx,
                    'status': 'PENDING'
                }

        return self.get_full_status()

    async def _handle_scan_item_command(self, message):
        await self.logger.log(
            "DEBUG",
            f"_handle_scan_item_command received message={message}, workorder={self.workorder and self.workorder.get('workorder_id')}",
            data=self.get_full_status(),
            is_event=False
        )

        # 🔧 Accept both direct "item_id" and nested "data.barcode"
        item_id = (
                message.get("item_id")
                or (message.get("data", {}) or {}).get("barcode")
        )

        if not item_id:
            return {"status": "fail", "message": "No item_id/barcode provided."}

        if not self.workorder or not self.workorder.get("steps"):
            return {"status": "fail", "message": "No workorder active."}

        # Current + next step
        current_step = self.current_step_index
        next_step = current_step + 1

        # Allowed cases
        allowed = False
        target_step = None
        if self.process_state == "WAITING_FOR_ITEMS":
            allowed = True
            target_step = self.workorder["steps"][current_step]
        elif self.process_state == "MIXING" and next_step < len(self.workorder["steps"]):
            step_items = {i["item_id"] for i in self.workorder["steps"][next_step]["items"]}
            if item_id in step_items:
                allowed = True
                target_step = self.workorder["steps"][next_step]

        print(f"scanning allowed status {allowed}")
        if not allowed or not target_step:
            return {"status": "fail", "message": f"Cannot scan {item_id} in state {self.process_state}"}

        # Debug log to confirm
        await self.logger.log(
            "DEBUG",
            f"_handle_scan_item_command accepted item_id={item_id}, state={self.process_state}",
            data=self.get_full_status(),
            is_event=False
        )

        # Case 1: Current step → push into queue (normal flow)
        if self.process_state == "WAITING_FOR_ITEMS":
            future = asyncio.get_running_loop().create_future()
            print("adding message to the queue (current step)")
            await self.hmi_cmd_queue.put((message, future))
            try:
                return await asyncio.wait_for(future, timeout=15.0)
            except asyncio.TimeoutError:
                return {"status": "fail", "message": "Timeout while waiting for scan processing"}

        # Case 2: Next step while MIXING → process immediately
        elif self.process_state == "MIXING":
            future = asyncio.get_running_loop().create_future()
            scanned_item_ids = self.scanned_items_by_step.setdefault(next_step, set())
            await self._process_scan_item(message, future, target_step, scanned_item_ids)
            try:
                return await asyncio.wait_for(future, timeout=5.0)
            except asyncio.TimeoutError:
                return {"status": "fail", "message": "Timeout while processing early scan"}

    async def _handle_write_command(self, message):
        try:
            response = await self.gateway.send_command({
                "action": "write",
                "tag_name": message.get("tag_name"),
                "value": message.get("value")
            })
            return response
        except Exception as e:
            return {"error": f"Write command failed: {e}"}

    async def _handle_other_command(self, message):
        future = asyncio.get_running_loop().create_future()
        await self.hmi_cmd_queue.put((message, future))
        return await asyncio.wait_for(future, timeout=15.0)

    async def run(self):
        server = await asyncio.start_server(self.hmi_client_handler, config.HMI_HOST, config.HMI_PORT)
        asyncio.create_task(self._monitor_hardware_status())
        await self.logger.log("INFO", f"HMI Server listening on {config.HMI_HOST}:{config.HMI_PORT}", data={},
                              is_event=False)

        while True:
            await self.logger.log("INFO", "Controller is IDLE, waiting for a workorder command...",
                                  data=self.get_full_status(), is_event=False)
            cmd, future = await self.hmi_cmd_queue.get()

            if cmd["command"] == "load_and_start_workorder":
                if self.work_order_task and not self.work_order_task.done():
                    if future:
                        future.set_result({"status": "fail", "message": "A workorder is already active."})
                else:
                    self.workorder = cmd["data"] if cmd.get("data") else self.workorder
                    initial_barcode = cmd.get("barcode")
                    self.work_order_task = asyncio.create_task(self._process_workorder(initial_barcode))

                    if future:
                        future.set_result(self.get_full_status())

                    try:
                        await self.work_order_task
                    except asyncio.CancelledError:
                        await self.logger.log("WARNING", "Work order task was cancelled.", data=self.get_full_status(),
                                              is_event=True)
                    except Exception as e:
                        await self.logger.log("ERROR", f"Work order task failed with an unexpected error: {e}",
                                              data=self.get_full_status(), is_event=True)
                        self.process_state = "ERROR"
                        self.error_message = str(e)
                    finally:
                        await self._cleanup_after_workorder()
            else:
                if future:
                    future.set_result({"status": "fail", "message": "No workorder active-run."})

    async def _cleanup_after_workorder(self):
        await self.logger.log("INFO", "Work order task has ended. Performing cleanup.", data=self.get_full_status(),
                              is_event=False)

        if self.process_state == "PROCESS_COMPLETE":
            # ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ Do NOT reset here ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â wait for frontend to confirm
            await self.logger.log("INFO", "Workorder reached PROCESS_COMPLETE. Awaiting user confirmation.",
                                  data=self.get_full_status(), is_event=True)
            return


        elif self.process_state == "ERROR":
            await self.logger.log("ERROR", f"Workorder ended in ERROR state: {self.error_message}",
                                  data=self.get_full_status(), is_event=True)

        # Ensure motor stopped on cleanup
        await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})