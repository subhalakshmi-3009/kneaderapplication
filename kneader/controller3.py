# controller.py
import asyncio
import json
import time
from typing import Dict, Any, Optional
from Kneader2 import Kneader
import os
import configparser

from utils.AsyncJsonLogger import AsyncJsonLogger

import config
from gateway_client import AsyncGatewayClient


class KneaderController:

    def __init__(self):
        self._is_paused = asyncio.Event()
        self._confirm_start_event = asyncio.Event()
        self._is_paused.set()  # Start as not paused
        self._resume_event = asyncio.Event()

        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        config_path = os.path.join(current_dir, 'config.ini')

        config_parser = configparser.ConfigParser()
        config_parser.read(config_path)
        config_file_path = config_parser['files']['kneader_json_log_file']

        #threshold
        self.low_temp_threshold = config_parser['temperature_thresholds']['low']
        self.high_temp_threshold = config_parser['temperature_thresholds']['high']

        #Initialize logger
        self.logger = AsyncJsonLogger(config_file_path)
        asyncio.create_task(self.logger.start())

        # Initialize gateway
        self.gateway = AsyncGatewayClient(config.GATEWAY_HOST, config.GATEWAY_PORT, logger=self.logger)
        self.gateway.event_callback = self._handle_gateway_event
        self.remaining_mix_time = 0
        self.kneader = Kneader(
            kneader_id=1,
            device_ip=config.GATEWAY_HOST,
            device_id="KNEADER-1",
            logger=self.logger,
            tag_config=None,
            my_tag_configs=[],
            broadcast_callback=None
        )

        # internal state
        self.process_state = "IDLE"
        self.workorder: Optional[Dict[str, Any]] = None
        self.current_step_index = 0
        self.current_item_index = 0
        self.timer_start: Optional[float] = None

        # runtime values
        self.lid_open = True
        self.motor_running = False
        self.error_message = ""
        self.mixing_timer_started = False
        self.mixing_start_timestamp = None
        self.motor_start_failed_alert = False

        self.work_order_task: Optional[asyncio.Task] = None
        self.hmi_cmd_queue: asyncio.Queue = asyncio.Queue()
        self._prescan_data = None

    def _handle_gateway_event(self, event: Dict[str, Any]):
        if "tag_name" in event and "value" in event:
            if event["tag_name"] == "rd_lid_status_kn1":
                self.lid_open = event["value"] is False
            elif event["tag_name"] == "rd_motor_status_kn1":
                self.motor_running = event["value"]

        # status log
        asyncio.create_task(
            self.logger.log(
                "INFO",
                f"Updated from event: lid_open={self.lid_open}, motor_running={self.motor_running}",
                data=self.get_full_status(),
                is_event=False
            )
        )

    def _reset_internal_state(self):
        self.workorder = None
        self.process_state = "IDLE"
        self.current_step_index = -1
        self.current_item_index = -1
        self.error_message = ""
        self.lid_open = True
        self.motor_running = False
        self.mixing_timer_started = False
        self.mixing_start_timestamp = None
        self.motor_start_failed_alert = False

        while not self.hmi_cmd_queue.empty():
            try:
                self.hmi_cmd_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # status log
        asyncio.create_task(
            self.logger.log(
                "INFO",
                "Controller state and command queue have been reset to IDLE.",
                data=self.get_full_status(),
                is_event=False
            )
        )

    def get_full_status(self) -> Dict[str, Any]:
        status = {
            "process_state": self.process_state,
            "workorder_id": self.workorder["workorder_id"] if self.workorder else None,
            "workorder_name": self.workorder["name"] if self.workorder else None,
            "steps": self.workorder["steps"] if self.workorder else [],
            "current_step_index": self.current_step_index,
            "current_item_index": self.current_item_index,
            "total_steps": len(self.workorder["steps"]) if self.workorder else 0,
            "lid_open": self.lid_open,
            "motor_running": self.motor_running,
            "mixing_time_total": 0,
            "mixing_time_remaining": 0,
            "lid_alert_level": "none",
            "error_message": self.error_message,
            "item_add_alert": False,
            "motor_start_failed_alert": self.motor_start_failed_alert,
            # show prescan completion flag
            "prescan_complete": self.process_state != "PRESCANNING",
        }

        # Calculate mixing time for MIXING state
        if self.process_state == "PRESCANNING" and hasattr(self, '_prescan_data'):
            status["prescan_status"] = self._get_prescan_status(self._prescan_data)
        if self.process_state == "MIXING" and self.mixing_timer_started:
            mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
            elapsed = time.time() - self.mixing_start_timestamp
            status["mixing_time_total"] = mix_time
            status["mixing_time_remaining"] = max(0, int(mix_time - elapsed))

        # Show remaining time for ABORTED state
        elif self.process_state == "ABORTED" and hasattr(self, 'remaining_mix_time'):
            current_step_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"] if self.workorder else 0
            status["mixing_time_total"] = current_step_mix_time
            status["mixing_time_remaining"] = int(self.remaining_mix_time)

        return status

    async def pre_scanning(self, workorder_data: Dict[str, Any]):
        """
        NOTE: This function remains for compatibility if you ever call prescanning internally.
        Current recommended flow is: load_workorder -> prescan via prescan_item messages -> confirm_start -> load_and_start_workorder
        """
        prescan_data = {
            'all_items': {},
            'scanned_items': set(),
            'missing_items': set()
        }

        # Populate all_items from all steps
        for stage_idx, stage in enumerate(workorder_data['steps'], 1):
            for item in stage['items']:
                prescan_data['all_items'][item['item_id']] = {
                    'name': item['name'],
                    'stage': stage_idx,
                    'status': 'PENDING'
                }

        total_items = len(prescan_data['all_items'])
        await self.logger.log("INFO", f"Prescanning started for {total_items} items",
                              data=self._get_prescan_status(prescan_data), is_event=True)

        # First pass: scan all items
        while len(prescan_data['scanned_items']) < total_items:
            cmd, future = await self.hmi_cmd_queue.get()

            if cmd["command"] == "prescan_item":
                barcode = cmd["data"].get("barcode", "").strip()

                if barcode in prescan_data['all_items']:
                    if barcode not in prescan_data['scanned_items']:
                        prescan_data['scanned_items'].add(barcode)
                        prescan_data['all_items'][barcode]['status'] = 'DONE'

                        response = {
                            "status": "success",
                            "message": f"Item {prescan_data['all_items'][barcode]['name']} prescanned",
                            "prescan_status": self._get_prescan_status(prescan_data)
                        }
                        await self.logger.log("INFO", f"Item prescanned: {barcode}",
                                              data=response, is_event=False)
                    else:
                        response = {
                            "status": "fail",
                            "message": "Item already prescanned",
                            "prescan_status": self._get_prescan_status(prescan_data)
                        }
                        await self.logger.log("WARNING", f"Duplicate scan: {barcode}",
                                              data=response, is_event=False)
                else:
                    response = {
                        "status": "error",
                        "message": "Item does not belong to this workorder",
                        "prescan_status": self._get_prescan_status(prescan_data)
                    }
                    await self.logger.log("WARNING", f"Invalid item: {barcode}",
                                          data=response, is_event=False)

                if future:
                    future.set_result(response)
            else:
                if future:
                    future.set_result({"status": "fail", "message": "Only scan commands allowed during prescan"})

        # After first pass, all items are scanned
        await self.logger.log("INFO", "Prescanning completed successfully - all items available",
                              data=self._get_prescan_status(prescan_data), is_event=True)
        return True

    def _get_prescan_status(self, prescan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get formatted prescan status for UI display"""
        status_by_stage = {}

        for item_id, item_info in prescan_data['all_items'].items():
            stage_num = item_info['stage']
            if stage_num not in status_by_stage:
                status_by_stage[stage_num] = {
                    'items': [],
                    'mix_time': self.workorder['steps'][stage_num-1]['mix_time_sec'] if self.workorder else 0,
                    'live_status': 'WAITING'
                }

            status_by_stage[stage_num]['items'].append({
                'item_id': item_id,
                'name': item_info['name'],
                'status': item_info['status']
            })

        return {
            'total_items': len(prescan_data['all_items']),
            'scanned_count': len(prescan_data['scanned_items']),
            'missing_count': len(prescan_data['missing_items']),
            'status_by_stage': status_by_stage,
            'all_scanned': len(prescan_data['missing_items']) == 0
        }

    async def _process_workorder(self, initial_barcode: Optional[str] = None):
        """
        Main process loop: assumes prescanning was completed and confirmation was handled externally.
        """
        try:
            # status log
            await self.logger.log("INFO",
                                  f"Starting workorder: {self.workorder.get('name')}, initial_barcode: {initial_barcode}",
                                  data=self.get_full_status(), is_event=False)

            # Ensure prescan was completed before starting
            if not hasattr(self, '_prescan_data') or not self._prescan_data:
                # If prescan info not present, we still allow if workorder has no items (edge case),
                # otherwise mark error
                await self.logger.log("WARNING", "Prescan data missing - proceeding if steps have zero items",
                                      data=self.get_full_status(), is_event=True)
            else:
                status = self._get_prescan_status(self._prescan_data)
                if not status["all_scanned"]:
                    self.process_state = "ERROR"
                    self.error_message = "Prescanning failed - missing items"
                    await self.logger.log("ERROR", "Prescanning failed, cannot start process",
                                          data=self.get_full_status(), is_event=True)
                    return

            # FIXED: do not wait for confirm here - confirm is handled by enqueueing load_and_start_workorder
            self.process_state = "WAITING_FOR_ITEMS"
            await self.logger.log("INFO", "Prescanning confirmed earlier. Starting actual process now.",
                                  data=self.get_full_status(), is_event=True)

            for i, step in enumerate(self.workorder["steps"]):
                self.current_step_index = i
                self.current_item_index = 0
                await self.logger.log("INFO", f"Starting Step {i + 1}", data=self.get_full_status(), is_event=False)

                num_items_to_scan = len(step.get("items", []))
                if num_items_to_scan == 0:
                    await self.logger.log("WARNING", f"Step {i + 1} has no items, skipping.",
                                          data=self.get_full_status(), is_event=True)
                    continue

                scanned_item_ids = set()

                # Add initial barcode to scanned items if it belongs to this step (first step only)
                if i == 0 and initial_barcode:
                    valid_items = {item["item_id"]: item for item in step["items"]}
                    if initial_barcode in valid_items:
                        scanned_item_ids.add(initial_barcode)
                        item_info = valid_items[initial_barcode]
                        await self.logger.log("INFO",
                                              f"Initial scanned item added: {item_info['name']} ({initial_barcode})",
                                              data=self.get_full_status(), is_event=True)
                    else:
                        await self.logger.log("WARNING",
                                              f"Initial barcode {initial_barcode} does not belong to step {i + 1}",
                                              data=self.get_full_status(), is_event=True)

                # FIXED: announce ready for scanning before consuming queue so UI doesn't timeout
                self.process_state = "WAITING_FOR_ITEMS"
                await self.logger.log("INFO", f"Ready to accept scans for Step {i+1}",
                                      data=self.get_full_status(), is_event=True)

                while len(scanned_item_ids) < num_items_to_scan:
                    cmd, future = await self.hmi_cmd_queue.get()
                    if cmd["command"] == "scan_item":
                        barcode = cmd["data"].get("barcode", "").strip()

                        # Check if barcode belongs to this step
                        valid_items = {item["item_id"]: item for item in step["items"]}
                        if barcode in valid_items:
                            if barcode not in scanned_item_ids:
                                scanned_item_ids.add(barcode)
                                item_info = valid_items[barcode]
                                scan_response = {"status": "success", "message": f"Item {item_info['name']} scanned."}
                                await self.logger.log("INFO", f"Item scanned: {barcode}",
                                                      data=self.get_full_status(), is_event=False)
                            else:
                                scan_response = {"status": "fail", "message": "Item already scanned."}
                                await self.logger.log("WARNING", f"Duplicate scan attempt: {barcode}",
                                                      data=self.get_full_status(), is_event=False)
                        else:
                            scan_response = {"status": "fail", "message": "Scanned item does not belong to this step."}
                            await self.logger.log("WARNING", f"Invalid scan for this step: {barcode}",
                                                  data=self.get_full_status(), is_event=False)

                        if future:
                            future.set_result(scan_response)
                    else:
                        # If another command arrived (e.g., abort/resume/reset) let the caller have the status
                        if future:
                            future.set_result(self.get_full_status())

                await self.logger.log("INFO", f"All items scanned for Step {i + 1}, moving to lid close",
                                      data=self.get_full_status(), is_event=True)

                self.process_state = "WAITING_FOR_LID_CLOSE"
                await self.logger.log("INFO",
                                      "Process state updated to WAITING_FOR_LID_CLOSE, sending lid close command",
                                      data=self.get_full_status(), is_event=True)

                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 1})

                # Wait for lid to close with timeout (use default if config not available)
                lid_timeout = getattr(config, 'LID_CLOSE_TIMEOUT_SEC', 30.0)
                lid_close_start = time.time()
                while self.lid_open:
                    if time.time() - lid_close_start > lid_timeout:
                        raise ValueError("Lid failed to close within timeout")
                    await asyncio.sleep(0.5)
                await self.logger.log(
                    "DEBUG",
                    f"Waiting for lid to close... lid_open={self.lid_open}",
                    data=self.get_full_status(),
                    is_event=False
                )

                self.process_state = "WAITING_FOR_MOTOR_START"
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 1})

                # Wait for motor to start with timeout (use default if config not available)
                motor_timeout = getattr(config, 'MOTOR_START_TIMEOUT_SEC', 15.0)
                motor_start_ts = time.time()
                while not self.motor_running:
                    if time.time() - motor_start_ts > motor_timeout:
                        self.motor_start_failed_alert = True
                        raise ValueError("Motor failed to start")
                    await asyncio.sleep(0.5)

                self.process_state = "MIXING"
                self.mixing_timer_started = True
                self.mixing_start_timestamp = time.time()

                # Mix for the required time
                mix_duration = step["mix_time_sec"]
                while time.time() - self.mixing_start_timestamp < mix_duration:
                    # Check if we're paused
                    await self._is_paused.wait()
                    await asyncio.sleep(0.5)
                    if self.lid_open:
                        raise ValueError("Lid opened during mixing - emergency stop")

                self.mixing_timer_started = False
                # After mixing, set to WAITING_FOR_ITEMS if there are more steps, else will finish
                self.process_state = "WAITING_FOR_ITEMS"
                await self.logger.log("INFO", f"Mixing for Step {i+1} completed, moving to next step",
                                      data=self.get_full_status(), is_event=True)

                # Stop motor and open lid
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})

            self.process_state = "PROCESS_COMPLETE"
            await self.logger.log("INFO", "Work order has finished successfully.", data=self.get_full_status(),
                                  is_event=False)

        except asyncio.CancelledError:
            await self.logger.log("WARNING", "Work order processing was cancelled", data=self.get_full_status(),
                                  is_event=True)
            raise
        except Exception as e:
            await self.logger.log("ERROR", f"Work order processing failed: {e}", data=self.get_full_status(),
                                  is_event=True)
            self.process_state = "ERROR"
            self.error_message = str(e)
            # Ensure motor is stopped on error
            try:
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
            except:
                pass
            raise

    async def _monitor_hardware_status(self):
        last_aborted_log = 0
        lower_threshold = self.low_temp_threshold
        higher_threshold = self.high_temp_threshold
        while True:
            try:
                if not self.gateway.is_connected:
                    await self.gateway.connect()
                if self.gateway.is_connected:
                    res_lid = await self.gateway.send_command({"action": "read", "tag_name": "rd_lid_status_kn1"})
                    if res_lid and "value" in res_lid:
                        self.lid_open = res_lid["value"] is False
                    res_motor = await self.gateway.send_command({"action": "read", "tag_name": "rd_motor_status_kn1"})
                    if res_motor and "value" in res_motor:
                        self.motor_running = res_motor["value"]
                    if self.process_state == "MIXING" and self.lid_open:
                        await self.logger.log("CRITICAL", "LID OPENED DURING MIXING! EMERGENCY STOP!",
                                              data=self.get_full_status(), is_event=True)
                        self.error_message = "CRITICAL: Lid opened during mixing cycle."
                        self.process_state = "ERROR"
                        if self.work_order_task and not self.work_order_task.done():
                            self.work_order_task.cancel()
                    if self.process_state == "ABORTED":
                        now = time.time()
                        if now - last_aborted_log >= 2:
                            await self.logger.log("INFO", "Workorder is paused (ABORTED state) - waiting for operator action",
                                                  data=self.get_full_status(), is_event=False)
                            last_aborted_log = now
                try:
                    temp = self.get_temperature
                    if temp < lower_threshold:
                        print(f"temperature has dropped:{temp}")
                        await self.logger.log("WARNING", "TEMPERATURE HAS DROPPED", data={"temperature": temp}, is_event=True)
                    elif temp > higher_threshold:
                        print(f"temperature has raised above the level:{temp}")
                        await self.logger.log("WARNING", "TEMPERATURE HAS RAISED", data={"temperature": temp}, is_event=True)
                except Exception as e:
                    await self.logger.log(
                        "ERROR",
                        f"Temperature read failed: {e}",
                        data=self.get_full_status(),
                        is_event=True
                    )

            except Exception as e:
                await self.logger.log("ERROR", f"Error in hardware monitor: {e}", data=self.get_full_status(),
                                      is_event=True)
            await asyncio.sleep(1)

    async def hmi_client_handler(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                message = json.loads(data.decode())
                command = message.get("command")

                if command == "abort":
                    if self.process_state == "MIXING":
                        # Pause the process instead of canceling
                        try:
                            # Stop the motor
                            await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})

                            # Open the lid
                            await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})

                            # Calculate remaining mixing time
                            if self.mixing_timer_started and self.mixing_start_timestamp:
                                elapsed_time = time.time() - self.mixing_start_timestamp
                                total_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
                                self.remaining_mix_time = max(0, total_mix_time - elapsed_time)

                            # Stop the timer
                            #self.mixing_start_timestamp = None
                            self._is_paused.clear()
                            self.mixing_timer_started = False

                            # Change state to ABORTED (paused)
                            self.process_state = "ABORTED"
                            self.error_message = "Workorder paused by operator."

                            await self.logger.log("INFO", "Workorder paused - motor stopped, lid opened, timer paused",
                                                  data=self.get_full_status(), is_event=True)

                        except Exception as e:
                            await self.logger.log("ERROR", f"Failed to pause workorder: {e}",
                                                  data=self.get_full_status(), is_event=True)
                            self.process_state = "ERROR"
                            self.error_message = f"Failed to pause: {str(e)}"

                        response = self.get_full_status()

                    else:
                        await self.logger.log("WARNING", "Abort requested outside MIXING stage.",
                                              data=self.get_full_status(), is_event=True)
                        response = self.get_full_status()

                elif command == "resume":
                    if self.process_state == "ABORTED":
                        try:

                            await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 1})

                            lid_timeout = getattr(config, 'LID_CLOSE_TIMEOUT_SEC', 30.0)
                            lid_close_start = time.time()
                            while self.lid_open:
                                if time.time() - lid_close_start > lid_timeout:
                                    raise ValueError("Lid failed to close within timeout")
                                await asyncio.sleep(0.5)

                            await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 1})

                            motor_timeout = getattr(config, 'MOTOR_START_TIMEOUT_SEC', 15.0)
                            motor_start_ts = time.time()
                            while not self.motor_running:
                                if time.time() - motor_start_ts > motor_timeout:
                                    self.motor_start_failed_alert = True
                                    raise ValueError("Motor failed to start")
                                await asyncio.sleep(0.5)

                            self.process_state = "MIXING"
                            self.error_message = ""
                            #self.mixing_timer_started = True

                            # 4. Recalculate the start timestamp to account for the pause
                            total_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
                            elapsed_before_pause = total_mix_time - self.remaining_mix_time
                            self.mixing_start_timestamp = time.time() - elapsed_before_pause
                            self.mixing_timer_started = True

                            self._is_paused.set()
                            self._resume_event.set()

                            response = self.get_full_status()
                            await self.logger.log("INFO", "Process resumed successfully from ABORTED state",
                                                  data=self.get_full_status(), is_event=True)

                        except Exception as e:
                            await self.logger.log("ERROR", f"Resume failed: {e}",
                                                  data=self.get_full_status(), is_event=True)
                            self.process_state = "ERROR"
                            self.error_message = f"Resume failed: {str(e)}"
                            response = {"status": "fail", "message": f"Resume failed: {str(e)}"}

                    else:
                        response = {"status": "fail", "message": "Cannot resume - not in ABORTED state"}
                        await self.logger.log("WARNING", "Resume attempted outside ABORTED state",
                                              data=self.get_full_status(), is_event=True)

                elif command == "reset_controller":
                    if self.work_order_task and not self.work_order_task.done():
                        self.work_order_task.cancel()
                    self._reset_internal_state()
                    response = self.get_full_status()

                # FIXED: handle confirm_start by enqueuing load_and_start_workorder (Option 1)
                elif command == "confirm_start":

                    if self.process_state in ("PRESCANNING", "PRESCAN_COMPLETE"):

                        # Do not start _process_workorder here directly.
                        # Enqueue a load_and_start_workorder so run() picks it and starts the task consistently.
                        if self.work_order_task and not self.work_order_task.done():
                            response = {"status": "fail", "message": "Workorder already running"}
                        else:
                            future = asyncio.get_running_loop().create_future()
                            # Put into the run loop queue - run() will create the work_order_task
                            await self.hmi_cmd_queue.put((
                                {"command": "load_and_start_workorder", "data": self.workorder}, future
                            ))
                            response = {"status": "success", "message": "Prescan confirmed. Starting actual process."}

                    else:

                        response = {"status": "fail", "message": f"Confirm not allowed in state {self.process_state}"}

                elif command == "load_workorder":

                    self.workorder = message["data"]
                    self.process_state = "PRESCANNING"
                    # initialize prescan data structure
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

                    response = self.get_full_status()

                # Prescan item handling - same as before but mark PRESCAN_COMPLETE when all scanned
                elif command == "prescan_item":
                    if self.process_state in ("PRESCANNING", "PRESCAN_COMPLETE"):
                        future = asyncio.get_running_loop().create_future()
                        mock_cmd = {"command": "prescan_item", "data": message.get("data", {})}
                        asyncio.create_task(self._process_prescan_item(mock_cmd, future))
                        response = await asyncio.wait_for(future, timeout=15.0)
                    else:
                        response = {"status": "fail", "message": f"Prescan not allowed in state {self.process_state}"}


                # FIXED: proper scan_item handler - push into hmi_cmd_queue so _process_workorder consumes it
                elif command == "scan_item":
                    if self.process_state == "WAITING_FOR_ITEMS":
                        future = asyncio.get_running_loop().create_future()
                        # Put the actual scan message into queue to be processed by _process_workorder
                        await self.hmi_cmd_queue.put((message, future))
                        try:
                            response = await asyncio.wait_for(future, timeout=15.0)
                        except asyncio.TimeoutError:
                            response = {"status": "fail", "message": "Timeout while waiting for scan processing"}
                    else:
                        # Not allowed to scan in other states
                        response = {"status": "fail", "message": f"Cannot scan in state {self.process_state}"}

                elif command == "get_status":
                    response = self.get_full_status()

                elif command == "write":
                    # Handle write commands from Flask (lid/motor)
                    try:
                        response = await self.gateway.send_command({
                            "action": "write",
                            "tag_name": message.get("tag_name"),
                            "value": message.get("value")
                        })
                        print(f"Controller Gateway write response: {response}")
                    except Exception as e:
                        response = {"error": f"Write command failed: {e}"}

                else:
                    future = asyncio.get_running_loop().create_future()
                    await self.hmi_cmd_queue.put((message, future))
                    response = await asyncio.wait_for(future, timeout=15.0)

                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except Exception:
            await self.logger.log("WARNING", f"HMI client {peer} disconnected.", data={}, is_event=True)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_prescan_item(self, cmd, future):
        """Process a prescan item directly without using the queue"""
        barcode = cmd["data"].get("barcode", "").strip()

        if not hasattr(self, '_prescan_data') or not self._prescan_data:
            if future:
                future.set_result({"status": "error", "message": "Prescan data not initialized"})
            return

        if barcode in self._prescan_data['all_items']:
            if barcode not in self._prescan_data['scanned_items']:
                self._prescan_data['scanned_items'].add(barcode)
                self._prescan_data['all_items'][barcode]['status'] = 'DONE'

                response = {
                    "status": "success",
                    "message": f"Item {self._prescan_data['all_items'][barcode]['name']} prescanned",
                    "prescan_status": self._get_prescan_status(self._prescan_data)
                }
                await self.logger.log("INFO", f"Item prescanned: {barcode}",
                                      data=response, is_event=False)
            else:
                response = {
                    "status": "fail",
                    "message": "Item already prescanned",
                    "prescan_status": self._get_prescan_status(self._prescan_data)
                }
                await self.logger.log("WARNING", f"Duplicate scan: {barcode}",
                                      data=response, is_event=False)
        else:
            response = {
                "status": "error",
                "message": "Item does not belong to this workorder",
                "prescan_status": self._get_prescan_status(self._prescan_data)
            }
            await self.logger.log("WARNING", f"Invalid item: {barcode}",
                                  data=response, is_event=False)

        # FIXED: if all scanned, set PRESCAN_COMPLETE and log
        prescan_status = self._get_prescan_status(self._prescan_data)
        if prescan_status.get('all_scanned'):
            self.process_state = "PRESCAN_COMPLETE"
            await self.logger.log("INFO", "All prescan items scanned - PRESCAN_COMPLETE",
                                  data=self.get_full_status(), is_event=True)

        if future:
            future.set_result(response)

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
                    # FIXED: ensure we take the workorder already loaded (or the one passed)
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
                        await self.logger.log("INFO", "Work order task has ended. Performing cleanup.",
                                              data=self.get_full_status(), is_event=False)
                        if self.process_state == "PROCESS_COMPLETE":
                            self.process_state = "IDLE"
                            # Clear old workorder info
                            self.workorder = None
                            self.current_step_index = 0
                            self.current_item_index = 0
                            self.error_message = ""
                            self.remaining_mix_time = 0
                            self.mixing_timer_started = False
                            self.mixing_start_timestamp = None
                        elif self.process_state == "ERROR":
                            await self.logger.log("ERROR", f"Workorder ended in ERROR state: {self.error_message}",
                                                  data=self.get_full_status(), is_event=True)

                        await self.gateway.send_command(
                            {"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
            else:
                if future:
                    future.set_result({"status": "fail", "message": "No workorder active."})


# END of KneaderController

