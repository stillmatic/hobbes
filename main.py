import os
import traceback

import fire
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel

from controller import GameController
from utils import logger, setup_emulator

# Initialize Rich console
console = Console()
load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


def run_emulator_loop(
    pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode=True, headless=False
):
    """Run the main emulator game loop with the refactored architecture."""
    # Initialize controller with model and view
    controller = GameController(
        pyboy=pyboy,
        rom_path=rom_path,
        client=client,
        headless=headless,
    )

    # Set initial state
    controller.model.debug_mode = debug_mode
    controller.model.unlimited_fps_mode = unlimited_fps_mode

    # Run the game loop
    controller.run()


def main(
    rom_path="roms/pokemon_blue.gb",
    speed=1,
    skip_frames=2000,
    debug=False,
    unlimited_fps=False,
    agent_mode=True,
    headless=False,
):
    # Print a welcome banner
    console.print(
        Panel.fit(
            "[bold cyan]Pokemon Blue - AI Emulator[/bold cyan]\n"
            "[green]A smart Game Boy emulator that can play itself![/green]",
            title="Welcome",
            border_style="green",
        )
    )

    # Setup the emulator
    pyboy, debug_mode, unlimited_fps_mode = setup_emulator(
        rom_path, speed, skip_frames, debug, unlimited_fps
    )

    try:
        # Run the main game loop
        run_emulator_loop(
            pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode, headless
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error("Error in main loop", error=str(e))
        logger.error("Stack trace", trace=traceback.format_exc())
    finally:
        # Clean up
        pyboy.stop()
        logger.info("Emulator stopped. Goodbye!")


if __name__ == "__main__":
    fire.Fire(main)
