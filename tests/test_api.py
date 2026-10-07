import os
import time
import uuid

import psycopg2
import pytest
import requests

BASE_URL = os.environ["API_BASE_URL"]
DATABASE_URL = os.environ["TEST_DATABASE_URL"]

def request(method, path, **kwargs):
    return requests.request(
        method, 
        f"{BASE_URL}{path}",
        timeout=10,
        **kwargs,
    )
    
def clear_items():
    with psycopg2.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE items RESTART IDENTITY")

def item_count():
    with psycopg2.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM items")
            return cursor.fetchone()[0]

@pytest.fixture(scope="session", autouse=True)
def wait_for_api():
    deadline = time.monotonic() +30
    
    while time.monotonic() < deadline:
        try:
            response = requests.get(
                f"{BASE_URL}/ready",
                timeout=2,
            )
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        
        time.sleep(1)
        
    pytest.fail("API did not become ready within 30 seconds")

@pytest.fixture(autouse=True)
def clean_database(wait_for_api):
    clear_items()
    yield
    clear_items()

def create_item():
    name = f"test-{uuid.uuid4().hex}"
    response = request("POST", "/items", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["item"]

def test_health():
    response =  request("GET", "/health")
    assert response.status_code == 200, response.text
    
def test_ready_with_database():
    response = request("GET", "/ready")
    assert response.status_code == 200, reponse.text
    assert response.json()["database"] == "connected"

def test_create_item():
    item = create_item()
    
    assert isinstance(item["id"], int)
    assert item["id"] > 0
    assert item["name"].startswith("test-")
    assert item_count() == 1

def test_retrieve_saved_item():
    item = create_item()
    
    response = request("GET", f"/items/{item["id"]}")
    retrieved =  response.json()
    assert retrieved["id"] == item["id"]
    assert retrieved["name"] == item["name"]


@pytest.mark.parametrize("payload", [{}, {"name": 123}])
def test_invalid_input_does_not_insert(payload):
    response =  request("POST", "/items", json=payload)
    
    assert response.status_code == 422, response.text
    assert item_count() == 0

