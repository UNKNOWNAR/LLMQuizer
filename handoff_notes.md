# Handoff Notes for Future Agents

This document outlines the work completed and the unresolved issues encountered while trying to test the application in a Docker container.

## Successful Changes

1.  **Docker Build Optimization:**
    *   A `.dockerignore` file was created to exclude `venv`, `.git`, test files, and other unnecessary assets from the Docker build context. This significantly reduced the build time.
    *   The `requirements.txt` file was cleaned to remove testing-specific dependencies (`pytest`, `pytest-asyncio`, `respx`), resulting in a leaner production image.
    *   The `Dockerfile` syntax was updated from `ENV PORT 8080` to `ENV PORT=8080` to resolve a build warning.

2.  **Container Testing Script:**
    *   A new test script, `test_container.py`, was created to run the `pytest` suite against a running Docker container.
    *   This script was configured to point the HTTP client to `http://localhost:8000`.

3.  **Git Commits:**
    *   All the above changes were successfully committed and pushed to the `master` branch of the remote repository.

## Unresolved Problem: Container Test Failure

The primary goal of testing the running container was not achieved.

**Symptom:** The `test_full_quiz_chain_on_container` test in `test_container.py` consistently fails. The test polls a mock server for submissions from the application, but the submission log is always empty. This indicates that the application running inside the container is failing to communicate with the mock server running on the host.

**Debugging Steps Taken:**

1.  **Docker Networking (`host.docker.internal`):**
    *   Identified that `localhost` inside a container refers to the container itself, not the host machine.
    *   Modified `mock_server.py` to generate URLs using `http://host.docker.internal:8001` when a `DOCKER_TESTING` environment variable was set.
    *   Modified `test_container.py` to set this environment variable and to use `http://host.docker.internal:8001` as the initial URL for the quiz.
    *   Added the `--add-host=host.docker.internal:host-gateway` flag to the `docker run` command to ensure the DNS name resolves.

2.  **Diagnosing Silent Failure:**
    *   The background task in `main.py` appeared to be failing silently, as no errors were appearing in the Docker logs.
    *   To diagnose this, extensive `print()` statements were added to the `process_quiz` and `scrape_page_content` functions in `main.py`.

3.  **Docker Build Caching Issue:**
    *   **This is the core of the unresolved problem.** The new logging statements added to `main.py` never appeared in the container logs, even after multiple attempts to rebuild the image.
    *   The following was attempted to force the new `main.py` into the image:
        *   Rebuilding with `docker build --no-cache ...`
        *   Explicitly adding `COPY main.py .` to the `Dockerfile`.
        *   Removing the final `COPY . .` from the `Dockerfile`.
    *   None of these steps resulted in the updated `main.py` being present in the running container, which points to a fundamental and persistent Docker caching issue or a misunderstanding of the build context.

## Suggested Next Steps

1.  **Solve the Docker Build/Cache Issue:** The immediate priority is to figure out why the `main.py` file is not being updated in the Docker image.
    *   **Suggestion:** Before running `docker build`, try removing the `__pycache__` directory. It's possible some interaction with `.pyc` files is causing this issue.
    *   **Suggestion:** As a drastic measure, run `docker system prune -a` to clear all build caches, images, and containers to start from a truly clean slate.
    *   **Suggestion:** Double-check the contents of the `.dockerignore` file to ensure `main.py` is not being accidentally ignored.

2.  **Diagnose the Background Task:** Once the logging is actually present in the container logs, the real reason for the silent failure can be addressed. The logs should reveal if the error is in Playwright, `httpx`, or elsewhere.

3.  **Alternative Networking:** If the `host.docker.internal` approach continues to fail even after the build issue is fixed, consider creating a dedicated Docker network.
    *   Create a new network: `docker network create quiz-net`
    *   Run the application container on this network: `docker run ... --network quiz-net ...`
    *   Run the `mock_server` in its own Docker container on the same network. This would allow the containers to communicate using their container names as hostnames, which is a more robust solution than relying on host-to-container communication.

Good luck.
