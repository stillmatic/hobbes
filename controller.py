# controller.py - Orchestrates the model and view
import queue
import time
import traceback
import pygame
import threading

from model import GameModel
from view import GameView


class GameController:
    def __init__(self, pyboy, rom_path, client, headless=False):
        self.pyboy = pyboy
        self.rom_path = rom_path
        self.headless = headless

        # Initialize model and view
        self.model = GameModel(client)
        self.view = GameView()

        # Input thread (for non-headless mode)
        self.input_thread = None

    def ai_response_callback(self, updated_history, commands, thinking):
        """Callback for when AI responds."""
        self.model.conversation_history = updated_history
        self.model.waiting_for_ai = False

        # Display AI response if needed
        self.view.display_ai_response(thinking, commands)

    def start_input_thread(self):
        """Start the input thread for user commands."""
        if self.headless:
            return

        def input_thread_func():
            while self.model.running:
                try:
                    command = input()  # No prompt here, we'll use Rich for that
                    self.model.command_queue.put(command)
                except EOFError:
                    break

        self.input_thread = threading.Thread(target=input_thread_func, daemon=True)
        self.input_thread.start()

        # Display an input prompt with Rich
        self.view.prompt_for_input()

    def process_user_commands(self):
        """Process commands from the user input queue."""
        if self.headless:
            return

        try:
            while not self.model.command_queue.empty():
                command = self.model.command_queue.get_nowait()

                # Special command to trigger AI
                if command.lower() == "ai" and not self.model.waiting_for_ai:
                    try:
                        self.view.console.print(
                            "[bold blue]Triggering AI for next move..."
                        )
                        self.model.waiting_for_ai = True
                        self.model.get_ai_response_async(
                            self.pyboy, self.ai_response_callback
                        )
                    except Exception as e:
                        self.view.console.print(
                            f"[bold red]Error triggering AI: {str(e)}"
                        )
                        self.view.console.print("[bold red]Stack trace:")
                        self.view.console.print(traceback.format_exc(), style="red")
                        self.model.waiting_for_ai = False
                else:
                    _, _, quit_requested = self.model.process_agent_command(
                        command, self.pyboy
                    )
                    if quit_requested:
                        self.model.running = False

                # Update the prompt after processing a command
                self.view.prompt_for_input()
        except queue.Empty:
            pass

    def process_ai_commands(self):
        """Process commands from the AI command queue."""
        try:
            while not self.model.ai_command_queue.empty():
                cmd = self.model.ai_command_queue.get_nowait()
                self.view.console.print(f"[cyan]Executing AI command: {cmd}")
                _, _, quit_requested = (
                    self.model.process_agent_command(cmd, self.pyboy)
                )
                if quit_requested:
                    self.model.running = False
                    break
                # Add a small delay between commands
                time.sleep(0.2)
        except queue.Empty:
            pass

    def handle_headless_ai(self):
        """In headless mode, automatically trigger AI periodically."""
        if (
            self.headless
            and not self.model.waiting_for_ai
            and (self.model.ai_turn_counter == 0 or self.model.ai_turn_counter >= 180)
        ):
            try:
                self.view.console.print(
                    "\n[bold blue]Automatically triggering AI in headless mode..."
                )
                self.model.waiting_for_ai = True
                self.model.get_ai_response_async(self.pyboy, self.ai_response_callback)
                self.model.ai_turn_counter = 0
            except Exception as e:
                self.view.console.print(f"[bold red]Error triggering AI: {str(e)}")
                self.view.console.print("[bold red]Stack trace:")
                self.view.console.print(traceback.format_exc(), style="red")
                self.model.waiting_for_ai = False
                self.model.ai_turn_counter = 0

    def run(self):
        """Run the main game loop."""
        # Start input thread (for non-headless mode)
        self.start_input_thread()

        # Start the live display
        with self.view.get_live_display() as live:
            while self.model.running:
                # Update display
                self.view.update_command_history(self.model)
                self.view.update_ai_thinking(self.model)

                # Handle AI in headless mode
                self.handle_headless_ai()

                # Process AI commands
                self.process_ai_commands()

                # Process user commands
                self.process_user_commands()

                # Process window events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.model.running = False

                # Tick the emulator (advance one frame)
                self.model.running = self.model.running and self.pyboy.tick()

                # Increment counter in headless mode
                if self.headless:
                    self.model.ai_turn_counter += 1
