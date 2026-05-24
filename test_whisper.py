import os
import urllib.request
import whisper

def main():
    audio_url = "https://github.com/ggerganov/whisper.cpp/raw/master/samples/jfk.wav"
    audio_file = "jfk.wav"

    if not os.path.exists(audio_file):
        print(f"Downloading test audio from {audio_url}...")
        urllib.request.urlretrieve(audio_url, audio_file)
        print("Download complete.")
    else:
        print(f"Using existing audio file: {audio_file}")

    print("Loading Whisper 'tiny' model (CPU)...")
    # Using the tiny model for fast loading and low CPU usage
    model = whisper.load_model("tiny")

    print("Transcribing...")
    result = model.transcribe(audio_file)

    print("\n--- Transcription Result ---")
    print(result["text"].strip())
    print("----------------------------\n")

if __name__ == "__main__":
    main()
