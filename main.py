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
""",
)


def get_ai_response_async(pyboy, conversation_history, callback):
    """
    Get AI response for the current game state asynchronously.
    Uses a thread to avoid blocking the main game loop.
    """

    def ai_thread_func():
        try:
            # Capture current screen
            screenshot = pyboy.screen.image
            with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
                screenshot.save(temp_file.name)
                base64_image = base64.b64encode(
                    open(temp_file.name, "rb").read()
                ).decode("utf-8")

            # Add user message with screenshot to conversation history
            conversation_history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "This is the current state of the game, what should the next move be?",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            )

            # Get AI response
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "twitch.tv/memberoftechstaff",
                    "X-Title": "Member of Technical Staff",
                },
                # model="openai/gpt-4o",
                model="google/gemini-2.0-flash-001",
                messages=conversation_history,
            )

            # Parse AI response
            ai_response = completion.choices[0].message.content
            logger.info("AI response", response=ai_response)

            # Add AI response to conversation history
            conversation_history.append({"role": "assistant", "content": ai_response})

            # Extract thinking and commands
            thinking = ""
            commands = []

            thinking_match = re.search(
                r"<thinking>(.*?)</thinking>", ai_response, re.DOTALL
            )
            commands_match = re.search(
                r"<commands>(.*?)</commands>", ai_response, re.DOTALL
            )

            if thinking_match:
                thinking = thinking_match.group(1).strip()
                console.print(
                    Panel(
                        thinking, title="AI Thinking", border_style="blue", expand=False
                    )
                )

            if commands_match:
                commands_text = commands_match.group(1).strip()
                commands = [
                    cmd.strip() for cmd in commands_text.split("\n") if cmd.strip()
                ]

                # Create a table for commands
                table = Table(title="AI Commands")
                table.add_column("Command", style="cyan")
                for cmd in commands:
                    table.add_row(cmd)
                console.print(table)

            # Call the callback with the results
            callback(conversation_history, commands)

        except Exception as e:
            logger.error("Error getting AI response", error=str(e))
            logger.error("Stack trace", trace=traceback.format_exc())
            callback(conversation_history, [])

    # Start the AI processing in a separate thread
    ai_thread = threading.Thread(target=ai_thread_func)
    ai_thread.daemon = True
    ai_thread.start()


def run_emulator_loop(
    pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode=True, headless=False
):
    """Run the main emulator game loop."""
    # Agent-controlled loop with non-blocking AI
    command_queue = queue.Queue()
    ai_command_queue = queue.Queue()  # Queue for AI commands to be executed

    # Create a deque to store recent commands (max size 10)
    command_history = deque(maxlen=10)

    # Store the most recent AI thinking and commands
    most_recent_ai_thinking = ""
    most_recent_ai_commands = []

    # Flag to track if we're waiting for AI response
    waiting_for_ai = False

    def input_thread_func():
        while True:
            try:
                command = input()  # No prompt here, we'll use Rich for that
                command_queue.put(command)
            except EOFError:
                break

    # Start input thread (only if not in headless mode)
    if not headless:
        input_thread = threading.Thread(target=input_thread_func, daemon=True)
        input_thread.start()
        # Display an input prompt with Rich
        console.print("[bold cyan]Enter command: ", end="")

    # AI response callback
    def ai_response_callback(updated_history, commands):
        nonlocal waiting_for_ai
        nonlocal conversation_history
        nonlocal most_recent_ai_thinking
        nonlocal most_recent_ai_commands

        conversation_history = updated_history

        # Store the most recent AI response for display
        if len(conversation_history) >= 2:
            last_ai_response = conversation_history[-1]["content"]

            # Extract thinking
            thinking_match = re.search(
                r"<thinking>(.*?)</thinking>", last_ai_response, re.DOTALL
            )
            if thinking_match:
                most_recent_ai_thinking = thinking_match.group(1).strip()

            # Store commands
            most_recent_ai_commands = commands

        # Put commands in the queue to be executed
        if len(commands) > 1:
            # Multiple commands - combine into a sequence
            sequence_cmd = f"sequence {' '.join(commands)}"
            ai_command_queue.put(sequence_cmd)
        elif commands:
            # Single command - put directly in queue
            ai_command_queue.put(commands[0])

        # No longer waiting for AI
        waiting_for_ai = False

    running = True
    ai_turn_counter = 0  # Counter to control when to ask the AI

    # Initialize conversation history
    conversation_history = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    # Create a layout for the live display
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )

    # Split the main section to accommodate AI thinking and command history
    layout["main"].split_row(
        Layout(name="command_history", ratio=1), Layout(name="ai_thinking", ratio=1)
    )

    # Set initial content
    layout["header"].update(
        Panel("[bold green]Pokemon Blue - AI Emulator", style="green")
    )
    layout["command_history"].update(
        Panel("Game running...", title="Command History")
    )
    layout["ai_thinking"].update(Panel("No AI thinking yet", title="AI Thinking"))
    layout["footer"].update(
        Panel(
            "[bold cyan]Enter 'ai' to trigger AI move or enter commands directly",
            style="cyan",
        )
    )

    # Add a spinner for when waiting for AI
    ai_spinner = None

    with Live(layout, refresh_per_second=10, screen=False) as live:
        while running:
            # Update display
            if waiting_for_ai:
                # Show spinner when waiting for AI
                if ai_spinner is None:
                    ai_spinner = Panel(
                        "[bold yellow]Waiting for AI to respond...",
                        title="AI Status",
                        border_style="yellow",
                    )
                layout["command_history"].update(ai_spinner)

                # Keep showing previous AI thinking if available
                if most_recent_ai_thinking:
                    ai_thinking_panel = Panel(
                        Text(
                            most_recent_ai_thinking, style="blue", overflow="fold"
                        ),
                        title="Last AI Thinking",
                        border_style="blue",
                    )
                    layout["ai_thinking"].update(ai_thinking_panel)
                else:
                    layout["ai_thinking"].update(
                        Panel("No AI thinking yet", title="AI Thinking")
                    )
            else:
                ai_spinner = None

                # Show command history
                status_text = f"[bold green]Game Status:[/bold green]\n"
                status_text += f"Debug: {'ON' if debug_mode else 'OFF'}\n"
                status_text += (
                    f"Unlimited FPS: {'ON' if unlimited_fps_mode else 'OFF'}\n\n"
                )

                # Display recent command history
                if command_history:
                    status_text += "[bold blue]Recent Commands:[/bold blue]\n"
                    for i, cmd in enumerate(reversed(command_history), 1):
                        if i > 10:  # Safety check for maxlen
                            break
                        status_text += f"{i}. [cyan]{cmd}[/cyan]\n"
                else:
                    status_text += "[italic]No commands executed yet[/italic]\n"

                # Display last AI commands if available
                if most_recent_ai_commands:
                    status_text += (
                        "\n[bold magenta]Last AI Commands:[/bold magenta]\n"
                    )
                    for i, cmd in enumerate(most_recent_ai_commands, 1):
                        status_text += f"{i}. [magenta]{cmd}[/magenta]\n"

                layout["command_history"].update(
                    Panel(status_text, title="Command History")
                )

                # Show AI thinking
                if most_recent_ai_thinking:
                    # Truncate thinking if too long for display
                    ai_thinking_text = most_recent_ai_thinking
                    ai_thinking_panel = Panel(
                        Text(ai_thinking_text, style="blue", overflow="fold"),
                        title="Last AI Thinking",
                        border_style="blue",
                    )
                    layout["ai_thinking"].update(ai_thinking_panel)
                else:
                    layout["ai_thinking"].update(
                        Panel("No AI thinking yet", title="AI Thinking")
                    )

            # In headless mode, automatically trigger AI every few seconds if not already waiting
            if (
                headless
                and not waiting_for_ai
                and (ai_turn_counter == 0 or ai_turn_counter >= 120)
            ):  # Every ~2 seconds (120 frames)
                try:
                    console.print(
                        "\n[bold blue]Automatically triggering AI in headless mode..."
                    )
                    # Get AI response asynchronously
                    waiting_for_ai = True
                    get_ai_response_async(
                        pyboy, conversation_history, ai_response_callback
                    )

                    # Reset counter
                    ai_turn_counter = 0
                except Exception as e:
                    console.print(f"[bold red]Error triggering AI: {str(e)}")
                    console.print("[bold red]Stack trace:")
                    console.print(traceback.format_exc(), style="red")
                    waiting_for_ai = False
                    ai_turn_counter = 0

            # Process any AI commands in the queue
            try:
                while not ai_command_queue.empty():
                    cmd = ai_command_queue.get_nowait()
                    console.print(f"[cyan]Executing AI command: {cmd}")
                    debug_mode, unlimited_fps_mode, quit_requested = (
                        process_agent_command(
                            cmd,
                            pyboy,
                            rom_path,
                            debug_mode,
                            unlimited_fps_mode,
                            command_history,
                        )
                    )
                    if quit_requested:
                        running = False
                        break
                    # Add a small delay between commands
                    time.sleep(0.2)
            except queue.Empty:
                pass

            # Process any user commands in the queue (for non-headless mode)
            if not headless:
                try:
                    while not command_queue.empty():
                        command = command_queue.get_nowait()

                        # Special command to trigger AI if not already waiting
                        if command.lower() == "ai" and not waiting_for_ai:
                            try:
                                console.print(
                                    "[bold blue]Triggering AI for next move..."
                                )
                                # Get AI response asynchronously
                                waiting_for_ai = True
                                get_ai_response_async(
                                    pyboy,
                                    conversation_history,
                                    ai_response_callback,
                                )
                            except Exception as e:
                                console.print(
                                    f"[bold red]Error triggering AI: {str(e)}"
                                )
                                console.print("[bold red]Stack trace:")
                                console.print(traceback.format_exc(), style="red")
                                waiting_for_ai = False
                        else:
                            debug_mode, unlimited_fps_mode, quit_requested = (
                                process_agent_command(
                                    command,
                                    pyboy,
                                    rom_path,
                                    debug_mode,
                                    unlimited_fps_mode,
                                    command_history,
                                )
                            )
                            if quit_requested:
                                running = False
                                break

                        # Update the prompt after processing a command
                        console.print("[bold cyan]Enter command: ", end="")
                except queue.Empty:
                    pass

            # Process window events (for closing the window)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Tick the emulator (advance one frame)
            running = running and pyboy.tick()

            # Increment counter in headless mode
            if headless:
                ai_turn_counter += 1


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
