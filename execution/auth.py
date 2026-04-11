"""
MediRecord Auth Module
======================
- PRIMARY: MongoDB-backed user store (when MONGO_URI is reachable)
- FALLBACK: SQLite auth tables (when MongoDB is unavailable — e.g. local dev without mongod)
- bcrypt password hashing via passlib
- JWT access + refresh tokens via python-jose
- FastAPI dependency: get_current_user / get_current_user_optional
- Patient IDs: P-{DOB_YEAR}-{6_CHAR_NANOID}
"""

import os

from dotenv import load_dotenv as _load_dotenv
_load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

import uuid
import random
import sqlite3
import json as _json
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

MONGO_URI          = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME      = os.getenv("MONGO_DB", "medirecord")
SECRET_KEY         = os.getenv("JWT_SECRET", "medirecord-super-secret-key-change-in-prod-2026")
ALGORITHM          = "HS256"
ACCESS_TOKEN_TTL   = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "60"))
REFRESH_TOKEN_TTL  = int(os.getenv("REFRESH_TOKEN_TTL_DAYS",   "30"))

_AUTH_DB_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.data')
_AUTH_DB_PATH = os.path.join(_AUTH_DB_DIR, 'auth.db')

def _get_auth_conn():
    os.makedirs(_AUTH_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_auth_db():
    conn = _get_auth_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS auth_patients (
            id TEXT PRIMARY KEY,
            patientId TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            dob TEXT NOT NULL,
            gender TEXT NOT NULL,
            bloodGroup TEXT NOT NULL,
            allergies TEXT DEFAULT '',
            chronicConditions TEXT DEFAULT '[]',
            password TEXT NOT NULL,
            emergencyContact TEXT DEFAULT '{}',
            refreshToken TEXT,
            role TEXT DEFAULT 'patient',
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS auth_doctors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            specialization TEXT NOT NULL,
            licenseNumber TEXT UNIQUE NOT NULL,
            hospital TEXT DEFAULT '',
            password TEXT NOT NULL,
            refreshToken TEXT,
            role TEXT DEFAULT 'doctor',
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

_init_auth_db()

_mongo_client = None
_USE_MONGO    = False

def _try_connect_mongo():
    global _mongo_client, _USE_MONGO
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        _mongo_client = client
        _USE_MONGO    = True
        print(f"[auth] MongoDB connected at {MONGO_URI}")
    except Exception as e:
        print(f"[auth] MongoDB unavailable ({e}). Using SQLite auth fallback.")
        _USE_MONGO = False

_try_connect_mongo()

def _get_mongo_db():
    return _mongo_client[MONGO_DB_NAME]

def get_users_collection():
    return _get_mongo_db()["patients"]

def get_doctors_collection():
    return _get_mongo_db()["doctors"]

def check_mongo_connection() -> bool:
    if not _USE_MONGO:
        return False
    try:
        _get_mongo_db().command("ping")
        return True
    except Exception:
        return False

_NANOID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def _nanoid(n=6) -> str:
    return "".join(random.choices(_NANOID_ALPHABET, k=n))

def _generate_patient_id(dob: str) -> str:
    try:
        year = str(datetime.fromisoformat(dob[:10]).year)
    except Exception:
        year = str(datetime.utcnow().year)
    return f"P-{year}-{_nanoid()}"

def _ensure_unique_patient_id(dob: str) -> str:
    for _ in range(10):
        pid = _generate_patient_id(dob)
        if _USE_MONGO:
            if not get_users_collection().find_one({"patientId": pid}):
                return pid
        else:
            conn = _get_auth_conn()
            c = conn.cursor()
            c.execute("SELECT id FROM auth_patients WHERE patientId=?", (pid,))
            exists = c.fetchone()
            conn.close()
            if not exists:
                return pid
    raise RuntimeError("Could not generate unique patient ID")

import hashlib
import bcrypt

def _pre_hash_password(plain: str) -> bytes:
    """
    bcrypt has a strict 72-byte limit. To completely remove this limit 
    and maintain security, we pre-hash the password with SHA-256 and encode it.
    """
    return hashlib.sha256(plain.encode('utf-8')).hexdigest().encode('utf-8')

def hash_password(plain: str) -> str:

    hashed_bytes = bcrypt.hashpw(_pre_hash_password(plain), bcrypt.gensalt(10))
    return hashed_bytes.decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pre_hash_password(plain), hashed.encode('utf-8'))
    except Exception:
        return False

def create_access_token(user_id: str, role: str = "patient") -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_TTL)
    return jwt.encode(
        {"sub": user_id, "role": role, "type": "access", "exp": expire, "iat": datetime.utcnow()},
        SECRET_KEY, algorithm=ALGORITHM
    )

def create_refresh_token(user_id: str, role: str = "patient") -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_TTL)
    return jwt.encode(
        {"sub": user_id, "role": role, "type": "refresh", "exp": expire,
         "iat": datetime.utcnow(), "jti": str(uuid.uuid4())},
        SECRET_KEY, algorithm=ALGORITHM
    )

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

def _mirror_patient_to_sqlite(user_id, name, dob, gender, phone, email,
                               blood_group, allergies, chronic_conditions):
    try:
        from execution.database import _get_connection
        conn = _get_connection()
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE id = ?', (user_id,))
        if not c.fetchone():
            c.execute('''
                INSERT INTO users
                    (id, name, date_of_birth, gender, phone, email, blood_group,
                     allergies, chronic_conditions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, dob, gender, phone, email,
                  blood_group, allergies, chronic_conditions))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[auth] SQLite medical mirror failed (non-fatal): {e}")

def create_patient_in_mongo(*, name, phone, dob, gender, blood_group,
                              password, allergies="", chronic_conditions=None,
                              emergency_contact=None) -> dict:
    chronic_conditions = chronic_conditions or []
    emergency_contact  = emergency_contact  or {}
    patient_id = _ensure_unique_patient_id(dob)
    user_id    = str(uuid.uuid4())
    now        = datetime.utcnow().isoformat()
    hashed     = hash_password(password)

    if _USE_MONGO:
        col = get_users_collection()
        if col.find_one({"phone": phone.strip()}):
            raise HTTPException(status_code=400, detail="Phone number already registered")
        doc = {
            "_id": user_id, "patientId": patient_id,
            "name": name.strip(), "phone": phone.strip(), "dob": dob,
            "gender": gender, "bloodGroup": blood_group,
            "allergies": allergies, "chronicConditions": chronic_conditions,
            "password": hashed, "emergencyContact": emergency_contact,
            "refreshToken": None, "role": "patient", "created_at": now,
        }
        col.insert_one(doc)
    else:

        conn = _get_auth_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM auth_patients WHERE phone=?", (phone.strip(),))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Phone number already registered")
        c.execute('''
            INSERT INTO auth_patients
                (id, patientId, name, phone, dob, gender, bloodGroup,
                 allergies, chronicConditions, password, emergencyContact, role, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (user_id, patient_id, name.strip(), phone.strip(), dob, gender, blood_group,
              allergies, _json.dumps(chronic_conditions), hashed,
              _json.dumps(emergency_contact), "patient", now))
        conn.commit()
        conn.close()

    _mirror_patient_to_sqlite(user_id, name, dob, gender, phone, "",
                               blood_group, allergies,
                               ", ".join(chronic_conditions) if isinstance(chronic_conditions, list) else chronic_conditions)

    return {
        "id": user_id, "patientId": patient_id, "name": name.strip(),
        "phone": phone.strip(), "dob": dob, "gender": gender,
        "bloodGroup": blood_group, "allergies": allergies,
        "chronicConditions": chronic_conditions,
        "emergencyContact": emergency_contact, "role": "patient",
    }

def get_patient_by_identifier(identifier: str) -> Optional[dict]:
    """Find patient by patientId (P-YYYY-XXXXXX) or phone number."""
    if _USE_MONGO:
        return get_users_collection().find_one({
            "$or": [{"patientId": identifier.upper()}, {"phone": identifier}]
        })
    conn = _get_auth_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM auth_patients WHERE patientId=? OR phone=?",
              (identifier.upper(), identifier))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["_id"] = d.pop("id")
        d["chronicConditions"] = _json.loads(d.get("chronicConditions") or "[]")
        d["emergencyContact"]  = _json.loads(d.get("emergencyContact")  or "{}")
        return d
    return None

def get_patient_by_id(user_id: str) -> Optional[dict]:
    if _USE_MONGO:
        doc = get_users_collection().find_one({"_id": user_id})
        return _safe_patient(doc) if doc else None
    conn = _get_auth_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM auth_patients WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d.pop("password", None)
        d.pop("refreshToken", None)
        d["chronicConditions"] = _json.loads(d.get("chronicConditions") or "[]")
        d["emergencyContact"]  = _json.loads(d.get("emergencyContact")  or "{}")
        return d
    return None

def update_patient_refresh_token(user_id: str, refresh_token: Optional[str]):
    if _USE_MONGO:
        get_users_collection().update_one(
            {"_id": user_id},
            {"$set": {"refreshToken": refresh_token, "updated_at": datetime.utcnow().isoformat()}}
        )
    else:
        conn = _get_auth_conn()
        conn.execute("UPDATE auth_patients SET refreshToken=? WHERE id=?", (refresh_token, user_id))
        conn.commit()
        conn.close()

def update_patient_profile(user_id: str, fields: dict) -> dict:
    if _USE_MONGO:
        fields["updated_at"] = datetime.utcnow().isoformat()
        get_users_collection().update_one({"_id": user_id}, {"$set": fields})
    else:
        allowed = {"name", "phone", "dob", "gender", "bloodGroup", "allergies", "chronicConditions"}
        for k, v in fields.items():
            if k in allowed:
                conn = _get_auth_conn()
                conn.execute(f"UPDATE auth_patients SET {k}=? WHERE id=?", (v, user_id))
                conn.commit()
                conn.close()
    return get_patient_by_id(user_id)

def _safe_patient(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    d.pop("password", None)
    d.pop("refreshToken", None)
    if "_id" in d:
        d["id"] = d.pop("_id")
    return d

def create_doctor_in_mongo(*, name, phone, email, specialization,
                            license_number, hospital="", password) -> dict:
    doctor_id = str(uuid.uuid4())
    now       = datetime.utcnow().isoformat()
    hashed    = hash_password(password)

    if _USE_MONGO:
        col = get_doctors_collection()
        if col.find_one({"email": email.lower().strip()}):
            raise HTTPException(status_code=400, detail="Email already registered")
        if col.find_one({"licenseNumber": license_number.strip()}):
            raise HTTPException(status_code=400, detail="License number already registered")
        doc = {
            "_id": doctor_id, "name": name.strip(), "phone": phone.strip(),
            "email": email.lower().strip(), "specialization": specialization,
            "licenseNumber": license_number.strip(), "hospital": hospital.strip(),
            "password": hashed, "refreshToken": None, "role": "doctor", "created_at": now,
        }
        col.insert_one(doc)
    else:
        conn = _get_auth_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM auth_doctors WHERE email=?", (email.lower().strip(),))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")
        c.execute("SELECT id FROM auth_doctors WHERE licenseNumber=?", (license_number.strip(),))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="License number already registered")
        c.execute('''
            INSERT INTO auth_doctors
                (id, name, phone, email, specialization, licenseNumber,
                 hospital, password, role, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (doctor_id, name.strip(), phone.strip(), email.lower().strip(), specialization,
              license_number.strip(), hospital.strip(), hashed, "doctor", now))
        conn.commit()
        conn.close()

    return {
        "id": doctor_id, "name": name.strip(), "phone": phone.strip(),
        "email": email.lower().strip(), "specialization": specialization,
        "licenseNumber": license_number.strip(), "hospital": hospital.strip(),
        "role": "doctor",
    }

def get_doctor_by_email(email: str) -> Optional[dict]:
    if _USE_MONGO:
        return get_doctors_collection().find_one({"email": email.lower().strip()})
    conn = _get_auth_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM auth_doctors WHERE email=?", (email.lower().strip(),))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["_id"] = d.pop("id")
        return d
    return None

def get_doctor_by_id(doctor_id: str) -> Optional[dict]:
    if _USE_MONGO:
        doc = get_doctors_collection().find_one({"_id": doctor_id})
        return _safe_doctor(doc) if doc else None
    conn = _get_auth_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM auth_doctors WHERE id=?", (doctor_id,))
    row = c.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d.pop("password", None)
        d.pop("refreshToken", None)
        return d
    return None

def update_doctor_refresh_token(doctor_id: str, refresh_token: Optional[str]):
    if _USE_MONGO:
        get_doctors_collection().update_one(
            {"_id": doctor_id},
            {"$set": {"refreshToken": refresh_token, "updated_at": datetime.utcnow().isoformat()}}
        )
    else:
        conn = _get_auth_conn()
        conn.execute("UPDATE auth_doctors SET refreshToken=? WHERE id=?", (refresh_token, doctor_id))
        conn.commit()
        conn.close()

def _safe_doctor(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    d.pop("password", None)
    d.pop("refreshToken", None)
    if "_id" in d:
        d["id"] = d.pop("_id")
    return d

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

async def get_current_user(
    request: Request,
    token_from_header: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(default=None),
) -> dict:
    """Resolve current authenticated user from Bearer header or httpOnly cookie."""
    token = token_from_header or access_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    role    = payload.get("role", "patient")
    user_id = payload["sub"]

    user = get_doctor_by_id(user_id) if role == "doctor" else get_patient_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_user_optional(
    request: Request,
    token_from_header: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Cookie(default=None),
) -> Optional[dict]:
    try:
        return await get_current_user(request, token_from_header, access_token)
    except HTTPException:
        return None

class PatientSignupRequest(BaseModel):
    name: str
    phone: str
    dob: str
    gender: str
    blood_group: str
    password: str
    allergies: Optional[str] = ""
    chronic_conditions: Optional[list] = []
    emergency_contact: Optional[dict] = None

class DoctorSignupRequest(BaseModel):
    name: str
    phone: str
    email: str
    specialization: str
    license_number: str
    hospital: Optional[str] = ""
    password: str

class LoginRequest(BaseModel):
    identifier: str
    password: str
    role: str = "patient"

class RefreshRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
