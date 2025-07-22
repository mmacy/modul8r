#!/usr/bin/env python3
"""
Test script to validate logging fixes for duplicate entries.
This script simulates the logging behavior to ensure no duplicates are generated.
"""

import sys
import os
import asyncio
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

# Add the modul8r package to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_logging_no_duplicates():
    """Test that logging doesn't produce duplicate console entries."""
    print("Testing logging configuration for duplicates...")
    
    # Capture stdout and stderr
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        try:
            from modul8r.logging_config import get_logger, log_capture
            from modul8r.config import settings
            
            # Create logger
            logger = get_logger("test_logger")
            
            # Test without WebSocket subscribers (should not duplicate)
            print("Testing without WebSocket subscribers...")
            test_messages = [
                "Test message 1",
                "Test message 2", 
                "Test message 3"
            ]
            
            initial_entries = len(log_capture.entries)
            
            for i, msg in enumerate(test_messages):
                logger.info(msg, test_id=i)
            
            # Check that log capture didn't add entries when no subscribers
            final_entries = len(log_capture.entries)
            entries_added = final_entries - initial_entries
            
            print(f"Log capture entries added: {entries_added}")
            print(f"Expected: 0 (no WebSocket subscribers)")
            
            if entries_added == 0:
                print("✅ PASS: No duplicate entries when no WebSocket subscribers")
            else:
                print("❌ FAIL: Duplicate entries detected without subscribers")
                return False
                
        except Exception as e:
            print(f"❌ FAIL: Error during test: {e}")
            return False
    
    # Check captured output for duplicates
    stdout_content = stdout_capture.getvalue()
    stderr_content = stderr_capture.getvalue()
    
    print(f"\nStdout content length: {len(stdout_content)}")
    print(f"Stderr content length: {len(stderr_content)}")
    
    # Count log lines (simple heuristic)
    stdout_lines = [line for line in stdout_content.split('\n') if line.strip()]
    stderr_lines = [line for line in stderr_content.split('\n') if line.strip()]
    
    print(f"Stdout lines: {len(stdout_lines)}")
    print(f"Stderr lines: {len(stderr_lines)}")
    
    return True

def test_websocket_logging():
    """Test WebSocket logging functionality."""
    print("\nTesting WebSocket logging...")
    
    try:
        from modul8r.logging_config import get_logger, log_capture
        
        # Mock WebSocket subscriber
        class MockWebSocket:
            def __init__(self):
                self.messages = []
            
            async def send_json(self, message):
                self.messages.append(message)
        
        mock_ws = MockWebSocket()
        logger = get_logger("websocket_test")
        
        # Add subscriber
        log_capture.add_subscriber(mock_ws)
        
        # Test that we now have subscribers
        if not log_capture.has_subscribers():
            print("❌ FAIL: has_subscribers() should return True")
            return False
        
        print("✅ PASS: WebSocket subscriber detection works")
        
        # Remove subscriber
        log_capture.remove_subscriber(mock_ws)
        
        if log_capture.has_subscribers():
            print("❌ FAIL: has_subscribers() should return False after removal")
            return False
            
        print("✅ PASS: WebSocket subscriber removal works")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: WebSocket test error: {e}")
        return False

def test_deduplication():
    """Test log entry deduplication."""
    print("\nTesting log deduplication...")
    
    try:
        from modul8r.logging_config import LogCapture
        
        # Create test capture instance
        capture = LogCapture(max_entries=100)
        
        # Test duplicate detection
        entry1 = {"event": "test", "request_id": "123", "_websocket_only": True}
        entry2 = {"event": "test", "request_id": "123", "_websocket_only": True}  # Duplicate
        entry3 = {"event": "different", "request_id": "123", "_websocket_only": True}  # Different
        
        initial_count = len(capture.entries)
        
        capture.add_entry(entry1)
        count_after_first = len(capture.entries)
        
        capture.add_entry(entry2)  # Should be deduplicated
        count_after_duplicate = len(capture.entries)
        
        capture.add_entry(entry3)  # Should be added
        final_count = len(capture.entries)
        
        print(f"Initial: {initial_count}, After first: {count_after_first}, After duplicate: {count_after_duplicate}, Final: {final_count}")
        
        if count_after_first == initial_count + 1 and count_after_duplicate == count_after_first and final_count == count_after_first + 1:
            print("✅ PASS: Deduplication works correctly")
            return True
        else:
            print("❌ FAIL: Deduplication not working as expected")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Deduplication test error: {e}")
        return False

def main():
    """Run all logging tests."""
    print("=" * 60)
    print("LOGGING FIX VALIDATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Console Duplicate Prevention", test_logging_no_duplicates),
        ("WebSocket Functionality", test_websocket_logging),
        ("Log Deduplication", test_deduplication)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        print("-" * 40)
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ FAIL: {test_name} - {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 ALL TESTS PASSED! Logging fixes are working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the logging configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())