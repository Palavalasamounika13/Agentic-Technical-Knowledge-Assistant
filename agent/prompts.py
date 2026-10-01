"""Prompt builders. Each prompt ends with an explicit JSON shape so JSON-mode LLMs stay on schema."""

TOOLS = """\
- search_docs: search the indexed docs, PDFs and code. query = a focused search query.
- calculator: evaluate arithmetic. query = an expression such as "(120*3)/7".
- get_datetime: current date and time. query = "".
- list_sources: list files in the knowledge base. query = "".
- finish: enough evidence gathered, or more searching will not help. query = ""."""


def _history(history: list[dict]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"Q: {h['question']}\nA: {h['answer'][:300]}" for h in history)


def plan_prompt(question: str, history: list[dict]) -> str:
    return f"""You plan how to answer questions over a private knowledge base (docs, PDFs, code).

Chat history:
{_history(history)}

New question: {question}

1. Use the chat history ONLY to resolve references such as "it", "that" or "the second one". If the new question is already self-contained, copy it unchanged. Never carry facts, numbers, units or calculations from earlier answers into the new question.
2. Add 1-3 sub-questions only if the question truly has several parts. Otherwise leave the list empty.

Reply with JSON only:
{{"standalone_question": "...", "sub_questions": ["..."]}}"""


def decision_prompt(plan, trace: list[dict], n: int, max_steps: int) -> str:
    subs = "\n".join(f"- {q}" for q in plan.sub_questions) or "(none)"
    pad = "\n".join(
        f"Step {s['n']}: {s['thought']}\n  action: {s['action']}({s['query']!r})\n  observation: {s['observation']}"
        for s in trace
    ) or "(nothing done yet)"
    return f"""You are a research agent answering a question from a private knowledge base.

Question: {plan.standalone_question}
Sub-questions:
{subs}

Actions you can choose (these are NOT function calls. Never use a tool-calling format.
Reply with a JSON text object only):
{TOOLS}

Work so far:
{pad}

Rules:
- Use search_docs to find facts. If results look weak or off-topic, retry with different keywords.
- Use calculator for any arithmetic on numbers found in the docs.
- Observations show only the START of each chunk. The final answer step reads the FULL text of every chunk found,
  so if a result looks related to the question, choose finish. Do not keep searching for exact wording.
- If two searches with different wording found nothing related to the question, choose finish. Do not keep searching.
- Never repeat the same action with the same query.
- Choose finish once the observations cover the question, or when more searching will not help.
- This is step {n} of {max_steps}. On the last step choose finish.

Reply with JSON only:
{{"thought": "...", "action": "search_docs|calculator|get_datetime|list_sources|finish", "query": "..."}}"""


def final_prompt(question: str, evidence: list[dict], source_of) -> str:
    blocks = "\n\n".join(
        f"[{c['chunk_id']}] source: {source_of(c)}\n{c['text'][:1500]}" for c in evidence
    )
    return f"""Answer the question using ONLY the evidence below. Do not use outside knowledge.

Question: {question}

Evidence:
{blocks}

Rules:
- If the evidence does not answer the question, say so plainly and use confidence "low".
- Put the ids of evidence you actually used in cited_ids, copied exactly.
- confidence: high = directly stated; medium = partly stated or combined from several chunks; low = missing or unclear.
- Answer in one to three complete sentences that restate what was asked. Never reply with a bare number or fragment.

Reply with JSON only:
{{"answer": "...", "confidence": "high|medium|low", "cited_ids": ["id"]}}"""
