from flask import Flask, render_template, request, redirect, session, url_for, flash, send_from_directory, jsonify, Response
import csv
import io
import sqlite3
import os
import shutil
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_mail import Mail, Message
import threading

app = Flask(__name__, static_folder="static", template_folder=".")

# Detect base directory for PythonAnywhere/Production paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_NAME = os.path.join(BASE_DIR, "database.db")
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_development_only")

# ========== EMAIL CONFIGURATION ==========
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = 'medibook36@gmail.com'
app.config['MAIL_PASSWORD'] = 'iqxq xdaq swbm dzcc'
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'MediBook Alerts <noreply@medibook.com>')

mail = Mail(app)

def send_async_email(app_context, msg):
    """Internal helper to send email in a separate thread"""
    with app_context:
        try:
            mail.send(msg)
            print(f"✅ Email sent successfully")
        except Exception as e:
            print(f"❌ Email background error: {e}")

def send_email(subject, recipient, body_html):
    """Helper to send email asynchronously without blocking the main request"""
    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        print(f"📧 EMAIL LOG (Simulated):\nSubject: {subject}\nTo: {recipient}\nContent: {body_html}")
        return
    
    try:
        msg = Message(subject, recipients=[recipient])
        msg.html = body_html
        
        # Start a background thread to send the email
        # This prevents the web server from timing out on Render
        thread = threading.Thread(
            target=send_async_email, 
            args=(app.app_context(), msg)
        )
        thread.start()
        print(f"⏳ Email sending started for {recipient}...")
    except Exception as e:
        print(f"❌ Email initiation error: {e}")

# ========== DATABASE & INITIALIZATION ==========
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def setup_static_files():
    """Ensure style.css is in the static folder for production"""
    if not os.path.exists("static"):
        os.makedirs("static")
    if os.path.exists("style.css") and not os.path.exists("static/style.css"):
        shutil.copy("style.css", "static/style.css")
    elif os.path.exists("style.css"):
        # Always sync for local development updates
        shutil.copy("style.css", "static/style.css")

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
    if any(k in message_lower for k in ["how to book", "book an appointment", "booking", "schedule"]):
        return "📅 <b>To book an appointment:</b><br>1. Go to the <b>'Doctors'</b> page.<br>2. Choose your preferred specialist.<br>3. Select an available date and time slot.<br>4. Click 'Confirm Booking'.<br><br><a href='/doctors' class='btn btn-primary' style='width:100%; text-align:center; padding:10px; display:inline-block;'>🔍 Browse Doctors & Book</a>"

    if any(k in message_lower for k in ["cancel", "how to cancel", "remove booking"]):
        return "❌ <b>To cancel an appointment:</b><br>1. Log in to your account.<br>2. Navigate to your <b>'Dashboard'</b>.<br>3. Find the appointment you wish to cancel.<br>4. Click the 'Cancel' button next to it.<br><br><a href='/dashboard' class='btn btn-primary' style='width:100%; text-align:center; padding:10px; display:inline-block;'>📊 Go to Dashboard</a>"

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

    if any(k in message_lower for k in ["contact", "phone", "email", "support"]):
        return "📞 <b>Contact Support:</b><br>Phone: +1 555-123-4567<br>Email: support@medibook.com<br><br><a href='/contact' class='btn' style='width:100%; text-align:center; padding:8px; border:1px solid var(--card-border); display:inline-block;'>Open Contact Form</a>"

    if any(k in message_lower for k in ["location", "address", "where"]):
        return "📍 <b>Clinic Location:</b><br>123 Medical Street, Health City, Metro State.<br><br><i>Valet parking is available for all patients.</i>"

    if any(k in message_lower for k in ["fee", "price", "cost", "payment"]):
        return "💰 <b>Service Fees:</b><br>• General Consultation: $50<br>• Specialist Consultation: $80<br>• Follow-up Visit: $30<br><br><i>We accept all major insurance providers and credit cards.</i>"

    if any(k in message_lower for k in ["reschedule", "change", "edit"]):
        return "🔄 <b>Need to change your appointment?</b><br>You can easily reschedule from your dashboard or by calling us.<br><br><a href='/dashboard' class='btn btn-primary' style='width:100%; text-align:center; display:inline-block;'>Manage Appointments</a>"

    if any(k in message_lower for k in ["headache", "migrate", "pain"]):
        return "🤕 <b>Headache Advice:</b><br>If you have a persistent headache, please rest in a dark room and stay hydrated. <br><br>💡 <b>Tip:</b> If the pain is severe or accompanied by blurred vision, please book a <b>General Physician</b> immediately."

    if any(k in message_lower for k in ["fever", "cough", "flu", "cold"]):
        return "🤒 <b>Fever & Cough Advice:</b><br>Monitor your temperature and get plenty of rest. If your fever exceeds 102°F (39°C), or you have difficulty breathing, please consult a doctor.<br><br><a href='/doctors' class='btn btn-primary' style='width:100%; text-align:center; display:inline-block;'>Book a Consultation</a>"

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


@app.route("/about")
def about():
    """About page route"""
    return render_template("about.html")


@app.route("/contact")
def contact():
    """Contact page route"""
    return render_template("contact.html")


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
    
    # Get all appointments for the user
    appointments = conn.execute("""
        SELECT appointments.*, doctors.name as doctor_name, doctors.specialization as doctor_specialization
        FROM appointments
        JOIN doctors ON doctors.id = appointments.doctor_id
        WHERE appointments.user_id = ?
        ORDER BY appointments.id DESC
    """, (session["user_id"],)).fetchall()
    
    # Calculate specific stats
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute("SELECT COUNT(*) as count FROM appointments WHERE user_id=? AND date=? AND status!='Cancelled'", (session["user_id"], today_str)).fetchone()["count"]
    completed_count = conn.execute("SELECT COUNT(*) as count FROM appointments WHERE user_id=? AND status='Completed'", (session["user_id"],)).fetchone()["count"]
    pending_count = conn.execute("SELECT COUNT(*) as count FROM appointments WHERE user_id=? AND status='Pending'", (session["user_id"],)).fetchone()["count"]
    
    # Get the "Next" upcoming appointment
    next_appt = conn.execute("""
        SELECT a.date, a.time, d.name as doctor_name 
        FROM appointments a 
        JOIN doctors d ON a.doctor_id = d.id 
        WHERE a.user_id = ? AND a.status != 'Cancelled' 
        AND (a.date > date('now') OR (a.date = date('now') AND a.time >= time('now')))
        ORDER BY a.date ASC, a.time ASC 
        LIMIT 1
    """, (session["user_id"],)).fetchone()
    
    conn.close()

    return render_template("user_dashboard.html", 
                          appointments=appointments,
                          today_count=today_count,
                          completed_count=completed_count,
                          pending_count=pending_count,
                          next_appt=next_appt)


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
            
            # Fetch user email for notification
            user_data = conn.execute("SELECT email, name FROM users WHERE id=?", (session["user_id"],)).fetchone()
            
            if user_data:
                # Wrap email in a try/except so email issues NEVER crash the booking
                try:
                    send_email(
                        "Appointment Requested! 📅",
                        user_data["email"],
                        f"""
                        <div style="font-family: sans-serif; color: #333; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 12px;">
                            <h2 style="color: #4f46e5;">Booking Request Received</h2>
                            <p>Hello {user_data['name']},</p>
                            <p>Your appointment request has been successfully submitted. Here are the details:</p>
                            <div style="background: #f9fafb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                                <p style="margin: 5px 0;"><b>Doctor:</b> {doctor['name']}</p>
                                <p style="margin: 5px 0;"><b>Date:</b> {date}</p>
                                <p style="margin: 5px 0;"><b>Time:</b> {time}</p>
                                <p style="margin: 5px 0;"><b>Status:</b> <span style="color: #eab308; font-weight: bold;">PENDING</span></p>
                            </div>
                        </div>
                        """
                    )
                except Exception as email_err:
                    print(f"⚠️ Email could not be initiated: {email_err}")

            flash("✅ Appointment booked successfully!", "success")
            
        except sqlite3.IntegrityError as e:
            if "unique_doctor_time_slot" in str(e):
                flash("❌ This time slot was just booked by someone else. Please choose another time.", "danger")
            else:
                flash("❌ An error occurred with the database. Please try again.", "danger")
        except Exception as e:
            print(f"❌ Critical Booking Error: {e}")
            flash("❌ A system error occurred. Your booking might not have been saved.", "danger")
        finally:
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
    
    # Get user's own appointments to highlight conflicts
    user_upcoming_data = conn.execute("""
        SELECT date, time FROM appointments 
        WHERE user_id = ? AND status != 'Cancelled'
        AND date >= date('now')
    """, (session["user_id"],)).fetchall()
    
    # Convert Row objects to dictionaries so they can be JSON serialized in the template
    booked_slots_list = [dict(row) for row in booked_slots_data]
    user_upcoming_list = [dict(row) for row in user_upcoming_data]
    
    # Get today's date for min attribute
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn.close()
    
    return render_template("book_appointment.html", 
                         doctor=doctor, 
                         booked_slots=booked_slots_list,
                         user_upcoming=user_upcoming_list,
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
    # Get appointment info for the email
    appointment_data = conn.execute("""
        SELECT users.email, users.name as user_name, doctors.name as doctor_name, appointments.date, appointments.time 
        FROM appointments 
        JOIN users ON users.id = appointments.user_id 
        JOIN doctors ON doctors.id = appointments.doctor_id 
        WHERE appointments.id = ? AND appointments.user_id = ?
    """, (appointment_id, session["user_id"])).fetchone()

    conn.execute("UPDATE appointments SET status='Cancelled' WHERE id=? AND user_id=?",
                 (appointment_id, session["user_id"]))
    conn.commit()
    conn.close()

    if appointment_data:
        send_email(
            "Appointment Cancelled ❌",
            appointment_data["email"],
            f"""
            <div style="font-family: sans-serif; color: #333; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 12px;">
                <h2 style="color: #ef4444;">Appointment Cancelled</h2>
                <p>Hello {appointment_data['user_name']},</p>
                <p>Your appointment has been successfully cancelled as requested.</p>
                <div style="background: #f9fafb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><b>Doctor:</b> Dr. {appointment_data['doctor_name']}</p>
                    <p style="margin: 5px 0;"><b>Date:</b> {appointment_data['date']}</p>
                    <p style="margin: 5px 0;"><b>Time:</b> {appointment_data['time']}</p>
                </div>
                <p>If you wish to book a new appointment, please visit our website.</p>
            </div>
            """
        )

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
        "How do I cancel an appointment?",
        "What are the clinic working hours?",
        "Find a doctor",
        "View my appointment status",
        "Contact support"
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
        LIMIT 50
    """).fetchall()

    # Enhanced Admin Stats
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_appts = conn.execute("SELECT COUNT(*) as total FROM appointments WHERE date = ? AND status != 'Cancelled'", (today_str,)).fetchone()["total"]
    pending_appts = conn.execute("SELECT COUNT(*) as total FROM appointments WHERE status = 'Pending'").fetchone()["total"]
    completed_appts = conn.execute("SELECT COUNT(*) as total FROM appointments WHERE status = 'Completed'").fetchone()["total"]
    
    # Get all doctors for display
    doctors = conn.execute("SELECT * FROM doctors ORDER BY id DESC").fetchall()

    conn.close()

    return render_template("admin_dashboard.html",
                           users_count=users_count,
                           doctors_count=doctors_count,
                           today_appts=today_appts,
                           pending_appts=pending_appts,
                           completed_appts=completed_appts,
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
        status_color = "#22c55e" if status == "Confirmed" else "#ef4444"
        send_email(
            f"Appointment {status}! 🩺",
            appointment_data["email"],
            f"""
            <div style="font-family: sans-serif; color: #333; max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px; border-radius: 12px;">
                <h2 style="color: {status_color};">Appointment {status}</h2>
                <p>Hello {appointment_data['user_name']},</p>
                <p>The status of your appointment with <b>Dr. {appointment_data['doctor_name']}</b> has been updated.</p>
                <div style="background: #f9fafb; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><b>Date:</b> {appointment_data['date']}</p>
                    <p style="margin: 5px 0;"><b>Time:</b> {appointment_data['time']}</p>
                    <p style="margin: 5px 0;"><b>New Status:</b> <span style="color: {status_color}; text-transform: uppercase; font-weight: bold;">{status}</span></p>
                </div>
                {"<p>We look forward to seeing you!</p>" if status == "Confirmed" else "<p>If you have any questions, please contact our support team.</p>"}
            </div>
            """
        )
    
    flash(f"✅ Appointment status updated to {status}!", "success")
    return redirect("/admin")

@app.route("/admin/delete-appointment/<int:appointment_id>", methods=["POST"])
def delete_appointment(appointment_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")
    
    conn = get_db()
    conn.execute("DELETE FROM appointments WHERE id=?", (appointment_id,))
    conn.commit()
    conn.close()
    
    flash("🗑️ Appointment permanently deleted!", "success")
    return redirect("/admin")

@app.route("/admin/delete-doctor/<int:doctor_id>", methods=["POST"])
def delete_doctor(doctor_id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")
    
    conn = get_db()
    # Also delete appointments associated with this doctor to avoid foreign key/logic issues
    conn.execute("DELETE FROM appointments WHERE doctor_id=?", (doctor_id,))
    conn.execute("DELETE FROM doctors WHERE id=?", (doctor_id,))
    conn.commit()
    conn.close()
    
    flash("🗑️ Doctor and their associated appointments deleted!", "success")
    return redirect("/admin")

@app.route("/admin/export-appointments")
def export_appointments():
    """Export appointments from the last 30 days as CSV"""
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db()
    # Fetch data for the last 30 days
    appointments = conn.execute("""
        SELECT 
            a.id, 
            u.name as patient_name, 
            u.email as patient_email,
            d.name as doctor_name, 
            a.date, 
            a.time, 
            a.status
        FROM appointments a
        JOIN users u ON u.id = a.user_id
        JOIN doctors d ON d.id = a.doctor_id
        WHERE a.date >= date('now', '-30 days')
        ORDER BY a.date DESC
    """).fetchall()
    conn.close()

    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow(['ID', 'Patient Name', 'Patient Email', 'Doctor Name', 'Date', 'Time', 'Status'])
    
    # Data rows
    for row in appointments:
        writer.writerow([
            row['id'], 
            row['patient_name'], 
            row['patient_email'],
            row['doctor_name'], 
            row['date'], 
            row['time'], 
            row['status']
        ])

    output.seek(0)
    
    # Return as downloadable file
    filename = f"medibook_report_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


# Initialize files and DB on startup (required for Gunicorn/Production)
setup_static_files()
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))