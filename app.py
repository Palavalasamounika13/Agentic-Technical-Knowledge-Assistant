"""Agentic Technical Q&A bot.   Run:  streamlit run app.py

Sidebar : upload files, optional git repo, build index, manage files, agent settings, export chat.
Main    : chat with live agent steps, confidence, timing, expandable reasoning and cited sources.
"""
import gc
import shutil
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from agent.core import MAX_STEPS, Agent
from rag import config

st.set_page_config(page_title="Agentic Q&A", page_icon="🤖", layout="wide")

ROOT = Path(__file__).resolve().parent
# Where the built index lives. Uses config.STORAGE_DIR if your rag/config.py defines it.
STORAGE_DIR = Path(getattr(config, "STORAGE_DIR", ROOT / "storage"))

DOCS_DIR = Path(config.DEFAULT_DOCS_DIR)
PDF_DIR = Path(config.DEFAULT_PDF_DIR)
CODE_DIR = Path(config.DEFAULT_CODE_DIR)

DOC_EXT = {".md", ".txt", ".html", ".htm"}
PDF_EXT = {".pdf"}
CODE_EXT = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".cs", ".rb", ".php"}
TARGETS = [(DOC_EXT, DOCS_DIR), (PDF_EXT, PDF_DIR), (CODE_EXT, CODE_DIR)]
UPLOAD_TYPES = sorted(e.lstrip(".") for e in DOC_EXT | PDF_EXT | CODE_EXT)
CONF_COLOR = {"high": "green", "medium": "orange", "low": "red"}
STARTERS = [
    "What documents are in the knowledge base?",
    "Summarize the main topics covered in my documents.",
    "What is the current date and time?",
]

for key, default in (("messages", []), ("uploader_key", 0),
                     ("flash", None), ("chunks", None), ("pending", None)):
    st.session_state.setdefault(key, default)

st.markdown(
    "<style>.block-container{padding-top:2rem;max-width:1100px}</style>", unsafe_allow_html=True
)


# ---------- helpers ----------
@st.cache_resource(show_spinner="Loading indices and models...")
def get_agent() -> Agent:
    return Agent()


def target_dir(filename: str):
    ext = Path(filename).suffix.lower()
    return next((folder for exts, folder in TARGETS if ext in exts), None)


def save_uploads(files) -> int:
    saved = 0
    for f in files:
        folder = target_dir(f.name)
        if folder is None:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        (folder / Path(f.name).name).write_bytes(f.getbuffer())
        saved += 1
    return saved


def list_files() -> list[Path]:
    found: list[Path] = []
    for folder in (DOCS_DIR, PDF_DIR, CODE_DIR):
        if folder.exists():
            found += [p for p in sorted(folder.rglob("*")) if p.is_file() and not p.name.startswith(".")]
    return found


def rebuild_index(repo_url: str) -> int:
    from rag.chunking import chunk_all
    from rag.indexing import build_all_indices
    from rag.ingest import ingest_all

    get_agent.clear()  # release index handles first (Windows file locks)
    gc.collect()
    with st.status("Building index...", expanded=True) as status:
        st.write("Reading files")
        raw = ingest_all(repo_url=repo_url or None, docs_folder=str(DOCS_DIR),
                         pdf_folder=str(PDF_DIR), code_folder=str(CODE_DIR))
        st.write("Chunking")
        chunks = chunk_all(raw)
        st.write(f"Indexing {len(chunks)} chunks")
        build_all_indices(chunks)
        status.update(label=f"Index ready: {len(chunks)} chunks", state="complete", expanded=False)
    st.session_state.chunks = len(chunks)
    return len(chunks)


def clear_index():
    """Delete the built index so removed files can no longer be answered from."""
    get_agent.clear()
    gc.collect()
    if STORAGE_DIR.exists():
        shutil.rmtree(STORAGE_DIR)
    st.session_state.chunks = None


def history_from(messages: list[dict]) -> list[dict]:
    pairs, q = [], None
    for m in messages:
        if m["role"] == "user":
            q = m["content"]
        elif q is not None:
            pairs.append({"question": q, "answer": m["answer"]})
            q = None
    return pairs


def describe(ev: dict) -> str:
    if ev["type"] == "plan":
        subs = "".join(f"\n  - {q}" for q in ev["sub_questions"])
        return f"**Plan:** {ev['standalone_question']}{subs}"
    if ev["action"] == "finish":
        return f"**Step {ev['n']}:** finish. {ev['thought']}"
    return f"**Step {ev['n']}:** `{ev['action']}({ev['query']})`. {ev['thought']}"


def friendly_error(e: Exception) -> str:
    text = str(e)
    low = text.lower()
    if "429" in text or "rate limit" in low or "rate_limit" in low:
        return "Rate limit reached. Wait a minute and retry, or lower Max steps."
    if "401" in text or "invalid api key" in low:
        return "API key rejected. Check GROQ_API_KEY in .env."
    if "404" in text and "model" in low:
        return "Model not available on your Groq account. Set GROQ_MODEL in .env."
    return f"Something went wrong: {text}"


def render_answer(msg: dict):
    st.markdown(msg["answer"])
    conf = msg["confidence"]
    n_src = len(msg["sources"])
    st.caption(
        f"Confidence: :{CONF_COLOR.get(conf, 'gray')}[**{conf}**]  ·  {msg['steps']} steps  ·  "
        f"{msg['seconds']:.1f}s  ·  {n_src} source{'s' if n_src != 1 else ''}"
    )
    if msg["events"]:
        with st.expander("Agent reasoning"):
            for ev in msg["events"]:
                st.markdown(describe(ev))
                if ev["type"] == "step" and ev["observation"]:
                    st.code(ev["observation"], language="text")
    for s in msg["sources"]:
        with st.expander(f"📄 [{s['id']}] {Path(s['source']).name}"):
            st.code(s["text"], language="markdown")
            st.caption(f"{s['source']}  ·  rerank score {s['score']:.3f}")


def transcript_md(messages: list[dict]) -> str:
    out = [f"# Chat export ({datetime.now():%Y-%m-%d %H:%M})\n"]
    for m in messages:
        if m["role"] == "user":
            out.append(f"## Q: {m['content']}\n")
        else:
            srcs = ", ".join(sorted({Path(s["source"]).name for s in m["sources"]})) or "none"
            out.append(f"{m['answer']}\n\n*Confidence: {m['confidence']} · Sources: {srcs}*\n")
    return "\n".join(out)


# ---------- sidebar ----------
with st.sidebar:
    st.header("📁 Knowledge base")
    if st.session_state.flash:
        st.success(st.session_state.flash)
        st.session_state.flash = None

    uploads = st.file_uploader(
        "Upload files", type=UPLOAD_TYPES, accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
        help="Docs (.md .txt .html), text-based PDFs and source code.",
    )
    repo_url = st.text_input("Git repo URL (optional)", placeholder="https://github.com/org/repo")
    if st.button("Build index", type="primary", use_container_width=True):
        try:
            n_saved = save_uploads(uploads or [])
            n_chunks = rebuild_index(repo_url.strip())
            st.session_state.flash = f"Saved {n_saved} file(s). Indexed {n_chunks} chunks."
            st.session_state.uploader_key += 1
            st.rerun()
        except Exception as e:
            st.error(f"Build failed: {e}")

    files = list_files()
    with st.expander(f"Files ({len(files)})"):
        if files:
            doomed = st.multiselect("Select files to delete", files, format_func=lambda p: p.name)
            st.caption("Deleting also rebuilds the index, so removed files stop appearing in answers.")
            if st.button("Delete selected & rebuild", disabled=not doomed):
                for p in doomed:
                    p.unlink(missing_ok=True)
                try:
                    if list_files() or repo_url.strip():
                        n_chunks = rebuild_index(repo_url.strip())
                        st.session_state.flash = f"Deleted {len(doomed)} file(s). Index rebuilt: {n_chunks} chunks."
                    else:
                        clear_index()
                        st.session_state.flash = "Knowledge base is empty. Index cleared."
                    st.session_state.messages = []  # old answers came from the old index
                    st.rerun()
                except PermissionError:
                    st.error("Index files are locked. Stop the app (Ctrl+C), delete the storage folder, restart.")
                except Exception as e:
                    st.error(f"Rebuild failed: {e}")
        else:
            st.caption("No files yet.")
    if st.session_state.chunks is not None:
        st.caption(f"Last build: {st.session_state.chunks} chunks")

    st.divider()
    st.header("🤖 Agent")
    max_steps = st.slider("Max steps per question", 1, 8, MAX_STEPS,
                          help="More steps = deeper search, slower answers, more API calls.")
    show_live = st.toggle("Show live reasoning", value=True)
    st.caption("Tools: search_docs, calculator, get_datetime, list_sources")

    st.divider()
    if st.session_state.messages:
        st.download_button("Download chat (.md)", transcript_md(st.session_state.messages),
                           file_name="chat.md", mime="text/markdown", use_container_width=True)
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ---------- main ----------
st.title("🤖 Agentic Technical Q&A")
st.caption("Plans, searches several times, calculates, then answers with cited sources.")

try:
    agent = get_agent()
except RuntimeError as e:
    st.info("No index yet. Upload files in the sidebar, then click **Build index**.")
    st.caption(str(e))
    st.stop()

if not st.session_state.messages:
    st.markdown("##### Try one of these")
    cols = st.columns(len(STARTERS))
    for col, text in zip(cols, STARTERS):
        if col.button(text, use_container_width=True):
            st.session_state.pending = text
            st.rerun()

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            render_answer(m)

question = st.chat_input("Ask about your docs, code or PDFs") or st.session_state.pop("pending", None)
if question:
    history = history_from(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        events: list[dict] = []
        t0 = time.perf_counter()
        with st.status("Agent working...", expanded=show_live) as status:
            def on_step(ev: dict):
                events.append(ev)
                if show_live:
                    st.markdown(describe(ev))

            try:
                result = agent.run(question, history=history, max_steps=max_steps, on_step=on_step)
            except Exception as e:
                status.update(label="Failed", state="error")
                st.session_state.messages.pop()  # drop the unanswered question
                st.error(friendly_error(e))
                st.stop()
            status.update(label=f"Done in {result.steps_used} steps", state="complete", expanded=False)

        msg = {
            "role": "assistant", "answer": result.answer, "confidence": result.confidence,
            "sources": result.citations, "events": events, "steps": result.steps_used,
            "seconds": time.perf_counter() - t0,
        }
        render_answer(msg)
    st.session_state.messages.append(msg)
