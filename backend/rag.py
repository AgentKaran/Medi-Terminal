import os
import sys
import re
from pathlib import Path
import sqlite3
from sentence_transformers import CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from langchain_groq import ChatGroq

# Add the parent folder to Python path to import backend modules
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    EMBED_MODEL,
    RERANK_MODEL,
    DB_PATH,
    QDRANT_PATH,
    ROLE_COLLECTIONS,
    COLLECTION_DISPLAY_NAMES
)
from backend.database import get_schema_info, execute_read_query

# 1. Initialize LLM
llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model_name=GROQ_MODEL,
    temperature=0.0
)

# Lazy-loaded models to avoid initial import overhead
_dense_embeddings = None
_sparse_embeddings = None
_vectorstore = None
_cross_encoder = None

def get_dense_embeddings():
    global _dense_embeddings
    if _dense_embeddings is None:
        _dense_embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
    return _dense_embeddings

def get_sparse_embeddings():
    global _sparse_embeddings
    if _sparse_embeddings is None:
        _sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25", batch_size=32)
    return _sparse_embeddings

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        # Check if vectorstore exists
        if not os.path.exists(QDRANT_PATH):
            raise FileNotFoundError(f"Vector store not found at {QDRANT_PATH}. Please run ingest.py first.")
        _vectorstore = QdrantVectorStore.from_existing_collection(
            embedding=get_dense_embeddings(),
            sparse_embedding=get_sparse_embeddings(),
            path=QDRANT_PATH,
            collection_name="medibot_collection",
            retrieval_mode=RetrievalMode.HYBRID
        )
    return _vectorstore

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder(RERANK_MODEL)
    return _cross_encoder

# 2. Query Routing and RBAC Guardrails
def is_analytical_question(question: str) -> bool:
    """
    Classifies if the question is an analytical/numerical query that should go to the SQL database.
    """
    prompt = f"""You are a query routing assistant for a healthcare network database.
Analyze the user's question and decide if it is a quantitative, statistical, or numerical query about claims or equipment maintenance tickets that lives in a database table.
Database tables available:
1. 'claims': contains claims data across departments, insurers, claimed and approved amounts, dates, and status.
2. 'maintenance_tickets': contains equipment tickets, category, campus, issue types, raised date, resolved date, status, and notes.

User Question: "{question}"

Answer with ONLY "YES" if it requires database statistics/metrics, or "NO" if it asks about general procedures, treatment protocols, medical guides, drug information, or policies.
Response:"""
    
    response = llm.invoke(prompt)
    answer = response.content.strip().upper()
    return "YES" in answer

def get_target_collection_for_question(question: str) -> str:
    """
    Uses the LLM to identify which document collection the question refers to.
    Returns one of: 'general', 'clinical', 'nursing', 'billing', 'equipment'.
    """
    prompt = f"""You are a document classifier for a hospital network.
Classify the user's question into ONE of the following 5 document collections it is asking about:
- 'general': Hospital HR handbooks, staff leave policies, code of conduct, general FAQs.
- 'clinical': Treatment protocols, drug formulary, diagnostic reference guides.
- 'nursing': ICU nursing procedures, infection control guidelines.
- 'billing': Insurance billing code references, claim submission guides.
- 'equipment': Equipment operation, calibration, maintenance manuals.

User Question: "{question}"

Answer with ONLY the lowercase collection name (one of: general, clinical, nursing, billing, equipment). If it's a general greeting or does not target a specific collection, return "general".
Response:"""
    
    response = llm.invoke(prompt)
    answer = response.content.strip().lower()
    
    for coll in ["general", "clinical", "nursing", "billing", "equipment"]:
        if coll in answer:
            return coll
    return "general"

def check_rbac_access(role: str, target_collection: str) -> tuple[bool, str]:
    """
    Checks if a role has access to a target collection.
    Returns (has_access, refusal_message).
    """
    allowed_collections = ROLE_COLLECTIONS.get(role, ["general"])
    if target_collection in allowed_collections:
        return True, ""
    
    # Generate custom refusal message
    accessible_names = [COLLECTION_DISPLAY_NAMES[c] for c in allowed_collections]
    accessible_str = ", ".join(accessible_names)
    
    refusal = f"As a {role}, you do not have access to {target_collection} documents. I can only answer questions from the following collections: {accessible_str}."
    return False, refusal

# 3. Component 4: SQL RAG Chain
def clean_sql_query(raw_sql: str) -> str:
    """
    Clean raw LLM output to extract only the SQL query statement.
    """
    cleaned = raw_sql.strip()
    
    # Strip markdown block quotes
    if "```" in cleaned:
        # Extract content between ```sql ... ``` or ``` ... ```
        match = re.search(r"```(?:sql)?\s+(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned = match.group(1)
        else:
            cleaned = cleaned.replace("```", "")
            
    cleaned = cleaned.replace("`", "").strip()
    if cleaned.lower().startswith("sql"):
        cleaned = cleaned[3:].strip()
        
    # Remove any trailing semicolons or comments
    cleaned = re.sub(r";\s*$", "", cleaned)
    
    # Replace markdown table structures or other non-SQL wrappers
    return cleaned.strip()

def sql_rag_chain(question: str) -> str:
    """
    SQL RAG pipeline:
    1. Translate natural language question into SQLite query using LLM.
    2. Clean raw LLM output to extract only the SQL query.
    3. Run SQL query against the database and format natural language answer.
    """
    # Step 1: Translate to SQL
    schema_info = get_schema_info()
    translate_prompt = f"""You are a SQLite expert database administrator.
Given the schema and sample rows of our hospital database, write a valid SQLite SELECT query to answer the question.
Important constraints:
1. ONLY return the SQL statement. Do NOT include markdown code blocks, formatting, backticks, or explanation.
2. The query must be read-only (SELECT only).
3. Be precise with dates (YYYY-MM-DD) and text matching (case insensitive using LIKE if necessary).

Database Schema:
{schema_info}

User Question: {question}
SQLite Query:"""
    
    translate_response = llm.invoke(translate_prompt)
    raw_sql = translate_response.content
    
    # Step 2: Clean SQL
    sql_query = clean_sql_query(raw_sql)
    print(f"\n[SQL RAG] Generated SQL: {sql_query}")
    
    # Step 3: Execute and Answer
    try:
        db_result = execute_read_query(sql_query)
        print(f"[SQL RAG] Query execution result: {db_result}")
        
        answer_prompt = f"""You are a helpful MediAssist support analytics assistant.
Given the user's question, the generated SQL query, and the result from the database, provide a clear, concise, and natural language answer.
Be specific with numbers and facts from the data. If no rows were returned, state that clearly.

User Question: {question}
SQL Query: {sql_query}
Database Result: {db_result}

Natural Language Answer:"""
        
        answer_response = llm.invoke(answer_prompt)
        return answer_response.content.strip()
        
    except Exception as e:
        print(f"[SQL RAG] Error: {str(e)}")
        return f"I encountered an error executing the analytical query: {str(e)}. Please try rephrasing the question."

# 4. Hybrid RAG Chain with Reranking and RBAC Filters
def hybrid_rag_chain(question: str, role: str, target_collection: str = None) -> tuple[str, list[dict]]:
    """
    Hybrid RAG pipeline:
    1. Filter vectors based on access_roles and target collection in Qdrant.
    2. Retrieve top-10 broad candidates using Hybrid search (Dense + BM25).
    3. Rerank using CrossEncoder and select top-3.
    4. LLM answers using the selected context.
    """
    # 1. Setup metadata filter based on user's role and target collection
    must_conditions = [
        FieldCondition(
            key="metadata.access_roles",
            match=MatchValue(value=role)
        )
    ]
    if target_collection:
        must_conditions.append(
            FieldCondition(
                key="metadata.collection",
                match=MatchValue(value=target_collection)
            )
        )
        
    qdrant_filter = Filter(must=must_conditions)
    
    # 2. Retrieve broad candidate set (top-10)
    print(f"\n[Hybrid Search] Fetching top-10 candidates for question '{question}' with RBAC filter for role '{role}'...")
    vs = get_vectorstore()
    
    # Search with score to debug hybrid retrieval
    docs_with_scores = vs.similarity_search_with_score(
        query=question,
        k=10,
        filter=qdrant_filter
    )
    
    if not docs_with_scores:
        print("[Hybrid Search] 0 chunks retrieved.")
        return "I could not find any documents related to your query that you are authorized to access.", []
        
    print(f"[Hybrid Search] Retrieved {len(docs_with_scores)} candidates.")
    
    # 3. Rerank candidates using CrossEncoder
    cross_encoder = get_cross_encoder()
    
    # Prepare pairs for cross-encoder evaluation
    pairs = [(question, doc.page_content) for doc, _ in docs_with_scores]
    rerank_scores = cross_encoder.predict(pairs)
    
    # Attach scores to documents
    scored_docs = []
    for idx, (doc, _) in enumerate(docs_with_scores):
        scored_docs.append({
            "doc": doc,
            "rerank_score": float(rerank_scores[idx])
        })
        
    # Sort by cross-encoder score descending
    scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
    
    # Log scores (Tip Requirement: Log the reranker scores during development)
    print("\n[Reranker Scores]:")
    for idx, item in enumerate(scored_docs):
        doc = item["doc"]
        score = item["rerank_score"]
        source = doc.metadata.get("source_document", "unknown")
        section = doc.metadata.get("section_title", "General")
        safe_preview = doc.page_content[:80].encode("ascii", errors="replace").decode("ascii").replace("\n", " ")
        print(f"  Rank {idx+1}: Score = {score:.4f} | File: {source} -> {section} | Content preview: {safe_preview}...")
        
    # Select top-3 candidates
    top_docs = scored_docs[:3]
    print(f"\n[Reranker] Selected top-3 documents for LLM Generation.")
    
    # Format context for LLM
    context_blocks = []
    sources = []
    
    for item in top_docs:
        doc = item["doc"]
        context_blocks.append(doc.page_content)
        sources.append({
            "source_document": doc.metadata.get("source_document", "unknown"),
            "section_title": doc.metadata.get("section_title", "General"),
            "collection": doc.metadata.get("collection", "general")
        })
        
    context_text = "\n\n---\n\n".join(context_blocks)
    
    # 4. LLM Generation
    system_prompt = f"""You are MediBot, an advanced medical/clinical AI assistant for the MediAssist Health Network.
Your task is to answer the user's question by summarizing or extracting relevant information from the provided document context.

IMPORTANT: You are an internal database search assistant assisting hospital staff. You are NOT providing clinical advice to patients. You are simply retrieving and summarizing the contents of the internal hospital documents as requested. Do NOT refuse to answer on the grounds of medical advice, as the user is a credentialed medical professional accessing internal documents.

Instructions:
- Base your answer strictly on the facts directly mentioned in the context. Do not make up facts or use external medical or technical knowledge.
- Handling general vs. specific queries:
  1. If the user asks about guidelines, policies, reference ranges, or schedules for a specific department (such as the ICU), role, or specific procedure/task (such as calibration), but the context contains general guidelines, policies, reference ranges, or general maintenance/service/check schedules that cover that category, department, or device: you MUST summarize them. Treat them as the applicable guidelines/schedules for the requested department, role, or device.
  2. If the user asks a general question about guidelines, policies, reference ranges, or schedules, but the context only contains specific sections, examples, parameters, or sub-schedules of those guidelines (such as specific haematology ranges like D-dimer or ESR, or specific isolation protocols/signage): you MUST summarize these available details as the answer.
  3. In both cases, DO NOT start your response with "I cannot find the answer" or state that the information is missing. Directly present the available guidelines, policies, reference ranges, or schedules from the context as the answer.
- A context is considered related to the topic of the query if it covers the same general domain (for example, general Infection Control Guidelines are fully related to ICU infection control, and specific laboratory values/reference ranges are fully related to diagnostic reference guidelines). A context is unrelated only if it covers a completely different domain (for example, if the context is about leave policies but the question is about treatment protocols).
- If the context does not contain any information related to the topic of the query (i.e. it is from a completely unrelated domain), only then say "I cannot find the answer in the provided documents."
- Maintain a professional, factual, and clear tone.

Context:
{context_text}

Question: {question}
Answer:"""

    response = llm.invoke(system_prompt)
    return response.content.strip(), sources

# 5. Main Unified Chat Handler
def get_chat_response(question: str, role: str) -> dict:
    """
    Main entry point for /chat endpoint.
    Coordinates routing, RBAC checks, SQL RAG, and Hybrid RAG.
    """
    role = role.lower()
    
    # 1. Routing classification
    is_sql = is_analytical_question(question)
    
    if is_sql:
        print(f"[Router] Question routed to SQL RAG: '{question}'")
        # Check permissions for SQL RAG (only billing_executive and admin)
        if role not in ["billing_executive", "admin"]:
            # Route back to Hybrid RAG if SQL RAG is blocked (fallback or immediate block)
            # Actually, instruction says: "SQL RAG is only available to roles with analytical responsibilities: billing_executive and admin"
            # So if role is not permitted, we should return a refusal message.
            refusal_msg = "SQL RAG queries are only available to roles with analytical responsibilities: billing_executive and admin."
            return {
                "answer": f"Access Denied: {refusal_msg}",
                "sources": [],
                "retrieval_type": "sql_rag",
                "role": role
            }
            
        # Execute SQL RAG
        answer = sql_rag_chain(question)
        return {
            "answer": answer,
            "sources": [],
            "retrieval_type": "sql_rag",
            "role": role
        }
        
    else:
        print(f"[Router] Question routed to Hybrid RAG: '{question}'")
        # 2. RBAC Pre-Check (Which collection does this pertain to?)
        target_collection = get_target_collection_for_question(question)
        print(f"[RBAC Classifier] Question pertains to '{target_collection}' collection.")
        
        has_access, refusal_msg = check_rbac_access(role, target_collection)
        if not has_access:
            print(f"[RBAC Block] Blocked user '{role}' from querying collection '{target_collection}'")
            return {
                "answer": refusal_msg,
                "sources": [],
                "retrieval_type": "hybrid_rag",
                "role": role
            }
            
        # Execute Hybrid RAG
        answer, sources = hybrid_rag_chain(question, role, target_collection)
        return {
            "answer": answer,
            "sources": sources,
            "retrieval_type": "hybrid_rag",
            "role": role
        }

if __name__ == "__main__":
    # Test router
    print("Testing router...")
    q1 = "How many claims are pending?"
    print(f"Q: '{q1}' | Analytical? {is_analytical_question(q1)}")
    
    q2 = "What are the ICU nursing procedures for intubation?"
    print(f"Q: '{q2}' | Analytical? {is_analytical_question(q2)}")
