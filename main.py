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

IS_DOCKER = os.getenv("DOCKER_TESTING", "false").lower() in ("1", "true", "yes")
DEFAULT_BASE = "http://host.docker.internal:8001" if IS_DOCKER else "http://localhost:8001"
BASE_URL = os.getenv("BASE_URL", DEFAULT_BASE)

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
        raise HTTPException(status_code=422, detail="JSON decode error")

    email = payload.get("email")
    secret = payload.get("secret")
    start_url = payload.get("url")

    if not email or not secret or not start_url:
        raise HTTPException(status_code=422, detail="Missing fields")

    if secret != MY_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
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
            json=payload, timeout=15.0
        )
        
        if response.status_code != 200:
            logger.error(f"[Groq] Error {response.status_code}: {response.text}")
            return None

        content = response.json()["choices"][0]["message"]["content"]
        if json_mode:
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*$", "", content)
            return json.loads(content)
        return content
    except Exception as e:
        logger.error(f"[Groq] Exception: {e}")
        return None

async def answer_image_gemini(client: httpx.AsyncClient, img_url: str, question_context: str):
    if not GOOGLE_API_KEY: return "Error: No GOOGLE_API_KEY"
    try:
        # Download Image
        resp = await client.get(img_url)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))

        # Query Gemini
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        Analyze this image and answer the question embedded in this text: "{question_context}".
        Return a JSON object with a single key "answer".
        Example: {{"answer": "A red cat"}}
        """
        response = await model.generate_content_async([prompt, img])
        
        # Parse JSON response
        text = response.text
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        data = json.loads(text)
        return data.get("answer")
    except Exception as e:
        logger.error(f"[Gemini] Error: {e}")
        return "Error processing image"

# --- AGENT LOGIC ---
async def run_agent_chain(start_url: str, email: str, secret: str):
    client_timeout = httpx.Timeout(45.0) 
    async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=True) as client:
        current_url = start_url
        visited = set()
        MAX_STEPS = 15

        for step in range(MAX_STEPS):
            if not current_url or current_url in visited: break
            visited.add(current_url)
            logger.info(f"Step {step+1}: {current_url}")

            try:
                resp = await client.get(current_url)
                if resp.status_code >= 400: break
            except Exception: break

            page_text = resp.text
            # Decode Mock Server Wrapper (Regex is faster/lighter than Playwright here)
            b64_match = re.search(r'atob\([\"\']([A-Za-z0-9+/=]+)[\"\']\)', page_text)
            page_inner = base64.b64decode(b64_match.group(1)).decode(errors="ignore") if b64_match else page_text

            # Extract Navigation (Regex First - Faster/Cheaper)
            submit_url = None
            # Pattern 1: Plain text "Post your answer to <URL>"
            m_plain = re.search(r"Post.*?to\s+(https?://[^\s<]+)", page_inner, re.IGNORECASE)
            # Pattern 2: HTML "Post ... to <strong><URL></strong>"
            m_tags = re.search(r"Post.*?to.*?>([^<]+)<", page_inner, re.IGNORECASE)
            
            if m_plain:
                submit_url = m_plain.group(1)
            elif m_tags:
                submit_url = m_tags.group(1)

            # Fallback: LLM if Regex fails
            if not submit_url:
                nav_data = await query_groq(client, f"Analyze HTML. Return JSON {{'url': '...'}} for submission. HTML: {page_inner[-3000:]}")
                submit_url = nav_data.get("url") if nav_data else None

            if submit_url:
                submit_url = urljoin(current_url, submit_url)
            if not submit_url: break

            # Heuristics & Answers
            file_links = re.findall(r'(https?://[^"\s<]+|/files/[^"\s<]+)', page_inner)
            norm_files = []
            for link in file_links:
                if link.startswith("/"): norm_files.append(urljoin(current_url, link))
                elif "localhost" in link or "lhr.life" in link or "railway" in link: norm_files.append(link)
            
            answer = None
            csv_url = next((f for f in norm_files if ".csv" in f.lower()), None)
            txt_url = next((f for f in norm_files if f.endswith((".txt", ".pdf"))), None)
            img_url = next((f for f in norm_files if f.endswith((".png", ".jpg", ".jpeg"))), None)

            if csv_url:
                answer = await answer_csv_sum(client, csv_url)
            elif txt_url:
                answer = await answer_txt_secret(client, txt_url)
            elif img_url:
                logger.info(f"Image found: {img_url}. Sending to Gemini.")
                answer = await answer_image_gemini(client, img_url, page_inner[-1000:])
            else:
                # LLM Fallback for Q&A
                qa_data = await query_groq(client, f"Answer question in text. Return JSON {{'answer': '...'}}. Text: {page_inner[-2000:]}")
                answer = qa_data.get("answer") if qa_data else "start"

            # Submit
            try:
                post_resp = await client.post(submit_url, json={"email": email, "secret": secret, "url": current_url, "answer": answer})
                res = post_resp.json()
                if res.get("correct"):
                    current_url = res.get("url")
                    if not current_url: break
                else:
                    break
            except Exception: break

# --- HELPERS ---
async def answer_csv_sum(client, url):
    try:
        resp = await client.get(url)
        lines = resp.text.strip().splitlines()
        if len(lines) < 2: return 0
        header = lines[0].lower().split(',')
        idx = next((i for i, h in enumerate(header) if "population" in h or "value" in h), len(header)-1)
        total = 0
        for row in lines[1:]:
            cols = row.split(',')
            if len(cols) > idx:
                val = re.sub(r"[^0-9\-]", "", cols[idx])
                if val: total += int(val)
        return total
    except: return 0

async def answer_txt_secret(client, url):
    try:
        resp = await client.get(url)
        m = re.search(r"['\"]([A-Za-z\-]+)['\"]", resp.text)
        return m.group(1) if m else "unknown"
    except: return "error"