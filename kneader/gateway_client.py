import asyncio
import json
from typing import Dict, Any, Optional
from utils.AsyncJsonLogger import AsyncJsonLogger


class AsyncGatewayClient:
    def __init__(self, host: str, port: int, logger: Optional[AsyncJsonLogger] = None):
        self.host, self.port, self.lock = host, port, asyncio.Lock()
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connected = False
        self._listener_task: Optional[asyncio.Task] = None
        self.pending_response_future: Optional[asyncio.Future] = None
        self.event_callback = None  # Callback for handling events

       
        self.logger: AsyncJsonLogger = logger

    async def connect(self):
        if self.logger:
            await self.logger.log("INFO", f"Connecting to gateway at {self.host}:{self.port}...", data={}, is_event=False)
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.is_connected = True
            if self.logger:
                await self.logger.log("INFO", "Connected to gateway.", data={}, is_event=False)

            # Subscribe to tags (lid & motor updates)
            subscribe_cmd = {"action": "subscribe_events", "tags": ["rd_lid_status_kn1", "rd_motor_status_kn1"]}
            self.writer.write((json.dumps(subscribe_cmd) + "\n").encode())
            await self.writer.drain()

            sub_response_data = await asyncio.wait_for(self.reader.readline(), timeout=10.0)
            if self.logger:
                await self.logger.log("INFO", f"Subscription response: {sub_response_data.decode().strip()}", data={}, is_event=False)

            if self._listener_task is None or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen())
        except Exception as e:
            if self.logger:
                await self.logger.log("ERROR", f"Gateway connection failed: {e}", data={}, is_event=True)
            await self._close()

    async def _listen(self):
        while self.is_connected:
            try:
                data = await self.reader.readline()
                if not data:
                    raise ConnectionError("Gateway closed connection")
                message = json.loads(data.decode().strip())

                if "event" in message:
                    if self.logger:
                        await self.logger.log("INFO", f"Received event: {message}", data=message, is_event=True)
                    if self.event_callback:
                        self.event_callback(message)
                elif self.pending_response_future and not self.pending_response_future.done():
                    self.pending_response_future.set_result(message)  # response handling = status
                else:
                    if self.logger:
                        await self.logger.log("WARNING", f"Unexpected response: {message}", data=message, is_event=False)

            except Exception as e:
                if self.logger:
                    await self.logger.log("ERROR", f"Gateway listener error: {e}", data={}, is_event=True)
                if self.pending_response_future and not self.pending_response_future.done():
                    self.pending_response_future.set_exception(e)
                await self._close()
                break
    """async def send_command(self, command, timeout=3):
    
        if not self.is_connected:
            await self.connect()
            if not self.is_connected:
                return {"error": "Cannot connect to controller"}

        try:
            message = json.dumps(command) + "\n"
            self.writer.write(message.encode())
            await self.writer.drain()

            # Wait for one line of response
            response_data = await asyncio.wait_for(self.reader.readline(), timeout=timeout)

            if response_data:
                response_str = response_data.decode("utf-8").strip()
                try:
                    return json.loads(response_str)
                except json.JSONDecodeError:
                    return {"raw_response": response_str}
            else:
                return {"error": "No response from controller"}

        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for controller"}
        except Exception as e:
            return {"error": str(e)}"""

    async def send_command(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with self.lock:
            if not self.is_connected:
                await self.connect()
                if not self.is_connected:
                    return None
            try:
                message = (json.dumps(command) + "\n").encode()
                self.writer.write(message)
                await self.writer.drain()

                self.pending_response_future = asyncio.get_running_loop().create_future()
                response = await asyncio.wait_for(self.pending_response_future, timeout=10.0)
                self.pending_response_future = None
                return response  # status (command response)
            except Exception as e:
                if self.logger:
                    await self.logger.log("ERROR", f"Error sending command: {e}", data=command, is_event=True)
                await self._close()
                return None

    async def _close(self):
        self.is_connected = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.reader = self.writer = None
        self.pending_response_future = None
        if self.logger:
            await self.logger.log("INFO", "Closed gateway connection.", data={}, is_event=False)
