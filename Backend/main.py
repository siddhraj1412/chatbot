from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os
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

app = FastAPI(title="AI Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
@app.on_event("startup")
async def startup():
    init_db()

# --- Auth Routes ---

@app.post("/auth/register")
def register(user: UserCreate):
    user_id = create_user(user.username, user.email, user.password)
    if not user_id:
        raise HTTPException(status_code=400, detail="Email or username already exists")
    return {"message": "User registered successfully", "user_id": user_id}

@app.post("/auth/login")
def login(user: UserLogin):
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
    session_id = create_session(data.user_id, data.session_name)
    return {"session_id": session_id, "session_name": data.session_name}

@app.get("/sessions/{user_id}")
def get_sessions(user_id: int):
    sessions = get_user_sessions(user_id)
    return {"sessions": [dict(s) for s in sessions]}

@app.get("/history/{session_id}")
def get_history(session_id: int):
    messages = get_session_messages(session_id)
    return {"messages": [dict(m) for m in messages]}

# --- Chat Route (SSE Streaming) ---

@app.get("/chat/stream")
async def chat_stream(session_id: int, user_id: int, message: str):

    async def event_generator():
        try:
            # Route to agent first
            agent_response = router_agent(message)
            if agent_response:
                save_message(session_id, "user", message)
                save_message(session_id, "assistant", agent_response)
                # Stream agent response word by word
                for word in agent_response.split():
                    yield f"data: {json.dumps({'token': word + ' '})}\n\n"
                    await asyncio.sleep(0.05)
                yield f"data: {json.dumps({'done': True, 'full_response': agent_response})}\n\n"
                return

            # Load memory for this session
            messages_from_db = get_session_messages(session_id)
            chat_history = load_memory_from_db(session_id, [dict(m) for m in messages_from_db])
            llm_messages = [SystemMessage(content=SYSTEM_PROMPT)] + chat_history + [HumanMessage(content=message)]

            # Stream from Groq
            llm = get_llm()
            full_response = ""

            save_message(session_id, "user", message)

            async for chunk in llm.astream(llm_messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'token': token})}\n\n"

            save_message(session_id, "assistant", full_response)
            yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

# --- Question Suggestion Route ---

@app.post("/suggestions")
async def get_suggestions(data: dict):
    try:
        response_text = data.get("response", "")
        llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama3-8b-8192",
            temperature=0.5
        )
        prompt = QUESTION_SUGGESTION_PROMPT.format(response=response_text)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        suggestions = json.loads(result.content)
        return {"suggestions": suggestions}
    except:
        return {"suggestions": ["Tell me more", "Can you explain that?", "Give me an example"]}