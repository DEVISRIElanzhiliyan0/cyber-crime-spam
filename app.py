from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import pickle
import os
import sqlite3
import uuid
import datetime
import shutil

# --- PATH CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'frontend', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'frontend', 'static')

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('FLASK_SECRET') or 'dev-secret-change-me'

# --- CLOUD COMPATIBILITY ---
IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    UPLOAD_DIR = '/tmp/uploads'
    DB_PATH = '/tmp/cybercrime.db'
    # Copy DB to writable /tmp
    if not os.path.exists(DB_PATH):
        orig_db = os.path.join(BASE_DIR, 'cybercrime.db')
        if os.path.exists(orig_db):
            shutil.copy2(orig_db, DB_PATH)
else:
    UPLOAD_DIR = os.path.join(STATIC_DIR, 'uploads')
    DB_PATH = os.path.join(BASE_DIR, 'cybercrime.db')

os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- DATABASE ---
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize DB on first load
with sqlite3.connect(DB_PATH) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT,
            name TEXT,
            email TEXT,
            phone TEXT,
            type TEXT,
            status TEXT DEFAULT 'Received'
        )
    ''')

# --- ML MODELS ---
model = None
vectorizer = None
def load_ml():
    global model, vectorizer
    try:
        m_path = os.path.join(BASE_DIR, 'ml', 'spam_model.pkl')
        v_path = os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl')
        if os.path.exists(m_path) and os.path.exists(v_path):
            with open(m_path, 'rb') as f: model = pickle.load(f)
            with open(v_path, 'rb') as f: vectorizer = pickle.load(f)
    except: pass

load_ml()

# --- TRANSLATIONS ---
TRANSLATIONS = {
    'en': {'title': 'AI Cyber Assistant', 'welcome': 'Hello! I am your Cyber Safety Partner.', 'safe_msg': 'Content Safe', 'spam_msg': 'Spam detected', 'phishing_msg': 'Phishing alert', 'scam_msg': 'Scam alert'},
    'ta': {'title': 'AI உதவியாளர்', 'welcome': 'வணக்கம்!', 'safe_msg': 'பாதுகாப்பு', 'spam_msg': 'ஸ்பேம்', 'phishing_msg': 'ஃபிஷிங்', 'scam_msg': 'மோசடி'},
    'hi': {'title': 'AI सहायक', 'welcome': 'नमस्ते!', 'safe_msg': 'सुरक्षित', 'spam_msg': 'स्पैम', 'phishing_msg': 'फ़िशिंग', 'scam_msg': 'घोटाला'}
}

# --- ROUTES ---
@app.before_request
def setup():
    if 'lang' not in session: session['lang'] = 'en'
    if request.args.get('lang'): session['lang'] = request.args.get('lang')

def get_t(): return TRANSLATIONS.get(session.get('lang', 'en'), TRANSLATIONS['en'])

@app.route('/')
def home(): return render_template("index.html")

@app.route('/complaint', methods=['GET', 'POST'])
def complaint():
    if request.method == 'POST':
        unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                       (unique_id, request.form['name'], request.form['email'], request.form['phone'], request.form['type'], 'Received'))
            conn.commit()
            lid = cur.lastrowid
        return render_template('complaint_success.html', complaint_id=unique_id, db_id=lid, name=request.form['name'], ctype=request.form['type'])
    return render_template("complaint.html")

@app.route('/track', methods=['GET','POST'])
def track():
    result, error = None, None
    if request.method == 'POST':
        cid = request.form.get('id', '').strip()
        with get_db() as conn:
            cur = conn.cursor()
            if cid.isdigit(): cur.execute("SELECT * FROM complaints WHERE id=?", (int(cid),))
            else: cur.execute("SELECT * FROM complaints WHERE UPPER(complaint_id)=?", (cid.upper(),))
            row = cur.fetchone()
            if row: result = dict(row)
            else: error = 'No complaint found.'
    return render_template("track.html", result=result, error=error)

@app.route('/spam', methods=['GET','POST'])
def spam():
    if request.method == 'POST':
        msg = request.form['message']
        if model is None: load_ml()
        if model:
            res = "Spam" if int(model.predict(vectorizer.transform([msg]))[0]) == 1 else "Not Spam"
            return f"Prediction: {res}"
        return "Model not ready."
    return render_template("spam_check.html")

@app.route('/spam/upload', methods=['POST'])
def spam_upload():
    if 'screenshot' not in request.files: return "No file", 400
    f = request.files['screenshot']
    path = os.path.join(UPLOAD_DIR, secure_filename(f.filename))
    f.save(path)
    ocr = ""
    try:
        import pytesseract
        from PIL import Image
        ocr = pytesseract.image_to_string(Image.open(path))
    except: pass
    txt = (request.form.get('message', '') + " " + ocr).strip()
    if not txt: return render_template('spam_check.html', ocr_error='No text.')
    if model is None: load_ml()
    res = "Spam" if model and int(model.predict(vectorizer.transform([txt]))[0]) == 1 else "Unknown"
    return render_template('spam_check.html', ocr_text=txt, ocr_result=res, uploaded=f.filename)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['email'] == "devisrie24aid@vetias.ac.in" and request.form['password'] == "kimtaehyungdevi":
            session['admin'] = request.form['email']
            return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    with get_db() as conn:
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        recent = [dict(r) for r in cur.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 10").fetchall()]
    return render_template('admin_dashboard.html', total=total, recent=recent)

@app.route('/assistant')
def assistant(): return render_template('assistant.html', t=get_t(), lang=session['lang'])

@app.route('/assistant/analyze', methods=['POST'])
def assistant_analyze():
    msg, t = request.form.get('message', ''), get_t()
    ocr = ""
    if 'screenshot' in request.files and request.files['screenshot'].filename:
        f = request.files['screenshot']
        path = os.path.join(UPLOAD_DIR, secure_filename(f.filename))
        f.save(path)
        try:
            import pytesseract
            from PIL import Image
            ocr = pytesseract.image_to_string(Image.open(path))
        except: pass
    comb = (msg + " " + ocr).strip().lower()
    score, rtype, rlvl = 0, "Safe", "low"
    if any(w in comb for w in ['bank', 'verify', 'password']): score, rtype, rlvl = 85, "Phishing", "high"
    elif any(w in comb for w in ['win', 'prize']): score, rtype, rlvl = 90, "Scam", "high"
    return render_template('assistant.html', t=t, lang=session['lang'], analyzed=True, score=score, res_type=rtype, level=rlvl, message=msg, ocr_text=ocr)

@app.route('/static/uploads/<path:filename>')
def uploads(filename): return send_from_directory(UPLOAD_DIR, filename)

@app.route('/games')
def games(): return render_template('games.html')

@app.route('/guidelines')
def guidelines(): return render_template('guidelines.html')

# Health check
@app.route('/api/health')
def health(): return {"status": "ok"}

if __name__ == "__main__":
    app.run(debug=True)
