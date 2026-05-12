from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os
from dotenv import load_dotenv
load_dotenv()  # looks for .env in the same folder as main.py

import json
import asyncio

from database import (
    init_db, create_user, get_user_by_email,
    create_session, get_user_sessions,
    save_message, get_session_messages, hash_password
)
from schemas import UserCreate, UserLogin, SessionCreate, ChatRequest
from memory import get_memory, load_memory_from_db
from agents import router_agent, get_llm
from prompts import SYSTEM_PROMPT, QUESTION_SUGGESTION_PROMPT

load_dotenv()

# FastAPI app wiring auth, sessions, streaming chat, and suggestions.
app = FastAPI(title="AI Chatbot API")

# Allow the frontend to call this API from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the DB as soon as the server starts.
@app.on_event("startup")
async def startup():
    init_db()

# --- Auth Routes ---

@app.post("/auth/register")
def register(user: UserCreate):
    # Create a new user if the email/username is unused.
    user_id = create_user(user.username, user.email, user.password)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    return {"message": "User registered successfully", "user_id": user_id}

@app.post("/auth/login")
def login(user: UserLogin):
    # Validate credentials and return basic profile info.
    db_user = get_user_by_email(user.email)
    if not db_user or db_user["password_hash"] != hash_password(user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "message": "Login successful",
        "user_id": db_user["id"],
        "username": db_user["username"]
    }

# --- Session Routes ---

@app.post("/sessions/create")
def create_new_session(data: SessionCreate):
    # Create an empty session and return its id.
    session_id = create_session(data.user_id, data.session_name)
    return {"session_id": session_id, "session_name": data.session_name}

@app.get("/sessions/{user_id}")
def get_sessions(user_id: int):
    # List sessions for the sidebar.
    sessions = get_user_sessions(user_id)
    return {"sessions": [dict(s) for s in sessions]}

@app.get("/history/{session_id}")
def get_history(session_id: int):
    # Load chat history for a session.
    messages = get_session_messages(session_id)
    return {"messages": [dict(m) for m in messages]}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    # Remove a session and its messages.
    import sqlite3
    conn = sqlite3.connect("chatbot.db")  # change "chatbot.db" to your actual DB filename
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"message": "Session deleted"}
# --- Chat Route (SSE Streaming) ---

@app.get("/chat/stream")
async def chat_stream(session_id: int, user_id: int, message: str):

    async def event_generator():
        try:
            # 1) Try rule-based agents first (fast answers).
            agent_response = router_agent(message)
            if agent_response:
                save_message(session_id, "user", message)
                save_message(session_id, "assistant", agent_response)
                for word in agent_response.split():
                    yield f"data: {json.dumps({'token': word + ' '})}\n\n"
                    await asyncio.sleep(0.03)
                yield f"data: {json.dumps({'done': True, 'full_response': agent_response})}\n\n"
                return

            # 2) Load DB history and build the LLM message list.
            messages_from_db = get_session_messages(session_id)
            chat_history = load_memory_from_db(session_id, [dict(m) for m in messages_from_db])

            llm_messages = [SystemMessage(content=SYSTEM_PROMPT)] + chat_history + [HumanMessage(content=message)]

            llm = get_llm()
            full_response = ""

            save_message(session_id, "user", message)

            # 3) Stream tokens back to the frontend (SSE).
            async for chunk in llm.astream(llm_messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'token': token})}\n\n"
                    await asyncio.sleep(0)

            # 4) Save the final assistant response.
            save_message(session_id, "assistant", full_response)
            yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()  # prints full error in terminal
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
# --- Question Suggestion Route ---

@app.post("/suggestions")
async def get_suggestions(data: dict):
    # Ask the LLM for short follow-up questions.
    try:
        response_text = data.get("response", "")
        llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.3-70b-versatile",
            temperature=0.5
        )
        prompt = QUESTION_SUGGESTION_PROMPT.format(response=response_text)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        suggestions = json.loads(result.content)
        return {"suggestions": suggestions}
    except:
        return {"suggestions": ["Tell me more", "Can you explain that?", "Give me an example"]}