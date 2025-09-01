import os, json, requests, uuid
from flask import (
    Flask, send_from_directory, request, session,
    redirect, render_template_string, send_file
)
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = "super-secret-key"   # change for production!

# 🔑 Paystack Keys
PAYSTACK_SECRET_KEY = "sk_test_xxxxx"   # replace with your real secret key

# --- Email Config (Gmail SMTP example) ---
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "yourgmail@gmail.com"   # replace
app.config["MAIL_PASSWORD"] = "your-app-password"     # Gmail app password
app.config["MAIL_DEFAULT_SENDER"] = ("Ultimate Comics", "yourgmail@gmail.com")

mail = Mail(app)

# --- Users stored in JSON ---
USERS_FILE = "users.json"
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

def load_users():
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


# --- Serve static pages ---
@app.route("/")
def home():
    return send_from_directory("pages", "main.html")

@app.route("/<path:filename>")
def static_pages(filename):
    return send_from_directory("pages", filename)


# --- Signup with Paystack + Email Verification ---
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    reference = data.get("ref")

    users = load_users()
    if username in users:
        return "User already exists", 400

    # Verify Paystack payment
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if not response["status"] or response["data"]["status"] != "success":
        return "Payment verification failed", 403

    # Generate verification token
    token = str(uuid.uuid4())

    # Save user (unverified)
    users[username] = {
        "password": password,
        "email": email,
        "verified": False,
        "token": token
    }
    save_users(users)

    # Send verification email
    verify_url = f"http://127.0.0.1:5000/verify/{token}"
    msg = Message("Verify your account", recipients=[email])
    msg.body = f"Hello {username},\n\nPlease click this link to verify your account:\n{verify_url}\n\nThanks!"
    mail.send(msg)

    return "Account created. Please check your email to verify."


# --- Email Verification ---
@app.route("/verify/<token>")
def verify_email(token):
    users = load_users()
    for username, info in users.items():
        if info.get("token") == token:
            users[username]["verified"] = True
            save_users(users)
            return f"✅ {username}, your email has been verified! You can now <a href='/signin.html'>login</a>."
    return "Invalid or expired token", 400


# --- Login / Logout ---
@app.route("/login", methods=["POST"])
def login():
    data = request.form
    username = data.get("username")
    password = data.get("password")

    users = load_users()
    if username in users and users[username]["password"] == password:
        if not users[username]["verified"]:
            return "Please verify your email first.", 403
        session["user"] = username
        return redirect("/bookshop.html")
    return "Invalid credentials", 401

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/signin.html")


# --- Books JSON ---
@app.route("/get-books")
def get_books():
    return send_from_directory("static", "books.json")


# --- Secure Download ---
@app.route("/download/<int:book_id>")
def download_book(book_id):
    reference = request.args.get("ref")
    if not reference:
        return "Missing payment reference", 400

    # Verify Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if response["status"] and response["data"]["status"] == "success":
        with open("static/books.json") as f:
            books = json.load(f)
        book = next((b for b in books if b["id"] == book_id), None)
        if book:
            return send_file(f".{book['file']}", as_attachment=True)

    return "Payment not verified", 403


# --- Submit Book (Login + Paystack required) ---
UPLOAD_FOLDER = "protected"
COVER_FOLDER = "static/covers"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVER_FOLDER, exist_ok=True)

@app.route("/submit-book", methods=["POST"])
def submit_book():
    if "user" not in session:
        return "You must be logged in to submit books", 403

    reference = request.form.get("ref")
    title = request.form.get("title")
    price = int(request.form.get("price", 0))
    file = request.files.get("file")
    cover = request.files.get("cover")

    if not reference or not file or not cover or not title:
        return "Missing fields", 400

    # Verify Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if response["status"] and response["data"]["status"] == "success":
        # Save cover
        cover_filename = secure_filename(cover.filename)
        cover_path = os.path.join(COVER_FOLDER, cover_filename)
        cover.save(cover_path)

        # Save book as PDF
        book_filename = secure_filename(file.filename)
        if not book_filename.endswith(".pdf"):
            book_filename += ".pdf"
        book_path = os.path.join(UPLOAD_FOLDER, book_filename)
        file.save(book_path)

        # Update books.json
        with open("static/books.json") as f:
            books = json.load(f)
        new_id = max([b["id"] for b in books]) + 1 if books else 1
        books.append({
            "id": new_id,
            "title": title,
            "price": price,
            "cover": f"/static/covers/{cover_filename}",
            "file": f"/protected/{book_filename}"
        })
        with open("static/books.json", "w") as f:
            json.dump(books, f, indent=2)

        return redirect("/bookshop.html")
    else:
        return "Payment verification failed", 403


# --- Dynamic Bookshop with Submit Button ---
@app.route("/bookshop.html")
def bookshop_page():
    with open("pages/bookshop.html") as f:
        html = f.read()

    if "user" in session:
        submit_button = f'<a href="/submit.html" style="margin-left:20px; color:orange; font-weight:bold;">📚 Submit Book</a> | <a href="/logout" style="color:red;">Logout</a>'
    else:
        submit_button = '<a href="/signin.html" style="margin-left:20px; color:orange; font-weight:bold;">🔑 Login to Submit</a>'

    # inject button before </body>
    html = html.replace("</body>", f"{submit_button}</body>")
    return render_template_string(html)


if __name__ == "__main__":
    os.makedirs("pages", exist_ok=True)
    os.makedirs("static/covers", exist_ok=True)
    os.makedirs("protected", exist_ok=True)
    app.run(debug=True, port=5000)
