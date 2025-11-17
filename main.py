import os
import re
import httpx
import asyncio
import io
import sys
import json
import base64
import pdfplumber
import google.generativeai as genai
from PIL import Image
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from groq import Groq
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MY_EMAIL = os.getenv("MY_EMAIL")
MY_SECRET = os.getenv("MY_SECRET")

# --- Clients (Initialized once) ---
app = FastAPI()
groq_client = Groq(api_key=GROQ_API_KEY)
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
http_client = httpx.AsyncClient(timeout=60.0)


class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str


# --- 1. The Scraper (Hands) ---
async def scrape_page_content(url: str):
    """Uses Playwright to visit the URL, run JS, and scrape all text."""
    print("--- scrape_page_content: Starting ---")
    async with async_playwright() as p:
        browser = None
        try:
            print("--- scrape_page_content: Launching browser ---")
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()
            print(f"--- scrape_page_content: Navigating to {url} ---")
            await page.goto(url, timeout=30000, wait_until="networkidle")
            print("--- scrape_page_content: Evaluating page content ---")
            content = await page.evaluate("document.body.innerText")
            if not content:
                content = await page.content()  # Fallback
            print("--- scrape_page_content: Finished successfully ---")
            return content
        except Exception as e:
            print(f"Playwright scrape error: {e}")
            return f"Error: Could not scrape page. {e}"
        finally:
            if browser:
                await browser.close()


# --- 2. The Brain (Hybrid AI) ---
async def get_answer_from_ai(scraped_text: str, feedback: str = None):
    """
    Analyzes scraped text, fetches content from linked files, and asks the
    appropriate AI model (Groq for text, Gemini for images) for the answer.
    """
    # This regex looks for a full URL ending in a common file extension
    match = re.search(
        r'https?://[^\s"\']+\.(csv|pdf|png|jpg|jpeg|gif|txt)', scraped_text, re.IGNORECASE
    )

    # Default to text-based analysis with Groq
    if not match:
        print("No data file found. Using Groq for text analysis.")
        return await get_answer_from_groq(scraped_text, "", feedback)

    data_url = match.group(0)
    print(f"Found data URL: {data_url}")

    try:
        # --- Image Task: Use Gemini 2.5 Flash ---
        if data_url.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            if not GOOGLE_API_KEY:
                return "Error: GOOGLE_API_KEY not configured for image task."
            print("Image file detected. Routing to Gemini...")
            response = await http_client.get(data_url)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content))

            # Force Gemini to return JSON
            gemini_model = genai.GenerativeModel(
                "gemini-2.5-flash",
                generation_config={"response_mime_type": "application/json"},
            )

            prompt_parts = [
                f"""
            Analyze the user's question based on the provided image.
            The user's question is embedded in the following text:
            ---
            {scraped_text}
            ---
            Pay close attention to the required format for the answer on the quiz page.
            You MUST respond in a single, clean JSON object with a single key: "answer".
            - If the answer is a number (e.g., 12345), the JSON should be: {{"answer": 12345}}
            - If the answer is text, the JSON should be: {{"answer": "some text"}}
            - If the answer requires generating a file (like a chart or image), create it and provide it as a base64 encoded data URI string: {{"answer": "data:image/png;base64,iVBORw0KGgo..."}}
            - The value of "answer" can also be a boolean or a JSON object if the question requires it.

            Analyze the question and context carefully to determine the correct data type and format for the final answer. Do not add any other text, explanations, or formatting outside of the single JSON object.
            """
            ]
            if feedback:
                prompt_parts.append(f"\nIMPORTANT FEEDBACK: {feedback}\n")
            prompt_parts.append(img)
            
            try:
                response = await gemini_model.generate_content_async(prompt_parts)
                # The response text is now guaranteed to be a JSON string
                response_data = json.loads(response.text)
                return response_data.get("answer", None) # Return None if 'answer' key not found
            except json.JSONDecodeError as e:
                print(f"Gemini JSON decode error: {e} - Response text: {response.text}")
                return None # Indicate failure to parse JSON
            except Exception as e:
                print(f"Gemini AI Brain error: {e}")
                return None # Indicate general error

        # --- Text Task: Use Groq ---
        elif data_url.lower().endswith((".csv", ".pdf", ".txt")):
            print("Text file detected. Routing to Groq...")
            response = await http_client.get(data_url)
            response.raise_for_status()

            if data_url.lower().endswith(".csv"):
                additional_context = response.text
                print("Extracted text from CSV.")
            elif data_url.lower().endswith(".txt"):
                additional_context = response.text
                print("Extracted text from TXT.")
            else:  # PDF
                with io.BytesIO(response.content) as f:
                    with pdfplumber.open(f) as pdf:
                        all_text = [page.extract_text() or "" for page in pdf.pages]
                        additional_context = "\n".join(all_text)
                        print(f"Extracted text from all {len(pdf.pages)} pages of PDF.")

            return await get_answer_from_groq(scraped_text, additional_context, feedback)

    except Exception as e:
        print(f"AI Brain error: {e}")
        return f"Error during AI analysis: {e}"

    return "Error: Could not determine task type."


async def get_answer_from_groq(scraped_text: str, additional_context: str, feedback: str = None):
    """Sends a text-based query to Groq's Llama3 model."""
    system_prompt = """
You are a master problem solver. You will be given context from a web page and potentially content from a linked file (like a CSV or PDF).
Your job is to analyze all the provided information to answer the question asked on the web page.

Pay close attention to the required format for the answer. The quiz page may specify how the answer should be structured.

You MUST respond in a single, clean JSON object with a single key: "answer".
- If the answer is a number (e.g., 12345), the JSON should be: {"answer": 12345}
- If the answer is text, the JSON should be: {"answer": "some text"}
- If the answer requires generating a file (like a chart or image), create it and provide it as a base64 encoded data URI string: {"answer": "data:image/png;base64,iVBORw0KGgo..."}
- The value of "answer" can also be a boolean or a JSON object if the question requires it.

Analyze the question and context carefully to determine the correct data type and format for the final answer. Do not add any other text, explanations, or formatting outside of the single JSON object.
"""
    user_prompt = f"""
    Your task is to answer the question based *only* on the data provided in the contexts below.
    Do not use any external knowledge. You must, however, perform any necessary analysis or calculations on the data provided to arrive at the answer.
    If a question asks for a specific value, word, or piece of text, you must extract it literally and exactly as it appears in the context.

    Here is the context from the web page:
    ---
    {scraped_text}
    ---

    Here is the content from the linked file (if any):
    ---
    {additional_context}
    ---
    """
    if feedback:
        user_prompt += f"\nIMPORTANT FEEDBACK ON PREVIOUS ATTEMPT: {feedback}\n"
    
    user_prompt += """
    Based *only* on the data provided above, what is the answer to the question? Provide the single, final answer in the specified JSON format.
    """
    try:
        chat_completion = await asyncio.to_thread(
            groq_client.chat.completions.create,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
        )
        response_text = chat_completion.choices[0].message.content
        response_data = json.loads(response_text)
        return response_data.get("answer", None) # Return None if 'answer' key not found
    except json.JSONDecodeError as e:
        print(f"Groq JSON decode error: {e} - Response text: {response_text}")
        return None # Indicate failure to parse JSON
    except Exception as e:
        print(f"Groq AI Brain error: {e}")
        return None # Indicate general error


# --- 3. The Submitter ---
def extract_submit_url(text: str):
    """Finds the submission URL mentioned in the quiz text."""
    print("\n--- EXTRACTING SUBMIT URL ---")
    match = re.search(r'(Post your answer to|submit to|POST this JSON to) (https?://[^\s"\\]+)', text, re.IGNORECASE)
    print(f"Regex match result: {match}")
    if match:
        url = match.group(2).strip('.,')
        print(f"Found URL: {url}")
        return url
    print("Warning: Could not find submit URL in the scraped text.")
    return None


async def submit_answer(submit_url: str, answer, task_url: str):
    payload = {
        "email": MY_EMAIL,
        "secret": MY_SECRET,
        "url": task_url,
        "answer": answer,
    }

    # Check payload size before submission
    payload_str = json.dumps(payload)
    payload_size_bytes = sys.getsizeof(payload_str)
    MAX_PAYLOAD_SIZE_BYTES = 1 * 1024 * 1024 # 1 MB

    if payload_size_bytes > MAX_PAYLOAD_SIZE_BYTES:
        print(f"WARNING: Submission payload size ({payload_size_bytes} bytes) exceeds 1MB limit for URL: {task_url}. Submitting a generic error message instead.")
        payload["answer"] = "Error: Answer payload exceeded 1MB limit."
        # Re-calculate size for the error payload, though it should be small
        payload_str = json.dumps(payload)
        payload_size_bytes = sys.getsizeof(payload_str)
        if payload_size_bytes > MAX_PAYLOAD_SIZE_BYTES:
            print("CRITICAL ERROR: Even the error payload exceeds 1MB. This should not happen.")
            return {"correct": False, "reason": "Critical Error: Even error payload too large."}

    try:
        response = await http_client.post(submit_url, json=payload)
        print(f"Submission Response: {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        print(f"Submit answer failed: {e}")
        return {"correct": False, "reason": str(e)}


import time
# ... (other imports)

# --- 4. The Main Router / Background Task ---
async def process_quiz(request: QuizRequest, start_time: float = None, retry_count: int = 0, feedback: str = None):
    try:
        print("--- process_quiz: Task starting ---")
        MAX_RETRIES = 2 # Allow up to 2 retries for a single quiz

        if start_time is None:
            start_time = time.time()

        # Check for timeout at the beginning of each processing cycle
        if (time.time() - start_time) > 290: # 4 minutes 50 seconds, for a 5-minute limit
            print(f"Timeout reached for quiz chain starting at {request.url}. Stopping.")
            return

        print(f"Processing quiz: {request.url} (Attempt: {retry_count + 1})")
        
        # 1. Scrape
        scraped_text = await scrape_page_content(request.url)
        if "Error:" in scraped_text:
            await submit_answer(
                "https://tds-llm-analysis.s-anand.net/submit", scraped_text, request.url
            )
            return

        # 2. Find Submit URL
        submit_url = extract_submit_url(scraped_text)
        if not submit_url:
            print(f"Error: Could not find submit URL for quiz: {request.url}. Stopping.")
            return

        # 3. Get Answer from Brain (Hybrid)
        answer = await get_answer_from_ai(scraped_text, feedback=feedback)

        if answer is None:
            print(f"Error: AI failed to produce a valid answer for quiz: {request.url}. Submitting error message.")
            answer = "Error: AI could not determine the answer." # Provide a default error message
            # We still attempt to submit this error message, so the quiz server gets a response.

        print(f"Final Answer from AI: {answer}")

        # 4. Submit
        submit_result = await submit_answer(submit_url, answer, request.url)
        
        # 5. Handle Submission Result and Recurse/Retry
        if "url" in submit_result and submit_result["url"]:
            # Always prioritize moving to a new URL if provided
            print(f"New URL provided. Moving to next quiz: {submit_result['url']}")
            next_request = QuizRequest(
                email=request.email, secret=request.secret, url=submit_result["url"]
            )
            # Reset retry count and feedback for the new quiz
            await process_quiz(next_request, start_time=start_time)
        elif not submit_result.get("correct") and retry_count < MAX_RETRIES:
            # If incorrect and no new URL, and retries remaining, try again
            print(f"Answer incorrect. Retrying quiz: {request.url}")
            
            # Prepare feedback for the next attempt
            new_feedback = submit_result.get("reason") or "Your previous answer was incorrect. Please re-evaluate and try again."
            
            await process_quiz(request, start_time=start_time, retry_count=retry_count + 1, feedback=new_feedback)
        else:
            # Quiz chain finished (correct with no new URL, or failed after retries)
            print(f"Quiz chain finished or failed. Reason: {submit_result.get('reason')}")
        print("--- process_quiz: Task finished ---")
    except Exception as e:
        print(f"--- CRITICAL ERROR IN process_quiz ---")
        print(f"Exception: {e}")
        import traceback
        print(traceback.format_exc())


# --- API Endpoints ---
@app.get("/")
def home():
    return {"status": "Hybrid AI Agent is ready"}


@app.post("/quiz")
async def receive_task(request: QuizRequest, background_tasks: BackgroundTasks):
    print("--- receive_task: Endpoint hit ---")
    if request.secret != MY_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid secret key")

    print(f"--- receive_task: Task received for {request.url}, starting background agent. ---")
    background_tasks.add_task(process_quiz, request)
    print("--- receive_task: Background task added. ---")

    return {"message": "Agent started in background"}


@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
