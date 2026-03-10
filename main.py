import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from inngest.experimental import ai
from dotenv import load_dotenv
import uuid
import os
import datetime
from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage
from custom_types import RAGQueryResult, RAGSearchResult, RAGUpsertResult, RAGChunkAndSrc

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=True,
    serializer=inngest.PydanticSerializer()
)


@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    # Fixed: Use 'limit' instead of 'count'
    throttle=inngest.Throttle(
        limit=2,  # ✅ Changed from 'count' to 'limit'
        period=datetime.timedelta(minutes=1)
    ),
    rate_limit=inngest.RateLimit(
        limit=1,
        period=datetime.timedelta(hours=4),
        key="event.data.source_id",
    ),
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        logger.info(f"Loaded {len(chunks)} chunks from {pdf_path}")
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)
    
    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        logger.info(f"Embedding {len(chunks)} chunks...")
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        logger.info("Upserting to Qdrant...")
        QdrantStorage().upsert(ids, vecs, payloads)
        logger.info(f"Successfully upserted {len(chunks)} chunks")
        return RAGUpsertResult(ingested=len(chunks))
    
    chunks_and_src = await ctx.step.run(
        "load-and-chunk", 
        lambda: _load(ctx), 
        output_type=RAGChunkAndSrc
    )
    ingested = await ctx.step.run(
        "embed-and-upsert", 
        lambda: _upsert(chunks_and_src), 
        output_type=RAGUpsertResult
    )
    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5) -> RAGSearchResult:
        logger.info(f"Searching for: '{question}' with top_k={top_k}")
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k)
        logger.info(f"Found {len(found['contexts'])} contexts from {len(found['sources'])} sources")
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])
    
    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    
    logger.info(f"Query received: '{question}'")
    
    found = await ctx.step.run(
        "embed-and-search", 
        lambda: _search(question, top_k), 
        output_type=RAGSearchResult
    )
    
    logger.info(f"Search completed. Contexts: {len(found.contexts)}, Sources: {found.sources}")
    
    context_block = "\n\n".join(f"- {c}" for c in found.contexts)
    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above."
    )
    
    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )
    
    logger.info("Calling LLM for answer generation...")
    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You answer questions using only the provided context."},
                {"role": "user", "content": user_content}
            ]
        }
    )
    
    logger.info("LLM response received")
    answer = res["choices"][0]["message"]["content"].strip()
    logger.info(f"Answer generated: {answer[:100]}...")
    
    return {
        "answer": answer, 
        "sources": found.sources, 
        "num_contexts": len(found.contexts)
    }


app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok", "service": "production-ai-support-agent"}

inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])