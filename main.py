import os
import re
import httpx
import asyncio
import io
import sys
import json
import base64
import pdfplumber
import pandas as pd
import google.generativeai as genai
from PIL import Image
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from groq import Groq
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import time
import traceback

# Load environment variables
load_dotenv()

# --- Configuration ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MY_EMAIL = os.getenv("MY_EMAIL")
MY_SECRET = os.getenv("MY_SECRET")

# --- Clients ---
app = FastAPI()
groq_client = Groq(api_key=GROQ_API_KEY)
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
http_client = httpx.AsyncClient(timeout=60.0)


class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str


# --- 1. Scraper ---
async def scrape_page_content(url: str):
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
            content = await page.evaluate("document.body.innerText")
            if not content:
                content = await page.content()
            print("--- scrape_page_content: Finished successfully ---")
            return content, None
        except Exception as e:
            print(f"Playwright scrape error: {e}")
            return None, f"Error: Could not scrape page. {e}"
        finally:
            if browser:
                await browser.close()


# --- 2. Task Handlers (The Toolbox) ---


async def handle_csv_task(url: str, question: str):
    """Downloads CSV and uses Pandas to solve it."""
    print(f"Handling CSV task: {url}")
    try:
        response = await http_client.get(url)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))

        if "sum" in question.lower():
            numeric_cols = df.select_dtypes(include=["number"]).columns
            for col in df.columns:
                if col.lower() in question.lower():
                    clean_col = pd.to_numeric(df[col], errors="coerce").fillna(0)
                    return clean_col.sum()
            if len(numeric_cols) > 0:
                return df[numeric_cols[-1]].sum()

        return await get_answer_from_groq(question, df.to_string(index=False))
    except Exception as e:
        return f"Error processing CSV: {e}"


# --- 3. The Brain (Router) ---
async def get_answer_from_ai(scraped_text: str):
    match = re.search(
        r'https?://[^\s"\']+\.(csv|pdf|png|jpg|jpeg|gif|txt)',
        scraped_text,
        re.IGNORECASE,
    )

    if not match:
        print("No data file found. Using Groq for pure text analysis.")
        return await get_answer_from_groq(scraped_text, "")

    data_url = match.group(0)
    print(f"Found data URL: {data_url}")

    try:
        if data_url.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
            if not GOOGLE_API_KEY:
                return "Error: No Google API Key."
            print("Routing to Gemini (Vision)...")
            response = await http_client.get(data_url)
            img = Image.open(io.BytesIO(response.content))

            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config={"response_mime_type": "application/json"},
            )
            prompt = f"Analyze this image and the question: '{scraped_text}'. Return JSON {{'answer': ...}}"
            resp = await model.generate_content_async([prompt, img])
            return json.loads(resp.text).get("answer")

        elif data_url.lower().endswith(".csv"):
            print("Routing to CSV Handler...")
            return await handle_csv_task(data_url, scraped_text)

        elif data_url.lower().endswith((".pdf", ".txt")):
            print("Routing to Groq (Text/PDF)...")
            response = await http_client.get(data_url)
            if data_url.endswith(".txt"):
                context = response.text
            else:
                with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                    context = "\n".join([p.extract_text() or "" for p in pdf.pages])

            return await get_answer_from_groq(scraped_text, context)

    except Exception as e:
        print(f"AI Error: {e}")
        return f"Error: {e}"

    return "Error: Unknown task type."


async def get_answer_from_groq(question: str, context: str):
    try:
        chat = await asyncio.to_thread(
            groq_client.chat.completions.create,
            messages=[
                {
                    "role": "system",
                    "content": "You are a quiz solver. Return ONLY a JSON object {'answer': ...}. No markdown.",
                },
                {
                    "role": "user",
                    "content": f"Context: {context}\n\nQuestion: {question}",
                },
            ],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
        )
        return json.loads(chat.choices[0].message.content).get("answer")
    except Exception as e:
        return f"Groq Error: {e}"


# --- 4. Submitter ---
def extract_submit_url(text: str):
    match = re.search(
        r'(Post your answer to|submit to|POST this JSON to) (https?://[^\s"\\]+)',
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(2).strip(".,")
    if "tds-llm-analysis.s-anand.net/demo" in text:
        return "https://tds-llm-analysis.s-anand.net/submit"
    return None


async def submit_answer(submit_url: str, answer, task_url: str):
    payload = {
        "email": MY_EMAIL,
        "secret": MY_SECRET,
        "url": task_url,
        "answer": answer,
    }
    try:
        resp = await http_client.post(submit_url, json=payload)
        print(f"Submission: {resp.status_code} - {resp.text}")
        return resp.json()
    except Exception as e:
        return {"correct": False, "reason": str(e)}


# --- 5. Main Process ---
async def process_quiz(request: QuizRequest):
    print(f"Processing: {request.url}")
    scraped_text, error = await scrape_page_content(request.url)

    submit_url = extract_submit_url(scraped_text)
    if not submit_url:
        print("CRITICAL: No submit URL found.")
        return

    if error:
        await submit_answer(submit_url, error, request.url)
        return

    answer = await get_answer_from_ai(scraped_text)
    print(f"Answer: {answer}")

    result = await submit_answer(submit_url, answer, request.url)
    if result.get("url"):
        print(f"Next URL: {result['url']}")
        await process_quiz(
            QuizRequest(email=request.email, secret=request.secret, url=result["url"])
        )
    else:
        print("Quiz finished.")


# --- API ---
@app.post("/quiz")
async def receive_task(req: QuizRequest, bg: BackgroundTasks):
    if req.secret != MY_SECRET:
        raise HTTPException(403, "Bad Secret")
    bg.add_task(process_quiz, req)
    return {"message": "Started"}


@app.get("/")
def home():
    return {"status": "Ready"}
