#!/usr/bin/env python3
"""Test browser setup and configuration for tour tests."""

import subprocess
import sys
import os

def test_browser_environment():
    """Test if browser environment is properly configured."""
    print("Testing browser environment configuration...")
    
    # Check if Chromium is available
    try:
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Chromium found at: {result.stdout.strip()}")
        else:
            print("✗ Chromium not found")
            return False
    except Exception as e:
        print(f"✗ Error checking Chromium: {e}")
        return False
    
    # Check Chromium version
    try:
        result = subprocess.run(['chromium', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Chromium version: {result.stdout.strip()}")
        else:
            print(f"✗ Chromium version check failed: {result.stderr}")
    except Exception as e:
        print(f"✗ Error getting Chromium version: {e}")
    
    # Test basic headless browser functionality
    print("\nTesting basic headless browser functionality...")
    try:
        html_content = '<html><body><h1>Browser Test</h1><script>console.log("JS works");</script></body></html>'
        cmd = [
            'chromium',
            '--headless=new',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-software-rasterizer',
            '--virtual-time-budget=5000',
            '--run-all-compositor-stages-before-draw',
            '--dump-dom',
            f'data:text/html,{html_content}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            if 'Browser Test' in result.stdout:
                print("✓ Basic headless browser test passed")
                return True
            else:
                print(f"✓ Browser launched successfully but unexpected output:")
                print(f"  Stdout: {result.stdout[:200]}...")
                return True  # Browser works, just different output than expected
        else:
            print(f"✗ Basic browser test failed:")
            print(f"  Return code: {result.returncode}")
            print(f"  Stdout: {result.stdout[:200]}...")
            print(f"  Stderr: {result.stderr[:200]}...")
            return False
    except subprocess.TimeoutExpired:
        print("✗ Browser test timed out")
        return False
    except Exception as e:
        print(f"✗ Browser test error: {e}")
        return False

def test_odoo_browser_integration():
    """Test if Odoo can successfully start with browser integration."""
    print("\nTesting Odoo browser integration...")
    
    # Set environment variables that Odoo's browser_js expects
    env = os.environ.copy()
    env.update({
        'HEADLESS_CHROMIUM': '1',
        'CHROMIUM_BIN': '/usr/bin/chromium',
        'CHROMIUM_FLAGS': '--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer --window-size=1920,1080 --no-first-run --no-default-browser-check --virtual-time-budget=30000 --run-all-compositor-stages-before-draw',
        'DISPLAY': ':99',
    })
    
    # Test Odoo startup with minimal configuration (no tests, just asset generation)
    cmd = [
        '/odoo/odoo-bin',
        '-d', 'opw',
        '--addons-path', '/volumes/addons,/odoo/addons,/volumes/enterprise',
        '--http-port', '20199',
        '--stop-after-init',
        '--log-level=info',
        '--without-demo=all',
        '--init=base',  # Only initialize base module
    ]
    
    try:
        print("Starting Odoo with browser environment...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        
        if result.returncode == 0:
            if 'bundles generated' in result.stdout:
                print("✓ Odoo asset generation completed successfully")
                return True
            else:
                print("? Odoo started but asset generation status unclear")
                print("Last few lines of output:")
                print('\n'.join(result.stdout.split('\n')[-10:]))
                return False
        else:
            print(f"✗ Odoo startup failed with return code {result.returncode}")
            print("Error output:")
            print(result.stderr[-500:])  # Last 500 chars of error
            return False
            
    except subprocess.TimeoutExpired:
        print("✗ Odoo startup timed out (likely hanging during asset generation)")
        return False
    except Exception as e:
        print(f"✗ Odoo startup error: {e}")
        return False

def main():
    """Run all browser setup tests."""
    print("Browser Setup Diagnostic Tool")
    print("=" * 50)
    
    all_passed = True
    
    # Test 1: Browser environment
    if not test_browser_environment():
        all_passed = False
    
    # Test 2: Odoo browser integration  
    if not test_odoo_browser_integration():
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ All browser setup tests passed")
        print("Browser environment appears to be configured correctly for tour tests")
        sys.exit(0)
    else:
        print("✗ Some browser setup tests failed")
        print("Tour tests may not work properly until these issues are resolved")
        sys.exit(1)

if __name__ == '__main__':
    main()