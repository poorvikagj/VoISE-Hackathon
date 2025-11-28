# backend/server.py
import os
import json
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

# Groq async client
from groq import AsyncGroq

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ.get("MONGO_URL")
if not mongo_url:
    raise RuntimeError("MONGO_URL not set in .env")
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get("DB_NAME", "test_db")]

# Groq client (async)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env")
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# FastAPI app and router
app = FastAPI()
api_router = APIRouter(prefix="/api")

# System prompt (kept from your original)
CLINICAL_SYSTEM_PROMPT = """You are ClinicalNoteGPT, a medical AI that converts doctor–patient conversations and non-verbal observations into structured clinical documentation.

Input to you will include:
1. Transcript of the doctor–patient conversation.
2. Non-verbal patient actions (gestures, movements, expressions, behaviors).

Interpret both verbal and non-verbal cues.

Examples of non-verbal cues:
- Clutching chest → chest pain
- Limping → leg/knee/ankle pain
- Holding abdomen → abdominal pain
- Pointing to throat → sore throat or swallowing difficulty
- Shallow breathing → respiratory distress
- Dizziness or imbalance → neurological concern

Use symptoms, context, and actions to generate clinical insights.

Rules:
- Do NOT hallucinate.
- If unsure, write "Not enough information."
- All output must follow the JSON schema.
- Non-verbal cues should appear in Objective and Assessment.
- Detect red-flag symptoms (e.g., chest pain, shortness of breath, collapse).
- Generate ICD-10 codes with highest specificity.
- Flag possible drug interactions.

You MUST respond with ONLY valid JSON in this exact format:
{
  "subjective": "",
  "objective": "",
  "assessment": "",
  "plan": "",
  "icd10_codes": [
    {"condition": "", "code": ""}
  ],
  "medication_interactions": [
    {"drug_a": "", "drug_b": "", "severity": "", "note": ""}
  ],
  "red_flags": [],
  "non_verbal_signs": [],
  "clinical_summary": ""
}"""

# Pydantic models
class ICD10Code(BaseModel):
    condition: str
    code: str

class MedicationInteraction(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    note: str

class ClinicalOutput(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    icd10_codes: List[ICD10Code]
    medication_interactions: List[MedicationInteraction]
    red_flags: List[str]
    non_verbal_signs: List[str]
    clinical_summary: str

class TranscriptionRequest(BaseModel):
    transcript: str
    observed_actions: str

class TranscriptionResponse(BaseModel):
    transcript: str

class ClinicalNote(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    transcript: str
    observed_actions: str
    clinical_output: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Routes
@api_router.get("/")
async def root():
    return {"message": "Pre-Charting AI Assistant API (Groq)"}

@api_router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe an uploaded audio file using Groq speech-to-text.
    Saves the uploaded file temporarily, sends to Groq, and returns text.
    """
    try:
        suffix = Path(file.filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Open the file and call Groq transcription API (async)
        with open(tmp_path, "rb") as audio_file:
            transcription = await groq_client.audio.transcriptions.create(
                file=audio_file,
                model=os.environ.get("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo"),
                response_format="json",
                language="en",
                temperature=0.0,
            )

        # transcription.text is provided by Groq client (see docs)
        text = getattr(transcription, "text", None) or (transcription.get("text") if isinstance(transcription, dict) else None)
        if text is None:
            # Try fallback: if verbose json or different structure
            text = json.dumps(transcription, default=str)

        # cleanup
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return TranscriptionResponse(transcript=text)

    except Exception as e:
        logger.exception("Transcription error")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@api_router.post("/generate-notes", response_model=ClinicalOutput)
async def generate_clinical_notes(request: TranscriptionRequest):
    """
    Generate clinical notes using Groq chat completions.
    """
    try:
        # Build messages (system + user)
        messages = [
            {"role": "system", "content": CLINICAL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Please analyze the following doctor-patient interaction and generate structured clinical notes in strict JSON format.

Transcript:
{request.transcript}

Observed Non-Verbal Actions:
{request.observed_actions}

Return ONLY valid JSON that matches this schema:
{{
  "subjective": "",
  "objective": "",
  "assessment": "",
  "plan": "",
  "icd10_codes": [{{"condition": "","code": ""}}],
  "medication_interactions": [{{"drug_a":"","drug_b":"","severity":"","note":""}}],
  "red_flags": [],
  "non_verbal_signs": [],
  "clinical_summary": ""
}}
"""
            }
        ]

        # call Groq async chat completion
        chat_resp = await groq_client.chat.completions.create(
            messages=messages,
            model=os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.0,
            max_completion_tokens=1500,
            stream=False,
        )

        # Extract content from response. Groq returns choices[0].message.content per docs
        choice = chat_resp.choices[0]
        # Support both message.content or .message.content nested structures
        content = None
        if hasattr(choice, "message") and getattr(choice.message, "content", None) is not None:
            content = choice.message.content
        elif isinstance(choice, dict):
            content = choice.get("message", {}).get("content") or choice.get("text")
        # final fallback
        if content is None:
            content = str(chat_resp)

        # Strip possible markdown fences
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Parse JSON
        clinical_data = json.loads(content)

        # Validate by constructing ClinicalOutput (will raise if schema mismatch)
        validated = ClinicalOutput(**clinical_data)

        # Save to DB
        note = ClinicalNote(
            transcript=request.transcript,
            observed_actions=request.observed_actions,
            clinical_output=clinical_data,
        )
        doc = note.model_dump()
        doc["timestamp"] = doc["timestamp"].isoformat()
        await db.clinical_notes.insert_one(doc)

        return validated

    except json.JSONDecodeError as e:
        logger.exception("Failed to parse JSON from model response")
        raise HTTPException(status_code=500, detail=f"Failed to parse LLM response: {str(e)}")
    except Exception as e:
        logger.exception("Clinical notes generation error")
        raise HTTPException(status_code=500, detail=f"Clinical notes generation failed: {str(e)}")

@api_router.get("/notes", response_model=List[ClinicalNote])
async def get_clinical_notes():
    notes = await db.clinical_notes.find({}, {"_id": 0}).to_list(1000)
    # convert timestamps back to datetime where needed
    for n in notes:
        if isinstance(n.get("timestamp"), str):
            try:
                n["timestamp"] = datetime.fromisoformat(n["timestamp"])
            except Exception:
                pass
    return notes

# include router & middleware
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
