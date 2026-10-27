"""
IT 110 Lab Activity 10 - Endpoint Testing Script
Tests all SmartTrack API endpoints and generates response log
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8001"
TOKEN = None  # Will be set after login

def print_test_result(name, method, url, status_code, response_data):
    """Print formatted test result"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"METHOD: {method}")
    print(f"URL: {url}")
    print(f"STATUS: {status_code}")
    print(f"RESPONSE: {json.dumps(response_data, indent=2)}")
    print(f"{'='*60}")

def test_health():
    """Test health endpoint"""
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    print_test_result("Health Check", "GET", url, response.status_code, response.json())
    return response.status_code == 200

def test_root():
    """Test root endpoint"""
    url = f"{BASE_URL}/"
    response = requests.get(url)
    print_test_result("Root Endpoint", "GET", url, response.status_code, response.json())
    return response.status_code == 200

def test_register():
    """Test user registration"""
    url = f"{BASE_URL}/api/auth/register"
    data = {
        "email": f"test_lab10_{datetime.now().timestamp()}@csu.edu",
        "password": "SecurePass123!",
        "full_name": "Lab 10 Test User",
        "role": "faculty"
    }
    try:
        response = requests.post(url, json=data)
        print_test_result("User Registration", "POST", url, response.status_code, response.json())
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_login():
    """Test user login and get JWT token"""
    global TOKEN
    url = f"{BASE_URL}/api/auth/login"
    data = {
        "email": "admin@smarttrack.csu.edu",  # Use existing admin account
        "password": "admin123"
    }
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
            TOKEN = result.get("access_token")
            print_test_result("User Login", "POST", url, response.status_code, result)
            return True
        else:
            print_test_result("User Login", "POST", url, response.status_code, response.json())
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_get_travels():
    """Test list travels endpoint"""
    url = f"{BASE_URL}/api/travels"
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    try:
        response = requests.get(url, headers=headers)
        print_test_result("List Travels", "GET", url, response.status_code, response.json())
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_get_colleges():
    """Test list colleges endpoint"""
    url = f"{BASE_URL}/api/colleges"
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    try:
        response = requests.get(url, headers=headers)
        print_test_result("List Colleges", "GET", url, response.status_code, response.json())
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_get_document_types():
    """Test list document types endpoint"""
    url = f"{BASE_URL}/api/document-types"
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    try:
        response = requests.get(url, headers=headers)
        print_test_result("List Document Types", "GET", url, response.status_code, response.json())
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def run_all_tests():
    """Run all endpoint tests"""
    print("\n" + "="*60)
    print("SmartTrack API Endpoint Testing - Lab Activity 10")
    print(f"Base URL: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    tests = [
        ("Health Check", test_health),
        ("Root Endpoint", test_root),
        ("User Registration", test_register),
        ("User Login", test_login),
        ("List Travels", test_get_travels),
        ("List Colleges", test_get_colleges),
        ("List Document Types", test_get_document_types),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {name} PASSED")
            else:
                failed += 1
                print(f"❌ {name} FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {name} FAILED: {e}")
    
    print("\n" + "="*60)
    print(f"TEST SUMMARY")
    print(f"Total: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")
    print("="*60)

if __name__ == "__main__":
    run_all_tests()
