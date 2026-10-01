# Agentic RAG add-on

Upgrades the RAG bot from one-shot retrieval to an agent that plans, uses tools in a loop,
and answers with validated citations. Existing files (`main.py`, `app.py`, `rag/`) stay untouched.

## Quick start (Windows)

1. Unzip anywhere, for example `C:\Users\mounilka\Downloads\agentic_rag`.
2. Double-click `setup.bat`. It copies the `rag/` engine, `data/`, `storage/` index and `.env`
   from the old project (default path is inside the file; pass another path as an argument),
   creates `.venv`, installs packages, runs the offline tests.
3. Put your NEW Groq key in `.env`: `GROQ_API_KEY=gsk_...`
4. Double-click `run_cli.bat` (terminal) or `run_ui.bat` (web UI).

Manual route: copy `rag/`, `data/`, `storage/`, `.env` from the old project, then
`python -m venv .venv`, `.venv\Scripts\activate.bat`, `pip install -r requirements.txt`.

## Run

```bash
python main.py build                       # index must exist first
python agent_main.py ask "How long does a refund take, and what is 3x that in days?"
python agent_main.py chat                  # multi-turn, follow-ups understood
streamlit run app.py                       # web UI: upload files, build index, chat with the agent
python tests/test_agent.py                 # offline tests, no key needed
```

## How it works

```
question (+ chat history)
   |
 PLAN      rewrite as standalone question, split into sub-questions
   |
 LOOP  (max N steps)
   |   DECIDE   LLM picks: search_docs | calculator | get_datetime | list_sources | finish
   |   ACT      run tool, collect evidence chunks (dedupe by id, keep best rerank score)
   |   OBSERVE  result goes back into the next decision prompt
   |
 ANSWER    LLM answers from pooled evidence only; cited ids are validated,
           bad ids trigger one retry, no valid citation forces confidence "low"
```

Why this beats plain RAG: multi-part questions get several searches, weak first searches get
retried with new wording, math is computed instead of guessed, follow-ups like "and for
international ones?" are resolved from history.

## Tune (agent/core.py)

| Constant | Effect |
|---|---|
| `MAX_STEPS` | more steps = deeper search, slower, more Groq calls |
| `MAX_EVIDENCE` | chunks given to the final answer |
| `HISTORY_TURNS` | previous Q/A pairs used for follow-ups |

Each question costs about 3 to 7 LLM calls. On the free tier, watch for 429 errors and lower `--max-steps`.

## Add a tool

1. Add a `_method(self, query) -> ToolResult` in `agent/tools.py` and register it in `run()`.
2. Add its name to `Action` in `agent/schemas.py`.
3. Describe it in `TOOLS` in `agent/prompts.py`.

Return `chunks=[...]` in the `ToolResult` if the answer should be able to cite the tool output.

## Notes

- Calculator uses an AST whitelist. No `eval`, no names, no calls.
- Tool errors are caught and shown to the agent as observations. The loop never crashes on a tool.
- If the loop finds no evidence, the bot answers "not found" without an extra LLM call.
