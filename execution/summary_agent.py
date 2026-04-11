import ollama
import json

def generate_doctor_summary(user_data: dict, timeline: list, medications: list) -> str:
    """
    Generates a fast 1-page clinical summary optimized for a doctor's consultation.
    Takes user profile info, recent timeline events, and active medications.
    """
    
    prompt = f"""
    You are a medical AI assistant. You need to prepare a "1-Page Patient Summary" to be read by a doctor who is walking into the consultation room.
    The doctor has exactly 30 seconds to catch up on the patient's history.
    
    Patient Info:
    {json.dumps(user_data, indent=2)}
    
    Active Medications:
    {json.dumps(medications, indent=2)}
    
    Recent Timeline History (Interventions, Diagnoses, Reports):
    {json.dumps(timeline[:10], indent=2)}
    
    Structure your markdown response:

    * **Age/Gender**: [Infer if possible, else N/A]
    * **Blood Group**: {user_data.get('blood_group', 'Unknown')}
    * **Allergies**: {user_data.get('allergies', 'None recorded')}
    

    [Summarize the last 3-4 timeline events into clinical context. What brought them here recently?]
    

    [List as punchy bullets]
    

    [List based on the history if deduced, or user_data chronic_conditions]
    
    Keep it strictly professional and clinical. No conversational filler.
    """
    
    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=[{'role': 'user', 'content': prompt}],
            options={"temperature": 0.1}
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"Summary Generation Failed: {e}")
        return "⚠️ Error: Unable to generate summary. Please check the model connection."
