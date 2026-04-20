import logging
import asyncio
import re
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from config import GROQ_API_KEY

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
    try:
        response = await chain.ainvoke({"context": context, "question": user_message})
        return re.sub(r'<think>.*?</think>', '', response.content, flags=re.DOTALL).strip()
    except Exception as e:
        if "429" in str(e):
            return "Rate limit hit. Wait a minute."
        return f"Error: {e}"