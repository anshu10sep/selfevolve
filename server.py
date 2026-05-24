import os
import shutil
import tempfile
import whisper
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Whisper Speech-to-Text Server")

# Enable CORS for local file access and local servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the model on startup (cached in memory)
print("Loading Whisper 'tiny' model...")
model = whisper.load_model("tiny")
print("Whisper model loaded successfully!")

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def read_root():
    # Serve index.html relative to this script
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>index.html not found</h1>", status_code=404)

@app.get("/status")
def read_status():
    return {"status": "running", "model": "tiny"}

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Validate file presence
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    # Create a temporary file to save the uploaded audio
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = temp_file.name

    try:
        # Transcribe audio using the preloaded Whisper model
        # Disable FP16 since we're running on CPU
        result = model.transcribe(temp_path, fp16=False)
        transcription_text = result.get("text", "").strip()
        
        return JSONResponse(content={
            "success": True,
            "text": transcription_text
        })
    except Exception as e:
        print(f"Error during transcription: {str(e)}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": str(e)
        })
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
