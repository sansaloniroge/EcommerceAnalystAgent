from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.agent import ask as agent_ask

app = FastAPI(title="EcommerceAnalystAgent")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    trace: list[dict]
    iterations_used: int


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    result = agent_ask(payload.question)
    return AskResponse(answer=result.answer, trace=result.trace, iterations_used=result.iterations_used)
