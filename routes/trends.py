from fastapi import APIRouter
import os
from supabase import create_client, Client
from datetime import datetime, timedelta

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL else None

@router.get("/trends")
async def get_trends():
    if not supabase:
        # Return safe defaults for local/dev use when Supabase isn't available
        return {
            "interventions": [],
            "avgDelay": 0,
            "totalInterventions": 0,
            "alertFatigue": 0,
            "timestampAccuracy": None,
        }
    
    # Query interventions for the last 30 days. Be resilient to missing columns
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    interventions = []
    try:
        res = supabase.table("interventions").select("*").gte("documented_at", thirty_days_ago).execute()
        interventions = res.data or []
    except Exception:
        interventions = []

    # Fallback: if no rows found with the date filter, fetch recent rows and filter locally
    if not interventions:
        try:
            recent = supabase.table("interventions").select("*").order("id", {"ascending": False}).limit(1000).execute()
            recent_rows = recent.data or []
            # Accept any of these timestamp fields defined in the Intervention type
            def valid_recent(r):
                for key in ("documented_at", "created_at", "actual_time"):
                    val = r.get(key)
                    if val:
                        try:
                            # Normalize and compare
                            ts = datetime.fromisoformat(val.replace('Z', '+00:00'))
                            if ts >= datetime.fromisoformat(thirty_days_ago):
                                return True
                        except Exception:
                            continue
                return False

            interventions = [r for r in recent_rows if valid_recent(r)]
        except Exception:
            interventions = []
    
    counts = {}
    categories = {}
    total_delay = 0
    delay_count = 0
    total_interventions = 0
    
    for i in interventions:
        action = i.get("action")
        category = i.get("category", "other")
        if action:
            counts[action] = counts.get(action, 0) + 1
            total_interventions += 1
            categories[action] = category
            
        if i.get("is_delayed") and i.get("actual_time"):
            doc_at_str = i.get("documented_at")
            act_at_str = i.get("actual_time")
            if doc_at_str and act_at_str:
                try:
                    doc_at = datetime.fromisoformat(doc_at_str.replace('Z', '+00:00'))
                    act_at = datetime.fromisoformat(act_at_str.replace('Z', '+00:00'))
                    diff = (doc_at - act_at).total_seconds() / 60
                    if diff > 0:
                        total_delay += diff
                        delay_count += 1
                except ValueError:
                    pass
                
    top_actions = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]

    avg_delay = (total_delay / delay_count) if delay_count > 0 else 0

    # previous 30-day period for simple alert-fatigue comparison
    start_prev = (datetime.utcnow() - timedelta(days=60)).isoformat()
    end_prev = (datetime.utcnow() - timedelta(days=30)).isoformat()
    prev_res = supabase.table("interventions").select("*").gte("documented_at", start_prev).lt("documented_at", end_prev).execute()
    prev_interventions = prev_res.data or []
    prev_total = len(prev_interventions)

    alert_fatigue_change = 0
    if prev_total > 0:
        alert_fatigue_change = round(((prev_total - total_interventions) / prev_total) * 100, 1)

    timestamp_accuracy = None
    if total_interventions > 0:
        # approximate: proportion of non-delayed documented interventions
        non_delayed = total_interventions - delay_count
        timestamp_accuracy = round((non_delayed / total_interventions) * 100, 1)

    return {
        "interventions": [{"action": k, "count": v, "category": categories[k]} for k, v in top_actions],
        "avgDelay": round(avg_delay, 1),
        "totalInterventions": total_interventions,
        "alertFatigue": alert_fatigue_change,
        "timestampAccuracy": timestamp_accuracy
    }
