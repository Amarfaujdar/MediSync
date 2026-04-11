import sqlite3
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.data')
DB_PATH = os.path.join(DB_DIR, 'health_platform.db')

def _get_connection():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            date_of_birth TEXT,
            gender TEXT,
            phone TEXT,
            email TEXT,
            blood_group TEXT,
            allergies TEXT,
            emergency_contact TEXT,
            chronic_conditions TEXT,
            insurance_provider TEXT,
            insurance_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            filepath TEXT,
            filename TEXT,
            document_type TEXT,
            status TEXT DEFAULT 'Pending' CHECK(status IN ('Pending', 'Processing', 'Completed', 'Failed')),
            extracted_text TEXT,
            extracted_json TEXT,
            body_map TEXT,
            sensitivity_level TEXT DEFAULT 'normal' CHECK(sensitivity_level IN ('normal', 'restricted')),
            tags TEXT DEFAULT '[]',
            date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS timeline_events (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            event_date TIMESTAMP,
            event_type TEXT,
            title TEXT,
            description TEXT,
            doc_id TEXT,
            source_page_img TEXT,
            is_verified BOOLEAN DEFAULT FALSE,
            sensitivity_level TEXT DEFAULT 'normal' CHECK(sensitivity_level IN ('normal', 'restricted')),
            tags TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS medications (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            doc_id TEXT,
            med_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            duration TEXT,
            purpose TEXT,
            precautions TEXT,
            side_effects TEXT,
            status TEXT DEFAULT 'Current' CHECK(status IN ('Current', 'Past')),
            is_verified BOOLEAN DEFAULT FALSE,
            sensitivity_level TEXT DEFAULT 'normal' CHECK(sensitivity_level IN ('normal', 'restricted')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS lab_results (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            doc_id TEXT,
            test_name TEXT NOT NULL,
            result_value TEXT,
            reference_range TEXT,
            unit TEXT,
            is_abnormal BOOLEAN DEFAULT FALSE,
            tested_on TEXT,
            sensitivity_level TEXT DEFAULT 'normal' CHECK(sensitivity_level IN ('normal', 'restricted')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS share_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT,
            recipient_name TEXT NOT NULL,
            recipient_type TEXT DEFAULT 'Doctor',
            permissions TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_revoked BOOLEAN DEFAULT FALSE,
            view_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS blockchain_records (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            transaction_id TEXT,
            ipfs_uri TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (doc_id) REFERENCES documents(id),
            FOREIGN KEY (patient_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS access_permissions (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            granted_to TEXT NOT NULL,
            doc_id TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'revoked')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users(id),
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            accessed_by TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS follow_ups (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            doc_id TEXT,
            title TEXT NOT NULL,
            doctor_name TEXT,
            hospital TEXT,
            follow_up_date TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'completed', 'missed')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS cache_store (
            cache_key TEXT PRIMARY KEY,
            cache_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        demo_user_id = str(uuid.uuid4())
        c.execute('''
            INSERT INTO users (id, name, date_of_birth, gender, phone, email,
                               blood_group, allergies, emergency_contact, chronic_conditions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (demo_user_id, 'Jane Doe', '1985-04-12', 'Female',
              '+1 (555) 234-5678', 'patient@email.com',
              'O+', 'Penicillin', 'John Doe: 555-0199', 'Hypertension'))

    conn.commit()
    conn.close()

def upgrade_db_schema():
    """Non-destructive migration: add new columns if they don't exist yet."""
    conn = _get_connection()
    c = conn.cursor()

    migrations = [
        ('users', 'date_of_birth', 'TEXT'),
        ('users', 'gender', 'TEXT'),
        ('users', 'phone', 'TEXT'),
        ('users', 'email', 'TEXT'),
        ('users', 'insurance_provider', 'TEXT'),
        ('users', 'insurance_id', 'TEXT'),
        ('documents', 'sensitivity_level', "TEXT DEFAULT 'normal'"),
        ('documents', 'body_map', 'TEXT'),
        ('documents', 'tags', "TEXT DEFAULT '[]'"),
        ('timeline_events', 'is_verified', 'BOOLEAN DEFAULT FALSE'),
        ('timeline_events', 'source_page_img', 'TEXT'),
        ('timeline_events', 'sensitivity_level', "TEXT DEFAULT 'normal'"),
        ('timeline_events', 'tags', "TEXT DEFAULT '[]'"),
        ('medications', 'is_verified', 'BOOLEAN DEFAULT FALSE'),
        ('medications', 'sensitivity_level', "TEXT DEFAULT 'normal'"),
        ('medications', 'is_cured', 'BOOLEAN DEFAULT FALSE'),
        ('medications', 'cured_at', 'TEXT'),
    ]

    for table, column, col_type in migrations:
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

def get_cache(key: str, ttl_hours: float = None) -> Optional[str]:
    """Get a cached value. If ttl_hours is set, returns None if the entry is older than that."""
    conn = _get_connection()
    c = conn.cursor()
    if ttl_hours is not None:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=ttl_hours)).isoformat()
        c.execute(
            'SELECT cache_value FROM cache_store WHERE cache_key = ? AND created_at > ?',
            (key, cutoff)
        )
    else:
        c.execute('SELECT cache_value FROM cache_store WHERE cache_key = ?', (key,))
    res = c.fetchone()
    conn.close()
    return res['cache_value'] if res else None

def set_cache(key: str, value: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO cache_store (cache_key, cache_value, created_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(cache_key) DO UPDATE SET cache_value=excluded.cache_value, created_at=CURRENT_TIMESTAMP
    ''', (key, value))
    conn.commit()
    conn.close()

def get_persistent_cache(user_id: str, cache_type: str) -> Optional[str]:
    """Retrieve a long-lived user-specific cache (summaries, predictions). No TTL expiry."""
    return get_cache(f"persistent_{cache_type}_{user_id}")

def set_persistent_cache(user_id: str, cache_type: str, value: str):
    """Store a long-lived, user-specific AI result that persists across server restarts."""
    set_cache(f"persistent_{cache_type}_{user_id}", value)

def get_demo_user_id() -> str:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM users LIMIT 1')
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def get_user(user_id: str) -> Dict[str, Any]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    res = c.fetchone()
    conn.close()
    return dict(res) if res else None

def update_user(user_id: str, name: str, date_of_birth: str, gender: str,
                phone: str, email: str, blood_group: str,
                allergies: str, chronic_conditions: str,
                insurance_provider: str = '', insurance_id: str = ''):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE users
        SET name=?, date_of_birth=?, gender=?, phone=?, email=?,
            blood_group=?, allergies=?, chronic_conditions=?,
            insurance_provider=?, insurance_id=?
        WHERE id=?
    ''', (name, date_of_birth, gender, phone, email,
          blood_group, allergies, chronic_conditions,
          insurance_provider, insurance_id, user_id))
    conn.commit()
    conn.close()

def insert_document(user_id: str, filepath: str, filename: str, doc_type: str = 'Unknown') -> str:
    conn = _get_connection()
    c = conn.cursor()
    doc_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO documents (id, user_id, filepath, filename, document_type, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (doc_id, user_id, filepath, filename, doc_type, 'Pending'))
    conn.commit()
    conn.close()
    return doc_id

def update_document_extraction(doc_id: str, extracted_text: str, extracted_json: str, status: str = 'Completed', body_map: str = None):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE documents
        SET extracted_text=?, extracted_json=?, body_map=?, status=?
        WHERE id=?
    ''', (extracted_text, extracted_json, body_map, status, doc_id))
    conn.commit()
    conn.close()

def set_document_sensitivity(doc_id: str, level: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('UPDATE documents SET sensitivity_level=? WHERE id=?', (level, doc_id))
    conn.commit()
    conn.close()

def get_documents(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM documents WHERE user_id=? ORDER BY date_uploaded DESC', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def get_events_by_doc(doc_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM timeline_events WHERE doc_id=?', (doc_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def get_medications_by_doc(doc_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM medications WHERE doc_id=?', (doc_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def insert_timeline_event(user_id: str, event_date: str, event_type: str,
                           title: str, description: str,
                           doc_id: str = None, source_page_img: str = None) -> str:
    conn = _get_connection()
    c = conn.cursor()
    event_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO timeline_events
            (id, user_id, event_date, event_type, title, description, doc_id, source_page_img)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (event_id, user_id, event_date, event_type, title, description, doc_id, source_page_img))
    conn.commit()
    conn.close()
    return event_id

def get_timeline(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT t.*, d.filename, d.filepath, d.document_type, d.extracted_json
        FROM timeline_events t
        LEFT JOIN documents d ON t.doc_id = d.id
        WHERE t.user_id=?
        ORDER BY t.event_date DESC
    ''', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def update_timeline_event(event_id: str, event_date: str, event_type: str, title: str, description: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE timeline_events
        SET event_date=?, event_type=?, title=?, description=?, is_verified=TRUE
        WHERE id=?
    ''', (event_date, event_type, title, description, event_id))
    conn.commit()
    conn.close()

def link_document_to_event(event_id: str, doc_id: str, source_page_img: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE timeline_events SET doc_id=?, source_page_img=? WHERE id=?
    ''', (doc_id, source_page_img, event_id))
    conn.commit()
    conn.close()

def set_event_sensitivity(event_id: str, level: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('UPDATE timeline_events SET sensitivity_level=? WHERE id=?', (level, event_id))
    conn.commit()
    conn.close()

def insert_medication(user_id: str, doc_id: str, med_name: str, dosage: str,
                       frequency: str, duration: str, purpose: str,
                       precautions: str, side_effects: str, status: str = 'Current') -> str:
    conn = _get_connection()
    c = conn.cursor()
    med_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO medications
            (id, user_id, doc_id, med_name, dosage, frequency, duration,
             purpose, precautions, side_effects, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (med_id, user_id, doc_id, med_name, dosage, frequency, duration,
          purpose, precautions, side_effects, status))
    conn.commit()
    conn.close()
    return med_id

def get_medications(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM medications WHERE user_id=?', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def update_medication(med_id: str, med_name: str, dosage: str, frequency: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE medications SET med_name=?, dosage=?, frequency=?, is_verified=TRUE WHERE id=?
    ''', (med_name, dosage, frequency, med_id))
    conn.commit()
    conn.close()

def insert_lab_result(user_id: str, doc_id: str, test_name: str,
                       result_value: str, reference_range: str, unit: str,
                       is_abnormal: bool, tested_on: str) -> str:
    conn = _get_connection()
    c = conn.cursor()
    lab_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO lab_results
            (id, user_id, doc_id, test_name, result_value, reference_range, unit, is_abnormal, tested_on)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lab_id, user_id, doc_id, test_name, result_value, reference_range, unit, is_abnormal, tested_on))
    conn.commit()
    conn.close()
    return lab_id

def get_lab_results(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM lab_results WHERE user_id=? ORDER BY tested_on DESC', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def create_share_token(user_id: str, recipient_name: str, recipient_type: str,
                        permissions: dict, expires_hours: int = 168) -> str:
    """Create a new share token. Returns the token string."""
    import json
    token = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO share_tokens (token, user_id, recipient_name, recipient_type, permissions, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (token, user_id, recipient_name, recipient_type, json.dumps(permissions), expires_at))
    conn.commit()
    conn.close()
    return token

def get_share_token(token: str) -> Optional[Dict[str, Any]]:
    """Fetch a share token row. Returns None if not found."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM share_tokens WHERE token=?', (token,))
    res = c.fetchone()
    conn.close()
    return dict(res) if res else None

def increment_token_view(token: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('UPDATE share_tokens SET view_count = view_count + 1 WHERE token=?', (token,))
    conn.commit()
    conn.close()

def list_share_tokens(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM share_tokens
        WHERE user_id=?
        ORDER BY created_at DESC
    ''', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def revoke_share_token(token: str, user_id: str) -> bool:
    """Revoke a token belonging to this user. Returns True if a row was updated."""
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE share_tokens SET is_revoked=TRUE
        WHERE token=? AND user_id=?
    ''', (token, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def insert_blockchain_record(doc_id: str, patient_id: str, document_hash: str, transaction_id: str, ipfs_uri: str) -> str:
    conn = _get_connection()
    c = conn.cursor()
    record_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO blockchain_records (id, doc_id, patient_id, document_hash, transaction_id, ipfs_uri)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (record_id, doc_id, patient_id, document_hash, transaction_id, ipfs_uri))
    conn.commit()
    conn.close()
    return record_id

def log_access(doc_id: str, accessed_by: str, action: str):
    conn = _get_connection()
    c = conn.cursor()
    log_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO audit_logs (id, doc_id, accessed_by, action)
        VALUES (?, ?, ?, ?)
    ''', (log_id, doc_id, accessed_by, action))
    conn.commit()
    conn.close()

def get_document_hash(doc_id: str) -> Optional[str]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT document_hash FROM blockchain_records WHERE doc_id=?', (doc_id,))
    res = c.fetchone()
    conn.close()
    return res['document_hash'] if res else None

def get_blockchain_metadata(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM blockchain_records WHERE doc_id=?', (doc_id,))
    res = c.fetchone()
    conn.close()
    return dict(res) if res else None

def get_audit_logs(doc_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM audit_logs WHERE doc_id=? ORDER BY timestamp DESC', (doc_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def get_follow_ups(user_id: str) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM follow_ups WHERE user_id=? ORDER BY follow_up_date ASC', (user_id,))
    res = [dict(r) for r in c.fetchall()]
    conn.close()
    return res

def insert_follow_up(user_id: str, title: str, follow_up_date: str,
                     doctor_name: str = '', hospital: str = '',
                     notes: str = '', doc_id: str = None) -> str:
    conn = _get_connection()
    c = conn.cursor()
    fu_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO follow_ups (id, user_id, doc_id, title, doctor_name, hospital, follow_up_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (fu_id, user_id, doc_id, title, doctor_name, hospital, follow_up_date, notes))
    conn.commit()
    conn.close()
    return fu_id

def update_follow_up(fu_id: str, title: str, follow_up_date: str,
                     doctor_name: str = '', hospital: str = '',
                     notes: str = '', status: str = 'scheduled'):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE follow_ups SET title=?, follow_up_date=?, doctor_name=?, hospital=?, notes=?, status=?
        WHERE id=?
    ''', (title, follow_up_date, doctor_name, hospital, notes, status, fu_id))
    conn.commit()
    conn.close()

def delete_follow_up(fu_id: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM follow_ups WHERE id=?', (fu_id,))
    conn.commit()
    conn.close()

def get_chat_history(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM chat_history WHERE user_id=?
        ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    res = list(reversed([dict(r) for r in c.fetchall()]))
    conn.close()
    return res

def append_chat_message(user_id: str, role: str, content: str):
    conn = _get_connection()
    c = conn.cursor()
    msg_id = str(uuid.uuid4())
    c.execute('''
        INSERT INTO chat_history (id, user_id, role, content)
        VALUES (?, ?, ?, ?)
    ''', (msg_id, user_id, role, content))
    conn.commit()
    conn.close()

def clear_chat_history(user_id: str):
    conn = _get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM chat_history WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()

def mark_medication_cured(med_id: str) -> bool:
    import datetime as dt
    conn = _get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE medications SET is_cured=TRUE, cured_at=?, status='Past'
        WHERE id=?
    ''', (dt.datetime.utcnow().isoformat(), med_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def mark_medication_active(med_id: str) -> bool:
    conn = _get_connection()
    c = conn.cursor()
    c.execute("UPDATE medications SET is_cured=FALSE, cured_at=NULL, status='Current' WHERE id=?", (med_id,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

init_db()
upgrade_db_schema()

def cleanup_duplicates():
    """Retroactively removes redundant medications, lab results, and follow-ups to keep sections clean."""
    conn = _get_connection()
    c = conn.cursor()
    

    c.execute('''
        DELETE FROM medications 
        WHERE rowid NOT IN (
            SELECT MAX(rowid) 
            FROM medications 
            GROUP BY user_id, LOWER(TRIM(med_name))
        )
    ''')
    

    c.execute('''
        DELETE FROM lab_results 
        WHERE rowid NOT IN (
            SELECT MAX(rowid) 
            FROM lab_results 
            GROUP BY user_id, LOWER(TRIM(test_name)), TRIM(result_value), tested_on
        )
    ''')
    

    c.execute('''
        DELETE FROM follow_ups 
        WHERE rowid NOT IN (
            SELECT MAX(rowid) 
            FROM follow_ups 
            GROUP BY user_id, LOWER(TRIM(title)), follow_up_date
        )
    ''')
    
    conn.commit()
    conn.close()
