import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
import stripe
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from models import Comment, Post, User
from social_media import SocialMedia

app = Flask(__name__)
app.secret_key = os.environ.get("JWT_SECRET", "zivo-dev-secret-change-me-32b-secure-jwt")

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
)

social = SocialMedia()
reset_tokens = {}
revoked_tokens = set()
RESET_SECONDS = 30 * 60
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_SECONDS = 7 * 24 * 60 * 60
PREMIUM_PRICE_CENTS = 499

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
FRONTEND = os.path.abspath(os.path.join(BASE_DIR, "..", "Frontend"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def load_env():
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path) as file:
        for line in file:
            line = line.strip()
            if line == "" or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_env()
app.secret_key = os.environ.get("JWT_SECRET", app.secret_key)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def save_data():
    users = []
    for user in social.users:
        users.append({
            "id": user.user_id,
            "name": user.name,
            "email": user.email,
            "password": user.password,
            "username": user.username,
            "bio": user.bio,
            "photo": user.photo,
            "cover": user.cover,
            "premium": bool(user.premium),
        })

    posts = []
    for post in social.posts:
        comments = []
        for comment in post.comments.traverse():
            comments.append({
                "id": comment.comment_id,
                "email": comment.author.email,
                "text": comment.text,
            })
        posts.append({
            "id": post.post_id,
            "email": post.author.email,
            "text": post.text,
            "image": post.image,
            "likes": post.likes,
            "comments": comments,
        })

    saved_resets = []
    for token, record in reset_tokens.items():
        saved_resets.append({
            "token": token,
            "email": record["email"],
            "expires": record["expires"],
        })

    data = {
        "users": users,
        "posts": posts,
        "reset_tokens": saved_resets,
        "following": social.following,
        "next_user_id": social.next_user_id,
        "next_post_id": social.next_post_id,
        "next_comment_id": social.next_comment_id,
    }
    with open(DATA_FILE, "w") as file:
        json.dump(data, file)


def load_data():
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE) as file:
        data = json.load(file)

    social.users = []
    social.users_by_email = {}
    social.posts = []
    social.following = {}
    reset_tokens.clear()

    for row in data.get("users", []):
        user = User(
            row["id"],
            row["name"],
            row["email"],
            row["password"],
            row.get("username", ""),
            row.get("bio", ""),
            row.get("photo", ""),
            row.get("cover", ""),
        )
        user.premium = bool(row.get("premium", False))
        social.users.append(user)
        social.users_by_email[user.email] = user
        social.friends.add_user(user.email)

    for row in data.get("posts", []):
        author = social.users_by_email.get(row["email"])
        if author is None:
            continue
        post = Post(row["id"], author, row["text"], row.get("image", ""))
        for email in row.get("likes", []):
            if email in social.users_by_email:
                post.likes.append(email)
        for saved in row.get("comments", []):
            comment_author = social.users_by_email.get(saved.get("email"))
            if comment_author is None:
                continue
            comment = Comment(saved["id"], comment_author, saved.get("text", ""))
            post.comments.insert_at_end(comment)
            if comment.comment_id >= social.next_comment_id:
                social.next_comment_id = comment.comment_id + 1
        social.posts.append(post)

    saved_following = data.get("following", {})
    for email, others in saved_following.items():
        if email not in social.users_by_email:
            continue
        kept = []
        for other in others:
            if other in social.users_by_email and other != email:
                kept.append(other)
        social.following[email] = kept

    now = time.time()
    for row in data.get("reset_tokens", []):
        email = row.get("email", "")
        expires = row.get("expires", 0)
        if email in social.users_by_email and expires > now:
            reset_tokens[row["token"]] = {"email": email, "expires": expires}

    if "next_user_id" in data:
        social.next_user_id = data["next_user_id"]
    if "next_post_id" in data:
        social.next_post_id = data["next_post_id"]
    if "next_comment_id" in data and data["next_comment_id"] > social.next_comment_id:
        social.next_comment_id = data["next_comment_id"]


def read_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def current_user():
    token = read_token()
    if token == "" or token in revoked_tokens:
        return None

    try:
        payload = jwt.decode(token, app.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    email = payload.get("sub")
    if not email:
        return None
    return social.users_by_email.get(email)


def new_token(email):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(seconds=JWT_EXPIRES_SECONDS),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, app.secret_key, algorithm=JWT_ALGORITHM)


def save_upload(file_storage):
    if file_storage is None or file_storage.filename == "":
        return ""

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_IMAGES:
        return None

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size == 0:
        return ""
    if size > MAX_IMAGE_BYTES:
        return None

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = secrets.token_hex(8) + ext
    file_storage.save(os.path.join(UPLOAD_DIR, name))
    return name


def photo_path(filename):
    if filename == "":
        return ""
    return "/uploads/" + filename


def follower_count(email):
    count = 0
    for followed in social.following.values():
        if email in followed:
            count = count + 1
    return count


def profile_payload(user, viewer):
    posts = []
    for post in reversed(social.posts):
        if post.author.email == user.email:
            posts.append(post_public(post, viewer.email))

    return {
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "bio": user.bio,
        "photo": photo_path(user.photo),
        "cover": photo_path(user.cover),
        "is_self": viewer.email == user.email,
        "following": social.is_following(viewer.email, user.email),
        "followers_count": follower_count(user.email),
        "following_count": len(social.following.get(user.email, [])),
        "premium": bool(user.premium),
        "posts": posts,
    }


def user_public(user, viewer_email):
    return {
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "bio": user.bio,
        "photo": photo_path(user.photo),
        "following": social.is_following(viewer_email, user.email),
        "premium": bool(user.premium),
    }


def comment_public(comment):
    return {
        "id": comment.comment_id,
        "name": comment.author.name,
        "email": comment.author.email,
        "username": comment.author.username,
        "photo": photo_path(comment.author.photo),
        "premium": bool(comment.author.premium),
        "text": comment.text,
    }


def post_public(post, viewer_email=""):
    comments = []
    for comment in post.comments.traverse():
        comments.append(comment_public(comment))

    return {
        "id": post.post_id,
        "name": post.author.name,
        "email": post.author.email,
        "username": post.author.username,
        "photo": photo_path(post.author.photo),
        "premium": bool(post.author.premium),
        "text": post.text,
        "image": photo_path(post.image),
        "like_count": len(post.likes),
        "liked": viewer_email in post.likes,
        "comments": comments,
    }


def signup_error(name, email, username, password):
    name = name.strip()
    email = email.strip().lower()
    username = username.strip()
    password = password.strip()

    if name == "" or email == "" or password == "":
        return "Name, email and password cannot be empty."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if email in social.users_by_email:
        return "Account already exists."
    if username != "":
        for existing in social.users:
            if existing.username == username:
                return "Username already taken."
    return None


load_data()


@app.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    email = data.get("email", "")
    username = data.get("username", "")
    password = data.get("password", "")

    message = signup_error(name, email, username, password)
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    user = social.create_account(name, email, password, username)
    if user is None:
        return jsonify({"ok": False, "message": "Could not create that account."}), 400

    token = new_token(user.email)
    save_data()
    return jsonify({"ok": True, "token": token})


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    user = social.login(email, password)

    if user is None:
        return jsonify({"ok": False, "message": "Email or password is wrong."}), 400

    token = new_token(user.email)
    return jsonify({"ok": True, "token": token})


@app.post("/forgot")
def forgot():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    user = social.users_by_email.get(email)
    if user is not None:
        token = secrets.token_urlsafe(24)
        reset_tokens[token] = {
            "email": email,
            "expires": time.time() + RESET_SECONDS,
        }
        save_data()
        link = "http://127.0.0.1:5000/resetpassword.html?token=" + token
        print("", flush=True)
        print("Password reset link (valid for 30 minutes):", flush=True)
        print(link, flush=True)
        print("", flush=True)

    return jsonify({
        "ok": True,
        "message": "If that email has an account, the reset link is in the server terminal.",
    })


@app.post("/reset")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    record = reset_tokens.get(token)
    if record is None or record["expires"] < time.time():
        if token in reset_tokens:
            del reset_tokens[token]
            save_data()
        return jsonify({"ok": False, "message": "That reset link is invalid or expired."}), 400

    message = social.set_password(record["email"], data.get("password", ""))
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    del reset_tokens[token]
    save_data()
    return jsonify({"ok": True, "message": "Password updated. You can sign in."})


@app.get("/me")
def me():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    return jsonify({
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "bio": user.bio,
        "photo": photo_path(user.photo),
        "cover": photo_path(user.cover),
        "following_count": len(social.following.get(user.email, [])),
        "premium": bool(user.premium),
    })


@app.get("/premium/config")
def premium_config():
    return jsonify({
        "ok": True,
        "publishableKey": os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        "priceCents": PREMIUM_PRICE_CENTS,
        "priceFormatted": f"${PREMIUM_PRICE_CENTS / 100:.2f}",
    })


@app.post("/premium/checkout")
def premium_checkout():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    if user.premium:
        return jsonify({"ok": True, "already": True})
    if not stripe.api_key:
        return jsonify({"ok": False, "message": "Stripe is not configured."}), 500

    origin = request.headers.get("Origin") or request.host_url.rstrip("/")
    referer = request.headers.get("Referer")
    if referer:
        redirect_base = referer.split("?")[0].rstrip("/")
    else:
        redirect_base = origin + "/premium.html"

    try:
        checkout = stripe.checkout.Session.create(
            mode="payment",
            customer_email=user.email,
            client_reference_id=user.email,
            metadata={"email": user.email},
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": PREMIUM_PRICE_CENTS,
                    "product_data": {
                        "name": "Zivo Premium",
                        "description": "Verified badge and Premium on your Zivo account.",
                    },
                },
            }],
            success_url=f"{redirect_base}?success=1&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{redirect_base}?canceled=1",
        )
    except stripe.StripeError as e:
        return jsonify({"ok": False, "message": str(e) or "Could not start checkout. Try again."}), 400
    except Exception:
        return jsonify({"ok": False, "message": "Could not start checkout. Try again."}), 400

    return jsonify({"ok": True, "url": checkout.url})


@app.post("/premium/confirm")
def premium_confirm():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    if user.premium:
        return jsonify({"ok": True, "premium": True})
    if not stripe.api_key:
        return jsonify({"ok": False, "message": "Stripe is not configured."}), 500

    session_id = (request.get_json(silent=True) or {}).get("session_id", "").strip()
    if session_id == "":
        return jsonify({"ok": False, "message": "Missing checkout session."}), 400

    try:
        checkout = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError as e:
        return jsonify({"ok": False, "message": str(e) or "Could not verify that payment."}), 400

    paid = checkout.payment_status == "paid"
    email = ""
    if checkout.metadata:
        email = checkout.metadata.get("email", "")
    if not email:
        email = checkout.client_reference_id or ""
    if not email:
        email = checkout.customer_email or ""

    if not paid or email.strip().lower() != user.email.strip().lower():
        return jsonify({"ok": False, "message": "Payment is not complete."}), 400

    user.premium = True
    save_data()
    return jsonify({"ok": True, "premium": True})


@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

    event = None
    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except (ValueError, stripe.SignatureVerificationError):
            return jsonify({"ok": False, "message": "Invalid webhook signature"}), 400
    else:
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception:
            return jsonify({"ok": False, "message": "Invalid JSON"}), 400

    event_type = event.get("type") if isinstance(event, dict) else getattr(event, "type", "")
    data_obj = (
        event.get("data", {}).get("object", {})
        if isinstance(event, dict)
        else getattr(getattr(event, "data", None), "object", {})
    )

    if event_type == "checkout.session.completed":
        session_obj = data_obj
        paid = (
            session_obj.get("payment_status")
            if isinstance(session_obj, dict)
            else getattr(session_obj, "payment_status", "")
        ) == "paid"
        metadata = (
            session_obj.get("metadata", {})
            if isinstance(session_obj, dict)
            else getattr(session_obj, "metadata", {}) or {}
        )
        email = (
            metadata.get("email")
            if isinstance(metadata, dict)
            else getattr(metadata, "email", "")
        )
        if not email:
            email = (
                session_obj.get("client_reference_id")
                if isinstance(session_obj, dict)
                else getattr(session_obj, "client_reference_id", "")
            )
        if not email:
            email = (
                session_obj.get("customer_email")
                if isinstance(session_obj, dict)
                else getattr(session_obj, "customer_email", "")
            )

        if paid and email:
            email = str(email).strip().lower()
            target_user = social.users_by_email.get(email)
            if target_user:
                target_user.premium = True
                save_data()

    return jsonify({"ok": True, "received": True})


@app.post("/logout")
def logout():
    token = read_token()
    if token:
        revoked_tokens.add(token)
    return jsonify({"ok": True})


@app.get("/posts")
def list_posts():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    rows = []
    for post in reversed(social.posts):
        rows.append(post_public(post, user.email))
    return jsonify(rows)


@app.post("/posts")
def add_post():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    image_name = ""
    if request.content_type and "multipart/form-data" in request.content_type:
        text = request.form.get("text", "")
        image_name = save_upload(request.files.get("image"))
        if image_name is None:
            return jsonify({"ok": False, "message": "Use a jpg, png, gif, or webp under 2 MB."}), 400
    else:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")

    post = social.create_post(user.email, text, image_name)
    if post is None:
        return jsonify({"ok": False, "message": "Write something or add an image."}), 400

    save_data()
    return jsonify(post_public(post, user.email))


@app.post("/posts/<int:post_id>/like")
def toggle_like(post_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    post = social.find_post(post_id)
    if post is None:
        return jsonify({"ok": False, "message": "Post not found."}), 404

    if user.email in post.likes:
        message = social.unlike_post(user.email, post_id)
    else:
        message = social.like_post(user.email, post_id)

    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    save_data()
    return jsonify(post_public(post, user.email))


@app.post("/posts/<int:post_id>/comments")
def comment_on_post(post_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = social.add_comment(user.email, post_id, data.get("text", ""))
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    post = social.find_post(post_id)
    save_data()
    return jsonify(post_public(post, user.email))


@app.post("/posts/<int:post_id>/edit")
def edit_post(post_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = social.update_post(user.email, post_id, data.get("text", ""))
    if message is not None:
        status = 404 if message == "Post not found." else 400
        return jsonify({"ok": False, "message": message}), status

    save_data()
    return jsonify(post_public(social.find_post(post_id), user.email))


@app.post("/posts/<int:post_id>/delete")
def remove_post(post_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message = social.delete_post(user.email, post_id)
    if message is not None:
        status = 404 if message == "Post not found." else 400
        return jsonify({"ok": False, "message": message}), status

    save_data()
    return jsonify({"ok": True, "id": post_id})


@app.post("/posts/<int:post_id>/comments/<int:comment_id>/edit")
def edit_comment(post_id, comment_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = social.update_comment(user.email, post_id, comment_id, data.get("text", ""))
    if message is not None:
        status = 404 if message in ("Post not found.", "Comment not found.") else 400
        return jsonify({"ok": False, "message": message}), status

    save_data()
    return jsonify(post_public(social.find_post(post_id), user.email))


@app.post("/posts/<int:post_id>/comments/<int:comment_id>/delete")
def remove_comment(post_id, comment_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message = social.delete_comment(user.email, post_id, comment_id)
    if message is not None:
        status = 404 if message in ("Post not found.", "Comment not found.") else 400
        return jsonify({"ok": False, "message": message}), status

    save_data()
    return jsonify(post_public(social.find_post(post_id), user.email))


@app.get("/users")
def list_users():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    rows = []
    for other in social.users:
        if other.email == user.email:
            continue
        rows.append(user_public(other, user.email))
    return jsonify(rows)


@app.post("/follow")
def follow():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = social.find_person(data.get("user", ""))
    if other is None:
        return jsonify({"ok": False, "message": "User not found."}), 404

    message = social.follow_user(user.email, other.email)
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    save_data()
    return jsonify({"ok": True})


@app.post("/unfollow")
def unfollow():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = social.find_person(data.get("user", ""))
    if other is None:
        return jsonify({"ok": False, "message": "User not found."}), 404

    message = social.unfollow_user(user.email, other.email)
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    save_data()
    return jsonify({"ok": True})


@app.post("/settings")
def settings():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    name = request.form.get("name", user.name)
    bio = request.form.get("bio", "")
    photo_name = save_upload(request.files.get("photo"))
    cover_name = save_upload(request.files.get("cover"))
    if photo_name is None or cover_name is None:
        return jsonify({"ok": False, "message": "Use a jpg, png, gif, or webp under 2 MB."}), 400

    message = social.update_profile(user.email, name, bio, photo_name, cover_name)
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    save_data()
    return jsonify({
        "ok": True,
        "name": user.name,
        "bio": user.bio,
        "photo": photo_path(user.photo),
        "cover": photo_path(user.cover),
    })


@app.get("/profile")
def my_profile():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    return jsonify(profile_payload(user, user))


@app.get("/profile/<username>")
def view_profile(username):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    other = social.find_person(username)
    if other is None:
        return jsonify({"ok": False, "message": "User not found."}), 404
    return jsonify(profile_payload(other, user))


@app.get("/uploads/<filename>")
def uploaded_file(filename):
    safe = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        return jsonify({"ok": False, "message": "Not found."}), 404
    return send_from_directory(UPLOAD_DIR, safe)


@app.get("/")
def home_page():
    return send_from_directory(FRONTEND, "homepage.html")


@app.get("/<path:name>")
def frontend_file(name):
    folder = FRONTEND
    target = os.path.abspath(os.path.join(folder, name))
    if not target.startswith(folder + os.sep) or not os.path.isfile(target):
        return jsonify({"ok": False, "message": "Not found."}), 404
    return send_from_directory(folder, name)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
