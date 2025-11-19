import uvicorn
import base64
import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse

app = FastAPI()

# --- CONFIGURATION ---
# UPDATE THIS URL every time you restart your tunnel (ngrok/localhost.run)
BASE_URL = "https://466645bd723bc6.lhr.life"

# Global variable to track submissions
_submission_log = []

# Path helpers for repo-local dummy files
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
DUMMY_CSV = os.path.join(ROOT_DIR, "Dummy_CSV__sales_.csv")
DUMMY_TXT = os.path.join(ROOT_DIR, "dummy_notes.txt")
DUMMY_PNG = os.path.join(ROOT_DIR, "dummy_table.png")
DUMMY_JPG = os.path.join(ROOT_DIR, "dummy_table.jpg")
DUMMY_PDF = os.path.join(ROOT_DIR, "dummy_doc.pdf")


# --- 1. FAKE DATA ENDPOINTS ---
@app.get("/files/local_cities.csv")
def get_local_csv():
    csv_content = """ID,Name,Population
1,New York,8175133
2,Los Angeles,3792621
3,Chicago,2695598
4,Houston,2100263"""
    return Response(content=csv_content.strip(), media_type="text/csv")

@app.get("/files/sales.csv")
def get_sales_csv():
    if os.path.exists(DUMMY_CSV):
        return FileResponse(DUMMY_CSV, media_type="text/csv")
    return JSONResponse(status_code=404, content={"error": "Dummy CSV not found."})

@app.get("/files/simple.txt")
def get_local_txt():
    if os.path.exists(DUMMY_TXT):
        with open(DUMMY_TXT, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/plain")
    return Response(content="The secret word is 'supercalifragilisticexpialidocious'.", media_type="text/plain")

@app.get("/files/PNG_Test.png")
def get_local_image():
    if os.path.exists(DUMMY_PNG):
        return FileResponse(DUMMY_PNG, media_type="image/png")
    if os.path.exists(DUMMY_JPG):
        return FileResponse(DUMMY_JPG, media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": "Test image not found."})

@app.get("/files/dummy_doc.pdf")
def get_dummy_pdf():
    if os.path.exists(DUMMY_PDF):
        return FileResponse(DUMMY_PDF, media_type="application/pdf")
    return JSONResponse(status_code=404, content={"error": "Dummy PDF not found."})


# --- 2. FAKE SUBMISSION ENDPOINTS ---
@app.post("/mock-submit/start")
async def mock_submit_start(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "START")
    return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/csv", "reason": "Initial task correct."})

@app.post("/mock-submit/csv")
async def mock_submit_csv(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "CSV")
    return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/pdf", "reason": "CSV task correct."})

@app.post("/mock-submit/pdf")
async def mock_submit_pdf(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "PDF")
    return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/image", "reason": "PDF task correct."})

@app.post("/mock-submit/image")
async def mock_submit_image(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "IMAGE")
    return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/retry-test", "reason": "Image task correct."})

@app.post("/mock-submit/fail-with-reason")
async def mock_submit_fail(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "RETRY_ATTEMPT")
    
    retry_url = f"{BASE_URL}/mock-quiz/retry-test"
    submission_count = sum(1 for item in _submission_log if item.get("url") == retry_url)

    if submission_count > 1:
        return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/stop-test", "reason": "Retry successful!"})
    
    return JSONResponse(content={"correct": False, "url": None, "reason": "The first answer was wrong. Please try again."})

@app.post("/mock-submit/stop")
async def mock_submit_stop(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "STOP")
    return JSONResponse(content={"correct": True, "url": None, "reason": "Quiz chain finished."})

@app.get("/mock-submit/log")
def get_submission_log():
    return JSONResponse(content=_submission_log)

@app.get("/mock-submit/clear")
def clear_submission_log():
    global _submission_log
    _submission_log = []
    return JSONResponse(content={"status": "cleared"})

def print_submission(data: dict, step: str):
    print(f"\n--- MOCK SERVER RECEIVED SUBMISSION ({step}) ---")
    print(json.dumps(data, indent=2))
    print("-------------------------------------------\n")


# --- 3. FAKE QUIZ PAGES (UPDATED FORMAT) ---
def create_js_page(b64_content: str):
    """
    Creates the exact minimal HTML structure requested.
    It injects the Base64 content into the #result div using JS.
    """
    return f"""<div id="result"></div><script>
  document.querySelector("#result").innerHTML = atob(`{b64_content}`);</script>"""

@app.get("/", response_class=HTMLResponse)
def get_test_html():
    """Serves the main `test.html`."""
    test_html_path = os.path.join(ROOT_DIR, "test.html")
    
    if os.path.exists(test_html_path):
        with open(test_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        # Fallback if file is missing
        html_content = f"""
        <h2>Q0: The Start of the Test</h2>
        <p>This is the first task. The answer is simply the string "start".</p>
        <p>Post your answer to <strong>/mock-submit/start</strong>.</p>
        """

    # --- FIX: AUTO-REPLACE LOCALHOST ---
    # This ensures that even if test.html has 'localhost', it gets swapped for the tunnel URL.
    html_content = html_content.replace("http://localhost:8001", BASE_URL)
    
    b64_content = base64.b64encode(html_content.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/csv", response_class=HTMLResponse)
def get_csv_quiz():
    question_html = f"""
    <h2>Q1: CSV Task</h2>
    <p>Download <a href="{BASE_URL}/files/local_cities.csv">file</a>.</p>
    <p>What is the sum of the "Population" column?</p>
    <p>Post your answer to <strong>/mock-submit/csv</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/pdf", response_class=HTMLResponse)
def get_pdf_quiz():
    question_html = f"""
    <h2>Q2: TXT Task</h2>
    <p>Download <a href="{BASE_URL}/files/simple.txt">file</a>.</p>
    <p>What is the secret word?</p>
    <p>Post your answer to <strong>/mock-submit/pdf</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/image", response_class=HTMLResponse)
def get_image_quiz():
    question_html = f"""
    <h2>Q3: Image Task</h2>
    <p>Analyze <a href="{BASE_URL}/files/PNG_Test.png">image</a>.</p>
    <p>What is the main subject?</p>
    <p>Post your answer to <strong>/mock-submit/image</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/retry-test", response_class=HTMLResponse)
def get_retry_quiz():
    question_html = f"""
    <h2>Q4: Retry Task</h2>
    <p>What is the capital of France?</p>
    <p>Post your answer to <strong>/mock-submit/fail-with-reason</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/stop-test", response_class=HTMLResponse)
def get_stop_quiz():
    question_html = f"""
    <h2>Q5: Stop Task</h2>
    <p>What is 2+2?</p>
    <p>Post your answer to <strong>/mock-submit/stop</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

# --- Edge Case Quizzes ---
@app.get("/mock-quiz/broken-link", response_class=HTMLResponse)
def get_broken_link_quiz():
    question_html = f"""
    <h2>Edge Case: Broken Link</h2>
    <p>Download <a href="{BASE_URL}/files/non-existent-file.csv">file</a>.</p>
    <p>Post to <strong>/mock-submit/broken-link</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/llm-fail", response_class=HTMLResponse)
def get_llm_fail_quiz():
    question_html = f"""
    <h2>Edge Case: LLM Fail</h2>
    <p>Respond with invalid JSON key.</p>
    <p>Post to <strong>/mock-submit/llm-fail</strong>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.post("/mock-submit/broken-link")
async def mock_submit_broken_link(request: Request):
    return JSONResponse(content={"correct": True, "url": None})

@app.post("/mock-submit/llm-fail")
async def mock_submit_llm_fail(request: Request):
    return JSONResponse(content={"correct": True, "url": None})

if __name__ == "__main__":
    print("--- Starting Mock Quiz Server on http://localhost:8001 ---")
    uvicorn.run(app, host="0.0.0.0", port=8001)