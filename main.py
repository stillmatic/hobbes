from pyboy import PyBoy
import pygame
import time
import fire
import threading
import queue
from openai import OpenAI
from dotenv import load_dotenv
import os
import base64
from io import BytesIO
import re


load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)


def setup_emulator(rom_path, speed, skip_frames, debug, unlimited_fps):
    """Initialize and configure the PyBoy emulator."""
    # Initialize PyBoy
    pyboy = PyBoy(rom_path)

    # Set options
    pyboy.set_emulation_speed(speed)  # 1 is normal speed, 0 is as fast as possible

    # Skip through the start screen
    print(f"Skipping through start screen ({skip_frames} frames)...")
    pyboy.tick(skip_frames)

    print(f"\n{rom_path} is running!")
    print("Available commands for the agent:")
    print("  up, down, left, right: D-pad directions")
    print("  a, b: A and B buttons")
    print("  start, select: Start and Select buttons")
    print("  screenshot: Save a screenshot")
    print("  save: Save game state")
    print("  load: Load game state")
    print("  speed [0-4]: Set emulation speed (0=unlimited)")
    print("  debug [on/off]: Toggle debug information")
    print("  quit: Exit the emulator")
    print("  sequence [commands]: Execute a sequence of commands with 0.5s delay")

    # Initialize debug state
    debug_mode = debug
    unlimited_fps_mode = unlimited_fps
    if unlimited_fps_mode:
        pyboy.set_emulation_speed(0)
        print("Unlimited FPS: ON")

    if debug_mode:
        print("Debug mode: ON")

    pygame.init()

    return pyboy, debug_mode, unlimited_fps_mode


def process_agent_command(command, pyboy, rom_path, debug_mode, unlimited_fps_mode):
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

    # Split the command into parts
    parts = command.lower().strip().split()
    if not parts:
        print("Empty command received")
        return debug_mode, unlimited_fps_mode, False

    main_command = parts[0]

    # Handle button presses
    if main_command in button_commands:
        button_name = button_commands[main_command]
        pyboy.button(button_name, "press")
        time.sleep(0.1)  # Hold for a short time
        pyboy.button(button_name, "release")
        print(f"Button pressed and released: {button_name}")

    elif main_command == "sequence" and len(parts) > 1:
        # Execute a sequence of commands with delay between them
        sequence = parts[1:]
        print(f"Executing sequence: {' '.join(sequence)}")
        for cmd in sequence:
            if cmd in button_commands:
                button_name = button_commands[cmd]
                pyboy.button(button_name, "press")
                time.sleep(0.1)
                pyboy.button(button_name, "release")
                print(f"Button pressed and released: {button_name}")
                time.sleep(0.5)  # Delay between commands
            else:
                print(f"Unknown command in sequence: {cmd}")

    else:
        print(f"Unknown command: {main_command}")

    return debug_mode, unlimited_fps_mode, False


def run_emulator_loop(pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode=True):
    """Run the main emulator game loop."""
    if not agent_mode:
        # Original human-controlled loop
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
                            print(f"Button pressed: {button_name}")

                    # Special emulator functions
                    elif event.key == pygame.K_ESCAPE:
                        running = False

                    # Unlimited FPS toggle
                    elif event.key == pygame.K_SPACE:
                        unlimited_fps_mode = not unlimited_fps_mode
                        speed = 0 if unlimited_fps_mode else 1  # 0 = unlimited
                        pyboy.set_emulation_speed(speed)
                        print(f"Unlimited FPS: {'ON' if unlimited_fps_mode else 'OFF'}")

                    # Debug mode toggle
                    elif event.key == pygame.K_d:
                        debug_mode = not debug_mode
                        print(f"Debug mode: {'ON' if debug_mode else 'OFF'}")

                    # Screenshot
                    elif event.key == pygame.K_o:
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        screenshot_path = f"screenshot-{timestamp}.png"
                        pyboy.screen.image.save(screenshot_path)
                        print(f"Screenshot saved as {screenshot_path}")

                    # Save state
                    elif event.key == pygame.K_z:
                        save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
                        pyboy.save_state(save_path)
                        print(f"Game state saved to {save_path}")

                    # Load state
                    elif event.key == pygame.K_x:
                        try:
                            save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
                            pyboy.load_state(save_path)
                            print(f"Game state loaded from {save_path}")
                        except:
                            print("No save state found or error loading state")

                    # Memory navigation (J/K)
                    elif event.key == pygame.K_j:
                        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                            print("Memory window +0x1000")
                        else:
                            print("Memory window +0x100")

                    elif event.key == pygame.K_k:
                        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                            print("Memory window -0x1000")
                        else:
                            print("Memory window -0x100")

                # Handle key release events
                elif event.type == pygame.KEYUP:
                    if event.key in button_map:
                        button_name = button_map[event.key]
                        pyboy.button(button_name, "release")
                        if debug_mode:
                            print(f"Button released: {button_name}")

            # Tick the emulator (advance one frame)
            running = pyboy.tick()

            # Display debug info if enabled
            if debug_mode and pyboy.frame_count % 60 == 0:  # Update about once a second
                print(f"Frame count: {pyboy.frame_count}, FPS: {pyboy.fps}")
    else:
        # Agent-controlled loop
        command_queue = queue.Queue()

        def input_thread_func():
            while True:
                try:
                    command = input("Enter command: ")
                    command_queue.put(command)
                except EOFError:
                    break

        # Start input thread
        input_thread = threading.Thread(target=input_thread_func, daemon=True)
        input_thread.start()

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
                a
                </commands>
                """
            }
        ]
        
        while running:
            # Process any commands in the queue
            try:
                while not command_queue.empty():
                    command = command_queue.get_nowait()
                    
                    # Special command to trigger AI
                    if command.lower() == "ai":
                        # Capture current screen
                        screenshot = pyboy.screen.image
                        buffered = BytesIO()
                        screenshot.save(buffered, format="PNG")
                        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        
                        # Add user message with screenshot to conversation history
                        conversation_history.append({
                            "role": "user",
                            "content": "This is the current state of the game, what should the next move be?",
                        })
                        
                        conversation_history.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "low"},
                        })
                        
                        # Get AI response
                        try:
                            completion = client.chat.completions.create(
                                extra_headers={
                                    "HTTP-Referer": "twitch.tv/memberoftechstaff", 
                                    "X-Title": "Member of Technical Staff",
                                },
                                model="openai/gpt-4o",
                                messages=conversation_history,
                            )
                            
                            # Parse AI response
                            ai_response = completion.choices[0].message.content
                            
                            # Add AI response to conversation history
                            conversation_history.append({
                                "role": "assistant",
                                "content": ai_response
                            })
                            
                            # Extract thinking and commands
                            thinking = ""
                            commands = []
                            
                            thinking_match = re.search(r'<thinking>(.*?)</thinking>', ai_response, re.DOTALL)
                            commands_match = re.search(r'<commands>(.*?)</commands>', ai_response, re.DOTALL)
                            
                            if thinking_match:
                                thinking = thinking_match.group(1).strip()
                                print("\nAI Thinking:")
                                print(thinking)
                            
                            if commands_match:
                                commands_text = commands_match.group(1).strip()
                                commands = [cmd.strip() for cmd in commands_text.split('\n') if cmd.strip()]
                                print("\nAI Commands:")
                                for cmd in commands:
                                    print(f"- {cmd}")
                                
                                # Execute each command
                                for cmd in commands:
                                    debug_mode, unlimited_fps_mode, quit_requested = process_agent_command(
                                        cmd, pyboy, rom_path, debug_mode, unlimited_fps_mode
                                    )
                                    if quit_requested:
                                        running = False
                                        break
                                    # Add a small delay between commands
                                    time.sleep(0.2)
                            
                        except Exception as e:
                            print(f"Error getting AI response: {e}")
                    else:
                        debug_mode, unlimited_fps_mode, quit_requested = (
                            process_agent_command(
                                command, pyboy, rom_path, debug_mode, unlimited_fps_mode
                            )
                        )
                        if quit_requested:
                            running = False
                            break
            except queue.Empty:
                pass

            # Process window events (for closing the window)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Tick the emulator (advance one frame)
            running = running and pyboy.tick()

            # Display debug info if enabled
            if debug_mode and pyboy.frame_count % 60 == 0:  # Update about once a second
                print(f"Frame count: {pyboy.frame_count}, FPS: {pyboy.fps}")
                # Take a screenshot every second in debug mode to help the agent
                if pyboy.frame_count > 0:
                    screenshot_path = "current_frame.png"
                    pyboy.screen.image.save(screenshot_path)


def main(
    rom_path="roms/pokemon_blue.gb",
    speed=1,
    skip_frames=2000,
    debug=False,
    unlimited_fps=False,
    agent_mode=True,
):
    # Setup the emulator
    pyboy, debug_mode, unlimited_fps_mode = setup_emulator(
        rom_path, speed, skip_frames, debug, unlimited_fps
    )

    try:
        # Run the main game loop
        run_emulator_loop(pyboy, rom_path, debug_mode, unlimited_fps_mode, agent_mode)
    finally:
        # Clean up
        pyboy.stop()
        print("Emulator stopped.")


if __name__ == "__main__":
    fire.Fire(main)
