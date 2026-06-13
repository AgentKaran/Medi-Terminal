import os
import sys
from pathlib import Path
from transformers import AutoTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode

# Add the parent folder to Python path to import backend modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.config import (
    QDRANT_PATH,
    EMBED_MODEL,
    DATA_DIR,
    ROLE_COLLECTIONS
)

# Reverse mapping to get access_roles from collection name
def get_access_roles(collection_name: str) -> list:
    access_roles = []
    for role, collections in ROLE_COLLECTIONS.items():
        if collection_name in collections:
            access_roles.append(role)
    return access_roles

def determine_chunk_type(chunk) -> str:
    """
    Determine the type of chunk (text, table, heading, code)
    based on the document items present in the chunk.
    """
    for item in chunk.meta.doc_items:
        label = getattr(item, "label", "").lower()
        class_name = type(item).__name__.lower()
        if "table" in label or "table" in class_name:
            return "table"
        if "code" in label or "code" in class_name:
            return "code"
        if "heading" in label or "heading" in class_name:
            return "heading"
    return "text"

def run_ingestion():
    print("Starting MediBot Document Ingestion Pipeline...")
    
    # 1. Initialize Docling and HybridChunker
    converter = DocumentConverter()
    print("Loading HuggingFace tokenizer for embedding model token alignment...")
    tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL)
    chunker = HybridChunker(
        tokenizer=tokenizer,
        max_tokens=128,
        merge_peers=True
    )
    
    # 2. Find all files
    collections = ["general", "clinical", "nursing", "billing", "equipment"]
    documents_to_process = []
    
    for coll in collections:
        coll_dir = DATA_DIR / coll
        if not coll_dir.exists():
            print(f"Warning: Collection directory {coll_dir} does not exist.")
            continue
            
        for file_path in coll_dir.glob("*"):
            if file_path.suffix.lower() in [".pdf", ".md"]:
                documents_to_process.append((file_path, coll))
                
    print(f"Found {len(documents_to_process)} documents to ingest.")
    
    all_chunks = []
    
    # 3. Process documents
    for file_path, collection_name in documents_to_process:
        print(f"Processing [{collection_name}] {file_path.name}...")
        try:
            # Convert document using Docling
            dl_doc = converter.convert(file_path).document
            
            # Reconstruct heading paths using custom levels
            import re
            item_headings = {}
            active_headings = {}
            
            def get_custom_heading_level(text: str) -> int:
                text_clean = text.strip()
                if text_clean in [
                    "Standard Treatment Protocols", 
                    "Diagnostic Reference Guide", 
                    "Equipment Operation & Maintenance Manual", 
                    "Hospital Staff Handbook",
                    "Insurance Claim Submission Guide",
                    "Insurance Claim Submission & Escalation Guide",
                    "Clinical Reference - First-Line Management Guidelines"
                ]:
                    return 0
                match_letter = re.match(r"^([A-Z])\.\s", text_clean)
                if match_letter:
                    return 1
                match_num = re.match(r"^([0-9\.]+)(\s|\.)", text_clean)
                if match_num:
                    num_str = match_num.group(1).rstrip('.')
                    dots = num_str.count('.')
                    return dots + 1
                if text_clean.lower().startswith("appendix") or text_clean.lower().startswith("disclaimer") or text_clean.lower().startswith("purpose") or text_clean.lower().startswith("quick reference"):
                    return 1
                return 2


            for item, level in dl_doc.iterate_items():
                class_name = type(item).__name__
                if "Header" in class_name or "header" in getattr(item, "label", ""):
                    custom_level = get_custom_heading_level(item.text)
                    active_headings[custom_level] = item.text
                    # Clear deeper levels
                    for l in list(active_headings.keys()):
                        if l > custom_level:
                            active_headings.pop(l)
                
                # Store active headings path for this item's self_ref
                self_ref = getattr(item, "self_ref", None)
                if self_ref:
                    path = [active_headings[l] for l in sorted(active_headings.keys()) if l > 0]
                    item_headings[self_ref] = path
            
            # Chunk document using HybridChunker
            doc_chunks = chunker.chunk(dl_doc=dl_doc)
            
            # Create LangChain documents with metadata
            access_roles = get_access_roles(collection_name)
            
            for chunk in doc_chunks:
                # Reconstruct path using item_headings map
                chunk_headings = []
                for item in chunk.meta.doc_items:
                    self_ref = getattr(item, "self_ref", None)
                    item_path = item_headings.get(self_ref, [])
                    if len(item_path) > len(chunk_headings):
                        chunk_headings = item_path
                
                breadcrumb = " > ".join(chunk_headings)
                content = chunk.text.strip()
                serialized_text = f"{breadcrumb}\n\n{content}" if breadcrumb else content
                
                # Extract section title (use leaf section title or fallback to General)
                section_title = "General"
                if chunk_headings:
                    section_title = chunk_headings[-1]
                    
                chunk_type = determine_chunk_type(chunk)
                
                doc = Document(
                    page_content=serialized_text,
                    metadata={
                        "source_document": file_path.name,
                        "collection": collection_name,
                        "access_roles": access_roles,
                        "section_title": section_title,
                        "chunk_type": chunk_type
                    }
                )
                all_chunks.append(doc)
                
            print(f"  Generated {len(all_chunks)} total chunks so far.")
            
        except Exception as e:
            print(f"  Error processing {file_path.name}: {str(e)}")
            
    if not all_chunks:
        print("No chunks generated. Ingestion aborted.")
        return
        
    print(f"Total chunks generated: {len(all_chunks)}")
    
    # 4. Initialize embedding models
    print("Loading dense embedding model (HuggingFace)...")
    dense_embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )
    
    print("Loading sparse embedding model (FastEmbed BM25)...")
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25", batch_size=32)
    
    # 5. Index chunks in Qdrant Local Store
    print(f"Indexing into local Qdrant collection at: {QDRANT_PATH}")
    collection_name = "medibot_collection"
    
    # Remove old vector store path if we want clean index
    import shutil
    if os.path.exists(QDRANT_PATH):
        print(f"Cleaning existing database at {QDRANT_PATH}...")
        shutil.rmtree(QDRANT_PATH)
        
    vectorstore = QdrantVectorStore.from_documents(
        documents=all_chunks,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        path=QDRANT_PATH,
        collection_name=collection_name,
        retrieval_mode=RetrievalMode.HYBRID
    )
    
    print(f"Success! Indexed {len(all_chunks)} chunks into Qdrant collection '{collection_name}'.")

if __name__ == "__main__":
    run_ingestion()
