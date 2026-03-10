# production-ai-support-agent

A minimal Retrieval-Augmented Generation (RAG) demo that ingests PDFs, stores text chunks in Qdrant, and answers questions using an LLM with Inngest orchestration and a Streamlit UI. ✅

---

## 🚀 Overview

This project demonstrates a small RAG pipeline:

- Ingest PDFs and split them into text chunks (llama-index PDFReader + SentenceSplitter)
- Create embeddings (OpenAI embeddings API)
- Store vectors and payloads in **Qdrant** for similarity search
- Use **Inngest** functions to orchestrate ingest and query flows
- Provide a simple **Streamlit** UI to upload PDFs and ask questions

---

## 🔧 Features

- PDF ingestion pipeline with chunking, embedding, and upsert to Qdrant
- Query flow that retrieves top-K contexts and asks an LLM (via Inngest AI adapters) to answer
- FastAPI + Inngest integration for function serving
- Streamlit app for easy local testing and demos

---

## 🧩 Architecture

- `main.py` — Inngest functions: `rag_ingest_pdf` and `rag_query_pdf_ai`
- `data_loader.py` — PDF loading, chunking, and embedding helpers
- `vector_db.py` — Qdrant client wrapper (upsert & search)
- `streamlit_app.py` — Lightweight UI to upload PDFs and query the system
- `custom_types.py` — Pydantic models used across Inngest steps

---

## ⚙️ Prerequisites

- Python 3.12+ (project `pyproject.toml` requires >=3.12)
- Docker (recommended for running Qdrant locally)
- An OpenAI API key with embeddings access

---

## 🏁 Quickstart (local)

1. Create a virtual env and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables

```bash
export OPENAI_API_KEY="sk-..."
# (Optional) override Qdrant URL: export QDRANT_URL="http://localhost:6333"
```

3. Start Qdrant (Docker)

```bash
# Quick local Qdrant (default port 6333)
docker run -p 6333:6333 qdrant/qdrant
```

4. Start the FastAPI app (serves Inngest endpoints)

```bash
uvicorn main:app --reload --port 8000
```

5. Start the Inngest dashboard (local dev dashboard assumed at http://localhost:8288)

- Ensure your Inngest dev environment/dashboard is running and reachable. See Inngest docs for your chosen setup.

6. Start the Streamlit UI

```bash
streamlit run streamlit_app.py
```

Open the Streamlit app (usually at http://localhost:8501) to upload PDFs and ask questions.

---

## 📌 Usage

### Ingest via Streamlit
1. Upload a PDF in the **Upload PDF** panel
2. Click **Ingest PDF** — the app triggers an Inngest event and waits for the run to finish

### Query via Streamlit
1. Enter a question and select the number of chunks (top_k)
2. Submit the query — the app triggers the query Inngest event and displays the answer + sources

### Programmatic example (Python)

```py
import inngest
client = inngest.Inngest(app_id="rag_app", is_production=False)

# Ingest a PDF
event_ids = client.send_sync(
    inngest.Event(
        name="rag/ingest_pdf",
        data={"pdf_path": "/abs/path/to/file.pdf", "source_id": "file.pdf"}
    )
)

# Query
event_ids = client.send_sync(
    inngest.Event(
        name="rag/query_pdf_ai",
        data={"question": "What is this document about?", "top_k": 5}
    )
)
```

---

## 🛠️ Development notes

- Embedding model: `text-embedding-3-large` (EMBED_DIM=3072). Keep this consistent across `data_loader.py` and `vector_db.py`.
- Pydantic models are defined in `custom_types.py` (used by Inngest as typed payloads).
- `vector_db.py` wraps Qdrant. It creates the collection if missing and exposes `upsert` and `search`.
- Logging is configured in `main.py` for visibility during runs.

---

## 🧪 Tests & CI

- Add unit tests to validate chunking, embedding shapes, and vector upsert/search behavior.
- Add basic CI steps: lint, type-check (mypy), and `pip-audit` for dependency security.

---

## ⚠️ Troubleshooting

- If the Streamlit app shows Inngest / FastAPI / Qdrant as offline, verify services are running and accessible at:
  - Inngest dashboard: http://localhost:8288
  - FastAPI (uvicorn): http://localhost:8000
  - Qdrant: http://localhost:6333
- If embeddings fail, ensure `OPENAI_API_KEY` is set and has the necessary permissions.
- If returned embedding lengths don't match `EMBED_DIM`, check the model and update `EMBED_DIM` accordingly.

---

## 🤝 Contributing

Contributions are welcome! Please open issues or PRs for bugs, improvements, or feature requests. Keep changes small and include tests when possible.

---

## 📜 License

This project is provided as-is. Add an appropriate license file (`LICENSE`) if you intend to open-source it.

---

Happy building! ⚡
