from flask import Flask, render_template, request, redirect, session, url_for, flash, send_from_directory, jsonify
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__, static_folder="static", template_folder=".")

app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_development_only")
DB_NAME = "database.db"

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


# -------------------- MAIN ROUTES --------------------
@app.route("/")
def index():
    conn = get_db()
    doctors_count = conn.execute("SELECT COUNT(*) as count FROM doctors").fetchone()["count"]
    appointments_count = conn.execute("SELECT COUNT(*) as count FROM appointments").fetchone()["count"]
    users_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='user'").fetchone()["count"]
    
    # Get today's booked slots for doctors
    today = datetime.now().strftime("%Y-%m-%d")
    booked_slots = conn.execute("""
        SELECT doctor_id, COUNT(*) as booked_count 
        FROM appointments 
        WHERE date = ? AND status != 'Cancelled'
        GROUP BY doctor_id
    """, (today,)).fetchall()
    
    conn.close()
    
    stats = {
        "doctors": doctors_count,
        "appointments": appointments_count,
        "specializations": 15
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
    conn.execute("UPDATE appointments SET status=? WHERE id=?", (status, appointment_id))
    conn.commit()
    conn.close()

    flash("✅ Status updated!", "success")
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