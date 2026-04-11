import ollama
import json

def generate_health_predictions(user_data: dict, tl_events: list, meds: list, labs: list) -> list:
    """
    Generates dynamic AI health predictions and alerts based on patient data state.
    """
    
    prompt = f"""
    You are an expert AI clinical risk analyzer. Based on the patient's data, generate 3-5 dynamic health predictions, warnings, or reminders.
    
    Patient Info: {json.dumps(user_data)}
    Active Medications: {json.dumps(meds)}
    Lab Results: {json.dumps(labs[:10])}
    Timeline Events: {json.dumps(tl_events[:10])}
    
    Evaluate potential drug interactions, abnormal lab trends, overdue checkups based on their condition, or risk of missing timeline verifications.
    
    Return STRICTLY valid JSON ONLY in this format:
    [
      {{
        "level": "high",  // Can be "critical", "high", "medium", or "low"
        "type": "risk",   // General category string (e.g. "risk", "conflict", "reminder", "insight")
        "badge": "High Risk",
        "typeLabel": "RISK",
        "iconType": "alert", // "alert", "trend", "bell", "info"
        "title": "Elevated Cardiovascular Risk",
        "body": "Detailed explanation..."
      }}
    ]
    
    Ensure no markdown formatting wrapping the JSON (no ```json ... ```). Just the raw JSON array.
    """
    
    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=[{'role': 'user', 'content': prompt}],
            options={"temperature": 0.2}
        )
        
        raw_text = response['message']['content'].strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        predictions = json.loads(raw_text.strip())
        if isinstance(predictions, list):
            return predictions
        return []
    except Exception as e:
        print(f"Prediction logic failed: {e}. Falling back to default heuristics.")

        unverified = [e for e in tl_events if not e.get('is_verified')]
        preds = []
        if unverified:
            preds.append({
                "level": "high", "type": "risk", "badge": "High Risk", "typeLabel": "RISK",
                "iconType": "alert", "title": "Unverified Records", 
                "body": f"You have {len(unverified)} unverified record(s). Please verify records in the Timeline."
            })
        if len(meds) > 3:
            preds.append({
                "level": "medium", "type": "conflict", "badge": "Medium", "typeLabel": "CONFLICT",
                "iconType": "trend", "title": "Potential Drug Interaction", 
                "body": f"Taking {len(meds)} medications. Physician review recommended."
            })
        if not preds:
            preds.append({
                "level": "low", "type": "reminder", "badge": "Low Priority", "typeLabel": "REMINDER",
                "iconType": "bell", "title": "Annual Health Checkup Due", 
                "body": "Schedule your annual preventive health screening."
            })
        return preds
