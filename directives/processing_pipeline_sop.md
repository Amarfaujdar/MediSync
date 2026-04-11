# Processing Pipeline SOP

## Purpose
This directive governs the handling of uploaded medical documents (PDFs, JPEGs, PNGs) from the moment they are dragged into the Streamlit vault until they are structured and committed to the database.

## Inputs
1. The uploaded file path.
2. The user ID.

## Expected Workflow (Orchestration)
1. **File Normalization (`ocr_agent.py`)**: 
   - If the file is a PDF, it must be converted into a list of images (JPEG) using `pdf2image`.
   - If it's an image, proceed directly.
2. **Vision Extraction (`extraction_agent.py`)**: 
   - Use the multimodal capability of the `qwen3-vl:235b-cloud` model via the Ollama client.
   - Instruct the model to extract the structured JSON.
   - Importantly, **Safety Rule**: If the AI is not absolutely confident, it MUST leave the field empty or add it to `low_confidence_text`. It must NOT invent data.
3. **Database Commitment (`database.py`)**:
   - Update the Document status to `Completed` with the extracted JSON.
   - Set the `is_verified` flag to `0` / `False` by default for all extracted records.
4. **User Verification (UI Layer)**:
   - Present the extracted fields to the user.
   - Highlight missing or low-confidence data explicitly. Ensure missing data says "Missing" and low-confidence says "Verify".
   - Allow the user to inline edit and save the payload back to the DB, turning the `is_verified` flag to `True`.

## Safety Rules
- The LLM prompt MUST forbid diagnosing the patient.
- The LLM MUST simply transcribe what it sees.
- If it cannot read the handwriting, it should add the snippet to `low_confidence_text` or omit it. Do not attempt to guess highly toxic/dangerous drug names if illegible.
