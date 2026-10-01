"""Tools the agent can call. Add a new tool: write a _method, register it in run(),
then add it to Action in schemas.py and to TOOLS in prompts.py."""
import ast
import datetime as dt
import operator as op
from dataclasses import dataclass, field
from pathlib import Path

_OPS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.Mod: op.mod, ast.FloorDiv: op.floordiv,
    ast.USub: op.neg, ast.UAdd: op.pos,
}


def safe_eval(expr: str):
    """Evaluate plain arithmetic only. No names, calls or attributes."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            left, right = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("unsupported expression")

    return ev(ast.parse(expr.strip(), mode="eval"))


def chunk_source(chunk: dict) -> str:
    return chunk.get("source") or (chunk.get("metadata") or {}).get("source") or "unknown"


def _preview(text: str, n: int = 500) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "..."


@dataclass
class ToolResult:
    text: str                                   # what the agent sees
    chunks: list[dict] = field(default_factory=list)  # evidence to pool for the final answer


class Toolbox:
    def __init__(self, retriever):
        self.retriever = retriever
        self._counts: dict[str, int] = {}

    def reset(self):
        self._counts = {}

    def run(self, action: str, query: str = "") -> ToolResult:
        handlers = {
            "search_docs": self._search,
            "calculator": self._calc,
            "get_datetime": self._clock,
            "list_sources": self._sources,
        }
        fn = handlers.get(action)
        if fn is None:
            return ToolResult(f"Unknown tool '{action}'.")
        try:
            return fn((query or "").strip())
        except Exception as e:  # tool failure must never crash the loop
            return ToolResult(f"Tool error: {e}")

    def _pseudo_chunk(self, kind: str, text: str) -> dict:
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return {"chunk_id": f"{kind}_{self._counts[kind]}", "text": text,
                "source": kind, "rerank_score": 1.0, "_tool": True}

    def _search(self, query: str) -> ToolResult:
        if not query:
            return ToolResult("Empty query. Give a focused search query.")
        chunks = self.retriever.retrieve(query, verbose=False)
        if not chunks:
            return ToolResult("No results.")
        lines = [f"[{c['chunk_id']}] ({Path(chunk_source(c)).name}) {_preview(c['text'])}" for c in chunks]
        return ToolResult(f"{len(chunks)} results:\n" + "\n".join(lines), chunks)

    def _calc(self, expr: str) -> ToolResult:
        if not expr or len(expr) > 200:
            return ToolResult("Give a short arithmetic expression.")
        value = safe_eval(expr)
        if isinstance(value, float):
            value = round(value, 10)
        chunk = self._pseudo_chunk("calc", f"{expr} = {value}")
        return ToolResult(f"{expr} = {value} (evidence id: {chunk['chunk_id']})", [chunk])

    def _clock(self, _query: str) -> ToolResult:
        now = dt.datetime.now().astimezone().strftime("%A, %d %B %Y, %H:%M %Z")
        chunk = self._pseudo_chunk("clock", f"Current date and time: {now}")
        return ToolResult(f"{now} (evidence id: {chunk['chunk_id']})", [chunk])

    def _sources(self, _query: str) -> ToolResult:
        from rag import config

        names: list[str] = []
        for d in (config.DEFAULT_DOCS_DIR, config.DEFAULT_PDF_DIR, config.DEFAULT_CODE_DIR):
            p = Path(d)
            if p.exists():
                names += [f.name for f in sorted(p.rglob("*")) if f.is_file() and not f.name.startswith(".")]
        text = "Files in the knowledge base: " + ", ".join(names) if names else "The knowledge base has no files."
        chunk = self._pseudo_chunk("files", text)  # citable evidence, so the final answer can use it
        return ToolResult(f"{text} (evidence id: {chunk['chunk_id']})", [chunk])
