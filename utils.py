import time
from pyboy import PyBoy
import pygame
import structlog
from datetime import datetime

# Configure structlog to write to a log file
log_filename = f"pokemon_ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure structlog processors
processors = [
    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.JSONRenderer(),
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

def setup_emulator(rom_path, speed, skip_frames, debug, unlimited_fps):
    """Initialize and configure the PyBoy emulator."""
    # Initialize PyBoy
    pyboy = PyBoy(rom_path, cgb=True)

    # Set options
    pyboy.set_emulation_speed(speed)  # 1 is normal speed, 0 is as fast as possible

    # Skip through the start screen
    pyboy.tick(skip_frames)

    # Initialize debug state
    debug_mode = debug
    unlimited_fps_mode = unlimited_fps
    if unlimited_fps_mode:
        pyboy.set_emulation_speed(0)

    pygame.init()

    return pyboy, debug_mode, unlimited_fps_mode

def process_agent_command(
    command, pyboy, rom_path, debug_mode, unlimited_fps_mode, command_history=None
):
    """Process a command from the agent and return updated state."""
    # Map of command strings to PyBoy button names
    valid_commands = ["up", "down", "left", "right", "a", "b", "start", "select"]

    # Add command to history if it exists
    if command_history is not None:
        command_history.append(command)

    logger.info("Processing agent command", command=command)

    # Split the command into parts
    parts = command.lower().strip().split()
    if not parts:
        logger.warning("Empty command received")
        return debug_mode, unlimited_fps_mode, False

    main_command = parts[0]

    # Handle button presses
    if main_command in valid_commands:
        pyboy.button(main_command, 5)
    elif main_command == "wait" and len(parts) > 1:
        try:
            seconds = float(parts[1])
            frames = int(seconds * 60)  # 60 frames per second
            for _ in range(frames):
                pyboy.tick()
        except ValueError:
            logger.error("Invalid wait duration", duration=parts[1])

    elif main_command == "sequence" and len(parts) > 1:
        # Execute a sequence of commands with delay between them
        sequence = parts[1:]
        for cmd in sequence:
            if cmd in valid_commands:
                pyboy.button(cmd, 5)
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
        except ValueError:
            logger.error("Invalid speed value", value=parts[1])

    elif main_command == "debug":
        if len(parts) > 1 and parts[1] in ["on", "off"]:
            debug_mode = parts[1] == "on"
        else:
            logger.error("Invalid debug option", option=parts[1])

    elif main_command == "screenshot":
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        screenshot_path = f"screenshot-{timestamp}.png"
        pyboy.screen.image.save(screenshot_path)

    elif main_command == "save":
        save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
        pyboy.save_state(save_path)

    elif main_command == "load":
        try:
            save_path = f"{rom_path.split('/')[-1].split('.')[0]}.state"
            pyboy.load_state(save_path)
        except:
            logger.error("No save state found or error loading state")

    else:
        logger.error("Unknown command", command=main_command)

    return debug_mode, unlimited_fps_mode, False
