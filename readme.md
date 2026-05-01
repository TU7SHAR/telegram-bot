# 🤖 SALESJI - AI Telegram Bot Backend

The Python-powered engine behind **SALESJI**. This system acts as a context-aware sales assistant on Telegram, utilizing a hybrid RAG (Retrieval-Augmented Generation) pipeline, real-time security validation, and automated lead capture via webhooks.

---

## ✨ Core Capabilities

- **Live Security & Authorization:** Intercepts every incoming Telegram message to verify the user's token status directly against Supabase. Revoked or banned users are blocked instantly.
- **Hybrid RAG Engine:** Dynamically queries FAISS vector stores built from the `ingested_files` table to provide highly accurate, tenant-specific answers.
- **Automated Lead Onboarding:** A structured conversational flow that captures user data and qualifies leads directly into the `onboarding_leads` table.
- **Independent State Management:** Uses a dedicated `user_states` table to track conversational context (e.g., mid-quiz, mid-onboarding) independently, keeping main user profiles clean.
- **Multi-Format Data Ingestion:** Natively parses and chunks PDFs, DOCX files, PPTX presentations, and live web URLs (via Firecrawl and BeautifulSoup).

---

## 🗄️ Database Architecture (9-Table Schema)

The architecture is fully normalized and split into four logical zones:

1. **Access Control:** `invite_tokens`, `authorized_users`
2. **State Engine:** `user_states`
3. **Knowledge Base:** `bot_settings`, `ingested_files`
4. **Analytics & Output:** `chat_analytics`, `onboarding_leads`, `quiz_scores`, `test_results`

---

## 🛠️ Tech Stack & Libraries

### Bot Framework & Networking

- `python-telegram-bot` (v22.7) - Core Telegram API wrapper
- `aiohttp`, `httpx` - Asynchronous HTTP networking
- `ngrok` - Webhook tunneling

### AI, LLMs & Vector Search

- `langchain`, `langgraph`, `langchain-core` - Orchestration
- `groq`, `langchain-groq` - High-speed LLM inference
- `google-genai` - Google Gemini integration
- `faiss-cpu` - Fast, dense vector similarity search
- `sentence-transformers`, `torch` - Embedding generation

### Database & Cloud

- `supabase` (v2.28.3) - PostgreSQL operations and state validation
- `SQLAlchemy` - ORM toolkit

### Document Parsing & Audio

- `beautifulsoup4`, `firecrawl-py` - Web scraping
- `pypdf`, `pdfplumber`, `pdfminer.six` - PDF extraction
- `python-docx`, `python-pptx`, `openpyxl` - Microsoft Office parsing
- `SpeechRecognition`, `pydub` - Voice note processing

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory and add the following variables:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
WEBHOOK_URL=your_ngrok_url


```

_Developed by Tushar Gautam using Gemini_
