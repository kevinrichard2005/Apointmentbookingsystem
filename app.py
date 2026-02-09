from flask import Flask, render_template, request, redirect, session, url_for, flash, send_from_directory, jsonify
import sqlite3
import os
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_mail import Mail, Message

app = Flask(__name__, static_folder="static", template_folder=".")

app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_development_only")
DB_NAME = "database.db"

# ========== EMAIL CONFIGURATION ==========
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'MediBook Alerts <noreply@medibook.com>')

mail = Mail(app)

def send_email(subject, recipient, body_html):
    """Helper to send email with fallback to console logging"""
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"📧 EMAIL LOG (Simulated):\nSubject: {subject}\nTo: {recipient}\nContent: {body_html}\n(Configure MAIL_USERNAME/PASSWORD to send real emails)")
        return
    try:
        msg = Message(subject, recipients=[recipient])
        msg.html = body_html
        mail.send(msg)
        print(f"✅ Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Email error: {e}")

# ========== FIX FOR STATIC FILES ==========
import shutil

def setup_static_files():
    """Ensure static files are set up properly"""
    if not os.path.exists("static"):
        os.makedirs("static")
        print("✅ Created static folder")
    
    if os.path.exists("style.css") and not os.path.exists("static/style.css"):
        shutil.copy("style.css", "static/style.css")
        print("✅ Copied style.css to static folder")
    
    if os.path.exists("static/style.css"):
        print("✅ style.css exists in static folder")
    
    if os.path.exists("style.css"):
        print("✅ style.css exists in root folder")

@app.route('/style.css')
def serve_css():
    """Serve CSS from either static folder or root"""
    if os.path.exists('static/style.css'):
        return send_from_directory('static', 'style.css')
    elif os.path.exists('style.css'):
        return send_from_directory('.', 'style.css')
    else:
        return "/* Basic CSS */ body { background: #0b1220; color: white; }", 200, {'Content-Type': 'text/css'}

@app.route('/debug-files')
def debug_files():
    """Debug endpoint to see file structure"""
    result = []
    result.append(f"<h3>Current Directory: {os.getcwd()}</h3>")
    
    result.append("<h4>Files in root:</h4>")
    for item in os.listdir('.'):
        if os.path.isdir(item):
            result.append(f"📁 {item}/")
            if item == 'static':
                if os.path.exists('static'):
                    result.append("Contents of static/:")
                    for subitem in os.listdir('static'):
                        result.append(f"  - {subitem}")
        else:
            result.append(f"📄 {item}")
    
    return "<br>".join(result)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)
# ========== END FIX ==========

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialization TEXT NOT NULL,
            available_days TEXT NOT NULL,
            time_slots TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(doctor_id) REFERENCES doctors(id)
        )
    """)

    # Add UNIQUE constraint to prevent double booking
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS unique_doctor_time_slot 
            ON appointments(doctor_id, date, time) 
            WHERE status != 'Cancelled'
        """)
        print("✅ Created unique constraint for appointments")
    except Exception as e:
        print(f"Note: Index creation - {e}")

    # Create chat_logs table for AI chatbot
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_message TEXT,
            ai_response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create admin if not exists
    cursor.execute("SELECT * FROM users WHERE email=?", ("admin@gmail.com",))
    admin = cursor.fetchone()
    if not admin:
        cursor.execute("""
            INSERT INTO users(name, email, password, role)
            VALUES(?,?,?,?)
        """, ("Admin", "admin@gmail.com", generate_password_hash("admin123"), "admin"))
        print("✅ Admin user created")

    # Add 7 sample doctors if table is empty
    cursor.execute("SELECT COUNT(*) as count FROM doctors")
    if cursor.fetchone()["count"] == 0:
        sample_doctors = [
            ("Dr. Sarah Wilson", "Cardiologist", "Mon, Wed, Fri", "9:00 AM - 12:00 PM, 2:00 PM - 5:00 PM"),
            ("Dr. Michael Chen", "Dentist", "Tue, Thu, Sat", "10:00 AM - 1:00 PM, 3:00 PM - 6:00 PM"),
            ("Dr. Emily Johnson", "Pediatrician", "Mon, Tue, Wed, Thu, Fri", "8:00 AM - 4:00 PM"),
            ("Dr. Robert Brown", "Orthopedic Surgeon", "Mon, Wed, Fri", "10:00 AM - 2:00 PM, 4:00 PM - 7:00 PM"),
            ("Dr. Priya Sharma", "Gynecologist", "Tue, Thu, Sat", "9:00 AM - 1:00 PM, 3:00 PM - 6:00 PM"),
            ("Dr. David Lee", "Dermatologist", "Mon, Wed, Fri", "11:00 AM - 3:00 PM, 5:00 PM - 8:00 PM"),
            ("Dr. James Miller", "General Physician", "Mon-Sat", "9:00 AM - 1:00 PM, 4:00 PM - 7:00 PM")
        ]
        for doctor in sample_doctors:
            cursor.execute("""
                INSERT INTO doctors(name, specialization, available_days, time_slots)
                VALUES(?,?,?,?)
            """, doctor)
        print("✅ 7 sample doctors added to database!")

    conn.commit()
    conn.close()


# -------------------- AI CHATBOT FUNCTIONS (YOUR ORIGINAL BUT ENHANCED) --------------------
def ai_response(user_message, user_id=None):
    """Generate AI response based on user message - ENHANCED KEYWORD VERSION"""
    message_lower = user_message.lower().strip()
    
    # ========== EMERGENCY CHECK (PRIORITY) ==========
    emergency_keywords = ["emergency", "urgent", "immediate help", "critical", 
                         "heart attack", "stroke", "bleeding", "unconscious", 
                         "chest pain", "can't breathe", "severe pain", "dying",
                         "911", "ambulance", "hospital now"]
    
    for keyword in emergency_keywords:
        if keyword in message_lower:
            return "🚨 **EMERGENCY NOTICE** 🚨\n\nIf this is a medical emergency, please:\n\n1. **CALL YOUR LOCAL EMERGENCY NUMBER IMMEDIATELY**\n2. Go to the nearest emergency room\n3. Do NOT wait for online assistance\n\n**Emergency Numbers:**\n• USA/Canada: 911\n• UK: 999\n• Australia: 000\n• EU: 112\n\nThis chatbot is for appointment booking only and cannot handle emergencies."

    # ========== GREETINGS ==========
    greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening", "greetings"]
    for greeting in greetings:
        if greeting in message_lower:
            responses = [
                "Hello! I'm MediBook AI Assistant. How can I help you with your healthcare needs today?",
                "Hi there! Welcome to MediBook. How can I assist you with appointments or medical queries?",
                "Hello! I'm here to help you book appointments, find doctors, or answer medical questions."
            ]
            return random.choice(responses)

    # ========== THANKS ==========
    thanks = ["thank you", "thanks", "appreciate", "helpful", "thank"]
    for thank in thanks:
        if thank in message_lower:
            responses = [
                "You're welcome! I'm glad I could help. Don't hesitate to ask if you need anything else.",
                "Happy to help! Remember, I'm here 24/7 to assist with your healthcare needs.",
                "My pleasure! Let me know if you have any other questions about appointments or healthcare."
            ]
            return random.choice(responses)

    # ========== APPOINTMENT BOOKING ==========
    appointment_keywords = ["book appointment", "schedule appointment", "make appointment", 
                          "see doctor", "want to book", "need appointment", "book a visit",
                          "make booking", "schedule visit", "book doctor"]
    
    for keyword in appointment_keywords:
        if keyword in message_lower:
            conn = get_db()
            doctors_count = conn.execute("SELECT COUNT(*) as count FROM doctors").fetchone()["count"]
            conn.close()
            
            responses = [
                f"I can help you book an appointment! We have {doctors_count} verified doctors available.\n\n**Steps to book:**\n1. Go to 'Doctors' page to browse available doctors\n2. Click 'Book Now' on any doctor's card\n3. Select your preferred date and time\n4. Confirm booking\n\nYou'll receive instant confirmation!",
                f"To book an appointment:\n1. Visit the 'Doctors' section\n2. Choose from {doctors_count} specialists\n3. Select date and time\n4. Get confirmation\n\nWhat type of specialist are you looking for? I can help you find the right doctor."
            ]
            return random.choice(responses)

    # ========== DOCTOR SEARCH ==========
    doctor_keywords = ["find doctor", "search doctor", "available doctors", "specialists", 
                      "which doctors", "looking for doctor", "need doctor", "doctor available"]
    
    for keyword in doctor_keywords:
        if keyword in message_lower:
            conn = get_db()
            doctors = conn.execute("SELECT specialization, COUNT(*) as count FROM doctors GROUP BY specialization").fetchall()
            conn.close()
            
            specialties = ", ".join([f"{doc['specialization']} ({doc['count']})" for doc in doctors])
            
            return f"**Available Specialists:**\n\n{specialties}\n\n**How to find a doctor:**\n1. Visit 'Doctors' page\n2. Browse by specialization\n3. Check availability and timings\n4. Click 'Book Now' to schedule\n\nWhich specialty are you interested in?"

    # ========== CANCELLATION ==========
    cancel_keywords = ["cancel appointment", "reschedule", "change appointment", "cancel booking",
                      "postpone", "cancel my", "need to cancel", "want to cancel"]
    
    for keyword in cancel_keywords:
        if keyword in message_lower:
            if user_id:
                conn = get_db()
                pending_appointments = conn.execute("""
                    SELECT COUNT(*) as count FROM appointments 
                    WHERE user_id = ? AND status IN ('Pending', 'Approved')
                """, (user_id,)).fetchone()["count"]
                conn.close()
                
                if pending_appointments > 0:
                    return f"**Cancellation Process:**\n\nYou have {pending_appointments} appointment(s) that can be cancelled.\n\n**Steps:**\n1. Go to your Dashboard\n2. Find the appointment in the table\n3. Click 'Cancel' button\n4. Confirm cancellation\n\n**Note:** You can only cancel appointments with 'Pending' or 'Approved' status."
            
            return "**To cancel or reschedule:**\n1. Go to your Dashboard\n2. Find the appointment\n3. Click 'Cancel' (if status is Pending/Approved)\n4. For rescheduling: Cancel first, then book new slot\n\nVisit your Dashboard to manage appointments."

    # ========== APPOINTMENT STATUS ==========
    status_keywords = ["my appointment", "appointment status", "my bookings", "check appointment",
                      "status of", "when is my", "upcoming appointment"]
    
    for keyword in status_keywords:
        if keyword in message_lower and user_id:
            conn = get_db()
            appointments = conn.execute("""
                SELECT a.date, a.time, a.status, d.name 
                FROM appointments a 
                JOIN doctors d ON a.doctor_id = d.id 
                WHERE a.user_id = ? 
                ORDER BY a.date DESC LIMIT 5
            """, (user_id,)).fetchall()
            conn.close()
            
            if appointments:
                response = "**Your Recent Appointments:**\n\n"
                for app in appointments:
                    status_icon = "🟡" if app['status'] == 'Pending' else "🟢" if app['status'] == 'Approved' else "🔵" if app['status'] == 'Completed' else "🔴"
                    response += f"{status_icon} **{app['date']} at {app['time']}**\nDr. {app['name']} - Status: **{app['status']}**\n\n"
                response += "Visit your **Dashboard** for full details and management options."
                return response
            else:
                return "You don't have any appointments yet. Would you like to book one? Visit the **'Doctors'** page to get started!"

    # ========== MEDICATION ==========
    med_keywords = ["medicine", "prescription", "drug", "pharmacy", "meds", "pill", "tablet",
                   "dosage", "side effects", "take medicine"]
    
    for keyword in med_keywords:
        if keyword in message_lower:
            return "**Medication Guidance:**\n\n⚠️ **Important:** I cannot prescribe medication or provide medical advice.\n\n**For medication queries:**\n1. Consult with your doctor during appointment\n2. Visit a licensed pharmacist\n3. Never self-medicate without professional advice\n\nI can help you book an appointment with a doctor who can assist with medication questions."

    # ========== SYMPTOMS ==========
    symptom_keywords = ["fever", "headache", "cough", "pain", "fatigue", "rash", "cold", "flu",
                       "nausea", "vomiting", "diarrhea", "dizziness", "back pain", "stomach pain",
                       "sore throat", "allergy", "itchy", "swelling", "bleeding", "bruise"]
    
    for keyword in symptom_keywords:
        if keyword in message_lower:
            conn = get_db()
            # Find relevant specialist based on symptom
            specialist_map = {
                "fever": "General Physician",
                "headache": "General Physician or Neurologist",
                "cough": "General Physician or Pulmonologist",
                "pain": "General Physician",
                "rash": "Dermatologist",
                "cold": "General Physician",
                "flu": "General Physician",
                "nausea": "General Physician or Gastroenterologist",
                "back pain": "Orthopedic Surgeon",
                "stomach pain": "General Physician or Gastroenterologist",
                "sore throat": "General Physician or ENT Specialist",
                "allergy": "General Physician or Allergist"
            }
            
            recommended_specialist = "General Physician"
            for symptom, specialist in specialist_map.items():
                if symptom in message_lower:
                    recommended_specialist = specialist
                    break
            
            doctors = conn.execute("""
                SELECT name, specialization FROM doctors 
                WHERE specialization LIKE ? 
                LIMIT 3
            """, (f"%{recommended_specialist.split()[0]}%",)).fetchall()
            conn.close()
            
            response = "**Symptom Guidance:**\n\n"
            response += "⚠️ **Disclaimer:** This is general information only, not medical advice.\n\n"
            response += "**Recommendation:** Consult a healthcare professional for accurate diagnosis.\n\n"
            
            if doctors:
                response += f"**Available {recommended_specialist}s:**\n"
                for doc in doctors:
                    response += f"• Dr. {doc['name']} ({doc['specialization']})\n"
                response += "\nVisit **'Doctors'** page to book an appointment."
            else:
                response += f"Book an appointment with a **{recommended_specialist}** for proper evaluation."
            
            return response

    # ========== CLINIC HOURS ==========
    hour_keywords = ["clinic hours", "working hours", "open", "availability", "timing", 
                    "when open", "close", "operating hours", "business hours"]
    
    for keyword in hour_keywords:
        if keyword in message_lower:
            return "**Clinic Hours:**\n\n• **Weekdays (Mon-Fri):** 9:00 AM - 7:00 PM\n• **Saturdays:** 10:00 AM - 4:00 PM\n• **Sundays:** Emergency services only\n• **Holidays:** Check with specific clinic\n\n**Note:** Individual doctor hours may vary. Check doctor profiles for specific availability."

    # ========== CONTACT INFO ==========
    contact_keywords = ["contact", "phone", "email", "support", "help", "customer service",
                       "reach", "get in touch", "address", "location", "where are you"]
    
    for keyword in contact_keywords:
        if keyword in message_lower:
            return "**Contact Information:**\n\n📧 **Email:** support@medibook.com\n📞 **Phone:** +1 (555) 123-4567\n📍 **Address:** 123 Medical Street, Health City\n⏰ **Support Hours:** Mon-Fri, 9AM-6PM\n\n**For Urgent Matters:**\n• Technical issues: tech@medibook.com\n• Billing: billing@medibook.com\n• Feedback: feedback@medibook.com"

    # ========== PRICING ==========
    price_keywords = ["price", "cost", "fee", "charge", "how much", "payment", "bill", 
                     "insurance", "covered", "afford"]
    
    for keyword in price_keywords:
        if keyword in message_lower:
            return "**Pricing Information:**\n\n💰 **Consultation Fees:**\n• Vary by doctor and specialization\n• Typically range: $100 - $300\n• Exact fees shown when booking\n\n**Insurance:**\n• Most major insurances accepted\n• Check with specific doctor's clinic\n• Bring insurance card to appointment\n\n**Payment Methods:**\n• Credit/Debit Cards\n• Health Savings Accounts (HSA)\n• Cash (at clinic)\n• Insurance co-pays"

    # ========== LOCATION ==========
    location_keywords = ["location", "where", "address", "directions", "map", "how to reach",
                        "clinic location", "hospital location", "find clinic"]
    
    for keyword in location_keywords:
        if keyword in message_lower:
            return "**Location & Directions:**\n\n📍 **Main Clinic:**\n123 Medical Street\nHealth City, HC 10001\n\n**Branch Clinics:**\n1. Downtown Health Center: 456 Business Ave\n2. Northside Medical: 789 Park Road\n3. Westend Clinic: 321 Oak Street\n\n**Parking:** Available at all locations\n**Public Transport:** Bus routes 101, 205, 308\n**Accessibility:** Wheelchair accessible"

    # ========== DOCTOR-SPECIFIC QUERIES ==========
    specialties = ["cardiologist", "dentist", "pediatrician", "orthopedic", "gynecologist", 
                   "dermatologist", "psychiatrist", "ent", "ophthalmologist", "physician",
                   "cardiology", "dental", "pediatrics", "orthopedics", "gynecology",
                   "dermatology", "psychiatry", "eye", "general", "neurologist", 
                   "gastroenterologist", "pulmonologist", "urologist", "allergist"]
    
    for specialty in specialties:
        if specialty in message_lower:
            conn = get_db()
            doctors = conn.execute("""
                SELECT name, specialization, available_days, time_slots 
                FROM doctors WHERE specialization LIKE ? OR specialization LIKE ? 
                LIMIT 3
            """, (f"%{specialty}%", f"%{specialty[:-1]}%")).fetchall()
            conn.close()
            
            if doctors:
                response = f"**{specialty.title()} Specialists Available:**\n\n"
                for doc in doctors:
                    response += f"👨‍⚕️ **Dr. {doc['name']}**\n"
                    response += f"• Specialty: {doc['specialization']}\n"
                    response += f"• Available: {doc['available_days']}\n"
                    response += f"• Timings: {doc['time_slots']}\n\n"
                response += "Visit **'Doctors'** page to book appointment with any of these specialists."
                return response
            else:
                return f"**Specialist Search:**\n\nWe currently don't have {specialty} specialists available.\n\n**Suggestions:**\n1. Check back later for new doctors\n2. Contact support for referrals\n3. Try searching for similar specialties\n\n**Alternative:** Visit 'Doctors' page to see all available specialists."

    # ========== GENERAL HELP ==========
    help_keywords = ["help", "what can you do", "how can you help", "capabilities", 
                    "features", "assist", "guide", "what help", "need help"]
    
    for keyword in help_keywords:
        if keyword in message_lower:
            return "**How I Can Help You:**\n\n🔍 **Find Doctors:** Search by specialty\n📅 **Book Appointments:** Easy scheduling\n🗓️ **Manage Bookings:** View, cancel, reschedule\nℹ️ **Clinic Info:** Hours, contact, location\n💊 **Medication Guidance:** General information\n🤒 **Symptom Check:** Basic health guidance\n📞 **Support:** Contact information\n\n**Ask me anything about:**\n• Booking appointments\n• Finding doctors\n• Clinic information\n• Basic health questions"

    # ========== DEFAULT RESPONSES ==========
    default_responses = [
        "I'm here to help with medical appointments and healthcare information. Could you be more specific about what you need help with?",
        
        "I can help you with:\n• Booking appointments with doctors\n• Finding specialists by category\n• Checking appointment status\n• Basic medical guidance\n• Clinic hours and contact info\n\nWhat would you like to know?",
        
        "I'm your MediBook assistant! I specialize in helping with appointment booking, doctor information, and basic healthcare queries. How can I assist you today?",
        
        "Let me help you! I can guide you through booking appointments, finding the right doctor, or answering questions about our services. What would you like to know?",
        
        "I understand you're looking for information. Could you tell me more about what you need help with? I can assist with:\n• Appointment booking\n• Doctor search\n• Clinic information\n• General health questions"
    ]
    
    return random.choice(default_responses)

def log_chat(user_id, user_message, ai_response):
    """Log chat conversations to database"""
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO chat_logs (user_id, user_message, ai_response)
            VALUES (?, ?, ?)
        """, (user_id, user_message[:500], ai_response[:1000]))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging chat: {e}")

@app.route("/")
def index():
    conn = get_db()
    
    # Get stats for dashboard
    users_count = conn.execute("SELECT COUNT(*) as total FROM users WHERE role='user'").fetchone()["total"]
    doctors_count = conn.execute("SELECT COUNT(*) as total FROM doctors").fetchone()["total"]
    appointments_count = conn.execute("SELECT COUNT(*) as total FROM appointments WHERE status!='Cancelled'").fetchone()["total"]
    
    # Get some doctors for display
    doctors = conn.execute("SELECT * FROM doctors ORDER BY id DESC LIMIT 3").fetchall()
    
    # Get today's booked slots count
    today = datetime.now().strftime("%Y-%m-%d")
    booked_slots = conn.execute("SELECT COUNT(*) as count FROM appointments WHERE date = ? AND status != 'Cancelled'", (today,)).fetchone()["count"]
    
    conn.close()
    
    stats = {
        "users": users_count,
        "doctors": doctors_count,
        "appointments": appointments_count
    }
    
    return render_template("index.html", 
                         stats=stats, 
                         doctors_count=doctors_count,
                         booked_slots=booked_slots)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        try:
            conn = get_db()
            conn.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                         (name, email, password))
            conn.commit()
            conn.close()
            
            # Send Welcome Email
            send_email(
                "Welcome to MediBook! 🩺",
                email,
                f"<h2>Hello {name}!</h2><p>Thank you for joining MediBook. Your account is now active.</p><p>You can now book appointments with our world-class specialists.</p><br><a href='#' style='padding:10px 20px; background:#4f46e5; color:white; text-decoration:none; border-radius:10px;'>Go to Dashboard</a>"
            )
            
            flash("✅ Registration successful! Please login.", "success")
            return redirect("/login")
        except:
            flash("❌ Email already exists!", "danger")
            return redirect("/register")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]

            flash("✅ Login Successful!", "success")

            if user["role"] == "admin":
                return redirect("/admin")
            return redirect("/dashboard")

        flash("❌ Invalid email or password!", "danger")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("✅ Logged out successfully!", "success")
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    appointments = conn.execute("""
        SELECT appointments.*, doctors.name as doctor_name, doctors.specialization as doctor_specialization
        FROM appointments
        JOIN doctors ON doctors.id = appointments.doctor_id
        WHERE appointments.user_id = ?
        ORDER BY appointments.id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()

    return render_template("user_dashboard.html", appointments=appointments)


@app.route("/doctors")
def doctors():
    conn = get_db()
    doctors = conn.execute("SELECT * FROM doctors ORDER BY id DESC").fetchall()
    
    # Get today's booked slots count for each doctor
    today = datetime.now().strftime("%Y-%m-%d")
    booked_counts = {}
    booked_slots_data = conn.execute("""
        SELECT doctor_id, COUNT(*) as count 
        FROM appointments 
        WHERE date = ? AND status != 'Cancelled'
        GROUP BY doctor_id
    """, (today,)).fetchall()
    
    for row in booked_slots_data:
        booked_counts[row["doctor_id"]] = row["count"]
    
    conn.close()
    
    return render_template("doctors.html", 
                          doctors=doctors, 
                          booked_counts=booked_counts,
                          today=today)


@app.route("/book/<int:doctor_id>", methods=["GET", "POST"])
def book_appointment(doctor_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    doctor = conn.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()

    if not doctor:
        flash("❌ Doctor not found!", "danger")
        conn.close()
        return redirect("/doctors")

    if request.method == "POST":
        date = request.form["date"]
        time = request.form["time"]
        
        # Validate time format
        try:
            time_obj = datetime.strptime(time.strip().upper(), "%I:%M %p")
            time = time_obj.strftime("%I:%M %p")
        except ValueError:
            flash("❌ Please enter time in format like '10:00 AM' or '2:30 PM'", "danger")
            conn.close()
            return redirect(f"/book/{doctor_id}")
        
        # Check if the user already has an appointment at this time (any doctor)
        existing_user_appointment = conn.execute("""
            SELECT * FROM appointments 
            WHERE user_id = ? AND date = ? AND time = ? 
            AND status != 'Cancelled'
        """, (session["user_id"], date, time)).fetchone()
        
        if existing_user_appointment:
            flash("❌ You already have an appointment booked at this time! Please choose another slot.", "danger")
            conn.close()
            return redirect(f"/book/{doctor_id}")
        
        # Check if the slot is already booked with this doctor
        existing_doctor_appointment = conn.execute("""
            SELECT * FROM appointments 
            WHERE doctor_id = ? AND date = ? AND time = ? 
            AND status != 'Cancelled'
        """, (doctor_id, date, time)).fetchone()
        
        if existing_doctor_appointment:
            flash("❌ This time slot is already booked! Please choose another time.", "danger")
            conn.close()
            return redirect(f"/book/{doctor_id}")
        
        try:
            # Try to insert the appointment
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO appointments(user_id, doctor_id, date, time, status)
                VALUES(?,?,?,?,?)
            """, (session["user_id"], doctor_id, date, time, "Pending"))
            conn.commit()
            
            # Send Booking Confirmation Email
            user_email = conn.execute("SELECT email FROM users WHERE id=?", (session["user_id"],)).fetchone()["email"]
            send_email(
                "Appointment Requested! 📅",
                user_email,
                f"<h3>Booking Request Received</h3><p>Your appointment request for <b>Dr. {doctor['name']}</b> on <b>{date}</b> at <b>{time}</b> is currently <b>PENDING</b>.</p><p>We will notify you once the doctor approves it!</p>"
            )
            
            flash("✅ Appointment booked successfully!", "success")
            
        except sqlite3.IntegrityError as e:
            # This catches the unique constraint violation
            if "unique_doctor_time_slot" in str(e):
                flash("❌ This time slot was just booked by someone else. Please choose another time.", "danger")
            else:
                flash("❌ An error occurred. Please try again.", "danger")
        
        conn.close()
        return redirect("/dashboard")

    # GET request - show booking form
    # Get all booked slots for this doctor
    booked_slots_data = conn.execute("""
        SELECT date, time FROM appointments 
        WHERE doctor_id = ? AND status != 'Cancelled'
        AND date >= date('now')
        ORDER BY date, time
    """, (doctor_id,)).fetchall()
    
    # Get user's upcoming appointments
    user_upcoming_data = conn.execute("""
        SELECT date, time, doctors.name as doctor_name 
        FROM appointments 
        JOIN doctors ON doctors.id = appointments.doctor_id
        WHERE user_id = ? AND status != 'Cancelled'
        AND date >= date('now')
        ORDER BY date, time
    """, (session["user_id"],)).fetchall()
    
    # Get today's date for min attribute
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Convert to regular dictionaries
    booked_slots = []
    for slot in booked_slots_data:
        booked_slots.append({"date": slot["date"], "time": slot["time"]})
    
    user_upcoming = []
    for app in user_upcoming_data:
        user_upcoming.append({
            "date": app["date"], 
            "time": app["time"],
            "doctor_name": app["doctor_name"]
        })
    
    conn.close()
    
    return render_template("book_appointment.html", 
                         doctor=doctor, 
                         booked_slots=booked_slots,
                         user_upcoming=user_upcoming,
                         today=today)


@app.route("/check-slot-availability/<int:doctor_id>", methods=["POST"])
def check_slot_availability(doctor_id):
    """API endpoint to check slot availability in real-time"""
    if "user_id" not in session:
        return jsonify({"available": False, "message": "Please login first"})
    
    data = request.get_json()
    date = data.get("date")
    time = data.get("time")
    
    if not date or not time:
        return jsonify({"available": False, "message": "Date and time required"})
    
    # Validate time format
    try:
        time_obj = datetime.strptime(time.strip().upper(), "%I:%M %p")
        time = time_obj.strftime("%I:%M %p")
    except ValueError:
        return jsonify({"available": False, "message": "Invalid time format. Use '10:00 AM' format"})
    
    conn = get_db()
    
    # Check user's own appointments
    user_conflict = conn.execute("""
        SELECT * FROM appointments 
        WHERE user_id = ? AND date = ? AND time = ? 
        AND status != 'Cancelled'
    """, (session["user_id"], date, time)).fetchone()
    
    if user_conflict:
        conn.close()
        return jsonify({
            "available": False, 
            "message": "You already have an appointment at this time!"
        })
    
    # Check doctor's availability
    doctor_conflict = conn.execute("""
        SELECT * FROM appointments 
        WHERE doctor_id = ? AND date = ? AND time = ? 
        AND status != 'Cancelled'
    """, (doctor_id, date, time)).fetchone()
    
    conn.close()
    
    if doctor_conflict:
        return jsonify({
            "available": False, 
            "message": "This time slot is already booked!"
        })
    
    return jsonify({
        "available": True, 
        "message": "Slot is available!"
    })


@app.route("/cancel/<int:appointment_id>")
def cancel_appointment(appointment_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    conn.execute("UPDATE appointments SET status='Cancelled' WHERE id=? AND user_id=?",
                 (appointment_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash("✅ Appointment cancelled!", "success")
    return redirect("/dashboard")


# -------------------- AI CHATBOT ROUTES --------------------
@app.route("/chatbot")
def chatbot():
    """AI Chatbot page"""
    return render_template("chatbot_interface.html")

@app.route("/ai/chat", methods=["POST"])
def chat():
    """Handle chat messages"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Get user_id from session if available
        user_id = session.get('user_id') if 'user_id' in session else None
        
        # Generate AI response
        response = ai_response(user_message, user_id)
        
        # Log the conversation
        log_chat(user_id, user_message, response)
        
        return jsonify({
            'response': response,
            'timestamp': datetime.now().strftime("%H:%M")
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/ai/chat/suggestions", methods=["GET"])
def get_suggestions():
    """Get quick suggestion questions"""
    suggestions = [
        "How do I book an appointment?",
        "Find me a cardiologist",
        "Cancel my appointment",
        "Clinic working hours",
        "Contact information",
        "My appointment status",
        "What doctors are available?",
        "How to reschedule appointment?",
        "Book with a dentist",
        "Emergency contact",
        "Medicine for headache",
        "Fever and cough symptoms",
        "Clinic location",
        "Appointment fees",
        "Available time slots"
    ]
    
    return jsonify({'suggestions': suggestions})


# -------------------- ADMIN ROUTES --------------------
@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()

    users_count = conn.execute("SELECT COUNT(*) as total FROM users WHERE role='user'").fetchone()["total"]
    doctors_count = conn.execute("SELECT COUNT(*) as total FROM doctors").fetchone()["total"]
    appointments_count = conn.execute("SELECT COUNT(*) as total FROM appointments").fetchone()["total"]

    appointments = conn.execute("""
        SELECT appointments.*, users.name as user_name, doctors.name as doctor_name
        FROM appointments
        JOIN users ON users.id = appointments.user_id
        JOIN doctors ON doctors.id = appointments.doctor_id
        ORDER BY appointments.id DESC
        LIMIT 20
    """).fetchall()
    
    # Get all doctors for display
    doctors = conn.execute("SELECT * FROM doctors ORDER BY id DESC").fetchall()

    conn.close()

    return render_template("admin_dashboard.html",
                           users_count=users_count,
                           doctors_count=doctors_count,
                           appointments_count=appointments_count,
                           appointments=appointments,
                           doctors=doctors)


@app.route("/admin/add-doctor", methods=["GET", "POST"])
def add_doctor():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    if request.method == "POST":
        name = request.form["name"]
        specialization = request.form["specialization"]
        available_days = request.form["available_days"]
        time_slots = request.form["time_slots"]

        conn = get_db()
        conn.execute("""
            INSERT INTO doctors(name, specialization, available_days, time_slots)
            VALUES(?,?,?,?)
        """, (name, specialization, available_days, time_slots))
        conn.commit()
        conn.close()

        flash("✅ Doctor added successfully!", "success")
        return redirect("/admin")

    return render_template("add_doctor.html")


@app.route("/admin/update-status/<int:appointment_id>", methods=["POST"])
def update_status(appointment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    status = request.form["status"]

    conn = get_db()
    # Get user email and appointment info before update
    appointment_data = conn.execute("""
        SELECT users.email, users.name as user_name, doctors.name as doctor_name, appointments.date, appointments.time 
        FROM appointments 
        JOIN users ON users.id = appointments.user_id 
        JOIN doctors ON doctors.id = appointments.doctor_id 
        WHERE appointments.id = ?
    """, (appointment_id,)).fetchone()
    
    conn.execute("UPDATE appointments SET status=? WHERE id=?", (status, appointment_id))
    conn.commit()
    conn.close()

    if appointment_data:
        send_email(
            f"Appointment Status: {status} 🏥",
            appointment_data['email'],
            f"<h3>Status Update</h3><p>Hello {appointment_data['user_name']},</p><p>Your appointment with <b>Dr. {appointment_data['doctor_name']}</b> on <b>{appointment_data['date']}</b> has been updated to: <b>{status}</b>.</p><p>Check your dashboard for more details.</p>"
        )

    flash("✅ Status updated & Notification sent!", "success")
    return redirect("/admin")


# -------------------- EXTRA: Add more doctors route --------------------
@app.route("/add-more-doctors")
def add_more_doctors():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")
    
    extra_doctors = [
        ("Dr. Lisa Wang", "Psychiatrist", "Mon, Wed, Fri", "10:00 AM - 2:00 PM, 4:00 PM - 7:00 PM"),
        ("Dr. Raj Patel", "ENT Specialist", "Tue, Thu, Sat", "9:00 AM - 1:00 PM, 3:00 PM - 6:00 PM"),
        ("Dr. Maria Garcia", "Ophthalmologist", "Mon, Tue, Thu, Fri", "8:30 AM - 12:30 PM, 2:30 PM - 5:30 PM")
    ]
    
    conn = get_db()
    for doctor in extra_doctors:
        try:
            conn.execute("""
                INSERT INTO doctors(name, specialization, available_days, time_slots)
                VALUES(?,?,?,?)
            """, doctor)
        except:
            continue
    
    conn.commit()
    conn.close()
    
    flash("✅ Additional doctors added successfully!", "success")
    return redirect("/admin")


# -------------------- SIMPLE PAGES --------------------
@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Setup static files
    setup_static_files()
    
    # Get port from environment variable (Render provides this)
    port = int(os.environ.get("PORT", 5000))
    
    # Run the app
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )