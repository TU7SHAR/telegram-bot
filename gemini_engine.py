import os
import logging
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document

from config import GEMINI_API_KEY

# Set up basic logging so we can see errors in the terminal
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KB_FILE = "knowledge_base.txt"

def initialize_rag_chain():
    if not os.path.exists(KB_FILE):
        logger.error(f"CRITICAL: {KB_FILE} not found!")
        raise FileNotFoundError(f"Ensure {KB_FILE} is in the same directory.")

    logger.info("Loading knowledge base and building vectors... This takes a few seconds.")

    loader = TextLoader(KB_FILE, encoding="utf-8")
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=150,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    docs = text_splitter.split_documents(documents)

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2-preview",
        google_api_key=GEMINI_API_KEY
    )
    
    # --- THE FIX: Process documents one at a time to prevent the batching crash ---
    logger.info(f"Embedding {len(docs)} chunks one by one to avoid API batching bug...")
    vector_store = FAISS.from_documents([docs[0]], embeddings)
    for doc in docs[1:]:
        vector_store.add_documents([doc])
    # ------------------------------------------------------------------------------
    
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})

    # Using the higher-limit model for the actual chat
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite", 
        temperature=0.3,
        google_api_key=GEMINI_API_KEY
    )

    system_prompt = (
        "You are a helpful assistant for Panchkula Tech Hub. "
        "Use the following context to answer the user's question. "
        "If the answer is not in the context, say you don't know and provide the support email.\n\n"
        "Context:\n{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}")
    ])

    def format_docs(docs: List[Document]) -> str:
        return "\n\n".join(doc.page_content for doc in docs)

    chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough()
        }
        | prompt
        | llm
    )

    logger.info("Brain successfully loaded!")
    return chain
# Initialize the chain globally so it only loads once on startup
rag_chain = initialize_rag_chain()

# 8. Function for bot (Upgraded to Async)
async def get_groq_response(user_message: str) -> str:
    """Passes the user message to Gemini asynchronously."""
    try:
        # Use ainvoke instead of invoke to prevent blocking the Telegram loop
        response = await rag_chain.ainvoke(user_message)
        return response.content
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return "Sorry, I am having trouble connecting to my knowledge base right now. Please try again in a moment."