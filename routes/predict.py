from fastapi import APIRouter, HTTPException
try:
    from groq import Groq
except ImportError:
    Groq = None
import os
import json
from datetime import datetime
from typing import Optional, Any
from supabase.client import create_client, Client
from models.schemas import PredictionRequest, PredictionResponse, PredictedIntervention

router = APIRouter()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

supabase: Optional[Client] = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    if SUPABASE_URL else None
)

SYSTEM_PROMPT = """You are a clinical decision support assistant for staff nurses at Ormoc District Hospital (ODH),
a provincial hospital in Leyte, Philippines, assigned to the Operating Room and Delivery Room (OR/DR).

Your role: suggest nursing interventions based on patient presentation.
Follow Philippine DOH obstetric protocols and standards.
Flag interventions requiring physician authorization.
Consider resource constraints typical of provincial hospitals in the Philippines.

Rules:
1. Only suggest interventions within nursing scope of practice, or clearly mark physician orders
2. Patient safety is the highest priority
3. Confidence score = likelihood this intervention is needed (0-100)
4. Consider urgency of the situation in your confidence scoring
5. Never replace clinical judgment — frame as reminders, not orders
6. Respond ONLY in valid JSON — no markdown, no extra text, no explanation

Context: prototype system for academic evaluation (BSN-2 Nursing Informatics, VSU Faculty of Nursing)."""

_client: Optional[Any] = None

def get_client() -> Any:
    global _client
    if _client is None:
        if Groq is None:
            raise ValueError("groq package not installed")
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not configured")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def build_local_fallback_response(req: PredictionRequest, reason: str) -> PredictionResponse:
    flags = [f.lower() for f in (req.clinical_flags or [])]
    combined = " ".join(flags + [(req.chief_complaint or "").lower(), (req.historical_context or "").lower()])

    critical_terms = ["hemorrhage", "eclampsia", "seizure", "fetal distress", "cord prolapse"]
    high_terms = ["preeclampsia", "hypertension", "prolonged labor", "meconium", "fever"]

    if any(t in combined for t in critical_terms):
        risk_level = "critical"
    elif any(t in combined for t in high_terms):
        risk_level = "high"
    elif flags:
        risk_level = "moderate"
    else:
        risk_level = "low"

    interventions = [
        PredictedIntervention(
            action="Monitor maternal vital signs and fetal heart rate closely and trend findings.",
            confidence=78,
            category="monitoring",
            rationale="Frequent monitoring helps detect early deterioration.",
            requires_physician_order=False,
        ),
        PredictedIntervention(
            action="Reassess contractions, labor progress, and pain status at regular intervals.",
            confidence=74,
            category="procedure",
            rationale="Serial assessment supports timely recognition of abnormal labor patterns.",
            requires_physician_order=False,
        ),
        PredictedIntervention(
            action="Maintain IV access and prepare emergency maternal-fetal support equipment.",
            confidence=72,
            category="procedure",
            rationale="Readiness reduces delay if urgent intervention becomes necessary.",
            requires_physician_order=False,
        ),
        PredictedIntervention(
            action="Escalate to obstetric provider for non-reassuring signs or worsening status.",
            confidence=83,
            category="notification",
            rationale="Early provider notification shortens time to critical decisions.",
            requires_physician_order=True,
        ),
        PredictedIntervention(
            action="Update and communicate a clear bedside handoff plan with risk triggers.",
            confidence=70,
            category="other",
            rationale="Structured handoff improves continuity and safety during shifts.",
            requires_physician_order=False,
        ),
        PredictedIntervention(
            action="Document all assessments, interventions, and responses in real time.",
            confidence=76,
            category="monitoring",
            rationale="Timely documentation supports team coordination and legal safety.",
            requires_physician_order=False,
        ),
    ]

    return PredictionResponse(
        patient_id=req.patient_id,
        predicted_interventions=interventions,
        risk_level=risk_level,
        priority_note=(
            f"{risk_level.capitalize()} risk. Generated via local fallback because external model is unavailable. "
            f"Reason: {reason[:160]}"
        ),
        model_version="rules-fallback-v1",
        predicted_at=datetime.utcnow().isoformat(),
    )


def strip_to_json(text: str) -> str:
    """Strip markdown fences and any text outside the JSON object."""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return text.strip()


@router.post("/predict", response_model=PredictionResponse)
async def get_prediction(req: PredictionRequest):
    try:
        user_prompt = f"""Patient: {req.age or 'Unknown'} y/o, {req.gravida_para or 'Unknown'}, planning {req.mode_of_delivery} delivery.
Chief complaint: {req.chief_complaint or 'not stated'}.
Cervical dilation: {req.cervix_dilation or 'not recorded'}.
Contractions: {req.contraction_freq or 'not recorded'}.
Active clinical flags: {', '.join(req.clinical_flags) if req.clinical_flags else 'None'}.
{req.historical_context or ''}

Suggest the 6 most important nursing interventions for this patient.
Return ONLY this JSON (no markdown, no extra text):
{{
  "risk_level": "critical|high|moderate|low",
  "priority_note": "1-2 sentence clinical summary",
  "interventions": [
    {{
      "action": "specific actionable nursing intervention",
      "confidence": 85,
      "category": "medication|monitoring|procedure|transfer|notification|other",
      "rationale": "one sentence clinical rationale",
      "requires_physician_order": false
    }}
  ]
}}"""

        try:
            client = get_client()

            print("[Groq] Sending request to llama-3.3-70b-versatile...")

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )

            raw_text = completion.choices[0].message.content or ""
            print(f"[Groq] Raw response: {raw_text[:200]}...")

            cleaned = strip_to_json(raw_text)
            data = json.loads(cleaned)

            return PredictionResponse(
                patient_id=req.patient_id,
                predicted_interventions=data.get("interventions", []),
                risk_level=data.get("risk_level", "low"),
                priority_note=data.get("priority_note", ""),
                model_version="llama-3.3-70b-versatile",
                predicted_at=datetime.utcnow().isoformat()
            )
        except Exception as model_error:
            print(f"[Predict] Using local fallback: {model_error}")
            return build_local_fallback_response(req, str(model_error))
    except Exception as e:
        print(f"[Groq] PREDICT ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "QMeR+ AI (Groq / Llama 3.3)",
        "version": "1.0.0"
    }