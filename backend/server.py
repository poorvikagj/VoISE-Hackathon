from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from emergentintegrations.llm.openai import OpenAISpeechToText
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json
import tempfile

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Initialize AI services
emergent_key = os.environ.get('EMERGENT_LLM_KEY')
stt = OpenAISpeechToText(api_key=emergent_key)

# System prompt for clinical notes
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

# Models
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
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transcript: str
    observed_actions: str
    clinical_output: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Routes
@api_router.get("/")
async def root():
    return {"message": "Pre-Charting AI Assistant API"}

@api_router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio file using Whisper API"""
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Transcribe using Whisper
        with open(temp_path, "rb") as audio_file:
            response = await stt.transcribe(
                file=audio_file,
                model="whisper-1",
                response_format="json",
                language="en"
            )
        
        # Clean up temp file
        os.unlink(temp_path)
        
        return TranscriptionResponse(transcript=response.text)
    
    except Exception as e:
        logging.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@api_router.post("/generate-notes", response_model=ClinicalOutput)
async def generate_clinical_notes(request: TranscriptionRequest):
    """Generate clinical SOAP notes from transcript and observed actions"""
    try:
        # Initialize LLM chat
        chat = LlmChat(
            api_key=emergent_key,
            session_id=str(uuid.uuid4()),
            system_message=CLINICAL_SYSTEM_PROMPT
        ).with_model("openai", "gpt-5.1")
        
        # Create user message
        user_message = UserMessage(
            text=f"""Please analyze the following doctor-patient interaction and generate structured clinical notes.

Transcript:
{request.transcript}

Observed Non-Verbal Actions:
{request.observed_actions}

Generate the clinical documentation in JSON format."""
        )
        
        # Get LLM response
        response = await chat.send_message(user_message)
        
        # Parse JSON response
        # Try to extract JSON from response if it's wrapped in markdown
        response_text = response.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        clinical_data = json.loads(response_text)
        
        # Save to database
        note = ClinicalNote(
            transcript=request.transcript,
            observed_actions=request.observed_actions,
            clinical_output=clinical_data
        )
        
        doc = note.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        await db.clinical_notes.insert_one(doc)
        
        return ClinicalOutput(**clinical_data)
    
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing error: {str(e)}. Response was: {response}")
        raise HTTPException(status_code=500, detail=f"Failed to parse LLM response: {str(e)}")
    except Exception as e:
        logging.error(f"Clinical notes generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Clinical notes generation failed: {str(e)}")

@api_router.get("/notes", response_model=List[ClinicalNote])
async def get_clinical_notes():
    """Retrieve all clinical notes"""
    notes = await db.clinical_notes.find({}, {"_id": 0}).to_list(1000)
    
    for note in notes:
        if isinstance(note['timestamp'], str):
            note['timestamp'] = datetime.fromisoformat(note['timestamp'])
    
    return notes

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()