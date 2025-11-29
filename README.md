# LLMQuizer - Intelligent Quiz Solver Agent 🤖

A robust, AI-powered autonomous agent designed to solve complex multi-step quizzes. Built with FastAPI, Playwright, Groq (Llama 3), and Google Gemini Vision.

## 🚀 Key Features

- **Multi-Modal Solving**: Handles Text, CSV, PDF, Images, JSON, and Base64 inputs.
- **Intelligent Retry Logic**: 
  - Prioritizes "Next URL" if provided (even on wrong answers).
  - Automatically retries with LLM feedback if stuck (no next URL).
- **Visualization Generation**: Creates charts (Bar/Line) from data and submits as Base64.
- **Resilient Navigation**: 
  - Dynamic URL extraction (Regex + LLM fallback).
  - Handles `ngrok` browser warning pages automatically.
- **Production Ready**:
  - 1MB Payload validation.
  - Graceful error handling & timeouts.
  - Dockerized for Railway deployment.

## 🛠️ Tech Stack

- **Core**: Python 3.10, FastAPI
- **LLM**: Groq (Llama 3.3 70B) for text/logic
- **Vision**: Google Gemini Flash 2.0 for images/PDFs
- **Browser**: Playwright (Headless)
- **Deployment**: Railway + Docker

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Groq API Key
- Google Gemini API Key

### Local Setup

1. **Clone & Install**
   ```bash
   git clone https://github.com/UNKNOWNAR/LLMQuizer.git
   cd LLMQuizer
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Environment Variables**
   Create a `.env` file:
   ```ini
   GROQ_API_KEY=gsk_...
   GOOGLE_API_KEY=AIza...
   MY_SECRET=my-secret-value
   MY_EMAIL=test@example.com
   PORT=8080
   ```

3. **Run Server**
   ```bash
   uvicorn main:app --reload --port 8080
   ```

## 🧪 Testing

### Running the Mock Server
The included mock server simulates the entire quiz chain (CSV, TXT, PDF, Image, etc.).

1. **Start Mock Server**
   ```bash
   python mock_server.py
   ```
   *Runs on port 8001*

2. **Expose via Ngrok** (Optional but recommended for full test)
   ```bash
   ngrok http 8001
   ```
   *Update `BASE_URL` in `mock_server.py` with your ngrok URL.*

### Running Tests
Run the comprehensive test suite:

```bash
# Run full quiz chain test
pytest tests/test_main.py::test_full_quiz_chain -v -s

# Run specific test
pytest tests/test_main.py::test_chart_generation -v
```

## 📦 Deployment (Railway)

The project is configured for seamless deployment on Railway.

1. **Push to GitHub**
   - The repo includes `Dockerfile` and `requirements.txt`.
2. **Connect Railway**
   - Create new project from GitHub repo.
3. **Set Variables**
   - Add `GROQ_API_KEY`, `GOOGLE_API_KEY`, `MY_SECRET`, `MY_EMAIL` in Railway dashboard.
4. **Deploy**
   - Railway will auto-build and deploy.

## 🔄 Workflow

1. **Start**: Receive POST request with `start_url`.
2. **Navigate**: Agent visits URL, handles ngrok warnings.
3. **Analyze**: 
   - Detects file links (CSV, PDF, Images).
   - Extracts question context from HTML.
4. **Solve**:
   - **CSV/Text**: Processed by Groq.
   - **Images/PDF**: Processed by Gemini Vision.
   - **Charts**: Generated via Matplotlib + LLM parameters.
5. **Submit**: POST answer to extracted `submit_url`.
6. **Loop**: 
   - If Correct → Go to next URL.
   - If Wrong + Next URL → Go to next URL.
   - If Wrong + No URL → **Retry with Feedback**.

## 📂 Project Structure

```
LLMQuizer/
├── main.py              # Core agent logic (FastAPI app)
├── mock_server.py       # Simulation server for testing
├── requirements.txt     # Dependencies
├── Dockerfile           # Production container config
├── tests/
│   ├── test_main.py     # Comprehensive test suite
│   └── README.md        # Testing documentation
└── demo_files/          # Dummy files for mock server
```

## 🛡️ Retry Logic Explained

The agent uses a two-tier retry strategy:

1. **Priority 1 (Skip)**: If the server returns `correct: false` but provides a `next_url`, the agent prioritizes moving forward (assuming the quiz allows skipping).
2. **Priority 2 (Retry)**: If `correct: false` and `url: null`, the agent queries the LLM with the error reason and original question to generate a *different* answer and retries once.

---
**Status**: Production Ready 🚀
**Last Verified**: 29 Nov 2025