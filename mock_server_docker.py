import uvicorn
import base64
import json
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response

app = FastAPI()

# --- CONFIGURATION ---
# CRITICAL: This URL allows the Agent (inside Docker) to talk to this Server (on Laptop)
HOST_URL = "http://host.docker.internal:8001"


# --- HELPER: JS Obfuscator ---
def render_obfuscated_page(html_content: str):
    """
    Wraps HTML in the exact Base64/JS pattern used by the real evaluation.
    """
    b64_content = base64.b64encode(html_content.encode()).decode()
    return f"""
    <html>
    <head><title>Quiz Page</title></head>
    <body>
        <div id="content">Loading...</div>
        <script>
            // Simulate the evaluation environment
            document.body.style.backgroundColor = "#f0f0f0";
            setTimeout(() => {{
                const decoded = atob("{b64_content}");
                document.getElementById("content").innerHTML = decoded;
            }}, 200); // Small delay to mimic network
        </script>
    </body>
    </html>
    """


# --- ENDPOINTS: File Hosting ---
@app.get("/files/{filename}")
def get_file(filename: str):
    # Serve files from the current directory
    if not os.path.exists(filename):
        # Helpful error message if you forgot to create the file
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found. Please create it manually in the folder.",
        )

    # Determine media type
    media_type = "application/octet-stream"
    if filename.endswith(".csv"):
        media_type = "text/csv"
    if filename.endswith(".txt"):
        media_type = "text/plain"
    if filename.endswith(".png"):
        media_type = "image/png"

    return FileResponse(filename, media_type=media_type)


# --- ENDPOINTS: Quiz Pages ---


@app.get("/", response_class=HTMLResponse)
def get_start_page():
    """Level 1: The Entry Point (served at root)"""
    html = f"""
    <h1>Quiz Challenge Started</h1>
    <p>Welcome to the automated agent test.</p>
    <p><strong>Task:</strong> Simply reply with the word "start" to begin.</p>
    <p>Post your answer to: <strong>{HOST_URL}/submit</strong></p>
    """
    return render_obfuscated_page(html)


@app.get("/quiz/csv", response_class=HTMLResponse)
def get_csv_page():
    """Level 2: CSV Analysis"""
    # Assumes 'local_cities.csv' exists in your folder
    html = f"""
    <h1>Question 1: Data Analysis</h1>
    <p>Please download the data file from: <a href="{HOST_URL}/files/local_cities.csv">local_cities.csv</a></p>
    <p><strong>Question:</strong> What is the total sum of the 'Population' column?</p>
    <p>Post your answer to: <strong>{HOST_URL}/submit</strong></p>
    """
    return render_obfuscated_page(html)


@app.get("/quiz/txt", response_class=HTMLResponse)
def get_txt_page():
    """Level 3: Text Extraction"""
    # Assumes 'secret.txt' exists in your folder
    html = f"""
    <h1>Question 2: Information Retrieval</h1>
    <p>We have intercepted a document: <a href="{HOST_URL}/files/secret.txt">secret.txt</a></p>
    <p><strong>Question:</strong> What is the secret code mentioned in the text?</p>
    <p>Post your answer to: <strong>{HOST_URL}/submit</strong></p>
    """
    return render_obfuscated_page(html)


@app.get("/quiz/image", response_class=HTMLResponse)
def get_image_page():
    """Level 4: Vision Analysis"""
    # Assumes 'test_image.png' exists in your folder
    html = f"""
    <h1>Question 3: Visual Intelligence</h1>
    <p>Look at this image: <a href="{HOST_URL}/files/test_image.png">test_image.png</a></p>
    <p><strong>Question:</strong> What is the magic number written in the image?</p>
    <p>Post your answer to: <strong>{HOST_URL}/submit</strong></p>
    """
    return render_obfuscated_page(html)


# --- ENDPOINT: Submission Handler ---
@app.post("/submit")
async def handle_submission(request: Request):
    data = await request.json()
    print(f"\n[Server] Received Submission: {json.dumps(data, indent=2)}")

    user_answer = str(data.get("answer", "")).lower().strip()
    current_url = data.get("url", "")

    response_data = {"correct": False, "reason": "Incorrect", "url": None}

    # 1. Start Page Logic
    if current_url.endswith("8001") or current_url.endswith("8001/"):  # Root
        if "start" in user_answer:
            print("[Server] Level 1 Passed.")
            response_data = {
                "correct": True,
                "url": f"{HOST_URL}/quiz/csv",
                "reason": "Good start.",
            }

    # 2. CSV Page Logic
    elif "csv" in current_url:
        # IMPORTANT: Update this logic if your manual CSV has a different sum!
        # Default check for the sample CSV sum (16800000)
        if "16800000" in user_answer:
            print("[Server] Level 2 (CSV) Passed.")
            response_data = {
                "correct": True,
                "url": f"{HOST_URL}/quiz/txt",
                "reason": "Sum calculation correct.",
            }
        else:
            print(f"[Server] CSV Fail. Got {user_answer}")

    # 3. TXT Page Logic
    elif "txt" in current_url:
        # IMPORTANT: Update this logic if your manual text file has a different code!
        if "bluesky" in user_answer:
            print("[Server] Level 3 (TXT) Passed.")
            response_data = {
                "correct": True,
                "url": f"{HOST_URL}/quiz/image",
                "reason": "Secret code found.",
            }
        else:
            print(f"[Server] TXT Fail. Got {user_answer}")

    # 4. Image Page Logic
    elif "image" in current_url:
        # IMPORTANT: Update this logic for your manual image!
        if "42" in user_answer:
            print("[Server] Level 4 (Image) Passed.")
            response_data = {
                "correct": True,
                "url": None,  # End of chain
                "reason": "Vision task correct. All tests passed!",
            }
        else:
            print(f"[Server] Image Fail. Got {user_answer}")

    return JSONResponse(content=response_data)


if __name__ == "__main__":
    print(f"--- Starting Mock Server on 0.0.0.0:8001 ---")
    print(f"--- External Docker URL: {HOST_URL} ---")
    uvicorn.run(app, host="0.0.0.0", port=8001)
