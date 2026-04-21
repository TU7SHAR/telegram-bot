import logging
import asyncio
import re
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="qwen/qwen3-32b", 
    api_key=GROQ_API_KEY,
    temperature=0.2
)

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You are a document assistant. Answer based ONLY on the provided context. "
        "The context contains multiple files separated by '--- SOURCE: filename ---'. "
        "When you answer, you MUST start your response by mentioning the source file name(s). "
        "Example: 'According to [filename.pdf]...' "
        "Strictly provide the final answer only—no reasoning or <think> tags.\n\n"
        "CONTEXT:\n{context}"
    )),
    ("human", "{question}")
])

chain = prompt | llm

async def get_groq_response(user_message: str, context: str) -> str:
    logger.info(f"GROQ API CALL -> Query: '{user_message[:50]}...' | Context Size: {len(context)} chars")
    
    try:
        response = await chain.ainvoke({"context": context, "question": user_message})
        final_answer = re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
        
        logger.info(f"GROQ API 200 -> Success. Received response of length: {len(final_answer)} chars")
        return final_answer
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            logger.warning("GROQ API 429 -> Rate limit hit. Telling user to wait.")
            return "Rate limit hit. Wait a minute."
        
        logger.error(f"GROQ API ERROR -> {error_msg}")
        return f"Error: {e}"