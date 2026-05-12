from langchain_groq import ChatGroq
from datetime import datetime
import math
import os
import json
import re

def get_llm():
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model_name="llama3-8b-8192",
        temperature=0.7,
        streaming=True
    )

# --- Math Agent ---
def math_agent(query: str) -> str:
    """Handles basic math expressions and calculations"""
    try:
        # Clean the query to extract math expression
        expression = re.sub(r'[^0-9+\-*/().\s]', '', query)
        if expression.strip():
            result = eval(expression, {"__builtins__": {}}, {"math": math})
            return f"The answer is: {result}"
        return None
    except:
        return None

# --- Time Agent ---
def time_agent(query: str) -> str:
    """Handles current time and date queries"""
    query_lower = query.lower()
    if any(word in query_lower for word in ["time", "date", "today", "day", "month", "year"]):
        now = datetime.now()
        return f"Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')}"
    return None

# --- Router Agent ---
def router_agent(query: str) -> str | None:
    """
    Routes query to the right agent.
    Returns a string response if an agent handles it,
    or None if it should go to the main LLM.
    """
    # Check time/date queries first
    time_response = time_agent(query)
    if time_response:
        return time_response

    # Check if it looks like a math query
    math_keywords = ["calculate", "compute", "what is", "solve", "how much is", "+", "-", "*", "/"]
    has_numbers = bool(re.search(r'\d', query))
    has_math_keyword = any(kw in query.lower() for kw in math_keywords)

    if has_numbers and has_math_keyword:
        math_response = math_agent(query)
        if math_response:
            return math_response

    # Default — let main LLM handle it
    return None