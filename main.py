from pyboy import PyBoy
import pygame
import time
import sys
import fire

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
    print("Use the following controls:")
    print("  Arrow keys: D-pad")
    print("  Z: A button")
    print("  X: B button")
    print("  Enter: Start button")
    print("  Backspace: Select button")
    print("  ESC: Quit the emulator")
    print("  O: Save screenshot")
    print("  Z: Save state")
    print("  X: Load state")
    print("  Space: Toggle unlimited FPS")
    print("  D: Toggle debug information")
    
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

def run_emulator_loop(pyboy, rom_path, debug_mode, unlimited_fps_mode):
    """Run the main emulator game loop."""
    # Define mapping from pygame keys to PyBoy button names
    button_map = {
        pygame.K_UP: "up",
        pygame.K_DOWN: "down",
        pygame.K_LEFT: "left",
        pygame.K_RIGHT: "right",
        pygame.K_z: "a",
        pygame.K_x: "b",
        pygame.K_RETURN: "start",
        pygame.K_BACKSPACE: "select"
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
                    pyboy.screen_image().save(screenshot_path)
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
            
            # You can add more game-specific debug info here
            # For example, you might want to print memory values for Pokémon Blue
            # print(f"Player X: {pyboy.get_memory_value(0xD362)}")
            # print(f"Player Y: {pyboy.get_memory_value(0xD361)}")

def main(
    rom_path="roms/pokemon_blue.gb",
    speed=1,
    skip_frames=2000,
    debug=False,
    unlimited_fps=False
):
    # Setup the emulator
    pyboy, debug_mode, unlimited_fps_mode = setup_emulator(
        rom_path, speed, skip_frames, debug, unlimited_fps
    )
    
    try:
        # Run the main game loop
        run_emulator_loop(pyboy, rom_path, debug_mode, unlimited_fps_mode)
    finally:
        # Clean up
        pyboy.stop()
        print("Emulator stopped.")

if __name__ == "__main__":
    fire.Fire(main)