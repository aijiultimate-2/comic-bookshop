import os, json, requests, uuid
from flask import Flask, send_from_directory, request, session, redirect, render_template, render_template_string, send_file
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

# ------------------ Flask App ------------------
app = Flask(__name__, static_folder="static")
app.secret_key = "super-secret-key"  # CHANGE IN PRODUCTION

# ------------------ Paystack Config ------------------
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_xxxxx")  # env in prod

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
CURRENT_FOLDER = os.getcwd()

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

# ------------------ Pay.html ------------------
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

# ------------------ Bookshop Page ------------------
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
