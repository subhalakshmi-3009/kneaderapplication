import json
import time
import asyncio
from typing import List, Dict
from utils.stopwatch import Stopwatch
from utils.time_utils import TimeUtils


class Kneader:
    def __init__(self, kneader_id, device_ip, device_id, logger, tag_config, my_tag_configs: List[Dict], broadcast_callback):
        self.kneader_id = kneader_id
        self.device_ip = device_ip
        self.device_id = device_id
        self.logger = logger
        self.tag_config = tag_config
        self.broadcast_callback = broadcast_callback
        
        self.kneader_state = {
            "kneader_id": kneader_id,
            "lid_state": 0,
            "motor_off": 0,
            "previous_door_state": 0,
            "current_temperature": 0,
            "target_temperature": 100,
            "items": [],   # each item = batch dict
            "ui_signal": "Timer_steady",
            "other_issue": None,
            "internal_timers": {
                "item_added_lid_open": 0,
                "item_added_lid_close": 0,
            },
            "messages": ""
        }

        self.batch_timer: Dict[str, Stopwatch] = {}   # fixture_id → Stopwatch
        self.batch_removal_id = []
        self.previous_state = "idle"
        self.lid_closed = True
        self.event_triggered = False
        self.ingredient_added = False
        self.new_batches = []

    def to_json(self):
        """Return the kneader data as a JSON string."""
        data = {
            "kneader_id": self.kneader_id,
            "device_ip": self.device_ip,
            "device_id": self.device_id,
            "kneader_state": self.kneader_state
        }
        return json.dumps(data, indent=4)

    async def log_event(self, event_message: str):
        """Logs an event snapshot with kneader state."""
        try:
            self.kneader_state["messages"] = event_message
            log_data = {"kneader_state": self.kneader_state.copy()}
            await self.logger.log("INFO", event_message, data=log_data, is_event=True)
        finally:
            self.kneader_state["messages"] = ""

    async def process_log(self):
        """Periodic status logging with elapsed + remaining time for batches."""
        while True:
            try:
                kneader_log = self.kneader_state.copy()
                kneader_log["items"] = []

                for item in self.kneader_state["items"]:
                    item_data = item.copy()
                    sw = self.batch_timer.get(item.get("batch_id"))
                    if sw:
                        elapsed_time = sw.get_elapsed_time()
                        item_data["elapsed_time"] = elapsed_time
                        # use TimeUtils like oven does (curing_time → mixing_time_sec here)
                        total_time = item.get("mix_time_sec", 0)
                        if total_time:
                            remaining_time = await TimeUtils.time_difference(str(total_time), elapsed_time)
                            item_data["remaining_time"] = remaining_time
                    kneader_log["items"].append(item_data)

                await self.logger.log("INFO", "Kneader status update", data={"kneader_state": kneader_log}, is_event=False)

            except Exception as e:
                await self.logger.log("ERROR", f"Kneader process_log error: {e}", data={}, is_event=True)

            await asyncio.sleep(1)
