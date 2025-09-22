# main.py
import asyncio
import logging

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


async def main():
    controller = KneaderController()
    try:
        await controller.run()
    except asyncio.CancelledError:
        logger.info("Controller task cancelled.")
    except Exception as e:
        logger.error(f"Controller exited with error: {e}")
    finally:
        logger.info("KneaderController shutting down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt: shutting down KneaderController.")
