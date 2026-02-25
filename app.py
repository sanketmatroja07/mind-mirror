import csv
import os
from datetime import datetime
from functools import wraps
from io import StringIO

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from journal_utils import (
    add_entry,
    build_insights,
    build_product_signals,
    build_pro_insights,
    build_stats,
    create_user,
    delete_entry,
    get_user_by_email,
    get_user_by_id,
    init_db,
    load_entries,
    set_user_pro_status,
)
from sentiment import classify_sentiment


_root = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_root, "templates"),
            static_folder=os.path.join(_root, "static"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
init_db()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


@app.route("/", methods=["GET"])
@login_required
def home():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    entries = load_entries(user["id"])
    stats = build_stats(entries)
    insights = build_insights(entries, stats)
    product_signals = build_product_signals(entries, stats)
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return render_template(
        "index.html",
        entries=entries,
        stats=stats,
        insights=insights,
        product_signals=product_signals,
        greeting=greeting,
        user=user,
    )


@app.route("/entry", methods=["POST"])
@login_required
def create_entry():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    text = (request.form.get("entry_text") or "").strip()
    if not text:
        flash("Entry cannot be empty.", "error")
        return redirect(url_for("home"))

    sentiment = classify_sentiment(text)
    add_entry(text, sentiment, user["id"])
    flash("Entry saved and analyzed successfully.", "success")
    return redirect(url_for("home"))


@app.route("/api/entries", methods=["GET"])
@login_required
def entries_api():
    user = current_user()
    if not user:
        return jsonify([])
    entries = load_entries(user["id"])
    return jsonify(entries)


@app.route("/entry/<int:entry_id>/delete", methods=["POST"])
@login_required
def remove_entry(entry_id: int):
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    try:
        if delete_entry(entry_id, user["id"]):
            flash("Entry deleted.", "success")
        else:
            flash("Entry not found.", "error")
    except Exception:
        flash("Something went wrong while deleting the entry.", "error")
    return redirect(url_for("home"))


@app.route("/export/csv", methods=["GET"])
@login_required
def export_csv():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    entries = load_entries(user["id"])
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "created_at",
            "text",
            "label",
            "polarity",
            "subjectivity",
            "confidence",
            "provider",
            "model",
        ]
    )
    for entry in entries:
        sentiment = entry.get("sentiment", {})
        writer.writerow(
            [
                entry.get("id"),
                entry.get("created_at"),
                entry.get("text"),
                sentiment.get("label"),
                sentiment.get("polarity"),
                sentiment.get("subjectivity"),
                sentiment.get("confidence"),
                sentiment.get("provider"),
                sentiment.get("model"),
            ]
        )
    csv_data = output.getvalue()
    output.close()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=mind-mirror-entries.csv"},
    )


@app.route("/pro-insights", methods=["GET"])
@login_required
def pro_insights():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    entries = load_entries(user["id"])
    pro_data = build_pro_insights(entries)
    return render_template("pro_insights.html", user=user, pro_data=pro_data, entries=entries)


@app.route("/upgrade-pro", methods=["POST"])
@login_required
def upgrade_pro():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    set_user_pro_status(user["id"], True)
    flash("Pro features unlocked.", "success")
    return redirect(url_for("pro_insights"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        flash("Welcome back.", "success")
        return redirect(url_for("home"))

    return render_template("auth_login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if len(name) < 2:
            flash("Name must be at least 2 characters.", "error")
            return redirect(url_for("register"))
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        ok, message, user_id = create_user(name, email, generate_password_hash(password))
        if not ok:
            flash(message, "error")
            return redirect(url_for("register"))

        session["user_id"] = user_id
        flash("Account created successfully.", "success")
        return redirect(url_for("home"))

    return render_template("auth_register.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
