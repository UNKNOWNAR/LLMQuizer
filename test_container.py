import pytest
import pytest_asyncio
import httpx
import asyncio
import subprocess
import sys
import os
from time import sleep

# This test file is designed to run against a running Docker container.
# It assumes the main application is accessible at http://localhost:8000.

# --- Fixtures ---

@pytest.fixture(scope="session")
def mock_server():
    """Fixture to run the mock_server.py in a separate process."""
    # Ensure we use the python from the correct venv if possible
    python_executable = sys.executable
    
    # Set DOCKER_TESTING=true so the mock server uses host.docker.internal
    env = os.environ.copy()
    env["DOCKER_TESTING"] = "true"
    
    process = subprocess.Popen([python_executable, "mock_server.py"], env=env)
    sleep(2)  # Give the server a moment to start
    yield "http://localhost:8001"
    process.terminate()
    process.wait()

@pytest_asyncio.fixture
async def client():
    """Async client that points to the running Docker container."""
    # The main_app_server fixture is intentionally omitted.
    # These tests run against the container exposed on localhost:8000.
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        yield client

# --- Tests ---

@pytest.mark.asyncio
async def test_root_endpoint(client: httpx.AsyncClient):
    """Test the root endpoint of the container."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Hybrid AI Agent is ready"}

@pytest.mark.asyncio
async def test_invalid_secret(client: httpx.AsyncClient):
    """Test that an invalid secret returns a 403 error."""
    # The MY_SECRET in the container is set by the .env file.
    # We assume it's not 'wrong-secret'.
    payload = {
        "email": "test@example.com",
        "secret": "wrong-secret", # This will be invalid
        "url": "http://example.com"
    }
    response = await client.post("/quiz", json=payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "Unauthorized: Invalid secret key"}

@pytest_asyncio.fixture(autouse=True)
async def clear_mock_server_log(mock_server):
    """Fixture to clear the mock server's submission log before each test."""
    async with httpx.AsyncClient() as client:
        await client.get(f"{mock_server}/mock-submit/clear")

@pytest.mark.asyncio
async def test_full_quiz_chain_on_container(client: httpx.AsyncClient, mock_server):
    """
    Tests the full end-to-end flow of the quiz chain on the container.
    """
    # The MY_SECRET and MY_EMAIL for the payload must match the .env file
    # used to run the container.
    my_email = os.getenv("MY_EMAIL", "test@example.com")
    my_secret = os.getenv("MY_SECRET", "my-secret-value")

    # Use host.docker.internal for the container to reach the host
    initial_quiz_url = "http://host.docker.internal:8001/"
    
    payload = {
        "email": my_email,
        "secret": my_secret,
        "url": initial_quiz_url
    }
    response = await client.post("/quiz", json=payload)
    assert response.status_code == 200
    assert response.json() == {"message": "Agent started in background"}

    # Poll the mock server's log to ensure the background task has completed
    max_polls = 40
    poll_interval = 2
    
    submission_log = []
    for i in range(max_polls):
        try:
            log_response = await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")
            submission_log = log_response.json()
            if len(submission_log) >= 7:
                break
            print(f"Polling container test... ({i+1}/{max_polls}) - Submissions: {len(submission_log)}")
            await asyncio.sleep(poll_interval)
        except httpx.ConnectError as e:
            print(f"Connection error while polling mock server: {e}")
            await asyncio.sleep(poll_interval)
    else:
        pytest.fail(f"Mock server did not receive all submissions from container. Final log: {submission_log}")

    # Assertions on the submission log
    assert len(submission_log) >= 7, "Expected at least 7 submissions for the full chain"
    
    submitted_urls = [item.get("url") for item in submission_log]
    assert f"{mock_server}/" in submitted_urls
    assert f"{mock_server}/mock-quiz/csv" in submitted_urls
    assert f"{mock_server}/mock-quiz/pdf" in submitted_urls
    assert f"{mock_server}/mock-quiz/image" in submitted_urls
    assert submitted_urls.count(f"{mock_server}/mock-quiz/retry-test") == 2
    assert f"{mock_server}/mock-quiz/stop-test" in submitted_urls
    
    # Check a few answers for correctness
    assert submission_log[0]["answer"] == "start"
    assert isinstance(submission_log[1]["answer"], int)
    assert "supercalifragilisticexpialidocious" in submission_log[2]["answer"]
    assert isinstance(submission_log[3]["answer"], str)
    assert "paris" in str(submission_log[5]["answer"]).lower()
    assert submission_log[6]["answer"] == 4
