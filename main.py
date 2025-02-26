import base64
from datetime import datetime
import os
import queue
import re
import sys
import tempfile
import threading
import time
import traceback
from collections import deque

import fire
import pygame
import structlog
from dotenv import load_dotenv
from openai import OpenAI
from pyboy import PyBoy
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Initialize Rich console
console = Console()

logger = structlog.get_logger()

# Configure structlog to write to a log file
log_filename = f"pokemon_ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure structlog processors
processors = [
    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
    structlog.processors.StackInfoRenderer(),
    structlog.dev.ConsoleRenderer()
    if "--console-log" in sys.argv
    else structlog.processors.JSONRenderer(),
]

# Create a file handler
log_file = open(log_filename, "w", encoding="utf-8")

# Set up structlog to write to the file
structlog.configure(
    processors=processors,
    logger_factory=structlog.WriteLoggerFactory(file=log_file),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
logger.info("Starting Pokemon AI emulator", log_file=log_filename)

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


def setup_emulator(rom_path, speed, skip_frames, debug, unlimited_fps):
    """Initialize and configure the PyBoy emulator."""
    # Initialize PyBoy
    pyboy = PyBoy(rom_path, cgb=True)

    # Set options
    pyboy.set_emulation_speed(speed)  # 1 is normal speed, 0 is as fast as possible

    # Skip through the start screen
    with console.status(
        f"[bold green]Skipping through start screen ({skip_frames} frames)...",
        spinner="dots",
    ):
        pyboy.tick(skip_frames)

    console.print(Panel(f"[bold green]{rom_path} is running!", title="Game Started"))

    # Create a table for commands
    table = Table(title="Available Commands")
    table.add_column("Command", style="cyan")
    table.add_column("Description", style="green")

    table.add_row("up, down, left, right", "D-pad directions")
    table.add_row("a, b", "A and B buttons")
    table.add_row("start, select", "Start and Select buttons")
    table.add_row("screenshot", "Save a screenshot")
    table.add_row("save", "Save game state")
    table.add_row("load", "Load game state")
    table.add_row("speed [0-4]", "Set emulation speed (0=unlimited)")
    table.add_row("debug [on/off]", "Toggle debug information")
    table.add_row("quit", "Exit the emulator")
    table.add_row(
        "sequence [commands]", "Execute a sequence of commands with 0.5s delay"
    )
    table.add_row("ai", "Trigger AI to make a move")

    console.print(table)

    # Initialize debug state
    debug_mode = debug
    unlimited_fps_mode = unlimited_fps
    if unlimited_fps_mode:
        pyboy.set_emulation_speed(0)
        console.print("[bold yellow]Unlimited FPS: ON")

    if debug_mode:
        console.print("[bold yellow]Debug mode: ON")

    pygame.init()

    return pyboy, debug_mode, unlimited_fps_mode


def process_agent_command(
    command, pyboy, rom_path, debug_mode, unlimited_fps_mode, command_history=None
):
    """Process a command from the agent and return updated state."""
    # Map of command strings to PyBoy button names
    button_commands = {
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "a": "a",
        "b": "b",
        "start": "start",
        "select": "select",
    }

    # Add command to history if it exists
    if command_history is not None:
        command_history.append(command)

    logger.info("Processing agent command", command=command)

    # Split the command into parts
    parts = command.lower().strip().split()
    if not parts:
        console.print("[yellow]Empty command received")
        return debug_mode, unlimited_fps_mode, False

    main_command = parts[0]

    # Handle button presses
    if main_command in button_commands:
        button_name = button_commands[main_command]
        pyboy.button(button_name, 5)
        logger.info("Button pressed and released", button_name=button_name)
    elif main_command == "wait" and len(parts) > 1:
        try:
            seconds = float(parts[1])
            frames = int(seconds * 60)  # 60 frames per second
            with console.status(
                f"[bold green]Waiting for {seconds} seconds ({frames} frames)...",
                spinner="dots",
            ):
                for _ in range(frames):
                    pyboy.tick()
            logger.info("Wait completed")
        except ValueError:
            logger.error("Invalid wait duration", duration=parts[1])

    elif main_command == "sequence" and len(parts) > 1:
        # Execute a sequence of commands with delay between them
        sequence = parts[1:]
        logger.info("Executing sequence", sequence=" ".join(sequence))
        for cmd in sequence:
            if cmd in button_commands:
                button_name = button_commands[cmd]
                pyboy.button(button_name, 5)
                logger.info("Button pressed and released", button_name=button_name)
                time.sleep(0.5)  # Delay between commands
            else:
                logger.error("Unknown command in sequence", command=cmd)

    elif main_command == "quit":
        logger.info("Quitting emulator")
        return debug_mode, unlimited_fps_mode, True

    elif main_command == "speed" and len(parts) > 1:
        try:
            speed = int(parts[1])
            pyboy.set_emulation_speed(speed)
            logger.info("Emulation speed set", speed=speed)
        except ValueError:
            logger.error("Invalid speed value", value=parts[1])

    elif main_command == "debug":
        if len(parts) > 1 and parts[1] in ["on", "off"]:
            debug_mode = parts[1] == "on"
            logger.info("Debug mode set", mode=debug_mode)
        else:
            logger.error("Invalid debug option", option=parts[1])

    elif main_command == "screenshot":
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        screenshot_path = f"screenshot-{timestamp}.png"
        pyboy.screen.image.save(screenshot_path)
        logger.info("Screenshot saved", path=screenshot_path)

    elif main_command == "save":
        save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
        pyboy.save_state(save_path)
        logger.info("Game state saved", path=save_path)

    elif main_command == "load":
        try:
            save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
            pyboy.load_state(save_path)
            logger.info("Game state loaded", path=save_path)
        except:
            logger.error("No save state found or error loading state")

    else:
        logger.error("Unknown command", command=main_command)

    return debug_mode, unlimited_fps_mode, False


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
    if not agent_mode:
        # Human-controlled loop with Rich UI
        # Define mapping from pygame keys to PyBoy button names
        button_map = {
            pygame.K_UP: "up",
            pygame.K_DOWN: "down",
            pygame.K_LEFT: "left",
            pygame.K_RIGHT: "right",
            pygame.K_z: "a",
            pygame.K_x: "b",
            pygame.K_RETURN: "start",
            pygame.K_BACKSPACE: "select",
        }

        # Main game loop
        running = True
        while running:
            # Process input events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                # Handle key press events
                elif event.type == pygame.KEYDOWN:
                    # Check for Game Boy buttons
                    if event.key in button_map:
                        button_name = button_map[event.key]
                        pyboy.button(button_name, "press")
                        if debug_mode:
                            console.print(f"[cyan]Button pressed: {button_name}")

                    # Special emulator functions
                    elif event.key == pygame.K_ESCAPE:
                        running = False

                    # Unlimited FPS toggle
                    elif event.key == pygame.K_SPACE:
                        unlimited_fps_mode = not unlimited_fps_mode
                        speed = 0 if unlimited_fps_mode else 1  # 0 = unlimited
                        pyboy.set_emulation_speed(speed)
                        console.print(
                            f"[yellow]Unlimited FPS: {'ON' if unlimited_fps_mode else 'OFF'}"
                        )

                    # Debug mode toggle
                    elif event.key == pygame.K_d:
                        debug_mode = not debug_mode
                        console.print(
                            f"[yellow]Debug mode: {'ON' if debug_mode else 'OFF'}"
                        )

                    # Screenshot
                    elif event.key == pygame.K_p:
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        screenshot_path = f"screenshot-{timestamp}.png"
                        pyboy.screen.image.save(screenshot_path)
                        console.print(f"[green]Screenshot saved as {screenshot_path}")

                    # Save state
                    elif event.key == pygame.K_s:
                        save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
                        pyboy.save_state(save_path)
                        console.print(f"[green]Game state saved to {save_path}")

                    # Load state
                    elif event.key == pygame.K_l:
                        try:
                            save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
                            pyboy.load_state(save_path)
                            console.print(f"[green]Game state loaded from {save_path}")
                        except:
                            console.print(
                                "[red]No save state found or error loading state"
                            )

                # Handle key release events
                elif event.type == pygame.KEYUP:
                    if event.key in button_map:
                        button_name = button_map[event.key]
                        pyboy.button(button_name, "release")
                        if debug_mode:
                            console.print(f"[cyan]Button released: {button_name}")

            # Tick the emulator (advance one frame)
            running = pyboy.tick()
    else:
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
                "content": """You are Hobbes, a very intelligent but fun AI agent. You are currently playing Pokemon Blue on a Game Boy emulator. 
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
