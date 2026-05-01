# SALESJI - AI Telegram Bot & Backend 🤖

The Python-powered engine behind SALESJI. This system acts as a context-aware sales assistant on Telegram, utilizing a hybrid RAG (Retrieval-Augmented Generation) pipeline, real-time security validation, and automated lead capture via webhooks.

## 🛠 Core Frameworks & Libraries

**Bot Framework & Networking**

- `python-telegram-bot` (v22.7) - Core Telegram API wrapper
- `ngrok` - Required for local webhook tunneling
- `aiohttp`, `httpx` - Asynchronous HTTP networking

**AI, RAG & LLM Pipeline**

- `langchain`, `langgraph`, `langchain-core` - Orchestration and state management
- `groq`, `langchain-groq` - High-speed LLM inference
- `google-genai` - Google Gemini integration
- `faiss-cpu` - Fast, dense vector similarity search
- `sentence-transformers`, `torch` - Embedding generation

**Database & Cloud**

- `supabase` (v2.28.3) - PostgreSQL database operations and state validation

**Data Ingestion & Document Parsing**

- `beautifulsoup4`, `firecrawl-py` - Web scraping and crawling
- `pypdf`, `pdfplumber`, `pdfminer.six` - PDF text extraction
- `python-docx`, `python-pptx`, `openpyxl` - Microsoft Office document parsing
- `markitdown` - Markdown conversion

**Audio & Speech Processing**

- `SpeechRecognition`, `pydub` - Voice note processing capabilities

## ✨ Key Features

- **Live Security Validation:** Intercepts every incoming Telegram message to verify the user's token status in Supabase. Revoked or banned users are blocked instantly.
- **Hybrid RAG Engine:** Dynamically queries FAISS vector stores built from the `ingested_files` table to provide tenant-specific, context-aware answers.
- **Automated Lead Onboarding:** A structured conversational flow that captures data directly into the `onboarding_leads` table.
- **Independent State Management:** Uses a dedicated `user_states` table to track conversational context (e.g., mid-quiz, mid-onboarding) independently of the main user profiles.

## 🗄️ Database Architecture Overview (9-Table Schema)

1.  **Access:** `invite_tokens`, `authorized_users`
2.  **Engine:** `user_states`
3.  **Knowledge:** `bot_settings`, `ingested_files`
4.  **Analytics:** `chat_analytics`, `onboarding_leads`, `quiz_scores`, `test_results`

## ⚙️ Environment Variables

Create a `.env` file in the root directory:

\`\`\`env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
WEBHOOK_URL=your_ngrok_url # e.g., https://your-ngrok-id.ngrok-free.app
\`\`\`

## 🚀 Quick Start (Local Development with Webhooks)

Because this bot utilizes webhooks for instantaneous updates rather than long-polling, you must expose your local server to the internet.

1. **Install Dependencies:**
   \`\`\`bash
   python -m venv venv
   source venv/bin/activate # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   \`\`\`

2. **Start Ngrok:**
   In a separate terminal, start an ngrok HTTP tunnel on the port your bot is listening to (default 8000):
   \`\`\`bash
   ngrok http 8000
   \`\`\`
   _Copy the `Forwarding` HTTPS URL provided by ngrok and add it to your `.env` file as `WEBHOOK_URL`._

3. **Start the Bot:**
   \`\`\`bash
   python main.py
   \`\`\`

---

_Developed by Tushar Gautam using Gemini_
