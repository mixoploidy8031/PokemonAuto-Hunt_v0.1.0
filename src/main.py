import os
import random
import time
import threading
import pygame
from PIL import Image, ImageTk 
import tkinter as tk
from colorama import Fore, Style
from config_loader import load_config, check_file_exists
from data_manager import DataManager
from logger import logger
from pathlib import Path
import sys

print("Starting application...")
print(f"Executable path: {sys.executable}")
print(f"Working directory: {os.getcwd()}")

def get_base_path():
    # Determine base path for development and PyInstaller
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle (PyInstaller)
        return Path(sys.executable).parent
    else:
        # If running in development
        return Path(__file__).parent.parent

PROJECT_ROOT = get_base_path()

# Load configuration
config = load_config()

# Create data manager instance
data_manager = DataManager(config)

# Extract user-configurable values
gif_directory = config["gif_directory"]

# Extract internal defaults
shiny_count_file = config["shiny_count_file"]
pokemon_data_file = config["pokemon_data_file"]
encounter_delay = config["encounter_delay"]
rarity_weights = config["rarity_weights"]
shiny_rate = config["shiny_rate"]
mute_audio = config["mute_audio"]

# Validate required files
check_file_exists(shiny_count_file)
check_file_exists(pokemon_data_file)

# Initialize global variables
current_encounter = None
total_encounters = 0
total_shiny_found = 0
shiny_found = False
elapsed_time = 0
start_time = None
timer_running = False
frames = []

# Initialize pygame mixer globally
pygame.mixer.init()

# Initialize the Tkinter window
root = tk.Tk()
root.title("IdleMon")
root.minsize(500, 500)

# Load the background image
background_image_path = config["background_image"]
if os.path.isabs(background_image_path):
    # If it's an absolute path, use it directly
    background_path = Path(background_image_path)
else:
    # If it's a relative path, use it relative to project root
    background_path = PROJECT_ROOT / background_image_path

# Fallback to default background if specified path doesn't exist
if not check_file_exists(background_path):
    print(f"Warning: Could not find background image at {background_path}")
    print("Falling back to default background...")
    background_path = PROJECT_ROOT / "assets" / "images" / "default_background.jpg"
    if not check_file_exists(background_path):
        print(f"Error: Could not find default background image at {background_path}")
        root.destroy()
        sys.exit(1)

background_image = tk.PhotoImage(file=str(background_path))

# Get dimensions of the background image
background_width = background_image.width()
background_height = background_image.height()

# Set Tkinter window constraints
root.maxsize(background_width, background_height)
root.resizable(width=True, height=False)

# Update shiny count and save it
def update_shiny_count():
    global total_shiny_found
    total_shiny_found += 1
    shiny_label.config(text=f"Shiny Pokémon Found: {total_shiny_found}")
    data_manager.save_shiny_count(total_shiny_found)

# Initialize shiny count from file
def initialize_shiny_count():
    global total_shiny_found
    total_shiny_found = data_manager.load_shiny_count()
    shiny_label.config(text=f"Shiny Pokémon Found: {total_shiny_found}")

# Handle shiny Pokémon encounter
def handle_shiny_encounter(pokemon_name, pokemon_rarity):
    global shiny_found, timer_running
    shiny_found = True
    info_label.config(
        text=f"{pokemon_name} - {pokemon_rarity} (Shiny!)",
        fg="gold"
    )
    print(Fore.YELLOW + f"Congrats!!! You found a shiny {pokemon_name} after {total_encounters} encounters!" + Style.RESET_ALL)
    
    # Play shiny encounter sound if not muted
    if not mute_audio:
        shiny_sound_path = PROJECT_ROOT / "assets" / "sounds" / "shiny_sound1.wav"
        if os.path.exists(shiny_sound_path):
            try:
                sound = pygame.mixer.Sound(shiny_sound_path)
                sound.play()
            except pygame.error as e:
                logger.log_error(f"Error playing shiny sound: {e}")
        else:
            logger.log_error(f"Shiny sound file not found: {shiny_sound_path}")
    
    update_shiny_count()
    logger.log_shiny(pokemon_name, pokemon_rarity)
    continue_button.place(relx=0.5, rely=0.5, anchor="center")
    timer_running = False

# Load Pokémon data
def initialize_pokemon_data():
    global pokemon_data
    pokemon_data = data_manager.load_pokemon_data()

# Calculate encounter weights based on rarity
def calculate_weights(pokemon_data):
    weights = [rarity_weights.get(rarity, 0) for rarity in pokemon_data.values()]
    return weights

# Simulate shiny encounter
def shiny_pokemon():
    shiny_value = random.randint(1, shiny_rate)
    if shiny_value == 1:
        return True
    elif random.randint(1, shiny_rate // 5) == 1:
        print(Fore.MAGENTA + "You hear a shiny Pokémon nearby..." + Style.RESET_ALL)
    return False

# Display the Pokémon GIF
def display_pokemon_gif(pokemon_name, is_shiny=False):
    global current_encounter, frames
    
    # Get the new gif path using the correct subdirectory
    gif_subdir = "shiny" if is_shiny else "normal"
    new_gif_path = PROJECT_ROOT / "assets" / "gifs" / gif_subdir / f"{pokemon_name}.gif"
    
    # Set different animation speeds for normal and shiny Pokémon
    NORMAL_FRAME_DELAY = 50   # Normal Pokémon: 50ms per frame
    SHINY_FRAME_DELAY = 100   # Shiny Pokémon: 100ms per frame
    FRAME_DELAY = SHINY_FRAME_DELAY if is_shiny else NORMAL_FRAME_DELAY

    # Stop any existing animation
    if hasattr(display_pokemon_gif, 'after_id'):
        root.after_cancel(display_pokemon_gif.after_id)
        display_pokemon_gif.after_id = None

    # Load new frames if it's a different GIF file
    if not hasattr(display_pokemon_gif, 'current_gif_path') or new_gif_path != display_pokemon_gif.current_gif_path:
        try:
            image = Image.open(new_gif_path)
            frames = []  # Store frames in the global variable
            
            # Extract frames for animated GIFs
            for frame in range(0, image.n_frames):
                image.seek(frame)
                frames.append(ImageTk.PhotoImage(image.copy()))

            display_pokemon_gif.current_gif_path = new_gif_path

        except FileNotFoundError:
            print(f"GIF file not found: {new_gif_path}")
            return
        except Image.UnidentifiedImageError:
            print(f"Invalid image format for {new_gif_path}")
            return
        except Exception as e:
            print(f"Unexpected error loading {pokemon_name}: {e}")
            return

    # Define animation function
    def animate(frame_index=0):
        if not frames:  # Safety check
            return
        
        # Clear only Pokémon GIF
        canvas.delete("pokemon_gif")
        
        # Calculate the center of the canvas
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        center_x = canvas_width // 2
        center_y = (canvas_height * 5) // 6
        
        try:
            # Add bounds checking
            current_frame = frame_index % len(frames)
            # Add the current frame of the Pokémon GIF to the canvas
            canvas.create_image(center_x, center_y, image=frames[current_frame], tag="pokemon_gif")
            
            # Schedule next frame with appropriate delay
            display_pokemon_gif.after_id = root.after(FRAME_DELAY, animate, (frame_index + 1) % len(frames))
        except (IndexError, ZeroDivisionError) as e:
            print(f"Animation error: frame_index={frame_index}, frames length={len(frames)}")
            return
    
    # Start the animation
    animate()
    
    # Always update current encounter regardless of whether we loaded a new GIF
    current_encounter = pokemon_name

# Update the timer label
def update_timer():
    global elapsed_time, start_time, timer_running
    while timer_running:
        if start_time is not None:
            elapsed_time += time.time() - start_time
            start_time = time.time()
        minutes, seconds = divmod(int(elapsed_time), 60)
        stats_label.config(text=f"Time Elapsed: {minutes:02}:{seconds:02}")
        time.sleep(1)

# Handle the "Continue" button click
def continue_hunt():
    global shiny_found, start_time, timer_running, total_encounters

    # Reset encounters counter when continuing
    total_encounters = 0
    encounter_label.config(text=f"Encounters: {total_encounters}")

    # Play continue button sound if not muted
    if not mute_audio:
        continue_sound_path = PROJECT_ROOT / "assets" / "sounds" / "continue_sound1.wav"
        if os.path.exists(continue_sound_path):
            try:
                sound = pygame.mixer.Sound(continue_sound_path)
                sound.play()
            except pygame.error as e:
                logger.log_error(f"Error playing continue sound: {e}")
        else:
            logger.log_error(f"Continue sound file not found: {continue_sound_path}")

    shiny_found = False
    start_time = time.time()
    continue_button.place_forget()
    if not timer_running:
        timer_running = True
        threading.Thread(target=update_timer, daemon=True).start()
    start_encounter_thread()

# Start the encounter loop
def start_encounter():
    global current_encounter, total_encounters, shiny_found

    # Load Pokémon data
    pokemon_data = data_manager.load_pokemon_data()
    if not pokemon_data:
        print("No Pokémon data available. Exiting encounter loop.")
        return
    
    # Extract Pokémon names and calculate weights
    pokemon_list = list(pokemon_data.keys())
    weights = calculate_weights(pokemon_data)

    # Encounter loop
    while not shiny_found:
        time.sleep(encounter_delay)
        total_encounters += 1
        encounter_label.config(text=f"Encounters: {total_encounters}")

        # Randomly select a Pokémon based on weights
        pokemon_name = random.choices(pokemon_list, weights=weights, k=1)[0]
        pokemon_rarity = pokemon_data[pokemon_name]
        current_encounter = pokemon_name

        # Determine if the encounter is shiny
        is_shiny = shiny_pokemon()

        # Display Pokémon gif
        display_pokemon_gif(pokemon_name, is_shiny=is_shiny)

        # Update info label for shiny or normal Pokémon
        if is_shiny:
            handle_shiny_encounter(pokemon_name, pokemon_rarity)
        else:
            info_label.config(
                text=f"{pokemon_name} - {pokemon_rarity}",
                fg="white"
            )
            print(f"You encountered a wild {pokemon_name}!")

# Start encounter simulation
def start_encounter_thread():
    threading.Thread(target=start_encounter, daemon=True).start()

# Initialize the timer
def initialize_timer():
    global start_time, timer_running
    start_time = time.time()
    timer_running = True
    threading.Thread(target=update_timer, daemon=True).start()

# Add label with a semi-transparent background to the canvas
def create_label_with_background(canvas, text, x, y, width, height, font=("Arial", 10)):
    rectangle = canvas.create_rectangle(
        x, y, x + width, y + height,
        fill="black",
        outline=""
    )
    label = tk.Label(root, text=text, font=font, bg="black", fg="white")
    label_window = canvas.create_window(x + 5, y + height // 2, anchor="w", window=label)
    return label, rectangle

# Create the canvas and UI elements
canvas_width = 500
canvas_height = 500
canvas = tk.Canvas(root, width=canvas_width, height=canvas_height)
canvas.pack(fill="both", expand=False)
canvas.create_image(0, 0, image=background_image, anchor="nw")

# Create labels
info_label, info_bg = create_label_with_background(canvas, "Walking through the Kanto region...", 10, 10, 200, 20)
encounter_label, encounter_bg = create_label_with_background(canvas, "Encounters: 0", 10, 40, 200, 20)
shiny_label, shiny_bg = create_label_with_background(canvas, "Shiny Pokémon Found: 0", 10, 70, 200, 20)
stats_label, stats_bg = create_label_with_background(canvas, "Time Elapsed: 0 seconds", 10, 100, 200, 20)

# Create continue button
continue_button = tk.Button(
    root,
    text="Continue Hunt",
    command=continue_hunt,
    font=("Arial", 12),
    bg="green",
    fg="white"
)

# Initialize and start
initialize_shiny_count()
initialize_timer()
start_encounter_thread()

# Handle window close
def on_closing():
    global timer_running
    timer_running = False
    pygame.mixer.quit()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Start the main loop
root.mainloop()
