from dotenv import load_dotenv
import csv
import io
import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_
from email.message import EmailMessage
import smtplib
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-deployment")
database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///applications.db"
)

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql+psycopg://",
        1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

STATUSES = [
    "Submitted", "Under Review", "Additional Information Required",
    "Approved", "Rejected", "Completed"
]
REASONS = [
    "Flight cancellation", "Flight delay", "Missed connection",
    "Medical emergency", "Duplicate booking", "Booking error", "Other"
]
PAYMENT_METHODS = ["Debit Card", "Credit Card", "Other approved refund method"]

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(24), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    flight_reference = db.Column(db.String(80), nullable=False, index=True)

    ticket_number = db.Column(db.String(30), nullable=True)
    ticket_issue_date = db.Column(db.String(10), nullable=True)
    ticket_expiry_date = db.Column(db.String(10), nullable=True)

    reason = db.Column(db.String(80), nullable=False)
    reason_other = db.Column(db.String(500))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    street_address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state_province = db.Column(db.String(100))
    postal_code = db.Column(db.String(30))
    date_of_birth = db.Column(db.String(10))  # Optional; avoid collecting unless necessary.
    payment_method = db.Column(db.String(60), nullable=False)
    cardholder_name = db.Column(db.String(120))
    status = db.Column(db.String(50), nullable=False, default="Submitted")
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


def send_email(to_address, subject, body):
    host = os.environ.get("MAIL_SERVER")
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    sender = os.environ.get("MAIL_DEFAULT_SENDER", username or "")
    port = int(os.environ.get("MAIL_PORT", "587"))
    if not all([host, username, password, sender, to_address]):
        app.logger.warning("Email not sent: mail settings are incomplete.")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return True
    except Exception:
        app.logger.exception("Email delivery failed.")
        return False


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"independent_disclosure": "Independent refund assistance service. Not affiliated with, endorsed by, or acting on behalf of Allegiant Air."}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "GET":
        return render_template("apply.html", reasons=REASONS, methods=PAYMENT_METHODS)

    # Honeypot field: bots often fill hidden fields.
    if request.form.get("website"):
        abort(400)

    required = ["full_name", "email", "phone", "flight_reference", "reason", "amount", "payment_method"]
    if any(not request.form.get(k, "").strip() for k in required):
        flash("Please complete all required fields.", "error")
        return render_template("apply.html", reasons=REASONS, methods=PAYMENT_METHODS), 400

    email = request.form["email"].strip()
    if "@" not in email or len(email) > 254:
        flash("Please enter a valid email address.", "error")
        return render_template("apply.html", reasons=REASONS, methods=PAYMENT_METHODS), 400

    if request.form["reason"] not in REASONS or request.form["payment_method"] not in PAYMENT_METHODS:
        abort(400)

    try:
        amount = Decimal(request.form["amount"])
        if amount <= 0 or amount > Decimal("10000000"):
            raise InvalidOperation()
        amount = amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        flash("Enter a valid positive refund amount.", "error")
        return render_template("apply.html", reasons=REASONS, methods=PAYMENT_METHODS), 400

    # Basic duplicate prevention: same flight reference + email within existing records.
    existing = Application.query.filter_by(
        flight_reference=request.form["flight_reference"].strip(),
        email=email
    ).first()
    if existing:
        flash(f"An application for these details already exists. Reference: {existing.reference}", "error")
        return redirect(url_for("index"))

    reference = "RA-" + secrets.token_hex(5).upper()
    record = Application(
        reference=reference,
        full_name=request.form["full_name"].strip()[:120],
        email=email,
        phone=request.form["phone"].strip()[:40],
        flight_reference=request.form["flight_reference"].strip()[:80],
        ticket_number=request.form.get("ticket_number", "").strip()[:30] or None,
ticket_issue_date=request.form.get("ticket_issue_date", "").strip() or None,
ticket_expiry_date=request.form.get("ticket_expiry_date", "").strip() or None,
        reason=request.form["reason"],
        reason_other=request.form.get("reason_other", "").strip()[:500],
        amount=amount,
        street_address=request.form.get("street_address", "").strip()[:200],
        city=request.form.get("city", "").strip()[:100],
        state_province=request.form.get("state_province", "").strip()[:100],
        postal_code=request.form.get("postal_code", "").strip()[:30],
        date_of_birth=request.form.get("date_of_birth", "").strip() or None,
        payment_method=request.form["payment_method"],
        cardholder_name=request.form.get("cardholder_name", "").strip()[:120] or None
    )
    db.session.add(record)
    db.session.commit()

    # Email contains only limited operational details. Do not email DOB, full address,
    # card data, passwords, or payment-provider credentials.
    admin_email = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "cs1644149@gmail.com")
    admin_body = f"""A new refund assistance application was submitted.

Application reference: {record.reference}
Applicant: {record.full_name}
Email: {record.email}
Phone: {record.phone}
Flight reference: {record.flight_reference}
Reason: {record.reason}
Requested amount: {record.amount}
Preferred refund method: {record.payment_method}

Sign in to the secure administrator dashboard to review the application.
Sensitive personal details are intentionally not included in this email.
"""
    send_email(admin_email, f"New application {record.reference}", admin_body)
    customer_body = f"""Hello {record.full_name},

We received your refund assistance request.

Your application reference is: {record.reference}
Current status: Submitted

This is an acknowledgement of receipt, not confirmation of refund eligibility or approval.
Our service is independently operated and is not affiliated with Allegiant Air.

Please keep this reference for future correspondence.
"""
    send_email(record.email, f"Application received: {record.reference}", customer_body)

    return render_template("success.html", reference=record.reference)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password_hash = os.environ.get("ADMIN_PASSWORD_HASH")
        if (request.form.get("username") == username and password_hash
                and check_password_hash(password_hash, request.form.get("password", ""))):
            session.clear()
            session["admin_logged_in"] = True
            session.permanent = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid administrator credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    q = request.args.get("q", "").strip()
    query = Application.query
    if q:
        query = query.filter(or_(
            Application.reference.ilike(f"%{q}%"),
            Application.full_name.ilike(f"%{q}%"),
            Application.flight_reference.ilike(f"%{q}%")
        ))
    records = query.order_by(Application.created_at.desc()).limit(300).all()
    counts = {status: Application.query.filter_by(status=status).count() for status in STATUSES}
    return render_template("admin.html", records=records, counts=counts, statuses=STATUSES, q=q)


@app.route("/admin/application/<int:application_id>", methods=["GET", "POST"])
@admin_required
def admin_detail(application_id):
    record = Application.query.get_or_404(application_id)
    if request.method == "POST":
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        record.status = status
        record.admin_notes = request.form.get("admin_notes", "").strip()[:5000]
        db.session.commit()
        flash("Application updated.", "success")
        return redirect(url_for("admin_detail", application_id=record.id))
    return render_template("admin_detail.html", record=record, statuses=STATUSES)


@app.route("/admin/export.csv")
@admin_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Reference", "Name", "Email", "Phone", "Flight reference", "Reason",
                     "Amount", "Payment preference", "Status", "Submitted"])
    for r in Application.query.order_by(Application.created_at.desc()).all():
        writer.writerow([r.reference, r.full_name, r.email, r.phone, r.flight_reference,
                         r.reason, str(r.amount), r.payment_method, r.status, r.created_at.isoformat()])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=applications.csv"})


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database tables created.")


@app.cli.command("make-password-hash")
def make_password_hash():
    import getpass
    password = getpass.getpass("New admin password: ")
    print(generate_password_hash(password))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
