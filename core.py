"""Agent loop: plan -> (decide -> act -> observe)* -> grounded final answer with validated citations."""
from __future__ import annotations

import json
from typing import Callable, get_args

from rag.llm import generate_json

from .prompts import decision_prompt, final_prompt, plan_prompt
from .schemas import Action, AgentResult, Decision, FinalAnswer, Plan
from .tools import Toolbox, chunk_source

MAX_STEPS = 5       # tool-use steps per question (finish counts as one)
MAX_EVIDENCE = 8    # chunks passed to the final answer
HISTORY_TURNS = 3   # previous Q/A pairs used to resolve follow-ups
NO_EVIDENCE = "I could not find relevant information in the knowledge base."


def _recover_tool_call(err: Exception, schema):
    """Groq rejects replies shaped like a native tool call ('tool_use_failed').
    The rejected text comes back in the error, so salvage it into a Decision."""
    if schema is not Decision:
        return None
    body = getattr(err, "body", None)
    body = body.get("error", body) if isinstance(body, dict) else {}
    try:
        call = json.loads(body.get("failed_generation"))
        name, args = call["name"], call.get("arguments") or {}
        if name not in get_args(Action):
            return None
        query = next((v for v in args.values() if isinstance(v, str)), "") if isinstance(args, dict) else ""
        return Decision(thought="(recovered from a tool-call style reply)", action=name, query=query)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def _call(prompt: str, schema, retries: int = 2):
    """LLM call with schema validation. Retries on malformed JSON or tool-call style replies."""
    hint, last = "", None
    for _ in range(retries + 1):
        try:
            return schema.model_validate_json(generate_json(prompt + hint, schema))
        except ValueError as e:  # pydantic ValidationError subclasses ValueError
            last = e
            hint = f"\n\nYour previous reply was invalid ({str(e)[:200]}). Reply with valid JSON only."
        except Exception as e:
            if "tool_use_failed" not in str(e):
                raise
            salvaged = _recover_tool_call(e, schema)
            if salvaged is not None:
                return salvaged
            last = e
            hint = "\n\nDo NOT call functions or tools. Reply with one plain JSON object as text only."
    raise last


class Agent:
    def __init__(self, retriever=None):
        if retriever is None:
            from rag.retrieval import HybridRetriever
            retriever = HybridRetriever()
        self.tools = Toolbox(retriever)

    def run(self, question: str, history: list[dict] | None = None, max_steps: int = MAX_STEPS,
            on_step: Callable[[dict], None] | None = None) -> AgentResult:
        emit = on_step or (lambda _ev: None)
        self.tools.reset()
        history = (history or [])[-HISTORY_TURNS:]

        plan = self._plan(question, history)
        emit({"type": "plan", **plan.model_dump()})

        evidence: dict[str, dict] = {}
        trace: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for n in range(1, max_steps + 1):
            d = _call(decision_prompt(plan, trace, n, max_steps), Decision)
            step = {"n": n, "thought": d.thought, "action": d.action, "query": d.query, "observation": ""}
            if d.action != "finish":
                key = (d.action, d.query.strip().lower())
                if key in seen:
                    step["observation"] = "Already done with the same input. Use different wording or finish."
                else:
                    seen.add(key)
                    res = self.tools.run(d.action, d.query)
                    step["observation"] = res.text
                    for c in res.chunks:
                        old = evidence.get(c["chunk_id"])
                        if old is None or c.get("rerank_score", 0) > old.get("rerank_score", 0):
                            evidence[c["chunk_id"]] = c
            trace.append(step)
            emit({"type": "step", **step})
            if d.action == "finish":
                break

        answer, confidence, citations = self._final(plan.standalone_question, self._pick(evidence))
        return AgentResult(answer, confidence, citations, trace, plan.model_dump(), len(trace))

    def _plan(self, question: str, history: list[dict]) -> Plan:
        try:
            return _call(plan_prompt(question, history), Plan)
        except ValueError:
            return Plan(standalone_question=question, sub_questions=[])

    @staticmethod
    def _pick(evidence: dict[str, dict]) -> list[dict]:
        tool = [c for c in evidence.values() if c.get("_tool")]
        docs = sorted((c for c in evidence.values() if not c.get("_tool")),
                      key=lambda c: c.get("rerank_score", 0), reverse=True)
        return tool + docs[: max(MAX_EVIDENCE - len(tool), 0)]

    @staticmethod
    def _final(question: str, evidence: list[dict]) -> tuple[str, str, list[dict]]:
        if not evidence:
            return NO_EVIDENCE, "low", []
        valid = {c["chunk_id"] for c in evidence}
        prompt = final_prompt(question, evidence, chunk_source)
        ans = _call(prompt, FinalAnswer)
        bad = [i for i in ans.cited_ids if i not in valid]
        if bad:
            ans = _call(prompt + f"\n\nYou cited unknown ids {bad}. Cite only ids from the evidence.", FinalAnswer)
        cited = [i for i in dict.fromkeys(ans.cited_ids) if i in valid]
        confidence = ans.confidence if cited else "low"
        by_id = {c["chunk_id"]: c for c in evidence}
        citations = [{"id": i, "source": chunk_source(by_id[i]), "text": by_id[i]["text"],
                      "score": by_id[i].get("rerank_score", 0)} for i in cited]
        return ans.answer, confidence, citations
