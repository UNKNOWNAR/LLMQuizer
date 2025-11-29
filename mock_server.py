import uvicorn
import base64
import json
import os
import io
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

@app.get("/files/data.json")
def get_json_data():
    """JSON file for testing JSON parsing"""
    data = {
        "sales": [
            {"product": "A", "quantity": 100, "price": 10.5},
            {"product": "B", "quantity": 200, "price": 15.75},
            {"product": "C", "quantity": 150, "price": 20.0}
        ],
        "total_revenue": 6525.0
    }
    return JSONResponse(content=data)


# --- 2. FAKE SUBMISSION ENDPOINTS ---
@app.post("/mock-submit/start")
async def mock_submit_start(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "START")
    if data.get("answer") == "start":
         return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/csv", "reason": "Initial task correct."})
    return JSONResponse(content={"correct": False, "url": None, "reason": "Incorrect answer."})

@app.post("/mock-submit/csv")
async def mock_submit_csv(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "CSV")
    answer = data.get("answer")
    if answer == 800:  # Sum of value column in CSV file
        return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/txt", "reason": "CSV task correct."})
    return JSONResponse(content={"correct": False, "url": None, "reason": "Incorrect answer."})

@app.post("/mock-submit/txt")
async def mock_submit_txt(request: Request):
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "TXT")
    answer = data.get("answer")
    if "secret-word" in str(answer) or "supercalifragilisticexpialidocious" in str(answer) or answer == 12 or answer == 45:
        return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/pdf", "reason": "TXT task correct."})
    return JSONResponse(content={"correct": False, "url": None, "reason": "Incorrect answer."})

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
    return JSONResponse(content={"correct": True, "url": f"{BASE_URL}/mock-quiz/json-object", "reason": "Image task correct."})

@app.post("/mock-submit/json-object")
async def mock_submit_json_object(request: Request):
    """Test JSON object answer format"""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "JSON-OBJECT")
    
    # Validate that answer is a JSON object with expected fields
    answer = data.get("answer", {})
    if isinstance(answer, dict) and "sum" in answer and "count" in answer:
        return JSONResponse(content={
            "correct": True, 
            "url": f"{BASE_URL}/mock-quiz/base64-image", 
            "reason": "JSON object answer correct."
        })
    else:
        return JSONResponse(content={
            "correct": False,
            "url": f"{BASE_URL}/mock-quiz/retry",  # Give next URL even on wrong answer
            "reason": "Expected JSON object with 'sum' and 'count' fields."
        })

@app.post("/mock-submit/base64-image")
async def mock_submit_base64_image(request: Request):
    """Test base64 data URI answer format"""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "BASE64-IMAGE")
    
    answer = data.get("answer", "")
    # Check if answer is a base64 data URI
    if isinstance(answer, str) and answer.startswith("data:image/"):
        return JSONResponse(content={
            "correct": True,
            "url": f"{BASE_URL}/mock-quiz/boolean",
            "reason": "Base64 image received successfully."
        })
    else:
        return JSONResponse(content={
            "correct": False,
            "url": None,
            "reason": "Expected base64 data URI starting with 'data:image/'"
        })

@app.post("/mock-submit/boolean")
async def mock_submit_boolean(request: Request):
    """Test boolean answer format"""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "BOOLEAN")
    
    answer = data.get("answer")
    if isinstance(answer, bool):
        return JSONResponse(content={
            "correct": True,
            "url": f"{BASE_URL}/mock-quiz/stop-test",
            "reason": "Boolean answer correct."
        })
    else:
        return JSONResponse(content={
            "correct": False,
            "url": None,
            "reason": f"Expected boolean, got {type(answer).__name__}"
        })

@app.post("/mock-submit/wrong-then-next")
async def mock_submit_wrong_then_next(request: Request):
    """Test re-submission scenario: wrong answer but provides next URL"""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "WRONG-THEN-NEXT")
    
    return JSONResponse(content={
        "correct": False,
        "url": f"{BASE_URL}/mock-quiz/retry",
        "reason": "Answer incorrect, but here's the next URL to continue."
    })

@app.post("/mock-submit/retry")
async def mock_submit_retry(request: Request):
    """Test retry after wrong answer"""
    data = await request.json()
    _submission_log.append(data)
    print_submission(data, "RETRY")
    
    return JSONResponse(content={
        "correct": True,
        "url": None,
        "reason": "Retry successful! Quiz complete."
    })

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
    """Serves the main `html`."""
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
    <p>What is the value of alpha in the table?</p>
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
    <p>What is the value of beta in the table?</p>
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
    <p>What is the sum of the values of measurement A&C in page 2m in the data table?</p>
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

@app.get("/mock-quiz/json-object", response_class=HTMLResponse)
def get_json_object_quiz():
    """Quiz requiring JSON object as answer"""
    question_html = f"""
    <h2>Q5. JSON Object Answer</h2>
    <p>Download <a href="{BASE_URL}/files/data.json">JSON data file</a>.</p>
    <p>Calculate the sum of all quantities and the count of products.</p>
    <p>Return your answer as a JSON object with two fields: "sum" and "count".</p>
    <p>Post your answer to {BASE_URL}/mock-submit/json-object with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/json-object",
  "answer": {{"sum": 450, "count": 3}}
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/base64-image", response_class=HTMLResponse)
def get_base64_image_quiz():
    """Quiz requiring base64 image as answer"""
    question_html = f"""
    <h2>Q6. Generate Chart as Base64</h2>
    <p>Download <a href="{BASE_URL}/files/data.json">JSON data file</a>.</p>
    <p>Create a bar chart showing product quantities and return it as a base64 data URI.</p>
    <p>The answer should be a string starting with "data:image/png;base64,..."</p>
    <p>Post your answer to {BASE_URL}/mock-submit/base64-image with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/base64-image",
  "answer": "data:image/png;base64,iVBORw0KGgoAAAANS..."
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/boolean", response_class=HTMLResponse)
def get_boolean_quiz():
    """Quiz requiring boolean answer"""
    question_html = f"""
    <h2>Q7. Boolean Answer</h2>
    <p>Download <a href="{BASE_URL}/files/sales.csv">sales data CSV</a>.</p>
    <p>Are there more than 5 rows in the CSV file? Answer with true or false.</p>
    <p>Post your answer to {BASE_URL}/mock-submit/boolean with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/boolean",
  "answer": true
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/wrong-answer", response_class=HTMLResponse)
def get_wrong_answer_quiz():
    """Quiz that will return wrong answer with next URL"""
    question_html = f"""
    <h2>Q8. Re-submission Test</h2>
    <p>What is 2 + 2? (This will be marked wrong to test re-submission flow)</p>
    <p>Post your answer to {BASE_URL}/mock-submit/wrong-then-next with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/wrong-answer",
  "answer": 4
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/retry", response_class=HTMLResponse)
def get_retry_quiz():
    """Retry quiz page"""
    question_html = f"""
    <h2>Q9. Retry</h2>
    <p>This is a retry step.</p>
    <p>Post your answer to {BASE_URL}/mock-submit/retry with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/retry",
  "answer": "retry"
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/broken-link", response_class=HTMLResponse)
def get_broken_link_quiz():
    """Quiz with a broken link"""
    question_html = f"""
    <h2>Broken Link Test</h2>
    <p>This page has a broken link.</p>
    <p>Post your answer to <a href="{BASE_URL}/does-not-exist">broken link</a>.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/llm-fail", response_class=HTMLResponse)
def get_llm_fail_quiz():
    """Quiz that might confuse the LLM"""
    question_html = f"""
    <h2>LLM Fail Test</h2>
    <p>This page has no clear instructions or submission URL.</p>
    <p>Just some random text.</p>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

@app.get("/mock-quiz/stop-test", response_class=HTMLResponse)
def get_stop_test():
    """Final stop page"""
    question_html = f"""
    <h2>Test Complete</h2>
    <p>The test is finished.</p>
    <p>Post your answer to {BASE_URL}/mock-submit/stop with this JSON payload:</p>
    <pre>
{{
  "email": "your-email",
  "secret": "your-secret",
  "url": "{BASE_URL}/mock-quiz/stop-test",
  "answer": "stop"
}}
    </pre>
    """
    b64_content = base64.b64encode(question_html.encode()).decode()
    return create_js_page(b64_content)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)