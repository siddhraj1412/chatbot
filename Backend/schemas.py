from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Pydantic models define request/response shapes for the API.

# User schemas
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str

# Session schemas
class SessionCreate(BaseModel):
    user_id: int
    session_name: str

class SessionResponse(BaseModel):
    id: int
    user_id: int
    session_name: str
    created_at: str

# Message schemas
class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    timestamp: str

# Chat schemas
class ChatRequest(BaseModel):
    session_id: int
    user_id: int
    message: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str