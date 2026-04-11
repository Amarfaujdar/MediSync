import hashlib
import os

def generate_document_hash(file_bytes: bytes) -> str:
    """Generate SHA-256 hash for document verification."""
    return hashlib.sha256(file_bytes).hexdigest()

def mock_encrypt_document(file_bytes: bytes) -> bytes:
    """
    Mock AES-256 encryption.
    In a production system, this would use the cryptography library.
    """
    # Simply prefixing for mock demonstration
    return b"ENCRYPTED_AES256_" + file_bytes

def mock_upload_to_ipfs(file_bytes: bytes, filename: str) -> str:
    """
    Mock upload to IPFS. Returns a pseudo-CID.
    """
    mock_cid = "Qm" + hashlib.sha256(file_bytes[0:100]).hexdigest()[:44]
    return f"ipfs://{mock_cid}/{filename}"
