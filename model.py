# model.py - Handles game state, AI interactions, and core logic
import base64
import re
import tempfile
import threading
import queue
import traceback
from collections import deque
from utils import logger

class GameModel:
    def __init__(self, system_prompt, client):
        self.conversation_history = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]
        self.client = client
        self.command_history = deque(maxlen=10)
        self.ai_command_queue = queue.Queue()
        self.waiting_for_ai = False
        self.most_recent_ai_thinking = ""
        self.most_recent_ai_commands = []
        self.debug_mode = False
        self.unlimited_fps_mode = False
        self.running = True
        self.ai_turn_counter = 0
        self.command_queue = queue.Queue()

    def get_screenshot(self, pyboy):
        """Capture the current game screen and convert to base64."""
        screenshot = pyboy.screen.image
        with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
            screenshot.save(temp_file.name)
            return base64.b64encode(
                open(temp_file.name, "rb").read()
            ).decode("utf-8")

    def add_user_message(self, base64_image):
        """Add a user message with screenshot to conversation history."""
        self.conversation_history.append(
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

    def call_ai_api(self):
        """Call the AI API with the current conversation history."""
        return self.client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "twitch.tv/memberoftechstaff",
                "X-Title": "Member of Technical Staff",
            },
            # model="openai/gpt-4o",
            model="google/gemini-2.0-flash-001",
            messages=self.conversation_history,
        )

    def parse_ai_response(self, ai_response):
        """Parse AI response for thinking and commands."""
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

        if commands_match:
            commands_text = commands_match.group(1).strip()
            commands = [cmd.strip() for cmd in commands_text.split("\n") if cmd.strip()]

        return thinking, commands

    def add_ai_response(self, ai_response):
        """Add AI response to conversation history."""
        self.conversation_history.append({"role": "assistant", "content": ai_response})

    def get_ai_response_async(self, pyboy, callback):
        """
        Get AI response for the current game state asynchronously.
        Uses a thread to avoid blocking the main game loop.
        """
        def ai_thread_func():
            try:
                # Capture current screen
                base64_image = self.get_screenshot(pyboy)

                # Add user message with screenshot
                self.add_user_message(base64_image)

                # Get AI response
                completion = self.call_ai_api()

                # Parse AI response
                ai_response = completion.choices[0].message.content
                logger.info("AI response", response=ai_response)

                # Add AI response to conversation history
                self.add_ai_response(ai_response)

                # Extract thinking and commands
                thinking, commands = self.parse_ai_response(ai_response)
                
                # Store for display purposes
                self.most_recent_ai_thinking = thinking if thinking else self.most_recent_ai_thinking
                self.most_recent_ai_commands = commands

                # Queue commands for execution
                if len(commands) > 1:
                    # Multiple commands - combine into a sequence
                    sequence_cmd = f"sequence {' '.join(commands)}"
                    self.ai_command_queue.put(sequence_cmd)
                elif commands:
                    # Single command - put directly in queue
                    self.ai_command_queue.put(commands[0])

                # Call the callback with the results
                callback(self.conversation_history, commands, thinking)

            except Exception as e:
                logger.error("Error getting AI response", error=str(e))
                logger.error("Stack trace", trace=traceback.format_exc())
                callback(self.conversation_history, [], "")

        # Start the AI processing in a separate thread
        ai_thread = threading.Thread(target=ai_thread_func)
        ai_thread.daemon = True
        ai_thread.start()

    def process_agent_command(self, command, pyboy, rom_path):
        """Process a game command from either user or AI."""
        # This would contain the logic from your existing process_agent_command function
        # For now, I'll just add a stub returning the three values that your original function returned
        
        # Add command to history
        self.command_history.append(command)
        
        # Placeholder for the actual command processing logic
        # In the actual implementation, this would execute the command on pyboy
        # and return updated debug_mode, unlimited_fps_mode, and quit_requested
        
        quit_requested = command.lower() == "quit"
        
        # Update debug_mode and unlimited_fps_mode based on commands
        if command.lower() == "debug":
            self.debug_mode = not self.debug_mode
        elif command.lower() == "unlimited_fps":
            self.unlimited_fps_mode = not self.unlimited_fps_mode
        
        return self.debug_mode, self.unlimited_fps_mode, quit_requested
