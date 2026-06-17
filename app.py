from __future__ import annotations

import os
import sys
import random
import time
import pprint
from google.cloud import storage
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from dotenv import load_dotenv # type: ignore
from flask import Flask, abort, jsonify, request, send_from_directory # type: ignore
from flask_cors import CORS # type: ignore

pp = pprint.PrettyPrinter(indent=4)

# Define your absolute paths first
APP_DIR = Path(__file__).resolve().parent
AUDIO_DIR = APP_DIR / "audio"
LOCAL_LOG_PATH = APP_DIR / "submissions.csv"

STEP_1_TRIALS = int(os.getenv("STEP_1_TRIALS", "5"))
STEP_2_TRIALS = int(os.getenv("STEP_2_TRIALS", "5"))
STEP_3_TRIALS = int(os.getenv("STEP_3_TRIALS", "5"))

URL_EXPIRATION = int(os.getenv("URL_EXPIRATION", "3600"))  # Default to 3600 seconds if not set 

STIMULUS_CANDIDATES = [
    APP_DIR / "template_spreadsheet.csv",
]

CAPTION_KEYS = [
    "Caption 1 - Text",
    "Caption 2 - Text",
    "Caption 3 - Text",
    "Caption 4 - Text",
    "Caption 5 - Text",
]

# FIX: Explicitly pass absolute paths to Flask so it never misses the target inside Docker
app = Flask(
    __name__, 
    static_folder=str(APP_DIR / 'static'),      
    template_folder=str(APP_DIR / 'static')    
)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@dataclass(slots=True)
class StimulusRow:
    rir_id: str
    audio_clap_id: str
    audio_music_id: str
    audio_speech_id: str
    processing_step: str
    num_of_captions: int
    num_of_scored_captions: int
    captions: list[dict[str, str]]


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _load_stimuli(session_id: str) -> list[StimulusRow]:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        raise ValueError("No Google Sheets ID found in environment variables. Please set GOOGLE_SHEETS_ID to load stimuli from Google Sheets.")

    try:
        import gspread # type: ignore
        import google.auth # type: ignore
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(spreadsheet_id)

        # 1. Fetch both relational tables
        audio_records = spreadsheet.worksheet("audio_stimuli").get_all_records()
        caption_records = spreadsheet.worksheet("captions_table").get_all_records()

        # 2. Group captions by their foreign key (audio_id)
        captions_by_rir = {}
        for cap in caption_records:
            r_id = str(cap.get("rir_id", "")).strip()
            
            if str(cap.get("session_id", "")).strip() == session_id:
                continue
            
            if r_id not in captions_by_rir:
                captions_by_rir[r_id] = []
                
            captions_by_rir[r_id].append(cap)
        
        rows = []
        # 3. Construct the flat StimulusRow objects for the frontend
        for rir in audio_records:
            rir_id = str(rir.get("rir_id", "")).strip()
            
            # print(f"Processing RIR record with ID: {rir_id}")
            if not rir_id:
                continue
            
            
            # Fetch all captions linked to this audio file
            linked_captions = captions_by_rir.get(rir_id, [])
            
            raw_num = str(rir.get("num_of_captions", "0")).strip()
            num_captions = int(raw_num) if raw_num.isdigit() else 0
            
            scored_raw = str(rir.get("num_of_scored_captions", "0")).strip()
            num_scored_captions = int(scored_raw) if scored_raw.isdigit() else 0
            
            row = StimulusRow(
                rir_id=rir_id,
                audio_clap_id=rir.get("audio_clap_id", "").strip(),
                audio_music_id=rir.get("audio_music_id", "").strip(),
                audio_speech_id=rir.get("audio_speech_id", "").strip(),
                processing_step=rir.get("processing_step", "").strip(),
                num_of_captions=num_captions,
                num_of_scored_captions=num_scored_captions,
                captions=linked_captions,
            )
            rows.append(row)
        if not rows:
            raise ValueError("No valid stimuli rows mapped from database.")
        return rows
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ValueError(f"Failed to load stimuli from Google Sheets: {e}")

def _make_rng(seed_value: str | None) -> random.Random:
    if seed_value is None or seed_value == "":
        return random.Random()
    try:
        return random.Random(int(seed_value))
    except ValueError:
        return random.Random(seed_value)

def _pick_rows(rows: list[StimulusRow], count: int, rng: random.Random) -> list[StimulusRow]:
    if count <= 0:
        return []
    if count <= len(rows):
        return rng.sample(rows, count)

    pool = rows[:]
    rng.shuffle(pool)
    selected = list(pool)
    while len(selected) < count:
        refill = rows[:]
        rng.shuffle(refill)
        selected.extend(refill)
    return selected[:count]


def generate_presigned_url(bucket_name: str, object_path: str, expiration: int = 3600) -> str:
    """Generates a presigned URL for a GCS object using IAM API signing method.

    Args:
        bucket_name (str): Name of GCS Bucket
        object_name (str): Path to the object within the bucket (e.g., "folder/audio.mp3")
        expiration (int, optional): Time of expiration from creation. Defaults to 3600.

    Returns:
        str: Returns a string of the Signed URL. If error, returns an empty string.
    """
    try:
        gcp_project = os.getenv("GCP_PROJECT_ID")
        import google.auth # type: ignore
        from google.auth.transport import requests # type: ignore
        
        credentials, _ = google.auth.default()
        if os.getenv("RUNNING_LOCAL"):
            print("Running locally, using default credentials")
        else:        
            credentials.refresh(requests.Request())
        # print(f"Obtained credentials of type {credentials} for project {gcp_project}")
        
        storage_client = storage.Client(project=gcp_project, credentials=credentials)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)
        # print(f"SA EMAIL: {os.getenv('GCP_SERVICE_ACCOUNT_EMAIL')}")
        # sa_email = os.getenv("GCP_SERVICE_ACCOUNT_EMAIL")
        sa_email = "972036545446-compute@developer.gserviceaccount.com" 

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration),
            method="GET",
            service_account_email=sa_email,
            access_token=credentials.token
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        import traceback
        traceback.print_exc()
        return ""
    

def _build_trial_payload(phase: str, row: StimulusRow, trial_index: int, rng: random.Random) -> dict[str, Any]:
    # Extract file names
    clap_file = Path(row.audio_clap_id).name
    music_file = Path(row.audio_music_id).name
    speech_file = Path(row.audio_speech_id).name
    
    file_mappings = {
        "claps": clap_file,
        "music": music_file,
        "speech": speech_file
    }
    
    secure_urls = {}
    for folder, filename in file_mappings.items():
        if filename: # Ensure it's not a blank string
            # Combine them to create the exact GCS object path
            gcs_object_path = f"audio/{folder}/{filename}"
            secure_urls[filename] = generate_presigned_url(
                bucket_name="stimuli", 
                object_path=gcs_object_path, 
                expiration=URL_EXPIRATION
            )
            
    payload: dict[str, Any] = {
        "phase": phase,
        "trial_index": trial_index,
        "rir_id": row.rir_id,
        "clap_file_url": secure_urls.get(clap_file, f"/audio/claps/{clap_file}"),
        "music_file_url": secure_urls.get(music_file, f"/audio/music/{music_file}"),
        "speech_file_url": secure_urls.get(speech_file, f"/audio/speech/{speech_file}"),
    }
    # print(f"Base payload for trial {trial_index} in {phase}: {payload}")
    # Assign a random caption for editing/evaluating if the phase requires it
    if phase in ["step_2", "step_3"] and row.captions:
        selected_caption = rng.choice(row.captions)
        payload["caption_id"] = selected_caption.get("caption_id")
        # Naming it 'baseline_caption' here matches your App.jsx expectations
        payload["baseline_caption"] = selected_caption.get("caption_text") 
    else:
        payload["caption_id"] = None
        payload["baseline_caption"] = None

    return payload

def _get_pis_pdf_url() -> str:
    """Finds the PIS PDF in the GCP bucket and returns a presigned URL."""
    try:
        gcp_project = os.getenv("GCP_PROJECT_ID")
        storage_client = storage.Client(project=gcp_project)
        bucket = storage_client.bucket("stimuli")
        
        # List all files in the 'pdfs/' folder
        blobs = bucket.list_blobs(prefix="pdfs/")
        
        for blob in blobs:
            # Look for a PDF with 'PIS' in the name
            if "PIS" in blob.name.upper() and blob.name.lower().endswith("_latest.pdf"):
                # Expiration set to 1 hour (3600 seconds)
                return generate_presigned_url("stimuli", blob.name, expiration=URL_EXPIRATION)
        return ""
    except Exception as e:
        print(f"Error fetching PIS PDF url: {e}")
        return ""

def _batch_stimuli(step_1_trials: int, step_2_trials: int, step_3_trials: int, seed_value: str | None, session_id: str) -> dict[str, Any]:
    
    rng = _make_rng(seed_value)
    rows = _load_stimuli(session_id)
    print(f"Loaded {len(rows)} stimulus rows from the database for session {session_id}.")
    # 1. Partition the pools based on your new processing rules
    step_1_pool = []
    step_2_pool = []
    step_3_pool = []
    
    for r in rows:
        p_step = r.processing_step.lower()
        caps = r.num_of_captions
        # print(r)
        # Step 1: Gathering phase, less than 5 captions
        if caps < 5 and p_step == 'gathering':
            step_1_pool.append(r)
            
        # Step 2: Editing phase, exactly 5 captions, must have caption data to edit
        if (caps == 5 and p_step == 'editing') or r.num_of_captions > 0:
            step_2_pool.append(r)
            
        # Step 3: Editing OR Scoring phase, exactly 5 captions, must have caption data to score
        if (caps == 5 and p_step in ['editing', 'scoring']) or (r.num_of_captions > r.num_of_scored_captions and r.num_of_captions > 0):
            step_3_pool.append(r)
    
    # 2. Select Step 1 
    # print(f"Pools: Step 1: {len(step_1_pool)}, Step 2: {len(step_2_pool)}, Step 3: {len(step_3_pool)}")
    step_1_selected = _pick_rows(step_1_pool, step_1_trials, rng)
    # print(f"Selected {len(step_1_selected)} rows for Step 1. {step_1_trials} requested.")
    used_rir_ids = {r.rir_id for r in step_1_selected} # Track IDs to prevent session overlap
    # print(f"length of RIR ID sUsed: {(len(used_rir_ids))} - {len(rows)}")
    # 3. Select Step 2 (Excluding anything used in Step 1)
    available_for_step_2 = [r for r in step_2_pool if r.rir_id not in used_rir_ids]
    if len(available_for_step_2) < step_2_trials:
        print(f"Warning: Only {len(available_for_step_2)} eligible rows for Step 2 after filtering, but {step_2_trials} trials requested. Will allow repeats from Step 1 pool.")
    
    # print(f"Available for Step 2: {len(available_for_step_2)}")
    step_2_selected = _pick_rows(available_for_step_2, step_2_trials, rng)
    used_rir_ids.update({r.rir_id for r in step_2_selected}) # Update tracking
   
    # print(f"Used RIR IDs after Step 2: {len(rows)} - {len(used_rir_ids)}")
    # 4. Select Step 3 (Excluding anything used in Step 1 or 2)
    available_for_step_3 = [r for r in step_3_pool if r.rir_id not in used_rir_ids]
    if len(available_for_step_3) < step_3_trials:
        print(f"Warning: Only {len(available_for_step_3)} eligible rows for Step 3 after filtering, but {step_3_trials} trials requested. Will allow repeats from previous pools.")
    step_3_selected = _pick_rows(available_for_step_3, step_3_trials, rng)
    
    batches = {"step_1": [], "step_2": [], "step_3": []}

    # 5. Build the payloads
    for i, row in enumerate(step_1_selected):
        batches["step_1"].append(_build_trial_payload("step_1", row, i, rng))
    for i, row in enumerate(step_2_selected):
        batches["step_2"].append(_build_trial_payload("step_2", row, i, rng))
    for i, row in enumerate(step_3_selected):
        batches["step_3"].append(_build_trial_payload("step_3", row, i, rng))
        
    training_urls = {
        "speech_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed_sing.mp3", URL_EXPIRATION),
        "music_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed_drum.mp3", URL_EXPIRATION),
        "clap_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed.mp3", URL_EXPIRATION),
        "training_baseline_caption": "An auditory experience at in evokes a balanced and natural sensation as sound waves bounce within the grand, cavernous environment.",
    }
    
    training_payload = {
        "training_step_1": training_urls,
        "training_step_2": training_urls,
    }
    
    return {
        "batch_id": uuid4().hex,
        "requested_trials": {"step_1": step_1_trials, "step_2": step_2_trials, "step_3": step_3_trials},
        "training": training_payload,
        "stimuli": batches,
        "pis_url": _get_pis_pdf_url(),
    }

def append_row_to_sheet(sheet_name: str, record: dict[str, Any]) -> None:
    """Appends a dictionary record to the specified Google Sheet worksheet."""
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")

    if not spreadsheet_id:
        print(f"No Google Sheets ID found. Saving {sheet_name} locally (Not implemented in this refactor).")
        return

    try:
        import gspread # type: ignore
        import google.auth # type: ignore
        print(f"Appending record to {sheet_name}: {record} at {datetime.now(timezone.utc).isoformat()}")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)
        print(f"Logged in {credentials.service_account_email if hasattr(credentials, 'service_account_email') else 'unknown'} to Google Sheets. at {datetime.now(timezone.utc).isoformat()}")
        print(f"Opening Spreadsheet ID: {spreadsheet_id}, Sheet Name: {sheet_name}")
        # Connect to the specific table/worksheet
        worksheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        print(f"Successfully opened worksheet {sheet_name}. Current row count: {worksheet.row_count} at {datetime.now(timezone.utc).isoformat()}")
        # Ensure we write values in the exact order of the provided dictionary
        worksheet.append_row(list(record.values()))
        print(f"Successfully appended row to {sheet_name} at {datetime.now(timezone.utc).isoformat()}. New row count: {worksheet.row_count}")
    except Exception as e:
        print(f"Error appending to {sheet_name}: {e}")

def get_caption_by_id(caption_id: str, ) -> None:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        return
    try:
        import gspread # type: ignore
        import google.auth # type: ignore
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)
        
        worksheet = client.open_by_key(spreadsheet_id).worksheet("captions_table")
        cell = worksheet.find(caption_id, in_column=1)
        
        row_number = cell.row
        return worksheet.cell(row_number, 5).value
        
    except gspread.exceptions.CellNotFound:
        print(f"Error: rir_id '{caption_id}' not found in audio_stimuli sheet.")
    except Exception as e:
        print(f"Error incrementing caption count: {e}")
        
def increment_caption_count(rir_id: str, target_col_name: str) -> None:
    """Finds a specific rir_id in the audio_stimuli sheet and increments its caption count."""
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    target_col = 0
    if not spreadsheet_id:
        return

    try:
        import gspread # type: ignore
        import google.auth # type: ignore
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)
        
        worksheet = client.open_by_key(spreadsheet_id).worksheet("audio_stimuli")
        cell = worksheet.find(rir_id, in_column=1)
        row_number = cell.row
        
        if target_col_name == "num_of_captions":
            target_col = 8
        if target_col_name == "num_of_scored_captions":
            target_col = 9
        if target_col_name == "max_captions":
            target_col = 10
        elif target_col == 0:
            raise ValueError("No Target Column Name given for updating the number of captions in the dataset for a given RIR ID.")
            
        current_value = worksheet.cell(row_number, target_col).value
        
        # 3. Calculate the new value (handling blank cells gracefully)
        new_count = int(current_value) + 1 if current_value else 1
        
        # 4. Write the incremented value back to the exact cell
        worksheet.update_cell(row_number, target_col, new_count)
        
    except gspread.exceptions.CellNotFound:
        print(f"Error: rir_id '{rir_id}' not found in audio_stimuli sheet.")
    except Exception as e:
        print(f"Error incrementing caption count: {e}")

# ROUTE HANDLERS 
@app.get("/api/health")
def health_check() -> Any:
    return jsonify({"ok": True})

@app.get("/api/get-stimuli")
def get_stimuli() -> Any:
    session_id = request.args.get("session_id") or uuid4().hex
    seed_value = request.args.get("seed") or 42

    try:
        payload = _batch_stimuli(
            step_1_trials=STEP_1_TRIALS,
            step_2_trials=STEP_2_TRIALS,
            step_3_trials=STEP_3_TRIALS,
            seed_value=seed_value,
            session_id=session_id,
        )
        print(f"Prepared stimuli payload for session {session_id}:")
        payload["prolific_context"] = {
            "prolific_id": request.args.get("prolific_id", ""),
            "study_id": request.args.get("study_id", ""),
            "session_id": session_id,
        }
        return jsonify(payload)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Failed to prepare stimuli: {exc}"}), 500

@app.post("/api/submit-response")
def submit_response() -> Any:
    payload = request.get_json(silent=True) or {}
    # print("Received submission payload:")
    # pp.pprint(payload)
    phase = payload.get("phase")
    
    if phase not in {"step_1", "step_2", "step_3"}:
        return jsonify({"error": "phase must be one of step_1, step_2, or step_3"}), 400

    participant_context = payload.get("participant_context") or {}
    # print("Participant context:")
    # pp.pprint(participant_context)
    stimulus = payload.get("stimulus") or {}
    
    # Common Identifiers
    annotator_id = _clean_value(participant_context.get("prolific_id"))
    rir_id = _clean_value(stimulus.get("rir_id"))
    
    target_caption_id = _clean_value(stimulus.get("caption_id"))
    
    # ------------------------------------------------
    # TABLE SUMMARIES: 
    # Captions: 
    # caption_id, rir_id, prolific_id, session_id, caption_text, caption_type, parent_caption_id, 
    # total_accuracy_score, total_fluency_score
    
    # Annotators: 
    # prolific_id	timestamp	phase	study_id	session_id	age_range	experience_in_audio
    
    # Audio Stimuli:
    # rir_id	audio_speech_id	audio_music_id	audio_clap_id	source_dataset	duration_seconds	processing_step
    
    # Evaluations:
    # evaluation_id	caption_id	annotator_id	accuracy_score	fluency_score
    # ----------------------------------------------------
    # ROUTE 1: Generative Captioning -> captions_table
    # ----------------------------------------------------
    if phase == "step_1":
        generated_text = _clean_value(payload.get("generated_text") or payload.get("response_text"))
        if not generated_text:
            return jsonify({"error": "step_1 requires generated_text"}), 400
        
        append_row_to_sheet("captions_table", {
            "caption_id": uuid4().hex, # Create new unique ID for a new caption
            "rir_id": rir_id,
            "prolific_id": participant_context.get("prolific_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "caption_text": generated_text,
            "caption_type": "Initial",
            "parent_caption_id": "",
        })
        
        append_row_to_sheet("annotators_table", {
            "prolific_id": annotator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "study_id": participant_context.get("study_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "age_range": participant_context.get("age_range", ""),
            "experience_in_audio": participant_context.get("experience_in_audio", ""),
        })
        
        increment_caption_count(rir_id, target_col_name="num_of_captions")
        print(f"Step 1 submission processed for RIR ID {rir_id} by annotator {annotator_id}. New caption added and count incremented.")
    # ----------------------------------------------------
    # ROUTE 2: Rephrasing/Editing -> captions_table
    # ----------------------------------------------------
    elif phase == "step_2":
        edited_text = _clean_value(payload.get("edited_text") or payload.get("response_text"))
        if not edited_text:
            return jsonify({"error": "step_2 requires edited_text"}), 400
            
        append_row_to_sheet("captions_table", {
            "caption_id": uuid4().hex, # Generate a new ID for this new edit
            "rir_id": rir_id,
            "prolific_id": participant_context.get("prolific_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "caption_text": edited_text, 
            "caption_type": "Edited",    
            "parent_caption_id": target_caption_id,
        })
        
        append_row_to_sheet("annotators_table", {
            "prolific_id": annotator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "study_id": participant_context.get("study_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "age_range": participant_context.get("age_range", ""),
            "experience_in_audio": participant_context.get("experience_in_audio", ""),
        })
        original_caption = get_caption_by_id(target_caption_id)
        if edited_text != original_caption:
            increment_caption_count(rir_id, target_col_name="num_of_captions")
        print(f"Step 2 submission processed for RIR ID {rir_id} by annotator {annotator_id}. Edited caption added and count updated if changed.")
    # ----------------------------------------------------
    # ROUTE 3: Evaluation -> evaluations_table
    # ----------------------------------------------------
    elif phase == "step_3":
        grammar = payload.get("grammar_rating")
        accuracy = payload.get("accuracy_rating")
        
        if not grammar or not accuracy:
            return jsonify({"error": "step_3 requires grammar_rating and accuracy_rating"}), 400
        
        append_row_to_sheet("annotators_table", {
            "prolific_id": annotator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "study_id": participant_context.get("study_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "age_range": participant_context.get("age_range", ""),
            "experience_in_audio": participant_context.get("experience_in_audio", ""),
        })
            
        append_row_to_sheet("evaluations_table", {
            "evaluation_id": uuid4().hex,
            "caption_id": target_caption_id, 
            "annotator_id": annotator_id,
            "accuracy_score": int(accuracy),
            "fluency_score": int(grammar)
        })

        increment_caption_count(rir_id, target_col_name="num_of_scored_captions")
        print(f"Step 3 submission processed for RIR ID {rir_id} by annotator {annotator_id}. Evaluation recorded and scored caption count incremented.")
        
    return jsonify({"ok": True, "phase": phase})

@app.get("/audio/<path:filename>")
def serve_audio(filename: str) -> Any:
    if not AUDIO_DIR.exists():
        abort(404)
    return send_from_directory(AUDIO_DIR, filename)

@app.get("/files/<path:filename>")
def serve_study_file(filename: str) -> Any:
    requested_path = (APP_DIR / filename).resolve()
    if APP_DIR not in requested_path.parents and requested_path != APP_DIR:
        abort(404)
    if not requested_path.exists() or requested_path.suffix.lower() not in {".pdf", ".csv"}:
        abort(404)
    return send_from_directory(APP_DIR, filename)

@app.post("/api/log")
def client_log() -> Any:
    """Receives logs from the React frontend and prints them to the Docker console."""
    payload = request.get_json(silent=True) or {}
    level = payload.get("level", "INFO").upper()
    message = payload.get("message", "No message provided")
    context = payload.get("context", {})

    # Format the log so it stands out in your terminal
    log_string = f"[CLIENT {level}] {message} | Context: {context}"
    
    # Print to stderr to ensure Docker flushes it to the console immediately
    print(log_string, file=sys.stderr)
    
    return jsonify({"ok": True})

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == "__main__":
    load_dotenv()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)