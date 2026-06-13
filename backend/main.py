import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

# Add the parent folder to Python path to import backend modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.config import (
    JWT_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DEMO_USERS,
    USER_ROLES,
    ROLE_COLLECTIONS
)
from backend.rag import get_chat_response

app = FastAPI(title="MediBot Backend", description="Advanced RAG and SQL RAG Backend with RBAC")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Password hashing configuration (for demo purposes we just compare plain text)
# but we can use CryptContext to be professional
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 1. Models
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str

class ChatRequest(BaseModel):
    question: str

class SourceCitation(BaseModel):
    source_document: str
    section_title: str
    collection: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceCitation]
    retrieval_type: str
    role: str

# 2. JWT Helpers
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_current_user_role(credentials: HTTPAuthorizationCredentials = Depends(security)) -> tuple[str, str]:
    """
    Decodes the JWT token and returns (username, role).
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
        return username, role
    except JWTError:
        raise credentials_exception

# 3. Endpoints
@app.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    username = request.username.strip()
    password = request.password.strip()
    
    # Check if user exists
    if username not in DEMO_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
        
    expected_password = DEMO_USERS[username] # password is the role name
    if password != expected_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
        
    role = USER_ROLES[username]
    access_token = create_access_token(data={"sub": username, "role": role})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role,
        "username": username
    }

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_info: tuple[str, str] = Depends(get_current_user_role)):
    username, role = user_info
    question = request.question.strip()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty"
        )
        
    print(f"\nIncoming question from '{username}' ({role}): '{question}'")
    response_data = get_chat_response(question, role)
    return response_data

@app.get("/collections/{role}")
def get_collections(role: str):
    role = role.lower()
    if role not in ROLE_COLLECTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role}' not found"
        )
    return {
        "role": role,
        "accessible_collections": ROLE_COLLECTIONS[role]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
