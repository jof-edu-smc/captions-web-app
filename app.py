from __future__ import annotations

import os
import sys
import random
import time
import pprint
import pandas as pd # type: ignore
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

try:
    from google.cloud import storage
except ImportError:  # pragma: no cover - optional in local editor environments
    storage = None
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from dotenv import load_dotenv # type: ignore
from flask import Flask, abort, jsonify, request, send_from_directory # type: ignore
from flask_cors import CORS # type: ignore

pp = pprint.PrettyPrinter(indent=4)

load_dotenv()

# Define your absolute paths first
APP_DIR = Path(__file__).resolve().parent
AUDIO_DIR = APP_DIR / "audio"
LOCAL_LOG_PATH = APP_DIR / "submissions.csv"

STEP_1_TRIALS = int(os.getenv("STEP_1_TRIALS", "5"))
STEP_2_TRIALS = int(os.getenv("STEP_2_TRIALS", "5"))
STEP_3_TRIALS = int(os.getenv("STEP_3_TRIALS", "5"))

URL_EXPIRATION = int(os.getenv("URL_EXPIRATION", "3600"))  # Default to 3600 seconds if not set 
SHOW_AUDIO_FILES = os.getenv("SHOW_AUDIO_FILES", "True").strip().lower() in {"1", "true", "yes", "on"}

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

STATIC_DIR = str(APP_DIR / 'static')

# FIX: Explicitly pass absolute paths to Flask so it never misses the target inside Docker
app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    template_folder=STATIC_DIR,
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
    human_caption: str
    synthetic_caption: str
    caption_id: str
    metadata: dict[str, Any]

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
        audio_stimuli = spreadsheet.worksheet("audio_stimuli").get_all_records()
        df_stimuli = pd.DataFrame(audio_stimuli)
        # Caption records from original collection. 
        # caption_records = spreadsheet.worksheet("captions_table").get_all_records()
        # Caption Records for AB testing. 
        caption_records = spreadsheet.worksheet("ab_source_table").get_all_records()
        df_captions = pd.DataFrame(caption_records) 
        rows = [] 
        
        for caption_record in df_captions.itertuples(index=False):
            rir_value = getattr(caption_record, "rir_id", None)
            rir_id = str(rir_value).strip() if rir_value is not None else ""
            caption_id = str(getattr(caption_record, "caption_id", "") or "").strip()
            if not rir_id or not caption_id:
                print(f"Warning: Missing rir_id or caption_id in caption record: {caption_record}")

            stimuli_info = df_stimuli[df_stimuli["rir_id"] == rir_id]

            metadata = {
                "duration_seconds": float(stimuli_info["duration_seconds"].iloc[0]) if not stimuli_info.empty and "duration_seconds" in stimuli_info.columns else 0,
                "location": str(stimuli_info["location_tags"].iloc[0]) if not stimuli_info.empty and "location_tags" in stimuli_info.columns else "",
                "sample_rate": int(str(stimuli_info["sample_rate"].iloc[0]).strip() or 0) if not stimuli_info.empty and "sample_rate" in stimuli_info.columns else 0,
                "rt60": float(str(stimuli_info["rt60"].iloc[0]).strip() or 0) if not stimuli_info.empty and "rt60" in stimuli_info.columns else 0,
                "drr": float(str(stimuli_info["drr"].iloc[0]).strip() or 0) if not stimuli_info.empty and "drr" in stimuli_info.columns else 0,
                "c50": float(str(stimuli_info["c50"].iloc[0]).strip() or 0) if not stimuli_info.empty and "c50" in stimuli_info.columns else 0,
                "c80": float(str(stimuli_info["c80"].iloc[0]).strip() or 0) if not stimuli_info.empty and "c80" in stimuli_info.columns else 0,
                "d50": float(str(stimuli_info["d50"].iloc[0]).strip() or 0) if not stimuli_info.empty and "d50" in stimuli_info.columns else 0,
            }

            human_caption = ""
            if hasattr(caption_record, "human_caption"):
                human_caption = str(getattr(caption_record, "human_caption", "") or "").strip()

            synthetic_caption = ""
            for field_name in ("synthetic_gemini_caption", "synthetic_openai_caption"):
                value = str(getattr(caption_record, field_name, "") or "").strip()
                if value:
                    synthetic_caption = value
                    break

            new_row = StimulusRow(
                rir_id=rir_id,
                audio_clap_id=str(stimuli_info["audio_clap_id"].iloc[0]) if not stimuli_info.empty and "audio_clap_id" in stimuli_info.columns and stimuli_info["audio_clap_id"].notna().any() else "",
                audio_music_id=str(stimuli_info["audio_music_id"].iloc[0]) if not stimuli_info.empty and "audio_music_id" in stimuli_info.columns and stimuli_info["audio_music_id"].notna().any() else "",
                processing_step=str(stimuli_info["processing_step"].iloc[0]) if not stimuli_info.empty and "processing_step" in stimuli_info.columns and stimuli_info["processing_step"].notna().any() else "",
                audio_speech_id=str(stimuli_info["audio_speech_id"].iloc[0]) if not stimuli_info.empty and "audio_speech_id" in stimuli_info.columns and stimuli_info["audio_speech_id"].notna().any() else "",
                num_of_captions=int(str(stimuli_info["num_of_captions"].iloc[0]).strip() or 0) if not stimuli_info.empty and "num_of_captions" in stimuli_info.columns and pd.notna(stimuli_info["num_of_captions"].iloc[0]) else 0,
                num_of_scored_captions=int(str(stimuli_info["num_of_scored_captions"].iloc[0]).strip() or 0) if not stimuli_info.empty and "num_of_scored_captions" in stimuli_info.columns and pd.notna(stimuli_info["num_of_scored_captions"].iloc[0]) else 0,
                human_caption=human_caption,
                synthetic_caption=synthetic_caption,
                caption_id=caption_id,
                metadata=metadata,
            )
            rows.append(new_row)

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
        if storage is None:
            raise RuntimeError("google-cloud-storage is not installed in this environment")

        gcp_project = os.getenv("GCP_PROJECT_ID")
        import google.auth # type: ignore
        from google.auth.transport import requests # type: ignore

        credentials, _ = google.auth.default()
        if not os.getenv("RUNNING_LOCAL"):
            credentials.refresh(requests.Request())

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
    if SHOW_AUDIO_FILES:
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
        "clap_file_url": secure_urls.get(clap_file, f"/audio/claps/{clap_file}") if SHOW_AUDIO_FILES else "",
        "music_file_url": secure_urls.get(music_file, f"/audio/music/{music_file}") if SHOW_AUDIO_FILES else "",
        "speech_file_url": secure_urls.get(speech_file, f"/audio/speech/{speech_file}") if SHOW_AUDIO_FILES else "",
        "metadata": row.metadata,
    }
    
    # Assign one human caption or synthetic caption for each phase
    if phase == "step_2" and row.human_caption:
        payload["caption_id"] = row.caption_id
        payload["baseline_caption"] = row.human_caption

    if phase == "step_3" and row.human_caption and row.synthetic_caption:
        comparison = [row.human_caption, row.synthetic_caption]
        rng.shuffle(comparison)
        payload["caption_a"], payload["caption_b"] = comparison
    else:
        payload["caption_id"] = None
        payload["baseline_caption"] = None
    
    return payload

# def _get_pdf_urls() -> str:
#     """Finds the PIS PDF in the GCP bucket and returns a presigned URL."""
#     try:
#         gcp_project = os.getenv("GCP_PROJECT_ID")
#         storage_client = storage.Client(project=gcp_project)
#         bucket = storage_client.bucket("stimuli")
        
#         # List all files in the 'pdfs/' folder
#         blobs = bucket.list_blobs(prefix="pdfs/")
        
#         pis_url = ""
#         cf_url = ""
        
#         for blob in blobs:
#             # Look for a PDF with 'PIS' in the name
#             if "PIS" in blob.name.upper() and blob.name.lower().endswith("_latest.pdf"):
#                 # Expiration set to 1 hour (3600 seconds)
#                 pis_url = generate_presigned_url("stimuli", blob.name, expiration=URL_EXPIRATION)
#             if "Consent-Form" in blob.name and blob.name.lower().endswith("_latest.pdf"):
#                 cf_url = generate_presigned_url("stimuli", blob.name, expiration=URL_EXPIRATION)
#         return {
#             "pis_url": pis_url, 
#             "cf_url": cf_url,
#         }
#     except Exception as e:
#         print(f"Error fetching PIS PDF url: {e}")
#         return ""

def _batch_stimuli(step_1_trials: int, step_2_trials: int, step_3_trials: int, seed_value: str | None, session_id: str) -> dict[str, Any]:
    
    rng = _make_rng(seed_value)
    rows = _load_stimuli(session_id)
    print(f"DEBUG: Loaded {len(rows)} stimuli rows for session_id: {session_id}")
    # 1. Partition the pools based on your new processing rules
    step_1_pool = []
    step_2_pool = []
    step_3_pool = []
    
    for r in rows:
        p_step = r.processing_step.lower()
        caps = r.num_of_captions
        
        # Step 1: Gathering phase, less than 5 captions
        if STEP_1_TRIALS > 0:
            if caps <= STEP_1_TRIALS and p_step == 'gathering':
                step_1_pool.append(r)
            
        # Step 2: Editing phase, exactly 5 captions, must have caption data to edit
        if STEP_2_TRIALS > 0:
            if (caps <= STEP_2_TRIALS and p_step == 'editing') or r.num_of_captions > 0:
                if r not in step_1_pool:  # Ensure no overlap with Step 1
                    step_2_pool.append(r)
                        
        # Step 3: Editing OR Scoring phase, exactly 5 captions, must have caption data to score 
        if STEP_3_TRIALS > 0:
            # if (caps == STEP_3_TRIALS and p_step in ['editing', 'scoring']) or (r.num_of_captions > r.num_of_scored_captions and r.num_of_captions > 0):
            if caps <= STEP_3_TRIALS or r.num_of_captions > r.num_of_scored_captions:
                step_3_pool.append(r)
    iterator = 0 
    batches = {"step_1": [], "step_2": [], "step_3": []}
    # 2. Select Step 1 
    print(f"Pools: Step 1: {len(step_1_pool)}, Step 2: {len(step_2_pool)}, Step 3: {len(step_3_pool)}")
    
    step_1_selected = _pick_rows(step_1_pool, step_1_trials, rng)
    for i, row in enumerate(step_1_selected):
        batches["step_1"].append(_build_trial_payload("step_1", row, i, rng))
    
    used_rir_ids = {r.rir_id for r in step_1_selected} # Track IDs to prevent session overlap
    
    # 3. Select Step 2 (Excluding anything used in Step 1)
    available_for_step_2 = [r for r in step_2_pool if r.rir_id not in used_rir_ids]
    if len(available_for_step_2) >= step_2_trials:
        step_2_selected = _pick_rows(available_for_step_2, step_2_trials, rng)
        used_rir_ids.update({r.rir_id for r in step_2_selected}) # Update tracking
        
        for i, row in enumerate(step_2_selected):
            batches["step_2"].append(_build_trial_payload("step_2", row, i, rng))
            
    elif len(available_for_step_2) < step_2_trials:
        print(f"Warning: Only {len(available_for_step_2)} eligible rows for Step 2 after filtering, but {step_2_trials} trials requested.")

    # 4. Select Step 3 (Excluding anything used in Step 1 or 2)
    available_for_step_3 = [
        r for r in step_3_pool
        if r.rir_id not in used_rir_ids
        and r.synthetic_caption.strip()
        and r.human_caption.strip()
    ]
    
    if len(available_for_step_3) >= step_3_trials:
        step_3_selected = _pick_rows(available_for_step_3, step_3_trials, rng)
        for i, row in enumerate(step_3_selected):
            batches["step_3"].append(_build_trial_payload("step_3", row, i, rng))
    elif len(available_for_step_3) < step_3_trials:
        print(f"Warning: Only {len(available_for_step_3)} eligible rows for Step 3 after filtering, but {step_3_trials} trials requested.")
        
    training_urls = {
        "speech_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed_sing.mp3", URL_EXPIRATION) if SHOW_AUDIO_FILES else "",
        "music_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed_drum.mp3", URL_EXPIRATION) if SHOW_AUDIO_FILES else "",
        "clap_file_url": generate_presigned_url("stimuli", "training_stimuli/tunnel_entrance_f_1way_mono_processed.mp3", URL_EXPIRATION) if SHOW_AUDIO_FILES else "",
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
        "show_audio_files": SHOW_AUDIO_FILES,
        "stimuli": batches,
        # "pis_url": _get_pdf_urls()["pis_url"],
        # "cf_url": _get_pdf_urls()["cf_url"],
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
        # print(f"Appending record to {sheet_name}: {record} at {datetime.now(timezone.utc).isoformat()}")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)
        # print(f"Logged in with a {'Service Account' if hasattr(credentials, 'service_account_email') else 'unknown'} to Google Sheets at {datetime.now(timezone.utc).isoformat()}")
        # print(f"Opening Spreadsheet ID: {spreadsheet_id}, Sheet Name: {sheet_name}")
        # Connect to the specific table/worksheet
        worksheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        # print(f"Successfully opened worksheet {sheet_name}. Current row count: {worksheet.row_count} at {datetime.now(timezone.utc).isoformat()}")
        # Ensure we write values in the exact order of the provided dictionary
        worksheet.append_row(list(record.values()))
        # print(f"Successfully appended row to {sheet_name} at {datetime.now(timezone.utc).isoformat()}. New row count: {worksheet.row_count}")
    except Exception as e:
        print(f"Error appending to {sheet_name}: {e}")

def get_caption_by_id(caption_id: str) -> str | None:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not spreadsheet_id:
        return None
    try:
        import gspread # type: ignore
        import google.auth # type: ignore

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials, _ = google.auth.default(scopes=scopes)
        client = gspread.authorize(credentials)

        worksheet = client.open_by_key(spreadsheet_id).worksheet("captions_table")
        cell = worksheet.find(caption_id, in_column=1)
        if cell is None:
            return None

        row_number = cell.row
        return worksheet.cell(row_number, 5).value

    except Exception:
        return None


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
        if cell is None:
            return

        row_number = cell.row

        if target_col_name == "num_of_captions":
            target_col = 8
        elif target_col_name == "num_of_scored_captions":
            target_col = 9
        elif target_col_name == "max_captions":
            target_col = 10
        else:
            raise ValueError("No Target Column Name given for updating the number of captions in the dataset for a given RIR ID.")

        current_value = worksheet.cell(row_number, target_col).value
        new_count = int(current_value) + 1 if current_value else 1
        worksheet.update_cell(row_number, target_col, new_count)

    except Exception:
        return

# ROUTE HANDLERS 
@app.get("/api/health")
def health_check() -> Any:
    return jsonify({"ok": True})

@app.get("/api/get-stimuli")
def get_stimuli() -> Any:
    session_id = request.args.get("session_id") or uuid4().hex
    seed_value = request.args.get("seed")
    if seed_value is not None and seed_value != "":
        seed_value = str(seed_value)
    else:
        seed_value = None

    try:
        payload = _batch_stimuli(
            step_1_trials=STEP_1_TRIALS,
            step_2_trials=STEP_2_TRIALS,
            step_3_trials=STEP_3_TRIALS,
            seed_value=seed_value,
            session_id=session_id,
        )
        
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
    
    phase = payload.get("phase")
    
    if phase not in {"step_1", "step_2", "step_3"}:
        return jsonify({"error": "phase must be one of step_1, step_2, or step_3"}), 400

    participant_context = payload.get("participant_context") or {}
    
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
            "hearing_impairment": participant_context.get("hearing", ""),
        })
        
        increment_caption_count(rir_id, target_col_name="num_of_captions")
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
        
    # ----------------------------------------------------
    # ROUTE 3: Evaluation -> evaluations_table
    # ----------------------------------------------------
    elif phase == "step_3":
        caption_a = _clean_value(payload.get("caption_a"))
        caption_b = _clean_value(payload.get("caption_b"))
        selected_caption = _clean_value(payload.get("selected_caption"))
        accuracy_score_a = _clean_value(payload.get("accuracy_score_a"))
        accuracy_score_b = _clean_value(payload.get("accuracy_score_b"))
        
        if not caption_a or not caption_b:
            return jsonify({"error": "step_3 requires caption_a and caption_b"}), 400
        if selected_caption not in {"A", "B", "Neither"}:
            return jsonify({"error": "step_3 selected_caption must be A, B, or Neither"}), 400
        if accuracy_score_a not in {"1", "2", "3", "4"}:
            return jsonify({"error": "step_3 accuracy_score_a must be 1, 2, 3, or 4"}), 400
        if accuracy_score_b not in {"1", "2", "3", "4"}:
            return jsonify({"error": "step_3 accuracy_score_b must be 1, 2, 3, or 4"}), 400
        
        append_row_to_sheet("annotators_table", {
            "prolific_id": annotator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "study_id": participant_context.get("study_id", ""),
            "session_id": participant_context.get("session_id", ""),
            "age_range": participant_context.get("age_range", ""),
            "experience_in_audio": participant_context.get("experience_in_audio", ""),
            "hearing_impairment": participant_context.get("hearing", ""),
        })
            
        # append_row_to_sheet("evaluations_table", {
        append_row_to_sheet("ab_eval_table", {
            "annotator_id": annotator_id,
            "evaluation_id": uuid4().hex,
            "caption_id": target_caption_id,
            "prolific_id": annotator_id,
            "caption_a": caption_a,
            "caption_b": caption_b,
            "selected_caption": selected_caption,
            "accuracy_score_a": accuracy_score_a,
            "accuracy_score_b": accuracy_score_b,
        })

        increment_caption_count(rir_id, target_col_name="num_of_scored_captions")
        
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
def catch_all(path: str):
    if path != "" and os.path.exists(os.path.join(STATIC_DIR, path)):
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, 'index.html')

if __name__ == "__main__":
    load_dotenv()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)