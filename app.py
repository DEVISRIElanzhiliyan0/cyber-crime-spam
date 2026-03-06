from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
import pickle
import os
import sqlite3
import uuid
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'frontend', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'frontend', 'static')

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('FLASK_SECRET') or 'dev-secret-change-me'

# Detect Vercel environment
IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    UPLOAD_DIR = '/tmp/uploads'
else:
    UPLOAD_DIR = os.path.join(STATIC_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.before_request
def set_lang():
    if 'lang' not in session:
        session['lang'] = 'en'
    if request.args.get('lang'):
        session['lang'] = request.args.get('lang')

def get_t():
    lang = session.get('lang', 'en')
    return TRANSLATIONS.get(lang, TRANSLATIONS['en'])

# Admin credentials
ADMIN_USER = "devisrie24aid@vetias.ac.in"
ADMIN_PASSWORD_HASH = "scrypt:32768:8:1$Yl3E2f49hM8g7e1e$160938fc2909405d8f685c493c0429406f69841804194098"

# DB Connection
db_path = os.path.join(BASE_DIR, 'cybercrime.db')
db = sqlite3.connect(db_path, check_same_thread=False)
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
try:
    cursor.execute("ALTER TABLE complaints ADD COLUMN complaint_id TEXT")
    db.commit()
except: pass

# Load ML Model
model = None
vectorizer = None
try:
    model = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'spam_model.pkl'), "rb"))
    vectorizer = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl'), "rb"))
except:
    pass

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
        cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                       (unique_id, name, email, phone, ctype, 'Received'))
        db.commit()
        lid = cursor.lastrowid
        return render_template('complaint_success.html', complaint_id=unique_id, db_id=lid, name=name, ctype=ctype)
    return render_template("complaint.html")

@app.route('/track', methods=['GET','POST'])
def track():
    result = None
    error = None
    if request.method == 'POST':
        cid = request.form.get('id', '').strip()
        try:
            if cid.isdigit():
                cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE id=?", (int(cid),))
            else:
                cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE UPPER(complaint_id)=?", (cid.upper(),))
            row = cursor.fetchone()
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
        global model, vectorizer
        if model is None or vectorizer is None:
            try:
                model = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'spam_model.pkl'), 'rb'))
                vectorizer = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl'), 'rb'))
            except: pass
        if model is None or vectorizer is None:
            return "Model not available."
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
    global model, vectorizer
    if model is None or vectorizer is None:
        try:
            model = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'spam_model.pkl'), 'rb'))
            vectorizer = pickle.load(open(os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl'), 'rb'))
        except: pass
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
        cursor.execute("SELECT COUNT(*) FROM complaints")
        total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT type, COUNT(*) FROM complaints GROUP BY type")
        by_type = cursor.fetchall() or []
        cursor.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
        by_status = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT id, name, email, type, status FROM complaints ORDER BY id DESC LIMIT 10")
        recent = cursor.fetchall() or []
    except:
        total, by_type, by_status, recent = 0, [], {}, []
    return render_template('admin_dashboard.html', total=total, by_type=by_type, by_status=by_status, recent=recent, admin_email=session.get('admin'))

@app.route('/stats')
def stats():
    try:
        cursor.execute("SELECT COUNT(*) FROM complaints")
        total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT type, COUNT(*) FROM complaints GROUP BY type")
        by_type = cursor.fetchall() or []
        cursor.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
        by_status = cursor.fetchall() or []
    except:
        total, by_type, by_status = 0, [], []
    return render_template('stats.html', total=total, by_type=by_type, by_status=by_status)

@app.route('/report/save', methods=['POST'])
def report_save():
    unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                   (unique_id, "AI Report", '', '', 'Spam Report', 'Received'))
    db.commit()
    return redirect(url_for('assistant', lang=request.form.get('lang', 'en')))

@app.route('/report/flag', methods=['POST'])
def report_flag():
    unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                   (unique_id, "Flagged Content", '', '', 'Flagged', 'Under Review'))
    db.commit()
    return redirect(url_for('assistant', lang=request.form.get('lang', 'en')))

# Translations
TRANSLATIONS = {
    'en': {'title': 'AI Cyber Assistant', 'welcome': 'Hello!', 'scan_btn': 'Scan Image', 'quiz_btn': 'Quiz', 'risk_labels': {'high': 'High', 'med': 'Med', 'low': 'Low', 'safe': 'Safe'}, 'steps_title': 'Steps:', 'safe_msg': 'Safe', 'spam_msg': 'Spam', 'phishing_msg': 'Phishing', 'scam_msg': 'Scam', 'chat_kb': {'phishing': 'Phishing...', 'spam': 'Spam...', 'safe': 'Safe...', 'default': 'How can I help?'}},
    'ta': {'title': 'AI உதவியாளர்', 'welcome': 'வணக்கம்!', 'scan_btn': 'ஸ்கேன்', 'quiz_btn': 'வினாடி வினா', 'risk_labels': {'high': 'அதிக', 'med': 'நடுத்தர', 'low': 'குறைந்த', 'safe': 'பாதுகாப்பு'}, 'steps_title': 'நடவடிக்கை:', 'safe_msg': 'பாதுகாப்பு', 'spam_msg': 'ஸ்பேம்', 'phishing_msg': 'ஃபிஷிங்', 'scam_msg': 'மோசடி', 'chat_kb': {'phishing': 'ஃபிஷிங்...', 'spam': 'ஸ்பேம்...', 'safe': 'பாதுகாப்பு...', 'default': 'உதவ வேண்டுமா?'}},
    'hi': {'title': 'AI सहायक', 'welcome': 'नमस्ते!', 'scan_btn': 'स्कैन', 'quiz_btn': 'प्रश्नोत्तरी', 'risk_labels': {'high': 'उच्च', 'med': 'मध्यम', 'low': 'कम', 'safe': 'सुरक्षित'}, 'steps_title': 'कदम:', 'safe_msg': 'सुरक्षित', 'spam_msg': 'स्पैम', 'phishing_msg': 'फ़िशिंग', 'scam_msg': 'घोटाला', 'chat_kb': {'phishing': 'फ़िशिंग...', 'spam': 'स्पैम...', 'safe': 'सुरक्षित...', 'default': 'क्या मदद?'}}
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

@app.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    question = request.form.get('question', '').lower()
    t, lang = get_t(), session['lang']
    kb = t['chat_kb']
    answer = kb['default']
    if 'phish' in question: answer = kb['phishing']
    elif 'spam' in question: answer = kb['spam']
    elif 'safe' in question: answer = kb['safe']
    return render_template('assistant.html', t=t, lang=lang, chat_mode=True, question=question, answer=answer)

@app.route('/games')
def games(): return render_template('games.html')

@app.route('/guidelines')
def guidelines(): return render_template('guidelines.html')

# Vercel's entry point must expose the app object
# No app.run() needed here.

if __name__ == "__main__":
    app.run(debug=True)
