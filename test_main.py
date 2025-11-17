import pytest
import pytest_asyncio
import httpx
import asyncio
import subprocess
import sys
import os
from time import sleep
from unittest.mock import patch, AsyncMock

# Add project root to path to allow importing main
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# from main import app, QuizRequest # No longer needed to import app directly for separate process testing

# --- Fixtures ---

@pytest.fixture(scope="session")
def mock_server():
    """Fixture to run the mock_server.py in a separate process."""
    python_executable = sys.executable
    process = subprocess.Popen([python_executable, "mock_server.py"])
    sleep(2)  # Give the server a moment to start
    yield "http://localhost:8001"
    process.terminate()
    process.wait()

@pytest.fixture(scope="session")
def main_app_server():
    """Fixture to run the main.py application in a separate process."""
    python_executable = sys.executable
    
    # Create a copy of the current environment and set MY_SECRET for the subprocess
    env = os.environ.copy()
    env["MY_SECRET"] = "test-secret" # Set a consistent secret for testing
    
    process = subprocess.Popen([python_executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"], env=env)
    sleep(5)  # Give the server a moment to start
    yield "http://localhost:8000"
    process.terminate()
    process.wait()

@pytest_asyncio.fixture
async def client(main_app_server):
    """Async client for the main FastAPI app."""
    async with httpx.AsyncClient(base_url=main_app_server) as client:
        yield client

# --- Tests ---

@pytest.mark.asyncio
async def test_root_endpoint(client: httpx.AsyncClient):
    """Test the root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Hybrid AI Agent is ready"}

@pytest.mark.asyncio
async def test_invalid_secret(client: httpx.AsyncClient):
    """Test that an invalid secret returns a 403 error."""
    # MY_SECRET is set to "test-secret" by the main_app_server fixture
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
async def test_full_quiz_chain(client: httpx.AsyncClient, mock_server):
    """
    Tests the full end-to-end flow of the quiz chain, including:
    1. Initial Task -> 2. CSV -> 3. PDF -> 4. Image -> 5. Retry -> 6. Stop
    """
    # 1. Define the initial quiz payload, starting at the root
    initial_quiz_url = f"{mock_server}/"
    payload = {
        "email": "test@example.com",
        "secret": "test-secret", # This will be valid
        "url": initial_quiz_url
    }

    # 2. Make the request to start the agent
    response = await client.post("/quiz", json=payload)
    assert response.status_code == 200
    assert response.json() == {"message": "Agent started in background"}

    # 3. Poll the mock server's log to ensure the background task has completed
    max_polls = 40 # Increased polls for the full chain
    poll_interval = 2 # Increased interval for longer tasks like image processing
    
    submission_log = []
    for i in range(max_polls):
        try:
            log_response = await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")
            submission_log = log_response.json()
            
            # The full chain has 6 steps (start, csv, pdf, image, retry1, retry2, stop)
            # But the retry logic is complex. We expect at least 6 submissions.
            # start, csv, pdf, image, retry_fail, retry_success, stop
            if len(submission_log) >= 7:
                break
            
            print(f"Polling... ({i+1}/{max_polls}) - Submissions so far: {len(submission_log)}")
            await asyncio.sleep(poll_interval)
        except httpx.ConnectError as e:
            print(f"Connection error while polling: {e}")
            await asyncio.sleep(poll_interval) # Wait before retrying
    else:
        pytest.fail(f"Mock server did not receive all submissions. Final log: {submission_log}")

    # 4. Assertions on the submission log
    assert len(submission_log) >= 7, "Expected at least 7 submissions for the full chain"
    
    # Check the URLs submitted to ensure the chain was followed
    submitted_urls = [item.get("url") for item in submission_log]
    
    assert f"{mock_server}/" in submitted_urls
    assert f"{mock_server}/mock-quiz/csv" in submitted_urls
    assert f"{mock_server}/mock-quiz/pdf" in submitted_urls
    assert f"{mock_server}/mock-quiz/image" in submitted_urls
    # For the retry test, the same URL will be submitted twice
    assert submitted_urls.count(f"{mock_server}/mock-quiz/retry-test") == 2
    assert f"{mock_server}/mock-quiz/stop-test" in submitted_urls
    
    # Check a few answers for correctness (can be brittle, but good for sanity)
    # The AI is non-deterministic, so we check for expected types or keywords.
    assert submission_log[0]["answer"] == "start" # First answer should be "start"
    assert isinstance(submission_log[1]["answer"], int) # CSV answer is a number
    assert "supercalifragilisticexpialidocious" in submission_log[2]["answer"] # TXT answer
    assert isinstance(submission_log[3]["answer"], str) # Image answer is a string
    assert "paris" in str(submission_log[5]["answer"]).lower() # Successful retry answer
    assert submission_log[6]["answer"] == 4 # Stop test answer
@pytest.mark.asyncio
async def test_404_not_found(client: httpx.AsyncClient):
    """Test that a request to a non-existent endpoint returns a 404 error."""
    response = await client.get("/non-existent-endpoint")
    assert response.status_code == 404

@pytest.mark.asyncio
@pytest.mark.parametrize("payload, expected_detail", [
    ("this is not json", "JSON decode error"), # Malformed JSON
    ({"email": "test@example.com", "secret": "s"}, "Field required"), # Missing 'url'
    ({"email": "test@example.com", "url": "u"}, "Field required"), # Missing 'secret'
    ({"secret": "s", "url": "u"}, "Field required"), # Missing 'email'
])
async def test_422_invalid_payload(client: httpx.AsyncClient, payload, expected_detail):
    """Tests the server's response to various malformed or incomplete payloads."""
    if isinstance(payload, str):
        headers = {"Content-Type": "application/json"}
        response = await client.post("/quiz", content=payload, headers=headers)
    else:
        response = await client.post("/quiz", json=payload)
    
    assert response.status_code == 422
    # FastAPI's validation error messages can be complex. We just check for a key part.
    assert expected_detail in response.text

# --- Edge Case Tests ---

@pytest.mark.asyncio
async def test_broken_link_graceful_failure(client: httpx.AsyncClient, mock_server):
    """Tests that the agent handles a broken data file link gracefully."""
    quiz_url = f"{mock_server}/mock-quiz/broken-link"
    payload = {"email": "test@example.com", "secret": "test-secret", "url": quiz_url}

    response = await client.post("/quiz", json=payload)
    assert response.status_code == 200

    # Poll the log
    for _ in range(10):
        await asyncio.sleep(1)
        log_response = await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")
        submission_log = log_response.json()
        if len(submission_log) > 0:
            break
    else:
        pytest.fail("Mock server did not receive submission for broken link test.")

    # The agent should submit an error message as the answer
    assert len(submission_log) == 1
    submitted_answer = submission_log[0].get("answer", "")
    assert "Error" in submitted_answer

@pytest.mark.asyncio
async def test_llm_failure_graceful_handling(client: httpx.AsyncClient, mock_server):
    """Tests that the agent handles a confusing prompt by submitting a generic error."""
    quiz_url = f"{mock_server}/mock-quiz/llm-fail"
    payload = {"email": "test@example.com", "secret": "test-secret", "url": quiz_url}

    response = await client.post("/quiz", json=payload)
    assert response.status_code == 200

    # Poll the log
    for _ in range(10):
        await asyncio.sleep(1)
        log_response = await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")
        submission_log = log_response.json()
        if len(submission_log) > 0:
            break
    else:
        pytest.fail("Mock server did not receive submission for LLM failure test.")

    # The agent should submit the generic "AI could not determine" error
    assert len(submission_log) == 1
    submitted_answer = submission_log[0].get("answer", "")
    assert submitted_answer == "Error: AI could not determine the answer."

