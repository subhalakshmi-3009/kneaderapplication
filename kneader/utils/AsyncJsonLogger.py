import asyncio
import json
import time
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque


class AsyncJsonLogger:
    """
    An asynchronous JSON logger that handles logging to separate event and timer files.
    Timer/status logs are updated atomically to keep only the last two entries.
    """

    def __init__(
            self,
            log_file: str,
            max_queue_size: int = 1000,
            max_file_size: int = 10 * 1024 * 1024,
            event_rotation_interval: int = 86400,
            log_level: str = "INFO",
            batch_size: int = 1,
    ):
        self.base_log_file = log_file
        self.event_log_file_path = self.base_log_file.replace(".json", "_events.json")
        self.log_file_path = self.base_log_file
        self.max_file_size = max_file_size
        self.event_rotation_interval = event_rotation_interval
        self.log_level = log_level.upper()
        self.batch_size = batch_size
        self.log_queue = asyncio.Queue(maxsize=max_queue_size)
        self.logger_task = None
        self.status_log_buffer = deque(maxlen=2)
        self._initialize_log_file(self.event_log_file_path)
        self._initialize_log_file(self.log_file_path)
        self.last_event_rotation_time = time.time()

        # NEW: Lock to prevent concurrent writes to status log
        self._status_log_lock = asyncio.Lock()

    def _initialize_log_file(self, file_path: str):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    def _check_and_rotate_events(self, file_path: str):
        try:
            if not os.path.exists(file_path):
                return

            last_rotation_time = self.last_event_rotation_time
            rotation_interval = self.event_rotation_interval
            should_rotate = (
                    os.path.getsize(file_path) >= self.max_file_size or
                    (time.time() - last_rotation_time) >= rotation_interval
            )

            if should_rotate:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base, ext = os.path.splitext(file_path)
                rotated_file = f"{base}_{timestamp}{ext}"
                print(f"Rotating log file: {file_path} to {rotated_file}")
                os.replace(file_path, rotated_file)  # FIXED: safer than os.rename
                self.last_event_rotation_time = time.time()
        except Exception as e:
            print(f"Error during log rotation for {file_path}: {e}")

    async def _write_logs(self, logs: List[Dict[str, Any]], is_event_log: bool = False):
        """
        Writes logs. Appends for events, performs an atomic overwrite for status.
        """
        if is_event_log:
            file_to_write = self.event_log_file_path
            self._check_and_rotate_events(file_to_write)
            try:
                with open(file_to_write, "a") as f:
                    for log in logs:
                        f.write(json.dumps(log) + "\n")
            except Exception as e:
                print(f"Error writing to event log {file_to_write}: {e}")
        else:
            file_to_write = self.log_file_path
            temp_file_path = file_to_write + ".tmp"

            async with self._status_log_lock:  # FIXED: prevent concurrent writes
                try:
                    with open(temp_file_path, "w") as f:
                        for log in logs:
                            f.write(json.dumps(log) + "\n")

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, os.replace, temp_file_path, file_to_write)  # FIXED
                except Exception as e:
                    print(f"Error during atomic write to status log {file_to_write}: {e}")

    async def _logger_worker(self):
        """The main worker task that processes logs from the queue."""
        event_log_buffer = []
        while True:
            try:
                log_data = await self.log_queue.get()

                if log_data is None:
                    if event_log_buffer:
                        await self._write_logs(event_log_buffer, is_event_log=True)
                    break

                is_event = log_data.pop("is_event", False)

                if is_event:
                    event_log_buffer.append(log_data)
                    if len(event_log_buffer) >= self.batch_size:
                        await self._write_logs(event_log_buffer, is_event_log=True)
                        event_log_buffer.clear()
                else:
                    self.status_log_buffer.append(log_data)
                    await self._write_logs(list(self.status_log_buffer), is_event_log=False)

                self.log_queue.task_done()

            except asyncio.CancelledError:
                if event_log_buffer:
                    await self._write_logs(event_log_buffer, is_event_log=True)
                break
            except Exception as e:
                print(f"Error in logger worker: {e}")

    def _is_log_level_allowed(self, log_level: str) -> bool:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        try:
            return levels.index(log_level.upper()) >= levels.index(self.log_level)
        except ValueError:
            return False

    async def log(self, level: str, message: str, data: Optional[Dict[str, Any]] = None, is_event: bool = False):
        if not self._is_log_level_allowed(level):
            return
        if is_event:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = time.time()
        log_data = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message,
            "data": data or {},
            "is_event": is_event
        }
        try:
            self.log_queue.put_nowait(log_data)
        except asyncio.QueueFull:
            print("Warning: Logger queue is full. Log message dropped.")

    async def start(self):
        if not self.logger_task or self.logger_task.done():
            self.logger_task = asyncio.create_task(self._logger_worker())

    async def stop(self):
        if self.logger_task and not self.logger_task.done():
            await self.log_queue.put(None)
            await self.log_queue.join()
            self.logger_task.cancel()
            try:
                await self.logger_task
            except asyncio.CancelledError:
                pass
