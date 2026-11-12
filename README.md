# Independent Flight Refund Assistance Portal

A Flask starter application for an **independent** flight refund assistance service. It is not affiliated with, endorsed by, or an agent of Allegiant Air. Do not use airline logos, official-looking branding, or wording that implies authorization unless you have written permission.

## Included
- Responsive customer application form with the requested contact, flight, refund, address, optional DOB, payment preference, and cardholder-name fields.
- Flask backend and SQLite database (PostgreSQL-ready).
- Unique application references and basic duplicate detection.
- Gmail SMTP notifications to `cs1644149@gmail.com` and customer acknowledgement.
- Admin login, search, status updates, internal notes, and CSV export.
- CSRF protection and secure password hashing.

## Payment safety
This starter deliberately does **not** collect card numbers, expiry dates, CVV/CVC codes, bank passwords, or payment credentials. Never request or email these. If a legitimate payment workflow is required, integrate a PCI DSS-compliant provider's hosted payment/refund flow and follow the provider's requirements. Cardholder name is not sufficient to issue a refund; refunds should generally follow the original payment method and the relevant provider/airline process.

## Local setup (Windows PowerShell)
1. Install Python 3.11 or newer.
2. Extract this ZIP and open PowerShell in the project folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
4. Install packages:
   ```powershell
   pip install -r requirements.txt
   ```
   If the `gunicorn` line causes an installation issue on Windows, remove it locally; it is for Linux deployment.
5. Copy `.env.example` to `.env` and fill in the settings. Install `python-dotenv` and add `from dotenv import load_dotenv; load_dotenv()` near the top of `app.py` if you want Flask to load `.env` automatically, or set environment variables in PowerShell.
6. Generate an admin password hash:
   ```powershell
   $env:FLASK_APP = "app.py"
   flask make-password-hash
   ```
   Copy the printed hash into `ADMIN_PASSWORD_HASH`. Set a strong, unique `ADMIN_USERNAME`.
7. Initialize the database:
   ```powershell
   flask init-db
   ```
8. Run:
   ```powershell
   python app.py
   ```
9. Visit `http://127.0.0.1:5000`. Admin login is at `/admin/login`.

## Gmail configuration
Use Gmail SMTP with a Google App Password only if your Google account supports it and two-step verification is enabled. Never put your normal Gmail password in source code. For production, consider Gmail API with OAuth or a transactional email provider. Test delivery before launch.

## Production checklist
- Set a long random `SECRET_KEY`.
- Set `COOKIE_SECURE=1` behind HTTPS.
- Use PostgreSQL and managed backups.
- Set environment variables in the hosting provider; do not commit `.env`.
- Use a strong admin password and restrict dashboard access.
- Add rate limiting, login lockout/MFA, audit logging, security monitoring, and automated backups.
- Configure HTTPS, secure headers, and a production WSGI server.
- Add a clear operator legal name, physical/contact address, service fees (if any), refund/complaint process, data retention period, privacy contact, and jurisdiction-specific privacy disclosures.
- Collect only personal information necessary for the service. Date of birth is optional in this starter; remove it unless there is a documented lawful need.
- Have privacy, consumer-protection, trademark, and aviation-law disclosures reviewed by a qualified professional before accepting real customer data.
- Do not claim to determine airline refund eligibility or promise compensation.
- Confirm that you have a lawful basis to receive and process customer information, including any cross-border transfers.

## Important limitations
This is a functional starter, not a certified production payment system or legal compliance guarantee. Email notifications intentionally omit date of birth and full residential address. Authorized administrators can review submitted records in the dashboard.
