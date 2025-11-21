import uvicorn
import base64
import json
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse

app = FastAPI()

# --- CONFIGURATION ---
# UPDATE THIS URL every time you restart your tunnel (ngrok/localhost.run)
BASE_URL = "https://unhasty-felica-vigilant.ngrok-free.dev"

# Global variable to track submissions
_submission_log = []

# Path helpers for repo-local dummy files
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
DEMO_FILES_DIR = os.path.join(ROOT_DIR, "demo_files")
DUMMY_CSV = os.path.join(DEMO_FILES_DIR, "Dummy_CSV__sales_.csv")
DUMMY_TXT = os.path.join(DEMO_FILES_DIR, "dummy_notes.txt")
DUMMY_PNG = os.path.join(DEMO_FILES_DIR, "dummy_table.png")
DUMMY_JPG = os.path.join(DEMO_FILES_DIR, "dummy_table.jpg")
DUMMY_PDF = os.path.join(DEMO_FILES_DIR, "dummy_doc.pdf")


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
    return JSONResponse(content={"correct": True, "url": None, "reason": "Initial task correct."})

@app.post("/mock-submit/csv")
async def mock_submit_csv(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "CSV")
    return JSONResponse(content={"correct": True, "url": None, "reason": "CSV task correct."})

@app.post("/mock-submit/txt")
async def mock_submit_txt(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "TXT")
    return JSONResponse(content={"correct": True, "url": None, "reason": "TXT task correct."})

@app.post("/mock-submit/pdf")
async def mock_submit_pdf(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "PDF")
    return JSONResponse(content={"correct": True, "url": None, "reason": "PDF task correct."})

@app.post("/mock-submit/image")
async def mock_submit_image(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "IMAGE")
    return JSONResponse(content={"correct": True, "url": None, "reason": "Image task correct."})

@app.post("/mock-submit/pdf")
async def mock_submit_pdf(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "PDF")
    return JSONResponse(content={"correct": True, "url": None, "reason": "All tasks completed successfully!"})

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
        # Q0: Start - Simple text answer
        html_content = f"""
        <h2>Q0. The Start of the Test</h2>
        <p>This is the first task. The answer is simply the string "start".</p>
        <p>Post your answer to {BASE_URL}/mock-submit/start with this JSON payload:</p>
        <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/",
  "answer": "start"
}}
        </pre>
        """

    # --- FIX: AUTO-REPLACE LOCALHOST ---
    # This ensures that even if test.html has 'localhost', it gets swapped for the tunnel URL.
    html_content = html_content.replace("http://localhost:8001", BASE_URL)
    
    b64_content = base64.b64encode(html_content.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/csv", response_class=HTMLResponse)
def get_csv_quiz():
    # Q1: CSV file analysis
    question_html = f"""
    <h2>Q1. CSV Data Analysis</h2>
    <p>Download <a href="{BASE_URL}/files/sales.csv">sales data CSV</a>.</p>
    <p>What is the sum of all values in the CSV file?</p>
    <p>Post your answer to {BASE_URL}/mock-submit/csv with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/csv",
  "answer": 12345  // sum of values
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/txt", response_class=HTMLResponse)
def get_txt_quiz():
    # Q2: TXT file secret extraction
    question_html = f"""
    <h2>Q2. Text File Secret</h2>
    <p>Download <a href="{BASE_URL}/files/simple.txt">text file</a>.</p>
    <p>What is the secret word in quotes?</p>
    <p>Post your answer to {BASE_URL}/mock-submit/txt with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/txt",
  "answer": "secret-word"
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/image", response_class=HTMLResponse)
def get_image_quiz():
    # Q3: Image analysis
    question_html = f"""
    <h2>Q3. Image Analysis</h2>
    <p>Analyze <a href="{BASE_URL}/files/PNG_Test.png">this image</a>.</p>
    <p>What is the main subject or content of the image?</p>
    <p>Post your answer to {BASE_URL}/mock-submit/image with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/image",
  "answer": "description of image"
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/pdf", response_class=HTMLResponse)
def get_pdf_quiz():
    # Q4: PDF document
    question_html = f"""
    <h2>Q4. PDF Document</h2>
    <p>Download <a href="{BASE_URL}/files/dummy_doc.pdf">PDF document</a>.</p>
    <p>What information is contained in the PDF?</p>
    <p>Post your answer to {BASE_URL}/mock-submit/pdf with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/pdf",
  "answer": "pdf content summary"
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/stop-test", response_class=HTMLResponse)
def get_stop_quiz():
    question_html = f"""
    <h2>Q5: Stop Task</h2>
    <p>What is 2+2?</p>
    <p>Post your answer to {BASE_URL}/mock-submit/stop.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

# --- Edge Case Quizzes ---
@app.get("/mock-quiz/broken-link", response_class=HTMLResponse)
def get_broken_link_quiz():
    question_html = f"""
    <h2>Edge Case: Broken Link</h2>
    <p>Download <a href="{BASE_URL}/files/non-existent-file.csv">file</a>.</p>
    <p>Post to {BASE_URL}/mock-submit/broken-link.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/llm-fail", response_class=HTMLResponse)
def get_llm_fail_quiz():
    question_html = f"""
    <h2>Edge Case: LLM Fail</h2>
    <p>Respond with invalid JSON key.</p>
    <p>Post to {BASE_URL}/mock-submit/llm-fail.</p>
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