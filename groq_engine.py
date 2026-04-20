import logging
import asyncio
import re
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import GROQ_API_KEY

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="qwen/qwen3-32b", 
    api_key=GROQ_API_KEY,
    temperature=0.2
)

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a document assistant. Answer the user's question based ONLY on the provided context. "
        "If the answer isn't in the context, say you don't know based on the file provided. "
        "Strictly provide the final answer only—no reasoning or <think> tags.\n\n"
        "CONTEXT:\n{context}"
    )),
    ("human", "{question}")
])

chain = prompt | llm

async def get_groq_response(user_message: str, context: str) -> str:
    """Processes a question using the specific context provided."""
    if not context:
        return "Please upload a text file first so I have something to read!"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await chain.ainvoke({
                "context": context,
                "question": user_message
            })
            
            clean_text = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
            return clean_text
            
        except Exception as e:
            if "429" in str(e):
                await asyncio.sleep(2)
                continue
            logger.error(f"Groq Error: {e}")
            break
    return "Something went wrong. Try again in a moment."