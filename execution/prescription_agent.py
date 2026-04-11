import ollama

def explain_medications(medications: list[dict]) -> dict:
    """
    Takes a list of medication dicts and uses Ollama to generate an explanation
    for each one (purpose, precautions, side effects) suited for a patient.
    """
    if not medications:
        return {}
        

    prompt = f"""
    You are a medical assistant explaining drug information to a patient. 
    Review the following list of medications: {medications}
    
    For each medication, return a JSON object keyed by the medication name. 
    Each value MUST be a dictionary containing:
    1. "purpose": Simple explanation of what it does
    2. "usage": How generally it is taken (if given in input, repeat it. if not, keep generic)
    3. "precautions": Any major warnings
    4. "side_effects": Common side effects
    
    CRITICAL RULES:
    - Never alter the dosage.
    - Keep language simple (8th grade reading level).
    - If you include a disclaimer, put it inside a key named "DISCLAIMER_NOTICE" with a value that is ALSO a dictionary following the same keys (purpose, usage, etc) or simply omit it from the JSON if you can't fit it in that structure.
    - Return strictly valid JSON mapped by drug name.
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
            
        import json
        return json.loads(raw_text.strip())
        
    except Exception as e:
        print(f"Explanation failed: {e}")
        return {"error": "Could not generate explanations at this time."}
