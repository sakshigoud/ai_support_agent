from pathlib import Path
import time
import tempfile
import streamlit as st
import inngest
from dotenv import load_dotenv
import requests
import os

load_dotenv()

st.set_page_config(page_title="RAG PDF System", page_icon="📄", layout="wide")

# Production URLs
BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "https://production-ai-support-agent-production.up.railway.app"
)

INNGEST_API_BASE = "https://api.inngest.com/v1"
INNGEST_EVENT_KEY = os.getenv("INNGEST_EVENT_KEY", "")


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    """Get Inngest client for production"""
    event_key = os.getenv("INNGEST_EVENT_KEY")
    
    if event_key:
        return inngest.Inngest(
            app_id="rag_app",
            is_production=True,
            event_key=event_key
        )
    else:
        # Fallback mode - events sent but can't poll results
        return inngest.Inngest(
            app_id="rag_app",
            is_production=True
        )


def save_uploaded_pdf_temp(file) -> Path:
    """Save uploaded file to temp directory"""
    temp_dir = Path(tempfile.gettempdir()) / "rag_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = temp_dir / file.name
    
    # Write file bytes
    with open(file_path, "wb") as f:
        f.write(file.getbuffer())
    
    return file_path


def get_run_output(event_id: str, timeout: int = 120) -> dict:
    """Poll Inngest for run output"""
    if not INNGEST_EVENT_KEY:
        return {
            "success": False,
            "error": "INNGEST_EVENT_KEY not set. Check Inngest Dashboard manually."
        }
    
    start_time = time.time()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"{INNGEST_API_BASE}/events/{event_id}/runs",
                headers={"Authorization": f"Bearer {INNGEST_EVENT_KEY}"},
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                runs = data.get("data", [])
                
                if runs:
                    run = runs[0]
                    status = run.get("status", "Unknown")
                    
                    # Update progress
                    elapsed = time.time() - start_time
                    progress = min(elapsed / timeout, 1.0)
                    progress_bar.progress(progress)
                    status_text.text(f"Status: {status}")
                    
                    # Check completion
                    if status in ["Completed", "Succeeded", "Finished"]:
                        progress_bar.empty()
                        status_text.empty()
                        return {
                            "success": True,
                            "output": run.get("output", {})
                        }
                    
                    if status in ["Failed", "Cancelled"]:
                        progress_bar.empty()
                        status_text.empty()
                        return {
                            "success": False,
                            "error": f"Run {status.lower()}"
                        }
            
            time.sleep(1)
        
        except requests.exceptions.RequestException as e:
            progress_bar.empty()
            status_text.empty()
            return {
                "success": False,
                "error": f"Network error: {str(e)}"
            }
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            return {
                "success": False,
                "error": f"Error: {str(e)}"
            }
    
    # Timeout
    progress_bar.empty()
    status_text.empty()
    return {
        "success": False,
        "error": "Timeout waiting for result"
    }


# ====== MAIN UI ======

st.title("📄 RAG PDF System")

# Sidebar Status
with st.sidebar:
    st.header("🔧 System Status")
    
    # Check Backend
    try:
        r = requests.get(f"{BACKEND_URL}/", timeout=3)
        if r.status_code == 200:
            st.success("✅ Backend API")
        else:
            st.error(f"❌ Backend ({r.status_code})")
    except Exception as e:
        st.error(f"❌ Backend (unreachable)")
    
    # Check Inngest
    try:
        r = requests.get(f"{BACKEND_URL}/api/inngest", timeout=3)
        if r.status_code == 200:
            data = r.json()
            st.success(f"✅ Inngest ({data.get('function_count', 0)} functions)")
        else:
            st.error(f"❌ Inngest ({r.status_code})")
    except Exception as e:
        st.error(f"❌ Inngest (unreachable)")
    
    st.divider()
    
    # Show config
    st.caption("Backend URL:")
    st.code(BACKEND_URL, language="text")
    
    if INNGEST_EVENT_KEY:
        st.caption("✅ Event key configured")
    else:
        st.caption("⚠️ No event key (manual check needed)")
    
    st.divider()
    st.link_button("📊 Inngest Dashboard", "https://app.inngest.com")


# Two-column layout
col1, col2 = st.columns(2)

# ====== LEFT: PDF Upload ======
with col1:
    st.header("1️⃣ Upload PDF")
    
    uploaded = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        help="Upload a PDF to ingest into the RAG system"
    )
    
    if uploaded:
        st.info(f"📄 Selected: {uploaded.name} ({uploaded.size / 1024:.1f} KB)")
        
        if st.button("🚀 Ingest PDF", use_container_width=True, type="primary"):
            with st.spinner("Uploading and triggering ingestion..."):
                try:
                    # Save file temporarily
                    file_path = save_uploaded_pdf_temp(uploaded)
                    
                    # Get Inngest client
                    client = get_inngest_client()
                    
                    # Send event
                    event_ids = client.send_sync(
                        inngest.Event(
                            name="rag/ingest_pdf",
                            data={
                                "pdf_path": str(file_path),
                                "source_id": uploaded.name
                            }
                        )
                    )
                    
                    if event_ids and len(event_ids) > 0:
                        event_id = event_ids[0]
                        st.success(f"✅ Ingestion started!")
                        st.caption(f"Event ID: `{event_id}`")
                        
                        # Try to get result
                        result = get_run_output(event_id)
                        
                        if result["success"]:
                            output = result["output"]
                            chunks = output.get("ingested", 0)
                            st.success(f"🎉 Successfully ingested **{chunks} chunks**!")
                        elif "INNGEST_EVENT_KEY not set" in result.get("error", ""):
                            st.info("💡 Check [Inngest Dashboard](https://app.inngest.com) for progress")
                        else:
                            st.warning(f"⚠️ {result.get('error', 'Unknown error')}")
                            st.info("Check Inngest Dashboard for details")
                    else:
                        st.error("❌ Failed to trigger ingestion (no event ID)")
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)


# ====== RIGHT: Query ======
with col2:
    st.header("2️⃣ Ask Questions")
    
    with st.form("query_form", clear_on_submit=False):
        question = st.text_input(
            "Your question",
            placeholder="e.g., Who is Sakshi?",
            help="Ask anything about the uploaded PDFs"
        )
        
        top_k = st.slider(
            "Number of context chunks",
            min_value=1,
            max_value=10,
            value=5,
            help="More chunks = more context but slower"
        )
        
        submitted = st.form_submit_button(
            "🔍 Search",
            use_container_width=True,
            type="primary"
        )
        
        if submitted and question.strip():
            with st.spinner("Searching and generating answer..."):
                try:
                    client = get_inngest_client()
                    
                    # Send query event
                    event_ids = client.send_sync(
                        inngest.Event(
                            name="rag/query_pdf_ai",
                            data={
                                "question": question.strip(),
                                "top_k": top_k
                            }
                        )
                    )
                    
                    if event_ids and len(event_ids) > 0:
                        event_id = event_ids[0]
                        st.success("✅ Query submitted!")
                        st.caption(f"Event ID: `{event_id}`")
                        
                        # Get result
                        result = get_run_output(event_id)
                        
                        if result["success"]:
                            output = result["output"]
                            
                            # Display answer
                            st.subheader("💡 Answer")
                            answer = output.get("answer", "No answer generated")
                            st.markdown(answer)
                            
                            # Display sources
                            sources = output.get("sources", [])
                            num_contexts = output.get("num_contexts", 0)
                            
                            if sources:
                                st.subheader("📚 Sources")
                                st.caption(f"Used {num_contexts} context chunks from:")
                                for source in sources:
                                    st.write(f"- {source}")
                        
                        elif "INNGEST_EVENT_KEY not set" in result.get("error", ""):
                            st.info("💡 Check [Inngest Dashboard](https://app.inngest.com) for answer")
                        
                        else:
                            st.warning(f"⚠️ {result.get('error', 'Unknown error')}")
                            st.info("Check Inngest Dashboard for details")
                    
                    else:
                        st.error("❌ Failed to submit query (no event ID)")
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)


# Footer
st.divider()
st.caption("💡 **Tip:** Add `INNGEST_EVENT_KEY` in secrets for real-time results!")
st.caption("🔗 Backend: " + BACKEND_URL)