#!/usr/bin/env python3
"""Simple browser test to debug tour issues."""

import subprocess
import time
import signal
import sys

def test_browser_launch():
    """Test if we can launch and close browser properly."""
    print("Testing browser launch in container...")
    
    # Set up signal handler to clean up
    def signal_handler(sig, frame):
        print("\nCleaning up browser processes...")
        cleanup_cmd = ["docker", "exec", "odoo-opw-script-runner-1", "pkill", "-f", "chromium"]
        subprocess.run(cleanup_cmd, capture_output=True)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Launch browser with proper flags
        cmd = [
            "docker", "exec", 
            "-e", "DISPLAY=:99",
            "-e", "HEADLESS_CHROMIUM=1",
            "odoo-opw-script-runner-1",
            "chromium", 
            "--headless",
            "--no-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--remote-debugging-port=9222",
            "--timeout=30000",
            "--disable-web-security",
            "about:blank"
        ]
        
        print(f"Running: {' '.join(cmd)}")
        
        # Start browser process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        print("Browser launched, waiting for 10 seconds...")
        
        # Wait for 10 seconds to see if it stays running
        time.sleep(10)
        
        # Check if process is still running
        if process.poll() is None:
            print("Browser is still running - this is good!")
            # Terminate it
            process.terminate()
            process.wait(timeout=5)
            print("Browser terminated successfully")
        else:
            print(f"Browser exited with code: {process.returncode}")
            stdout, _ = process.communicate()
            print(f"Output: {stdout}")
            
    except Exception as e:
        print(f"Error: {e}")
    
    # Clean up any remaining processes
    cleanup_cmd = ["docker", "exec", "odoo-opw-script-runner-1", "pkill", "-f", "chromium"]
    subprocess.run(cleanup_cmd, capture_output=True)
    print("Cleanup completed")

if __name__ == "__main__":
    test_browser_launch()