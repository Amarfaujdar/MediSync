

let cachedExplanations = null;
let activeShares = [];
let currentShareType = 'Doctor';
let currentUser = null;
let allPredictions = [];
let bodyMapData = null;

const REGION_KEYWORDS = {
    head:    ['migraine','headache','seizure','epilepsy','stroke','tinnitus','vertigo','anxiety','depression','sleep','insomnia','memory','cognitive','neurolog','brain','sinus','thyroid'],
    chest:   ['hypertension','blood pressure','heart','cardiac','cardio','asthma','lung','pulmonary','bronchitis','pneumonia','lvh','arrhythmia','angina','chest','palpitation','respiratory','copd','atrial'],
    abdomen: ['diabetes','gastritis','gerd','ibs','bowel','liver','kidney','renal','pancreas','ulcer','crohn','colitis','celiac','hepatitis','gallbladder','spleen','digestive','acid reflux','stomach','abdominal'],
    arms:    ['arthritis','carpal','shoulder','elbow','wrist','tennis','bursitis','rotator','arm','hand','neuropathy'],
    legs:    ['knee','hip','ankle','foot','varicose','dvt','peripheral','gout','plantar','leg','joint','osteoporosis','fracture','tendon']
};

const REGION_SYMPTOMS = {
    head:    [],
    chest:   [{ name: 'Exertional dyspnea', date: 'Sep 15, 2024', severity: 'mild' }],
    abdomen: [],
    arms:    [],
    legs:    []
};

const PRED_ACTIONS = {
    'Elevated Cardiovascular Risk': [
        { icon: '🩺', title: 'Schedule Cardiology Consult', desc: 'Book an appointment with a cardiologist within 30 days for comprehensive risk assessment.' },
        { icon: '💊', title: 'Review Medications', desc: 'Ensure all cardiovascular medications are current and properly dosed.' },
        { icon: '🏃', title: 'Lifestyle Modifications', desc: 'Reduce sodium intake, increase aerobic exercise to 150 min/week, and quit smoking if applicable.' },
        { icon: '🧪', title: 'Order Lipid Panel', desc: 'Get a fasting lipid panel to check LDL, HDL, and triglycerides.' }
    ],
    'Potential Drug Interaction': [
        { icon: '👨‍⚕️', title: 'Consult Pharmacist', desc: 'Ask your pharmacist to review all current medications for interactions.' },
        { icon: '📋', title: 'Bring Medication List', desc: 'Bring a complete list of all medications to your next doctor visit.' },
        { icon: '🔍', title: 'Monitor Blood Glucose', desc: 'Monitor blood glucose more frequently when taking Metformin + Amlodipine.' }
    ],
    'Annual Health Checkup Due': [
        { icon: '📅', title: 'Schedule Annual Physical', desc: 'Book your annual preventive physical exam with your primary care physician.' },
        { icon: '🧪', title: 'Routine Lab Work', desc: 'Request a complete metabolic panel, CBC, and lipid panel.' },
        { icon: '💉', title: 'Update Vaccinations', desc: 'Review and update vaccinations including flu, COVID-19 booster, and tetanus.' }
    ],
    'Overdue: Diabetic Foot Exam': [
        { icon: '👣', title: 'Foot Examination', desc: 'Schedule a diabetic foot exam with your endocrinologist or podiatrist.' },
        { icon: '👟', title: 'Proper Footwear', desc: 'Ensure you are wearing diabetic-appropriate footwear to prevent ulcers.' },
        { icon: '🔍', title: 'Daily Self-Inspection', desc: 'Inspect feet daily for cuts, blisters, or sores and report any issues promptly.' }
    ]
};

const originalFetch = window.fetch;
const LS_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

window.fetch = async function() {
    const url    = typeof arguments[0] === 'string' ? arguments[0] : null;
    const options = arguments[1] || {};
    const method  = (options.method || 'GET').toUpperCase();
    const isBypass = (options.headers && options.headers['X-Bypass-Cache']) ||
                     (url && url.includes('bypass_cache=true'));

    const isCacheable = url && url.startsWith('/api/') && method === 'GET' &&
                        !url.includes('chat') && !isBypass;

    if (isCacheable) {
        const cacheKey = 'medisync_cache_' + url;
        try {
            const cached = localStorage.getItem(cacheKey);
            if (cached) {
                const { data, ts } = JSON.parse(cached);
                if (Date.now() - ts < LS_CACHE_TTL_MS) {
                    return { ok: true, json: async () => JSON.parse(data), text: async () => data, clone: function() { return this; } };
                }
            }
        } catch(e) {  }
    }

    if (url && url.startsWith('/api/') && method !== 'GET') {
        Object.keys(localStorage).filter(k => k.startsWith('medisync_cache_')).forEach(k => localStorage.removeItem(k));
    }

    const res = await originalFetch.apply(this, arguments);

    if (isCacheable && res.ok) {
        const clone = res.clone();
        clone.text().then(text => {
            localStorage.setItem('medisync_cache_' + url, JSON.stringify({ data: text, ts: Date.now() }));
        }).catch(() => {});
    }
    return res;
};

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initHistoryTabs();
    initTimelineTabs();
    initPredictionFilters();
    loadUserProfile().then(() => loadDashboard());

    const fi = document.getElementById('file-input');
    if (fi) fi.addEventListener('change', handleFileUpload);

    const dz = document.getElementById('drop-zone');
    if (dz) {
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
        dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
        dz.addEventListener('drop', e => {
            e.preventDefault();
            dz.classList.remove('drag-over');
            if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
        });
    }

    const glBtn = document.getElementById('gen-link-btn');
    if (glBtn) glBtn.addEventListener('click', generateShareLink);

    const hs = document.getElementById('history-search');
    if (hs) hs.addEventListener('input', filterHistoryTable);

    const pb = document.getElementById('profile-btn');
    if (pb) {
        pb.addEventListener('click', async () => {
            if(confirm("Are you sure you want to log out?")) {
                try {
                    await fetch('/auth/logout', { method: 'POST' });
                } catch(e) {}

                Object.keys(localStorage).filter(k => k.startsWith('medisync_cache_')).forEach(k => localStorage.removeItem(k));
                window.location.href = '/auth.html';
            }
        });
    }
});

const PAGE_META = {
    'dashboard-view':   { title: 'Dashboard',        sub: 'Your health overview at a glance' },
    'vault-view':       { title: 'Upload Documents',  sub: 'Add medical records, reports, and prescriptions' },
    'history-view':     { title: 'Medical History',   sub: 'Complete record of conditions, medications, and procedures' },
    'timeline-view':    { title: 'Health Timeline',   sub: 'Chronological view of your medical journey' },
    'bodymap-view':     { title: 'Body Map',          sub: 'Interactive symptom and condition mapping' },
    'predictions-view': { title: 'Health Predictions',sub: 'AI-powered risk alerts and recommendations' },
    'sharing-view':     { title: 'Record Sharing',    sub: 'Securely share your health data with providers' },
    'settings-view':    { title: 'Settings',          sub: 'Account and platform preferences' },
};

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', e => {
            e.preventDefault();
            const target = e.currentTarget.dataset.target;
            if (target) navigateTo(target);
        });
    });
}

window.navigateTo = function(targetId, tabId) {

    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const btn = document.querySelector(`.nav-btn[data-target="${targetId}"]`);
    if (btn) btn.classList.add('active');

    document.querySelectorAll('.view-section').forEach(v => v.classList.add('hidden'));
    const section = document.getElementById(targetId);
    if (section) section.classList.remove('hidden');

    const meta = PAGE_META[targetId] || {};
    setText('topnav-title', meta.title || '');
    setText('topnav-sub', meta.sub || '');

    if (targetId === 'vault-view')       loadVault();
    if (targetId === 'timeline-view')    loadTimeline();
    if (targetId === 'history-view')     loadHistory();
    if (targetId === 'predictions-view') loadPredictions();
    if (targetId === 'sharing-view')     renderSharing();
    if (targetId === 'settings-view')    loadSettingsForm();
    if (targetId === 'bodymap-view')     setTimeout(() => selectRegion('chest'), 200);

    if (tabId) {
        setTimeout(() => {

            const ht = document.querySelector(`.history-tab[data-htab="${tabId}"]`);
            if (ht) { ht.click(); return; }
        }, 100);
    }
};

async function loadUserProfile() {
    try {
        const res = await fetch('/auth/me');
        if (res.status === 401) {
            window.location.href = '/auth.html';
            return;
        }
        
        const payload = await res.json();
        currentUser = payload.data ? payload.data.user : payload;
        
        if (!currentUser?.name) return;

        const init = initials(currentUser.name);
        setText('user-name', currentUser.name);
        setText('user-meta', `${currentUser.blood_group || '—'}  ·  ${genderAbbr(currentUser.gender)}`);
        setText('sidebar-avatar', init);
        setText('hero-avatar', init);
        setText('hero-name', currentUser.name);

        const agePart  = currentUser.dob ? `${calcAge(currentUser.dob)} years old` : '';
        const genPart  = currentUser.gender || '';
        const bloodPart= currentUser.blood_group ? `Blood Group: ${currentUser.blood_group}` : '';
        setText('hero-meta', [agePart, genPart, bloodPart].filter(Boolean).join(' · ') || 'MediSync Patient');

        renderTags('hero-allergies', splitCsv(currentUser.allergies), 'allergy');
        renderTags('hero-conditions', splitCsv(currentUser.chronic_conditions), 'condition');
    } catch (e) { console.warn('Profile load', e); }
}

function initials(name) {
    const parts = (name || '').trim().split(/\s+/);
    return parts.length >= 2
        ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
        : (name || '?')[0].toUpperCase();
}

function genderAbbr(g) {
    if (!g) return '';
    const m = { 'male': 'M', 'female': 'F', 'non-binary': 'NB' };
    return m[g.toLowerCase()] || g;
}

function calcAge(dob) {
    if (!dob) return '';
    const b = new Date(dob);
    const diff = Date.now() - b.getTime();
    return Math.floor(diff / 3.15576e10);
}

function splitCsv(val) { 
    if (Array.isArray(val)) return val.filter(Boolean);
    return (val || '').split(',').map(s => s.trim()).filter(Boolean); 
}

function renderTags(id, items, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = items.length
        ? items.map(i => `<span class="tag ${cls}">${esc(i)}</span>`).join('')
        : `<span style="opacity:.55;font-size:12px">None recorded</span>`;
}

async function loadDashboard() {
    try {
        const [docsRes, medsRes, tlRes, fuRes] = await Promise.all([
            fetch('/api/documents'), fetch('/api/medications'),
            fetch('/api/timeline'), fetch('/api/follow-ups')
        ]);
        const docs      = await docsRes.json();
        const meds      = await medsRes.json();
        const timeline  = await tlRes.json();
        const followUps = await fuRes.json();
        const events    = Object.values(timeline).flat();
        const unverified = events.filter(e => !e.is_verified).length;

        const conditions = splitCsv(currentUser?.chronic_conditions);
        setText('dash-stat-conditions', conditions.length || 0);
        setText('dash-stat-meds',  meds.filter(m => !m.is_cured).length);
        setText('dash-stat-docs',  docs.length);
        setText('dash-stat-alerts', unverified);

        if (unverified > 0) {
            const d = document.getElementById('notif-dot');
            if (d) { d.classList.remove('hidden'); d.textContent = unverified; }
        }

        renderDashMeds(meds.slice(0, 5));
        renderDashDocs(docs.slice(0, 4));
        renderDashAlerts(events, unverified);
        renderFollowUps(followUps);
        renderDashConditions(conditions);
    } catch (e) { console.warn('Dashboard', e); }
}

function renderDashMeds(meds) {
    const el = document.getElementById('dash-meds-list');
    if (!el) return;
    el.innerHTML = meds.length ? meds.map(m => `
        <div class="med-row">
          <div class="med-row-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 20H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H20a2 2 0 0 1 2 2v3"/><circle cx="18" cy="18" r="3"/></svg>
          </div>
          <div class="med-row-info">
            <strong>${esc(m.med_name)}<span class="med-dosage">${esc(m.dosage || '')}</span></strong>
            <p>${esc(m.frequency || 'Not specified')}</p>
          </div>
        </div>`).join('')
      : `<p class="empty-msg">No medications found.</p>`;
}

function renderDashDocs(docs) {
    const el = document.getElementById('dash-docs-list');
    if (!el) return;
    el.innerHTML = docs.length ? docs.map(d => `
        <div class="doc-row" onclick="navigateTo('vault-view')">
          <div class="doc-row-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div class="doc-row-info">
            <strong>${esc(d.filename)}</strong>
            <p>${(d.date_uploaded || '').substring(0, 10)} · Document</p>
          </div>
          <span class="badge-parsed">parsed</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--neutral-400)"><polyline points="9 18 15 12 9 6"/></svg>
        </div>`).join('')
      : `<p class="empty-msg">No documents uploaded yet.</p>`;
}

function renderDashAlerts(events, count) {
    const badge = document.getElementById('alert-badge');
    if (badge) {
        badge.textContent = count > 0 ? `${count} High` : 'All Clear';
        badge.className = count > 0 ? 'badge-high' : 'badge-success';
    }

    const el = document.getElementById('dash-alerts-list');
    if (!el) return;
    const unverified = events.filter(e => !e.is_verified).slice(0, 3);
    el.innerHTML = unverified.length ? unverified.map(ev => `
        <div class="alert-row">
          <div class="alert-dot high"></div>
          <div class="alert-content">
            <strong>${esc(ev.title || 'Unverified Record')}</strong>
            <p>${esc(ev.description || 'Please verify this record in the Timeline.')}</p>
          </div>
        </div>`).join('')
      : `<div class="alert-row">
           <div class="alert-dot low"></div>
           <div class="alert-content">
             <strong>All Records Verified</strong>
             <p>Your medical records are up to date and verified.</p>
           </div>
         </div>`;
}

function renderDashFollowups(events) {
    const el = document.getElementById('dash-followups-list');
    if (!el) return;
    const now = new Date();
    const future = events
        .filter(e => e.event_date && new Date(e.event_date) > now)
        .sort((a, b) => new Date(a.event_date) - new Date(b.event_date))
        .slice(0, 3);
    const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
    el.innerHTML = future.length ? future.map(ev => {
        const d = new Date(ev.event_date);
        return `<div class="followup-row">
          <div class="followup-date-box"><div class="fday">${d.getDate()}</div><div class="fmonth">${months[d.getMonth()]}</div></div>
          <div class="followup-info"><strong>${esc(ev.title)}</strong><p>${esc(ev.event_type || 'Appointment')}</p></div>
        </div>`;
    }).join('') : `<p class="empty-msg">No upcoming follow-ups.</p>`;
}

function renderDashConditions(conditions) {
    const el = document.getElementById('dash-conditions-list');
    if (!el) return;
    const colors   = ['amber','blue','green','red','violet'];
    const statuses = ['chronic','active','chronic','active','chronic'];
    el.innerHTML = conditions.length ? conditions.map((c, i) => `
        <div class="condition-card">
          <div class="condition-card-left">
            <span class="condition-dot ${colors[i % colors.length]}"></span>
            <div>
              <div class="condition-name">${esc(c)}</div>
            </div>
          </div>
          <span class="status-${statuses[i % statuses.length]}">${statuses[i % statuses.length]}</span>
        </div>`).join('')
      : `<p class="empty-msg">No conditions recorded.<br>Update your profile in Settings.</p>`;
}

async function loadVault() {
    try {
        const docs = await (await fetch('/api/documents')).json();
        setText('vault-count', `${docs.length} document${docs.length !== 1 ? 's' : ''}`);
        renderVaultList(docs);
    } catch (e) { console.warn('Vault', e); }
}

function renderVaultList(docs) {
    const c = document.getElementById('vault-list');
    if (!c) return;
    c.innerHTML = '';
    if (!docs?.length) {
        c.innerHTML = `<p class="empty-msg" style="padding:32px 0">Your document library is empty. Upload your first document above.</p>`;
        return;
    }
    docs.forEach(doc => {
        const item = document.createElement('div');
        item.className = 'vault-item';
        item.onclick = () => showDocPreview(doc);
        item.innerHTML = `
          <div class="vault-item-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <div class="vault-item-info">
            <strong>${esc(doc.filename)}</strong>
            <p>${(doc.date_uploaded || '').substring(0, 10)}</p>
          </div>
          <svg class="vault-item-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`;
        c.appendChild(item);
    });
}

function showDocPreview(doc) {
    const panel = document.getElementById('doc-preview-panel');
    if (!panel) return;

    const events = doc.events || [];
    const meds   = doc.medications || [];

    panel.innerHTML = `
      <div class="card-header" style="margin-bottom:12px">
        <div class="card-header-left">
          <svg class="card-icon green" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <div>
            <h3 class="card-title" style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px">${esc(doc.filename)}</h3>
            <p class="card-subtitle-text">${(doc.date_uploaded || '').substring(0, 10)}</p>
          </div>
        </div>
        <span class="badge-parsed">Processed</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <p class="section-micro-label">EXTRACTED EVENTS (${events.length})</p>
        ${events.length ? events.map(ev => `
          <div style="border:1px solid var(--neutral-200);border-radius:var(--radius);padding:12px;font-size:12.5px">
            <div style="font-weight:600;color:var(--neutral-800);margin-bottom:4px">${esc(ev.title || 'Event')}</div>
            <div style="color:var(--neutral-500)">${esc(ev.event_date || '—')} · ${esc(ev.event_type || '')}</div>
          </div>`).join('') : `<p style="font-size:12px;color:var(--neutral-400)">No events extracted.</p>`}
        ${meds.length ? `
          <p class="section-micro-label" style="margin-top:8px">MEDICATIONS (${meds.length})</p>
          ${meds.map(m => `
            <div style="border:1px solid var(--neutral-200);border-radius:var(--radius);padding:12px;font-size:12.5px">
              <div style="font-weight:600;color:var(--neutral-800)">${esc(m.med_name)}</div>
              <div style="color:var(--neutral-500)">${esc(m.dosage || '')} · ${esc(m.frequency || '')}</div>
            </div>`).join('')}` : ''}
      </div>`;
}

async function handleFileUpload(e) {
    const f = e.target.files[0];
    if (f) { await uploadFile(f); e.target.value = ''; }
}

async function uploadFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    const bar = document.getElementById('upload-status');
    if (bar) bar.classList.remove('hidden');
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: 'Unknown server error' }));
            throw new Error(err.error || err.detail || 'Server returned ' + res.status);
        }
        await loadVault();
        await loadDashboard();
    } catch (e) { alert('Upload failed: ' + e.message); }
    finally { if (bar) bar.classList.add('hidden'); }
}

let historyMeds = [];
let historyConditions = [];

function initHistoryTabs() {
    document.querySelectorAll('.history-tab[data-htab]').forEach(tab => {
        tab.addEventListener('click', () => {
            const parent = tab.closest('.card, .history-tab-bar')?.parentElement || document;
            tab.closest('.history-tabs').querySelectorAll('.history-tab').forEach(t => t.classList.remove('active'));
            parent.querySelectorAll('.htab-content').forEach(c => c.classList.add('hidden'));
            tab.classList.add('active');
            const el = document.getElementById(tab.dataset.htab);
            if (el) el.classList.remove('hidden');
        });
    });
}

async function loadHistory() {
    try {
        const [medsRes, labsRes, tlRes] = await Promise.all([
            fetch('/api/medications'),
            fetch('/api/lab-results'),
            fetch('/api/timeline')
        ]);
        
        historyMeds = await medsRes.json();
        const historyLabs = await labsRes.json();
        const groupedTimeline = await tlRes.json();
        historyConditions = splitCsv(currentUser?.chronic_conditions);

        setText('hist-stat-conditions', historyConditions.length);
        setText('hist-stat-meds', historyMeds.length);
        const labCount = historyLabs.length;
        setText('hist-stat-labs', labCount);

        setText('cond-count', historyConditions.length);
        setText('meds-count', historyMeds.length);
        setText('labs-count', labCount);

        renderConditionsTable(historyConditions);
        renderMedsGrid(historyMeds);
        renderLabTestsTable(historyLabs);

        const allEvents = Object.values(groupedTimeline).flat();
        const imagesHtml = allEvents.filter(ev => ev.source_page_img && ev.event_type !== 'Prescription' && ev.event_type !== 'Visit Note').map(ev => {
            const imgUrl = '/uploads/' + ev.source_page_img;
            return `<div style="border:1px solid var(--neutral-200);border-radius:8px;overflow:hidden;cursor:pointer;" onclick="openImagePreview('${imgUrl}')">
                      <img src="${imgUrl}" style="width:100%;height:120px;object-fit:cover;display:block;">
                      <div style="padding:8px;font-size:11px;font-weight:600;background:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(ev.title || 'Document')}</div>
                    </div>`;
        }).join('');
        const lrGrid = document.getElementById('lab-reports-images');
        if (lrGrid) lrGrid.innerHTML = imagesHtml || '<p class="empty-msg" style="grid-column:1/-1">No lab images or scans found.</p>';
        
    } catch (e) { console.warn('History', e); }
}

const conditionMeta = [
    { name: 'Type 2 Diabetes Mellitus', code: 'E11', since: 'Jun 2019', status: 'chronic', note: 'Well controlled with Metformin. HbA1c at 6.8%.' },
    { name: 'Essential Hypertension',   code: 'I10', since: 'Feb 2020', status: 'chronic', note: 'BP consistently around 128/82 on medication.' },
    { name: 'Mild Persistent Asthma',   code: 'J45.30', since: 'Sep 2015', status: 'active', note: 'Seasonal exacerbations. Well managed with inhaler.' },
    { name: 'Vitamin D Deficiency',     code: 'E55.9', since: 'Mar 2022', status: 'resolved', note: 'Resolved after 3 months of supplementation.' },
    { name: 'GERD',                     code: 'K21.0', since: 'Jul 2021', status: 'active', note: 'Managed with dietary changes and PPI.' },
];

function renderConditionsTable(conditions) {
    const tbody = document.getElementById('conditions-list');
    if (!tbody) return;

    const rows = conditions.length
        ? conditions.map((c, i) => {
            const meta = conditionMeta[i] || {};
            const statusClass = meta.status || 'active';
            return `<tr>
              <td>
                <span class="htrow-name">${esc(meta.name || c)}</span>
                ${meta.note ? `<span class="htrow-sub">${esc(meta.note)}</span>` : ''}
              </td>
              <td><span class="htrow-code">${esc(meta.code || '—')}</span></td>
              <td style="color:var(--neutral-600)">${esc(meta.since || '—')}</td>
              <td><span class="status-${statusClass}">${statusClass}</span></td>
            </tr>`;
          }).join('')
        : `<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--neutral-400);">No conditions recorded. Update your profile in Settings.</td></tr>`;

    tbody.innerHTML = rows;
    setText('hist-stat-conditions', conditions.length);
    setText('cond-count', conditions.length);
}

function renderLabTestsTable(labs) {
    const tbody = document.getElementById('labtests-list');
    if (!tbody) return;

    if (!labs || labs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:32px;color:var(--neutral-400)">No lab test records found.</td></tr>`;
        setText('hist-stat-labs', 0);
        setText('labs-count', 0);
        return;
    }

    tbody.innerHTML = labs.map(l => {
        const dateStr = l.tested_on ? new Date(l.tested_on).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
        const isFlagged = l.is_abnormal ? 'flagged' : 'normal';
        return `
        <tr>
          <td><span class="htrow-name">${esc(l.test_name)}</span></td>
          <td style="color:var(--neutral-600)">${esc(dateStr)}</td>
          <td style="font-weight:500;color:var(--neutral-800)">${esc(l.result_value)} ${esc(l.unit || '')}</td>
          <td><span class="status-${isFlagged}">${isFlagged}</span></td>
        </tr>`;
    }).join('');

    const count = labs.length;
    setText('hist-stat-labs', count);
    setText('labs-count', count);
}

function filterHistoryTable() {
    const q = (document.getElementById('history-search')?.value || '').toLowerCase();
    document.querySelectorAll('#conditions-list tr, #labtests-list tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
}

function renderMedsGrid(meds) {
    const el = document.getElementById('meds-grid');
    if (!el) return;
    el.innerHTML = '';
    if (!meds?.length) {
        el.innerHTML = `<p class="empty-msg" style="grid-column:1/-1">No medications found.</p>`;
        return;
    }
    meds.forEach((m, idx) => {
        const intelId = `intel-${idx}`;
      const isCured = !!m.is_cured;
        const card = document.createElement('div');
        card.className = `med-card${isCured ? ' cured' : ''}`;
        card.innerHTML = `
          <div class="med-card-header">
            <div class="med-name" title="${esc(m.med_name)}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M10.5 20H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H20a2 2 0 0 1 2 2v3"/><circle cx="18" cy="18" r="3"/></svg>
              <span class="med-name-text" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(m.med_name)}</span>
              ${isCured ? '<span class="cured-badge" style="margin-left:6px;flex-shrink:0;">✓ Cured</span>' : ''}
              <button class="btn icon-btn sm" onclick="openMedModal('${m.id}', '${esc(m.med_name)}', '${esc(m.dosage||'')}', '${esc(m.frequency||'')}')" title="Edit Medication" style="margin-left:auto;opacity:0.6;flex-shrink:0"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
            </div>
          </div>
          <div class="med-details">
            <div class="med-detail"><span>Dosage</span><span style="text-align:right">${esc(m.dosage || 'Unknown')}</span></div>
            <div class="med-detail"><span>Frequency</span><span style="text-align:right">${esc(m.frequency || 'Unknown')}</span></div>
            ${m.duration ? `<div class="med-detail"><span>Duration</span><span style="text-align:right">${esc(m.duration)}</span></div>` : ''}
            ${isCured && m.cured_at ? `<div class="med-detail"><span>Cured On</span><span style="color:var(--green-600);text-align:right">${new Date(m.cured_at).toLocaleDateString()}</span></div>` : ''}
          </div>
          <div class="med-actions" style="display:flex;gap:8px;margin-top:16px;padding-top:12px;border-top:1px solid var(--neutral-100);justify-content:space-between">
            ${!isCured ? `<button class="btn ghost sm" style="flex:1;justify-content:center;color:var(--green-600)" onclick="cureMedication('${m.id}','${esc(m.med_name)}')">✅ Mark Cured</button>` : `<button class="btn ghost sm" style="flex:1;justify-content:center;color:var(--blue-600)" onclick="reactivateMedication('${m.id}','${esc(m.med_name)}')">↩ Restore</button>`}
            <button class="btn ghost sm" style="flex:1;justify-content:center;color:var(--blue-600)" onclick="toggleIntel('${esc(m.med_name)}','${intelId}')">✨ AI Insight</button>
          </div>
          <div id="${intelId}" class="med-intel-panel">
            <div class="intel-grid">
              <div class="intel-section purpose"><h5>Purpose</h5><div class="shimmer"></div><div class="shimmer" style="width:70%"></div></div>
              <div class="intel-section usage"><h5>Usage</h5><div class="shimmer"></div></div>
              <div class="intel-section precautions"><h5>Precautions</h5><div class="shimmer"></div></div>
              <div class="intel-section side-effects"><h5>Side Effects</h5><div class="shimmer"></div></div>
            </div>
          </div>`;
        el.appendChild(card);
    });
    const activeMeds = meds.filter(m => !m.is_cured).length;
    setText('meds-count', meds.length);
    setText('hist-stat-meds', activeMeds);
}

async function toggleIntel(medName, panelId) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    if (panel.classList.contains('open')) { panel.classList.remove('open'); return; }
    document.querySelectorAll('.med-intel-panel').forEach(p => p.classList.remove('open'));
    panel.classList.add('open');

    // Retrieve history from local storage
    if (!cachedExplanations) {
        try {
            const saved = localStorage.getItem('medisync_ai_insights');
            cachedExplanations = saved ? JSON.parse(saved) : {};
        } catch(e) { cachedExplanations = {}; }
    }

    // If memory/cache doesn't have it, fetch from backend
    if (!cachedExplanations[medName]) {
        try { 
            const newInsights = await (await fetch('/api/medications/explain', { method: 'POST' })).json(); 
            cachedExplanations = { ...cachedExplanations, ...newInsights };
            // Save history
            localStorage.setItem('medisync_ai_insights', JSON.stringify(cachedExplanations));
        }
        catch (e) { panel.innerHTML = `<p style="color:var(--red-500);font-size:13px">Failed to reach AI service.</p>`; return; }
    }

    const exp = cachedExplanations[medName];
    // Render
    setTimeout(() => {
        panel.innerHTML = exp
            ? `<div class="intel-grid">
                <div class="intel-section purpose"><h5>Purpose</h5><p>${exp.purpose || 'Unavailable'}</p></div>
                <div class="intel-section usage"><h5>Usage Guidance</h5><p>${exp.usage || 'Refer to physician'}</p></div>
                <div class="intel-section precautions"><h5>Precautions</h5><p>${exp.precautions || 'None documented'}</p></div>
                <div class="intel-section side-effects"><h5>Side Effects</h5><p>${exp.side_effects || 'None broadly reported'}</p></div>
               </div>`
            : `<p style="color:var(--neutral-500);font-size:13px;text-align:center;padding:16px 0">No AI data for <strong>${esc(medName)}</strong>.</p>`;
    }, 150);
}

function initTimelineTabs() {
    document.querySelectorAll('.history-tab[data-ttab]').forEach(tab => {
        tab.addEventListener('click', () => {
            tab.closest('.history-tabs').querySelectorAll('.history-tab').forEach(t => t.classList.remove('active'));
            const section = document.getElementById('timeline-view');
            if (section) section.querySelectorAll('.htab-content').forEach(c => c.classList.add('hidden'));
            tab.classList.add('active');
            const el = document.getElementById(tab.dataset.ttab);
            if (el) el.classList.remove('hidden');
        });
    });
}

async function loadTimeline() {
    try {
        const [tlRes, docsRes] = await Promise.all([fetch('/api/timeline'), fetch('/api/documents')]);
        const grouped = await tlRes.json();
        const allDocs = await docsRes.json();
        window.vaultDocs = allDocs;

        window._eventStore = {};
        Object.values(grouped).flat().forEach(ev => {
            if (ev.id) window._eventStore[ev.id] = ev;
        });

        renderTimelineRows(grouped);
        renderFilteredTab(grouped, 'diagnoses-tab',  ev => {
            const t = (ev.event_type || '').toLowerCase();
            return t.includes('visit') || t.includes('consult') || t.includes('diagnos') || t.includes('condition');
        });
        renderFilteredTab(grouped, 'medications-tab', ev => {
            const t = (ev.event_type || '').toLowerCase();
            return t.includes('prescription') || t.includes('med') || t.includes('drug');
        });
        renderFilteredTab(grouped, 'tests-tab', ev => {
            const t = (ev.event_type || '').toLowerCase();
            return t.includes('lab') || t.includes('blood') || t.includes('test') || t.includes('scan') || t.includes('imaging') || t.includes('radiol') || t.includes('xray');
        });
        renderFilteredTab(grouped, 'documents-tab', ev => {
            const t = (ev.event_type || '').toLowerCase();
            return t.includes('document') || t.includes('upload') || t.includes('update') || t.includes('modif') || !!ev.source_page_img;
        });
    } catch (e) { console.warn('Timeline', e); }
}

function renderFilteredTab(grouped, containerId, filterFn) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    const filteredGrouped = {};
    const years = Object.keys(grouped).sort((a, b) => b - a);
    years.forEach(year => {
        const filtered = (grouped[year] || []).filter(filterFn);
        if (filtered.length) filteredGrouped[year] = filtered;
    });

    if (!Object.keys(filteredGrouped).length) {
        const labels = {
            'diagnoses-tab':  'No diagnosis or visit note events found.',
            'medications-tab': 'No prescription or medication events found.',
            'tests-tab':       'No lab test or imaging events found.',
            'documents-tab':   'No document events found.',
        };
        container.innerHTML = `<p class="empty-msg" style="padding:48px 0">${labels[containerId] || 'No events found.'}</p>`;
        return;
    }

    renderTimelineRows(filteredGrouped, containerId);
}

function renderTimelineRows(grouped, containerId) {
    const container = document.getElementById(containerId || 'all-events-tab');
    if (!container) return;
    container.innerHTML = '';

    const years = Object.keys(grouped).sort((a, b) => b - a);
    if (!years.length) {
        container.innerHTML = `<p class="empty-msg" style="padding:60px 0">No events yet. Upload a document to begin.</p>`;
        return;
    }

    years.forEach(year => {
        const events = grouped[year];

        const yh = document.createElement('div');
        yh.className = 'year-header';
        yh.innerHTML = `
          <span class="year-label">${year}</span>
          <span class="year-count">${events.length} event${events.length !== 1 ? 's' : ''}</span>`;
        container.appendChild(yh);

        events.forEach(ev => {
            const { emoji, color } = getEventIcon(ev.event_type);
            const badgeLabel = getBadgeLabel(ev.event_type);
            const imgUrl = ev.source_image_url || (ev.source_page_img ? `/uploads/${ev.source_page_img}` : null);
            const isUnverified = !ev.is_verified;
            const evId = ev.id || '';

            const row = document.createElement('div');
            row.className = `timeline-row${isUnverified ? ' tl-unverified' : ''}`;

            const leftCol = imgUrl
                ? `<div class="tl-thumbnail" onclick="event.stopPropagation();openImagePreview('${imgUrl}')">
                     <img src="${imgUrl}" alt="Source document">
                   </div>`
                : `<div class="tl-row-icon" style="background:${color}">${emoji}</div>`;

            const docMeta = (ev.doctor_name || ev.hospital)
                ? `<div class="tl-doc-meta">${ev.doctor_name ? `<span>👨‍⚕️ ${esc(ev.doctor_name)}</span>` : ''}${ev.hospital ? `<span>🏥 ${esc(ev.hospital)}</span>` : ''}</div>`
                : '';

            const diagHtml = ev.diagnosis
                ? `<div class="tl-diagnosis">🩺 ${esc(ev.diagnosis)}</div>` : '';

            const meds = ev.medications_list || [];
            const medsHtml = meds.length
                ? `<div class="tl-chips-row">${meds.slice(0, 5).map(m => `<span class="tl-chip tl-chip-med">💊 ${esc(m.name)}</span>`).join('')}</div>` : '';

            const labs = ev.lab_tests_list || [];
            const labsHtml = labs.length
                ? `<div class="tl-chips-row">${labs.slice(0, 4).map(l => `<span class="tl-chip ${l.abnormal ? 'tl-chip-abnormal' : 'tl-chip-lab'}">🧪 ${esc(l.name)}: ${esc(String(l.value))} ${esc(l.unit || '')}${l.abnormal ? ' ⚠' : ''}</span>`).join('')}</div>` : '';

            row.innerHTML = `
              ${leftCol}
              <div class="tl-row-info">
                <h4>${esc(ev.title || '[No Title]')}</h4>
                ${docMeta}
                ${diagHtml}
                <p class="tl-notes">${esc(ev.description || '')}</p>
                ${medsHtml}
                ${labsHtml}
                ${isUnverified ? `<span class="tl-conf-warn">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                  Unverified · Low confidence — Click Edit to fix
                </span>` : ''}
              </div>
              <div class="tl-row-meta">
                <span class="tl-row-date">${ev.event_date ? fmtDateMonth(ev.event_date) : ''}</span>
                ${badgeLabel ? `<span class="tl-type-badge tl-badge-${badgeLabel.cls}">${badgeLabel.text}</span>` : ''}
                <div style="display:flex;gap:6px;align-items:center;margin-top:6px;">
                  ${ev.source_page_img ? `
                  <button class="tl-edit-btn" title="View Source Image/Evidence" style="background:var(--neutral-800);color:#fff;border-color:var(--neutral-800);width:auto;padding:0 8px;font-size:11px;font-weight:600;" onclick="event.stopPropagation();openImagePreview('/uploads/${ev.source_page_img}')">
                    📄 View Evidence
                  </button>` : ''}
                  <button class="tl-edit-btn" title="Verify Blockchain Record" style="background:var(--blue-50);color:var(--blue-600);border-color:var(--blue-200);width:auto;padding:0 8px;font-size:11px;font-weight:600" onclick="event.stopPropagation();verifyDocument('${ev.doc_id}')">
                    🛡️ Verify
                  </button>
                  <button class="tl-edit-btn" title="Edit event" onclick="event.stopPropagation();openEditModal('${evId}')">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  </button>
                </div>
              </div>`;

            row.addEventListener('click', () => showEventDetail(ev));
            container.appendChild(row);
        });
    });
}

window.openImagePreview = function(imgUrl) {
    const html = `
      <div class="modal-overlay" id="img-preview-modal" onclick="if(event.target===this)closeImgPreview()" style="align-items:center">
        <div style="position:relative;max-width:700px;width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.3)">
          <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--neutral-200)">
            <h3 style="font-size:14px;font-weight:600;color:var(--neutral-800)">Source Document</h3>
            <button class="modal-close" onclick="closeImgPreview()">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <img src="${imgUrl}" style="width:100%;max-height:70vh;object-fit:contain;background:#f1f5f9;display:block">
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    requestAnimationFrame(() => document.getElementById('img-preview-modal')?.classList.add('visible'));
};

window.closeImgPreview = function() {
    const m = document.getElementById('img-preview-modal');
    if (!m) return;
    m.classList.remove('visible');
    setTimeout(() => m.remove(), 200);
};

window.verifyDocument = async function(docId) {
    if (!docId) {
        alert("This event is not linked to a blockchain-backed document.");
        return;
    }
    try {
        const res = await fetch(`/api/documents/${docId}/blockchain`);
        if (!res.ok) throw new Error("Verification failed or record not found");
        const data = await res.json();
        
        const v = data.verification;
        const m = data.metadata;
        const valid = v.is_valid;
        
        const html = `
          <div class="modal-overlay" id="vr-modal" onclick="if(event.target===this)this.remove()" style="align-items:center">
            <div style="background:#fff;border-radius:12px;width:100%;max-width:500px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.15);position:relative">
              <button onclick="document.getElementById('vr-modal').remove()" style="position:absolute;top:16px;right:16px;background:none;border:none;cursor:pointer;opacity:.6"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
              
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;border-bottom:1px solid var(--neutral-100);padding-bottom:16px">
                <div style="font-size:32px">${valid ? '✅' : '❌'}</div>
                <div>
                  <h3 style="margin:0;font-size:16px;color:var(--neutral-800)">Blockchain Integrity Check</h3>
                  <p style="margin:2px 0 0;font-size:13px;color:${valid ? 'var(--green-600)' : 'var(--red-600)'};font-weight:600">${v.message}</p>
                </div>
              </div>
              
              <div style="display:flex;flex-direction:column;gap:12px">
                <div>
                  <label style="display:block;font-size:11px;font-weight:700;color:var(--neutral-500);text-transform:uppercase;margin-bottom:4px">Stored Document Hash (SHA-256)</label>
                  <div style="font-family:monospace;font-size:11px;background:var(--neutral-50);padding:8px;border-radius:6px;word-break:break-all;color:var(--neutral-700)">${m.document_hash}</div>
                </div>
                <div>
                  <label style="display:block;font-size:11px;font-weight:700;color:var(--neutral-500);text-transform:uppercase;margin-bottom:4px">Blockchain Tx ID</label>
                  <div style="font-family:monospace;font-size:11px;background:var(--neutral-50);padding:8px;border-radius:6px;word-break:break-all;color:var(--neutral-700)">${m.transaction_id}</div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                  <div>
                    <label style="display:block;font-size:11px;font-weight:700;color:var(--neutral-500);text-transform:uppercase;margin-bottom:4px">Timestamp</label>
                    <div style="font-size:13px;color:var(--neutral-800)">${fmtDateMonth(m.timestamp)}</div>
                  </div>
                  <div>
                    <label style="display:block;font-size:11px;font-weight:700;color:var(--neutral-500);text-transform:uppercase;margin-bottom:4px">Off-Chain Storage</label>
                    <div style="font-size:13px;color:var(--blue-600);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${m.ipfs_uri}</div>
                  </div>
                </div>
              </div>
              
              <div style="margin-top:24px;background:var(--blue-50);border:1px solid var(--blue-200);border-radius:8px;padding:12px;font-size:12.5px;color:var(--blue-800);line-height:1.5">
                <strong>Proof of Immutability:</strong> The document integrity matches the immutable cryptographic seal recorded by the patient upon upload. Data is verifiably untampered.
              </div>
            </div>
          </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        requestAnimationFrame(() => document.getElementById('vr-modal')?.classList.add('visible'));
    } catch(e) {
        alert("Error checking blockchain verification: " + e.message);
    }
};

window.openEditModal = function(evId) {
    const ev = (window._eventStore || {})[evId];
    if (!ev && !evId) { alert('Event data not available.'); return; }

    const html = `
      <div class="modal-overlay" id="edit-event-modal" onclick="if(event.target===this)closeEditModal()">
        <div class="modal-box">
          <div class="modal-header">
            <div>
              <h3 class="modal-title">Edit Timeline Event</h3>
              <p class="modal-sub">Correct AI-extracted data with accurate information</p>
            </div>
            <button class="modal-close" onclick="closeEditModal()">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="modal-body" style="gap:14px">
            <div class="field-group">
              <label>TITLE</label>
              <input type="text" id="edit-ev-title" value="${esc(ev?.title || '')}" placeholder="e.g. Prescription from Dr. Sharma">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
              <div class="field-group">
                <label>DATE</label>
                <input type="date" id="edit-ev-date" value="${ev?.event_date || ''}">
              </div>
              <div class="field-group">
                <label>EVENT TYPE</label>
                <select id="edit-ev-type">
                  <option value="Prescription" ${ev?.event_type==='Prescription'?'selected':''}>Prescription</option>
                  <option value="Visit Note" ${ev?.event_type==='Visit Note'?'selected':''}>Visit Note</option>
                  <option value="Lab Test" ${ev?.event_type==='Lab Test'?'selected':''}>Lab Test</option>
                  <option value="Diagnosis" ${ev?.event_type==='Diagnosis'?'selected':''}>Diagnosis</option>
                  <option value="Surgery" ${ev?.event_type==='Surgery'?'selected':''}>Surgery</option>
                  <option value="Document" ${ev?.event_type==='Document'?'selected':''}>Document</option>
                  <option value="Other" ${(!ev?.event_type||!['Prescription','Visit Note','Lab Test','Diagnosis','Surgery','Document'].includes(ev.event_type))?'selected':''}>Other</option>
                </select>
              </div>
            </div>
            <div class="field-group">
              <label>NOTES / DESCRIPTION</label>
              <textarea id="edit-ev-desc" rows="3" style="border:1px solid var(--neutral-200);border-radius:var(--radius);padding:8px 12px;outline:none;resize:vertical;width:100%;font-size:13px;color:var(--neutral-800)">${esc(ev?.description || '')}</textarea>
            </div>
            ${ev?.source_page_img ? `
              <div>
                <p style="font-size:10.5px;font-weight:700;letter-spacing:.06em;color:var(--neutral-500);margin-bottom:6px">SOURCE DOCUMENT</p>
                <img src="/uploads/${esc(ev.source_page_img)}" style="width:100%;max-height:200px;object-fit:contain;border-radius:var(--radius);border:1px solid var(--neutral-200);background:var(--neutral-50)">
              </div>` : ''}
          </div>
          <div class="modal-footer">
            <button class="btn secondary" onclick="closeEditModal()">Cancel</button>
            <button class="btn primary" onclick="saveEventEdit('${evId}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              Save Changes
            </button>
          </div>
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    requestAnimationFrame(() => document.getElementById('edit-event-modal')?.classList.add('visible'));
};

window.closeEditModal = function() {
    const m = document.getElementById('edit-event-modal');
    if (!m) return;
    m.classList.remove('visible');
    setTimeout(() => m.remove(), 200);
};

window.saveEventEdit = async function(evId) {
    const title = document.getElementById('edit-ev-title')?.value?.trim();
    const date  = document.getElementById('edit-ev-date')?.value;
    const type  = document.getElementById('edit-ev-type')?.value;
    const desc  = document.getElementById('edit-ev-desc')?.value?.trim();

    if (!title) { alert('Please enter a title.'); return; }

    try {
        await fetch(`/api/timeline/${evId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_date: date, event_type: type, title, description: desc })
        });
        closeEditModal();
        await loadTimeline(); // Reload to reflect changes
    } catch (e) {
        alert('Failed to save: ' + e.message);
    }
};

function getEventIcon(type) {
    if (!type) return { emoji: '📋', color: 'var(--neutral-100)' };
    const t = type.toLowerCase();
    if (t.includes('prescription') || t.includes('med')) return { emoji: '💊', color: 'var(--blue-50)' };
    if (t.includes('lab') || t.includes('blood') || t.includes('test')) return { emoji: '🧪', color: 'var(--green-50)' };
    if (t.includes('visit') || t.includes('consult')) return { emoji: '🩺', color: 'var(--cyan-50)' };
    if (t.includes('surgery') || t.includes('proc')) return { emoji: '🔬', color: 'var(--red-50)' };
    if (t.includes('document')) return { emoji: '📄', color: 'var(--blue-50)' };
    return { emoji: '📋', color: 'var(--neutral-100)' };
}

function getBadgeLabel(type) {
    if (!type) return null;
    const t = type.toLowerCase();
    if (t.includes('prescription') || t.includes('med')) return { text: 'Prescription', cls: 'purple' };
    if (t.includes('visit') || t.includes('consult'))    return { text: 'Visit Note',    cls: 'blue' };
    if (t.includes('lab') || t.includes('blood') || t.includes('test')) return { text: 'Lab Test',  cls: 'green' };
    if (t.includes('update') || t.includes('modified'))  return { text: 'Updated',       cls: 'gray' };
    if (t.includes('document'))                           return { text: 'Document',      cls: 'blue' };
    return { text: type, cls: 'gray' };
}

function fmtDateMonth(str) {
    const d = new Date(str);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}`;
}

function showEventDetail(ev) {
    const panel = document.getElementById('event-detail-panel');
    if (!panel) return;
    const imgUrl = ev.source_page_img ? `/uploads/${ev.source_page_img}` : '';

    panel.innerHTML = `
      <div class="card-header" style="margin-bottom:12px">
        <div>
          <h3 class="card-title">${esc(ev.title || '[No Title]')}</h3>
          <p class="card-subtitle-text" style="margin-top:2px">${esc(ev.event_type || 'Event')}</p>
        </div>
        ${ev.is_verified ? `<span class="badge-success">✓ Verified</span>` : `<span class="badge-missing">Unverified</span>`}
      </div>
      ${imgUrl ? `
      <div style="position:relative;cursor:pointer;margin-bottom:12px;border-radius:var(--radius);overflow:hidden;" onclick="openImagePreview('${imgUrl}')" class="evidence-hover">
        <div style="position:absolute;top:6px;right:6px;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);color:#fff;font-size:10px;font-weight:700;padding:4px 8px;border-radius:12px;pointer-events:none;z-index:2">
          ⤢ Click to Enlarge
        </div>
        <img src="${imgUrl}" style="width:100%;object-fit:contain;max-height:220px;background:var(--neutral-100);display:block;">
      </div>` : ''}
      <div style="display:flex;flex-direction:column;gap:12px">
        <div>
          <p class="section-micro-label">DATE</p>
          <p style="font-size:13px;color:var(--neutral-700)">${ev.event_date ? fmtDateFull(ev.event_date) : '—'}</p>
        </div>
        <div>
          <p class="section-micro-label">TYPE</p>
          <p style="font-size:13px;color:var(--neutral-700)">${esc(ev.event_type || '—')}</p>
        </div>
        <div>
          <p class="section-micro-label">NOTES</p>
          <p style="font-size:13px;color:var(--neutral-600);line-height:1.5">${esc(ev.description || 'No notes.')}</p>
        </div>
      </div>`;
}

function fmtDate(str) {
    const d = new Date(str);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}`;
}

function fmtDateFull(str) {
    const d = new Date(str);
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

window.selectRegion = function(region) {

    document.querySelectorAll('.body-region-svg').forEach(r => r.classList.remove('active-region'));

    document.querySelectorAll(`.body-region-svg[data-region="${region}"]`).forEach(r => r.classList.add('active-region'));

    const titles = {
        head:    'Head & Brain',
        chest:   'Chest & Lungs',
        arms:    'Arms & Shoulders',
        abdomen: 'Abdomen & Digestive',
        legs:    'Legs & Joints'
    };

    setText('region-title', titles[region] || region);

    const backendRegion = region === 'chest' ? 'chest_lungs' : region;
    renderRegionContent(backendRegion);
};

async function renderRegionContent(region) {
    const el = document.getElementById('region-content');
    if (!el) return;

    if (!bodyMapData) {
        try {
            const res = await fetch('/api/bodymap');
            const data = await res.json();
            bodyMapData = data.data || {};

            for (const [rKey, rVal] of Object.entries(bodyMapData)) {
                if ((rVal.conditions && rVal.conditions.length > 0) || (rVal.symptoms && rVal.symptoms.length > 0)) {
                    const dot = document.getElementById(`indicator-${rKey}`);
                    if (dot) dot.style.display = 'block';
                }
            }
        } catch (e) {
            console.error('Failed to load body map data', e);
            bodyMapData = {};
        }
    }

    const regionData = bodyMapData[region] || { conditions: [], symptoms: [] };
    const matched = regionData.conditions || [];
    const symptoms = regionData.symptoms || [];
    const colors = ['amber','amber','blue','green','red'];

    let html = '<p class="section-micro-label">CONDITIONS</p>';
    if (matched.length) {
        matched.forEach((c, i) => {
            html += `<div class="condition-row"><span class="cond-dot ${colors[i % colors.length]}"></span>${esc(c)}</div>`;
        });
    } else {
        html += `<p style="font-size:12.5px;color:var(--neutral-400);padding:8px 0 4px">No conditions recorded for this region.</p>`;
    }

    html += '<p class="section-micro-label" style="margin-top:16px">SYMPTOMS</p>';
    if (symptoms.length) {
        symptoms.forEach(s => {
            html += `
              <div class="symptom-row">
                <span class="cond-dot green"></span>
                <div class="symptom-info">
                  <strong>${esc(s)}</strong>
                  <span>Extracted from documents</span>
                </div>
              </div>`;
        });
    } else {
        html += `<p style="font-size:12.5px;color:var(--neutral-400);padding:8px 0 4px">No symptoms recorded for this region.</p>`;
    }

    el.innerHTML = html;
};

function initPredictionFilters() {
    document.querySelectorAll('.chip[data-filter]').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            filterPredictions(chip.dataset.filter);
        });
    });
}

function filterPredictions(filter) {
    const cards = document.querySelectorAll('.prediction-card');
    cards.forEach(card => {
        if (filter === 'all') {
            card.style.display = '';
        } else {
            const type = card.dataset.type || '';
            const level = card.dataset.level || '';
            card.style.display = (type === filter || level === filter) ? '' : 'none';
        }
    });
}

async function loadPredictions(forceRefresh = false) {
    const el = document.getElementById('predictions-list');
    if (!el) return;

    const userId = currentUser?.id || 'default';
    const CACHE_KEY = `medisync_cache_preds_${userId}`;
    const SCORE_KEY = `medisync_cache_score_${userId}`;
    const CACHE_TTL_MS = 48 * 60 * 60 * 1000; // 48 hours

    if (!forceRefresh) {
        try {
            const raw = localStorage.getItem(CACHE_KEY);
            const scoreRaw = localStorage.getItem(SCORE_KEY);
            if (raw) {
                const { data, ts } = JSON.parse(raw);
                if (Date.now() - ts < CACHE_TTL_MS) {
                    allPredictions = data;
                    _renderPredictions(allPredictions, scoreRaw ? JSON.parse(scoreRaw).data : null);

                    const hint = document.createElement('div');
                    hint.style.cssText = 'text-align:center;padding:8px;font-size:12px;color:var(--neutral-400);';
                    const age = Math.round((Date.now() - ts) / 3600000);
                    hint.innerHTML = `Cached ${age}h ago &nbsp;·&nbsp; <a href="#" onclick="loadPredictions(true);return false;" style="color:var(--primary-600);">Refresh</a>`;
                    el.insertAdjacentElement('afterend', hint);
                    return;
                }
            }
        } catch(_) {}
    }

    try {
        el.innerHTML = '<div style="padding:40px;text-align:center"><div class="shimmer" style="height:100px;border-radius:12px;margin-bottom:16px;"></div><div class="shimmer" style="height:100px;border-radius:12px;"></div></div>';

        const [predsRes, scoreRes] = await Promise.all([
            fetch('/api/predictions'),
            fetch('/api/health_score')
        ]);

        allPredictions = await predsRes.json();
        const scoreData = await scoreRes.json();

        try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({ data: allPredictions, ts: Date.now() }));
            localStorage.setItem(SCORE_KEY, JSON.stringify({ data: scoreData,       ts: Date.now() }));
        } catch(_) {}

        _renderPredictions(allPredictions, scoreData);

    } catch (e) { console.warn('Predictions', e); }
}

function _renderPredictions(allPredictions, scoreData) {
    const el = document.getElementById('predictions-list');

    const old = el?.nextElementSibling;
    if (old && old.style?.textAlign === 'center' && old.textContent.includes('Cached')) old.remove();

    const criticals = allPredictions.filter(p => p.level === 'critical').length;
    const highs = allPredictions.filter(p => p.level === 'high').length;
    const mediums = allPredictions.filter(p => p.level === 'medium').length;
    const lows = allPredictions.filter(p => p.level === 'low').length;

    setText('pred-critical', criticals);
    setText('pred-high', highs);
    setText('pred-medium', mediums);
    setText('pred-low', lows);

    if (!allPredictions || allPredictions.length === 0) {
        el.innerHTML = '<p class="empty-msg">No predictions identified. You are looking healthy!</p>';
    } else {
        el.innerHTML = allPredictions.map(p => renderPredCard(p)).join('');
    }

    if (scoreData && scoreData.health_score !== undefined) {
        setText('overall-score-num', scoreData.health_score);
        const gaugePath = document.getElementById('score-gauge-path');
        if (gaugePath) {
            const dashoffset = 126 - (scoreData.health_score / 100) * 126;
            gaugePath.style.strokeDashoffset = dashoffset;
            let color = '#22C55E';
            if (scoreData.health_score < 50) color = '#EF4444';
            else if (scoreData.health_score < 80) color = '#F59E0B';
            gaugePath.setAttribute('stroke', color);
        }
        const badge = document.getElementById('overall-score-badge');
        if (badge) {
            badge.style.display = 'inline-block';
            badge.textContent = scoreData.risk_level + " Risk";
            badge.className = `badge-${scoreData.risk_level === 'High' ? 'warn' : scoreData.risk_level === 'Medium' ? 'warn' : 'success'}`;
            if (scoreData.risk_level === 'High') {
                badge.style.backgroundColor = '#FEF2F2';
                badge.style.color = '#B91C1C';
            } else if (scoreData.risk_level === 'Low') {
                badge.style.backgroundColor = '#F0FDF4';
                badge.style.color = '#15803D';
            }
        }
        const breakdown = document.getElementById('score-breakdown');
        if (breakdown) {
            breakdown.innerHTML = scoreData.factors.map(f => {
                const isNeg = f.includes('(-');
                const color = isNeg ? 'var(--red-600)' : 'var(--green-600)';
                return `<div style="font-size:12.5px; margin-bottom:6px; color:${color};">${esc(f)}</div>`;
            }).join('');
        }
    }
}

function renderPredCard(p) {
    const iconSvg = {
        alert: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        trend: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>`,
        bell:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`,
    };
    const iconColor = { high: 'red', medium: 'amber', low: 'green' }[p.level] || 'blue';
    const badgeClass = `pred-badge-${p.level === 'high' ? 'high' : p.level === 'medium' ? 'medium' : 'low'}`;
    const cardId = `pred-card-${Math.random().toString(36).slice(2,8)}`;

    return `
      <div class="prediction-card ${p.level}" id="${cardId}" data-level="${p.level}" data-type="${p.type}" data-title="${esc(p.title)}">
        <div class="pred-header">
          <div class="pred-header-icon ${iconColor}">${iconSvg[p.iconType] || iconSvg.alert}</div>
          <span class="${badgeClass}">${p.badge}</span>
          <span class="pred-type-label">${p.typeLabel}</span>
        </div>
        <div class="pred-title">${esc(p.title)}</div>
        <div class="pred-body">${esc(p.body)}</div>
        <div class="pred-actions">
          <button class="btn secondary sm" onclick="openActionsModal('${esc(p.title)}')">View Actions ›</button>
          <button class="btn ghost sm" onclick="document.getElementById('${cardId}').style.display='none'">Dismiss</button>
        </div>
      </div>`;
}

window.openActionsModal = function(title) {
    const actions = PRED_ACTIONS[title] || [
        { icon: '👨‍⚕️', title: 'Consult Your Physician', desc: 'Discuss this alert with your primary care doctor at your next appointment.' },
        { icon: '📋', title: 'Review Medical Records', desc: 'Ensure all related medical records are up to date and verified.' }
    ];

    const modalHtml = `
      <div class="modal-overlay" id="actions-modal" onclick="if(event.target===this)closeActionsModal()">
        <div class="modal-box">
          <div class="modal-header">
            <div>
              <h3 class="modal-title">Recommended Actions</h3>
              <p class="modal-sub">${esc(title)}</p>
            </div>
            <button class="modal-close" onclick="closeActionsModal()">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="modal-body">
            ${actions.map((a, i) => `
              <div class="modal-action-item">
                <div class="modal-action-num">${i + 1}</div>
                <div class="modal-action-icon">${a.icon}</div>
                <div class="modal-action-info">
                  <strong>${esc(a.title)}</strong>
                  <p>${esc(a.desc)}</p>
                </div>
              </div>`).join('')}
          </div>
          <div class="modal-footer">
            <button class="btn secondary" onclick="closeActionsModal()">Close</button>
            <button class="btn primary" onclick="closeActionsModal()">Mark as Reviewed</button>
          </div>
        </div>
      </div>`;

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    requestAnimationFrame(() => document.getElementById('actions-modal')?.classList.add('visible'));
};

window.closeActionsModal = function() {
    const modal = document.getElementById('actions-modal');
    if (!modal) return;
    modal.classList.remove('visible');
    setTimeout(() => modal.remove(), 200);
};

async function renderSharing() {

    try {
        const res = await fetch('/api/share/list');
        activeShares = await res.json();
    } catch (e) {
        activeShares = [];
    }

    const badge = document.getElementById('active-shares-count');
    const activeCount = activeShares.filter(s => s.is_active).length;
    if (badge) badge.textContent = `${activeCount} active`;

    const el = document.getElementById('active-shares-list');
    if (!el) return;

    const activeList = activeShares.filter(s => s.is_active);
    el.innerHTML = activeList.length ? activeList.map(s => {
        const permsOn = Object.entries(s.permissions || {})
            .filter(([, v]) => v).map(([k]) => PERM_LABELS[k] || k);
        const expiresDate = s.expires_at
            ? new Date(s.expires_at + (s.expires_at.includes('Z') ? '' : 'Z')).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : '';
        const viewCount = s.view_count || 0;
        return `
          <div class="share-entry">
            <div class="share-entry-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              <strong>${esc(s.recipient_name)}</strong>
              <span class="badge-info">${esc(s.recipient_type)}</span>
              <div style="margin-left:auto;display:flex;gap:6px;align-items:center">
                <button class="btn ghost sm" title="Copy link" onclick="copyShareLink('${esc(s.share_url)}')"
                  style="color:var(--blue-500);display:flex;align-items:center;gap:4px">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  Copy
                </button>
                <button class="btn ghost sm" style="color:var(--red-500)" onclick="revokeShare('${esc(s.token)}')">Revoke</button>
              </div>
            </div>
            <div class="share-entry-meta">${permsOn.length} of 5 categories · Expires ${expiresDate} · ${viewCount} view${viewCount !== 1 ? 's' : ''}</div>
            <div class="share-entry-tags">${permsOn.map(p => `<span class="share-entry-tag">${esc(p)}</span>`).join('')}</div>
          </div>`;
    }).join('')
      : `<p class="empty-msg">No active shares yet.<br>Create a share link to get started.</p>`;
}

const PERM_LABELS = {
    conditions: 'Conditions',
    medications: 'Medications',
    documents: 'Documents',
    timeline: 'Timeline',
    lab_tests: 'Lab Tests'
};

async function generateShareLink() {
    const name = (document.getElementById('share-name-input')?.value || '').trim();
    if (!name) { alert('Please enter a recipient name.'); return; }

    const perms = {};
    const permMap = {
        'Conditions':  'conditions',
        'Medications': 'medications',
        'Documents':   'documents',
        'Timeline':    'timeline',
        'Lab Tests':   'lab_tests'
    };
    document.querySelectorAll('#sharing-view .permission-row').forEach(row => {
        const toggle = row.querySelector('.toggle-switch');
        const label  = row.querySelector('span')?.textContent?.trim();
        const key    = permMap[label];
        if (key) perms[key] = toggle?.classList.contains('on') ? true : false;
    });

    const expiryEl  = document.getElementById('share-expiry-select');
    const expiryHrs = expiryEl ? parseInt(expiryEl.value) : 168;

    const btn = document.getElementById('gen-link-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Generating…'; }

    try {
        const res = await fetch('/api/share/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                recipient_name: name,
                recipient_type: currentShareType,
                permissions: perms,
                expires_hours: expiryHrs
            })
        });
        const data = await res.json();
        document.getElementById('share-name-input').value = '';

        showGeneratedLink(data);
        await renderSharing();
    } catch (e) {
        alert('Failed to generate share link: ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '🔗 Generate Secure Share Link'; }
    }
}

function showGeneratedLink(data) {

    const existing = document.getElementById('generated-link-banner');
    if (existing) existing.remove();

    const fullUrl = window.location.origin + data.share_url;
    const expiryH = data.expires_hours;
    const expiryLabel = expiryH < 24 ? `${expiryH}h` : `${Math.round(expiryH / 24)} day${expiryH > 24 ? 's' : ''}`;

    const banner = document.createElement('div');
    banner.id = 'generated-link-banner';
    banner.style.cssText = `
        background: #f0fdf4; border: 1px solid #86efac; border-radius: 10px;
        padding: 14px 18px; margin: 16px 0; display: flex;
        flex-direction: column; gap: 10px; animation: fadeIn .3s ease;`;
    banner.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;font-weight:600;color:#166534;font-size:13px">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
        Share link generated — valid for ${esc(expiryLabel)}
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="gen-link-url" readonly value="${esc(fullUrl)}"
          style="flex:1;border:1px solid #86efac;border-radius:6px;padding:7px 10px;font-size:12px;
                 background:#fff;color:#1e293b;outline:none;font-family:monospace">
        <button onclick="copyShareLink('${data.share_url}')" class="btn primary sm"
          style="white-space:nowrap;display:flex;align-items:center;gap:6px">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy Link
        </button>
        <button id="preview-share-btn" class="btn secondary sm"
          style="white-space:nowrap">
          Preview
        </button>
      </div>`;

    const genBtn = document.getElementById('gen-link-btn');
    if (genBtn) genBtn.parentNode.insertBefore(banner, genBtn.nextSibling);

    const previewBtn = document.getElementById('preview-share-btn');
    if (previewBtn) previewBtn.addEventListener('click', () => window.open(fullUrl, '_blank'));
}

window.copyShareLink = async function(url) {
    const fullUrl = url.startsWith('http') ? url : window.location.origin + url;
    try {
        await navigator.clipboard.writeText(fullUrl);

        const toast = document.createElement('div');
        toast.textContent = '✅ Link copied to clipboard!';
        toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e293b;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;z-index:9999;box-shadow:0 4px 20px rgba(0,0,0,.2)';
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2200);
    } catch (e) {
        prompt('Copy this link:', fullUrl);
    }
};

window.revokeShare = async function(token) {
    if (!confirm('Revoke this share link? The doctor will no longer be able to access the record.')) return;
    try {
        await fetch(`/api/share/revoke/${token}`, { method: 'DELETE' });
        await renderSharing();
    } catch (e) { alert('Failed to revoke: ' + e.message); }
};

window.selectShareType = function(btn, type) {
    document.querySelectorAll('.share-type-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentShareType = type;

};

window.togglePermission = function(toggle) {
    toggle.classList.toggle('on');
    const row = toggle.closest('.permission-row');
    if (row) row.classList.toggle('active', toggle.classList.contains('on'));
};

function loadSettingsForm() {
    if (!currentUser) return;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
    set('set-name', currentUser.name);
    set('set-dob', currentUser.dob);
    set('set-gender', currentUser.gender);
    set('set-blood', currentUser.blood_group);
    set('set-phone', currentUser.phone);
    set('set-email', currentUser.email);
    set('set-allergies', currentUser.allergies);
    set('set-conditions', currentUser.chronic_conditions);
}

window.saveSettings = async function() {
    const data = {
        name:               document.getElementById('set-name')?.value || '',
        date_of_birth:      document.getElementById('set-dob')?.value || '',
        dob:                document.getElementById('set-dob')?.value || '',
        gender:             document.getElementById('set-gender')?.value || '',
        blood_group:        document.getElementById('set-blood')?.value || '',
        phone:              document.getElementById('set-phone')?.value || '',
        email:              document.getElementById('set-email')?.value || '',
        allergies:          document.getElementById('set-allergies')?.value || '',
        chronic_conditions: document.getElementById('set-conditions')?.value || '',
        insurance_provider: document.getElementById('set-insurance')?.value || '',
        insurance_id:       document.getElementById('set-insurance-id')?.value || '',
    };

    // Bust all relevant cache entries so fresh data is fetched after save
    ['medisync_cache_/auth/me', 'medisync_cache_/api/user'].forEach(k => localStorage.removeItem(k));

    const btn = document.querySelector('#settings-view button.btn.primary[onclick="saveSettings()"]');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

    try {
        const res = await originalFetch('/api/user', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const updated = await res.json();

        // Merge server response back into currentUser (use server truth where available)
        currentUser = {
            ...currentUser,
            ...updated,
            dob: updated.date_of_birth || updated.dob || data.dob,
            chronic_conditions: updated.chronic_conditions ?? data.chronic_conditions,
            allergies: updated.allergies ?? data.allergies,
        };

        // Re-render every dashboard surface that shows profile data
        await loadUserProfile();
        await loadDashboard();
        loadSettingsForm();

        showSettingsToast('✅ Profile saved and dashboard updated!', 'success');
    } catch (e) {
        // Fallback — apply locally so the dashboard still updates
        currentUser = {
            ...currentUser,
            ...data,
            dob: data.dob,
        };
        await loadUserProfile();
        await loadDashboard();
        loadSettingsForm();
        showSettingsToast('Profile updated locally. Changes will sync when online.', 'warn');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Save Profile'; }
    }
};

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function showSettingsToast(message, type = 'success') {
    const existing = document.getElementById('settings-toast');
    if (existing) existing.remove();

    const colors = {
        success: { bg: '#f0fdf4', border: '#86efac', text: '#166534' },
        warn:    { bg: '#fffbeb', border: '#fcd34d', text: '#92400e' },
        error:   { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
    };
    const c = colors[type] || colors.success;

    const toast = document.createElement('div');
    toast.id = 'settings-toast';
    toast.style.cssText = `
        position: fixed; bottom: 28px; right: 28px; z-index: 9999;
        background: ${c.bg}; border: 1px solid ${c.border}; color: ${c.text};
        padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 500;
        box-shadow: 0 8px 24px rgba(0,0,0,.12); display: flex; align-items: center; gap: 8px;
        animation: slideInToast .25s ease;
    `;
    toast.innerHTML = `
        <style>@keyframes slideInToast{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}</style>
        ${message}
        <button onclick="this.closest('#settings-toast').remove()"
          style="background:none;border:none;cursor:pointer;color:${c.text};font-size:15px;line-height:1;padding:0 0 0 6px;">×</button>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function esc(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

window.toggleChatPanel = function() {
    const panel    = document.getElementById('chat-panel');
    const backdrop = document.getElementById('chat-backdrop');
    if (!panel) return;
    const isOpen = panel.classList.toggle('open');
    if (backdrop) backdrop.classList.toggle('open', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
    if (isOpen) loadChatHistory();
};

async function loadChatHistory() {
    try {
        const res = await fetch('/api/chat/history');
        const msgs = await res.json();
        const container = document.getElementById('chat-messages');
        if (!container) return;
        if (msgs.length === 0) return; // Keep welcome screen

        container.innerHTML = '';
        msgs.forEach(m => appendChatBubble(m.role, m.content, false));
        container.scrollTop = container.scrollHeight;
    } catch(e) { console.warn('chat history', e); }
}

function appendChatBubble(role, content, scroll = true) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = `
      <div class="chat-bubble">${esc(content).replace(/\n/g, '<br>')}</div>
      <div class="chat-msg-time">${time}</div>`;
    container.appendChild(div);
    if (scroll) container.scrollTop = container.scrollHeight;
}

function showTyping() {
    const container = document.getElementById('chat-messages');
    if (!container) return null;
    const div = document.createElement('div');
    div.className = 'chat-typing';
    div.id = 'chat-typing-indicator';
    div.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

window.sendChatMessage = async function() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send-btn');
    const question = input?.value?.trim();
    if (!question) return;

    input.value = '';
    sendBtn.disabled = true;
    appendChatBubble('user', question);
    const typingEl = showTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ question })
        });
        const data = await res.json();
        typingEl?.remove();
        appendChatBubble('assistant', data.response || '⚠️ No response from AI.');
    } catch(e) {
        typingEl?.remove();
        appendChatBubble('assistant', '⚠️ Error connecting to Health AI. Please try again.');
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
};

window.sendSuggestion = function(text) {
    const input = document.getElementById('chat-input');
    if (input) { input.value = text; sendChatMessage(); }
};

window.clearChatHistory = async function() {
    if (!confirm('Clear all chat history?')) return;
    await fetch('/api/chat/history', { method: 'DELETE' });
    const container = document.getElementById('chat-messages');
    if (container) container.innerHTML = `
      <div class="chat-welcome">
        <div style="font-size:28px;margin-bottom:8px">👋</div>
        <div style="font-weight:600;color:var(--neutral-800);margin-bottom:4px">Chat cleared. How can I help?</div>
      </div>`;
};

let _editingFollowUpId = null;

window.renderFollowUps = function(followUps) {
    const el = document.getElementById('dash-followups-list');
    if (!el) return;
    if (!followUps || followUps.length === 0) {
        el.innerHTML = '<p class="empty-msg">No upcoming follow-ups scheduled. Click + Add to create one.</p>';
        return;
    }
    el.innerHTML = followUps.slice(0, 5).map(fu => {
        const dateStr = fu.follow_up_date ? new Date(fu.follow_up_date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric'}) : '—';
        return `
        <div class="followup-card">
          <div class="followup-dot ${fu.status || 'scheduled'}"></div>
          <div style="flex:1;min-width:0">
            <div class="followup-title">${esc(fu.title)}</div>
            <div class="followup-meta">${fu.doctor_name ? '👨‍⚕️ ' + esc(fu.doctor_name) : ''}${fu.hospital ? ' · 🏥 ' + esc(fu.hospital) : ''}</div>
            <div class="followup-date">📅 ${esc(dateStr)}</div>
            ${fu.notes ? `<div style="font-size:11px;color:var(--neutral-400);margin-top:3px;font-style:italic">${esc(fu.notes)}</div>` : ''}
          </div>
          <div class="followup-actions">
            <span class="followup-badge ${fu.status || 'scheduled'}">${fu.status || 'scheduled'}</span>
            <button style="background:none;border:none;cursor:pointer;color:var(--blue-500);font-size:12px;padding:2px 4px" onclick="editFollowUp('${fu.id}',${JSON.stringify(fu).replace(/"/g,'&quot;')})" title="Edit">✏️</button>
            <button style="background:none;border:none;cursor:pointer;color:var(--red-500);font-size:12px;padding:2px 4px" onclick="deleteFollowUp('${esc(fu.id)}')" title="Delete">🗑️</button>
          </div>
        </div>`;
    }).join('');
};

window.openFollowUpModal = function() {
    _editingFollowUpId = null;
    document.getElementById('fu-modal-title').textContent = 'Add Follow-up Appointment';
    document.getElementById('fu-edit-id').value = '';
    document.getElementById('fu-title').value = '';
    document.getElementById('fu-date').value = '';
    document.getElementById('fu-doctor').value = '';
    document.getElementById('fu-hospital').value = '';
    document.getElementById('fu-notes').value = '';
    document.getElementById('fu-status').value = 'scheduled';
    const modal = document.getElementById('followup-modal');
    modal.classList.add('visible');
};

window.editFollowUp = function(id, fu) {
    _editingFollowUpId = id;
    document.getElementById('fu-modal-title').textContent = 'Edit Follow-up Appointment';
    document.getElementById('fu-edit-id').value = id;
    document.getElementById('fu-title').value = fu.title || '';
    document.getElementById('fu-date').value = fu.follow_up_date?.slice(0, 10) || '';
    document.getElementById('fu-doctor').value = fu.doctor_name || '';
    document.getElementById('fu-hospital').value = fu.hospital || '';
    document.getElementById('fu-notes').value = fu.notes || '';
    document.getElementById('fu-status').value = fu.status || 'scheduled';
    document.getElementById('followup-modal').classList.add('visible');
};

window.closeFollowUpModal = function() {
    document.getElementById('followup-modal').classList.remove('visible');
    _editingFollowUpId = null;
};

window.saveFollowUp = async function() {
    const id = _editingFollowUpId;
    const body = {
        title:        document.getElementById('fu-title').value.trim(),
        follow_up_date: document.getElementById('fu-date').value,
        doctor_name:  document.getElementById('fu-doctor').value.trim(),
        hospital:     document.getElementById('fu-hospital').value.trim(),
        notes:        document.getElementById('fu-notes').value.trim(),
        status:       document.getElementById('fu-status').value
    };
    if (!body.title || !body.follow_up_date) { alert('Title and date are required.'); return; }

    try {
        const url    = id ? `/api/follow-ups/${id}` : '/api/follow-ups';
        const method = id ? 'PUT' : 'POST';
        await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
        closeFollowUpModal();
        const res = await fetch('/api/follow-ups');
        renderFollowUps(await res.json());
    } catch(e) { alert('Failed to save. Try again.'); }
};

window.deleteFollowUp = async function(id) {
    if (!confirm('Delete this follow-up?')) return;
    await fetch(`/api/follow-ups/${id}`, { method: 'DELETE' });
    const res = await fetch('/api/follow-ups');
    renderFollowUps(await res.json());
};

window.cureMedication = async function(medId, medName) {
    if (!confirm(`Mark "${medName}" as Cured? It will be moved to past medications.`)) return;
    await fetch(`/api/medications/${medId}/cure`, { method: 'POST' });
    const medsRes = await fetch('/api/medications');
    renderMedsGrid(await medsRes.json());
    loadDashboard();
};

window.reactivateMedication = async function(medId, medName) {
    if (!confirm(`Mark "${medName}" as Active again?`)) return;
    await fetch(`/api/medications/${medId}/reactivate`, { method: 'POST' });
    const medsRes = await fetch('/api/medications');
    renderMedsGrid(await medsRes.json());
    loadDashboard();
};

window.openMedModal = function(id, name, dosage, freq) {
    document.getElementById('med-edit-id').value = id;
    document.getElementById('med-edit-name').value = name || '';
    document.getElementById('med-edit-dosage').value = dosage || '';
    document.getElementById('med-edit-freq').value = freq || '';
    const modal = document.getElementById('edit-med-modal');
    modal.classList.add('visible');
    modal.style.pointerEvents = 'all';
};

window.closeMedModal = function() {
    const modal = document.getElementById('edit-med-modal');
    modal.classList.remove('visible');
    modal.style.pointerEvents = 'none';
};

window.saveMedication = async function() {
    const id = document.getElementById('med-edit-id').value;
    const data = {
        med_name: document.getElementById('med-edit-name').value.trim(),
        dosage: document.getElementById('med-edit-dosage').value.trim(),
        frequency: document.getElementById('med-edit-freq').value.trim()
    };
    if (!data.med_name) return alert('Name required');
    try {
        const res = await fetch(`/api/medications/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        if (res.ok) {
            closeMedModal();
            loadDashboard();
        }
    } catch (e) { console.error('Failed to update med', e); }
};

window.generateSummary = async function() {
    const btn = document.getElementById('generate-summary-btn');
    const content = document.getElementById('dash-summary-content');
    if (!content) return;

    const isRegen = btn.textContent.trim().startsWith('Regenerate');
    btn.textContent = 'Generating…';
    btn.disabled = true;
    content.style.display = 'block';
    content.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;padding:16px;color:var(--neutral-500);font-size:13px;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite;flex-shrink:0"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
        AI is generating your health summary…
      </div>`;

    try {
        const url = isRegen ? '/api/summary?bypass_cache=true' : '/api/summary';
        const res = await fetch(url, { headers: { 'X-Bypass-Cache': 'true' } });
        const data = await res.json();
        // Render plain-text summary: strip any residual markdown chars first
        let plain = data.summary || '';
        plain = plain.replace(/[*_`~]/g, '');
        plain = plain.replace(/^#{1,6}\s*/gm, '');
        plain = plain.replace(/^[-•>]\s+/gm, '');

        // HTML-escape the cleaned text
        let escaped = plain
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');

        // Style plain-text section labels (e.g. "PATIENT OVERVIEW")
        const sectionLabels = [
            'PATIENT OVERVIEW','RECENT CLINICAL HISTORY','ACTIVE MEDICATIONS',
            'KNOWN CONDITIONS','ALLERGIES','CURRENT MEDICATIONS','CLINICAL CONTEXT'
        ];
        const labelRe = new RegExp('(' + sectionLabels.join('|') + ')\\s*:?', 'g');
        escaped = escaped.replace(labelRe,
            '<strong style="display:block;margin-top:14px;margin-bottom:3px;font-size:12px;color:var(--blue-800);letter-spacing:0.06em;text-transform:uppercase;">$1</strong>'
        );

        // Convert newlines to line breaks
        const formatted = escaped.replace(/\n/g, '<br>');
        content.innerHTML = `
          <div style="background:linear-gradient(135deg,var(--blue-50),#f0f9ff);padding:18px 20px;border-radius:var(--radius);border:1px solid var(--blue-200);line-height:1.75;font-size:13.5px;color:var(--neutral-800);">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--blue-200);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--blue-600)" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
              <strong style="color:var(--blue-800);font-size:13px;">AI Clinical Summary</strong>
              <span style="margin-left:auto;font-size:10.5px;background:var(--blue-100);color:var(--blue-700);padding:2px 8px;border-radius:20px;">Generated by AI</span>
            </div>
            ${formatted}
          </div>`;
    } catch(e) {
        content.innerHTML = `<span style="color:var(--red-500);font-size:13px;">Failed to generate summary: ${e.message}</span>`;
    } finally {
        btn.textContent = 'Regenerate Summary';
        btn.disabled = false;
    }
};
