import ollama
import json

def compute_health_score(unverified_count: int, conditions: list[str], lab_results: list[dict], meds_count: int) -> dict:
    """
    Computes a Health Score (0-100) based on medical data using AI predictions.
    """
    prompt = f"""
    You are an expert AI medical underwriter and health risk analyst. 
    Analyze the following patient data context and compute a dynamic health score out of 100.
    
    Data:
    - Unverified Medical Records: {unverified_count}
    - Chronic Conditions: {conditions}
    - Lab Results: {json.dumps(lab_results[:10])}
    - Active Medications Count: {meds_count}
    
    Start with a baseline of 100 and rationally deduct points for severity, interactions, and abnormal labs.
    If conditions are benign or labs are normal, do not heavily penalize. 
    Be highly accurate. Output STRICTLY JSON without markdown formatting.
    
    Schema:
    {{
      "health_score": 85,
      "risk_level": "Low", // or "Medium", "High"
      "factors": ["Details about deduction or bonus", "Another factor..."]
    }}
    """
    
    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=[{'role': 'user', 'content': prompt}],
            options={"temperature": 0.1}
        )
        
        raw_text = response['message']['content'].strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        result = json.loads(raw_text.strip())
        return {
            "health_score": int(result.get("health_score", 100)),
            "risk_level": result.get("risk_level", "Medium"),
            "factors": result.get("factors", [])
        }
    except Exception as e:
        print(f"Health score prediction failed: {e}")

        score = 80
        if unverified_count > 0: score -= 10
        if meds_count > 3: score -= 10
        return {
            "health_score": score,
            "risk_level": "Medium",
            "factors": ["AI generation timeout - applying baseline estimator.", f"{unverified_count} unverified records", f"{meds_count} meds"]
        }
