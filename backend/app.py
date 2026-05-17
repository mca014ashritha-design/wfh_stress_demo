"""
Personal Stress Tracker
Flask + PyMongo + Ridge Regression + private email alerts
"""
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
import os
import pickle
import smtplib
import threading
import time
from zoneinfo import ZoneInfo

import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, OperationFailure
from werkzeug.security import check_password_hash, generate_password_hash

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "wfh_stress_db")
MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(os.path.dirname(__file__), "tuned_model.pkl"))
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-demo-secret-key")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
AUTO_WEEKLY_REPORTS = os.environ.get("AUTO_WEEKLY_REPORTS", "true").lower() == "true"
WEEKLY_REPORT_DAY = int(os.environ.get("WEEKLY_REPORT_DAY", "6"))  # Monday=0, Sunday=6
WEEKLY_REPORT_HOUR = int(os.environ.get("WEEKLY_REPORT_HOUR", "9"))
WEEKLY_REPORT_MINUTE = int(os.environ.get("WEEKLY_REPORT_MINUTE", "0"))
WEEKLY_REPORT_CHECK_SECONDS = int(os.environ.get("WEEKLY_REPORT_CHECK_SECONDS", "1800"))

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
app.secret_key = SECRET_KEY
CORS(app)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_col = db["users"]
employees_col = db["employees"]
predictions_col = db["predictions"]
weekly_reports_col = db["weekly_reports"]
users_col.create_index("username", unique=True)
users_col.create_index("email", unique=True, sparse=True)
employees_col.create_index("employee_id", unique=True)
predictions_col.create_index([("employee_id", 1), ("date", 1)])
weekly_reports_col.create_index([("user_id", 1), ("week_key", 1)], unique=True)
try:
    predictions_col.create_index([("user_id", 1), ("date", 1)], unique=True)
except OperationFailure as exc:
    print(f"Daily unique index not created yet: {exc}")

with open(MODEL_PATH, "rb") as fp:
    bm = pickle.load(fp)

MODEL = bm["model"]
FINAL_FEATURES = bm["final_features"]
LOW_T = bm.get("low_t", 4.15)
MOD_T = bm.get("mod_t", 6.85)
IMPUTER = bm["imputer"]
SCALER = bm["scaler"]
USE_SC = bm["use_sc"]


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def current_employee_id():
    return int(session.get("employee_id", 1))


def current_user():
    username = session.get("username")
    if not username:
        return None
    return users_col.find_one({"username": username})


def email_ready():
    return bool(SMTP_HOST and SMTP_FROM)


def send_email(to_email, subject, body):
    if not to_email:
        return False, "User email not found."
    if not email_ready():
        return False, "SMTP email settings are not configured."

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
        return True, "Email sent."
    except Exception as exc:
        return False, str(exc)


def high_stress_email_body(username, date, score, label, tip):
    return f"""Hi {username},

Your stress prediction for {date} is HIGH.

Score: {score}
Label: {label}

Recommended action:
{tip}

Please take a short recovery break now. If high stress continues, consider speaking with someone you trust or a health professional.

Personal Stress Tracker

Disclaimer: The predicted stress score is for informational purposes only and not a clinical diagnosis. Please consult a healthcare professional for medical advice.
"""


def local_now():
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def weekly_report_key(now=None):
    now = now or local_now()
    week_start = (now.date() - timedelta(days=now.weekday())).isoformat()
    return week_start


def current_week_record_count(user_id, now=None):
    now = now or local_now()
    week_start = (now.date() - timedelta(days=now.weekday())).isoformat()
    return predictions_col.count_documents({"user_id": user_id, "date": {"$gte": week_start}})


def send_automatic_weekly_reports(now=None):
    now = now or local_now()
    week_key = weekly_report_key(now)
    sent_count = 0
    skipped_count = 0

    for user in users_col.find({"email": {"$exists": True, "$ne": ""}}):
        user_id = str(user["_id"])
        if weekly_reports_col.find_one({"user_id": user_id, "week_key": week_key}):
            skipped_count += 1
            continue
        if current_week_record_count(user_id, now) < 3:
            skipped_count += 1
            continue

        payload = dashboard_payload(user_id, int(user.get("employee_id", 1)))
        weekly = payload["weekly"]
        sent, message = send_email(
            user.get("email"),
            "Your Weekly Stress Report - Personal Stress Tracker",
            weekly_report_email_body(user.get("username", "there"), weekly),
        )
        weekly_reports_col.insert_one({
            "user_id": user_id,
            "email": user.get("email"),
            "week_key": week_key,
            "sent": sent,
            "message": message,
            "weekly": weekly,
            "created_at": datetime.utcnow(),
        })
        sent_count += 1

    return {"sent_count": sent_count, "skipped_count": skipped_count, "week_key": week_key}


def weekly_report_scheduler_loop():
    print(
        f"Automatic weekly reports enabled: day={WEEKLY_REPORT_DAY}, "
        f"time={WEEKLY_REPORT_HOUR:02d}:{WEEKLY_REPORT_MINUTE:02d}, timezone={APP_TIMEZONE}"
    )
    while True:
        try:
            now = local_now()
            scheduled_time_reached = (now.hour, now.minute) >= (WEEKLY_REPORT_HOUR, WEEKLY_REPORT_MINUTE)
            if now.weekday() == WEEKLY_REPORT_DAY and scheduled_time_reached:
                result = send_automatic_weekly_reports(now)
                print(f"Automatic weekly report check complete: {result}")
        except Exception as exc:
            print(f"Automatic weekly report error: {exc}")
        time.sleep(WEEKLY_REPORT_CHECK_SECONDS)


def start_weekly_report_scheduler():
    if not AUTO_WEEKLY_REPORTS:
        print("Automatic weekly reports disabled.")
        return
    thread = threading.Thread(target=weekly_report_scheduler_loop, daemon=True)
    thread.start()


def weekly_report_email_body(username, weekly):
    focus = weekly.get("focus_areas") or ["general"]
    focus_text = ", ".join(str(item).replace("_", " ") for item in focus)
    comparison_ready = bool(weekly.get("comparison_ready"))
    last_week_avg = weekly.get("last_week_avg") if comparison_ready else "N/A"
    delta = weekly.get("delta") if comparison_ready else "N/A"
    record_count = weekly.get("record_count", len(weekly.get("days", [])))
    return f"""Hi {username},

Here is your private weekly stress report.

Recorded days: {record_count}
This week average: {weekly.get("this_week_avg", 0)}
Last week average: {last_week_avg}
Change: {delta}
Trend: {weekly.get("trend", "NO_DATA")}
Focus areas: {focus_text}

Weekly tip:
{weekly.get("weekly_tip", "Add more daily predictions to generate a weekly tip.")}

Note: Initial reports show a partial weekly average only. Full comparison with the previous 7 days starts after 14 records are available.

This report is private to your account.

Personal Stress Tracker

Disclaimer: The predicted stress score is for informational purposes only and not a clinical diagnosis. Please consult a healthcare professional for medical advice.
"""


def score_to_label(score):
    if score <= LOW_T:
        return "Low", "#27AE60"
    if score <= MOD_T:
        return "Moderate", "#E67E22"
    return "High", "#C0392B"


def get_tip(features, label):
    tips_map = {
        "sleep_hours": {
            "trigger": lambda f: f.get("sleep_hours", 7) < 6.0,
            "High": "Main issue: Low sleep. What to do: Finish work early today, avoid phone or laptop before bed, and try to sleep for 7-8 hours tonight.",
            "Moderate": "Main issue: Sleep is less than needed. What to do: Set a fixed bedtime tonight and avoid caffeine in the evening.",
            "Low": "Sleep was a little low, but your stress is controlled. Try to keep a steady sleep time tonight.",
        },
        "daily_work_hours": {
            "trigger": lambda f: f.get("daily_work_hours", 8) > 10.0,
            "High": "Main issue: Long work hours. What to do: Stop work as soon as possible, write tomorrow's top 3 tasks, and take rest.",
            "Moderate": "Main issue: Work hours are high. What to do: Set a clear logoff time tomorrow and avoid extending work into the evening.",
            "Low": "You worked for many hours, but stress is still low. Keep a clear start time and stop time tomorrow.",
        },
        "pending_task": {
            "trigger": lambda f: f.get("pending_task", 0) > 12,
            "High": "Main issue: Too many pending tasks. What to do: Write only the top 3 tasks for tomorrow. Do not try to finish everything today.",
            "Moderate": "Main issue: Pending tasks are increasing. What to do: Choose 3 important tasks and complete them first tomorrow morning.",
            "Low": "Your task load is manageable. Spend 5 minutes planning tomorrow's work.",
        },
        "home_distractions_score": {
            "trigger": lambda f: f.get("home_distractions_score", 4) > 6,
            "High": "Main issue: Too many home distractions. What to do: Create one quiet work block tomorrow and reduce interruptions during that time.",
            "Moderate": "Main issue: Distractions affected your focus. What to do: Choose a quiet place and inform others about your focus time.",
            "Low": "Distractions were present, but you handled them well. Continue using the setup that helped you focus.",
        },
        "exercise": {
            "trigger": lambda f: f.get("exercise", 30) < 15,
            "High": "Main issue: Very little movement. What to do: Take a 10-20 minute walk or do light stretching today.",
            "Moderate": "Main issue: Exercise is low. What to do: Plan a 20-minute walk tomorrow before or after work.",
            "Low": "Movement was low, but stress is controlled. Add a short walk or stretch break tomorrow.",
        },
        "breaks_per_day": {
            "trigger": lambda f: f.get("breaks_per_day", 4) < 2,
            "High": "Main issue: Not enough breaks. What to do: Tomorrow, take a 5-minute break after every 90 minutes of work.",
            "Moderate": "Main issue: Breaks were too few. What to do: Take at least 3 short breaks tomorrow.",
            "Low": "Breaks were fewer than ideal, but stress is low. Keep adding small pauses during work.",
        },
        "caffeine_intake": {
            "trigger": lambda f: f.get("caffeine_intake", 3) > 5,
            "High": "Main issue: High caffeine intake. What to do: Avoid more caffeine today and drink water instead.",
            "Moderate": "Main issue: Caffeine is high. What to do: Limit coffee or tea to 3-4 cups tomorrow and avoid it after lunch.",
            "Low": "Caffeine was high, but stress is low. Keep it moderate tomorrow to protect your sleep.",
        },
        "meetings_per_day": {
            "trigger": lambda f: f.get("meetings_per_day", 3) > 7,
            "High": "Main issue: Too many meetings. What to do: Keep a 2-hour no-meeting block tomorrow for focused work.",
            "Moderate": "Main issue: Meeting load is high. What to do: Group meetings together and keep one focus block free.",
            "Low": "You handled many meetings well. Still, keep some focus time protected tomorrow.",
        },
    }
    for driver, info in tips_map.items():
        if info["trigger"](features):
            return info[label], driver
    defaults = {
        "High": "Stress is high today. What to do: Take a short break, breathe slowly for 2 minutes, and write tomorrow's top 3 tasks.",
        "Moderate": "Stress is moderate today. What to do: Take a short walk, plan tomorrow's work, and try to sleep on time.",
        "Low": "Stress looks low today. Keep doing what is working: good sleep, short breaks, movement, and healthy work boundaries.",
    }
    return defaults[label], "general"

def predict_stress(features_dict):
    fv = np.array([features_dict.get(feature, 0.0) for feature in FINAL_FEATURES], dtype=float).reshape(1, -1)
    fv = IMPUTER.transform(fv)
    if USE_SC:
        fv = SCALER.transform(fv)
    score = float(np.clip(MODEL.predict(fv)[0], 1.0, 10.0))
    label, color = score_to_label(score)
    tip, driver = get_tip(features_dict, label)
    return round(score, 3), label, color, tip, driver


def dashboard_payload(user_id, employee_id):
    projection = {
        "_id": 0,
        "date": 1,
        "stress_score": 1,
        "stress_label": 1,
        "stress_color": 1,
        "tip": 1,
        "tip_driver": 1,
        "sleep_hours": 1,
        "daily_work_hours": 1,
        "breaks_per_day": 1,
        "exercise": 1,
    }
    docs = list(predictions_col.find({"user_id": user_id}, projection).sort("date", -1).limit(30))
    docs = list(reversed(docs))

    empty_weekly = {
        "this_week_avg": 0,
        "last_week_avg": None,
        "delta": None,
        "trend": "NO_DATA",
        "weekly_tip": "Add a few daily predictions to generate your weekly stress report.",
        "focus_areas": [],
        "days": [],
        "record_count": 0,
        "comparison_ready": False,
    }

    if not docs:
        return {
            "employee_id": employee_id,
            "total": 0,
            "average": 0,
            "latest": None,
            "distribution": {"Low": 0, "Moderate": 0, "High": 0},
            "trend": "NO_DATA",
            "delta": None,
            "comparison_ready": False,
            "history": [],
            "driver_counts": {},
            "weekly": empty_weekly,
        }

    scores = [float(doc["stress_score"]) for doc in docs]
    distribution = {"Low": 0, "Moderate": 0, "High": 0}
    driver_counts = {}
    for doc in docs:
        label = doc.get("stress_label", "Moderate")
        distribution[label] = distribution.get(label, 0) + 1
        driver = doc.get("tip_driver", "general")
        driver_counts[driver] = driver_counts.get(driver, 0) + 1

    total_records = len(scores)
    weekly_docs = docs[-7:]
    weekly_scores = [float(doc["stress_score"]) for doc in weekly_docs]
    recent_avg = float(np.mean(weekly_scores)) if weekly_scores else 0
    previous_avg = None
    delta = None
    comparison_ready = False

    if total_records < 3:
        trend = "INSUFFICIENT_DATA"
    elif total_records < 7:
        trend = "PARTIAL_WEEK"
    elif total_records < 14:
        trend = "CURRENT_WEEK"
    else:
        previous = scores[-14:-7]
        previous_avg = float(np.mean(previous))
        delta = recent_avg - previous_avg
        comparison_ready = True
        trend = "WORSENING" if delta > 0.35 else ("IMPROVING" if delta < -0.35 else "STABLE")

    weekly_driver_counts = {}
    for doc in weekly_docs:
        driver = doc.get("tip_driver", "general")
        weekly_driver_counts[driver] = weekly_driver_counts.get(driver, 0) + 1
    focus_areas = [driver for driver, _ in sorted(weekly_driver_counts.items(), key=lambda item: item[1], reverse=True)[:3]]

    weekly_tips = {
        "WORSENING": "Your weekly stress is increasing compared with the previous 7 days. This week, focus on sleep, short breaks, and a fixed logoff time.",
        "IMPROVING": "Your weekly stress is improving compared with the previous 7 days. Continue the habits that helped: sleep on time, move daily, and take planned breaks.",
        "STABLE": "Your weekly stress is stable compared with the previous 7 days. Choose one simple goal for next week: a walk, a focus block, or an earlier logoff time.",
        "CURRENT_WEEK": "This is your current 7-day average. Full comparison with the previous 7 days will start after 14 records are available.",
        "PARTIAL_WEEK": f"This is a partial weekly average based on {total_records} recorded days. Full trend comparison starts after 14 records are available.",
        "INSUFFICIENT_DATA": "Add at least 3 daily records to generate a useful partial weekly average.",
        "NO_DATA": "Add a few daily predictions to generate your weekly stress report and personalised weekly tips.",
    }
    weekly = {
        "this_week_avg": round(float(recent_avg), 2),
        "last_week_avg": round(float(previous_avg), 2) if previous_avg is not None else None,
        "delta": round(float(delta), 2) if delta is not None else None,
        "trend": trend,
        "weekly_tip": weekly_tips.get(trend, weekly_tips["STABLE"]),
        "focus_areas": focus_areas,
        "days": weekly_docs,
        "record_count": total_records,
        "comparison_ready": comparison_ready,
    }

    return {
        "employee_id": employee_id,
        "total": len(docs),
        "average": round(float(np.mean(scores)), 2),
        "latest": docs[-1],
        "distribution": distribution,
        "trend": trend,
        "delta": round(float(delta), 2) if delta is not None else None,
        "comparison_ready": comparison_ready,
        "history": docs[-14:],
        "driver_counts": driver_counts,
        "weekly": weekly,
    }


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or not email or not password:
            error = "All fields are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                employee_id_int = int(datetime.utcnow().timestamp())
                user_doc = {
                    "username": username,
                    "email": email,
                    "employee_id": employee_id_int,
                    "password_hash": generate_password_hash(password),
                    "created_at": datetime.utcnow(),
                }
                result = users_col.insert_one(user_doc)
                session["user_id"] = str(result.inserted_id)
                session["username"] = username
                session["email"] = email
                session["employee_id"] = employee_id_int
                return redirect(url_for("index"))
            except DuplicateKeyError:
                error = "Username or email already exists."

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = users_col.find_one({"username": username})

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            session["email"] = user.get("email", "")
            session["employee_id"] = user.get("employee_id", 1)
            return redirect(url_for("index"))
        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        low_t=LOW_T,
        mod_t=MOD_T,
        username=session.get("username"),
        employee_id=current_employee_id(),
    )



@app.route("/result")
@login_required
def result():
    latest = predictions_col.find_one(
        {"user_id": session.get("user_id")},
        {"_id": 0},
        sort=[("date", -1)],
    )
    if latest:
        latest["color"] = latest.get("stress_color", latest.get("color", "#2563eb"))
        latest["saved"] = True
        latest["email_sent"] = latest.get("high_alert_email_sent", False)
        latest["email_message"] = latest.get("high_alert_email_message", "")
    return render_template(
        "result.html",
        low_t=LOW_T,
        mod_t=MOD_T,
        username=session.get("username"),
        employee_id=current_employee_id(),
        latest_result=latest,
    )

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        username=session.get("username"),
        employee_id=current_employee_id(),
    )


@app.route("/api/predict", methods=["POST"])
@login_required
def predict():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    emp_id = current_employee_id()
    date = data.get("date", datetime.today().strftime("%Y-%m-%d"))
    existing = predictions_col.find_one({"user_id": session.get("user_id"), "date": date})
    if existing:
        return jsonify({
            "error": "You have already submitted your stress check-in for this date.",
            "already_submitted": True,
            "date": date,
            "stress_score": existing.get("stress_score"),
            "stress_label": existing.get("stress_label"),
            "tip": existing.get("tip"),
        }), 409

    prev = predictions_col.find_one({"user_id": session.get("user_id")}, sort=[("date", -1)])

    prev_score = float(prev["stress_score"]) if prev else 5.0
    lag1 = prev_score
    lag2 = float(prev.get("stress_lag1", prev_score)) if prev else prev_score
    roll3 = float(prev.get("stress_roll3", prev_score)) if prev else prev_score
    roll7 = float(prev.get("stress_roll7", prev_score)) if prev else prev_score
    work_lag1 = float(prev.get("daily_work_hours", data.get("daily_work_hours", 8))) if prev else float(data.get("daily_work_hours", 8))
    sleep_lag1 = float(prev.get("sleep_hours", data.get("sleep_hours", 7))) if prev else float(data.get("sleep_hours", 7))

    wh = float(data.get("daily_work_hours", 8))
    sl = float(data.get("sleep_hours", 7))
    features = {
        "sleep_hours": sl,
        "previous_day_stress_score": prev_score,
        "work_sleep_stress": max(wh - 8, 0) * max(7 - sl, 0),
        "daily_screen_time_hrs": float(data.get("daily_screen_time_hrs", 8)),
        "meetings_per_day": int(data.get("meetings_per_day", 3)),
        "daily_work_hours": wh,
        "exercise": float(data.get("exercise", 30)),
        "sleep_lag1": sleep_lag1,
        "pending_task": int(data.get("pending_task", 5)),
        "stress_roll3": roll3,
        "stress_lag1": lag1,
        "home_distractions_score": int(data.get("home_distractions_score", 4)),
        "breaks_per_day": int(data.get("breaks_per_day", 3)),
        "stress_lag2": lag2,
        "internet_stability_score": int(data.get("internet_stability_score", 7)),
        "weekday": int(data.get("weekday", datetime.today().weekday())),
        "water_intake": int(data.get("water_intake", 8)),
        "caffeine_intake": int(data.get("caffeine_intake", 2)),
        "work_hours_lag1": work_lag1,
        "stress_roll7": roll7,
    }

    score, label, color, tip, driver = predict_stress(features)
    record = {
        **features,
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "employee_id": emp_id,
        "date": date,
        "stress_score": score,
        "stress_label": label,
        "stress_color": color,
        "tip": tip,
        "tip_driver": driver,
        "created_at": datetime.utcnow(),
    }

    email_sent = False
    email_message = ""
    if label == "High":
        user = current_user()
        to_email = user.get("email") if user else session.get("email")
        email_sent, email_message = send_email(
            to_email,
            "High Stress Alert - Personal Stress Tracker",
            high_stress_email_body(session.get("username", "there"), date, score, label, tip),
        )
        record["high_alert_email_sent"] = email_sent
        record["high_alert_email_message"] = email_message

    try:
        predictions_col.insert_one(record)
    except DuplicateKeyError:
        return jsonify({
            "error": "You have already submitted your stress check-in for this date.",
            "already_submitted": True,
            "date": date,
        }), 409

    return jsonify({
        "stress_score": score,
        "stress_label": label,
        "color": color,
        "tip": tip,
        "tip_driver": driver,
        "thresholds": {"low": LOW_T, "moderate": MOD_T},
        "employee_id": emp_id,
        "date": date,
        "saved": True,
        "email_sent": email_sent,
        "email_message": email_message,
    })


@app.route("/api/submission-status")
@login_required
def submission_status():
    date = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))
    doc = predictions_col.find_one(
        {"user_id": session.get("user_id"), "date": date},
        {"_id": 0, "stress_score": 1, "stress_label": 1, "tip": 1, "tip_driver": 1},
    )
    return jsonify({"date": date, "submitted": bool(doc), "record": doc})


@app.route("/api/dashboard")
@login_required
def dashboard_data():
    return jsonify(dashboard_payload(session.get("user_id"), current_employee_id()))


@app.route("/api/weekly-report")
@login_required
def weekly_report():
    payload = dashboard_payload(session.get("user_id"), current_employee_id())
    return jsonify(payload["weekly"])


@app.route("/api/email-weekly-report", methods=["POST"])
@login_required
def email_weekly_report():
    user = current_user()
    payload = dashboard_payload(session.get("user_id"), current_employee_id())
    weekly = payload["weekly"]
    to_email = user.get("email") if user else session.get("email")
    sent, message = send_email(
        to_email,
        "Your Weekly Stress Report - Personal Stress Tracker",
        weekly_report_email_body(session.get("username", "there"), weekly),
    )
    return jsonify({"sent": sent, "message": message, "weekly": weekly})


@app.route("/api/history/<int:employee_id>")
@login_required
def history(employee_id):
    if employee_id != current_employee_id():
        return jsonify({"error": "You can only view your own history"}), 403

    days = int(request.args.get("days", 30))
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    docs = list(predictions_col.find({"user_id": session.get("user_id"), "date": {"$gte": since}}, {"_id": 0}).sort("date", 1))
    return jsonify({"employee_id": employee_id, "history": docs, "count": len(docs)})


@app.route("/api/model-info")
def model_info():
    return jsonify({
        "model": "Ridge Regression",
        "features": len(FINAL_FEATURES),
        "thresholds": {"low": LOW_T, "moderate": MOD_T},
        "source": "PSS-10 Cohen 1983",
    })


if __name__ == "__main__":
    start_weekly_report_scheduler()
    print(f"Personal Stress Tracker | MongoDB: {MONGO_URI} | Model: {MODEL_PATH}")
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)



