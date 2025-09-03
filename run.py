import os, json, requests, uuid
from flask import Flask, send_from_directory, request, session, redirect, send_file
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
CURRENT_FOLDER = os.getcwd()  # HTML folder

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

# ------------------ Signup (Create Account) ------------------
@app.route("/create", methods=["POST"])
def create_account():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    reference = data.get("ref")

    if not all([username, password, email, reference]):
        return {"msg": "Missing fields"}, 400

    users = load_users()
    if username in users:
        return {"msg": "User already exists"}, 400

    # Verify Paystack payment
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if not response.get("status") or response["data"]["status"] != "success":
        return {"msg": "Payment verification failed"}, 403

    # Save user with verification token
    token = str(uuid.uuid4())
    users[username] = {"password": password, "email": email, "verified": False, "token": token}
    save_users(users)

    verify_url = f"http://127.0.0.1:5000/verify/{token}"
    msg = Message("Verify your account", recipients=[email])
    msg.body = f"Hello {username},\nPlease verify your account: {verify_url}"
    mail.send(msg)

    return {"msg": "Account created. Check your email to verify."}

# ------------------ Verify Email ------------------
@app.route("/verify/<token>")
def verify_email(token):
    users = load_users()
    for username, info in users.items():
        if info.get("token") == token:
            users[username]["verified"] = True
            save_users(users)
            return f"✅ {username}, your email verified! <a href='/signin.html'>Login</a>"
    return "Invalid or expired token", 400

# ------------------ Login ------------------
@app.route("/signin", methods=["POST"])
def login_post():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    users = load_users()
    for username, info in users.items():
        if info["email"] == email and info["password"] == password:
            if not info["verified"]:
                return {"msg": "Please verify your email first"}, 403
            session["user"] = username
            return {"msg": "Login successful"}
    return {"msg": "Invalid credentials"}, 401

# ------------------ Logout ------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/signin.html")

# ------------------ Book Purchase Verification ------------------
@app.route("/buy_book", methods=["POST"])
def buy_book():
    if "user" not in session:
        return {"msg": "Login required"}, 403

    data = request.get_json()
    reference = data.get("reference")
    file_path = data.get("file")

    if not reference or not file_path:
        return {"msg": "Missing payment reference or file"}, 400

    # Verify payment with Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers).json()

    if not response.get("status") or response["data"]["status"] != "success":
        return {"msg": "Payment verification failed"}, 403

    # Check file exists
    local_path = os.path.join(CURRENT_FOLDER, file_path.lstrip("/"))
    if not os.path.exists(local_path):
        return {"msg": "Book file not found"}, 404

    return send_file(local_path, as_attachment=True)

# ------------------ Run App ------------------
if __name__ == "__main__":
    os.makedirs(os.path.join(CURRENT_FOLDER, "static", "covers"), exist_ok=True)
    os.makedirs(os.path.join(CURRENT_FOLDER, "protected"), exist_ok=True)
    app.run(debug=True, port=5000)
