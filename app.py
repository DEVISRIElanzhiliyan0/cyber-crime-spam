from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import pickle
import os
import sqlite3
import uuid
import datetime
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'frontend', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'frontend', 'static')

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('FLASK_SECRET') or 'dev-secret-change-me'

# Detect Vercel environment
IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    UPLOAD_DIR = '/tmp/uploads'
    DB_PATH = '/tmp/cybercrime.db'
    # Copy existing DB to writable /tmp on startup
    if not os.path.exists(DB_PATH):
        orig_db = os.path.join(BASE_DIR, 'cybercrime.db')
        if os.path.exists(orig_db):
            shutil.copy2(orig_db, DB_PATH)
else:
    UPLOAD_DIR = os.path.join(STATIC_DIR, 'uploads')
    DB_PATH = os.path.join(BASE_DIR, 'cybercrime.db')

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Admin credentials
ADMIN_USER = "devisrie24aid@vetias.ac.in"

def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    return db

@app.before_request
def set_lang():
    if 'lang' not in session:
        session['lang'] = 'en'
    if request.args.get('lang'):
        session['lang'] = request.args.get('lang')

def get_t():
    lang = session.get('lang', 'en')
    return TRANSLATIONS.get(lang, TRANSLATIONS['en'])

# Global DB init
db = get_db()
cursor = db.cursor()
cursor.execute('''
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
db.commit()

# Load ML Model
model = None
vectorizer = None
def load_ml():
    global model, vectorizer
    try:
        m_path = os.path.join(BASE_DIR, 'ml', 'spam_model.pkl')
        v_path = os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl')
        if os.path.exists(m_path):
            model = pickle.load(open(m_path, "rb"))
            vectorizer = pickle.load(open(v_path, "rb"))
    except: pass

load_ml()

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/complaint', methods=['GET', 'POST'])
def complaint():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        ctype = request.form['type']
        unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                       (unique_id, name, email, phone, ctype, 'Received'))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return render_template('complaint_success.html', complaint_id=unique_id, db_id=lid, name=name, ctype=ctype)
    return render_template("complaint.html")

@app.route('/track', methods=['GET','POST'])
def track():
    result = None
    error = None
    if request.method == 'POST':
        cid = request.form.get('id', '').strip()
        try:
            conn = get_db()
            cur = conn.cursor()
            if cid.isdigit():
                cur.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE id=?", (int(cid),))
            else:
                cur.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE UPPER(complaint_id)=?", (cid.upper(),))
            row = cur.fetchone()
            conn.close()
            if row:
                result = {'id': row[0], 'complaint_id': row[1] or ('—'), 'name': row[2], 'type': row[3], 'status': row[4]}
            else:
                error = 'No complaint found.'
        except:
            error = 'Retrieval error.'
    return render_template("track.html", result=result, error=error)

@app.route('/spam', methods=['GET','POST'])
def spam():
    if request.method == 'POST':
        message = request.form['message']
        if model is None or vectorizer is None: load_ml()
        if model is None or vectorizer is None: return "Model not available."
        data = vectorizer.transform([message])
        prediction = model.predict(data)
        result = "Spam" if int(prediction[0]) == 1 else "Not Spam"
        return f"Prediction: {result}"
    return render_template("spam_check.html")

@app.route('/spam/upload', methods=['POST'])
def spam_upload():
    if 'screenshot' not in request.files: return "No file", 400
    f = request.files['screenshot']
    if f.filename == '': return "Empty", 400
    filename = secure_filename(f.filename)
    save_path = os.path.join(UPLOAD_DIR, filename)
    f.save(save_path)
    ocr_text = None
    try:
        from PIL import Image
        import pytesseract
        ocr_text = pytesseract.image_to_string(Image.open(save_path))
    except: pass
    form_text = request.form.get('message', '')
    final_text = (form_text + " " + (ocr_text or "")).strip()
    if not final_text: return render_template('spam_check.html', ocr_error='No text extracted.')
    if model is None or vectorizer is None: load_ml()
    if model is None or vectorizer is None: return render_template('spam_check.html', ocr_text=final_text, ocr_error='Model error.')
    data = vectorizer.transform([final_text])
    result = "Spam" if int(model.predict(data)[0]) == 1 else "Not Spam"
    return render_template('spam_check.html', ocr_text=final_text, ocr_result=result, uploaded=filename)

@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if request.form['email'] == ADMIN_USER and request.form['password'] == "kimtaehyungdevi":
            session['admin'] = ADMIN_USER
            return redirect(url_for('admin_dashboard'))
        error = 'Invalid credentials.'
    return render_template('admin_login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('home'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM complaints")
        total = cur.fetchone()[0] or 0
        cur.execute("SELECT type, COUNT(*) FROM complaints GROUP BY type")
        by_type = cur.fetchall() or []
        cur.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
        by_status = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute("SELECT id, name, email, type, status FROM complaints ORDER BY id DESC LIMIT 10")
        recent = cur.fetchall() or []
        conn.close()
    except:
        total, by_type, by_status, recent = 0, [], {}, []
    return render_template('admin_dashboard.html', total=total, by_type=by_type, by_status=by_status, recent=recent, admin_email=session.get('admin'))

@app.route('/stats')
def stats():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM complaints")
        total = cur.fetchone()[0] or 0
        cur.execute("SELECT type, COUNT(*) FROM complaints GROUP BY type")
        by_type = cur.fetchall() or []
        cur.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
        by_status = cur.fetchall() or []
        conn.close()
    except:
        total, by_type, by_status = 0, [], []
    return render_template('stats.html', total=total, by_type=by_type, by_status=by_status)

# Translations Simplified
TRANSLATIONS = {
    'en': {'title': 'AI Cyber Assistant', 'welcome': 'Hello!', 'safe_msg': 'Safe', 'spam_msg': 'Spam', 'phishing_msg': 'Phishing', 'scam_msg': 'Scam'},
    'ta': {'title': 'AI உதவியாளர்', 'welcome': 'வணக்கம்!', 'safe_msg': 'பாதுகாப்பு', 'spam_msg': 'ஸ்பேம்', 'phishing_msg': 'ஃபிஷிங்', 'scam_msg': 'மோசடி'},
    'hi': {'title': 'AI सहायक', 'welcome': 'नमस्ते!', 'safe_msg': 'सुरक्षित', 'spam_msg': 'स्पैम', 'phishing_msg': 'फ़िशिंग', 'scam_msg': 'घोटाला'}
}

@app.route('/assistant')
def assistant():
    return render_template('assistant.html', t=get_t(), lang=session['lang'])

@app.route('/assistant/analyze', methods=['POST'])
def assistant_analyze():
    message, t, lang = request.form.get('message', ''), get_t(), session['lang']
    ocr_text, uploaded_filename = "", None
    if 'screenshot' in request.files:
        f = request.files['screenshot']
        if f and f.filename != '':
            filename = secure_filename(f.filename)
            save_path = os.path.join(UPLOAD_DIR, filename)
            f.save(save_path)
            uploaded_filename = filename
            try:
                from PIL import Image
                import pytesseract
                ocr_text = pytesseract.image_to_string(Image.open(save_path))
            except: pass
    combined = (message + " " + ocr_text).strip().lower()
    if not combined: return render_template('assistant.html', t=t, lang=lang, analyzed=False, error="Empty.")
    risk_score, res_type, reason, level = 0, "Safe", t['safe_msg'], "low"
    if any(w in combined for w in ['bank', 'login', 'verify', 'password']):
        risk_score, res_type, reason, level = 85, "Phishing", t['phishing_msg'], "high"
    elif any(w in combined for w in ['win', 'prize', 'lottery']):
        risk_score, res_type, reason, level = 90, "Scam", t['scam_msg'], "high"
    elif len(combined) > 10:
        risk_score, res_type, reason, level = 40, "Spam", t['spam_msg'], "med"
    return render_template('assistant.html', t=t, lang=lang, analyzed=True, score=risk_score, res_type=res_type, reason=reason, level=level, message=message, ocr_text=ocr_text, uploaded=uploaded_filename)

@app.route('/games')
def games(): return render_template('games.html')

@app.route('/guidelines')
def guidelines(): return render_template('guidelines.html')

if __name__ == "__main__":
    app.run(debug=True)
