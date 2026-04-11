from execution.database import get_timeline

def build_user_timeline(user_id: str) -> dict:
    """
    Fetches raw timeline events and groups them by Year -> Month for UI rendering.
    """
    raw_events = get_timeline(user_id)
    organized_timeline = {}
    
    for event in raw_events:

        date_str = event.get('event_date', '')
        if not date_str or len(date_str) < 4:
            year = "Unknown Time"
            month = "Unknown"
        else:
            year = date_str[:4]

            if len(date_str) >= 7:
                month = date_str[5:7]
            else:
                month = "01"
                
        if year not in organized_timeline:
            organized_timeline[year] = []
            
        organized_timeline[year].append(event)
        
    return organized_timeline
