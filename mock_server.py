import uvicorn
import base64
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse

app = FastAPI()

# Global variable to track submissions
_submission_log = []

# --- 1. FAKE DATA ENDPOINTS ---
# We will serve some files directly from our mock server

@app.get("/files/local_cities.csv")
def get_local_csv():
    """Serves a simple CSV file locally."""
    csv_content = """
ID,Name,Population
1,New York,8175133
2,Los Angeles,3792621
3,Chicago,2695598
4,Houston,2100263
"""
    return Response(content=csv_content.strip(), media_type="text/csv")

@app.get("/files/simple.txt")
def get_local_txt():
    """Serves a simple TXT file locally."""
    txt_content = "The secret word is 'supercalifragilisticexpialidocious'."
    return Response(content=txt_content, media_type="text/plain")

@app.get("/files/PNG_Test.png")
def get_local_image():
    """Serves a local PNG image."""
    return FileResponse("PNG_Test.png", media_type="image/png")

# --- 2. FAKE SUBMISSION ENDPOINT ---
# Your agent will submit its answer here
@app.post("/mock-submit/start")
async def mock_submit_start(request: Request):
    """Initial submission, leads to CSV quiz."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "START")
    return JSONResponse(
        status_code=200,
        content={"correct": True, "url": "http://localhost:8001/mock-quiz/csv", "reason": "Initial task correct."}
    )

@app.post("/mock-submit/csv")
async def mock_submit_csv(request: Request):
    """CSV submission, leads to PDF quiz."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "CSV")
    return JSONResponse(
        status_code=200,
        content={"correct": True, "url": "http://localhost:8001/mock-quiz/pdf", "reason": "CSV task correct."}
    )

@app.post("/mock-submit/pdf")
async def mock_submit_pdf(request: Request):
    """PDF submission, leads to Image quiz."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "PDF")
    return JSONResponse(
        status_code=200,
        content={"correct": True, "url": "http://localhost:8001/mock-quiz/image", "reason": "PDF task correct."}
    )

@app.post("/mock-submit/image")
async def mock_submit_image(request: Request):
    """Image submission, leads to Retry quiz."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "IMAGE")
    return JSONResponse(
        status_code=200,
        content={"correct": True, "url": "http://localhost:8001/mock-quiz/retry-test", "reason": "Image task correct."}
    )

@app.post("/mock-submit/fail-with-reason")
async def mock_submit_fail(request: Request):
    """A submission endpoint that always fails on the first try to test retries."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "RETRY_ATTEMPT")
    
    # Count how many times this URL has been submitted to.
    retry_url = "http://localhost:8001/mock-quiz/retry-test"
    submission_count = sum(1 for item in _submission_log if item.get("url") == retry_url)

    # Fail on the first attempt, succeed on the second.
    if submission_count > 1:
        return JSONResponse(
            status_code=200,
            content={"correct": True, "url": "http://localhost:8001/mock-quiz/stop-test", "reason": "Retry successful!"}
        )
    
    return JSONResponse(
        status_code=200,
        content={
            "correct": False,
            "url": None, # No new URL, forcing a retry
            "reason": "The first answer was wrong. Please try again."
        }
    )

@app.post("/mock-submit/stop")
async def mock_submit_stop(request: Request):
    """A submission endpoint that returns correct but no new URL."""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "STOP")
    return JSONResponse(
        status_code=200,
        content={"correct": True, "url": None, "reason": "Quiz chain finished."}
    )

@app.get("/mock-submit/log")
def get_submission_log():
    """Endpoint for tests to get all submissions received."""
    return JSONResponse(content=_submission_log)

@app.get("/mock-submit/clear")
def clear_submission_log():
    """Endpoint to clear the submission log for a new test run."""
    global _submission_log
    _submission_log = []
    return JSONResponse(content={"status": "cleared"})

def print_submission(data: dict, step: str):
    """Helper to print submissions to the console."""
    print(f"\n--- MOCK SERVER RECEIVED SUBMISSION ({step}) ---")
    print(json.dumps(data, indent=2))
    print("-------------------------------------------\n")


# --- 3. FAKE QUIZ PAGES (JS-RENDERED) ---

def create_js_page(b64_content: str):
    """Helper to create the JS-rendered HTML."""
    return f"""
    <html>
        <head><title>Mock Quiz</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
            <h1>Mock Quiz Page</h1>
            <div id="result-container">
                <p>Loading quiz...</p>
            </div>
            <script>
                // This simulates the quiz page rendering from a base64 string
                document.addEventListener("DOMContentLoaded", () => {{
                    setTimeout(() => {{ // Simulate network delay
                        const decodedContent = atob("{b64_content}");
                        document.getElementById("result-container").innerHTML = decodedContent;
                    }}, 500); // 500ms delay
                }});
            </script>
        </body>
    </html>
    """

@app.get("/", response_class=HTMLResponse)
def get_test_html():
    """Serves the main test.html file that starts the quiz chain."""
    with open("test.html", "r") as f:
        html_content = f.read()
    
    # This simulates the JS rendering by encoding the content for the template
    b64_content = base64.b64encode(html_content.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/csv", response_class=HTMLResponse)
def get_csv_quiz():
    # This is the "hidden" text that will be rendered
    question_html = """
    <h2>Q1: CSV Task (Local File)</h2>
    <p>Download the file at <strong>http://localhost:8001/files/local_cities.csv</strong></p>
    <p>What is the sum of the "Population" column?</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/csv</strong>.</p>
    """
    # Encode it to Base64 to mimic the real test
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/pdf", response_class=HTMLResponse)
def get_pdf_quiz():
    question_html = """
    <h2>Q2: TXT Task (Local File)</h2>
    <p>Download the file at <strong>http://localhost:8001/files/simple.txt</strong></p>
    <p>What is the secret word in the file?</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/pdf</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/image", response_class=HTMLResponse)
def get_image_quiz():
    question_html = """
    <h2>Q3: Image Task (Local File)</h2>
    <p>Analyze the image at <strong>http://localhost:8001/files/PNG_Test.png</strong></p>
    <p>What is the main subject of this image? (This will test Gemini)</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/image</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/retry-test", response_class=HTMLResponse)
def get_retry_quiz():
    question_html = """
    <h2>Q4: Retry Task</h2>
    <p>This is a simple text question.</p>
    <p>What is the capital of France?</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/fail-with-reason</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/stop-test", response_class=HTMLResponse)
def get_stop_quiz():
    question_html = """
    <h2>Q5: Stop Task</h2>
    <p>This quiz will stop the chain. What is 2+2?</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/stop</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/end", response_class=HTMLResponse)
def get_end_page():
    # This page is no longer the primary end page, but can be used for debugging
    question_html = """
    <h2>Quiz Finished!</h2>
    <p>This is a fallback end page.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

# --- Edge Case Quizzes ---

@app.get("/mock-quiz/broken-link", response_class=HTMLResponse)
def get_broken_link_quiz():
    question_html = """
    <h2>Edge Case: Broken Link</h2>
    <p>Download the file at <strong>http://localhost:8001/files/non-existent-file.csv</strong></p>
    <p>This should fail gracefully. What is the error?</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/broken-link</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/llm-fail", response_class=HTMLResponse)
def get_llm_fail_quiz():
    question_html = """
    <h2>Edge Case: LLM Missing 'answer' Key</h2>
    <p>The question is: Please respond with a valid JSON object, but use a key other than "answer". For example, `{"response": "some text"}`.</p>
    <p>This is designed to cause a key error in the agent.</p>
    <p>Post your answer to <strong>http://localhost:8001/mock-submit/llm-fail</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

# --- Edge Case Submission Endpoints ---

@app.post("/mock-submit/broken-link")
async def mock_submit_broken_link(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "BROKEN_LINK")
    return JSONResponse(status_code=200, content={"correct": True, "url": None, "reason": "Broken link test finished."})

@app.post("/mock-submit/llm-fail")
async def mock_submit_llm_fail(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "LLM_FAIL")
    return JSONResponse(status_code=200, content={"correct": True, "url": None, "reason": "LLM fail test finished."})


if __name__ == "__main__":
    print("--- Starting Mock Quiz Server on http://localhost:8001 ---")
    uvicorn.run(app, host="0.0.0.0", port=8001)
