import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add current folder to path
sys.path.append(str(Path(__file__).resolve().parent))

# Reconfigure stdout to use UTF-8 to prevent charmap crashes on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load dotenv
load_dotenv()

from backend.rag import get_chat_response

def test_query(question: str, role: str):
    print("=" * 80)
    print(f"Role: {role.upper()}")
    print(f"Question: '{question}'")
    print("-" * 80)
    
    try:
        response = get_chat_response(question, role)
        print(f"Retrieval Type: {response['retrieval_type'].upper()}")
        print(f"Answer: {response['answer']}")
        if response["sources"]:
            print("Sources:")
            for src in response["sources"]:
                print(f"  - Document: {src['source_document']} | Section: {src['section_title']} | Collection: {src['collection']}")
        else:
            print("Sources: None")
    except Exception as e:
        print(f"Error executing test query: {str(e)}")
    print("=" * 80 + "\n")

def run_tests():
    print("Starting MediBot RAG & RBAC Verification Tests...")
    
    # Check if Qdrant db exists
    qdrant_path = os.getenv("QDRANT_PATH", "mediassist_data/qdrant_db")
    if not os.path.exists(qdrant_path):
        print(f"Error: Vector store directory {qdrant_path} does not exist. Please run ingestion first!")
        return
        
    # Test 1: General Access (All roles can access 'general')
    test_query(
        question="What is the hospital staff leave policy?",
        role="nurse"
    )
    
    # Test 2: Authorized Clinical Access (Doctor can access 'clinical')
    test_query(
        question="What are the standard treatment protocols for diabetes?",
        role="doctor"
    )
    
    # Test 3: Blocked Clinical Access (Nurse cannot access 'clinical')
    test_query(
        question="What are the standard treatment protocols for diabetes?",
        role="nurse"
    )
    
    # Test 4: Blocked Billing Access (Nurse cannot access 'billing')
    test_query(
        question="Show me the insurance billing code reference sheet.",
        role="nurse"
    )
    
    # Test 5: Authorized Equipment Access (Technician can access 'equipment')
    test_query(
        question="What is the calibration schedule for infusion pumps?",
        role="technician"
    )
    
    # Test 6: Authorized SQL RAG Access (Billing Executive queries claims)
    test_query(
        question="How many pending billing claims do we have?",
        role="billing_executive"
    )
    
    # Test 7: Authorized SQL RAG Access (Admin queries tickets)
    test_query(
        question="How many maintenance tickets are currently in progress?",
        role="admin"
    )
    
    # Test 8: Blocked SQL RAG Access (Doctor tries to query claims count)
    test_query(
        question="How many claims are pending?",
        role="doctor"
    )

if __name__ == "__main__":
    run_tests()
