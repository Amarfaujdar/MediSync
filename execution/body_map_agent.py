
import json

def build_body_map(structured_data: dict, raw_text: str = "") -> dict:
    """
    Returns mapped conditions and symptoms per body region
    """
    regions = {
        "head": {"conditions": [], "symptoms": []},
        "chest_lungs": {"conditions": [], "symptoms": []},
        "abdomen": {"conditions": [], "symptoms": []},
        "arms": {"conditions": [], "symptoms": []},
        "legs": {"conditions": [], "symptoms": []}
    }
    

    rules = {
        "head": ["headache", "migraine", "sinusitis", "meningitis", "brain", "head", "concussion", "stroke", "tumor"],
        "chest_lungs": ["asthma", "pneumonia", "chest pain", "cough", "breathing", "heart", "lung", "cardio", "pulmonary", "bronchitis", "dyspnea", "lvh", "hypertension", "blood pressure"],
        "abdomen": ["stomach", "liver", "gastric", "digestion", "abdomen", "kidney", "intestinal", "bowel", "ulcer", "appendicitis", "nausea", "diarrhea", "diabetes"],
        "arms": ["arm ", "shoulder", "elbow", "wrist", "hand", "finger", "arm fracture", "arm pain", "arm swelling"],
        "legs": ["leg", "knee", "thigh", "calf", "ankle", "foot", "toe", "joint", "mobility", "leg fracture", "leg pain", "leg swelling", "arthritis"]
    }
    

    generic_symptoms = ["pain", "swelling", "fracture", "numbness", "tingling"]

    diagnosis = structured_data.get("diagnosis", "")
    

    symptoms_list = structured_data.get("symptoms", [])
    if isinstance(symptoms_list, str):
        symptoms_list = [s.strip() for s in symptoms_list.split(',')]
        
    extracted_conditions = [diagnosis] if diagnosis else []
    

    text_to_scan = f"{diagnosis} {' '.join(symptoms_list)} {raw_text}".lower()
    

    for condition in extracted_conditions:
        cond_lower = condition.lower()
        matched = False
        for region, keywords in rules.items():
            if any(kw in cond_lower for kw in keywords):
                if condition not in regions[region]["conditions"]:
                    regions[region]["conditions"].append(condition)
                matched = True
        

        if not matched:
            for region, keywords in rules.items():
                if any(kw in text_to_scan for kw in keywords):
                    if condition not in regions[region]["conditions"]:
                        regions[region]["conditions"].append(condition)

    all_symptoms_to_check = set(symptoms_list)
    for kw in ["headache", "migraine", "cough", "chest pain", "stomach pain", "nausea", "fever", "breathing issues", "joint pain"]:
        if kw in text_to_scan:
            all_symptoms_to_check.add(kw.capitalize())

    for symptom in all_symptoms_to_check:
        sym_lower = symptom.lower()
        matched = False
        for region, keywords in rules.items():
            if any(kw in sym_lower for kw in keywords):
                if symptom not in regions[region]["symptoms"]:
                    regions[region]["symptoms"].append(symptom.capitalize())
                matched = True
        

        if not matched:
            for region, keywords in rules.items():
                if any(kw in text_to_scan for kw in keywords):

                    if symptom not in regions[region]["symptoms"]:
                        regions[region]["symptoms"].append(symptom.capitalize())

    return regions
