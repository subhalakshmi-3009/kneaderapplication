async def _process_workorder(self, initial_barcode: Optional[str] = None):
        try:
            # status log
            await self.logger.log("INFO",
                                  f"Starting workorder: {self.workorder.get('name')}, initial_barcode: {initial_barcode}",
                                  data=self.get_full_status(), is_event=False)
            self.process_state = "WAITING_FOR_ITEMS"

            # Check lid status with timeout
            try:
                lid_status_res = await asyncio.wait_for(
                    self.gateway.send_command({"action": "read", "tag_name": "rd_lid_status_kn1"}),
                    timeout=5.0
                )
                is_lid_actually_closed = lid_status_res and lid_status_res.get("value") is True
                if is_lid_actually_closed:
                    await self.logger.log("INFO", "Lid is detected as closed at start, commanding it to open.",
                                          data=self.get_full_status(), is_event=False)
                    await self.gateway.send_command({"action": "write", "tag_name": "wr_lid_status_kn1", "value": 0})
                    await asyncio.sleep(1.5)
            except asyncio.TimeoutError:
                await self.logger.log("ERROR", "Timeout reading lid status at start", data=self.get_full_status(),
                                      is_event=True)
            except Exception as e:
                await self.logger.log("ERROR", f"Error checking lid status: {e}", data=self.get_full_status(),
                                      is_event=True)

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
                            else:
                                scan_response = {"status": "fail", "message": "Item already scanned."}
                        else:
                            scan_response = {"status": "fail", "message": "Scanned item does not belong to this step."}

                        if future:
                            future.set_result(scan_response)
                    else:
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
                #mix_time_remaining = step["mix_time_sec"]
                mix_duration = step["mix_time_sec"]
                while time.time() - self.mixing_start_timestamp < mix_duration:
                #while mix_time_remaining > 0:
                    # Check if we're paused
                    await self._is_paused.wait()

                    #if not self._is_paused.is_set():
                    #    await self.logger.log("DEBUG", "Mixing paused, waiting for resume...",
                      #                        data=self.get_full_status(), is_event=False)
                    #    await self._resume_event.wait()
                    #    self._resume_event.clear()
                    #    await self.logger.log("DEBUG", "Mixing resumed",
                    #                          data=self.get_full_status(), is_event=False)
                    await asyncio.sleep(0.5)
                    #mix_time_remaining -= 1
                    # Check for emergency stop conditions
                    if self.lid_open:
                        raise ValueError("Lid opened during mixing - emergency stop")

                self.mixing_timer_started = False
                self.process_state = "WAITING_FOR_ITEMS"

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
        -----------------------------------------------
async def _monitor_hardware_status(self)
    low temp=60
    high temp=100
    while true:
        try:
            temp=self.get_temp()
            if temp < low temp:
                msg=f"Temperature has dropped below the low level:{temp}"
            elif temp > high temp:
                msg=f"temperature has raised above the high level:{temp}"
            else 
                msg=(f"temperature:{temp}")
            print(msg)
            await self.logger.log("WARNING",msg,data={"Temperature":temp})
        except OSError as e:
            await self.logger.log("ERROR","Failed to read sensor",data=self.get_full_status(),is_event=True)
-----------------------------------------------------------------------------------------------------------------------
async def pre_scanning(self, workorder_data: Dict[str, Any]):
        prescan_data = {
            'all_items': {},  
            'scanned_items': set(),
            'missing_items': set()
        }
        
       
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
            
            if cmd["command"] == "scan_item":
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
        
        # Check for missing items after first pass
        prescan_data['missing_items'] = set(prescan_data['all_items'].keys()) - prescan_data['scanned_items']
        
        # Update status for missing items
        for missing_item in prescan_data['missing_items']:
            prescan_data['all_items'][missing_item]['status'] = 'MISSING'
        
        # Second pass: scan missing items
        while prescan_data['missing_items']:
            await self.logger.log("WARNING", f"Missing {len(prescan_data['missing_items'])} items, waiting for rescan", 
                                data=self._get_prescan_status(prescan_data), is_event=True)
            
            cmd, future = await self.hmi_cmd_queue.get()
            
            if cmd["command"] == "scan_item":
                barcode = cmd["data"].get("barcode", "").strip()
                
                if barcode in prescan_data['missing_items']:
                    prescan_data['scanned_items'].add(barcode)
                    prescan_data['missing_items'].remove(barcode)
                    prescan_data['all_items'][barcode]['status'] = 'DONE'
                    
                    response = {
                        "status": "success", 
                        "message": f"Missing item {prescan_data['all_items'][barcode]['name']} found",
                        "prescan_status": self._get_prescan_status(prescan_data)
                    }
                    await self.logger.log("INFO", f"Missing item scanned: {barcode}", 
                                        data=response, is_event=False)
                elif barcode in prescan_data['all_items']:
                    response = {
                        "status": "info", 
                        "message": "Item already scanned",
                        "prescan_status": self._get_prescan_status(prescan_data)
                    }
                else:
                    response = {
                        "status": "error", 
                        "message": "Item does not belong to this workorder",
                        "prescan_status": self._get_prescan_status(prescan_data)
                    }
                    await self.logger.log("WARNING", f"Invalid item during missing scan: {barcode}", 
                                        data=response, is_event=False)
                
                if future:
                    future.set_result(response)
            else:
                if future:
                    future.set_result({"status": "fail", "message": "Only scan commands allowed"})
        
        # Final verification
        if not prescan_data['missing_items']:
            await self.logger.log("INFO", "Prescanning completed successfully - all items available", 
                                data=self._get_prescan_status(prescan_data), is_event=True)
            return True
        else:
            await self.logger.log("ERROR", f"Prescanning failed - still missing {len(prescan_data['missing_items'])} items", 
                                data=self._get_prescan_status(prescan_data), is_event=True)
            return False

    