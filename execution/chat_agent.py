import ollama
import json

def ask_health_assistant(user_data: dict, timeline: list, medications: list, question: str, history: list = None) -> str:
    """
    RAG-style chat with persistent memory. Formats patient data + conversation
    history into context so the AI can answer with continuity.
    """
    lean_timeline = [
        {"date": t.get("event_date"), "event": t.get("title"), "details": t.get("description")}
        for t in timeline
    ]
    active_meds = [m['med_name'] for m in medications if not m.get('is_cured')]
    cured_meds  = [m['med_name'] for m in medications if m.get('is_cured')]

    system_prompt = f"""You are MediRecord AI, an intelligent health assistant analyzing a patient's personal health vault.
Answer the user's question using ONLY the provided patient context and conversation history. 
If the answer is not in the context, say "I cannot find this information in your uploaded records."
Do NOT give medical diagnoses or prescribe treatments. Be concise, warm and clinical.

PATIENT CONTEXT:
Name: {user_data.get('name', 'Unknown')}
DOB: {user_data.get('date_of_birth', 'N/A')}
Blood Group: {user_data.get('blood_group', 'N/A')}
Allergies: {user_data.get('allergies', 'None recorded')}
Chronic Conditions: {user_data.get('chronic_conditions', 'None recorded')}
Active Medications: {json.dumps(active_meds)}
Cured/Past Medications: {json.dumps(cured_meds)}
Medical Timeline (most recent events):
{json.dumps(lean_timeline[-10:], indent=2)}"""

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=messages,
            options={"temperature": 0.2}
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"Chat failed: {e}")
        return "⚠️ Health AI is temporarily unavailable. Please check your Ollama connection."
