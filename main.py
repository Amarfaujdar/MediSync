import os

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
import json
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from execution.database import (
    get_user, init_db, upgrade_db_schema,
    get_documents, insert_document, update_document_extraction,
    insert_timeline_event, insert_medication,
    get_timeline, get_medications,
    update_timeline_event, update_medication,
    link_document_to_event,
    get_events_by_doc, get_medications_by_doc,
    get_lab_results, insert_lab_result,
    create_share_token, get_share_token, list_share_tokens,
    revoke_share_token, increment_token_view, update_user,
    get_blockchain_metadata, get_audit_logs, log_access,
    get_follow_ups, insert_follow_up, update_follow_up, delete_follow_up,
    get_chat_history, append_chat_message, clear_chat_history,
    mark_medication_cured, mark_medication_active, cleanup_duplicates,
    get_cache, set_cache, get_persistent_cache, set_persistent_cache
)
import hashlib

from execution.auth import (

    create_patient_in_mongo, create_doctor_in_mongo,
    get_patient_by_identifier, get_doctor_by_email,
    get_patient_by_id, get_doctor_by_id,
    update_patient_refresh_token, update_doctor_refresh_token,
    update_patient_profile,
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    decode_token, check_mongo_connection,
    _mirror_patient_to_sqlite,

    get_current_user, get_current_user_optional,

    PatientSignupRequest, DoctorSignupRequest, LoginRequest,
    RefreshRequest, ChangePasswordRequest,
)

from execution.ocr_agent import prepare_images_from_file
from execution.extraction_agent import extract_structured_data
from execution.body_map_agent import build_body_map
from execution.health_score_agent import compute_health_score
from execution.prescription_agent import explain_medications
from execution.summary_agent import generate_doctor_summary
from execution.chat_agent import ask_health_assistant
from execution.prediction_agent import generate_health_predictions
from blockchain.agent.blockchain_agent import register_document_on_blockchain, verify_document_integrity

app = FastAPI(title="MediSync API")

from fastapi import Request as _Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(Exception)
async def _global_exception_handler(_req: _Request, exc: Exception):
    """Catch-all: return JSON error so the frontend can parse it."""
    import traceback
    detail = str(exc)
    print(f"[ERROR] Unhandled exception: {detail}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"success": False, "statusCode": 500, "message": detail, "errors": []}
    )

@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_req: _Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "statusCode": exc.status_code, "message": exc.detail, "errors": []}
    )

@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(_req: _Request, exc: RequestValidationError):
    errors = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"success": False, "statusCode": 422, "message": "Validation error", "errors": errors}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
upgrade_db_schema()

_COOKIE_OPTS = dict(
    httponly=True,
    samesite="strict",
    secure=os.getenv("NODE_ENV") == "production",
)

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie("access_token", access_token, **_COOKIE_OPTS)
    response.set_cookie("refresh_token", refresh_token, **_COOKIE_OPTS)

def _clear_auth_cookies(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

class EventUpdate(BaseModel):
    event_date: str
    event_type: str
    title: str
    description: str
    doc_id: Optional[str] = None
    source_page_img: Optional[str] = None

class MedUpdate(BaseModel):
    med_name: str
    dosage: str
    frequency: str

class ChatRequest(BaseModel):
    question: str

class UserUpdate(BaseModel):
    name: str
    date_of_birth: Optional[str] = ''
    gender: Optional[str] = ''
    phone: Optional[str] = ''
    email: Optional[str] = ''
    blood_group: Optional[str] = ''
    allergies: Optional[str] = ''
    chronic_conditions: Optional[str] = ''
    insurance_provider: Optional[str] = ''
    insurance_id: Optional[str] = ''

    dob: Optional[str] = ''

class ShareCreateRequest(BaseModel):
    recipient_name: str
    recipient_type: str = 'Doctor'
    permissions: Dict[str, bool]
    expires_hours: int = 168

class FollowUpCreate(BaseModel):
    title: str
    follow_up_date: str
    doctor_name: Optional[str] = ''
    hospital: Optional[str] = ''
    notes: Optional[str] = ''
    doc_id: Optional[str] = None

class FollowUpUpdate(BaseModel):
    title: str
    follow_up_date: str
    doctor_name: Optional[str] = ''
    hospital: Optional[str] = ''
    notes: Optional[str] = ''
    status: Optional[str] = 'scheduled'

@app.get("/auth/status")
async def auth_status():
    """Health-check: reports whether MongoDB is reachable."""
    mongo_ok = check_mongo_connection()
    return {
        "service": "MediSync API",
        "mongo": "connected" if mongo_ok else "unreachable",
        "status": "ok" if mongo_ok else "degraded",
    }

@app.post("/auth/patient/register", status_code=201)
async def patient_register(req: PatientSignupRequest, response: Response):
    """
    Register a new patient.
    Generates a unique Patient ID (P-{YEAR}-{NANOID}) and mirrors the user
    into the SQLite DB so all medical routes resolve immediately.
    Returns access + refresh tokens (also set as httpOnly cookies).
    """
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = create_patient_in_mongo(
        name=req.name, phone=req.phone, dob=req.dob,
        gender=req.gender, blood_group=req.blood_group,
        password=req.password, allergies=req.allergies or "",
        chronic_conditions=req.chronic_conditions or [],
        emergency_contact=req.emergency_contact,
    )

    access_token  = create_access_token(user["id"], role="patient")
    refresh_token = create_refresh_token(user["id"], role="patient")
    update_patient_refresh_token(user["id"], refresh_token)
    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "success"   : True,
        "statusCode": 201,
        "message"   : "Patient registered successfully",
        "data": {
            "user"         : user,
            "accessToken"  : access_token,
            "refreshToken" : refresh_token,
            "role"         : "patient",
        }
    }

@app.post("/auth/doctor/register", status_code=201)
async def doctor_register(req: DoctorSignupRequest, response: Response):
    """Register a new doctor."""
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = create_doctor_in_mongo(
        name=req.name, phone=req.phone, email=req.email,
        specialization=req.specialization, license_number=req.license_number,
        hospital=req.hospital or "", password=req.password,
    )

    access_token  = create_access_token(user["id"], role="doctor")
    refresh_token = create_refresh_token(user["id"], role="doctor")
    update_doctor_refresh_token(user["id"], refresh_token)
    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "success"   : True,
        "statusCode": 201,
        "message"   : "Doctor registered successfully",
        "data": {
            "user"         : user,
            "accessToken"  : access_token,
            "refreshToken" : refresh_token,
            "role"         : "doctor",
        }
    }

@app.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    """
    Unified login endpoint.
    - role="patient" → look up by patientId (P-YYYY-XXXXXX) OR phone number
    - role="doctor"  → look up by email address
    Returns user profile + access/refresh tokens (also set as httpOnly cookies).
    """
    role = req.role.lower()

    if role == "doctor":

        doc = get_doctor_by_email(req.identifier)
        if not doc:
            raise HTTPException(status_code=404, detail="No doctor account found with this email")
        if not verify_password(req.password, doc.get("password", "")):
            raise HTTPException(status_code=401, detail="Invalid password")
        user_id      = doc["_id"]
        access_token  = create_access_token(user_id, role="doctor")
        refresh_token = create_refresh_token(user_id, role="doctor")
        update_doctor_refresh_token(user_id, refresh_token)
        safe_user = get_doctor_by_id(user_id)
    else:

        doc = get_patient_by_identifier(req.identifier)
        if not doc:
            raise HTTPException(
                status_code=404,
                detail="No account found with this Patient ID or phone number"
            )
        if not verify_password(req.password, doc.get("password", "")):
            raise HTTPException(status_code=401, detail="Invalid password")
        user_id = doc["_id"]

        _mirror_patient_to_sqlite(
            user_id, doc.get("name", ""), doc.get("dob", ""), doc.get("gender", ""),
            doc.get("phone", ""), "", doc.get("bloodGroup", ""),
            doc.get("allergies", ""), ", ".join(doc.get("chronicConditions", []))
        )

        access_token  = create_access_token(user_id, role="patient")
        refresh_token = create_refresh_token(user_id, role="patient")
        update_patient_refresh_token(user_id, refresh_token)
        safe_user = get_patient_by_id(user_id)

    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "success"   : True,
        "statusCode": 200,
        "message"   : f"{role.capitalize()} logged in successfully",
        "data": {
            "user"         : safe_user,
            "accessToken"  : access_token,
            "refreshToken" : refresh_token,
            "role"         : role,
        }
    }

@app.post("/auth/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user)
):
    """Clear tokens from DB and cookies."""
    role = current_user.get("role", "patient")
    if role == "doctor":
        update_doctor_refresh_token(current_user["id"], None)
    else:
        update_patient_refresh_token(current_user["id"], None)
    _clear_auth_cookies(response)
    return {"success": True, "statusCode": 200, "message": "Logged out successfully", "data": {}}

@app.post("/auth/refresh")
async def refresh_token_endpoint(req: RefreshRequest, response: Response):
    """Issue a new access token using a valid refresh token."""
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role    = payload.get("role", "patient")
    user_id = payload["sub"]

    if role == "doctor":
        raw_user = get_doctor_by_id(user_id)
    else:
        raw_user = get_patient_by_id(user_id)

    stored_token = None
    try:
        from execution.auth import _USE_MONGO, _get_auth_conn
        if not _USE_MONGO:
            conn = _get_auth_conn()
            table = "auth_doctors" if role == "doctor" else "auth_patients"
            row = conn.execute(f"SELECT refreshToken FROM {table} WHERE id=?", (user_id,)).fetchone()
            conn.close()
            stored_token = row["refreshToken"] if row else None
        else:
            from execution.auth import get_doctors_collection, get_users_collection
            col_raw = get_doctors_collection() if role == "doctor" else get_users_collection()
            raw_doc = col_raw.find_one({"_id": user_id})
            stored_token = raw_doc.get("refreshToken") if raw_doc else None
    except Exception:
        stored_token = None

    if not raw_user or stored_token != req.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")

    new_access  = create_access_token(user_id, role=role)
    new_refresh = create_refresh_token(user_id, role=role)

    if role == "doctor":
        update_doctor_refresh_token(user_id, new_refresh)
        user = get_doctor_by_id(user_id)
    else:
        update_patient_refresh_token(user_id, new_refresh)
        user = get_patient_by_id(user_id)

    _set_auth_cookies(response, new_access, new_refresh)

    return {
        "success": True,
        "data"   : {"user": user, "accessToken": new_access, "refreshToken": new_refresh, "role": role}
    }

@app.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {"success": True, "data": {"user": current_user, "role": current_user.get("role", "patient")}}

@app.post("/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    """Change the authenticated user's password after verifying the current one."""
    role    = current_user.get("role", "patient")
    user_id = current_user["id"]

    try:
        from execution.auth import _USE_MONGO, _get_auth_conn
        stored_hash = None
        if not _USE_MONGO:
            conn = _get_auth_conn()
            table = "auth_doctors" if role == "doctor" else "auth_patients"
            row = conn.execute(f"SELECT password FROM {table} WHERE id=?", (user_id,)).fetchone()
            stored_hash = row["password"] if row else None
            
            if not stored_hash or not verify_password(req.current_password, stored_hash):
                conn.close()
                raise HTTPException(status_code=401, detail="Current password is incorrect")
                
            conn.execute(f"UPDATE {table} SET password=? WHERE id=?", (hash_password(req.new_password), user_id))
            conn.commit()
            conn.close()
        else:
            from execution.auth import get_doctors_collection, get_users_collection
            col = get_doctors_collection() if role == "doctor" else get_users_collection()
            doc = col.find_one({"_id": user_id})
            stored_hash = doc.get("password") if doc else None
            
            if not stored_hash or not verify_password(req.current_password, stored_hash):
                raise HTTPException(status_code=401, detail="Current password is incorrect")
                
            col.update_one({"_id": user_id}, {"$set": {"password": hash_password(req.new_password)}})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to change password")

    return {"success": True, "message": "Password changed successfully"}

@app.post("/api/v1/patient/register", status_code=201)
async def v1_patient_register(req: PatientSignupRequest, response: Response):
    return await patient_register(req, response)

@app.post("/api/v1/patient/login")
async def v1_patient_login(req: LoginRequest, response: Response):
    req.role = "patient"
    return await login(req, response)

@app.post("/api/v1/patient/logout")
async def v1_patient_logout(response: Response, current_user: dict = Depends(get_current_user)):
    return await logout(response, current_user)

@app.post("/api/v1/doctor/register", status_code=201)
async def v1_doctor_register(req: DoctorSignupRequest, response: Response):
    return await doctor_register(req, response)

@app.post("/api/v1/doctor/login")
async def v1_doctor_login(req: LoginRequest, response: Response):
    req.role = "doctor"
    return await login(req, response)

@app.get("/api/v1/patient/profile")
async def v1_patient_profile(current_user: dict = Depends(get_current_user)):
    return {"success": True, "statusCode": 200, "data": {"user": current_user, "role": "patient"}}

@app.put("/api/v1/patient/profile")
async def v1_update_patient_profile(
    data: dict,
    current_user: dict = Depends(get_current_user)
):
    from execution.auth import get_users_collection, get_patient_by_id
    col = get_users_collection()
    allowed = {"name", "phone", "dob", "gender", "bloodGroup", "emergencyContact",
               "allergies", "chronicConditions"}
    update_data = {k: v for k, v in data.items() if k in allowed}
    if update_data:
        col.update_one({"_id": current_user["id"]}, {"$set": update_data})
    return {"success": True, "data": {"user": get_patient_by_id(current_user["id"]), "role": "patient"}}

@app.get("/api/v1/doctor/profile")
async def v1_doctor_profile(current_user: dict = Depends(get_current_user)):
    return {"success": True, "statusCode": 200, "data": {"user": current_user, "role": "doctor"}}

@app.get("/api/v1/doctor/patient/{patient_id}")
async def v1_doctor_get_patient(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Doctors only")
    from execution.auth import get_users_collection, _safe_patient
    col = get_users_collection()
    doc = col.find_one({"patientId": patient_id.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Patient not found")

    safe = _safe_patient(doc)
    safe.pop("refreshToken", None)
    return {"success": True, "data": {"patient": safe}}

@app.get("/api/user")
async def api_get_user(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    u = get_user(user_id)
    if u and u.get('date_of_birth'):
        u['dob'] = u['date_of_birth']
    return u or current_user

@app.put("/api/user")
async def api_update_user(data: UserUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    dob = data.date_of_birth or data.dob or ''
    update_user(
        user_id, data.name, dob, data.gender,
        data.phone, data.email, data.blood_group,
        data.allergies, data.chronic_conditions,
        data.insurance_provider, data.insurance_id
    )
    

    try:
        from execution.auth import get_users_collection, _USE_MONGO
        if _USE_MONGO:
            col = get_users_collection()
            col.update_one(
                {"_id": user_id},
                {"$set": {
                    "name": data.name,
                    "dob": dob,
                    "gender": data.gender,
                    "phone": data.phone,
                    "email": data.email,
                    "blood_group": data.blood_group,
                    "allergies": data.allergies,
                    "chronic_conditions": data.chronic_conditions,
                    "insurance_provider": data.insurance_provider,
                    "insurance_id": data.insurance_id
                }}
            )
    except Exception:
        pass

    u = get_user(user_id)
    if u and u.get('date_of_birth'):
        u['dob'] = u['date_of_birth']
    return u

@app.get("/api/health_score")
async def api_health_score_underscored(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    all_events = get_timeline(user_id)
    unverified_count = sum(1 for e in all_events if not e.get('is_verified'))

    user = get_user(user_id)
    chronic = (user or {}).get('chronic_conditions', '') or \
              ", ".join(current_user.get("chronicConditions", []))
    conditions = [c.strip() for c in chronic.split(',') if c.strip()]

    lab_results = get_lab_results(user_id)
    meds = get_medications(user_id)

    cache_key = f"health_score_{hashlib.md5(repr((user_id, unverified_count, conditions, len(lab_results), len(meds))).encode()).hexdigest()}"
    cached = get_cache(cache_key)
    if cached:
        return json.loads(cached)

    score_data = compute_health_score(unverified_count, conditions, lab_results, len(meds))
    set_cache(cache_key, json.dumps(score_data))
    return score_data

@app.get("/api/predictions")
async def api_get_predictions(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    user = get_user(user_id) or current_user
    tl_events = get_timeline(user_id)
    meds = get_medications(user_id)
    labs = get_lab_results(user_id)

    cached = get_cache(f"persistent_preds_{user_id}", ttl_hours=48)
    if cached:
        return json.loads(cached)

    predictions = generate_health_predictions(user, tl_events, meds, labs)
    set_cache(f"persistent_preds_{user_id}", json.dumps(predictions))
    return predictions

@app.post("/api/cleanup")
async def api_cleanup_data(current_user: dict = Depends(get_current_user)):
    """Manually trigger the deduplication cleanup logic."""
    cleanup_duplicates()
    return {"status": "success", "message": "Redundant data removed from medications, labs, and follow-ups."}

@app.get("/api/bodymap")
async def api_bodymap(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    docs = get_documents(user_id)

    regions = {
        "head": {"conditions": [], "symptoms": []},
        "chest_lungs": {"conditions": [], "symptoms": []},
        "abdomen": {"conditions": [], "symptoms": []},
        "arms": {"conditions": [], "symptoms": []},
        "legs": {"conditions": [], "symptoms": []}
    }

    user = get_user(user_id)
    user_conds = (user or {}).get('chronic_conditions', '') or \
                  ", ".join(current_user.get("chronicConditions", []))
    if user_conds:
        for c in user_conds.split(','):
            cm = build_body_map({"diagnosis": c.strip()})
            for rk, rv in cm.items():
                regions[rk]['conditions'].extend([x for x in rv['conditions'] if x not in regions[rk]['conditions']])

    for doc in docs:
        bm = None
        if doc.get('body_map'):
            try:
                bm = json.loads(doc['body_map'])
            except Exception:
                pass
        elif doc.get('extracted_json'):
            try:
                extracted = json.loads(doc['extracted_json'])
                bm = build_body_map(extracted)
            except Exception:
                pass

        if bm:
            for r_key, r_data in bm.items():
                if r_key in regions:
                    for cond in r_data.get('conditions', []):
                        if cond not in regions[r_key]['conditions']:
                            regions[r_key]['conditions'].append(cond)
                    for sym in r_data.get('symptoms', []):
                        if sym not in regions[r_key]['symptoms']:
                            regions[r_key]['symptoms'].append(sym)

    return {"status": "success", "data": regions}

@app.get("/api/documents")
async def api_get_documents(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    docs = get_documents(user_id)
    for doc in docs:
        doc['events'] = get_events_by_doc(doc['id'])
        doc['medications'] = get_medications_by_doc(doc['id'])
        if doc.get('extracted_json'):
            try:
                doc['parsed'] = json.loads(doc['extracted_json'])
            except Exception:
                doc['parsed'] = {}
    return docs

@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]

    upload_dir = os.path.join(os.path.dirname(__file__), '.tmp')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    try:
        doc_id = insert_document(user_id, file_path, file.filename)

        bc_status = register_document_on_blockchain(doc_id, user_id, file_path)
        if bc_status.get("success"):
            print(f"Blockchain record created for {doc_id}: {bc_status['document_hash']}")
        images, extracted_text = prepare_images_from_file(file_path)

        page_filenames = []
        for i, img in enumerate(images):
            basename = os.path.splitext(file.filename)[0]
            page_name = f"{basename}_p{i}.jpg"
            page_path = os.path.join(upload_dir, page_name)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img.save(page_path, "JPEG")
            page_filenames.append(page_name)

        data = extract_structured_data(images, extracted_text)
        body_map_data = build_body_map(data, "")

        doc_type = data.get('document_type', 'Unknown Result')
        doc_date = data.get('date', '')
        doc_diag = data.get('diagnosis', '')
        source_page_idx = data.get('source_page')
        if source_page_idx is None:
            source_page_idx = 0
        primary_image = page_filenames[source_page_idx] if source_page_idx < len(page_filenames) else (page_filenames[0] if page_filenames else None)

        update_document_extraction(doc_id, "", json.dumps(data), 'Completed', json.dumps(body_map_data))

        title = f"{doc_type} from {data.get('doctor_name', 'Unknown Doctor') or 'Unknown Doctor'}"
        desc  = _build_rich_description(data)
        insert_timeline_event(user_id, doc_date, doc_type, title, desc, doc_id, primary_image)

        existing_meds = get_medications(user_id)
        existing_med_names = [m.get('med_name', '').lower().strip() for m in existing_meds if m.get('med_name')]

        meds = data.get('medications') or []
        for med in meds:
            med_name = med.get('med_name', '').strip()
            if med_name and med_name.lower() not in existing_med_names:
                insert_medication(
                    user_id=user_id, doc_id=doc_id, med_name=med_name,
                    dosage=med.get('dosage', ''), frequency=med.get('frequency', ''),
                    duration=med.get('duration', ''), purpose="", precautions="", side_effects=""
                )
                existing_med_names.append(med_name.lower())

        existing_labs = get_lab_results(user_id)
        labs = data.get('key_measurements') or []
        for lab in labs:
            test_name = lab.get('test_name', '').strip()
            val_str = str(lab.get('value', '')).strip()

            is_dup = any(
                el.get('test_name', '').strip().lower() == test_name.lower() and
                str(el.get('result_value', '')).strip() == val_str and
                el.get('tested_on', '') == doc_date
                for el in existing_labs
            )

            if test_name and not is_dup:
                insert_lab_result(
                    user_id=user_id, doc_id=doc_id, test_name=test_name,
                    result_value=val_str, reference_range="",
                    unit=lab.get('unit', ''),
                    is_abnormal=bool(lab.get('abnormal_flag', False)),
                    tested_on=doc_date
                )
                existing_labs.append({'test_name': test_name, 'result_value': val_str, 'tested_on': doc_date})

        existing_fus = get_follow_ups(user_id)
        follow_up_date = data.get('follow_up_date') or data.get('next_visit') or data.get('review_date')
        if follow_up_date:
            fu_date_str = str(follow_up_date).strip()
            fu_title = f"Follow-up: {doc_type}"
            is_fu_dup = any(
                ef.get('follow_up_date', '') == fu_date_str and ef.get('title', '') == fu_title
                for ef in existing_fus
            )
            if not is_fu_dup:
                insert_follow_up(
                    user_id=user_id, title=fu_title, follow_up_date=fu_date_str,
                    doctor_name=data.get('doctor_name', '') or '',
                    hospital=data.get('hospital', '') or '',
                    notes=f"Auto-extracted from uploaded document: {file.filename}",
                    doc_id=doc_id
                )

        return {"status": "success", "message": "Document processed", "data": data, "pages": page_filenames}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

def _build_rich_description(data: dict) -> str:
    """Build a comprehensive clinical description from AI-extracted document data."""
    parts = []
    diagnosis = (data.get('diagnosis') or '').strip()
    if diagnosis:
        parts.append(f"Diagnosis: {diagnosis}")
    hospital = (data.get('hospital') or '').strip()
    if hospital:
        parts.append(f"Facility: {hospital}")

    conclusions = (data.get('conclusions') or '').strip()
    if conclusions:
        parts.append(f"Conclusions: {conclusions}")

    radiology = (data.get('radiology_findings') or '').strip()
    if radiology:
        parts.append(f"Radiology Findings: {radiology}")

    tables = data.get('tabular_data') or []
    if tables:
        table_names = [t.get('table_name', 'Data Table') for t in tables if t.get('table_name')]
        if table_names:
            parts.append(f"Contains tables: {', '.join(table_names)}")

    meds = data.get('medications') or []
    if meds:
        med_names = [m.get('med_name', '') for m in meds if m.get('med_name')]
        if med_names:
            parts.append(f"Medications prescribed: {', '.join(med_names)}")
    labs = data.get('key_measurements') or []
    if labs:
        lab_items = []
        for l in labs[:6]:
            name = l.get('test_name', '')
            val  = l.get('value', '')
            unit = l.get('unit', '')
            flag = ' ⚠' if l.get('abnormal_flag') else ''
            if name:
                lab_items.append(f"{name}: {val} {unit}{flag}".strip())
        if lab_items:
            parts.append(f"Lab results — {'; '.join(lab_items)}")

    confidence = data.get('confidence_score', 1.0) or 1.0
    if confidence < 0.6:
        low_conf = data.get('low_confidence_text') or []
        if low_conf:
            snippet = '; '.join(str(t) for t in low_conf[:3])
            parts.append(f"Partial read: {snippet}")
        parts.append("Low extraction confidence — manual review recommended")

    doc_type = data.get('document_type', 'Document')
    return '. '.join(parts) if parts else f"Processed {doc_type}"

def _enrich_event(ev: dict) -> dict:
    """Parse extracted_json on a timeline event and attach structured sub-fields."""
    ev = dict(ev)
    ex_json_str = ev.pop('extracted_json', None)
    ex_data = {}
    if ex_json_str:
        try:
            ex_data = json.loads(ex_json_str)
        except Exception:
            pass
    ev['doctor_name']      = (ex_data.get('doctor_name') or '').strip()
    ev['hospital']         = (ex_data.get('hospital') or '').strip()
    ev['diagnosis']        = (ex_data.get('diagnosis') or '').strip()
    ev['confidence_score'] = ex_data.get('confidence_score')
    ev['medications_list'] = [
        {'name': m.get('med_name',''), 'dosage': m.get('dosage',''), 'frequency': m.get('frequency','')}
        for m in (ex_data.get('medications') or []) if m.get('med_name')
    ]
    ev['lab_tests_list'] = [
        {'name': l.get('test_name',''), 'value': l.get('value',''), 'unit': l.get('unit',''), 'abnormal': bool(l.get('abnormal_flag', False))}
        for l in (ex_data.get('key_measurements') or []) if l.get('test_name')
    ]
    src_img = ev.get('source_page_img')
    ev['source_image_url'] = f'/uploads/{src_img}' if src_img else None
    generic = {'Modified via Vault', 'Processed Prescription', 'Processed Visit Note',
                'Processed Unknown Result', 'Processed Lab Report', 'Processed Discharge Summary', ''}
    current_desc = (ev.get('description') or '').strip()
    if current_desc in generic and ex_data:
        ev['description'] = _build_rich_description(ex_data)
    return ev

@app.get("/api/timeline")
async def api_get_timeline(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    return _build_timeline_grouped(user_id)

def _build_timeline_grouped(user_id):
    events = get_timeline(user_id)
    grouped = {}
    for ev in events:
        ev = _enrich_event(ev)
        date_str = ev.get('event_date', '')
        year = date_str[:4] if date_str else 'Unknown'
        grouped.setdefault(year, []).append(ev)
    return grouped

@app.put("/api/timeline/{event_id}")
async def api_update_timeline(
    event_id: str, data: EventUpdate,
    current_user: dict = Depends(get_current_user)
):
    update_timeline_event(event_id, data.event_date, data.event_type, data.title, data.description)
    if data.doc_id is not None:
        link_document_to_event(event_id, data.doc_id, data.source_page_img)
    return {"status": "success"}

@app.get("/api/medications")
async def api_get_medications(current_user: dict = Depends(get_current_user)):
    return get_medications(current_user["id"])

@app.put("/api/medications/{med_id}")
async def api_update_med(
    med_id: str, data: MedUpdate,
    current_user: dict = Depends(get_current_user)
):
    update_medication(med_id, data.med_name, data.dosage, data.frequency)
    return {"status": "success"}

@app.post("/api/medications/explain")
async def api_explain_meds(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    meds = get_medications(user_id)
    if not meds:
        return {}
    meds_to_explain = [{"name": m['med_name'], "dosage": m['dosage']} for m in meds]
    return explain_medications(meds_to_explain)

@app.get("/api/lab-results")
async def api_get_lab_results(current_user: dict = Depends(get_current_user)):
    return get_lab_results(current_user["id"])

@app.get("/api/summary")
async def api_get_summary(
    bypass_cache: bool = False,
    current_user: dict = Depends(get_current_user)
):
    user_id   = current_user["id"]
    user_data = get_user(user_id) or current_user
    timeline  = get_timeline(user_id)
    meds      = get_medications(user_id)

    if not bypass_cache:
        cached = get_cache(f"persistent_summary_{user_id}", ttl_hours=24)
        if cached:
            return json.loads(cached)

    summary = generate_doctor_summary(dict(user_data), timeline, [dict(m) for m in meds])
    result  = {"summary": summary, "cached_at": datetime.utcnow().isoformat()}
    set_cache(f"persistent_summary_{user_id}", json.dumps(result))
    return result

@app.post("/api/chat")
async def api_chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_id   = current_user["id"]
    user_data = get_user(user_id) or current_user
    timeline  = get_timeline(user_id)
    meds      = get_medications(user_id)
    history   = get_chat_history(user_id, limit=12)
    append_chat_message(user_id, 'user', req.question)
    response = ask_health_assistant(
        dict(user_data), timeline, [dict(m) for m in meds],
        req.question, history
    )
    append_chat_message(user_id, 'assistant', response)
    return {"response": response}

@app.get("/api/chat/history")
async def api_chat_history(current_user: dict = Depends(get_current_user)):
    return get_chat_history(current_user["id"], limit=50)

@app.delete("/api/chat/history")
async def api_clear_chat(current_user: dict = Depends(get_current_user)):
    clear_chat_history(current_user["id"])
    return {"status": "cleared"}

@app.get("/api/health-score")
async def api_health_score_hyphenated(current_user: dict = Depends(get_current_user)):
    user_id   = current_user["id"]
    user_data = get_user(user_id) or current_user
    timeline  = get_timeline(user_id)
    meds      = get_medications(user_id)

    unverified    = sum(1 for ev in timeline if not ev.get("is_verified"))
    conditions_str = (user_data.get('chronic_conditions', '') or
                      ", ".join(current_user.get("chronicConditions", [])))

    cache_key = f"hp_score_{hashlib.md5(repr((user_id, unverified, conditions_str, len(meds))).encode()).hexdigest()}"
    cached = get_cache(cache_key)
    if cached:
        return json.loads(cached)

    base_score   = 100
    base_score  -= unverified * 2
    verify_pct   = max(0, 100 - unverified * 10)

    conditions    = [c.strip() for c in conditions_str.split(',') if c.strip()]
    base_score   -= len(conditions) * 5
    chronic_pct   = max(0, 100 - len(conditions) * 15)

    base_score -= len(meds) * 2
    med_pct     = max(0, 100 - len(meds) * 8)

    final_score = max(0, min(100, base_score))
    if final_score >= 85:
        status_txt, color = "Good Standing", "green"
    elif final_score >= 60:
        status_txt, color = "Needs Attention", "amber"
    else:
        status_txt, color = "High Risk", "red"

    res = {
        "overall_score": final_score,
        "status": status_txt,
        "status_color": color,
        "breakdown": [
            {"label": "Record Verification",  "pct": verify_pct,  "color": "green" if verify_pct  > 80 else "amber" if verify_pct  > 50 else "red"},
            {"label": "Chronic Management",    "pct": chronic_pct, "color": "green" if chronic_pct > 75 else "amber" if chronic_pct > 40 else "red"},
            {"label": "Medication Complexity", "pct": med_pct,     "color": "green" if med_pct     > 75 else "amber"},
        ]
    }
    set_cache(cache_key, json.dumps(res))
    return res

@app.get("/api/documents/{doc_id}/blockchain")
async def api_get_blockchain_meta(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    meta = get_blockchain_metadata(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="No blockchain record found.")

    docs = get_documents(current_user["id"])
    file_path = None
    for d in docs:
        if d['id'] == doc_id:
            file_path = d.get('filepath')
            break

    is_valid, msg = False, "File unavailable for verification"
    if file_path and os.path.exists(file_path):
        is_valid, msg = verify_document_integrity(doc_id, file_path)

    log_access(doc_id, "Patient (Self)", "Viewed Blockchain Integrity")

    return {
        "metadata": meta,
        "verification": {"is_valid": is_valid, "message": msg}
    }

@app.get("/api/documents/{doc_id}/audit-logs")
async def api_get_audit_logs(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    logs = get_audit_logs(doc_id)
    log_access(doc_id, "Patient (Self)", "Viewed Audit Logs")
    return {"logs": logs}

@app.post("/api/share/create")
async def api_share_create(
    req: ShareCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    token = create_share_token(
        user_id=user_id,
        recipient_name=req.recipient_name,
        recipient_type=req.recipient_type,
        permissions=req.permissions,
        expires_hours=req.expires_hours
    )
    share_url = f"/share/{token}"
    return {
        "token": token, "share_url": share_url,
        "expires_hours": req.expires_hours,
        "recipient_name": req.recipient_name,
        "recipient_type": req.recipient_type,
        "permissions": req.permissions
    }

@app.get("/api/share/list")
async def api_share_list(current_user: dict = Depends(get_current_user)):
    tokens = list_share_tokens(current_user["id"])
    result = []
    now = datetime.utcnow()
    for t in tokens:
        expires_at = datetime.fromisoformat(t['expires_at']) if t.get('expires_at') else None
        is_expired = expires_at and now > expires_at
        result.append({
            "token": t['token'],
            "recipient_name": t['recipient_name'],
            "recipient_type": t['recipient_type'],
            "permissions": json.loads(t['permissions']) if t.get('permissions') else {},
            "expires_at": t['expires_at'],
            "created_at": t['created_at'],
            "is_revoked": bool(t['is_revoked']),
            "is_expired": is_expired,
            "is_active": not bool(t['is_revoked']) and not is_expired,
            "view_count": t.get('view_count', 0),
            "share_url": f"/share/{t['token']}"
        })
    return result

@app.delete("/api/share/revoke/{token}")
async def api_share_revoke(token: str, current_user: dict = Depends(get_current_user)):
    ok = revoke_share_token(token, current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Token not found or not yours")
    return {"status": "revoked"}

@app.get("/api/share/{token}")
async def api_share_view(token: str):
    """
    Public endpoint — no auth needed.
    Returns filtered patient data based on the token's permissions.
    """
    row = get_share_token(token)
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found")

    expires_at = datetime.fromisoformat(row['expires_at']) if row.get('expires_at') else None
    if expires_at and datetime.utcnow() > expires_at:
        raise HTTPException(status_code=410, detail="This share link has expired")

    if bool(row['is_revoked']):
        raise HTTPException(status_code=410, detail="This share link has been revoked")

    increment_token_view(token)

    user_id     = row['user_id']
    permissions = json.loads(row['permissions']) if row.get('permissions') else {}
    user        = get_user(user_id) or {}

    def _age(dob_str):
        if not dob_str:
            return None
        try:
            dob = datetime.fromisoformat(dob_str)
            return (datetime.utcnow() - dob).days // 365
        except Exception:
            return None

    payload = {
        "meta": {
            "recipient_name": row['recipient_name'],
            "recipient_type": row['recipient_type'],
            "shared_at": row['created_at'],
            "expires_at": row['expires_at'],
            "permissions": permissions
        },
        "patient": {
            "name": user.get('name', ''),
            "age": _age(user.get('date_of_birth')),
            "gender": user.get('gender', ''),
            "blood_group": user.get('blood_group', ''),
            "allergies": user.get('allergies', ''),
            "phone": user.get('phone', ''),
            "email": user.get('email', ''),
        }
    }

    if permissions.get('conditions', False):
        payload['conditions'] = [
            c.strip() for c in (user.get('chronic_conditions') or '').split(',') if c.strip()
        ]

    if permissions.get('medications', False):
        all_meds = get_medications(user_id)
        payload['medications'] = [
            m for m in all_meds if m.get('sensitivity_level', 'normal') != 'restricted'
        ]

    if permissions.get('documents', False):
        all_docs = get_documents(user_id)
        enriched_docs = []
        for d in all_docs:
            if d.get('sensitivity_level', 'normal') == 'restricted':
                continue
            ex_data = {}
            if d.get('extracted_json'):
                try:
                    ex_data = json.loads(d['extracted_json'])
                except Exception:
                    pass
            enriched_docs.append({
                'id': d['id'], 'filename': d['filename'],
                'document_type': d.get('document_type') or ex_data.get('document_type', 'Document'),
                'date_uploaded': d.get('date_uploaded', ''),
                'doc_date': ex_data.get('date', ''),
                'status': d.get('status', ''),
                'doctor_name': ex_data.get('doctor_name', ''),
                'hospital': ex_data.get('hospital', ''),
                'diagnosis': ex_data.get('diagnosis', ''),
                'confidence': ex_data.get('confidence_score'),
            })
        payload['documents'] = enriched_docs

    if permissions.get('timeline', False):
        all_events = get_timeline(user_id)
        payload['timeline'] = [
            _enrich_event(ev) for ev in all_events
            if ev.get('sensitivity_level', 'normal') != 'restricted'
        ]

    if permissions.get('lab_tests', False):
        all_labs = get_lab_results(user_id)
        payload['lab_results'] = [
            lab for lab in all_labs
            if lab.get('sensitivity_level', 'normal') != 'restricted'
        ]

    return payload

@app.get("/share/{token}")
async def share_redirect(token: str):
    return RedirectResponse(url=f"/share_view.html?token={token}", status_code=302)

@app.get("/api/follow-ups")
async def api_get_follow_ups(current_user: dict = Depends(get_current_user)):
    return get_follow_ups(current_user["id"])

@app.post("/api/follow-ups")
async def api_create_follow_up(req: FollowUpCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    fu_id = insert_follow_up(
        user_id=user_id, title=req.title, follow_up_date=req.follow_up_date,
        doctor_name=req.doctor_name or '', hospital=req.hospital or '',
        notes=req.notes or '', doc_id=req.doc_id
    )
    return {"id": fu_id, "status": "created"}

@app.put("/api/follow-ups/{fu_id}")
async def api_update_follow_up(
    fu_id: str, req: FollowUpUpdate,
    current_user: dict = Depends(get_current_user)
):
    update_follow_up(
        fu_id=fu_id, title=req.title, follow_up_date=req.follow_up_date,
        doctor_name=req.doctor_name or '', hospital=req.hospital or '',
        notes=req.notes or '', status=req.status or 'scheduled'
    )
    return {"status": "updated"}

@app.delete("/api/follow-ups/{fu_id}")
async def api_delete_follow_up(fu_id: str, current_user: dict = Depends(get_current_user)):
    delete_follow_up(fu_id)
    return {"status": "deleted"}

@app.post("/api/medications/{med_id}/cure")
async def api_cure_medication(med_id: str, current_user: dict = Depends(get_current_user)):
    ok = mark_medication_cured(med_id)
    return {"status": "cured" if ok else "not_found"}

@app.post("/api/medications/{med_id}/reactivate")
async def api_reactivate_medication(med_id: str, current_user: dict = Depends(get_current_user)):
    ok = mark_medication_active(med_id)
    return {"status": "active" if ok else "not_found"}

upload_dir = os.path.join(os.path.dirname(__file__), '.tmp')
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
