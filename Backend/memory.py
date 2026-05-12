from langchain_core.messages import HumanMessage, AIMessage

# Simple in-memory store per session (speedy access while chatting).
session_memories = {}

# Get the list of messages for a session, creating it if missing.
def get_memory(session_id: int) -> list:
    if session_id not in session_memories:
        session_memories[session_id] = []
    return session_memories[session_id]

# Clear the cached memory for a session.
def clear_memory(session_id: int):
    if session_id in session_memories:
        session_memories[session_id] = []

# Convert DB rows into LangChain message objects.
def load_memory_from_db(session_id: int, messages: list) -> list:
    """Load existing messages from DB into memory on session restore"""
    memory = []
    for msg in messages:
        if msg["role"] == "user":
            memory.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            memory.append(AIMessage(content=msg["content"]))
    session_memories[session_id] = memory
    return memory