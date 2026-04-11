# Unified Personal Health Record & Medical Intelligence Platform

## Core Architecture

This platform provides a comprehensive, multi-layer architecture for ingestion, extraction, and secure sharing of medical records.

### 1. Ingestion & Transformation Layer (OCR)
- **Document Upload**: Users upload medical documents (prescriptions, lab results, discharge summaries).
- **OCR Pipeline**: Utilizing PyTesseract and PDF-to-Image capabilities, raw medical documents are converted to textual data.

### 2. Medical Intelligence Layer (Agents)
The platform is powered by an orchestrator pattern using deterministic Python agents directed by human-readable `.md` prompts:
- **Extraction Agent**: Transforms raw OCR text into structured JSON (doctor info, hospital, diagnoses, medications, lab readings).
- **Patient Memory Agent / Timeline**: Maps the extracted data chronologically into the patient's medical history timeline, linking back to the original source document.
- **Health Risk Agent**: Calculates holistic health scores based on conditions, medications, and labs.
- **Prescription Agent**: Analyzes prescription patterns and provides human-readable context on medical regimens.

### 3. Blockchain Security Layer
A hybrid decentralized approach for protecting medical records without storing PII on the public ledger.
- **Document Storage**: Documents are encrypted using AES-256 and stored securely (Off-chain / IPFS).
- **Hash Generation**: A SHA-256 hash is computed for the raw document to ensure uniqueness and tamper-detection.
- **Blockchain Metadata**: The patient ID, Document Hash, Timestamp, and ownership credentials are mathematically anchored onto a blockchain (e.g. Polygon).
- **Access Control & Audit**: Smart contracts enforce role-based access. Access grants (to doctors) and file read operations are immutably logged into an Audit Trail.

### 4. Interactive UX & Secure Sharing
- **Dynamic Body Map**: Visually graphs conditions to physiological regions.
- **Secure Sharing Portal**: Patients generate time-limited, cryptographically verifiable access links. Doctors can view a read-only perspective that derives all evidence cleanly from the immutable database.

## System Workflow Pipeline
`Patient Upload` → `OCR Extraction` → `Patient Memory / Timeline Update` → **`Encrypt Document`** → **`Generate Hash`** → **`Store Hash on Blockchain`** → `Grant Access` → `Doctor Verification`

## Project Structure
- `.data/`: SQLite embedded database.
- `execution/`: Multi-Agent python logic (`ocr_agent`, `extraction_agent`, etc.) and database interface.
- `blockchain/`: Contracts, crypto utilities, and blockchain bridging logic.
- `frontend/`: Standard static vanilla frontend utilizing API endpoints.
- `main.py`: FastAPI implementation serving API routes and orchestrator functions.
