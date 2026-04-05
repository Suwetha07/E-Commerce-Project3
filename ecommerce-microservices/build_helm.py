import os
import sys

if __name__ == '__main__':
    script_path = os.path.join('scripts', 'generate_helm.py')
    print(f"Redirecting to the new Umbrella Chart generator at {script_path}...")
    # Execute the actual script
    with open(script_path, 'r') as f:
        exec(f.read())
