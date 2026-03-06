from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
import pickle
import os
import sqlite3
import uuid
import datetime

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'templates'))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'static'))
app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)
app.secret_key = os.environ.get('FLASK_SECRET') or 'dev-secret-change-me'
# Detect Vercel environment
IS_VERCEL = os.environ.get('VERCEL') == '1'

if IS_VERCEL:
    UPLOAD_DIR = '/tmp/uploads'
else:
    UPLOAD_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'static', 'uploads'))
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

# Admin credentials (for demo purposes)
ADMIN_USER = "devisrie24aid@vetias.ac.in"
# Hash for 'kimtaehyungdevi'
ADMIN_PASSWORD_HASH = "scrypt:32768:8:1$Yl3E2f49hM8g7e1e$160938fc2909405d8f685c493c0429406f69841804194098"

admin_credentials = {
    'email': ADMIN_USER,
    'password_hash': ADMIN_PASSWORD_HASH
}

# Try MySQL, otherwise fall back to SQLite for local runs
use_mysql = False
cursor = None
db = None
try:
    import mysql.connector
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="cybercrime_db"
    )
    cursor = db.cursor()
    use_mysql = True
except Exception:
    # SQLite fallback
    db_path = os.path.join(os.path.dirname(__file__), '..', 'cybercrime.db')
    db = sqlite3.connect(db_path, check_same_thread=False)
    cursor = db.cursor()
    # Create table if it doesn't exist
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
    # Add complaint_id column if upgrading an existing DB
    try:
        cursor.execute("ALTER TABLE complaints ADD COLUMN complaint_id TEXT")
        db.commit()
    except Exception:
        pass  # Column already exists

# Load ML Model (if available)
model = None
vectorizer = None
try:
    model = pickle.load(open(os.path.join(os.path.dirname(__file__), '..', 'ml', 'spam_model.pkl'), "rb"))
    vectorizer = pickle.load(open(os.path.join(os.path.dirname(__file__), '..', 'ml', 'vectorizer.pkl'), "rb"))
except Exception:
    model = None
    vectorizer = None

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

        try:
            if use_mysql:
                cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (%s,%s,%s,%s,%s,%s)",
                               (unique_id, name, email, phone, ctype, 'Received'))
                db.commit()
                lid = cursor.lastrowid
            else:
                cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                               (unique_id, name, email, phone, ctype, 'Received'))
                db.commit()
                lid = cursor.lastrowid
        except Exception:
            lid = 0

        return render_template('complaint_success.html', complaint_id=unique_id, db_id=lid, name=name, ctype=ctype)

    return render_template("complaint.html")

@app.route('/track', methods=['GET','POST'])
def track():
    result = None
    error = None
    if request.method == 'POST':
        cid = request.form.get('id', '').strip()
        try:
            row = None
            if cid.isdigit():
                # Search by numeric database ID
                if use_mysql:
                    cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE id=%s", (int(cid),))
                else:
                    cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE id=?", (int(cid),))
                row = cursor.fetchone()
            else:
                # Search by CY-XXXXXX tracking ID (case-insensitive)
                if use_mysql:
                    cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE UPPER(complaint_id)=%s", (cid.upper(),))
                else:
                    cursor.execute("SELECT id, complaint_id, name, type, status FROM complaints WHERE UPPER(complaint_id)=?", (cid.upper(),))
                row = cursor.fetchone()

            if row:
                result = {
                    'id': row[0],
                    'complaint_id': row[1] or ('—'),
                    'name': row[2],
                    'type': row[3],
                    'status': row[4]
                }
            else:
                error = 'No complaint found with that Tracking ID. Please check and try again.'
        except Exception as e:
            error = 'Could not retrieve complaint. Please try again.'

    return render_template("track.html", result=result, error=error)

@app.route('/spam', methods=['GET','POST'])
def spam():
    if request.method == 'POST':
        message = request.form['message']
        # Try lazy-loading model files if they exist (no server restart required)
        global model, vectorizer
        if model is None or vectorizer is None:
            try:
                mpath = os.path.join(os.path.dirname(__file__), '..', 'ml', 'spam_model.pkl')
                vpath = os.path.join(os.path.dirname(__file__), '..', 'ml', 'vectorizer.pkl')
                if os.path.exists(mpath) and os.path.exists(vpath):
                    model = pickle.load(open(mpath, 'rb'))
                    vectorizer = pickle.load(open(vpath, 'rb'))
            except Exception:
                model = None
                vectorizer = None

        if model is None or vectorizer is None:
            return "Model not available. Run the training script in /ml to create models."

        data = vectorizer.transform([message])
        prediction = model.predict(data)

        result = "Spam" if int(prediction[0]) == 1 else "Not Spam"
        return f"Prediction: {result}"

    return render_template("spam_check.html")


@app.route('/spam/upload', methods=['POST'])
def spam_upload():
    if 'screenshot' not in request.files:
        return "No file uploaded", 400
    f = request.files['screenshot']
    if f.filename == '':
        return "Empty filename", 400
    filename = secure_filename(f.filename)
    save_path = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    f.save(save_path)

    # Try OCR using pytesseract
    ocr_text = None
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(save_path)
        ocr_text = pytesseract.image_to_string(img)
    except Exception:
        ocr_text = None

    # Combine text from form (if client-side OCR was successful) and server-side OCR
    form_text = request.form.get('message', '')
    final_text = (form_text + " " + (ocr_text or "")).strip()

    if not final_text:
        return render_template('spam_check.html', ocr_error='No text could be extracted from image. Please enter manually.')

    # Use existing model to predict if text is spam
    global model, vectorizer
    if model is None or vectorizer is None:
        try:
            mpath = os.path.join(os.path.dirname(__file__), '..', 'ml', 'spam_model.pkl')
            vpath = os.path.join(os.path.dirname(__file__), '..', 'ml', 'vectorizer.pkl')
            if os.path.exists(mpath) and os.path.exists(vpath):
                model = pickle.load(open(mpath, 'rb'))
                vectorizer = pickle.load(open(vpath, 'rb'))
        except Exception:
            model = None
            vectorizer = None

    if model is None or vectorizer is None:
        return render_template('spam_check.html', ocr_text=final_text, ocr_error='Model not available to classify text.')

    data = vectorizer.transform([final_text])
    prediction = model.predict(data)
    result = "Spam" if int(prediction[0]) == 1 else "Not Spam"

    return render_template('spam_check.html', ocr_text=final_text, ocr_result=result, uploaded=filename)


@app.route('/static/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Direct check against hardcoded constants for reliability
        if email == ADMIN_USER and password == "kimtaehyungdevi":
            session['admin'] = email
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'Invalid credentials.'
    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('home'))


@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    try:
        cursor.execute("SELECT COUNT(*) FROM complaints")
        total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT type, COUNT(*) FROM complaints GROUP BY type")
        by_type = cursor.fetchall() or []
        cursor.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
        status_rows = cursor.fetchall() or []
        by_status = {row[0]: row[1] for row in status_rows}
        
        # Fetch recent 10 complaints
        cursor.execute("SELECT id, name, email, type, status FROM complaints ORDER BY id DESC LIMIT 10")
        recent = cursor.fetchall() or []
    except Exception:
        total = 0
        by_type = []
        by_status = {}
        recent = []
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
    except Exception:
        total = 0
        by_type = []
        by_status = []
    return render_template('stats.html', total=total, by_type=by_type, by_status=by_status)

@app.route('/report/save', methods=['POST'])
def report_save():
    unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    try:
        if use_mysql:
            cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (%s,%s,%s,%s,%s,%s)",
                           (unique_id, "AI Report", '', '', 'Spam Report', 'Received'))
        else:
            cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                           (unique_id, "AI Report", '', '', 'Spam Report', 'Received'))
        db.commit()
        return redirect(url_for('assistant', lang=request.form.get('lang', 'en')))
    except Exception:
        return "Failed to save report"

@app.route('/report/flag', methods=['POST'])
def report_flag():
    unique_id = f"CY-{datetime.datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    try:
        if use_mysql:
            cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (%s,%s,%s,%s,%s,%s)",
                           (unique_id, "Flagged Content", '', '', 'Flagged', 'Under Review'))
        else:
            cursor.execute("INSERT INTO complaints (complaint_id,name,email,phone,type,status) VALUES (?,?,?,?,?,?)",
                           (unique_id, "Flagged Content", '', '', 'Flagged', 'Under Review'))
        db.commit()
        return redirect(url_for('assistant', lang=request.form.get('lang', 'en')))
    except Exception:
        return "Failed to flag content"

# AI Assistant & Awareness Data
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

@app.route('/assistant')
def assistant():
    return render_template('assistant.html', t=get_t(), lang=session['lang'])

@app.route('/assistant/analyze', methods=['POST'])
def assistant_analyze():
    message = request.form.get('message', '')
    t = get_t()
    lang = session['lang']
    
    ocr_text = ""
    uploaded_filename = None
    
    # Handle Screenshot Upload
    if 'screenshot' in request.files:
        f = request.files['screenshot']
        if f and f.filename != '':
            filename = secure_filename(f.filename)
            save_path = os.path.join(UPLOAD_DIR, filename)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            f.save(save_path)
            uploaded_filename = filename
            
            # Perform OCR
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(save_path)
                ocr_text = pytesseract.image_to_string(img)
            except Exception:
                ocr_text = ""

    # Combine text for analysis
    combined_message = (message + " " + ocr_text).strip().lower()
    
    # Analysis Logic
    risk_score = 0
    result_type = "Safe"
    reason = t['safe_msg']
    level = "low"
    
    if not combined_message:
        return render_template('assistant.html', t=t, lang=lang, analyzed=False, error="No text or image content provided.")

    if any(word in combined_message for word in ['bank', 'login', 'verify', 'update', 'password', 'urgent', 'account', 'kyc']):
        risk_score = 85
        result_type = "Phishing"
        reason = t['phishing_msg']
        level = "high"
    elif any(word in combined_message for word in ['win', 'prize', 'lottery', 'claim', 'money', 'crore', 'lakh', 'reward']):
        risk_score = 90
        result_type = "Scam"
        reason = t['scam_msg']
        level = "high"
    elif len(combined_message) > 10:
        risk_score = 40
        result_type = "Spam"
        reason = t['spam_msg']
        level = "med"
        
    return render_template('assistant.html', 
                          t=t, lang=lang,
                          analyzed=True,
                          score=risk_score,
                          res_type=result_type,
                          reason=reason,
                          level=level,
                          message=message,
                          ocr_text=ocr_text,
                          uploaded=uploaded_filename)

@app.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    question = request.form.get('question', '').lower()
    t = get_t()
    lang = session['lang']
    kb = t.get('chat_kb', t['chat_kb'])
    
    answer = kb['default']
    if 'phish' in question:
        answer = kb['phishing']
    elif 'spam' in question:
        answer = kb['spam']
    elif 'safe' in question or 'protect' in question:
        answer = kb['safe']
    
    return render_template('assistant.html', t=t, lang=lang, chat_mode=True, question=question, answer=answer)

@app.route('/games')
def games():
    return render_template('games.html')

@app.route('/guidelines')
def guidelines():
    return render_template('guidelines.html')

if __name__ == "__main__":
    app.run(debug=True)
