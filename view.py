# view.py - Handles display logic and UI rendering
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich.live import Live

class GameView:
    def __init__(self):
        self.console = Console()
        self.layout = self._create_layout()
        self.ai_spinner = None
    
    def _create_layout(self):
        """Create the initial layout structure."""
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        
        # Split the main section
        layout["main"].split_row(
            Layout(name="command_history", ratio=1), 
            Layout(name="ai_thinking", ratio=1)
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
        
        return layout
    
    def get_live_display(self):
        """Return a Live display object for the layout."""
        return Live(self.layout, refresh_per_second=10, screen=False)
    
    def update_command_history(self, model):
        """Update the command history panel."""
        if model.waiting_for_ai:
            # Show spinner when waiting for AI
            if self.ai_spinner is None:
                self.ai_spinner = Panel(
                    "[bold yellow]Waiting for AI to respond...",
                    title="AI Status",
                    border_style="yellow",
                )
            self.layout["command_history"].update(self.ai_spinner)
        else:
            self.ai_spinner = None
            
            # Show command history
            status_text = f"[bold green]Game Status:[/bold green]\n"
            status_text += f"Debug: {'ON' if model.debug_mode else 'OFF'}\n"
            status_text += (
                f"Unlimited FPS: {'ON' if model.unlimited_fps_mode else 'OFF'}\n\n"
            )
            
            # Display recent command history
            if model.command_history:
                status_text += "[bold blue]Recent Commands:[/bold blue]\n"
                for i, cmd in enumerate(reversed(model.command_history), 1):
                    if i > 10:  # Safety check for maxlen
                        break
                    status_text += f"{i}. [cyan]{cmd}[/cyan]\n"
            else:
                status_text += "[italic]No commands executed yet[/italic]\n"
            
            # Display last AI commands if available
            if model.most_recent_ai_commands:
                status_text += "\n[bold magenta]Last AI Commands:[/bold magenta]\n"
                for i, cmd in enumerate(model.most_recent_ai_commands, 1):
                    status_text += f"{i}. [magenta]{cmd}[/magenta]\n"
            
            self.layout["command_history"].update(
                Panel(status_text, title="Command History")
            )
    
    def update_ai_thinking(self, model):
        """Update the AI thinking panel."""
        if model.most_recent_ai_thinking:
            ai_thinking_panel = Panel(
                Text(model.most_recent_ai_thinking, style="blue", overflow="fold"),
                title="Last AI Thinking",
                border_style="blue",
            )
            self.layout["ai_thinking"].update(ai_thinking_panel)
        else:
            self.layout["ai_thinking"].update(
                Panel("No AI thinking yet", title="AI Thinking")
            )
    
    def display_ai_response(self, thinking, commands):
        """Display AI response components directly."""
        if thinking:
            self.console.print(
                Panel(thinking, title="AI Thinking", border_style="blue", expand=False)
            )
        
        if commands:
            # Create a table for commands
            table = Table(title="AI Commands")
            table.add_column("Command", style="cyan")
            for cmd in commands:
                table.add_row(cmd)
            self.console.print(table)
    
    def prompt_for_input(self):
        """Display the input prompt."""
        self.console.print("[bold cyan]Enter command: ", end="")
