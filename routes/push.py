from fastapi import APIRouter
from pywebpush import webpush, WebPushException
import json
import os
from supabase import create_client, Client
from models.schemas import PushBroadcastRequest

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:test@example.com")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL else None

@router.post("/push/broadcast")
async def broadcast_push(request: PushBroadcastRequest):
    if not supabase: 
        return {"error": "Supabase not configured"}
    
    res = supabase.table("push_subscriptions").select("*").execute()
    sent = 0
    failed = 0
    
    for row in res.data:
        try:
            webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": { "p256dh": row["p256dh"], "auth": row["auth_key"] }
                },
                data=json.dumps({
                    "title": request.title, 
                    "body": request.body, 
                    "url": request.url,
                    "urgency": request.urgency, 
                    "tag": request.tag
                }),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_EMAIL}
            )
            sent += 1
        except WebPushException as ex:
            if ex.response and ex.response.status_code == 410:
                supabase.table("push_subscriptions").delete().eq("endpoint", row["endpoint"]).execute()
            failed += 1
        except Exception as e:
            failed += 1
            
    return {"sent": sent, "failed": failed}

@router.get("/push/health")
async def push_health():
    return {"status": "ok", "service": "QMeR+ Push"}
