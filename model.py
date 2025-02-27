# model.py - Handles game state, AI interactions, and core logic
import base64
import json
import tempfile
import threading
import queue
import time
import traceback
from collections import deque

import pygame
from utils import logger



SYSTEM_PROMPT = """You are Hobbes, a very intelligent and fun AI agent playing Pokémon Blue. 
Your goal is to progress through the game by defeating gym leaders, building a strong Pokémon team, and eventually becoming the Pokémon League Champion.

Important game mechanics to remember:
- Pokémon have types that determine strengths and weaknesses
- Your Pokémon need to be healed at Pokémon Centers when their HP is low
- You need to catch wild Pokémon to build your team (use Pokéballs from PokéMarts)
- Gym battles require strategy based on type advantages

You are given a screenshot of the current state of the game, a plan you and your big brother have made, and your recent history. You need to decide what to do next.

---

You have a few tools at your disposal:

- `notes`: You can interact with your knowledge base. Your knowledge base is a collection of notes and information that you have gathered from the game. You can list the names of notes you have, add to a note, edit a note, or delete a note.
- `input`: You can interact with the game, by pressing buttons on the Game Boy. You may use D-pad directions (up, down, left, right), A and B buttons, Start and Select buttons.
- `bro`: You can ask your big brother for help. Your big brother is a very smart AI that doesn't have access to the game or images, but can reason over your notes and provide you with advice or a plan.

# Example 1: Using the 'notes' tool to add information to the knowledge base
{
  "role": "assistant",
  "content": "I can see we're at the beginning of the game. Let me make a note of our starter Pokémon.",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "notes",
        "arguments": "{\"action\":\"add\",\"note_name\":\"My Team\",\"content\":\"Starter: Bulbasaur, Level 5\\nType: Grass/Poison\\nMoves: Tackle, Growl\"}"
      }
    }
  ]
}

# Example 2: Using the 'input' tool to press buttons
{
  "role": "assistant",
  "content": "I need to move our character to the Pokémon Center to heal.",
  "tool_calls": [
    {
      "id": "call_def456",
      "type": "function",
      "function": {
        "name": "input",
        "arguments": "{\"commands\":[\"up\", \"up\", \"up\", \"right\", \"right\", \"a\"]}"
      }
    }
  ]
}

# Example 3: Using the 'bro' tool to ask for advice
{
  "role": "assistant",
  "content": "I'm not sure which Pokémon would be best against the first gym. Let me ask for advice.",
  "tool_calls": [
    {
      "id": "call_ghi789",
      "type": "function",
      "function": {
        "name": "bro",
        "arguments": "{\"question\":\"What Pokémon types are effective against Brock's Rock-type Pokémon in the first gym?\"}"
      }
    }
  ]
}
---

You're enthusiastic and enjoy the adventure! Share your excitement when you catch new Pokémon or win battles.

Keep well-organized notes about:
- Your current Pokémon team, their levels, moves, and types
- Your current location and objective
- Important NPCs and their information
- Items in your inventory
- Gyms defeated and badges collected

Update these notes after significant changes.

When deciding your next action, consider:
1. OBSERVE: What's on screen? What menu, area, or battle are you in?
2. ANALYZE: What are your current goals? What's your team status?
3. PLAN: What sequence of actions will help you progress?
4. ACT: Execute your plan with precise button commands.

Balance immediate needs (healing Pokémon, winning current battle) with long-term goals (completing the game, evolving Pokémon).
"""

button_map = ["up", "down", "left", "right", "a", "b", "start", "select"]

class GameModel:
    def __init__(self, client):
        self.conversation_history = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
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

        # Knowledge base for notes function
        self.knowledge_base = {}

    def get_screenshot(self, pyboy):
        """Capture the current game screen and convert to base64."""
        screenshot = pyboy.screen.image
        with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
            screenshot.save(temp_file.name)
            return base64.b64encode(open(temp_file.name, "rb").read()).decode("utf-8")

    def add_user_message(self, base64_image):
        """Add a user message with screenshot to conversation history."""
        self.conversation_history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "This is the current state of the game. Think carefully about what to do next and issue a tool call to move on.",
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

    def call_ai_api(self, remind_format=False):
        """Call the AI API with the current conversation history."""

        conversation_history = self.conversation_history
        if remind_format:
            conversation_history[-1]["content"][0]["text"] += "Remember to format your response using the tool calling functionality. You MUST use the tool calling functionality."

        return self.client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "twitch.tv/memberoftechstaff",
                "X-Title": "Member of Technical Staff",
            },
            model="openai/gpt-4o",
            # model="google/gemini-2.0-flash-001",
            messages=self.conversation_history,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "notes",
                        "description": "Manage your knowledge base by listing, adding, editing, or deleting notes",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["list", "add", "edit", "delete"],
                                    "description": "The action to perform on your notes",
                                },
                                "note_name": {
                                    "type": "string",
                                    "description": "The name of the note to add, edit, or delete",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The content to add or edit in the note (required for add/edit actions)",
                                },
                            },
                            "required": ["action"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "input",
                        "description": "Input a command or series of commands to be executed by the Game Boy emulator",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "commands": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "up",
                                            "down",
                                            "left",
                                            "right",
                                            "a",
                                            "b",
                                            "start",
                                            "select",
                                        ],
                                    },
                                    "description": "A series of Game Boy button commands to execute",
                                }
                            },
                            "required": ["commands"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "bro",
                        "description": "Ask your big brother AI for help with the game",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                    "description": "The question or request for advice you want to ask your big brother",
                                }
                            },
                            "required": ["question"],
                        },
                    },
                },
            ],
        )

    def parse_ai_response(self, completion):
        """Parse AI response for thinking, commands, and tool calls."""
        # Get the response message
        message = completion.choices[0].message

        logger.info("AI response", content=message.content)

        thinking = message.content
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = message.tool_calls
            logger.info("Parsed tools", tool_calls=tool_calls)
        else:
            raise ValueError("No tool calls found in AI response")

        return thinking, tool_calls

    def add_ai_response(self, message):
        """Add AI response to conversation history."""
        self.conversation_history.append(
            {
                "role": "assistant",
                "content": message.content,
                **(
                    {"tool_calls": message.tool_calls}
                    if hasattr(message, "tool_calls") and message.tool_calls
                    else {}
                ),
            }
        )

    def execute_tool_call(self, tool_call, pyboy=None):
        """Execute a tool call and return the result."""
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        result = None

        if function_name == "notes":
            # Handle notes function
            action = arguments.get("action")
            note_name = arguments.get("note_name", "")
            content = arguments.get("content", "")

            if action == "list":
                result = {"notes": list(self.knowledge_base.keys())}
                if note_name:
                    result = {
                        "note": self.knowledge_base.get(note_name, "Note not found")
                    }
            elif action == "add":
                self.knowledge_base[note_name] = content
                result = {"status": "Note added successfully"}
            elif action == "edit":
                if note_name in self.knowledge_base:
                    self.knowledge_base[note_name] = content
                    result = {"status": "Note edited successfully"}
                else:
                    result = {"status": "Note not found"}
            elif action == "delete":
                if note_name in self.knowledge_base:
                    del self.knowledge_base[note_name]
                    result = {"status": "Note deleted successfully"}
                else:
                    result = {"status": "Note not found"}

        elif function_name == "input" and pyboy:
            # Handle input function
            commands = arguments.get("commands", [])
            logger.info(f"Executing input commands: {commands}")

            executed_commands = []
            for btn in commands:
                if btn in button_map:
                    # Press the button
                    logger.info("Pressing button", button=btn)
                    pyboy.button(btn, 5)
                    executed_commands.append(btn)
                # Wait 20 ticks or 1/3 seconds
                pyboy.tick(20)

            result = {"status": "Commands executed", "executed": executed_commands}

            # Store the executed commands for the UI
            self.most_recent_ai_commands.extend(executed_commands)

        elif function_name == "bro":
            # Handle bro function (asking big brother AI for help)
            question = arguments.get("question", "")

            # Here you would implement the call to the big brother AI
            # For now, we'll return a placeholder response
            result = {
                "advice": f"Big brother is thinking about: {question}. "
                + "This is a placeholder - implement actual big brother AI call here."
            }

        return {"function_name": function_name, "result": result}

    def add_tool_result_to_conversation(self, tool_call_id, function_name, result):
        """Add tool result to conversation history."""
        self.conversation_history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": function_name,
                "content": json.dumps(result),
            }
        )

    def get_ai_response_async(self, pyboy, callback):
        """
        Get AI response for the current game state asynchronously.
        Uses a thread to avoid blocking the main game loop.
        Implements the full tool use loop.
        """

        def ai_thread_func():
            try:
                # Capture current screen
                base64_image = self.get_screenshot(pyboy)

                # Add user message with screenshot
                self.add_user_message(base64_image)

                # Step 1: Get initial AI response
                completion = self.call_ai_api()

                # Parse AI response
                tries = 0
                while tries < 3:
                    try:
                        thinking, tool_calls = self.parse_ai_response(completion)
                        break
                    except ValueError as e:
                        logger.error("No tool calls found in AI response", error=str(e))
                        # retry the call
                        completion = self.call_ai_api(remind_format=True)
                        thinking, tool_calls = self.parse_ai_response(completion)
                    except Exception as e:
                        logger.error("Error parsing AI response", error=str(e))
                        logger.error("Stack trace", trace=traceback.format_exc())
                        return
                    tries += 1

                # Store thinking for display purposes
                self.most_recent_ai_thinking = (
                    thinking if thinking else self.most_recent_ai_thinking
                )
                self.most_recent_ai_commands = []

                # Add AI response to conversation history
                self.add_ai_response(completion.choices[0].message)

                # Step 2 & 3: Handle tool calls if any
                if tool_calls:
                    for tool_call in tool_calls:
                        # Execute the tool call
                        tool_result = self.execute_tool_call(tool_call, pyboy)

                        # Add tool result to conversation
                        self.add_tool_result_to_conversation(
                            tool_call.id,
                            tool_result["function_name"],
                            tool_result["result"],
                        )

                        logger.info("Tool result", tool_result=tool_result)
                    
                    # # Step 4: Get final AI response with tool results
                    # final_completion = self.call_ai_api()

                    # # Parse final response
                    # final_thinking, final_tool_calls = self.parse_ai_response(
                    #     final_completion
                    # )

                    # # Update thinking if new thinking is available
                    # if final_thinking:
                    #     self.most_recent_ai_thinking = final_thinking

                    # # Add final AI response to conversation history
                    # self.add_ai_response(final_completion.choices[0].message)

                    # # Check if there are more tool calls (recursive tool calling)
                    # if final_tool_calls:
                    #     # Queue another AI turn to handle these tool calls
                    #     # This allows for recursive tool calling
                    #     self.waiting_for_ai = False
                    #     self.ai_turn_counter += 1
                    #     self.get_ai_response_async(pyboy, callback)
                    #     return

                time.sleep(0.2)

                # Call the callback with the results
                callback(
                    self.conversation_history,
                    self.most_recent_ai_commands,
                    self.most_recent_ai_thinking,
                )

            except Exception as e:
                logger.error("Error getting AI response", error=str(e))
                logger.error("Stack trace", trace=traceback.format_exc())
                callback(self.conversation_history, [], "")

        # Start the AI processing in a separate thread
        ai_thread = threading.Thread(target=ai_thread_func)
        ai_thread.daemon = True
        ai_thread.start()

    def process_agent_command(self, command, pyboy):
        """Process a game command from either user or AI."""
        # Add command to history
        self.command_history.append(command)

        # Check for special commands first
        quit_requested = command.lower() == "quit"

        # Update debug_mode and unlimited_fps_mode based on commands
        if command.lower() == "debug":
            self.debug_mode = not self.debug_mode
        elif command.lower() == "unlimited_fps":
            self.unlimited_fps_mode = not self.unlimited_fps_mode
        elif command.lower() in [
            "up",
            "down",
            "left",
            "right",
            "a",
            "b",
            "start",
            "select",
        ]:
            # Handle single button presses
            logger.info("Pressing button", button=command.lower())
            pyboy.button(command.lower(), 5)
        elif command.lower().startswith("input "):
            # Process tool function calls for input command
            try:
                # Parse command format: input {"commands": ["up", "a", "b"]}
                commands_str = command.split("input ", 1)[1]
                commands_json = json.loads(commands_str)
                commands = commands_json.get("commands", [])

                logger.info(f"Processing input commands: {commands}")
                for btn in commands:
                    if btn in button_map:
                        # Press the button
                        logger.info("Pressing button", button=btn)
                        pyboy.button(btn, 5)
            except Exception as e:
                logger.error(f"Error processing input command: {e}")
        elif command.lower().startswith("notes "):
            # Handle notes command directly
            try:
                # Parse command format: notes {"action": "list", "note_name": "something"}
                args_str = command.split("notes ", 1)[1]
                args_json = json.loads(args_str)

                action = args_json.get("action")
                note_name = args_json.get("note_name", "")
                content = args_json.get("content", "")

                if action == "list":
                    if note_name:
                        logger.info(
                            f"Note '{note_name}': {self.knowledge_base.get(note_name, 'Not found')}"
                        )
                    else:
                        logger.info(f"Notes: {list(self.knowledge_base.keys())}")
                elif action == "add":
                    self.knowledge_base[note_name] = content
                    logger.info(f"Added note: {note_name}")
                elif action == "edit":
                    if note_name in self.knowledge_base:
                        self.knowledge_base[note_name] = content
                        logger.info(f"Edited note: {note_name}")
                    else:
                        logger.info(f"Note not found: {note_name}")
                elif action == "delete":
                    if note_name in self.knowledge_base:
                        del self.knowledge_base[note_name]
                        logger.info(f"Deleted note: {note_name}")
                    else:
                        logger.info(f"Note not found: {note_name}")
            except Exception as e:
                logger.error(f"Error processing notes command: {e}")
        elif command.lower().startswith("bro "):
            # Handle bro command
            try:
                # Parse command format: bro {"question": "how do I..."}
                args_str = command.split("bro ", 1)[1]
                args_json = json.loads(args_str)

                question = args_json.get("question", "")
                logger.info(f"Big brother was asked: {question}")

                # Here you would implement the actual call to the big brother AI
                # For now, just log that we received the command
                logger.info("Big brother functionality not fully implemented")
            except Exception as e:
                logger.error(f"Error processing bro command: {e}")

        return self.debug_mode, self.unlimited_fps_mode, quit_requested
