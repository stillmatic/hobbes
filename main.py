import base64
import os
import queue
import re
import tempfile
import threading
import time
import traceback
from collections import deque

import fire
import pygame
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from controller import GameController
from utils import logger, process_agent_command, setup_emulator

# Initialize Rich console
console = Console()
load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

SYSTEM_PROMPT = (
    """You are Hobbes, a very intelligent but fun AI agent. You are currently playing Pokemon Blue on a Game Boy emulator. 

You are given a screenshot of the current state of the game and a description of the situation. You need to decide what to do next.

You can control the game with the following commands:
up, down, left, right: D-pad directions
a, b: A and B buttons
start, select: Start and Select buttons
wait [seconds]: Wait for the specified number of seconds.

You can also execute a sequence of commands with 0.5s delay between them.            
            
Return your response in the following format:

```
<thinking>
Your thoughts on the current state of the game and what to do next.
</thinking>
<commands>
The commands you want to execute. Put each command on a new line.
</commands>
```

Example:
<thinking>
I need to move two tiles up, and then make my next move.
</thinking>
<commands>
up
up
</commands>

Example 2:
<thinking>
[omitted for brevity]
</thinking>
<commands>
a
right 
right
wait 1
a
</commands>

You must follow the format exactly. Begin your response with <thinking>.

""",
)
def run_emulator_loop(pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode=True, headless=False):
    """Run the main emulator game loop with the refactored architecture."""
    # Initialize controller with model and view
    controller = GameController(
        pyboy=pyboy,
        rom_path=rom_path,
        system_prompt=SYSTEM_PROMPT,
        client=client,
        headless=headless
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
