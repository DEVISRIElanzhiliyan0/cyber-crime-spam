from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import pickle
import os
import sqlite3
import uuid
import datetime
import shutil

# --- PATH CONFIGURATION ---
# Current file is in /api/index.py
API_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(API_DIR) # Moves up to project root
TEMPLATES_DIR = os.path.join(BASE_DIR, 'frontend', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'frontend', 'static')

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('FLASK_SECRET') or 'dev-secret-change-me'

# --- CLOUD COMPATIBILITY ---
IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    UPLOAD_DIR = '/tmp/uploads'
    DB_PATH = '/tmp/cybercrime.db'
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

# Ensure DB is initialized
with sqlite3.connect(DB_PATH) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT,
            name TEXT,
            email TEXT,
            phone TEXT,
            type TEXT,
            description TEXT,
            status TEXT DEFAULT 'Received'
        )
    ''')

# --- ML MODELS ---
model = None
vectorizer = None
def load_ml():
    global model, vectorizer
    if model is not None: return
    try:
        m_path = os.path.join(BASE_DIR, 'ml', 'spam_model.pkl')
        v_path = os.path.join(BASE_DIR, 'ml', 'vectorizer.pkl')
        if os.path.exists(m_path) and os.path.exists(v_path):
            with open(m_path, 'rb') as f: model = pickle.load(f)
            with open(v_path, 'rb') as f: vectorizer = pickle.load(f)
        else:
            print(f"Model files not found at: {m_path} or {v_path}")
    except Exception as e:
        print(f"Error loading ML: {str(e)}")

# --- TRANSLATIONS ---
TRANSLATIONS = {
    'en': {
        'title': 'AI Cyber Assistant', 
        'welcome': 'Hello! I am your Cyber Safety Partner. How can I help you today?', 
        'scan_btn': 'Scan Image/Text',
        'quiz_btn': 'Take Safety Quiz',
        'risk_labels': {'high': 'High Risk', 'med': 'Medium Risk', 'low': 'Low Risk', 'safe': 'Safe'},
        'steps_title': 'What to do next:',
        'safe_msg': 'This content appears safe, but always remain vigilant.',
        'spam_msg': 'This is likely a spam attempt designed to clutter your inbox.',
        'phishing_msg': 'WARNING: This is a phishing attempt to steal your credentials!',
        'scam_msg': 'DANGER: This is a financial scam attempt.',
        'chat_kb': {
            'phishing': 'Phishing is a deceptive technique where attackers send fraudulent messages to trick victims into revealing sensitive info like passwords or banking details.',
            'spam': 'Spam refers to unsolicited bulk messages, usually sent via email, text, or social media, often for marketing or malicious purposes.',
            'safe': 'Always be cautious. If a link looks suspicious, do not click it. Check the sender\'s email or number carefully.',
            'default': 'I can help identify frauds. Ask me about Phishing, Spam, or how to report a crime!'
        }
    },
    'ta': {
        'title': 'AI சைபர் உதவியாளர்', 
        'welcome': 'வணக்கம்! நான் உங்கள் சைபர் பாதுகாப்பு துணையாக இருக்கிறேன். இன்று நான் உங்களுக்கு எப்படி உதவ முடியும்?', 
        'scan_btn': 'படம்/உரையை ஸ்கேன் செய்க',
        'quiz_btn': 'பாதுகாப்பு வினாடி வினா',
        'risk_labels': {'high': 'அதிக ஆபத்து', 'med': 'நடுத்தர ஆபத்து', 'low': 'குறைந்த ஆபத்து', 'safe': 'பாதுகாப்பானது'},
        'steps_title': 'அடுத்து என்ன செய்ய வேண்டும்:',
        'safe_msg': 'இந்த உள்ளடக்கம் பாதுகாப்பாகத் தெரிகிறது, ஆனால் எப்போதும் விழிப்புடன் இருங்கள்.',
        'spam_msg': 'இது உங்கள் இன்பாக்ஸைக் குவிக்கும் நோக்கம் கொண்ட ஸ்பேம் முயற்சி.',
        'phishing_msg': 'எச்சரிக்கை: இது உங்கள் நற்சான்றிதழ்களைத் திருடுவதற்கான ஃபிஷிங் முயற்சி!',
        'scam_msg': 'ஆபத்து: இது ஒரு நிதி மோசடி முயற்சி.',
        'chat_kb': {
            'phishing': 'ஃபிஷிங் என்பது ஏமாற்றும் நுட்பமாகும், இதில் தாக்குபவர்கள் கடவுச்சொற்கள் அல்லது வங்கி விவரங்கள் போன்ற முக்கியமான தகவல்களை வெளிப்படுத்த பாதிக்கப்பட்டவர்களை ஏமாற்றுவதற்காக மோசடி செய்திகளை அனுப்புகிறார்கள்.',
            'spam': 'ஸ்பேம் என்பது தேவையற்ற மொத்த செய்திகளைக் குறிக்கிறது, வழக்கமாக மின்னஞ்சல், உரை அல்லது சமூக ஊடகங்கள் மூலம் அனுப்பப்படும்.',
            'safe': 'எப்போதும் எச்சரிக்கையாக இருங்கள். ஒரு இணைப்பு சந்தேகத்திற்குரியதாகத் தெரிந்தால், அதை கிளிக் செய்ய வேண்டாம்.',
            'default': 'மோசடிகளைக் கண்டறிய நான் உதவ முடியும். ஃபிஷிங், ஸ்பேம் அல்லது குற்றத்தைப் புகாரளிப்பது பற்றி என்னிடம் கேளுங்கள்!'
        }
    },
    'hi': {
        'title': 'AI साइबर सहायक', 
        'welcome': 'नमस्ते! मैं आपका साइबर सुरक्षा भागीदार हूँ। आज मैं आपकी क्या मदद कर सकता हूँ?', 
        'scan_btn': 'छवि/टेक्स्ट स्कैन करें',
        'quiz_btn': 'सुरक्षा प्रश्नोत्तरी लें',
        'risk_labels': {'high': 'उच्च जोखिम', 'med': 'मध्यम जोखिम', 'low': 'कम जोखिम', 'safe': 'सुरक्षित'},
        'steps_title': 'आगे क्या करना है:',
        'safe_msg': 'यह सामग्री सुरक्षित लगती है, लेकिन हमेशा सतर्क रहें।',
        'spam_msg': 'यह शायद आपके इनबॉक्स को अव्यवस्थित करने के लिए डिज़ाइन किया गया स्पैम प्रयास है।',
        'phishing_msg': 'चेतावनी: यह आपकी क्रेडेंशियल चुराने का एक फ़िशिंग प्रयास है!',
        'scam_msg': 'खतरा: यह एक वित्तीय धोखाधड़ी का प्रयास है।',
        'chat_kb': {
            'phishing': 'फ़िशिंग एक भ्रामक तकनीक है जहाँ हमलावर पीड़ितों को पासवर्ड या बैंकिंग विवरण जैसी संवेदनशील जानकारी प्रकट करने के लिए धोखा देने के लिए धोखाधड़ी वाले संदेश भेजते हैं।',
            'spam': 'स्पैम अवांछित थोक संदेशों को संदर्भित करता है, जो आमतौर पर ईमेल, टेक्स्ट या सोशल मीडिया के माध्यम से भेजे जाते हैं।',
            'safe': 'हमेशा सतर्क रहें। यदि कोई लिंक संदिग्ध लगता है, तो उस पर क्लिक न करें।',
            'default': 'मैं धोखाधड़ी की पहचान करने में मदद कर सकता हूँ। मुझसे फ़िशिंग, स्पैम या अपराध की रिपोर्ट करने के बारे में पूछें!'
        }
    }
}

@app.before_request
def setup_session():
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
            conn.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,description,status) VALUES (?,?,?,?,?,?,?)",
                       (unique_id, request.form['name'], request.form['email'], request.form['phone'], request.form['type'], '', 'Received'))
            conn.commit()
            lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return render_template('complaint_success.html', complaint_id=unique_id, db_id=lid, name=request.form['name'], ctype=request.form['type'])
    return render_template("complaint.html")

@app.route('/track', methods=['GET','POST'])
def track():
    result, error = None, None
    if request.method == 'POST':
        cid = request.form.get('id', '').strip()
        with get_db() as conn:
            if cid.isdigit(): row = conn.execute("SELECT * FROM complaints WHERE id=?", (int(cid),)).fetchone()
            else: row = conn.execute("SELECT * FROM complaints WHERE UPPER(complaint_id)=?", (cid.upper(),)).fetchone()
            if row: 
                result = dict(row)
            else: error = 'Not found.'
    return render_template("track.html", result=result, error=error)

@app.route('/spam', methods=['GET','POST'])
def spam():
    if request.method == 'POST':
        msg = request.form['message']
        load_ml()
        if model:
            res = "Spam" if int(model.predict(vectorizer.transform([msg]))[0]) == 1 else "Not Spam"
            return f"Prediction: {res}"
        return "Model not loaded."
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
    if not txt: return render_template('spam_check.html', ocr_error='No text extracted.')
    load_ml()
    res = "Spam" if model and int(model.predict(vectorizer.transform([txt]))[0]) == 1 else "Unknown"
    return render_template('spam_check.html', ocr_text=txt, ocr_result=res, uploaded=f.filename)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['email'] == "devisrie24aid@vetias.ac.in" and request.form['password'] == "kimtaehyungdevi":
            session['admin'] = request.form['email']
            return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

@app.route('/dashboard')
@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        session['admin'] = 'admin@cyberportal.gov'
    try:
        with get_db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] or 0
            type_rows = conn.execute("SELECT type, COUNT(*) as count FROM complaints GROUP BY type").fetchall() or []
            by_type = [[r[0], r[1]] for r in type_rows]
            status_rows = conn.execute("SELECT status, COUNT(*) as count FROM complaints GROUP BY status").fetchall() or []
            by_status = {r[0]: r[1] for r in status_rows}
            recent_rows = conn.execute("SELECT id, name, email, type, status FROM complaints ORDER BY id DESC LIMIT 10").fetchall() or []
            recent = [[r[0], r[1], r[2], r[3], r[4]] for r in recent_rows]
    except Exception as e:
        print(f"API dashboard error: {e}")
        total = 0
        by_type = []
        by_status = {}
        recent = []
    return render_template('admin_dashboard.html', total=total, by_type=by_type, by_status=by_status, recent=recent, admin_email=session.get('admin', 'admin@cyberportal.gov'))

@app.route('/assistant')
def assistant(): return render_template('assistant.html', t=get_t(), lang=session['lang'])

@app.route('/assistant/analyze', methods=['POST'])
def assistant_analyze():
    msg, t = request.form.get('message', ''), get_t()
    ocr = ""
    uploaded_filename = None
    if 'screenshot' in request.files and request.files['screenshot'].filename:
        f = request.files['screenshot']
        filename = secure_filename(f.filename)
        path = os.path.join(UPLOAD_DIR, filename)
        f.save(path)
        uploaded_filename = filename
        try:
            import pytesseract
            from PIL import Image
            ocr = pytesseract.image_to_string(Image.open(path))
        except: pass
    
    comb = (msg + " " + ocr).strip().lower()
    score, rtype, rlvl, reason = 0, "Safe", "low", t['safe_msg']
    if any(w in comb for w in ['bank', 'login', 'verify', 'password', 'urgent', 'account', 'kyc']): 
        score, rtype, rlvl, reason = 85, "Phishing", "high", t['phishing_msg']
    elif any(w in comb for w in ['win', 'prize', 'lottery', 'claim', 'money', 'crore', 'lakh', 'reward']): 
        score, rtype, rlvl, reason = 90, "Scam", "high", t['scam_msg']
    elif len(comb) > 10:
        score, rtype, rlvl, reason = 40, "Spam", "med", t['spam_msg']
    
    return render_template('assistant.html', t=t, lang=session['lang'], analyzed=True, score=score, res_type=rtype, level=rlvl, reason=reason, message=msg, ocr_text=ocr, uploaded=uploaded_filename)

@app.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    question = request.form.get('question', '').lower()
    t = get_t()
    kb = t['chat_kb']
    answer = kb['default']
    if 'phish' in question: answer = kb['phishing']
    elif 'spam' in question: answer = kb['spam']
    elif 'safe' in question or 'protect' in question: answer = kb['safe']
    return render_template('assistant.html', t=t, lang=session['lang'], chat_mode=True, question=question, answer=answer)

@app.route('/static/uploads/<path:filename>')
def uploads(filename): return send_from_directory(UPLOAD_DIR, filename)

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/games')
def games(): return render_template('games.html')

@app.route('/guidelines')
def guidelines(): return render_template('guidelines.html')

@app.route('/stats')
def stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        by_type = conn.execute("SELECT type, COUNT(*) as count FROM complaints GROUP BY type").fetchall()
        by_status = conn.execute("SELECT status, COUNT(*) as count FROM complaints GROUP BY status").fetchall()
    return render_template('stats.html', total=total, by_type=[dict(r) for r in by_type], by_status=[dict(r) for r in by_status])

# Vercel needs 'app' exported
if __name__ == "__main__":
    app.run(debug=True)
