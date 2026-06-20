"""
FastAPI backend for MediBot with RBAC enforcement at the retrieval layer.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from hybrid_rag import (
    retrieve_and_prepare_prompt,
    RetrievalCandidate,
)
from sql_rag import SqlRag, SqlRagResult

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="MediBot API",
    description="Medical knowledge assistant with RBAC and hybrid RAG",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token: str
    token_type: str = "bearer"
    role: str
    username: str
    collections: list[str]


class ChatRequest(BaseModel):
    question: str
    retrieval_type: str | None = None


class SourceCitation(BaseModel):
    source_document: str
    collection: str
    section_title: str | None = None
    text_snippet: str


class ChatResponse(BaseModel):
    answer: str
    retrieval_type: str  # "hybrid_rag" or "sql_rag"
    sources: list[SourceCitation]
    role: str
    message: str = ""


class RBACRefusalResponse(BaseModel):
    answer: str = ""
    retrieval_type: str = "hybrid_rag"
    sources: list[SourceCitation] = []
    role: str
    message: str  # Explanation of why the query was blocked


class CollectionsResponse(BaseModel):
    role: str
    collections: list[str]


def encode_token(username: str, role: str) -> str:
    """Create a simple base64-encoded token."""
    token_data = f"{username}:{role}"
    return base64.b64encode(token_data.encode()).decode()


def decode_token(token: str) -> tuple[str, str]:
    """Decode a base64-encoded token."""
    try:
        token_data = base64.b64decode(token.encode()).decode()
        username, role = token_data.split(":", 1)
        return username, role
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def get_current_user(authorization: str | None = None) -> tuple[str, str]:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")

    token = parts[1]
    return decode_token(token)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "medibot-api"}


@app.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Authenticate a user and return a token."""
    logger.info("Login attempt for username=%s", request.username)

    if request.username not in config.DEMO_ACCOUNTS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    account = config.DEMO_ACCOUNTS[request.username]
    if account["password"] != request.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    role = account["role"]
    token = encode_token(request.username, role)
    collections = [
        collection
        for collection, allowed_roles in config.RBAC_MATRIX.items()
        if role in allowed_roles
    ]
    logger.info("User %s (role=%s) authenticated", request.username, role)

    return LoginResponse(
        access_token=token,
        token=token,
        token_type="bearer",
        role=role,
        username=request.username,
        collections=collections,
    )


@app.post("/chat", response_model=ChatResponse | RBACRefusalResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
):
    """
    Main chat endpoint.
    Accepts a natural language question, routes between Hybrid RAG and SQL RAG,
    and returns a structured answer with sources.
    """
    username, role = get_current_user(authorization)
    logger.info("Chat request from user=%s (role=%s): %s", username, role, request.question)

    if role not in config.ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {role}")

    retrieval_type = request.retrieval_type
    if retrieval_type is None:
        sql_rag = SqlRag(config.DB_PATH)
        if sql_rag.is_analytical_question(request.question):
            retrieval_type = "sql_rag"
        else:
            retrieval_type = "hybrid_rag"

    if retrieval_type not in {"hybrid_rag", "sql_rag"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="retrieval_type must be hybrid_rag or sql_rag")

    if retrieval_type == "sql_rag":
        if role not in config.SQL_RAG_ROLES:
            message = (
                f"As a {role}, you don't have permission to run analytical SQL queries. "
                "SQL RAG is available to billing_executive and admin only."
            )
            return RBACRefusalResponse(
                retrieval_type="sql_rag",
                role=role,
                message=message,
                sources=[],
            )

        try:
            sql_rag = SqlRag(config.DB_PATH)
            sql_result = sql_rag.execute_question(question=request.question, role=role)
        except PermissionError as e:
            logger.warning("SQL RAG access denied for user=%s (role=%s): %s", username, role, e)
            return RBACRefusalResponse(
                retrieval_type="sql_rag",
                role=role,
                message=str(e),
                sources=[],
            )
        except ValueError as e:
            logger.warning("SQL RAG classification failed: %s", e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        sources = [
            SourceCitation(
                source_document="mediassist.db",
                collection="sql_rag",
                section_title="SQL result",
                text_snippet=str(item)[:200],
            )
            for item in sql_result.sources
        ]

        return ChatResponse(
            answer=sql_result.answer,
            retrieval_type="sql_rag",
            sources=sources,
            role=role,
        )

    try:
        prompt, reranked_candidates = retrieve_and_prepare_prompt(
            query_text=request.question,
            role=role,
            retrieval_k=10,
            rerank_k=3,
        )
    except RuntimeError as e:
        logger.error("RBAC filter violation for user=%s (role=%s): %s", username, role, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not reranked_candidates:
        logger.info("No relevant documents found for user=%s (role=%s)", username, role)
        return RBACRefusalResponse(
            role=role,
            message=f"As a {role}, you don't have access to documents relevant to this query, or no documents match your question.",
            sources=[],
        )

    answer = call_llm(prompt)
    logger.info("Generated answer for user=%s", username)

    sources = [
        SourceCitation(
            source_document=candidate.source_document,
            collection=candidate.collection,
            section_title=str(candidate.metadata.get("section_title", "")),
            text_snippet=candidate.text[:200],
        )
        for candidate in reranked_candidates
    ]

    return ChatResponse(
        answer=answer,
        retrieval_type="hybrid_rag",
        sources=sources,
        role=role,
    )


@app.get("/collections/{role}", response_model=CollectionsResponse)
def collections(role: str, authorization: str | None = Header(default=None)):
    if role not in config.ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role: {role}")

    _, token_role = get_current_user(authorization)
    if token_role != role and token_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this role's collections")

    if role == "admin":
        collections = list(config.RBAC_MATRIX.keys())
    else:
        collections = [
            collection
            for collection, allowed_roles in config.RBAC_MATRIX.items()
            if role in allowed_roles
        ]

    return CollectionsResponse(role=role, collections=collections)


def call_llm(prompt: str) -> str:
    """
    Call Groq LLM API to generate an answer from the prompt.
    Falls back to a stub response if GROQ_API_KEY is not set.
    """
    if not config.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set; returning stub response")
        return (
            "I would provide a detailed answer based on the retrieved documents, "
            "but the LLM API key is not configured. Please set GROQ_API_KEY environment variable."
        )

    try:
        from groq import Groq

        client = Groq(api_key=config.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful medical assistant. Answer the user's question based on the provided documents. "
                        "Always cite the source document in your response. Do not hallucinate or provide information not in the documents."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        completion_text = response.choices[0].message.content
        logger.info("LLM response generated successfully")
        return completion_text
    except ImportError:
        logger.warning("Groq library not installed; returning stub response")
        return (
            "I would provide a detailed answer based on the retrieved documents, "
            "but the Groq client library is not installed. Please install it with: pip install groq"
        )
    except Exception as e:
        logger.error("Error calling Groq LLM: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"LLM error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
