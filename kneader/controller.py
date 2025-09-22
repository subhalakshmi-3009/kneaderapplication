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
        #self.low_temp_threshold = float(config_parser['temperature_thresholds']['low'])
        #self.high_temp_threshold = float(config_parser['temperature_thresholds']['high'])

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
            "prescan_complete": self.process_state != "PRESCANNING",
        }

        if self.process_state == "PRESCANNING" and self._prescan_data:
            status["prescan_status"] = self._get_prescan_status(self._prescan_data)

        if self.process_state == "MIXING" and self.mixing_timer_started:
            mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
            elapsed = time.time() - self.mixing_start_timestamp
            status["mixing_time_total"] = mix_time
            status["mixing_time_remaining"] = max(0, int(mix_time - elapsed))

        elif self.process_state == "ABORTED":
            current_step_mix_time = self.workorder["steps"][self.current_step_index][
                "mix_time_sec"] if self.workorder else 0
            status["mixing_time_total"] = current_step_mix_time
            status["mixing_time_remaining"] = int(self.remaining_mix_time)

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
                'status': item_info['status']
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

        #scanned_item_ids = set()
        scanned_item_ids = self.scanned_items_by_step.setdefault(step_index, set())
        self.process_state = "WAITING_FOR_ITEMS"
        await self.logger.log("INFO", f"Ready to accept scans for Step {step_index + 1}", data=self.get_full_status(),
                            is_event=True)

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

        # Execute the mixing process for this step
        return await self._execute_mixing_process(step_index)

    async def _process_scan_item(self, cmd, future, step, scanned_item_ids):
        barcode = cmd["data"].get("barcode", "").strip()
        valid_items = {item["item_id"]: item for item in step["items"]}

        if barcode in valid_items:
            if barcode not in scanned_item_ids:
                scanned_item_ids.add(barcode)
                # update controller-level index to reflect how many items scanned so far for UI visibility
                self.current_item_index = len(scanned_item_ids) - 1
                item_info = valid_items[barcode]
                scan_response = {"status": "success", "message": f"Item {item_info['name']} scanned."}
                await self.logger.log("INFO", f"Item scanned: {barcode} (step {self.current_step_index + 1})",
                                      data=self.get_full_status(), is_event=False)
            else:
                scan_response = {"status": "fail", "message": "Item already scanned."}
                await self.logger.log("WARNING", f"Duplicate scan attempt: {barcode}", data=self.get_full_status(),
                                      is_event=False)
        else:
            scan_response = {"status": "fail", "message": "Scanned item does not belong to this step."}
            await self.logger.log("WARNING", f"Invalid scan for this step: {barcode}", data=self.get_full_status(),
                                  is_event=False)

        # Provide the scan response back to the HMI caller
        if future:
            future.set_result(scan_response)

    async def _execute_mixing_process(self, step_index: int) -> bool:
        try:
            await self._ensure_gateway_connection()
            # Close lid
            self.process_state = "WAITING_FOR_LID_CLOSE"
            await self.logger.log("INFO", "Closing lid for mixing",
                                data=self.get_full_status(), is_event=True)

            # Send command to close lid with retry logic
            lid_close_attempts = 0
            while lid_close_attempts < 3:
                response = await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 1})
                if response and not response.get("error"):
                    break
                lid_close_attempts += 1
                await self.logger.log("WARNING", f"Lid close command failed, attempt {lid_close_attempts}",
                                    data=self.get_full_status(), is_event=True)
                await asyncio.sleep(1)

            if lid_close_attempts >= 3:
                raise ValueError("Failed to send lid close command after 3 attempts")

            # Wait for lid to close with timeout
            lid_timeout = getattr(config, 'LID_CLOSE_TIMEOUT_SEC', 30.0)
            lid_close_start = time.time()
            last_status_log = time.time()

            while self.lid_open:
                current_time = time.time()
                if current_time - lid_close_start > lid_timeout:
                    raise ValueError("Lid failed to close within timeout")

                # Log status every 5 seconds
                if current_time - last_status_log >= 5:
                    await self.logger.log("INFO", f"Waiting for lid to close... Time elapsed: {int(current_time - lid_close_start)}s",
                                        data=self.get_full_status(), is_event=False)
                    last_status_log = current_time

                await asyncio.sleep(0.5)

            await self.logger.log("INFO", "Lid closed successfully",
                                data=self.get_full_status(), is_event=True)

            # Start motor
            self.process_state = "WAITING_FOR_MOTOR_START"
            await self.logger.log("INFO", "Starting motor for mixing",
                                data=self.get_full_status(), is_event=True)

            # Send command to start motor with retry logic
            motor_start_attempts = 0
            while motor_start_attempts < 3:
                response = await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 1})
                if response and not response.get("error"):
                    break
                motor_start_attempts += 1
                await self.logger.log("WARNING", f"Motor start command failed, attempt {motor_start_attempts}",
                                    data=self.get_full_status(), is_event=True)
                await asyncio.sleep(1)

            if motor_start_attempts >= 3:
                raise ValueError("Failed to send motor start command after 3 attempts")

            # Wait for motor to start with timeout
            motor_timeout = getattr(config, 'MOTOR_START_TIMEOUT_SEC', 15.0)
            motor_start_ts = time.time()
            last_status_log = time.time()

            while not self.motor_running:
                current_time = time.time()
                if current_time - motor_start_ts > motor_timeout:
                    self.motor_start_failed_alert = True
                    raise ValueError("Motor failed to start within timeout")

                # Log status every 5 seconds
                if current_time - last_status_log >= 5:
                    await self.logger.log("INFO", f"Waiting for motor to start... Time elapsed: {int(current_time - motor_start_ts)}s",
                                        data=self.get_full_status(), is_event=False)
                    last_status_log = current_time

                await asyncio.sleep(0.5)

            # Start mixing
            self.process_state = "MIXING"
            self.mixing_timer_started = True
            self.mixing_start_timestamp = time.time()
            mix_duration = self.workorder["steps"][step_index]["mix_time_sec"]

            await self.logger.log("INFO", f"Mixing started for {mix_duration} seconds",
                                data=self.get_full_status(), is_event=True)

            # Mix for the required time
            mix_end_time = self.mixing_start_timestamp + mix_duration
            last_progress_log = time.time()

            while time.time() < mix_end_time:
                # Check if we're paused
                await self._is_paused.wait()

                # Log progress every 5 seconds
                current_time = time.time()
                if current_time - last_progress_log >= 5:
                    remaining = int(mix_end_time - current_time)
                    await self.logger.log("INFO", f"Mixing in progress... {remaining} seconds remaining",
                                        data=self.get_full_status(), is_event=False)
                    last_progress_log = current_time

                # Check for emergency stop conditions
                if self.lid_open:
                    raise ValueError("Lid opened during mixing - emergency stop")

                await asyncio.sleep(0.5)

            self.mixing_timer_started = False

            # Stop motor and open lid after mixing
            await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 1})#changed
            await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})

            # Wait for lid to open
            lid_open_start = time.time()
            while not self.lid_open:
                if time.time() - lid_open_start > lid_timeout:
                    await self.logger.log("WARNING", "Lid failed to open within timeout, but continuing",
                                        data=self.get_full_status(), is_event=True)
                    break
                await asyncio.sleep(0.5)

            self.process_state = "WAITING_FOR_ITEMS"
            await self.logger.log("INFO", f"Mixing for Step {step_index + 1} completed, ready for next step",
                                data=self.get_full_status(), is_event=True)

            return True

        except Exception as e:
            await self.logger.log("ERROR", f"Error in mixing process: {e}",
                                data=self.get_full_status(), is_event=True)
            # Ensure motor is stopped and lid is open on error
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

            self.process_state = "PROCESS_COMPLETE"
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

                    # Check for critical errors
                    if self.process_state == "MIXING" and self.lid_open:
                        await self.logger.log("CRITICAL", "LID OPENED DURING MIXING! EMERGENCY STOP!",
                                              data=self.get_full_status(), is_event=True)
                        self.error_message = "CRITICAL: Lid opened during mixing cycle."
                        self.process_state = "ERROR"
                        if self.work_order_task and not self.work_order_task.done():
                            self.work_order_task.cancel()

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

    """async def _monitor_temperature(self):
        try:
            temp = self.get_temperature
            if temp < self.low_temp_threshold:
                await self.logger.log("WARNING", f"Temperature has dropped: {temp}", data={"temperature": temp},
                                      is_event=True)
            elif temp > self.high_temp_threshold:
                await self.logger.log("WARNING", f"Temperature has raised above the level: {temp}",
                                      data={"temperature": temp}, is_event=True)
        except Exception as e:
            await self.logger.log("ERROR", f"Temperature read failed: {e}", data=self.get_full_status(), is_event=True)"""

    async def _handle_abort_command(self):
        if self.process_state == "MIXING":
            try:
                # Stop the motor and open the lid
                await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})
                await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})

                # Calculate remaining mixing time
                if self.mixing_timer_started and self.mixing_start_timestamp:
                    elapsed_time = time.time() - self.mixing_start_timestamp
                    total_mix_time = self.workorder["steps"][self.current_step_index]["mix_time_sec"]
                    self.remaining_mix_time = max(0, total_mix_time - elapsed_time)

                # Update state
                self._is_paused.clear()
                self.mixing_timer_started = False
                self.process_state = "ABORTED"
                self.error_message = "Workorder paused by operator."

                await self.logger.log("INFO", "Workorder paused - motor stopped, lid opened, timer paused",
                                      data=self.get_full_status(), is_event=True)
                return self.get_full_status()

            except Exception as e:
                await self.logger.log("ERROR", f"Failed to pause workorder: {e}", data=self.get_full_status(),
                                      is_event=True)
                self.process_state = "ERROR"
                self.error_message = f"Failed to pause: {str(e)}"
                return self.get_full_status()
        else:
            await self.logger.log("WARNING", "Abort requested outside MIXING stage.", data=self.get_full_status(),
                                  is_event=True)
            return self.get_full_status()

    async def _handle_resume_command(self):
        if self.process_state == "ABORTED":
            try:
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

                await self.logger.log("INFO", "Process resumed successfully from ABORTED state",
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
                self._prescan_data['all_items'][barcode]['status'] = 'DONE'

                response = {
                    "status": "success",
                    "message": f"Item {self._prescan_data['all_items'][barcode]['name']} prescanned",
                    "prescan_status": self._get_prescan_status(self._prescan_data)
                }
                await self.logger.log("INFO", f"Item prescanned: {barcode}", data=response, is_event=False)
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

        # Check if all items are scanned
        prescan_status = self._get_prescan_status(self._prescan_data)
        if prescan_status.get('all_scanned'):
            self.process_state = "PRESCAN_COMPLETE"
            await self.logger.log("INFO", "All prescan items scanned - PRESCAN_COMPLETE", data=self.get_full_status(),
                                  is_event=True)

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
                elif command == "reset_controller":
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
                    response = await self._handle_scan_item_command(message)
                elif command == "get_status":
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
                future = asyncio.get_running_loop().create_future()
                await self.hmi_cmd_queue.put(({"command": "load_and_start_workorder", "data": self.workorder}, future))
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
        if self.process_state == "WAITING_FOR_ITEMS":
            future = asyncio.get_running_loop().create_future()
            await self.hmi_cmd_queue.put((message, future))
            try:
                return await asyncio.wait_for(future, timeout=15.0)
            except asyncio.TimeoutError:
                return {"status": "fail", "message": "Timeout while waiting for scan processing"}
        else:
            return {"status": "fail", "message": f"Cannot scan in state {self.process_state}"}

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
                    future.set_result({"status": "fail", "message": "No workorder active."})

    async def _cleanup_after_workorder(self):
        await self.logger.log("INFO", "Work order task has ended. Performing cleanup.", data=self.get_full_status(),
                              is_event=False)

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

        await self.gateway.send_command({"action": "write", "tag_name": "wr_motor_control_kn1", "value": 0})