"""Pydantic schemas for every structured LLM call the agent makes."""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["search_docs", "calculator", "get_datetime", "list_sources", "finish"]
Confidence = Literal["high", "medium", "low"]


class Plan(BaseModel):
    standalone_question: str = Field(description="Question rewritten to make sense without chat history.")
    sub_questions: list[str] = Field(default_factory=list, description="0-3 smaller questions.")


class Decision(BaseModel):
    thought: str = Field(description="One short sentence: what is missing and why this action.")
    action: Action
    query: str = Field(default="", description="Search query or math expression. Empty for other actions.")


class FinalAnswer(BaseModel):
    answer: str
    confidence: Confidence
    cited_ids: list[str] = Field(default_factory=list)


@dataclass
class AgentResult:
    answer: str
    confidence: str
    citations: list[dict]   # {"id", "source", "text", "score"}
    trace: list[dict]       # {"n", "thought", "action", "query", "observation"}
    plan: dict              # {"standalone_question", "sub_questions"}
    steps_used: int
