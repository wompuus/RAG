import os
import re
import streamlit as st

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from vector import vector_store


# ----------------------------
# Config
# ----------------------------
MODEL_NAME = os.getenv("OLLAMA_MODEL", "mannix/llama3.1-8b-abliterated")

RAW_K = 20
SEED_K = 6
FINAL_K = 10
CHUNK_RADIUS = 1
PAGE_RADIUS = 2

model = OllamaLLM(model=MODEL_NAME)
retriever = vector_store.as_retriever(search_kwargs={"k": RAW_K})


# ----------------------------
# Prompts
# ----------------------------
ANSWER_TEMPLATE = """
You are an expert maintenance assistant for equipment manuals.

Answer using ONLY the provided manual context.

Rules:
- Use only the provided context.
- Relevant conversation context is only for resolving references like "it", "that", "same machine", "next step", or similar follow-ups.
- If the context contains a procedure, return the actual procedure steps.
- Do NOT tell the user where the information is located instead of giving the answer.
- Do NOT say "refer to the manual" or "see page" unless the needed step is missing from the context.
- Use numbered steps when the source is procedural.
- Be concise, but include the actual needed details.
- Cite every factual claim or step with the source and page label like:
  (Source: AutoBagger.pdf, Page: 5-77)
- If the answer is only partial, say exactly what part is missing.
- If the answer is not in the context, say exactly:
  "I couldn't find that information in the indexed manuals."
- Do not guess.
- Prefer specific procedural or troubleshooting content over general safety or introduction text.

Relevant conversation context:
{conversation}

Question:
{question}

Context from manuals:
{manuals}

Answer:
"""

REFINE_TEMPLATE = """
The user asked:
"{question}"

The current answer was:
"{result}"

Conversation history:
{history}

The user clicked "Not helpful? Refine search".

Generate a better retrieval query for equipment manuals.
Focus on:
- exact component names
- exact procedure names
- exact alarms or fault names
- machine-specific wording
- replacement / removal / installation wording if relevant

Return only the improved query.
"""

answer_chain = ChatPromptTemplate.from_template(ANSWER_TEMPLATE) | model
refine_chain = ChatPromptTemplate.from_template(REFINE_TEMPLATE) | model


# ----------------------------
# Session state
# ----------------------------
def init_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None


# ----------------------------
# Retrieval helpers
# ----------------------------
def tokenize(text: str):
    return [t for t in re.findall(r"[a-zA-Z0-9_./-]+", text.lower()) if len(t) > 2]


def classify_query(question: str):
    q = question.lower()
    if any(w in q for w in ["safe", "safety", "hazard", "ppe", "lockout", "loto"]):
        return "safety"
    return "operational"


def rerank_docs(question: str, docs):
    q_terms = tokenize(question)
    q_lower = question.lower()
    mode = classify_query(question)

    scored = []

    for doc in docs:
        text = doc.page_content.lower()
        meta = doc.metadata or {}

        section = str(meta.get("section", "unknown")).lower()
        page_num = int(meta.get("page", 9999))
        manual = str(meta.get("manual", meta.get("source", ""))).lower()

        score = 0.0

        # Exact token overlap
        exact_hits = sum(1 for term in q_terms if term in text)
        score += exact_hits * 2.5

        # Exact full-question match
        if q_lower in text:
            score += 6.0

        # Procedure-heavy terms
        phrase_bonuses = [
            "possible cause",
            "possible causes",
            "remedy",
            "remedies",
            "fault",
            "alarm",
            "error",
            "check",
            "adjust",
            "replace",
            "replacement",
            "remove",
            "removal",
            "install",
            "installation",
            "procedure",
            "step",
            "steps",
            "solution",
            "tighten",
            "loosen",
            "inspect",
            "verify",
            "perform",
            "route the belt",
            "remove tension",
        ]
        for phrase in phrase_bonuses:
            if phrase in text:
                score += 1.0

        # Strong alignment bonuses
        if "replacement" in q_lower or "replace" in q_lower:
            if "replacement" in text or "replace" in text:
                score += 3.0

        if "removal" in q_lower or "remove" in q_lower:
            if "removal" in text or "remove" in text:
                score += 3.0

        if "installation" in q_lower or "install" in q_lower:
            if "installation" in text or "install" in text:
                score += 3.0

        # Section weighting
        if mode == "operational":
            if section == "troubleshooting":
                score += 8.0
            elif section == "alarms":
                score += 7.0
            elif section == "maintenance":
                score += 8.0
            elif section == "setup":
                score += 4.0
            elif section == "installation":
                score += 5.0
            elif section == "theory of operation":
                score += 1.0
            elif section == "safety":
                score -= 5.0
            elif section == "general description":
                score -= 3.0
            elif section == "unknown":
                score -= 1.0
        else:
            if section == "safety":
                score += 6.0

        # Penalize front matter for operational questions
        if mode == "operational" and page_num < 20 and section in {
            "safety",
            "general description",
            "unknown",
        }:
            score -= 2.0

        # Manual name bonus
        manual_terms = tokenize(manual)
        if any(term in q_terms for term in manual_terms):
            score += 2.0

        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored]


def doc_key(doc: Document):
    meta = doc.metadata or {}
    return (
        meta.get("source"),
        meta.get("page"),
        meta.get("chunk"),
    )


def dedupe_docs(docs):
    seen = set()
    out = []

    for doc in docs:
        key = doc_key(doc)
        if key not in seen:
            seen.add(key)
            out.append(doc)

    return out


def expand_neighbor_chunks(seed_docs, chunk_radius=1, page_radius=2):
    wanted_ids = set()

    for doc in seed_docs:
        meta = doc.metadata or {}
        source = meta.get("source")
        page = meta.get("page")
        chunk = meta.get("chunk")
        section = str(meta.get("section", "unknown")).lower()

        if source is None or page is None or chunk is None:
            continue

        # Skip weak context unless explicitly needed
        if section in {"safety", "general description"}:
            continue

        for p in range(max(1, int(page) - page_radius), int(page) + page_radius + 1):
            for c in range(max(0, int(chunk) - chunk_radius), int(chunk) + chunk_radius + 1):
                wanted_ids.add(f"{source}_page_{p}_chunk_{c}")

    if not wanted_ids:
        return []

    raw = vector_store._collection.get(
        ids=list(wanted_ids),
        include=["documents", "metadatas"],
    )

    neighbors = []
    documents = raw.get("documents", []) or []
    metadatas = raw.get("metadatas", []) or []

    for text, meta in zip(documents, metadatas):
        if text and meta:
            neighbors.append(Document(page_content=text, metadata=meta))

    return neighbors


def format_manuals(final_docs):
    blocks = []

    for doc in final_docs:
        meta = doc.metadata or {}
        source = meta.get("source", "Unknown")
        section = meta.get("section", "Unknown")
        display_page = meta.get("display_page", meta.get("page", "Unknown"))

        blocks.append(
            f"Source: {source}, Section: {section}, Page: {display_page}\n{doc.page_content}"
        )

    return "\n\n".join(blocks)


def build_manual_context(question: str):
    raw_docs = retriever.invoke(question)
    reranked = rerank_docs(question, raw_docs)

    seed_docs = reranked[:SEED_K]
    neighbor_docs = expand_neighbor_chunks(
        seed_docs,
        chunk_radius=CHUNK_RADIUS,
        page_radius=PAGE_RADIUS,
    )

    combined = dedupe_docs(seed_docs + neighbor_docs)
    final_docs = rerank_docs(question, combined)[:FINAL_K]

    return format_manuals(final_docs)


# ----------------------------
# Conversation helpers
# ----------------------------
def conversation_text(messages):
    return "\n".join(
        [f"{msg['role'].title()}: {msg['content']}" for msg in messages]
    )


def is_followup_question(question: str) -> bool:
    q = question.lower().strip()

    explicit_phrases = [
        "what about",
        "how about",
        "same machine",
        "same one",
        "same manual",
        "that machine",
        "this machine",
        "that one",
        "this one",
        "that procedure",
        "this procedure",
        "that step",
        "this step",
        "those steps",
        "next step",
        "previous step",
        "other machine",
        "other manual",
        "does it say",
        "does it mention",
        "why is that",
        "why does it",
        "for that one",
        "on that machine",
        "for the same machine",
        "for the other machine",
        "reinstall it",
        "remove it",
        "replace it",
        "install it",
    ]

    if any(phrase in q for phrase in explicit_phrases):
        return True

    # Starts with a reference word
    if re.match(r"^(it|that|this|they|them|those|these)\b", q):
        return True

    # Explicit step/page follow-up
    if re.search(r"\b(step|page)\s+\d+\b", q):
        return True

    # Very short referential questions like "what about it?" or "and the other one?"
    referential_terms = {
        "it", "that", "this", "they", "them", "those", "these",
        "other", "same", "one", "ones"
    }
    words = re.findall(r"[a-zA-Z0-9']+", q)
    if len(words) <= 6 and any(word in referential_terms for word in words):
        return True

    return False


def recent_relevant_history(messages, max_turns=2):
    """
    Return only the most recent turns, not the entire conversation.
    """
    if not messages:
        return ""

    trimmed = messages[-(max_turns * 2):]
    return "\n".join(
        f"{msg['role'].title()}: {msg['content']}"
        for msg in trimmed
    )


def generate_answer(question: str):
    manuals = build_manual_context(question)

    history = ""
    if is_followup_question(question):
        history = recent_relevant_history(st.session_state.messages, max_turns=2)

    result = answer_chain.invoke(
        {
            "conversation": history,
            "question": question,
            "manuals": manuals,
        }
    )

    return result, manuals


def refine_last_answer():
    messages = st.session_state.messages

    last_assistant_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "assistant":
            last_assistant_idx = i
            break

    if last_assistant_idx is None:
        return

    last_user_idx = None
    for i in range(last_assistant_idx - 1, -1, -1):
        if messages[i]["role"] == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        return

    question = messages[last_user_idx]["content"]
    last_answer = messages[last_assistant_idx]["content"]
    history = conversation_text(messages[:last_assistant_idx])

    better_query = refine_chain.invoke(
        {
            "question": question,
            "result": last_answer,
            "history": history,
        }
    ).strip()

    manuals = build_manual_context(better_query)

    refined_history = ""
    if is_followup_question(question):
        refined_history = recent_relevant_history(messages[:last_assistant_idx], max_turns=2)

    refined_answer = answer_chain.invoke(
        {
            "conversation": refined_history,
            "question": question,
            "manuals": manuals,
        }
    )

    messages[last_assistant_idx] = {
        "role": "assistant",
        "content": f"[Refined retrieval query: {better_query}]\n\n{refined_answer}",
        "sources": manuals,
    }


# ----------------------------
# UI
# ----------------------------
init_state()
st.title("Ask FreshBot")

# Render chat history
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant" and message.get("sources"):
            with st.expander("View source chunks"):
                st.text(message["sources"])

        is_latest = idx == len(st.session_state.messages) - 1
        if message["role"] == "assistant" and is_latest:
            if st.button("Not helpful? Refine search", key="refine_latest"):
                with st.spinner("Refining search..."):
                    refine_last_answer()
                st.rerun()

# Handle new user input
question = st.chat_input("Ask your question here:")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.pending_question = question
    st.rerun()

# Generate pending assistant response
if st.session_state.pending_question:
    question = st.session_state.pending_question

    with st.chat_message("assistant"):
        with st.spinner("Searching manuals..."):
            answer, manuals = generate_answer(question)
            st.markdown(answer)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": manuals,
        }
    )
    st.session_state.pending_question = None
    st.rerun()