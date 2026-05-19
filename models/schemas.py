from pydantic import BaseModel
from typing import List, Optional

class PredictionRequest(BaseModel):
    patient_id: str
    clinical_flags: Optional[List[str]] = []
    chief_complaint: Optional[str] = None
    cervix_dilation: Optional[str] = None
    contraction_freq: Optional[str] = None
    mode_of_delivery: Optional[str] = "NSVD"
    gravida_para: Optional[str] = None
    age: Optional[str] = None
    historical_context: Optional[str] = None

class PredictedIntervention(BaseModel):
    action: str
    confidence: int
    category: str
    rationale: str
    requires_physician_order: bool

class PredictionResponse(BaseModel):
    patient_id: str
    predicted_interventions: List[PredictedIntervention]
    risk_level: str
    priority_note: str
    model_version: str
    predicted_at: str

class PushBroadcastRequest(BaseModel):
    title: str
    body: str
    url: str
    urgency: str = 'normal'
    tag: str = 'qmer-notification'
