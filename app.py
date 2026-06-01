from __future__ import annotations

import csv
import json
import os
import random
import pprint
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS

pp = pprint.PrettyPrinter(indent=4)

APP_DIR = Path(__file__).resolve().parent
APP_DIR = Path(__file__).resolve().parent
AUDIO_DIR = APP_DIR / "audio"

LOCAL_LOG_PATH = APP_DIR / "submissions.csv"

STEP_1_TRIALS = int(os.getenv("STEP_1_TRIALS", "5"))
STEP_2_TRIALS = int(os.getenv("STEP_2_TRIALS", "5"))
STEP_3_TRIALS = int(os.getenv("STEP_3_TRIALS", "5"))

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

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}})


@dataclass(slots=True)
class StimulusRow:
    rir_id: str
    audio_file: str
    audio_file_path: str
    caption_texts: list[str]
    source_row: dict[str, str]


def _first_existing_path(paths: Iterable[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("No supported stimulus CSV found in captions-web-app or sheets/")


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _normalize_stimulus_row(row: dict[str, str]) -> StimulusRow:
    normalized = {key.strip(): _clean_value(value) for key, value in row.items() if key is not None}

    rir_id = normalized.get("RIR ID") or normalized.get("rir_id") or normalized.get("rir_file") or normalized.get("rir")
    audio_file = normalized.get("audio_file") or normalized.get("audio_file_path")

    caption_texts: list[str] = []
    for key in CAPTION_KEYS:
        value = normalized.get(key)
        if value:
            caption_texts.append(value)

    if not caption_texts:
        for key, value in normalized.items():
            if key.lower().startswith("caption") and value:
                caption_texts.append(value)

    if not caption_texts:
        raise ValueError("Stimulus row did not contain any caption text")

    if not rir_id:
        rir_id = audio_file or "unknown-rir"
    if not audio_file:
        audio_file = rir_id or "unknown audio file"

    audio_file_path = normalized.get("audio_file_path") or f"/audio/{audio_file}"

    return StimulusRow(
        rir_id=rir_id,
        audio_file=audio_file,
        audio_file_path=audio_file_path,
        caption_texts=caption_texts,
        source_row=normalized,
    )

def get_template_csv() -> Path:
    stimulus_csv = _first_existing_path(STIMULUS_CANDIDATES)
    with stimulus_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [_normalize_stimulus_row(row) for row in reader if any((value or "").strip() for value in row.values())]
    if not rows:
        raise ValueError(f"No stimulus rows found in {stimulus_csv}")
    return rows

def _load_stimuli() -> list[StimulusRow]:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    credentials_source = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    worksheet_name = os.getenv("STIMULUS_GOOGLE_SHEETS_WORKSHEET", "template_spreadsheet")
    print(f"Loading stimulus with spreadsheet_id={spreadsheet_id}, credentials_source={'set' if credentials_source else 'not set'}, worksheet_name={worksheet_name}")
    if not spreadsheet_id or not credentials_source:
        print("Google Sheets credentials not fully configured, loading stimulus from local CSV")
        pp.pprint(get_template_csv())
        return get_template_csv()
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        if Path(credentials_source).exists():
            credentials_info = json.loads(Path(credentials_source).read_text(encoding="utf-8"))
        else:
            credentials_info = json.loads(credentials_source)
            
        print("Successfully loaded Google Sheets credentials")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        client = gspread.authorize(credentials)
        worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        worksheet_rows = worksheet.get_all_records()
        rows = [_normalize_stimulus_row(row) for row in worksheet_rows if any((value or "").strip() for value in row.values())]
        if not rows:
            raise ValueError(f"No stimulus rows found in Google Sheets worksheet {worksheet_name}")
        return rows
    except Exception:
        print("Failed to load stimulus from Google Sheets, falling back to local CSV")
        pp.pprint(get_template_csv())
        return get_template_csv()


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


def _load_rating_history() -> list[dict[str, Any]]:
    """Load all step_1 (generation) submissions with ratings from submissions.csv."""
    if not LOCAL_LOG_PATH.exists():
        return []
    try:
        rows = []
        with LOCAL_LOG_PATH.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("phase") == "step_1" and row.get("generated_text"):
                    rows.append(row)
        return rows
    except Exception:
        return []


def _build_caption_weights(history: list[dict[str, Any]], all_rows: list[StimulusRow]) -> dict[str, dict[str, float]]:
    """
    Build weight mapping: {audio_file: {caption_text: weight}}.
    Low-rated captions get higher weights for Step 2/3.
    """
    weights = {}
    caption_ratings = {}
    
    for record in history:
        audio_file = record.get("audio_file", "")
        caption_text = record.get("generated_text", "").strip()
        if not audio_file or not caption_text:
            continue
        
        key = (audio_file, caption_text)
        if key not in caption_ratings:
            caption_ratings[key] = []
        caption_ratings[key].append(record)
    
    for row in all_rows:
        audio_file = row.audio_file
        weights[audio_file] = {}
        
        rated_captions = {k[1]: v for k, v in caption_ratings.items() if k[0] == audio_file}
        
        if rated_captions:
            for caption_text, records in rated_captions.items():
                avg_rating = sum(int(r.get("rating", "3") or "3") for r in records) / len(records)
                weight = max(0.1, (6.0 - avg_rating) / 2.0)  # Lower rating = higher weight
                weights[audio_file][caption_text] = weight
        
        # Include initial captions as fallback
        for caption_text in row.caption_texts:
            if caption_text not in weights[audio_file]:
                weights[audio_file][caption_text] = 1.0
    
    return weights


def _pick_caption_for_step2_or_3(audio_file: str, row: StimulusRow, weights: dict[str, dict[str, float]], rng: random.Random) -> str:
    """Pick a caption for Step 2/3, preferring low-rated captions."""
    if audio_file not in weights or not weights[audio_file]:
        return rng.choice(row.caption_texts) if row.caption_texts else ""
    
    caption_pool = list(weights[audio_file].keys())
    weight_values = [weights[audio_file][c] for c in caption_pool]
    total_weight = sum(weight_values)
    
    if total_weight == 0:
        return rng.choice(row.caption_texts) if row.caption_texts else ""
    
    normalized_weights = [w / total_weight for w in weight_values]
    return rng.choices(caption_pool, weights=normalized_weights, k=1)[0]


def _build_trial_payload(phase: str, row: StimulusRow, trial_index: int, rng: random.Random) -> dict[str, Any]:
    caption_options = row.caption_texts[:]
    caption_index = rng.randrange(len(caption_options)) if caption_options else 0
    
    selected_caption = caption_options[caption_index] if caption_options else ""
    
    payload: dict[str, Any] = {
        "phase": phase,
        "trial_index": trial_index,
        "rir_id": row.rir_id,
        "audio_file": row.audio_file,
        "audio_file_path": row.audio_file_path,
        "audio_url": f"/audio/{Path(row.audio_file_path).name}",
        "caption_options": caption_options,
        "source_row": row.source_row,
    }

    if phase == "step_1":
        payload.update(
            {
                "selected_caption_index": caption_index,
                "selected_caption": selected_caption,
            }
        )
    elif phase == "step_2":
        payload.update(
            {
                "baseline_caption": selected_caption,
                "selected_caption_index": caption_index,
            }
        )
    elif phase == "step_3":
        payload.update(
            {
                "selected_caption_index": caption_index,
                "selected_caption": selected_caption,
            }
        )
    else:
        raise ValueError(f"Unsupported phase: {phase}")
    return payload


def _batch_stimuli(step_1_trials: int, step_2_trials: int, step_3_trials: int, seed_value: str | None) -> dict[str, Any]:
    rng = _make_rng(seed_value)
    rows = _load_stimuli()
    shuffled_rows = rows[:]
    rng.shuffle(shuffled_rows)
    
    # Load historical ratings for weighted caption selection in Step 2/3
    history = _load_rating_history()
    caption_weights = _build_caption_weights(history, rows)
    
    total_trials = step_1_trials + step_2_trials + step_3_trials
    selected_rows = _pick_rows(shuffled_rows, total_trials, rng)

    batches = {
        "step_1": [],
        "step_2": [],
        "step_3": [],
    }

    cursor = 0
    for trial_index in range(step_1_trials):
        batches["step_1"].append(_build_trial_payload("step_1", selected_rows[cursor], trial_index, rng))
        cursor += 1
    for trial_index in range(step_2_trials):
        payload = _build_trial_payload("step_2", selected_rows[cursor], trial_index, rng)
        audio_file = selected_rows[cursor].audio_file
        baseline_caption = _pick_caption_for_step2_or_3(audio_file, selected_rows[cursor], caption_weights, rng)
        payload["baseline_caption"] = baseline_caption
        batches["step_2"].append(payload)
        cursor += 1
    for trial_index in range(step_3_trials):
        payload = _build_trial_payload("step_3", selected_rows[cursor], trial_index, rng)
        audio_file = selected_rows[cursor].audio_file
        baseline_caption = _pick_caption_for_step2_or_3(audio_file, selected_rows[cursor], caption_weights, rng)
        payload["baseline_caption"] = baseline_caption
        batches["step_3"].append(payload)
        cursor += 1
    
    return {
        "batch_id": uuid4().hex,
        "requested_trials": {
            "step_1": step_1_trials,
            "step_2": step_2_trials,
            "step_3": step_3_trials,
        },
        "stimuli": batches,
    }


def _append_local_row(record: dict[str, Any]) -> None:
    file_exists = LOCAL_LOG_PATH.exists()
    fieldnames = list(record.keys())
    with LOCAL_LOG_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


def append_submission_row(record: dict[str, Any]) -> None:
    """Append a submission row to Google Sheets when configured, otherwise keep a local CSV log.

    Expected environment variables:
    - GOOGLE_SHEETS_ID: target spreadsheet id
    - GOOGLE_SERVICE_ACCOUNT_JSON: either a JSON string or a path to a service account file
    - SUBMISSIONS_WORKSHEET: worksheet name, defaults to 'submissions'
    """

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    credentials_source = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    worksheet_name = os.getenv("SUBMISSIONS_WORKSHEET", "submissions")

    if not spreadsheet_id or not credentials_source:
        _append_local_row(record)
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        if Path(credentials_source).exists():
            credentials_info = json.loads(Path(credentials_source).read_text(encoding="utf-8"))
        else:
            credentials_info = json.loads(credentials_source)

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials = Credentials.from_service_account_info(credentials_info, scopes=scopes)
        client = gspread.authorize(credentials)
        worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        worksheet.append_row([record.get(key, "") for key in record.keys()])
    except Exception:
        _append_local_row(record)


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


@app.get("/api/health")
def health_check() -> Any:
    return jsonify({"ok": True})


@app.get("/api/get-stimuli")
def get_stimuli() -> Any:
    try:
        payload = _batch_stimuli(
            step_1_trials=STEP_1_TRIALS,
            step_2_trials=STEP_2_TRIALS,
            step_3_trials=STEP_3_TRIALS,
            seed_value=request.args.get("seed"),
        )
        payload["prolific_context"] = {
            "prolific_id": request.args.get("prolific_id", ""),
            "study_id": request.args.get("study_id", ""),
            "session_id": request.args.get("session_id", ""),
        }
        return jsonify(payload)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Failed to prepare stimuli: {exc}"}), 500


@app.post("/api/submit-response")
def submit_response() -> Any:
    payload = request.get_json(silent=True) or {}
    print(payload)
    phase = payload.get("phase")
    if phase not in {"step_1", "step_2", "step_3"}:
        return jsonify({"error": "phase must be one of step_1, step_2, or step_3"}), 400

    participant_context = payload.get("participant_context") or {}
    stimulus = payload.get("stimulus") or {}
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "timestamp": timestamp,
        "phase": phase,
        "prolific_id": _clean_value(participant_context.get("prolific_id")),
        "study_id": _clean_value(participant_context.get("study_id")),
        "session_id": _clean_value(participant_context.get("session_id")),
        "age_range": _clean_value(participant_context.get("age_range")),
        "experience_in_audio": _clean_value(participant_context.get("experience_in_audio")),
        "batch_id": _clean_value(payload.get("batch_id")),
        "trial_index": _clean_value(payload.get("trial_index")),
        "rir_id": _clean_value(stimulus.get("rir_id")),
        "audio_file": _clean_value(stimulus.get("audio_file")),
        "audio_file_path": _clean_value(stimulus.get("audio_file_path")),
        "selected_caption_index": _clean_value(stimulus.get("selected_caption_index")),
        "selected_caption_text": _clean_value(stimulus.get("selected_caption")) or _clean_value(stimulus.get("baseline_caption")),
        "edited_text": _clean_value(payload.get("edited_text")),
        "generated_text": _clean_value(payload.get("generated_text")),
        "raw_text": _clean_value(payload.get("raw_text")),
        "response_text": _clean_value(payload.get("response_text")),
        "grammar_rating": _clean_value(payload.get("grammar_rating")),
        "accuracy_rating": _clean_value(payload.get("accuracy_rating")),
    }

    if phase == "step_1" and not (record["generated_text"] or record["raw_text"] or record["response_text"]):
        return jsonify({"error": "step_1 submissions require generated_text, raw_text, or response_text"}), 400
    if phase == "step_2" and not (record["edited_text"] or record["response_text"]):
        return jsonify({"error": "step_2 submissions require edited_text or response_text"}), 400
    if phase == "step_3" and not (record["grammar_rating"] and record["accuracy_rating"]):
        return jsonify({"error": "step_3 submissions require grammar_rating and accuracy_rating"}), 400

    append_submission_row(record)

    return jsonify({
        "ok": True,
        "phase": phase,
        "timestamp": timestamp,
        "stored_locally": not bool(os.getenv("GOOGLE_SHEETS_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
    })


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


if __name__ == "__main__":
    load_dotenv()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)