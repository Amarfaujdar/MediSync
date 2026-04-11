import ollama
import json

def generate_doctor_summary(user_data: dict, timeline: list, medications: list) -> str:
    """
    Generates a fast 1-page clinical summary optimized for a doctor's consultation.
    Takes user profile info, recent timeline events, and active medications.
    """
    
    prompt = f"""
    You are a medical AI assistant. Prepare a concise 1-page patient summary for a doctor with 30 seconds to review.

    Patient Info:
    {json.dumps(user_data, indent=2)}

    Active Medications:
    {json.dumps(medications, indent=2)}

    Recent Timeline History (Interventions, Diagnoses, Reports):
    {json.dumps(timeline[:10], indent=2)}

    STRICT FORMATTING RULES — follow exactly:
    - Do NOT use any markdown. No asterisks, no hashes, no underscores, no backticks, no bullet dashes.
    - Do NOT use emoji or special symbols.
    - Write in plain English sentences and short paragraphs only.
    - Use these plain-text section labels followed by a colon and a newline:
        PATIENT OVERVIEW
        RECENT CLINICAL HISTORY
        ACTIVE MEDICATIONS
        KNOWN CONDITIONS
        ALLERGIES
    - Keep it strictly professional and clinical. No conversational filler.

    Age and Gender: infer from date of birth if available, else write N/A.
    Blood Group: {user_data.get('blood_group', 'Unknown')}
    Allergies: {user_data.get('allergies', 'None recorded')}
    """
    
    try:
        response = ollama.chat(
            model='qwen3-vl:235b-cloud',
            messages=[{'role': 'user', 'content': prompt}],
            options={"temperature": 0.1}
        )
        raw = response['message']['content'].strip()
        # Strip any residual markdown symbols the model may have emitted
        import re
        raw = re.sub(r'[*_`~]{1,3}', '', raw)          # bold/italic/code markers
        raw = re.sub(r'^#{1,6}\s*', '', raw, flags=re.MULTILINE)  # headings
        raw = re.sub(r'^[-•>]\s+', '', raw, flags=re.MULTILINE)   # bullet/blockquote
        raw = re.sub(r'\n{3,}', '\n\n', raw)            # collapse excess blank lines
        return raw.strip()
    except Exception as e:
        print(f"Summary Generation Failed: {e}")
        return "⚠️ Error: Unable to generate summary. Please check the model connection."
