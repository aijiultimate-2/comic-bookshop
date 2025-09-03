import os, json, requests, uuid
from flask import Flask, send_from_directory, request, session, redirect, render_template_string, send_file
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

# ------------------ Flask App ------------------
app = Flask(__name__, static_folder="static")
app.secret_key = "super-secret-key"  # CHANGE IN PRODUCTION

# ------------------ Paystack Config ------------------
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_xxxxx")  # use env in production

# ------------------ Mail Config ------------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get("MAIL_USERNAME", "yourgmail@gmail.com"),
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", "your-app-password"),
    MAIL_DEFAULT_SENDER=("Ultimate Comics", os.environ.get("MAIL_USERNAME", "yourgmail@gmail.com"))
)
mail = Mail(app)

# ------------------ Users JSON ------------------
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

# ------------------ Current Folder ------------------
CURRENT_FOLDER = os.getcwd()  # C.HTML folder

# ------------------ Routes ------------------
@app.route("/")
def root():
    return send_from_directory(CURRENT_FOLDER, "intro.html")

@app.route("/MAIN.HTML")
def main():
    return send_from_directory(CURRENT_FOLDER, "MAIN.HTML")

@app.route("/<path:filename>")
def pages_route(filename):
    file_path = os.path.join(CURRENT_FOLDER, filename)
    if os.path.exists(file_path):
        return send_from_directory(CURRENT_FOLDER, filename)
    return "File not found", 404
@app.route("/payment.html")
def pay_page():
    with open(os.path.join(CURRENT_FOLDER, "static", "books.json")) as f:
        books = json.load(f)
    return render_template("pay.html", books=books)

# ------------------ Payment.html ------------------
@app.route("/pay.html/<int:book_id>")
def payment_page(book_id):
    if "user" not in session:
        return redirect("/signin.html")

    users = load_users()
    with open(os.path.join(CURRENT_FOLDER, "static", "books.json")) as f:
        books = json.load(f)
    book = next((b for b in books if b["id"] == book_id), None)
    if not book:
        return "Book not found", 404

    # Initialize Paystack payment
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": users[session["user"]]["email"],
        "amount": book["price"] * 100,
        "callback_url": f"http://127.0.0.1:5000/verify-payment/{book_id}"
    }
    response = requests.post(url, headers=headers, json=payload).json()

    if response.get("status"):
        return render_template("payment.html", payment_url=response["data"]["authorization_url"], book=book)
    return "Payment initialization failed", 500

# ------------------ Signup ------------------
@app.route("/create.html", methods=["POST"])
def create():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    reference = data.get("ref")

    if not all([username, password, email, reference]):
        return "Missing fields", 400

    users = load_users()
    if username in users:
        return "User already exists", 400

    # Verify Paystack payment
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if not response.get("status") or response["data"]["status"] != "success":
        return "Payment verification failed", 403

    # Save user with verification token
    token = str(uuid.uuid4())
    users[username] = {"password": password, "email": email, "verified": False, "token": token}
    save_users(users)

    verify_url = f"http://127.0.0.1:5000/verify/{token}"
    msg = Message("Verify your account", recipients=[email])
    msg.body = f"Hello {username},\nPlease verify your account: {verify_url}"
    mail.send(msg)

    return "Account created. Check your email to verify."

# ------------------ Verify Email ------------------
@app.route("/success.html")
def verify_email(token):
    users = load_users()
    for username, info in users.items():
        if info.get("token") == token:
            users[username]["verified"] = True
            save_users(users)
            return f"✅ {username}, your email verified! <a href='/signin.html'>Login</a>"
    return "Invalid or expired token", 400

# ------------------ Login / Logout ------------------
@app.route("/signin", methods=["POST"])
def login():
    data = request.form
    username = data.get("username")
    password = data.get("password")
    users = load_users()
    if username in users and users[username]["password"] == password:
        if not users[username]["verified"]:
            return "Please verify your email first", 403
        session["user"] = username
        return redirect("/book.html")
    return "Invalid credentials", 401

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/signin.html")

# ------------------ Books JSON ------------------
@app.route("/get-books")
def get_books():
    return send_from_directory(os.path.join(CURRENT_FOLDER, "static"), "books.json")

# ------------------ Secure Book Download ------------------
@app.route("/download/<int:book_id>")
def download_book(book_id):
    reference = request.args.get("ref")
    if not reference:
        return "Missing payment reference", 400

    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if response.get("status") and response["data"]["status"] == "success":
        with open(os.path.join(CURRENT_FOLDER, "static", "books.json")) as f:
            books = json.load(f)
        book = next((b for b in books if b["id"] == book_id), None)
        if book:
            return send_file(os.path.join(CURRENT_FOLDER, book['file']), as_attachment=True)

    return "Payment not verified", 403

# ------------------ Book Submission ------------------
UPLOAD_FOLDER = os.path.join(CURRENT_FOLDER, "protected")
COVER_FOLDER = os.path.join(CURRENT_FOLDER, "static", "covers")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVER_FOLDER, exist_ok=True)

@app.route("/submit.html", methods=["POST"])
def submit_book():
    if "user" not in session:
        return "Login required", 403

    reference = request.form.get("ref")
    title = request.form.get("title")
    price = int(request.form.get("price", 0))
    file = request.files.get("file")
    cover = request.files.get("cover")
    if not all([reference, title, file, cover]):
        return "Missing fields", 400

    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()
    if not (response.get("status") and response["data"]["status"] == "success"):
        return "Payment verification failed", 403

    cover_path = os.path.join(COVER_FOLDER, secure_filename(cover.filename))
    cover.save(cover_path)
    book_filename = secure_filename(file.filename)
    if not book_filename.endswith(".pdf"):
        book_filename += ".pdf"
    book_path = os.path.join(UPLOAD_FOLDER, book_filename)
    file.save(book_path)

    books_file = os.path.join(CURRENT_FOLDER, "static", "books.json")
    with open(books_file) as f:
        books = json.load(f)
    new_id = max([b["id"] for b in books], default=0) + 1
    books.append({
        "id": new_id,
        "title": title,
        "price": price,
        "cover": f"/static/covers/{secure_filename(cover.filename)}",
        "file": f"/protected/{book_filename}"
    })
    with open(books_file, "w") as f:
        json.dump(books, f, indent=2)
    return redirect("/book.html")

# ------------------ Book Purchase Flow ------------------
@app.route("/buy/<int:book_id>", methods=["POST"])
def buy_book(book_id):
    users = load_users()
    if "user" not in session:
        return "Login required", 403

    with open(os.path.join(CURRENT_FOLDER, "static", "books.json")) as f:
        books = json.load(f)
    book = next((b for b in books if b["id"] == book_id), None)
    if not book:
        return "Book not found", 404

    # Initialize Paystack payment
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": users[session["user"]]["email"],
        "amount": book["price"] * 100,  # kobo
        "callback_url": f"http://127.0.0.1:5000/verify-payment/{book_id}",
        "metadata": {"book_id": book_id, "username": session["user"]}
    }
    response = requests.post(url, headers=headers, json=payload).json()
    if response.get("status"):
        return {"payment_url": response["data"]["authorization_url"]}
    return "Payment initialization failed", 500

@app.route("/verify-payment/<int:book_id>")
def verify_payment(book_id):
    reference = request.args.get("reference")
    if not reference:
        return "Missing reference", 400

    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if response.get("status") and response["data"]["status"] == "success":
        with open(os.path.join(CURRENT_FOLDER, "static", "books.json")) as f:
            books = json.load(f)
        book = next((b for b in books if b["id"] == book_id), None)
        if book:
            return redirect(book["file"])
    return "Payment failed", 403

# ------------------ Dynamic Book Page ------------------
@app.route("/book.html")
def bookshop_page():
    file_path = os.path.join(CURRENT_FOLDER, "book.html")
    if not os.path.exists(file_path):
        return "File not found", 404
    with open(file_path) as f:
        html = f.read()

    if "user" in session:
        submit_button = '<a href="/submit.html" style="margin-left:20px;color:orange;font-weight:bold;">📚 Submit Book</a> | <a href="/logout" style="color:red;">Logout</a>'
    else:
        submit_button = '<a href="/signin.html" style="margin-left:20px;color:orange;font-weight:bold;">🔑 Login to Submit</a>'
    html = html.replace("</body>", f"{submit_button}</body>")
    return render_template_string(html)

# ------------------ Run App ------------------
if __name__ == "__main__":
    os.makedirs(os.path.join(CURRENT_FOLDER, "static", "covers"), exist_ok=True)
    os.makedirs(os.path.join(CURRENT_FOLDER, "protected"), exist_ok=True)
    app.run(debug=True, port=5000)
