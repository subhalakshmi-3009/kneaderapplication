import asyncio
import json
import logging
import time
from typing import Dict, Any

# Basic configuration for logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - SIMULATOR - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KneaderSimulator:
    """Simulates the kneader microcontroller, handling reads, writes, and custom commands."""

    def __init__(self):
        # MODIFIED: Added pin 6 for lid control
        self.device_states = {
            "1": False,  # Lid Status (Read, False=open, True=closed)
            "2": False,  # Motor Status (Read)
            "3": None,  # Motor Control (Write)
            "4": None,  # Beep Control (Write)
            "5": None,  # Alarm Control (Write)
            "6": None   # Lid Control (Write)
        }
        self.subscribed_pins = set()
        self.clients = set()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handles an incoming connection from the gateway server."""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"Gateway connected from {client_addr}")
        self.clients.add(writer)
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                try:
                    message = json.loads(data.decode().strip())
                    logger.debug(f"Received from gateway: {message}")
                    response = await self.process_command(message)
                    if response:
                        writer.write((json.dumps(response) + "\n").encode())
                        await writer.drain()
                        logger.debug(f"Sent to gateway: {response}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except ConnectionError:
            logger.info(f"Gateway at {client_addr} disconnected")
        finally:
            self.clients.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def process_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Processes commands and returns an appropriate response."""
        cmd_type = command.get("cmd")

        if cmd_type == "force_lid_close":
            logger.info("Force command received. Simulating lid closure.")
            if not self.device_states["1"]:
                self.device_states["1"] = True
                await self.notify_pin_change("1", True)
            return {"status": "ok", "message": "Lid status has been set to closed."}
        elif cmd_type == "force_lid_open":
            logger.info("Force command received: Simulating lid opening.")
            if self.device_states["1"]:
                self.device_states["1"] = False
                await self.notify_pin_change("1", False)
            return {"status": "ok", "message": "Lid status set to open."}
        elif cmd_type == "subscribe":
            pins = command.get("pins", [])
            for pin_info in pins:
                self.subscribed_pins.add(str(pin_info.get("pin")))
            return {"status": "ok", "subscribed_to": [p['pin'] for p in pins]}
        elif cmd_type == "read":
            pin = str(command.get("pin"))
            if pin in self.device_states:
                return {"status": "ok", "slave_id": command.get("slave_id", 1), "pin": int(pin),
                        "value": self.device_states[pin], "io_type":"Read Pin"}
            return {"status": "error", "message": f"Invalid register {pin} for read"}
        elif cmd_type == "write":
            pin = str(command.get("pin"))
            value = bool(command.get("value"))
            print(f"[Simulator] Write request: pin={pin}, value={value}")
            self.device_states[pin] = value
            # MODIFIED: Added handler for lid control on pin 6
            if pin == "3":  # Motor control
                asyncio.create_task(self.update_motor_status(value))
            elif pin == "6": # Lid control
                asyncio.create_task(self.update_lid_status(value))
            return {"status": "ok", "slave_id": command.get("slave_id", 1), "pin": int(pin), "value": value,"io_type":"Write Pin"}
        elif cmd_type == "modbus_read":
            register = str(command.get("register"))
            if register in self.device_states:
                return {"status": "ok", "slave_id": command.get("slave_id", 1), "register": int(register),
                        "value": self.device_states[register]}
            return {"status": "error", "message": f"Invalid register {register} for read"}
        elif cmd_type == "modbus_write":
            register = str(command.get("register"))
            value = bool(command.get("value"))
            self.device_states[register] = value
            if register == "3":
                asyncio.create_task(self.update_motor_status(value))
            return {"status": "ok", "slave_id": command.get("slave_id", 1), "register": int(register), "value": value}

        return {"status": "error", "message": "Unknown command"}

    # NEW: Method to simulate lid state changes with a delay
    async def update_lid_status(self, should_be_closed: bool):
        """Simulates lid open/close delay."""
        await asyncio.sleep(1.0)  # Simulate a 1-second delay for the lid to move
        self.device_states["1"] = should_be_closed
        logger.info(f"Lid status is now {'CLOSED' if should_be_closed else 'OPEN'}")
        await self.notify_pin_change("1", should_be_closed)

    async def update_motor_status(self, should_run: bool):
        """Simulates motor startup/shutdown delay."""
        await asyncio.sleep(1.5)
        self.device_states["2"] = should_run
        logger.info(f"Motor status is now {'RUNNING' if should_run else 'STOPPED'}")
        await self.notify_pin_change("2", should_run)

    async def notify_pin_change(self, pin: str, value: bool):
        """Notifies the gateway about a state change if subscribed."""
        """if pin in self.subscribed_pins:"""
        message = {
                "event": "gpio_interrupt", "source": "esp32",
                "pin": int(pin), "value": value,
                "timestamp": time.time()
            }
        message_bytes = (json.dumps(message) + "\n").encode()
        for client_writer in list(self.clients):
            try:
                client_writer.write(message_bytes)
                await client_writer.drain()
            except ConnectionError:
                self.clients.remove(client_writer)

    async def start_server(self, host: str = "0.0.0.0", port: int = 8888):
        """Starts the simulator's TCP server."""
        server = await asyncio.start_server(self.handle_client, host, port)
        logger.info(f"Microcontroller simulator running on {host}:{port}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    simulator = KneaderSimulator()
    try:
        asyncio.run(simulator.start_server())
    except KeyboardInterrupt:
        logger.info("Shutting down simulator.")