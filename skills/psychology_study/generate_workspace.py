import os

def create_psychology_workspace():
    # Define the root portfolio directory
    base_dir = "Psychology_Portfolio"
    
    # Define the required subdirectory structure
    structure = [
        "01_Introduction_to_Psychology/Conceptual_Logs",
        "01_Introduction_to_Psychology/Exams_and_Validation",
    ]
    
    print(f"🚀 Initializing academic workspace in ./{base_dir}...")
    
    # Create directories
    for folder in structure:
        path = os.path.join(base_dir, folder)
        os.makedirs(path, exist_ok=True)
        print(f"  └── Created: {path}")
        
        # Initialize an empty gitkeep or placeholder file to preserve structure
        placeholder = os.path.join(path, ".gitkeep")
        with open(placeholder, "w") as f:
            pass

    print("\n✅ Workspace generation complete! You are ready to track your studies.")

if __name__ == "__main__":
    create_psychology_workspace()
