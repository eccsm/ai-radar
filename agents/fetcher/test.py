#!/usr/bin/env python
import os
import sys

print("=== DIAGNOSTIC INFORMATION ===")
print(f"Current working directory: {os.getcwd()}")
print(f"Directory contents: {os.listdir('.')}")
print(f"PYTHONPATH: {os.environ.get('PYTHONPATH')}")
print(f"sys.path: {sys.path}")
try:
    print("Trying to import main...")
    import main
    print("Successfully imported main!")
    print(f"Main module location: {main.__file__}")
except Exception as e:
    print(f"Error importing main: {e}")
print("=== END DIAGNOSTIC ===")

# Keep the container running for further inspection
print("Sleeping to allow inspection...")
import time
time.sleep(3600)
