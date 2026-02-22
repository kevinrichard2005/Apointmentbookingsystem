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
    """Generate smart healthcare responses based on message keywords and DB state"""
    message_lower = user_message.lower().strip()
    
    # ========== EMERGENCY CHECK ==========
    emergency_keywords = ["emergency", "911", "chest pain", "bleeding", "stroke", "accident", "suicide", "dying"]
    for keyword in emergency_keywords:
        if keyword in message_lower:
            return "🚨 <b style='color:var(--danger);'>EMERGENCY NOTICE</b> 🚨<br><br>If this is a medical emergency, please:<br><br>1. <b>CALL 911 IMMEDIATELY</b><br>2. Go to the nearest emergency room<br>3. Do NOT wait for online assistance<br><br><a href='tel:911' class='btn' style='background:var(--danger); color:white; width:100%; text-align:center; padding:12px; border-radius:10px; display:inline-block; font-weight:700;'>📞 CALL 911 NOW</a>"

    # ========== GREETINGS & THANKS ==========
    if any(k in message_lower for k in ["hello", "hi", "hey", "greetings"]):
        return "👋 <b>Hello! I'm MediBook AI.</b><br>I'm here to help you book appointments, find doctors, and answer health queries.<br><br><b>How can I assist you today?</b>"
    
    if any(k in message_lower for k in ["thank", "thanks", "helpful"]):
        return "You're very welcome! I'm glad I could help. Is there anything else you need assistance with? 😊"

    # ========== APPOINTMENT BOOKING ==========
    if any(k in message_lower for k in ["book", "appointment", "schedule"]):
        try:
            conn = get_db()
            count = conn.execute("SELECT COUNT(*) as count FROM doctors").fetchone()["count"]
            conn.close()
        except:
            count = "several"
        return f"📅 <b>Ready to book?</b><br>We have {count} specialists available for you.<br><br><a href='/doctors' class='btn btn-primary' style='width:100%; text-align:center; padding:10px; border-radius:12px; display:inline-block;'>🔍 Browse Doctors & Book</a>"

    # ========== DOCTOR SEARCH & SPECIALTIES ==========
    specialties_list = {
        "heart": "Cardiologist", "chest": "Cardiologist",
        "tooth": "Dentist", "teeth": "Dentist", "dental": "Dentist",
        "child": "Pediatrician", "kid": "Pediatrician",
        "bone": "Orthopedic", "joint": "Orthopedic",
        "skin": "Dermatologist", "rash": "Dermatologist",
        "eye": "Ophthalmologist", "vision": "Ophthalmologist",
        "ear": "ENT Specialist", "nose": "ENT Specialist", "throat": "ENT Specialist",
        "stomach": "Gastroenterologist", "digestion": "Gastroenterologist"
    }

    for key, spec in specialties_list.items():
        if key in message_lower:
            try:
                conn = get_db()
                docs = conn.execute("SELECT id, name FROM doctors WHERE specialization LIKE ? LIMIT 2", (f"%{spec.split()[0]}%",)).fetchall()
                conn.close()
            except:
                docs = []
            
            resp = f"🏥 <b>Recommended Specialty: {spec}</b><br>Based on your query, here are some top specialists:<br>"
            if docs:
                for d in docs:
                    resp += f"<div style='background:rgba(255,255,255,0.05); padding:10px; border-radius:12px; margin:10px 0; border:1px solid var(--card-border);'><b>Dr. {d['name']}</b><br><a href='/book/{d['id']}' style='color:var(--primary); font-size:0.85rem; font-weight:600; text-decoration:none;'>📅 Book Dr. {d['name']} →</a></div>"
            else:
                resp += f"<br><a href='/doctors' class='btn btn-primary' style='width:100%; text-align:center; padding:8px; display:inline-block;'>🔍 Search for {spec}</a>"
            return resp

    # ========== MY APPOINTMENTS ==========
    if any(k in message_lower for k in ["my appointment", "my booking", "status"]):
        if not user_id:
            return "🔑 <b>Please log in</b> to view your appointments.<br><br><a href='/login' class='btn btn-primary' style='width:100%; text-align:center; padding:8px; display:inline-block;'>Login to MediBook</a>"
        
        try:
            conn = get_db()
            apps = conn.execute("SELECT a.date, a.time, a.status, d.name FROM appointments a JOIN doctors d ON a.doctor_id = d.id WHERE a.user_id = ? ORDER BY a.date DESC LIMIT 3", (user_id,)).fetchall()
            conn.close()
            
            if apps:
                resp = "📂 <b>Your Recent Bookings:</b><br><br>"
                for a in apps:
                    clr = "#eab308" if a['status'] == 'Pending' else "#22c55e"
                    resp += f"<div style='border-left:3px solid {clr}; padding-left:10px; margin-bottom:12px;'><b>{a['date']}</b> at {a['time']}<br>Dr. {a['name']} ({a['status']})</div>"
                resp += "<a href='/dashboard' class='btn' style='width:100%; text-align:center; border:1px solid var(--card-border); padding:8px; border-radius:10px; display:inline-block;'>Go to Dashboard</a>"
                return resp
            return "You have no upcoming appointments. <a href='/doctors' style='color:var(--primary);'>Book one now?</a>"
        except:
            return "Could not retrieve appointments at this time. Please try checking your dashboard."

    # ========== CLINIC INFO ==========
    if any(k in message_lower for k in ["hour", "open", "timing"]):
        return "🕒 <b>Clinic Hours:</b><br>• Mon-Fri: 9AM - 7PM<br>• Sat: 10AM - 4PM<br>• Sun: Emergency Only<br><br><b>Location:</b><br>123 Medical St, Health City"

    if any(k in message_lower for k in ["contact", "phone", "email"]):
        return "📞 <b>Contact Support:</b><br>Phone: +1 555-123-4567<br>Email: support@medibook.com<br><br><a href='/contact' class='btn' style='width:100%; text-align:center; padding:8px; border:1px solid var(--card-border); display:inline-block;'>Form Support</a>"

    # ========== DEFAULT ==========
    return """
    <b>What can I help with?</b><br>
    Try asking about:<br>
    • 👨‍⚕️ "Available doctors"<br>
    • 📅 "Book an appointment"<br>
    • 🤒 "I have a toothache"<br>
    • 🕒 "Clinic hours"
    """

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
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Backend Validation
        if not name or not email or not password:
            flash("❌ All fields are required!", "danger")
            return redirect("/register")
        
        if len(password) < 8:
            flash("❌ Password must be at least 8 characters long!", "danger")
            return redirect("/register")

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db()
            conn.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                         (name, email, hashed_password))
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
        except sqlite3.IntegrityError:
            flash("❌ Email already exists!", "danger")
            return redirect("/register")
        except Exception as e:
            flash(f"❌ An error occurred: {str(e)}", "danger")
            return redirect("/register")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("❌ Email and password are required!", "danger")
            return redirect("/login")

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
                f"""
                <div style="font-family: sans-serif; color: #333; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 12px;">
                    <h2 style="color: #4f46e5;">Booking Request Received</h2>
                    <p>Hello {session['name']},</p>
                    <p>Your appointment request has been successfully submitted. Here are the details:</p>
                    <div style="background: #f9fafb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 5px 0;"><b>Doctor:</b> Dr. {doctor['name']}</p>
                        <p style="margin: 5px 0;"><b>Date:</b> {date}</p>
                        <p style="margin: 5px 0;"><b>Time:</b> {time}</p>
                        <p style="margin: 5px 0;"><b>Status:</b> <span style="color: #eab308; font-weight: bold;">PENDING</span></p>
                    </div>
                    <p><b>Note:</b> We will send you another notification once the doctor approves this appointment.</p>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="font-size: 0.85rem; color: #666;">
                        ⏰ <b>Reminder Service:</b> Our system will automatically send you a reminder email 24 hours before your scheduled visit.
                    </p>
                    <p style="font-size: 0.85rem; color: #666;">If you need to change your appointment, please visit your dashboard.</p>
                </div>
                """
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