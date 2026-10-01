"""CLI for the agentic RAG bot.

  python agent_main.py ask "your question" [--max-steps 5]
  python agent_main.py chat [--max-steps 5]
"""
import argparse

from agent.core import MAX_STEPS, Agent


def show_event(ev: dict):
    if ev["type"] == "plan":
        print(f"\n[plan] {ev['standalone_question']}")
        for q in ev["sub_questions"]:
            print(f"       - {q}")
        return
    act = "finish" if ev["action"] == "finish" else f"{ev['action']}({ev['query']!r})"
    print(f"[step {ev['n']}] {act}\n         why: {ev['thought']}")


def show_result(r):
    print("\n=== ANSWER ===")
    print(r.answer)
    print(f"\nConfidence: {r.confidence}   Steps: {r.steps_used}")
    if r.citations:
        print("\nSources:")
        for c in r.citations:
            print(f"  - [{c['id']}] {c['source']}")


def cmd_ask(args):
    show_result(Agent().run(args.question, max_steps=args.max_steps, on_step=show_event))


def cmd_chat(args):
    agent = Agent()
    history: list[dict] = []
    print("Agentic RAG chat. Type 'exit' to quit.")
    while True:
        try:
            q = input("\nQ> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit", "q"):
            break
        if not q:
            continue
        r = agent.run(q, history=history, max_steps=args.max_steps, on_step=show_event)
        show_result(r)
        history.append({"question": q, "answer": r.answer})


def main():
    ap = argparse.ArgumentParser(description="Agentic RAG bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("ask", cmd_ask, "one question"), ("chat", cmd_chat, "interactive loop")):
        p = sub.add_parser(name, help=help_)
        if name == "ask":
            p.add_argument("question")
        p.add_argument("--max-steps", type=int, default=MAX_STEPS)
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
