import os
import sys

# Get the path to the current directory (api/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the root directory
root_dir = os.path.dirname(current_dir)

# Add both to sys.path
sys.path.append(root_dir)
sys.path.append(os.path.join(root_dir, 'backend'))

from backend.app import app

# This is the entry point for Vercel
# Vercel's @vercel/python builder looks for 'app'
app = app
