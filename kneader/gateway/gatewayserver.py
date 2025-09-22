import asyncio
import json
import logging
import configparser
import os
from collections import defaultdict, deque
from typing import Dict, Any, Optional, Set, List, Tuple

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - GATEWAY - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# --- Main Gateway Orchestrator ---

class GatewayManager:
    """
    Central class to manage all microcontroller connections and the server for top-level clients.
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.mc_clients: Dict[Tuple[str, int], MicrocontrollerClient] = {}
        self.tag_map: Dict[str, Dict[str, Any]] = {}
        self.tag_to_mc_map: Dict[str, MicrocontrollerClient] = {}
        self.interrupt_source_to_tag_map: Dict[Tuple, str] = {}
        self.event_queue = asyncio.Queue()
        # NEW: Dictionary to hold queues of Futures for pending requests
        self.pending_requests: Dict[Tuple, deque] = defaultdict(deque)

    def load_config(self):
        """Parses the main JSON config to build the gateway's operational structure."""
        logger.info(f"Loading configuration from {self.config_path}")
        with open(self.config_path, 'r') as f:
            full_config = json.load(f)

        tags_by_mc = defaultdict(list)
        for tag in full_config:
            self.tag_map[tag['tag_name']] = tag
            mc_host = tag.get("micro_controller_ip", "0.0.0.0")
            mc_port = int(tag.get("micro_controller_port", 8888))
            tags_by_mc[(mc_host, mc_port)].append(tag)

            if tag.get("event_report") == "state based":
                key = None
                if "pcf_addr" in tag and "pcf_pin" in tag:
                    key = ("pcf8574", tag["pcf_addr"].lower(), int(tag["pcf_pin"]))
                elif "function_code" in tag and "Pin" in tag["function_code"]:
                    key = ("esp32", int(tag["start_add"]))
                if key: self.interrupt_source_to_tag_map[key] = tag['tag_name']
        logger.info(f"Interrupt sources mapped: {self.interrupt_source_to_tag_map}")  # Add this line here
        for (host, port), tags in tags_by_mc.items():
            client = MicrocontrollerClient(host, port, tags, self)  # Pass self (manager)
            self.mc_clients[(host, port)] = client
            for tag in tags: self.tag_to_mc_map[tag['tag_name']] = client

        logger.info(f"Configuration loaded. Found {len(self.mc_clients)} microcontrollers.")

    def get_tag_for_event(self, event: Dict) -> Optional[str]:
        source, key = event.get("source"), None
        if source == "esp32":
            key = ("esp32", event.get("pin"))
        elif source == "pcf8574":
            key = ("pcf8574", event.get("addr", "").lower(), event.get("pin"))
        logger.debug(f"Event mapping: source={source}, key={key}, map={self.interrupt_source_to_tag_map}")
        return self.interrupt_source_to_tag_map.get(key)

    async def start(self):
        self.load_config()
        self.top_controller_server = GatewayTCPServer('0.0.0.0', 5020, self)
        tasks = [mc.run() for mc in self.mc_clients.values()]
        tasks.append(self.top_controller_server.start())
        await asyncio.gather(*tasks)

    async def route_command_to_mc(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Routes a command, creates a future for its response, and sends it."""
        tag_name = command.get("tag_name")
        if not tag_name: return {"status": "error", "message": "Command missing 'tag_name'"}

        mc_client = self.tag_to_mc_map.get(tag_name)
        if not mc_client: return {"status": "error", "message": f"No microcontroller found for tag '{tag_name}'"}

        tag_config = self.tag_map.get(tag_name, {})
        esp32_command, request_key = self._build_esp32_command_and_key(command, tag_config, mc_client)

        if esp32_command is None:
            return {"status": "error", "message": "Unsupported action or invalid command format"}

        if command.get("action") == "direct_command":
            await mc_client.send_command(esp32_command)
            return {"status": "ok", "message": "Direct command sent."}

        if not esp32_command or not request_key:
            return {"status": "error", "message": "Could not build a valid command"}

        # Create a future for this specific request
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_key].append(future)

        # Send the command to the microcontroller
        await mc_client.send_command(esp32_command)

        try:
            # Wait for the future to be resolved by the listener task
            return await asyncio.wait_for(future, timeout=5.0)
        except asyncio.TimeoutError:
            # Clean up the future if it timed out
            if future in self.pending_requests[request_key]:
                self.pending_requests[request_key].remove(future)
            return {"status": "error", "message": "Response timeout from microcontroller"}

    def _build_esp32_command_and_key(self, incoming_cmd: Dict, tag_config: Dict, mc_client) -> Tuple[
        Optional[Dict], Optional[Tuple]]:
        """Builds the ESP32 command and a unique key for tracking the request."""
        action, value = incoming_cmd.get("action"), incoming_cmd.get("value")
        print(f"DEBUG: Building command for action '{action}', tag_config: {tag_config}")
        is_pcf = "pcf_addr" in tag_config and "pcf_pin" in tag_config
        slave_id, start_add = tag_config["slave_id"], tag_config.get("start_add")
        pcf_addr_str, pcf_pin = (tag_config["pcf_addr"], tag_config["pcf_pin"]) if is_pcf else (None, None)
        mc_key = (mc_client.host, mc_client.port)
        function_code = tag_config["function_code"]

        ### This change for gateway_server to replicate close lid.
        if action == "direct_command":
            print(f"Direct command received {incoming_cmd}")
            payload = incoming_cmd.get("payload")
            return payload, None  # No response key needed

        command, req_key = None, None

        if action == "read":
            if is_pcf:
                command = {"cmd": "pcf_read", "slave_id": slave_id, "addr": int(pcf_addr_str, 16), "pin": pcf_pin}
                req_key = ("pcf_read", *mc_key, slave_id, pcf_addr_str, pcf_pin)
            else:
                if function_code == "Read Pin":
                    command = {"cmd": "read", "slave_id": slave_id, "pin": start_add}
                    req_key = ("read", *mc_key, slave_id, start_add)
                else:
                    command = {"cmd": "modbus_read", "slave_id": slave_id, "register": start_add}
                    req_key = ("modbus_read", *mc_key, slave_id, start_add)
            return command, req_key  # ADD THIS RETURN FOR READ ACTIONS

        elif action == "write":
            if is_pcf:
                command = {
                    "cmd": "pcf_write",
                    "slave_id": slave_id,
                    "addr": int(pcf_addr_str, 16),
                    "pin": pcf_pin,
                    "value": value
                }
                req_key = ("pcf_write", *mc_key, slave_id, pcf_addr_str, pcf_pin)
            else:
                if function_code == "Write Pin":
                    command = {
                        "cmd": "write",
                        "slave_id": slave_id,
                        "pin": start_add,
                        "value": value
                    }
                    req_key = ("write", *mc_key, slave_id, start_add)
                else:
                    command = {
                        "cmd": "modbus_write",
                        "slave_id": slave_id,
                        "register": start_add,
                        "value": value
                    }
                    req_key = ("modbus_write", *mc_key, slave_id, start_add)
            return command, req_key

        # Return None, None for unsupported actions
        return None, None

# --- Client for a single Microcontroller ---

class MicrocontrollerClient:
    """Manages a connection to one ESP32 and routes its responses."""

    def __init__(self, host: str, port: int, tags: List[Dict], manager: GatewayManager):
        self.host, self.port, self.tags, self.manager = host, port, tags, manager
        self.reader, self.writer, self.is_connected = None, None, False

    async def run(self):
        # Auto-reconnection loop
        while True:
            try:
                logger.info(f"Attempting to connect to microcontroller at {self.host}:{self.port}...")
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self.is_connected = True
                logger.info(f"✅ Connection successful to {self.host}:{self.port}")
                await self._send_subscribe_command()
                await self._listener()
            except (ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.error(f"Could not connect to {self.host}:{self.port}. Reason: {e}")
            finally:
                self.is_connected = False
                self._fail_pending_requests()
                logger.info(f"Disconnected from {self.host}:{self.port}. Retrying in 10 seconds...")
                await asyncio.sleep(10)

    def _fail_pending_requests(self):
        """On disconnect, fail any requests that were waiting for a response from this micro."""
        mc_key = (self.host, self.port)
        for req_key, future_queue in list(self.manager.pending_requests.items()):
            if req_key[1:3] == mc_key:
                for future in future_queue:
                    future.set_exception(ConnectionError(f"Connection to {self.host}:{self.port} was lost."))
                del self.manager.pending_requests[req_key]

    async def _listener(self):
        """Listens for all data and routes it to the correct future or event queue."""
        while self.is_connected:
            data = await self.reader.readline()
            if not data: raise ConnectionError("Microcontroller closed connection")
            payload = json.loads(data.decode().strip())

            if payload.get("event") == "gpio_interrupt":
                await self.manager.event_queue.put(payload)
                continue

            # --- NEW: Correlate response to a pending request future ---
            mc_key = (self.host, self.port)
            # Infer the request key from the response payload
            print(f"Payload from simulator {payload}")
            if "pin" in payload:
                is_write_response = payload.get("io_type")
                action = "write" if is_write_response == "Write Pin" else "read"
                req_key = (action, *mc_key, payload.get("slave_id"), payload.get("pin"))
            elif "register" in payload:  # It's a Modbus response
                action = "modbus_write" if "value" in payload and "status" in payload else "modbus_read"
                req_key = (action, *mc_key, payload.get("slave_id"), payload.get("register"))
            elif "addr" in payload:  # It's a PCF response
                action = "pcf_write" if "value" in payload and "status" in payload else "pcf_read"
                req_key = (action, *mc_key, payload.get("slave_id"), payload.get("addr"), payload.get("pin"))
            else:
                req_key = None

            # Find the queue of futures for this key and resolve the oldest one
            if req_key and req_key in self.manager.pending_requests:
                future_queue = self.manager.pending_requests[req_key]
                if future_queue:
                    future = future_queue.popleft()
                    future.set_result(payload)
                if not future_queue:
                    del self.manager.pending_requests[req_key]  # Clean up empty deque
                print(f"[Gateway] Response from simulator: {payload}")
            else:
                logger.warning(f"Received uncorrelated response from {self.host}:{self.port}: {payload}")

    async def send_command(self, command: Dict):
        """Sends a pre-formatted command to the microcontroller."""
        if not self.is_connected:
            raise ConnectionError("Microcontroller not connected")
        message = (json.dumps(command) + "\n").encode()
        self.writer.write(message)
        await self.writer.drain()
        logger.info(f"--> Sent to {self.host}:{self.port}: {command}")

    async def _send_subscribe_command(self):
        """Builds and sends the subscribe command."""
        # This function remains the same as the previous version
        pins_to_subscribe = []
        for tag in self.tags:
            if tag.get("event_report") == "state based":
                pin_info = {}
                if "pcf_addr" in tag and "pcf_pin" in tag:
                    pin_info = {"source": "pcf8574", "slave_id": tag["slave_id"], "addr": tag["pcf_addr"],
                                "pin": tag["pcf_pin"], "int_gpio": tag.get("int_gpio", 14)}
                elif "function_code" in tag and "Pin" in tag["function_code"]:
                    pin_info = {"source": "esp32", "slave_id": tag["slave_id"], "pin": tag["start_add"]}
                if pin_info: pins_to_subscribe.append(pin_info)
        if not pins_to_subscribe: return
        await self.send_command({"cmd": "subscribe", "pins": pins_to_subscribe, "debounce_ms": 100})


# --- Server for Top-Level Controllers ---

class GatewayTCPServer:
    """Accepts connections from top-level clients and handles their requests and event subscriptions."""

    # This class is now simplified, as the complex correlation logic is in the Manager
    def __init__(self, host: str, port: int, manager: GatewayManager):
        self.host, self.port, self.manager = host, port, manager
        self.event_subscriptions = defaultdict(set)
        self.client_to_tags_map = defaultdict(set)

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info(f"✅ Gateway TCP Server listening on {self.host}:{self.port}")
        asyncio.create_task(self.forward_events_to_clients())
        async with server:
            await server.serve_forever()

    async def forward_events_to_clients(self):
        logger.info("Event forwarder for top-level clients started.")
        while True:
            event = await self.manager.event_queue.get()
            tag_name = self.manager.get_tag_for_event(event)
            if not tag_name: continue
            event['tag_name'] = tag_name
            message = (json.dumps(event) + "\n").encode()
            if tag_name in self.event_subscriptions:
                for writer in list(self.event_subscriptions[tag_name]):
                    try:
                        writer.write(message)
                        await writer.drain()
                    except (ConnectionError, BrokenPipeError):
                        pass

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info('peername')
        logger.info(f"✅ Top-level client connected from {peername}")

        try:
            while True:
                data = await reader.readline()
                if not data: break

                command = json.loads(data.decode().strip())
                action = command.get("action")

                if action == "subscribe_events":
                    tags_to_sub = command.get("tags", [])
                    for tag in tags_to_sub:
                        self.event_subscriptions[tag].add(writer)
                        self.client_to_tags_map[writer].add(tag)
                    logger.info(f"Client {peername} subscribed to events for tags: {tags_to_sub}")
                    response = {"status": "ok", "subscribed_to_events_for": tags_to_sub}
                else:  # Handle regular read/write commands
                    print(f"got the command {command}")
                    response = await self.manager.route_command_to_mc(command)

                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except (ConnectionError, asyncio.IncompleteReadError):
            logger.warning(f"Client {peername} disconnected.")
        finally:
            if writer in self.client_to_tags_map:
                for tag in self.client_to_tags_map[writer]:
                    if tag in self.event_subscriptions: self.event_subscriptions[tag].discard(writer)
                del self.client_to_tags_map[writer]
            writer.close()
            await writer.wait_closed()


# --- Main Entry Point ---

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    config_path = os.path.join(parent_dir, 'config.ini')

    config = configparser.ConfigParser()
    config.read(config_path)
    config_file_path = config['files']['rtu_config_file']
    gateway_manager = GatewayManager(config_file_path)
    try:
        asyncio.run(gateway_manager.start())
    except KeyboardInterrupt:
        logger.info("Gateway shutting down.")