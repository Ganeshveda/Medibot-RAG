"""
Test script to demonstrate MediBot API endpoints and RBAC enforcement.
Run the FastAPI server first: python app.py
Then run this script in another terminal: python test_api.py
"""
import base64
import json
from typing import Any

try:
    import requests
except ImportError:
    print("requests library not installed. Install with: pip install requests")
    exit(1)

BASE_URL = "http://localhost:8000"


def make_request(method: str, endpoint: str, data: dict[str, Any] = None, token: str = None) -> dict[str, Any]:
    """Make a request to the API."""
    url = f"{BASE_URL}{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=5)
        else:
            raise ValueError(f"Unknown method: {method}")

        print(f"\n{method} {endpoint}")
        print(f"Status: {response.status_code}")
        try:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        except:
            print(f"Response: {response.text}")
            return {}
    except requests.exceptions.ConnectionError:
        print(f"\n❌ ERROR: Could not connect to {BASE_URL}")
        print("Make sure the FastAPI server is running: python app.py")
        return {}


def test_health():
    """Test health endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Health Check")
    print("=" * 60)
    make_request("GET", "/health")


def test_login():
    """Test login endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Login - Valid Credentials (doctor)")
    print("=" * 60)
    result = make_request("POST", "/login", {"username": "dr.mehta", "password": "doctor"})
    return result.get("access_token")


def test_login_invalid():
    """Test login with invalid credentials."""
    print("\n" + "=" * 60)
    print("TEST: Login - Invalid Credentials")
    print("=" * 60)
    make_request("POST", "/login", {"username": "dr.mehta", "password": "wrong_password"})


def test_chat_no_token():
    """Test chat without token."""
    print("\n" + "=" * 60)
    print("TEST: Chat - Missing Authorization Header")
    print("=" * 60)
    make_request("POST", "/chat", {"question": "What is paracetamol dosage?"})


def test_chat_doctor(token: str):
    """Test chat as doctor."""
    print("\n" + "=" * 60)
    print("TEST: Chat - Doctor Query (Clinical Access)")
    print("=" * 60)
    make_request("POST", "/chat", {"question": "What is the dosage for paracetamol?"}, token=token)


def test_collections():
    """Test collection access endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Collections Endpoint")
    print("=" * 60)
    make_request("GET", "/collections/admin")
    make_request("GET", "/collections/nurse")


def test_chat_nurse():
    """Test chat as nurse."""
    print("\n" + "=" * 60)
    print("TEST: Login - Nurse")
    print("=" * 60)
    result = make_request("POST", "/login", {"username": "nurse.priya", "password": "nurse"})
    token = result.get("access_token")

    if token:
        print("\n" + "=" * 60)
        print("TEST: Chat - Nurse Query (Should have no clinical access)")
        print("=" * 60)
        make_request("POST", "/chat", {"question": "Show me the drug formulary for antibiotics"}, token=token)


def test_chat_billing():
    """Test chat as billing executive."""
    print("\n" + "=" * 60)
    print("TEST: Login - Billing Executive")
    print("=" * 60)
    result = make_request("POST", "/login", {"username": "billing.ravi", "password": "billing_executive"})
    token = result.get("access_token")

    if token:
        print("\n" + "=" * 60)
        print("TEST: Chat - Billing Query (Billing Access Only)")
        print("=" * 60)
        make_request("POST", "/chat", {"question": "How do I submit a claim?"}, token=token)

        print("\n" + "=" * 60)
        print("TEST: Chat - Billing User Trying to Access Clinical (Should Fail)")
        print("=" * 60)
        make_request("POST", "/chat", {"question": "What treatment protocols are available?"}, token=token)


def main():
    print("\n🏥 MediBot API Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print("=" * 60)

    # Test basic endpoints
    test_health()
    test_login_invalid()

    # Test successful login and chat
    token_doctor = test_login()

    if token_doctor:
        test_chat_no_token()
        test_chat_doctor(token_doctor)
        test_collections()

    # Test RBAC with nurse
    test_chat_nurse()

    # Test RBAC with billing
    test_chat_billing()

    print("\n" + "=" * 60)
    print("✅ Test suite complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
