import os
import re
import json
import base64
import asyncio
import logging
import io
from urllib.parse import urljoin
from typing import Optional, Any

import httpx
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import JSONResponse
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

# Env Vars
PORT = int(os.getenv("PORT", 8080))
MY_SECRET = os.getenv("MY_SECRET", "my-secret-value")
MY_EMAIL = os.getenv("MY_EMAIL", "test@example.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Setup Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- ENDPOINTS ---
@app.get("/")
def root():
    return {"status": "Hybrid AI Agent is ready", "service": "LLMQuizer"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/quiz")
async def start_quiz(request: Request, background: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON decode error")

    email = payload.get("email")
    secret = payload.get("secret")
    start_url = payload.get("url")

    if not email or not secret or not start_url:
        raise HTTPException(status_code=400, detail="Missing fields")

    if secret != MY_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Secret")
    
    if not GROQ_API_KEY:
        logger.critical("GROQ_API_KEY missing.")
        raise HTTPException(status_code=500, detail="Server misconfiguration: GROQ_API_KEY")
    
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY missing. Image tasks will fail.")

    logger.info(f"Starting agent for {email}")
    background.add_task(run_agent_chain, start_url, email, secret)
    return JSONResponse(status_code=200, content={"message": "Agent started"})

# --- AI HELPERS ---
async def query_groq(client: httpx.AsyncClient, prompt: str, json_mode: bool = True) -> Optional[Any]:
    if not GROQ_API_KEY: return None
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        if json_mode: payload["response_format"] = {"type": "json_object"}

        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload, timeout=20.0
        )
        
        if response.status_code != 200:
            logger.error(f"[Groq] Error {response.status_code}: {response.text}")
            return None

        content = response.json()["choices"][0]["message"]["content"]
        if json_mode:
            # Clean up potential markdown formatting
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*$", "", content)
            return json.loads(content)
        return content
    except Exception as e:
        logger.error(f"[Groq] Exception: {e}")
        return None

async def answer_image_gemini(client: httpx.AsyncClient, img_url: str, question_context: str):
    try:
        resp = await client.get(img_url)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))

        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        Analyze this image and answer the question embedded in this text: "{question_context}".
        Return a JSON object with a single key "answer".
        Example: {{'answer': 'A red cat'}}
        """
        response = await model.generate_content_async([prompt, img])
        
        text = response.text
        # Clean up potential markdown formatting
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        data = json.loads(text)
        return data.get("answer")
    except Exception as e:
        logger.error(f"[Gemini] Error: {e}")
        return "Error processing image"

async def answer_audio_gemini(client: httpx.AsyncClient, audio_url: str, question_context: str):
    try:
        import tempfile
        logger.info(f"Downloading audio: {audio_url}")
        resp = await client.get(audio_url)
        resp.raise_for_status()
        
        # Save to temp file for Gemini
        suffix = os.path.splitext(audio_url)[1] or ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name
            
        try:
            logger.info("Uploading audio to Gemini...")
            audio_file = genai.upload_file(tmp_path)
            
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"""
            Listen to this audio and answer the question: "{question_context}".
            Return a JSON object with a single key "answer".
            """
            response = await model.generate_content_async([prompt, audio_file])
            
            text = response.text
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*$", "", text)
            data = json.loads(text)
            return data.get("answer")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception as e:
        logger.error(f"[Gemini Audio] Error: {e}")
        return "Error processing audio"

def extract_submit_url(html_content: str) -> Optional[str]:
    """
    Extracts the submission URL from HTML content, prioritizing regex and falling back to an LLM.
    """
    # 1. Split at <pre> (handling attributes) to ignore example payloads
    # Using case-insensitive split to be safe
    parts = re.split(r'<pre[^>]*>', html_content, flags=re.IGNORECASE)
    instruction_part = parts[0]
    
    # Debug log to see what we are searching in
    # logger.info(f"Searching for URL in: {instruction_part[:200]}...")

    # 2. Try a series of regex patterns from most specific to most general.
    patterns = [
        # Pattern for: "Post your answer to <strong>URL</strong>"
        r'Post your answer to\s+<strong>\s*(https?://[^\s<]+)\s*</strong>',
        # Pattern for: "Post your answer to URL" (Standard)
        r'Post your answer to\s+(https?://[^\s<]+)',
        # Loose pattern: "answer to ... URL" (Handles extra words/newlines/nbsp)
        r'answer to.*?((?:https?://|/)[^\s<]+)',
        # Very loose fallback: just look for the URL in the instruction part if it contains "mock-submit"
        r'((?:https?://|/)[^\s<]*mock-submit[^\s<]*)',
        # Pattern for: "POSTing JSON to URL" (Project 2 specific)
        r'POSTing\s+JSON\s+to\s+((?:https?://|/)[^\s,]+)',
        # Pattern for: "Submit to: <code>URL</code>"
        r'Submit to:\s*<code>\s*(https?://[^\s<]+)\s*</code>'
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, instruction_part, re.IGNORECASE | re.DOTALL)
        if match:
            url = match.group(1).strip()
            # Clean up trailing punctuation
            if url.endswith('.'):
                url = url[:-1]
            logger.info(f"[Regex-{i+1}] Extracted URL: {url}")
            return url

    logger.warning("All regex patterns failed to find a submission URL.")
    return None

def process_answer(answer: Any) -> Any:
    """
    Process the answer to handle different formats:
    - Convert string booleans ("true"/"false") to actual booleans
    - Keep numbers as numbers
    - Keep strings as strings
    - Keep JSON objects/arrays as-is
    """
    if answer is None:
        return None
    
    # If it's already a dict/list (JSON object/array), return as-is
    if isinstance(answer, (dict, list)):
        return answer
    
    # Convert to string for processing
    answer_str = str(answer).strip()
    
    # Handle boolean strings
    if answer_str.lower() == "true":
        return True
    elif answer_str.lower() == "false":
        return False
    
    # Try to convert to number
    try:
        # Try int first
        if '.' not in answer_str:
            return int(answer_str)
        # Then float
        return float(answer_str)
    except (ValueError, AttributeError):
        pass
    
    # Return as string
    return answer


# --- AGENT LOGIC ---
async def run_agent_chain(start_url: str, email: str, secret: str):
    client_timeout = httpx.Timeout(45.0) 
    async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=True) as client:
        current_url = start_url
        visited = set()
        MAX_STEPS = 15

        for step in range(MAX_STEPS):
            if not current_url or current_url in visited:
                logger.info(f"Stopping chain: current_url is empty or already visited. Current: {current_url}, Visited: {current_url in visited}")
                break
            visited.add(current_url)
            logger.info(f"Step {step+1}: {current_url}")

            try:
                # Add ngrok bypass header only for ngrok URLs (testing)
                headers = {"ngrok-skip-browser-warning": "true"} if "ngrok" in current_url else {}
                resp = await client.get(current_url, headers=headers)
                if resp.status_code >= 400:
                    logger.error(f"Failed to fetch {current_url}, status: {resp.status_code}")
                    break
            except httpx.RequestError as e:
                logger.error(f"Request error fetching {current_url}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error fetching {current_url}: {e}")
                break

            page_text = resp.text
            b64_match = re.search(r'atob\([\'"`]([A-Za-z0-9+/=]+)[\'"`]\)', page_text)
            page_inner = base64.b64decode(b64_match.group(1)).decode(errors="ignore") if b64_match else page_text

            # --- URL EXTRACTION ---
            submit_url = extract_submit_url(page_inner)

            # LLM Fallback if all regex fails
            if not submit_url:
                # Project 2 Specific: Default to /submit if on tds-llm-analysis
                if "tds-llm-analysis.s-anand.net" in current_url:
                    logger.info("[Project 2] Defaulting to /submit endpoint.")
                    submit_url = "https://tds-llm-analysis.s-anand.net/submit"
                else:
                    logger.info("[LLM Fallback] Using LLM to extract submission URL.")
                    prompt = f"""
                    You are an expert web agent. Your task is to find the **submission URL** from the provided HTML snippet.
                    The submission URL is the URL where the answer should be POSTed. It's usually in a phrase like 'Post your answer to...'.
                    **Crucially, you must IGNORE any URLs found inside `<pre>` or `<code>` tags**, as they are examples for the user.
                    Return a JSON object with a single key "submit_url".

                    HTML:
                    {page_inner[-3000:]}
                    """
                    nav_data = await query_groq(client, prompt)
                    submit_url = nav_data.get("submit_url") if nav_data else None
                    if submit_url:
                        logger.info(f"[LLM] Extracted URL: {submit_url}")

            if not submit_url:
                logger.error("Could not determine submission URL. Ending chain.")
                break
            
            submit_url = urljoin(current_url, submit_url)
            logger.info(f"[Final] Resolved URL: {submit_url}")

            # --- FILE & ANSWER LOGIC ---
            file_links = re.findall(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', page_inner)
            norm_files = [urljoin(current_url, link) for link in file_links]
            
            answer = None
            csv_url = next((f for f in norm_files if ".csv" in f.lower()), None)
            txt_url = next((f for f in norm_files if f.endswith((".txt", ".pdf"))), None)
            img_url = next((f for f in norm_files if f.endswith((".png", ".jpg", ".jpeg"))), None)
            audio_url = next((f for f in norm_files if f.endswith((".mp3", ".wav", ".ogg"))), None)

            if csv_url:
                answer = await answer_csv_sum(client, csv_url, page_inner[-1000:])
            elif txt_url:
                # Check if it's actually a PDF
                if txt_url.lower().endswith(".pdf"):
                     answer = await answer_pdf(client, txt_url, page_inner[-1000:])
                else:
                     answer = await answer_txt_secret(client, txt_url, page_inner[-1000:])
            elif img_url:
                logger.info(f"Image found: {img_url}. Sending to Gemini.")
                answer = await answer_image_gemini(client, img_url, page_inner[-1000:])
            elif audio_url:
                logger.info(f"Audio found: {audio_url}. Sending to Gemini.")
                answer = await answer_audio_gemini(client, audio_url, page_inner[-1000:])
            else:
                # If no files, assume it's a simple text question
                logger.info("No specific file type found. Querying LLM for answer from page text.")
                qa_data = await query_groq(client, f"Answer the question or provide the required information from the following text. Return a JSON object with a single key 'answer'. Text: {page_inner[-2000:]}")
                answer = qa_data.get("answer") if qa_data else "start" # Default to "start" if LLM fails

            # Process answer to handle different formats (boolean, number, string, JSON)
            answer = process_answer(answer)

            # --- SUBMISSION ---
            try:
                logger.info(f"Submitting answer: {answer}")
                post_payload = {"email": email, "secret": secret, "url": current_url, "answer": answer}
                post_resp = await client.post(submit_url, json=post_payload)
                
                if post_resp.status_code != 200:
                    logger.error(f"Submission to {submit_url} failed with status {post_resp.status_code}: {post_resp.text}")
                    break

                res = post_resp.json()
                logger.info(f"Submission response: {res}")
                
                # Check if there's a next URL (regardless of correct/incorrect)
                next_url = res.get("url")
                
                if res.get("correct"):
                    logger.info("✓ Answer was correct!")
                    if next_url:
                        current_url = next_url
                        logger.info(f"Moving to next quiz: {next_url}")
                    else:
                        logger.info("Quiz complete! No next URL provided.")
                        break
                else:
                    # Answer was wrong
                    reason = res.get('reason', 'No reason provided')
                    logger.warning(f"✗ Answer was incorrect: {reason}")
                    
                    if next_url:
                        # They gave us the next URL anyway, continue to it
                        logger.info(f"Continuing to next URL despite wrong answer: {next_url}")
                        current_url = next_url
                    else:
                        # No next URL - attempt retry with LLM feedback
                        logger.warning(f"No next URL. Attempting retry with feedback: {reason}")
                        logger.info(f"Previous wrong answer was: {answer}")
                        
                        # Re-attempt with LLM feedback about the incorrect answer
                        retry_prompt = f"""
                        The previous answer was INCORRECT. The system said: "{reason}"
                        
                        Original Question Context:
                        {page_inner[-2000:]}
                        
                        Previous answer that was wrong: {answer}
                        
                        Please analyze why the answer was wrong and provide a CORRECTED answer.
                        Return a JSON object with a single key "answer".
                        """
                        
                        retry_data = await query_groq(client, retry_prompt)
                        retry_answer = retry_data.get("answer") if retry_data else None
                        
                        if retry_answer and retry_answer != answer:
                            # Process and re-submit
                            retry_answer = process_answer(retry_answer)
                            logger.info(f"Retry attempt with new answer: {retry_answer}")
                            
                            retry_payload = {"email": email, "secret": secret, "url": current_url, "answer": retry_answer}
                            retry_resp = await client.post(submit_url, json=retry_payload)
                            
                            if retry_resp.status_code == 200:
                                retry_res = retry_resp.json()
                                logger.info(f"Retry response: {retry_res}")
                                
                                if retry_res.get("correct"):
                                    logger.info("✓ Retry successful!")
                                    retry_next = retry_res.get("url")
                                    if retry_next:
                                        current_url = retry_next
                                    else:
                                        logger.info("Quiz complete after retry!")
                                        break
                                else:
                                    logger.warning(f"Retry also failed: {retry_res.get('reason')}")
                                    # Move to next URL if provided in retry response, otherwise end
                                    retry_next = retry_res.get("url")
                                    if retry_next:
                                        current_url = retry_next
                                    else:
                                        logger.warning("No next URL after retry. Quiz ended.")
                                        break
                            else:
                                logger.error(f"Retry submission failed with status {retry_resp.status_code}")
                                break
                        else:
                            logger.warning("LLM could not generate different answer. Ending quiz.")
                            break
            except httpx.RequestError as e:
                logger.error(f"Request error during submission to {submit_url}: {e}")
                break
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON from submission response: {post_resp.text}")
                break
            except Exception as e:
                logger.error(f"Unexpected exception during submission: {e}")
                break

# --- TASK-SPECIFIC HELPERS ---
async def answer_csv_sum(client, url, question_context=""):
    try:
        logger.info(f"Processing CSV: {url}")
        resp = await client.get(url)
        csv_content = resp.text
        
        # Use LLM to answer the question based on CSV content
        prompt = f"""
        Answer the question based on the following CSV file content.
        Question: {question_context}
        
        CSV Content:
        {csv_content[:5000]}
        
        Return a JSON object with a single key "answer". 
        If the question asks for a sum or calculation, return just the number.
        """
        
        data = await query_groq(client, prompt)
        answer = data.get("answer") if data else 0
        
        # Try to convert to number if it looks like one
        try:
            return int(float(str(answer)))
        except:
            return answer
            
    except Exception as e:
        logger.error(f"Error processing CSV {url}: {e}")
        return 0

async def answer_txt_secret(client, url, question_context=""):
    try:
        logger.info(f"Processing TXT: {url}")
        resp = await client.get(url)
        text_content = resp.text
        
        # Use LLM to answer the question based on text content
        prompt = f"""
        Answer the question based on the following text file content.
        Question: {question_context}
        
        Text File Content:
        {text_content[:5000]}
        
        Return a JSON object with a single key "answer". The answer should be concise (a number, word, or short phrase).
        """
        
        data = await query_groq(client, prompt)
        return data.get("answer") if data else "unknown"
        
    except Exception as e:
        logger.error(f"Error processing TXT {url}: {e}")
        return "error"

async def answer_pdf(client, url, question_context):
    try:
        import pypdf
        logger.info(f"Processing PDF: {url}")
        resp = await client.get(url)
        pdf_file = io.BytesIO(resp.content)
        reader = pypdf.PdfReader(pdf_file)
        
        text_content = ""
        for page in reader.pages:
            text_content += page.extract_text() + "\n"
        
        # Use LLM to answer the question based on PDF content
        prompt = f"""
        Answer the question based on the following PDF content.
        Question: {question_context}
        
        PDF Content:
        {text_content[:10000]} # Limit context size
        
        Return a JSON object with a single key "answer".
        """
        
        data = await query_groq(client, prompt)
        return data.get("answer") if data else "Error processing PDF"
        
    except Exception as e:
        logger.error(f"Error processing PDF {url}: {e}")
        return "Error"
