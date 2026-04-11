import uuid
from typing import Dict, Any, Tuple
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from blockchain.utils.crypto_utils import generate_document_hash, mock_upload_to_ipfs, mock_encrypt_document
from execution.database import insert_blockchain_record, get_document_hash

def register_document_on_blockchain(doc_id: str, patient_id: str, filepath: str) -> Dict[str, Any]:
    """
    Encrypts document, generates SHA-256 hash, stores on IPFS, and records the
    metadata onto the Blockchain Security Layer (database).
    """
    try:
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        return {"success": False, "error": str(e)}

    # 1. Generate SHA-256 hash of raw document
    doc_hash = generate_document_hash(file_bytes)
    
    # 2. Encrypt document for off-chain storage
    encrypted_bytes = mock_encrypt_document(file_bytes)
    
    # 3. Store in off-chain / IPFS
    filename = os.path.basename(filepath)
    ipfs_uri = mock_upload_to_ipfs(encrypted_bytes, filename)
    
    # 4. Store Hash and details onto Blockchain (Smart Contract mock)
    # The pseudo transaction ID simulates a blockchain tx hash
    mock_tx_id = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}"
    
    # Update relational DB with blockchain metadata
    record_id = insert_blockchain_record(
        doc_id=doc_id,
        patient_id=patient_id,
        document_hash=doc_hash,
        transaction_id=mock_tx_id,
        ipfs_uri=ipfs_uri
    )
    
    return {
        "success": True,
        "record_id": record_id,
        "document_hash": doc_hash,
        "transaction_id": mock_tx_id,
        "ipfs_uri": ipfs_uri
    }

def verify_document_integrity(doc_id: str, filepath: str) -> Tuple[bool, str]:
    """
    Verifies that the uploaded document matches the immutable hash stored on the blockchain.
    """
    blockchain_hash = get_document_hash(doc_id)
    if not blockchain_hash:
        return False, "No blockchain record found for this document"
        
    try:
        with open(filepath, 'rb') as f:
            current_bytes = f.read()
    except Exception as e:
        return False, f"Could not read local file: {e}"
        
    current_hash = generate_document_hash(current_bytes)
    is_valid = (current_hash == blockchain_hash)
    
    message = "Integrity Verified: Match" if is_valid else "TAMPER ALERT: Hash Mismatch!"
    return is_valid, message
