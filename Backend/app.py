import json
import os
import secrets
import time

from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS

from models import Comment, Post, User
from social_media import SocialMedia

app = Flask(__name__)
app.secret_key = "zivo-dev-secret"

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
)

social = SocialMedia()
tokens = {}
reset_tokens = {}
RESET_SECONDS = 30 * 60

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
FRONTEND = os.path.abspath(os.path.join(BASE_DIR, "..", "Frontend"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


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

    saved_tokens = []
    for token, email in tokens.items():
        saved_tokens.append({"token": token, "email": email})

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
        "tokens": saved_tokens,
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
    tokens.clear()
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

    for row in data.get("tokens", []):
        email = row["email"]
        if email in social.users_by_email:
            tokens[row["token"]] = email

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
    if token != "" and token in tokens:
        email = tokens[token]
        return social.users_by_email.get(email)

    email = session.get("email")
    if email is None:
        return None
    return social.users_by_email.get(email)


def new_token(email):
    token = secrets.token_hex(16)
    tokens[token] = email
    return token


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
    }


def comment_public(comment):
    return {
        "id": comment.comment_id,
        "name": comment.author.name,
        "email": comment.author.email,
        "username": comment.author.username,
        "photo": photo_path(comment.author.photo),
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

    session["email"] = user.email
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

    session["email"] = user.email
    token = new_token(user.email)
    save_data()
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
    })


@app.post("/logout")
def logout():
    token = read_token()
    if token in tokens:
        del tokens[token]
    session.clear()
    save_data()
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
