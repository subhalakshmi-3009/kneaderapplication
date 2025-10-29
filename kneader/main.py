import asyncio
import logging
import json
import paho.mqtt.client as mqtt
from controller import KneaderController
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - KNEADER_CONTROLLER - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MqttBridge:
    """
    Bridges MQTT commands from Flask/backend to the KneaderController.
    """
    def __init__(self, controller):
        self.controller = controller
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.loop = asyncio.get_event_loop()

    def start(self):
        logger.info("🔌 Connecting to MQTT broker (localhost:1883)...")
        self.client.connect("localhost", 1883, 60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("✅ Connected to MQTT broker successfully.")
            client.subscribe("kneader/commands/#")
            logger.info("📡 Subscribed to topic: kneader/commands/#")
        else:
            logger.error(f"❌ MQTT connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"📥 MQTT received: {payload}")
            # Schedule handling in event loop
            asyncio.run_coroutine_threadsafe(
                self.handle_command(payload),
                self.loop
            )
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")

    async def handle_command(self, payload):
        """
        Pass command to KneaderController and publish response.
        """
        try:
            # Reuse existing handler logic
            command = payload.get("command")
            response = await self.controller.hmi_command_dispatch(payload)
            topic = f"kneader/responses/{command}"
            self.client.publish(topic, json.dumps(response))
            logger.info(f"📤 Published response to {topic}")
        except Exception as e:
            err_msg = {"status": "error", "message": str(e)}
            self.client.publish("kneader/responses/error", json.dumps(err_msg))
            logger.error(f"Failed to process command: {e}")


async def main():
    controller = KneaderController()
    mqtt_bridge = MqttBridge(controller)

    # Start MQTT bridge
    mqtt_bridge.start()

    logger.info("🚀 KneaderController running with MQTT bridge...")

    # Keep the main event loop alive forever
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt: shutting down KneaderController.")
