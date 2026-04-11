import ollama
import json
import base64
import io
from PIL import Image

def _image_to_base64(img: Image.Image) -> str:
    buffered = io.BytesIO()

    if img.mode == 'RGBA':
        img = img.convert('RGB')
    img.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def extract_structured_data(images: list[Image.Image], text_content: str = "") -> dict:
    """
    Takes a list of PIL Images (and optional raw text), passes them to the Qwen3-VL model via Ollama,
    and returns a structured JSON dictionary containing extracted medical data.
    """
    b64_images = [_image_to_base64(img) for img in images]
    
    prompt = f"""
    You are an expert medical data extraction AI. You do not diagnose or alter medical data. You transcribe exactly what you see.
    Analyze the provided document imaging (prescription, lab report, X-Ray, notes) and return a strict JSON object with this exact structure:
    
    {{
      "document_type": "[Prescription, Lab Report, Discharge Summary, Visit Note, Radiology Report, or Unknown]",
      "patient_info": {{"name": "", "age": "", "gender": ""}},
      "doctor_name": "",
      "hospital": "",
      "date": "YYYY-MM-DD",
      "diagnosis": "",
      "source_page": 0,
      "medications": [
        {{"med_name": "", "dosage": "", "frequency": "", "duration": "", "source_page": 0}}
      ],
      "key_measurements": [
        {{"test_name": "", "value": "", "unit": "", "abnormal_flag": false, "source_page": 0}}
      ],
      "tabular_data": [
        {{"table_name": "", "columns": ["col1", "col2"], "rows": [["val1", "val2"]]}}
      ],
      "conclusions": "Any overall conclusions drawn by the doctor/report.",
      "radiology_findings": "Any findings from X-Rays, MRIs, or scans.",
      "confidence_score": 0.95,
      "low_confidence_text": []
    }}
    
    CRITICAL: For every medication, measurement, and table, you must specify the 'source_page' index (0, 1, 2...) from the list of images.
    If a medication's frequency or dosage is illegible, corrupted (e.g. OCR artifacts), or makes no sense, set it as "Not Specified".
    If multiple pieces of information belong to different reports within one file, treat them as separate entries in your mind but return one JSON.
    Return ONLY valid JSON.
    
    TEXT CONTENT (if any):
    {text_content}
    """
    

    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=[
                {
                    'role': 'user',
                    'content': prompt,
                    'images': b64_images
                }
            ],
            options={"temperature": 0.1}
        )
        
        raw_text = response['message']['content'].strip()
        

        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        data = json.loads(raw_text.strip())
        return data
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from model: {raw_text}")
        raise RuntimeError("Model returned invalid JSON format")
    except Exception as e:
        raise RuntimeError(f"Ollama API Error: {e}")
