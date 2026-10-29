import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
import stripe
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room

from cache import read_cache
from dbpool import ConnectionPool
from mail import absolute_url, send_password_changed, send_password_reset, send_welcome
from models import Blog, Chat, ChatMessage, Comment, Group, Post, User, Webinar, WebinarMessage
from social_media import CHAT_REACTIONS, WEBINAR_ROOM_CAP, SocialMedia
from workers import resize_upload

app = Flask(__name__)
app.secret_key = os.environ.get("JWT_SECRET", "zivo-dev-secret-change-me-32b-secure-jwt")

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type", "Authorization"],
)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

social = SocialMedia()
reset_tokens = {}
revoked_tokens = set()
live_rooms = {}
sid_rooms = {}
socket_users = {}
state_lock = threading.RLock()
HOST_GRACE_SECONDS = 20
SIGNAL_BYTES = 64 * 1024
RESET_SECONDS = 30 * 60
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_SECONDS = 7 * 24 * 60 * 60
PREMIUM_PRICE_CENTS = 499

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.environ.get("ZIVO_DATA_DIR", BASE_DIR)
DATA_FILE = os.path.join(DATA_ROOT, "data.json")
DB_FILE = os.path.join(DATA_ROOT, "zivo.db")
FRONTEND = os.path.abspath(os.path.join(BASE_DIR, "..", "Frontend"))
db_pool = ConnectionPool(DB_FILE)
UPLOAD_DIR = os.path.join(BASE_DIR, "temp")
LEGACY_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
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


def chat_rows():
    rows = []
    for chat in social.chats:
        members = []
        for email, last_read in chat.members.items():
            members.append({"email": email, "last_read": last_read})
        messages = []
        for message in chat.messages:
            messages.append({
                "id": message.message_id,
                "email": "" if message.author is None else message.author.email,
                "text": message.text,
                "image": message.image,
                "created_at": message.created_at,
                "system": bool(message.system),
                "edited": bool(message.edited),
                "reply_to": message.reply_to,
                "reactions": message.reactions,
            })
        rows.append({
            "id": chat.chat_id,
            "name": chat.name,
            "photo": chat.photo,
            "owner_email": chat.owner_email,
            "members": members,
            "messages": messages,
        })
    return rows


def webinar_rows():
    rows = []
    for webinar in social.webinars:
        messages = []
        for message in webinar.messages:
            messages.append({
                "id": message.message_id,
                "email": "" if message.author is None else message.author.email,
                "text": message.text,
                "created_at": message.created_at,
            })
        rows.append({
            "id": webinar.webinar_id,
            "title": webinar.title,
            "description": webinar.description,
            "cover": webinar.cover,
            "host_email": webinar.host_email,
            "visibility": webinar.visibility,
            "status": webinar.status,
            "starts_at": webinar.starts_at,
            "created_at": webinar.created_at,
            "ended_at": webinar.ended_at,
            "invited": list(webinar.invited),
            "messages": messages,
        })
    return rows


NOTE_PAGES = (
    "feed.html", "profile.html", "group.html", "groups.html", "chat.html", "chats.html",
    "webinar.html", "webinars.html", "blog.html", "blogs.html", "notifications.html",
)


def safe_note_href(href):
    href = "" if href is None else str(href).strip()
    if href.startswith(NOTE_PAGES):
        return href[:180]
    return ""


def stored_notification(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if text == "":
            return None
        return {"id": social.next_notification_id, "text": text[:180], "kind": "", "href": "", "read": True, "created_at": 0}
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if text == "":
        return None
    try:
        note_id = int(raw.get("id") or 0)
    except (TypeError, ValueError):
        note_id = 0
    if note_id <= 0:
        note_id = social.next_notification_id
    try:
        created = int(raw.get("created_at") or 0)
    except (TypeError, ValueError):
        created = 0
    return {
        "id": note_id,
        "text": text[:180],
        "kind": str(raw.get("kind") or "")[:24],
        "href": safe_note_href(raw.get("href")),
        "read": bool(raw.get("read")),
        "created_at": created if created > 0 else 0,
    }


def notification_rows(user):
    rows = []
    for item in user.notifications.items:
        note = stored_notification(item)
        if note is not None:
            rows.append(note)
    return rows


def blog_rows():
    rows = []
    for blog in social.blogs:
        comments = []
        for comment in blog.comments.traverse():
            comments.append({
                "id": comment.comment_id,
                "email": comment.author.email,
                "text": comment.text,
            })
        rows.append({
            "id": blog.blog_id,
            "email": blog.author.email,
            "title": blog.title,
            "body": blog.body,
            "cover": blog.cover,
            "created_at": blog.created_at,
            "updated_at": blog.updated_at,
            "likes": list(blog.likes),
            "comments": comments,
        })
    return rows


def save_data():
    with state_lock:
        text = write_data()
        db_pool.save_payload(text)
        with open(DATA_FILE, "w") as file:
            file.write(text)
        read_cache.clear()


def write_data():
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
            "notifications": notification_rows(user),
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
            "images": list(post.images),
            "poll": post.poll,
            "group_id": post.group_id,
            "likes": list(post.likes),
            "comments": comments,
        })

    groups = []
    for group in social.groups:
        members = []
        for email, role in group.members.items():
            members.append({"email": email, "role": role})
        groups.append({
            "id": group.group_id,
            "name": group.name,
            "description": group.description,
            "photo": group.photo,
            "owner_email": group.owner_email,
            "members": members,
            "pending": group.pending,
            "who_can_post": group.who_can_post,
            "who_can_comment": group.who_can_comment,
            "who_can_add": group.who_can_add,
            "who_can_edit": group.who_can_edit,
            "require_approval": group.require_approval,
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
        "groups": groups,
        "reset_tokens": saved_resets,
        "following": {email: list(others) for email, others in social.following.items()},
        "next_user_id": social.next_user_id,
        "next_post_id": social.next_post_id,
        "next_comment_id": social.next_comment_id,
        "next_group_id": social.next_group_id,
        "chats": chat_rows(),
        "next_chat_id": social.next_chat_id,
        "next_message_id": social.next_message_id,
        "webinars": webinar_rows(),
        "next_webinar_id": social.next_webinar_id,
        "next_webinar_message_id": social.next_webinar_message_id,
        "blogs": blog_rows(),
        "next_blog_id": social.next_blog_id,
        "next_notification_id": social.next_notification_id,
    }
    return json.dumps(data)


def empty_room():
    return {"people": {}, "speakers": set(), "pending": set(), "hands": [], "timer": None, "blocked": set()}


def clear_all_live_rooms():
    with state_lock:
        for room in live_rooms.values():
            timer = room.get("timer")
            if timer is not None:
                timer.cancel()
        live_rooms.clear()
        sid_rooms.clear()


def load_data():
    clear_all_live_rooms()
    db_pool.start()
    stored = db_pool.load_payload()
    data = None
    if stored:
        data = json.loads(stored)
    elif os.path.exists(DATA_FILE):
        with open(DATA_FILE) as file:
            data = json.load(file)
        db_pool.save_payload(json.dumps(data))
    if data is None:
        return

    social.users = []
    social.users_by_email = {}
    social.posts = []
    social.groups = []
    social.chats = []
    social.webinars = []
    social.blogs = []
    social.webinar_chat_times = {}
    social.next_blog_id = 1
    social.next_notification_id = 1
    social.following = {}
    social.next_group_id = 1
    social.next_chat_id = 1
    social.next_message_id = 1
    social.next_webinar_id = 1
    social.next_webinar_message_id = 1
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
        for saved in row.get("notifications", []):
            note = stored_notification(saved)
            if note is None:
                continue
            user.notifications.enqueue(note)
            if note["id"] >= social.next_notification_id:
                social.next_notification_id = note["id"] + 1
        social.users.append(user)
        social.users_by_email[user.email] = user
        social.friends.add_user(user.email)

    loaded_group_ids = set()
    for row in data.get("groups", []):
        try:
            group_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        group = Group(
            group_id,
            row.get("name", ""),
            row.get("description", ""),
            row.get("photo", ""),
            row.get("owner_email", ""),
        )
        group.who_can_post = row.get("who_can_post", "all_members")
        group.who_can_comment = row.get("who_can_comment", "all_members")
        group.who_can_add = row.get("who_can_add", "all_members")
        group.who_can_edit = row.get("who_can_edit", "admins_only")
        approval = row.get("require_approval", True)
        group.require_approval = approval if isinstance(approval, bool) else True
        for member in row.get("members", []):
            if not isinstance(member, dict):
                continue
            member_email = member.get("email", "")
            if member_email != "":
                group.members[member_email] = member.get("role", "member")
        pending = row.get("pending", [])
        group.pending = list(pending) if isinstance(pending, list) else []
        if not social.normalize_group(group):
            continue
        social.groups.append(group)
        loaded_group_ids.add(group.group_id)
        if group.group_id >= social.next_group_id:
            social.next_group_id = group.group_id + 1

    for row in data.get("posts", []):
        author = social.users_by_email.get(row["email"])
        if author is None:
            continue
        try:
            group_id = int(row.get("group_id", 0) or 0)
        except (TypeError, ValueError):
            group_id = 0
        if group_id != 0 and group_id not in loaded_group_ids:
            continue
        post = Post(
            row["id"],
            author,
            row["text"],
            row.get("image", ""),
            group_id,
            stored_image_names(row),
            stored_poll(row.get("poll")),
        )
        for email in row.get("likes", []):
            if email in social.users_by_email:
                post.likes.add(email)
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
    if "next_group_id" in data:
        try:
            saved_group_id = int(data["next_group_id"])
        except (TypeError, ValueError):
            saved_group_id = social.next_group_id
        if saved_group_id > social.next_group_id:
            social.next_group_id = saved_group_id

    for row in data.get("chats", []):
        try:
            chat_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        chat = Chat(chat_id, row.get("name", ""), row.get("photo", ""), row.get("owner_email", ""))
        for member in row.get("members", []):
            if not isinstance(member, dict):
                continue
            member_email = member.get("email", "")
            if member_email != "":
                chat.members[member_email] = member.get("last_read", 0)
        for saved in row.get("messages", []):
            if not isinstance(saved, dict):
                continue
            try:
                message_id = int(saved.get("id", 0))
            except (TypeError, ValueError):
                continue
            system = bool(saved.get("system", False))
            author = None
            if not system:
                author = social.users_by_email.get(saved.get("email", ""))
                if author is None:
                    continue
            try:
                created_at = float(saved.get("created_at", 0) or 0)
            except (TypeError, ValueError):
                created_at = 0
            reactions = saved.get("reactions", [])
            message = ChatMessage(
                message_id,
                author,
                saved.get("text", ""),
                "" if system else saved.get("image", ""),
                created_at,
                system,
                bool(saved.get("edited", False)),
                saved.get("reply_to", 0),
                reactions if isinstance(reactions, list) else [],
            )
            chat.messages.append(message)
            if message_id >= social.next_message_id:
                social.next_message_id = message_id + 1
        if not social.normalize_chat(chat):
            continue
        social.chats.append(chat)
        if chat.chat_id >= social.next_chat_id:
            social.next_chat_id = chat.chat_id + 1

    if "next_chat_id" in data:
        try:
            saved_chat_id = int(data["next_chat_id"])
        except (TypeError, ValueError):
            saved_chat_id = social.next_chat_id
        if saved_chat_id > social.next_chat_id:
            social.next_chat_id = saved_chat_id
    if "next_message_id" in data:
        try:
            saved_message_id = int(data["next_message_id"])
        except (TypeError, ValueError):
            saved_message_id = social.next_message_id
        if saved_message_id > social.next_message_id:
            social.next_message_id = saved_message_id

    ended_on_load = False
    for row in data.get("webinars", []):
        if not isinstance(row, dict):
            continue
        try:
            webinar_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        was_live = row.get("status") == "live"
        webinar = Webinar(
            webinar_id,
            row.get("title", ""),
            row.get("description", ""),
            row.get("cover", ""),
            row.get("host_email", ""),
            row.get("visibility", "public"),
            row.get("starts_at", 0),
        )
        webinar.status = row.get("status", "scheduled")
        webinar.created_at = row.get("created_at", 0)
        webinar.ended_at = row.get("ended_at", 0)
        invited = row.get("invited", [])
        webinar.invited = list(invited) if isinstance(invited, list) else []
        for saved in row.get("messages", []):
            if not isinstance(saved, dict):
                continue
            try:
                message_id = int(saved.get("id", 0))
            except (TypeError, ValueError):
                continue
            author = social.users_by_email.get(saved.get("email", ""))
            if author is None:
                continue
            webinar.messages.append(WebinarMessage(
                message_id,
                author,
                saved.get("text", ""),
                saved.get("created_at", 0),
            ))
        if not social.normalize_webinar(webinar):
            continue
        if was_live:
            ended_on_load = True
        social.webinars.append(webinar)
        if webinar.webinar_id >= social.next_webinar_id:
            social.next_webinar_id = webinar.webinar_id + 1

    if "next_webinar_id" in data:
        try:
            saved_webinar_id = int(data["next_webinar_id"])
        except (TypeError, ValueError):
            saved_webinar_id = social.next_webinar_id
        if saved_webinar_id > social.next_webinar_id:
            social.next_webinar_id = saved_webinar_id
    if "next_webinar_message_id" in data:
        try:
            saved_webinar_message_id = int(data["next_webinar_message_id"])
        except (TypeError, ValueError):
            saved_webinar_message_id = social.next_webinar_message_id
        if saved_webinar_message_id > social.next_webinar_message_id:
            social.next_webinar_message_id = saved_webinar_message_id
    for row in data.get("blogs", []):
        author = social.users_by_email.get(row.get("email", ""))
        if author is None:
            continue
        try:
            blog_id = int(row.get("id", 0))
        except (TypeError, ValueError):
            continue
        title = str(row.get("title", "") or "").strip()[:80]
        body = str(row.get("body", "") or "").strip()[:4000]
        if title == "" or body == "":
            continue
        try:
            created = int(row.get("created_at", 0) or 0)
        except (TypeError, ValueError):
            created = 0
        blog = Blog(blog_id, author, title, body, os.path.basename(str(row.get("cover", "") or "")), created)
        try:
            blog.updated_at = int(row.get("updated_at", created) or created)
        except (TypeError, ValueError):
            blog.updated_at = created
        for email in row.get("likes", []):
            if email in social.users_by_email:
                blog.likes.add(email)
        for saved in row.get("comments", []):
            comment_author = social.users_by_email.get(saved.get("email"))
            if comment_author is None:
                continue
            try:
                comment_id = int(saved.get("id", 0))
            except (TypeError, ValueError):
                continue
            text = str(saved.get("text", "") or "").strip()[:500]
            if text == "":
                continue
            comment = Comment(comment_id, comment_author, text)
            blog.comments.insert_at_end(comment)
            if comment.comment_id >= social.next_comment_id:
                social.next_comment_id = comment.comment_id + 1
        social.blogs.append(blog)
        if blog.blog_id >= social.next_blog_id:
            social.next_blog_id = blog.blog_id + 1

    if "next_blog_id" in data:
        try:
            saved_blog_id = int(data["next_blog_id"])
        except (TypeError, ValueError):
            saved_blog_id = social.next_blog_id
        if saved_blog_id > social.next_blog_id:
            social.next_blog_id = saved_blog_id
    if "next_notification_id" in data:
        try:
            saved_note_id = int(data["next_notification_id"])
        except (TypeError, ValueError):
            saved_note_id = social.next_notification_id
        if saved_note_id > social.next_notification_id:
            social.next_notification_id = saved_note_id

    social.reindex()

    if ended_on_load:
        save_data()


def read_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def user_from_token(token):
    if not token or token in revoked_tokens:
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


def unauthorized_payload():
    token = read_token()
    if not token:
        return {
            "ok": False,
            "message": "Please log in again.",
            "reason": "required",
        }
    if token in revoked_tokens:
        return {
            "ok": False,
            "message": "You were signed out. Please sign in again.",
            "reason": "logout",
        }
    try:
        jwt.decode(token, app.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return {
            "ok": False,
            "message": "Your session expired. Please sign in again.",
            "reason": "expired",
        }
    except jwt.InvalidTokenError:
        return {
            "ok": False,
            "message": "Please log in again.",
            "reason": "required",
        }
    return {
        "ok": False,
        "message": "Please log in again.",
        "reason": "required",
    }


def unauthorized_response():
    return jsonify(unauthorized_payload()), 401


def current_user():
    return user_from_token(read_token())


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
    path = os.path.join(UPLOAD_DIR, name)
    file_storage.save(path)
    resize_upload(path)
    return name


def discard_upload(filename):
    if filename == "":
        return
    safe = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def discard_uploads(filenames):
    for filename in filenames:
        discard_upload(filename)


def stored_upload(filename):
    safe = os.path.basename(filename)
    temp_path = os.path.join(UPLOAD_DIR, safe)
    if os.path.isfile(temp_path):
        return UPLOAD_DIR, safe
    legacy_path = os.path.join(LEGACY_UPLOAD_DIR, safe)
    if os.path.isfile(legacy_path):
        return LEGACY_UPLOAD_DIR, safe
    return None, safe


def stored_image_names(row):
    names = []
    saved = row.get("images")
    if isinstance(saved, list):
        for name in saved:
            name = os.path.basename(str(name or "").strip())
            if name and name not in names:
                names.append(name)
            if len(names) == 4:
                break
    if not names:
        single = os.path.basename(str(row.get("image", "") or "").strip())
        if single:
            names.append(single)
    return names


def stored_poll(raw):
    if not isinstance(raw, dict):
        return None
    options = raw.get("options")
    if not isinstance(options, list):
        return None
    clean = []
    for item in options:
        text = str(item or "").strip()
        if text:
            clean.append(text[:40])
        if len(clean) == 4:
            break
    if len(clean) < 2:
        return None
    votes = {}
    saved = raw.get("votes")
    if isinstance(saved, dict):
        for email, choice in saved.items():
            try:
                choice = int(choice)
            except (TypeError, ValueError):
                continue
            if 0 <= choice < len(clean):
                votes[str(email)] = choice
    return {"options": clean, "votes": votes}


def photo_path(filename):
    if filename == "":
        return ""
    return "/uploads/" + filename


def follower_count(email):
    return len(social.follower_index.get(email, ()))


def profile_payload(user, viewer):
    posts = []
    for post in reversed(social.posts):
        if post.author.email == user.email and post.group_id == 0:
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
        "images": [photo_path(name) for name in post.images],
        "poll": poll_public(post, viewer_email),
        "group_id": post.group_id,
        "like_count": len(post.likes),
        "liked": viewer_email in post.likes,
        "comments": comments,
    }


def poll_public(post, viewer_email):
    poll = post.poll
    if not isinstance(poll, dict):
        return None
    options = poll.get("options") or []
    votes = poll.get("votes") or {}
    counts = [0] * len(options)
    for choice in votes.values():
        if isinstance(choice, int) and 0 <= choice < len(counts):
            counts[choice] += 1
    total = sum(counts)
    mine = votes.get(viewer_email)
    rows = []
    for index, label in enumerate(options):
        percent = 0 if total == 0 else int(round(counts[index] * 100 / total))
        rows.append({"text": label, "count": counts[index], "percent": percent})
    return {
        "options": rows,
        "total": total,
        "choice": mine if isinstance(mine, int) else None,
    }


def parse_poll_field(raw):
    if raw is None or raw == "":
        return None, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, "A poll needs choices."
    return raw, None


def collect_post_uploads():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get("text", ""), [], data.get("poll"), None

    text = request.form.get("text", "")
    poll_raw = request.form.get("poll", "")
    names = []
    for storage in request.files.getlist("image"):
        if storage is None or not getattr(storage, "filename", ""):
            continue
        if len(names) >= 4:
            discard_uploads(names)
            return text, [], poll_raw, "A post can have 4 photos at most."
        name = save_upload(storage)
        if name is None:
            discard_uploads(names)
            return text, [], poll_raw, "Use a jpg, png, gif, or webp under 2 MB."
        if name == "":
            continue
        names.append(name)
    return text, names, poll_raw, None


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
    if username != "" and username.lower() in social.users_by_username:
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
    send_welcome(user.email, user.name)
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
        link = absolute_url("resetpassword.html?token=" + token)
        send_password_reset(user.email, user.name, link)
        if os.environ.get("SMTP_DEBUG", "").strip() == "1":
            print("", flush=True)
            print("Password reset link (valid for 30 minutes):", flush=True)
            print(link, flush=True)
            print("", flush=True)

    return jsonify({
        "ok": True,
        "message": "If that email has an account, we sent a reset link. Check your inbox (and spam).",
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

    email = record["email"]
    message = social.set_password(email, data.get("password", ""))
    if message is not None:
        return jsonify({"ok": False, "message": message}), 400

    del reset_tokens[token]
    save_data()
    user = social.users_by_email.get(email)
    if user is not None:
        send_password_changed(user.email, user.name)
    return jsonify({"ok": True, "message": "Password updated. You can sign in."})


@app.get("/me")
def me():
    user = current_user()
    if user is None:
        return unauthorized_response()

    return jsonify({
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "bio": user.bio,
        "photo": photo_path(user.photo),
        "cover": photo_path(user.cover),
        "following_count": len(social.following.get(user.email, [])),
        "followers_count": follower_count(user.email),
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

    cache_key = "posts:" + user.email
    cached = read_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    rows = []
    for post in reversed(social.posts):
        if post.group_id != 0:
            continue
        rows.append(post_public(post, user.email))
    read_cache.put(cache_key, rows)
    return jsonify(rows)


@app.post("/posts")
def add_post():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    text, names, poll_raw, upload_error = collect_post_uploads()
    if upload_error is not None:
        return jsonify({"ok": False, "message": upload_error}), 400

    parsed_poll, poll_error = parse_poll_field(poll_raw)
    if poll_error is not None:
        discard_uploads(names)
        return jsonify({"ok": False, "message": poll_error}), 400
    poll, poll_error = social.clean_poll(parsed_poll)
    if poll_error is not None:
        discard_uploads(names)
        return jsonify({"ok": False, "message": poll_error}), 400

    image_name = names[0] if names else ""
    message = social.post_error(user.email, text, image_name, 0, poll)
    if message is not None:
        discard_uploads(names)
        return jsonify({"ok": False, "message": message}), 400

    post = social.create_post(user.email, text, image_name, 0, names, poll)
    if post is None:
        discard_uploads(names)
        return jsonify({"ok": False, "message": "Write something, add a photo, or start a poll."}), 400

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


@app.post("/posts/<int:post_id>/vote")
def vote_on_post(post_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = social.vote_poll(user.email, post_id, data.get("choice"))
    if message is not None:
        status = 404 if message == "Post not found." else 400
        return jsonify({"ok": False, "message": message}), status

    save_data()
    return jsonify(post_public(social.find_post(post_id), user.email))


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

    post = social.find_post(post_id)
    image_names = list(post.images) if post is not None else []
    message = social.delete_post(user.email, post_id)
    if message is not None:
        status = 404 if message == "Post not found." else 400
        return jsonify({"ok": False, "message": message}), status

    discard_uploads(image_names)
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

    cache_key = "users:" + user.email
    cached = read_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    rows = []
    for other in social.users:
        if other.email == user.email:
            continue
        rows.append(user_public(other, user.email))
    read_cache.put(cache_key, rows)
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


def group_http(message):
    status = 404 if message in ("Group not found.", "User not found.", "Post not found.", "Comment not found.") else 400
    return jsonify({"ok": False, "message": message}), status


def person_from_body(data):
    return social.find_person(data.get("user", ""))


def member_public(user, role):
    return {
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "photo": photo_path(user.photo),
        "premium": bool(user.premium),
        "role": role,
    }


def group_payload(group, viewer, detailed=False):
    role = group.members.get(viewer.email, "")
    is_member = role != ""
    can_moderate = role in ("owner", "admin")
    payload = {
        "id": group.group_id,
        "name": group.name,
        "description": group.description,
        "photo": photo_path(group.photo),
        "member_count": len(group.members),
        "role": role,
        "is_member": is_member,
        "is_owner": role == "owner",
        "pending": viewer.email in group.pending,
        "can_post": social.group_allows(group, viewer.email, "who_can_post"),
        "can_comment": social.group_allows(group, viewer.email, "who_can_comment"),
        "can_add": social.group_allows(group, viewer.email, "who_can_add"),
        "can_edit": social.group_allows(group, viewer.email, "who_can_edit"),
        "can_moderate": can_moderate,
    }
    if not detailed or not is_member:
        return payload

    payload["settings"] = {
        "who_can_post": group.who_can_post,
        "who_can_comment": group.who_can_comment,
        "who_can_add": group.who_can_add,
        "who_can_edit": group.who_can_edit,
        "require_approval": group.require_approval,
    }
    members = []
    for email, member_role in group.members.items():
        person = social.users_by_email.get(email)
        if person is None:
            continue
        members.append(member_public(person, member_role))
    members.sort(key=lambda item: ({"owner": 0, "admin": 1, "member": 2}.get(item["role"], 9), item["name"].lower()))
    payload["members"] = members
    if can_moderate:
        requests = []
        for email in group.pending:
            person = social.users_by_email.get(email)
            if person is None:
                continue
            requests.append(member_public(person, "pending"))
        payload["requests"] = requests
    return payload


def read_group_photo():
    photo_name = save_upload(request.files.get("photo"))
    if photo_name is None:
        return "", "Use a jpg, png, gif, or webp under 2 MB."
    return photo_name, None


@app.post("/groups")
def create_group_route():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    photo_name, image_error = read_group_photo()
    if image_error is not None:
        return jsonify({"ok": False, "message": image_error}), 400

    group, message = social.create_group(
        user.email,
        request.form.get("name", ""),
        request.form.get("description", ""),
        photo_name,
    )
    if message is not None:
        discard_upload(photo_name)
        return group_http(message)

    save_data()
    return jsonify(group_payload(group, user, True))


@app.get("/groups")
def list_groups():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    query = request.args.get("q", "").strip().lower()
    mine = []
    discover = []
    for group in sorted(social.groups, key=lambda item: item.group_id, reverse=True):
        if query != "" and query not in group.name.lower():
            continue
        card = group_payload(group, user, False)
        if card["is_member"]:
            mine.append(card)
        else:
            discover.append(card)
    return jsonify({"mine": mine, "discover": discover})


@app.get("/groups/<int:group_id>")
def view_group(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    group = social.find_group(group_id)
    if group is None:
        return group_http("Group not found.")
    return jsonify(group_payload(group, user, True))


@app.post("/groups/<int:group_id>/update")
def update_group_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    group = social.find_group(group_id)
    old_photo = group.photo if group is not None else ""
    photo_name, image_error = read_group_photo()
    if image_error is not None:
        return jsonify({"ok": False, "message": image_error}), 400

    message = social.update_group(
        user.email,
        group_id,
        request.form.get("name", ""),
        request.form.get("description", ""),
        photo_name,
    )
    if message is not None:
        discard_upload(photo_name)
        return group_http(message)

    if photo_name != "" and old_photo != "" and old_photo != photo_name:
        discard_upload(old_photo)
    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/settings")
def update_group_settings_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = social.update_group_settings(
        user.email,
        group_id,
        data.get("who_can_post"),
        data.get("who_can_comment"),
        data.get("who_can_add"),
        data.get("who_can_edit"),
        data.get("require_approval"),
    )
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/join")
def join_group_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message = social.join_group(user.email, group_id)
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/leave")
def leave_group_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message, images = social.leave_group(user.email, group_id)
    if message is not None:
        return group_http(message)

    discard_uploads(images)
    save_data()
    deleted = social.find_group(group_id) is None
    return jsonify({"ok": True, "deleted": deleted})


@app.post("/groups/<int:group_id>/delete")
def delete_group_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message, images = social.delete_group(user.email, group_id)
    if message is not None:
        return group_http(message)

    discard_uploads(images)
    save_data()
    return jsonify({"ok": True, "deleted": True})


@app.post("/groups/<int:group_id>/transfer")
def transfer_group_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.transfer_group(user.email, group_id, other.email)
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/members")
def add_group_member_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.add_group_member(user.email, group_id, other.email)
    if message is not None:
        return group_http(message)

    save_data()
    saved = social.find_group(group_id)
    payload = group_payload(saved, user, True)
    if other.email in saved.members:
        payload["outcome"] = "added"
    elif other.email in saved.pending:
        payload["outcome"] = "requested"
    return jsonify(payload)


@app.post("/groups/<int:group_id>/members/remove")
def remove_group_member_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.remove_group_member(user.email, group_id, other.email)
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/members/role")
def set_group_role_route(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.set_group_role(user.email, group_id, other.email, data.get("role"))
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/requests/approve")
def approve_group_request(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.approve_join(user.email, group_id, other.email)
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.post("/groups/<int:group_id>/requests/reject")
def reject_group_request(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return group_http("User not found.")

    message = social.reject_join(user.email, group_id, other.email)
    if message is not None:
        return group_http(message)

    save_data()
    return jsonify(group_payload(social.find_group(group_id), user, True))


@app.get("/groups/<int:group_id>/posts")
def list_group_posts(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    group = social.find_group(group_id)
    if group is None:
        return group_http("Group not found.")
    if user.email not in group.members:
        return group_http("Only members can see posts in this group.")

    rows = []
    for post in reversed(social.posts_in_group(group_id)):
        rows.append(post_public(post, user.email))
    return jsonify(rows)


@app.post("/groups/<int:group_id>/posts")
def add_group_post(group_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    text, names, poll_raw, upload_error = collect_post_uploads()
    if upload_error is not None:
        return jsonify({"ok": False, "message": upload_error}), 400

    parsed_poll, poll_error = parse_poll_field(poll_raw)
    if poll_error is not None:
        discard_uploads(names)
        return group_http(poll_error)
    poll, poll_error = social.clean_poll(parsed_poll)
    if poll_error is not None:
        discard_uploads(names)
        return group_http(poll_error)

    image_name = names[0] if names else ""
    message = social.post_error(user.email, text, image_name, group_id, poll)
    if message is not None:
        discard_uploads(names)
        return group_http(message)

    post = social.create_post(user.email, text, image_name, group_id, names, poll)
    if post is None:
        discard_uploads(names)
        return jsonify({"ok": False, "message": "Write something, add a photo, or start a poll."}), 400

    save_data()
    return jsonify(post_public(post, user.email))


def chat_http(message):
    status = 404 if message in ("Chat not found.", "User not found.", "Message not found.") else 400
    return jsonify({"ok": False, "message": message}), status


def reactions_public(message, viewer_email):
    grouped = []
    index = {}
    for item in message.reactions or []:
        if not isinstance(item, dict):
            continue
        emoji = item.get("emoji", "")
        if emoji not in index:
            index[emoji] = {"emoji": emoji, "count": 0, "mine": False}
            grouped.append(index[emoji])
        index[emoji]["count"] = index[emoji]["count"] + 1
        if item.get("email") == viewer_email:
            index[emoji]["mine"] = True
    return grouped


def reply_public(message, chat, viewer_email):
    reply_to = getattr(message, "reply_to", 0) or 0
    if not reply_to:
        return None
    target = social.find_chat_message(chat, reply_to)
    if target is None:
        return {"id": reply_to, "removed": True, "system": False, "name": "", "text": "", "image": False}
    if target.system or target.author is None:
        return {
            "id": target.message_id,
            "removed": False,
            "system": True,
            "name": "",
            "text": target.text,
            "image": False,
        }
    mine = target.author.email == viewer_email
    return {
        "id": target.message_id,
        "removed": False,
        "system": False,
        "name": "You" if mine else target.author.name,
        "text": target.text,
        "image": target.image != "",
    }


def message_public(message, viewer_email, chat):
    system = bool(message.system) or message.author is None
    if system:
        return {
            "id": message.message_id,
            "text": message.text,
            "image": "",
            "created_at": message.created_at,
            "system": True,
            "edited": False,
            "mine": False,
            "seen": False,
            "reply": None,
            "reactions": [],
            "name": "",
            "email": "",
            "username": "",
            "photo": "",
            "premium": False,
        }
    author = message.author
    return {
        "id": message.message_id,
        "text": message.text,
        "image": photo_path(message.image),
        "created_at": message.created_at,
        "system": False,
        "edited": bool(message.edited),
        "mine": author.email == viewer_email,
        "seen": social.chat_seen(chat, message, viewer_email),
        "reply": reply_public(message, chat, viewer_email),
        "reactions": reactions_public(message, viewer_email),
        "name": author.name,
        "email": author.email,
        "username": author.username,
        "photo": photo_path(author.photo),
        "premium": bool(author.premium),
    }


def chat_preview(chat, viewer_email):
    if not chat.messages:
        return None
    last = chat.messages[-1]
    public = message_public(last, viewer_email, chat)
    if public["system"]:
        public["preview"] = public["text"]
    elif public["text"] == "" and public["image"] != "":
        public["preview"] = "Sent a photo"
    else:
        public["preview"] = public["text"]
    return public


def chat_payload(chat, viewer, detailed=False):
    role = "owner" if chat.owner_email == viewer.email else "member"
    payload = {
        "id": chat.chat_id,
        "name": chat.name,
        "photo": photo_path(chat.photo),
        "member_count": len(chat.members),
        "is_member": viewer.email in chat.members,
        "is_owner": chat.owner_email == viewer.email,
        "role": role if viewer.email in chat.members else "",
        "unread": social.chat_unread(chat, viewer.email) if viewer.email in chat.members else 0,
        "last_message": chat_preview(chat, viewer.email),
    }
    if not detailed or viewer.email not in chat.members:
        return payload
    members = []
    for email in chat.members:
        person = social.users_by_email.get(email)
        if person is None:
            continue
        members.append(member_public(person, "owner" if email == chat.owner_email else "member"))
    members.sort(key=lambda item: (0 if item["role"] == "owner" else 1, item["name"].lower()))
    payload["members"] = members
    return payload


def chat_people(raw):
    tokens = []
    for part in str(raw or "").replace(",", " ").split():
        if part not in tokens:
            tokens.append(part)
    emails = []
    for token in tokens:
        person = social.find_person(token)
        if person is None:
            return None, "Couldn't find " + token + "."
        if person.email not in emails:
            emails.append(person.email)
    return emails, None


@app.post("/chats")
def create_chat_route():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    photo_name, image_error = read_group_photo()
    if image_error is not None:
        return jsonify({"ok": False, "message": image_error}), 400

    emails, message = chat_people(request.form.get("members", ""))
    if message is not None:
        discard_upload(photo_name)
        return chat_http(message)

    chat, message = social.create_chat(user.email, request.form.get("name", ""), photo_name, emails)
    if message is not None:
        discard_upload(photo_name)
        return chat_http(message)

    save_data()
    return jsonify(chat_payload(chat, user, True))


@app.get("/chats")
def list_chats():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    rows = []
    for chat in social.chats:
        if user.email not in chat.members:
            continue
        rows.append(chat_payload(chat, user, False))
    rows.sort(key=lambda item: (
        0 if item["last_message"] is None else -item["last_message"]["created_at"],
        -item["id"],
    ))
    return jsonify(rows)


@app.get("/chats/<int:chat_id>")
def view_chat(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    chat = social.find_chat(chat_id)
    if chat is None:
        return chat_http("Chat not found.")
    if user.email not in chat.members:
        return chat_http("Only members can see this chat.")
    return jsonify(chat_payload(chat, user, True))


@app.get("/chats/<int:chat_id>/messages")
def list_chat_messages(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    chat = social.find_chat(chat_id)
    if chat is None:
        return chat_http("Chat not found.")
    if user.email not in chat.members:
        return chat_http("Only members can see this chat.")

    try:
        after = int(request.args.get("after", "0") or 0)
    except (TypeError, ValueError):
        after = 0
    rows = []
    thread = []
    for message in chat.messages:
        public = message_public(message, user.email, chat)
        thread.append(public)
        if message.message_id > after:
            rows.append(public)
    return jsonify({
        "chat": chat_payload(chat, user, True),
        "messages": rows,
        "thread": thread,
    })


@app.post("/chats/<int:chat_id>/messages")
def add_chat_message(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    image_name = ""
    if request.content_type and "multipart/form-data" in request.content_type:
        text = request.form.get("text", "")
        raw_reply = request.form.get("reply_to", 0)
        image_name = save_upload(request.files.get("image"))
        if image_name is None:
            return jsonify({"ok": False, "message": "Use a jpg, png, gif, or webp under 2 MB."}), 400
    else:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")
        raw_reply = data.get("reply_to", 0)

    message, error = social.send_chat_message(user.email, chat_id, text, image_name, raw_reply)
    if error is not None:
        discard_upload(image_name)
        return chat_http(error)

    save_data()
    chat = social.find_chat(chat_id)
    return jsonify(message_public(message, user.email, chat))


@app.post("/chats/<int:chat_id>/messages/<int:message_id>/edit")
def edit_chat_message_route(chat_id, message_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    text = data.get("text", request.form.get("text", ""))
    message, error = social.edit_chat_message(user.email, chat_id, message_id, text)
    if error is not None:
        return chat_http(error)
    save_data()
    chat = social.find_chat(chat_id)
    return jsonify(message_public(message, user.email, chat))


@app.post("/chats/<int:chat_id>/messages/<int:message_id>/delete")
def delete_chat_message_route(chat_id, message_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    image, error = social.delete_chat_message(user.email, chat_id, message_id)
    if error is not None:
        return chat_http(error)
    discard_upload(image)
    save_data()
    return jsonify({"ok": True})


@app.post("/chats/<int:chat_id>/messages/<int:message_id>/react")
def react_chat_message_route(chat_id, message_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    error = social.react_chat_message(user.email, chat_id, message_id, data.get("emoji", ""))
    if error is not None:
        return chat_http(error)
    save_data()
    chat = social.find_chat(chat_id)
    message = social.find_chat_message(chat, message_id)
    return jsonify(message_public(message, user.email, chat))


@app.post("/chats/<int:chat_id>/read")
def read_chat(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message = social.mark_chat_read(user.email, chat_id)
    if message is not None:
        return chat_http(message)
    save_data()
    return jsonify({"ok": True})


@app.post("/chats/<int:chat_id>/update")
def update_chat_route(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    chat = social.find_chat(chat_id)
    old_photo = chat.photo if chat is not None else ""
    photo_name, image_error = read_group_photo()
    if image_error is not None:
        return jsonify({"ok": False, "message": image_error}), 400

    message = social.update_chat(user.email, chat_id, request.form.get("name", ""), photo_name)
    if message is not None:
        discard_upload(photo_name)
        return chat_http(message)
    if photo_name != "" and old_photo != "" and old_photo != photo_name:
        discard_upload(old_photo)
    save_data()
    return jsonify(chat_payload(social.find_chat(chat_id), user, True))


@app.post("/chats/<int:chat_id>/members")
def add_chat_member_route(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return chat_http("User not found.")
    message = social.add_chat_member(user.email, chat_id, other.email)
    if message is not None:
        return chat_http(message)
    save_data()
    return jsonify(chat_payload(social.find_chat(chat_id), user, True))


@app.post("/chats/<int:chat_id>/members/remove")
def remove_chat_member_route(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return chat_http("User not found.")
    message = social.remove_chat_member(user.email, chat_id, other.email)
    if message is not None:
        return chat_http(message)
    save_data()
    return jsonify(chat_payload(social.find_chat(chat_id), user, True))


@app.post("/chats/<int:chat_id>/leave")
def leave_chat_route(chat_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    message, images = social.leave_chat(user.email, chat_id)
    if message is not None:
        return chat_http(message)
    discard_uploads(images)
    save_data()
    return jsonify({"ok": True, "deleted": social.find_chat(chat_id) is None})


def webinar_http(message):
    status = 404 if message in ("Webinar not found.", "User not found.") else 400
    return jsonify({"ok": False, "message": message}), status


def webinar_host_public(webinar):
    person = social.users_by_email.get(webinar.host_email)
    if person is None:
        return None
    return member_public(person, "host")


def webinar_card(webinar, viewer):
    room = live_rooms.get(webinar.webinar_id)
    count = len(room["people"]) if room is not None and webinar.status == "live" else 0
    return {
        "id": webinar.webinar_id,
        "title": webinar.title,
        "description": webinar.description,
        "cover": photo_path(webinar.cover),
        "visibility": webinar.visibility,
        "status": webinar.status,
        "starts_at": webinar.starts_at,
        "created_at": webinar.created_at,
        "ended_at": webinar.ended_at,
        "host": webinar_host_public(webinar),
        "is_host": viewer.email == webinar.host_email,
        "invited": viewer.email in webinar.invited,
        "listener_count": count,
    }


def webinar_message_public(message, viewer_email):
    author = message.author
    return {
        "id": message.message_id,
        "text": message.text,
        "created_at": message.created_at,
        "name": author.name,
        "email": author.email,
        "username": author.username,
        "photo": photo_path(author.photo),
        "premium": bool(author.premium),
        "mine": author.email == viewer_email,
    }


def ice_servers():
    servers = [{"urls": "stun:stun.l.google.com:19302"}]
    turn = os.environ.get("TURN_URL", "").strip()
    if turn != "":
        servers.append({
            "urls": turn,
            "username": os.environ.get("TURN_USERNAME", ""),
            "credential": os.environ.get("TURN_PASSWORD", ""),
        })
    return servers


@app.get("/webinars/ice")
def webinar_ice():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    return jsonify({"iceServers": ice_servers()})


@app.post("/webinars")
def create_webinar_route():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    photo_name, image_error = read_group_photo()
    if image_error is not None:
        return jsonify({"ok": False, "message": image_error}), 400

    emails, message = chat_people(request.form.get("invites", ""))
    if message is not None:
        discard_upload(photo_name)
        return webinar_http(message)

    webinar, message = social.create_webinar(
        user.email,
        request.form.get("title", ""),
        request.form.get("description", ""),
        photo_name,
        request.form.get("visibility", "public"),
        request.form.get("starts_at", 0),
        emails,
    )
    if message is not None:
        discard_upload(photo_name)
        return webinar_http(message)

    save_data()
    return jsonify(webinar_card(webinar, user))


@app.get("/webinars")
def list_webinars():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    live = []
    upcoming = []
    ended = []
    mine = []
    invited = []
    for webinar in social.webinars:
        card = webinar_card(webinar, user)
        if webinar.host_email == user.email:
            mine.append(card)
        if user.email in webinar.invited:
            invited.append(card)
        if webinar.visibility != "public":
            continue
        if webinar.status == "live":
            live.append(card)
        elif webinar.status == "ended":
            ended.append(card)
        else:
            upcoming.append(card)
    live.sort(key=lambda item: -item["id"])
    upcoming.sort(key=lambda item: (item["starts_at"] or 0, item["id"]))
    ended.sort(key=lambda item: (-(item["ended_at"] or 0), -item["id"]))
    mine.sort(key=lambda item: -item["id"])
    invited.sort(key=lambda item: -item["id"])
    return jsonify({
        "live": live,
        "upcoming": upcoming,
        "ended": ended,
        "mine": mine,
        "invited": invited,
    })


@app.get("/webinars/<int:webinar_id>")
def view_webinar(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    webinar = social.find_webinar(webinar_id)
    if webinar is None:
        return webinar_http("Webinar not found.")
    return jsonify(webinar_card(webinar, user))


@app.post("/webinars/<int:webinar_id>/update")
def update_webinar_route(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    webinar = social.find_webinar(webinar_id)
    old_cover = webinar.cover if webinar is not None else ""
    if request.content_type and "multipart/form-data" in request.content_type:
        photo_name, image_error = read_group_photo()
        if image_error is not None:
            return jsonify({"ok": False, "message": image_error}), 400
        title = request.form.get("title", "")
        description = request.form.get("description", "")
        visibility = request.form.get("visibility", "public")
        starts_at = request.form.get("starts_at", 0)
    else:
        photo_name = ""
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
        description = data.get("description", "")
        visibility = data.get("visibility", "public")
        starts_at = data.get("starts_at", 0)

    message = social.update_webinar(user.email, webinar_id, title, description, visibility, starts_at, photo_name)
    if message is not None:
        discard_upload(photo_name)
        return webinar_http(message)
    if photo_name != "" and old_cover != "" and old_cover != photo_name:
        discard_upload(old_cover)
    save_data()
    return jsonify(webinar_card(social.find_webinar(webinar_id), user))


@app.post("/webinars/<int:webinar_id>/start")
def start_webinar_route(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    with state_lock:
        message = social.start_webinar(user.email, webinar_id)
        if message is not None:
            return webinar_http(message)
        clear_live_room(webinar_id)
        live_rooms[webinar_id] = empty_room()
        write_data()
        payload = webinar_card(social.find_webinar(webinar_id), user)
    return jsonify(payload)


@app.post("/webinars/<int:webinar_id>/end")
def end_webinar_route(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    with state_lock:
        webinar = social.find_webinar(webinar_id)
        if webinar is None:
            return webinar_http("Webinar not found.")
        message = social.end_webinar(user.email, webinar_id)
        if message is not None:
            return webinar_http(message)
        clear_live_room(webinar_id)
        write_data()
        socketio.emit("ended", {"webinar_id": webinar_id}, room=live_room_name(webinar_id))
        payload = webinar_card(social.find_webinar(webinar_id), user)
    return jsonify(payload)


@app.post("/webinars/<int:webinar_id>/invite")
def invite_webinar_route(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return webinar_http("User not found.")
    message = social.invite_webinar(user.email, webinar_id, other.email)
    if message is not None:
        return webinar_http(message)
    save_data()
    return jsonify(webinar_card(social.find_webinar(webinar_id), user))


@app.post("/webinars/<int:webinar_id>/host")
def pass_webinar_host_route(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    other = person_from_body(data)
    if other is None:
        return webinar_http("User not found.")
    with state_lock:
        webinar = social.find_webinar(webinar_id)
        room = live_rooms.get(webinar_id)
        if webinar is None:
            return webinar_http("Webinar not found.")
        if room is None or other.email not in room["people"]:
            return webinar_http("That person is not in this room.")
        message = apply_pass_host(webinar, room, user.email, other.email)
        if message is not None:
            return webinar_http(message)
        payload = webinar_card(webinar, user)
    return jsonify(payload)


@app.get("/webinars/<int:webinar_id>/messages")
def list_webinar_messages(webinar_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401

    webinar = social.find_webinar(webinar_id)
    if webinar is None:
        return webinar_http("Webinar not found.")
    rows = []
    for message in webinar.messages[-100:]:
        rows.append(webinar_message_public(message, user.email))
    return jsonify({"messages": rows})


def live_room_name(webinar_id):
    return "webinar-" + str(webinar_id)


def cancel_host_grace(room):
    timer = room.get("timer")
    if timer is not None:
        timer.cancel()
        room["timer"] = None


def clear_live_room(webinar_id):
    room = live_rooms.pop(webinar_id, None)
    if room is None:
        return
    cancel_host_grace(room)
    for person in room["people"].values():
        sid_rooms.pop(person.get("sid"), None)


def remove_live_person(room, email):
    person = room["people"].pop(email, None)
    room["speakers"].discard(email)
    room["pending"].discard(email)
    if email in room["hands"]:
        room["hands"] = [item for item in room["hands"] if item != email]
    if person is not None:
        sid_rooms.pop(person.get("sid"), None)
    return person


def person_live_role(webinar, room, email):
    if email == webinar.host_email:
        return "host"
    if email in room["speakers"]:
        return "speaker"
    return "listener"


def can_publish_live(webinar, room, email):
    if email in room["pending"]:
        return False
    return email in room["people"]


def room_people(webinar, room):
    people = []
    for email in room["people"]:
        user = social.users_by_email.get(email)
        if user is None:
            continue
        person = room["people"][email]
        row = member_public(user, person_live_role(webinar, room, email))
        row["audio"] = bool(person.get("audio"))
        row["video"] = bool(person.get("video"))
        row["screen"] = bool(person.get("screen"))
        row["hand"] = email in room["hands"]
        row["pending"] = email in room["pending"]
        people.append(row)
    people.sort(key=lambda item: ({"host": 0, "speaker": 1, "listener": 2}.get(item["role"], 9), item["name"].lower()))
    return people


def emit_room_state(webinar):
    room = live_rooms.get(webinar.webinar_id)
    if room is None:
        return
    people = room_people(webinar, room)
    speakers = []
    for email in room["speakers"]:
        if email in room["people"]:
            speakers.append(email)
    hands = []
    for email in room["hands"]:
        if email in room["people"]:
            hands.append(email)
    host_online = webinar.host_email in room["people"]
    for email, person in room["people"].items():
        socketio.emit("room", {
            "webinar_id": webinar.webinar_id,
            "status": webinar.status,
            "host_email": webinar.host_email,
            "you": person_live_role(webinar, room, email),
            "you_pending": email in room["pending"],
            "host_online": host_online,
            "count": len(people),
            "people": people,
            "hands": hands,
            "speakers": speakers,
        }, to=person["sid"])


def emit_hands(webinar):
    room = live_rooms.get(webinar.webinar_id)
    if room is None:
        return
    hands = [email for email in room["hands"] if email in room["people"]]
    socketio.emit("hands", {"webinar_id": webinar.webinar_id, "hands": hands}, room=live_room_name(webinar.webinar_id))


def arm_host_grace(webinar_id):
    room = live_rooms.get(webinar_id)
    if room is None:
        return
    cancel_host_grace(room)

    def fire(saved_id=webinar_id):
        finish_host_grace(saved_id)

    timer = threading.Timer(HOST_GRACE_SECONDS, fire)
    timer.daemon = True
    room["timer"] = timer
    timer.start()


def finish_host_grace(webinar_id):
    with state_lock:
        room = live_rooms.get(webinar_id)
        webinar = social.find_webinar(webinar_id)
        if room is None or webinar is None or webinar.status != "live":
            return
        if webinar.host_email in room["people"]:
            return
        message = social.end_webinar(webinar.host_email, webinar_id)
        if message is not None:
            return
        clear_live_room(webinar_id)
        write_data()
        socketio.emit("ended", {"webinar_id": webinar_id}, room=live_room_name(webinar_id))


def apply_pass_host(webinar, room, actor_email, target_email):
    if target_email not in room["people"]:
        return "That person is not in this room."
    was_speaker = target_email in room["speakers"]
    message = social.pass_webinar_host(actor_email, webinar.webinar_id, target_email)
    if message is not None:
        return message
    room["speakers"].add(actor_email)
    room["speakers"].discard(target_email)
    room["pending"].discard(target_email)
    room["hands"] = [item for item in room["hands"] if item != target_email]
    if not was_speaker:
        room["pending"].add(target_email)
        socketio.emit("admitted", {"webinar_id": webinar.webinar_id}, to=room["people"][target_email]["sid"])
    write_data()
    emit_room_state(webinar)
    emit_hands(webinar)
    return None


def require_live_member():
    email = socket_users.get(request.sid)
    located = sid_rooms.get(request.sid)
    if email is None or located is None:
        emit("notice", {"message": "Join the room first."})
        return None
    webinar_id, member_email = located
    if member_email != email:
        emit("notice", {"message": "Join the room first."})
        return None
    webinar = social.find_webinar(webinar_id)
    room = live_rooms.get(webinar_id)
    if webinar is None or room is None or webinar.status != "live" or email not in room["people"]:
        emit("notice", {"message": "This webinar is not live."})
        return None
    if room["people"][email].get("sid") != request.sid:
        emit("notice", {"message": "You joined in another window."})
        return None
    return webinar, room, email


def end_live_room(webinar, email):
    message = social.end_webinar(email, webinar.webinar_id)
    if message is not None:
        emit("notice", {"message": message})
        return False
    webinar_id = webinar.webinar_id
    clear_live_room(webinar_id)
    write_data()
    socketio.emit("ended", {"webinar_id": webinar_id}, room=live_room_name(webinar_id))
    return True


@socketio.on("connect")
def socket_connect(auth=None):
    token = ""
    if isinstance(auth, dict):
        token = str(auth.get("token") or "")
    user = user_from_token(token)
    if user is None:
        return False
    with state_lock:
        socket_users[request.sid] = user.email
    return True


@socketio.on("disconnect")
def socket_disconnect():
    sid = request.sid
    with state_lock:
        socket_users.pop(sid, None)
        located = sid_rooms.pop(sid, None)
        if located is None:
            return
        webinar_id, email = located
        room = live_rooms.get(webinar_id)
        webinar = social.find_webinar(webinar_id)
        if room is None or webinar is None:
            return
        person = room["people"].get(email)
        if person is None or person.get("sid") != sid:
            return
        remove_live_person(room, email)
        if webinar.status != "live":
            return
        if email == webinar.host_email:
            arm_host_grace(webinar_id)
        emit_room_state(webinar)
        emit_hands(webinar)


@socketio.on("join")
def socket_join(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        email = socket_users.get(request.sid)
        if email is None:
            emit("notice", {"message": "Please log in again."})
            return
        try:
            webinar_id = int(data.get("webinar_id"))
        except (TypeError, ValueError):
            emit("notice", {"message": "Webinar not found."})
            return
        webinar = social.find_webinar(webinar_id)
        if webinar is None:
            emit("notice", {"message": "Webinar not found."})
            return
        if webinar.status == "ended":
            emit("notice", {"message": "This webinar has ended."})
            return
        if webinar.status != "live":
            emit("notice", {"message": "This webinar has not started."})
            return

        previous = sid_rooms.get(request.sid)
        if previous is not None and previous[0] != webinar_id:
            previous_room = live_rooms.get(previous[0])
            previous_webinar = social.find_webinar(previous[0])
            if previous_room is not None:
                person = previous_room["people"].get(previous[1])
                if person is not None and person.get("sid") == request.sid:
                    remove_live_person(previous_room, previous[1])
                    if previous_webinar is not None and previous[1] == previous_webinar.host_email and previous_webinar.status == "live":
                        arm_host_grace(previous[0])
                    elif previous_webinar is not None:
                        emit_room_state(previous_webinar)
            leave_room(live_room_name(previous[0]))

        room = live_rooms.get(webinar_id)
        if room is None:
            room = empty_room()
            live_rooms[webinar_id] = room
        if email in room.get("blocked", ()) and email != webinar.host_email:
            emit("notice", {"message": "The host removed you."})
            return
        current = room["people"].get(email)
        if current is not None and current.get("sid") != request.sid:
            old_sid = current["sid"]
            sid_rooms.pop(old_sid, None)
            leave_room(live_room_name(webinar_id), sid=old_sid)
            socketio.emit("replaced", {"message": "You joined in another window."}, to=old_sid)
            disconnect(old_sid)
        if email not in room["people"] and len(room["people"]) >= WEBINAR_ROOM_CAP:
            emit("notice", {"message": "This room is full."})
            return

        media = current if current is not None else {}
        room["people"][email] = {
            "sid": request.sid,
            "audio": bool(media.get("audio")),
            "video": bool(media.get("video")),
            "screen": bool(media.get("screen")),
        }
        sid_rooms[request.sid] = (webinar_id, email)
        if email == webinar.host_email:
            cancel_host_grace(room)
            room["pending"].discard(email)
            room["speakers"].discard(email)
        join_room(live_room_name(webinar_id))
        emit_room_state(webinar)
        emit_hands(webinar)


@socketio.on("leave")
def socket_leave(data=None):
    with state_lock:
        located = sid_rooms.get(request.sid)
        if located is None:
            return
        webinar_id, email = located
        webinar = social.find_webinar(webinar_id)
        if webinar is not None and email == webinar.host_email and webinar.status == "live":
            end_live_room(webinar, email)
            return
        room = live_rooms.get(webinar_id)
        if room is not None:
            person = room["people"].get(email)
            if person is not None and person.get("sid") == request.sid:
                remove_live_person(room, email)
        sid_rooms.pop(request.sid, None)
        leave_room(live_room_name(webinar_id))
        if webinar is not None:
            emit_room_state(webinar)
            emit_hands(webinar)


@socketio.on("signal")
def socket_signal(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        kind = data.get("kind")
        if kind not in ("offer", "answer", "ice"):
            emit("notice", {"message": "That signal is not valid."})
            return
        target = data.get("to")
        if not isinstance(target, str) or target == email or target not in room["people"]:
            emit("notice", {"message": "That person is not in this room."})
            return
        payload = data.get("payload")
        if payload is None:
            emit("notice", {"message": "That signal is not valid."})
            return
        try:
            encoded = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError):
            emit("notice", {"message": "That signal is not valid."})
            return
        if len(encoded) > SIGNAL_BYTES:
            emit("notice", {"message": "That signal is too large."})
            return
        if kind == "offer" and not can_publish_live(webinar, room, email):
            emit("notice", {"message": "Only presenters can share audio or video."})
            return
        socketio.emit("signal", {
            "from": email,
            "kind": kind,
            "payload": payload,
        }, to=room["people"][target]["sid"])


@socketio.on("media")
def socket_media(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        person = room["people"][email]
        person["audio"] = bool(data.get("audio"))
        person["video"] = bool(data.get("video"))
        person["screen"] = bool(data.get("screen"))
        socketio.emit("media", {
            "email": email,
            "audio": person["audio"],
            "video": person["video"],
            "screen": person["screen"],
        }, room=live_room_name(webinar.webinar_id))


@socketio.on("raise-hand")
def socket_raise(data=None):
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email == webinar.host_email or email in room["speakers"]:
            emit("notice", {"message": "You are already presenting."})
            return
        if email in room["pending"]:
            emit("notice", {"message": "Waiting for your microphone."})
            return
        if email not in room["hands"]:
            room["hands"].append(email)
        emit_hands(webinar)
        emit_room_state(webinar)


@socketio.on("lower-hand")
def socket_lower(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        target = data.get("user") or email
        if not isinstance(target, str) or target == "":
            target = email
        if target != email and email != webinar.host_email:
            emit("notice", {"message": "Only the host can dismiss a hand."})
            return
        room["hands"] = [item for item in room["hands"] if item != target]
        emit_hands(webinar)
        emit_room_state(webinar)


@socketio.on("admit")
def socket_admit(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email != webinar.host_email:
            emit("notice", {"message": "Only the host can allow someone to speak."})
            return
        target = data.get("user")
        if not isinstance(target, str) or target not in room["people"]:
            emit("notice", {"message": "That person is not in this room."})
            return
        if target == webinar.host_email or target in room["speakers"]:
            emit("notice", {"message": "That person is already presenting."})
            return
        if target in room["pending"]:
            emit("notice", {"message": "Waiting for their microphone."})
            return
        room["hands"] = [item for item in room["hands"] if item != target]
        room["pending"].add(target)
        socketio.emit("admitted", {"webinar_id": webinar.webinar_id}, to=room["people"][target]["sid"])
        emit_hands(webinar)
        emit_room_state(webinar)


@socketio.on("publish-ready")
def socket_publish_ready(data=None):
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email not in room["pending"]:
            emit("notice", {"message": "You have not been asked to speak."})
            return
        room["pending"].discard(email)
        if email != webinar.host_email:
            room["speakers"].add(email)
        emit_room_state(webinar)


@socketio.on("publish-failed")
def socket_publish_failed(data=None):
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email not in room["pending"]:
            return
        room["pending"].discard(email)
        if email != webinar.host_email:
            host = room["people"].get(webinar.host_email)
            user = social.users_by_email.get(email)
            if host is not None:
                socketio.emit("publish-failed", {
                    "email": email,
                    "name": user.name if user is not None else "Someone",
                    "message": "Couldn't turn on the microphone.",
                }, to=host["sid"])
        emit_room_state(webinar)


@socketio.on("revoke")
def socket_revoke(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email != webinar.host_email:
            emit("notice", {"message": "Only the host can stop a presenter."})
            return
        target = data.get("user")
        if not isinstance(target, str) or target not in room["people"]:
            emit("notice", {"message": "That person is not in this room."})
            return
        if target == webinar.host_email:
            emit("notice", {"message": "You are the host."})
            return
        if target not in room["speakers"] and target not in room["pending"]:
            emit("notice", {"message": "That person is not presenting."})
            return
        room["speakers"].discard(target)
        room["pending"].discard(target)
        socketio.emit("revoked", {"email": target}, room=live_room_name(webinar.webinar_id))
        emit_room_state(webinar)


@socketio.on("kick")
def socket_kick(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        if email != webinar.host_email:
            emit("notice", {"message": "Only the host can remove people."})
            return
        target = data.get("user")
        if target == email:
            emit("notice", {"message": "Leave the room instead of removing yourself."})
            return
        if not isinstance(target, str) or target not in room["people"]:
            emit("notice", {"message": "That person is not in this room."})
            return
        room.setdefault("blocked", set()).add(target)
        person = remove_live_person(room, target)
        if person is not None:
            socketio.emit("kicked", {"message": "The host removed you."}, to=person["sid"])
            leave_room(live_room_name(webinar.webinar_id), sid=person["sid"])
            disconnect(person["sid"])
        emit_room_state(webinar)
        emit_hands(webinar)


@socketio.on("pass-host")
def socket_pass_host(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        target = data.get("user")
        if not isinstance(target, str):
            emit("notice", {"message": "That person is not in this room."})
            return
        message = apply_pass_host(webinar, room, email, target)
        if message is not None:
            emit("notice", {"message": message})


@socketio.on("end")
def socket_end(data=None):
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        end_live_room(webinar, email)


@socketio.on("chat")
def socket_chat(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        message, error = social.send_webinar_message(email, webinar.webinar_id, data.get("text", ""))
        if error is not None:
            emit("notice", {"message": error})
            return
        write_data()
        socketio.emit("chat", webinar_message_public(message, ""), room=live_room_name(webinar.webinar_id))


@socketio.on("react")
def socket_react(data=None):
    data = data if isinstance(data, dict) else {}
    with state_lock:
        located = require_live_member()
        if located is None:
            return
        webinar, room, email = located
        emoji = "" if data.get("emoji") is None else str(data.get("emoji")).strip()
        if emoji not in CHAT_REACTIONS:
            emit("notice", {"message": "Choose a reaction from the list."})
            return
        user = social.users_by_email.get(email)
        socketio.emit("react", {
            "name": user.name if user is not None else "Someone",
            "emoji": emoji,
        }, room=live_room_name(webinar.webinar_id))


def blog_public(blog, viewer_email, detail=False):
    comments = blog.comments.traverse()
    excerpt = " ".join(blog.body.split())
    if len(excerpt) > 160:
        excerpt = excerpt[:157].rstrip() + "..."
    row = {
        "id": blog.blog_id,
        "title": blog.title,
        "excerpt": excerpt,
        "cover": photo_path(blog.cover),
        "created_at": blog.created_at,
        "updated_at": blog.updated_at,
        "name": blog.author.name,
        "email": blog.author.email,
        "username": blog.author.username,
        "photo": photo_path(blog.author.photo),
        "premium": bool(blog.author.premium),
        "like_count": len(blog.likes),
        "liked": viewer_email in blog.likes,
        "comment_count": len(comments),
    }
    if detail:
        saved = []
        for comment in comments:
            saved.append(comment_public(comment))
        row["body"] = blog.body
        row["comments"] = saved
    return row


def notification_public(item):
    note = stored_notification(item)
    if note is None:
        return None
    return note


@app.get("/notifications")
def list_notifications():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    rows = []
    for item in reversed(user.notifications.items):
        note = notification_public(item)
        if note is not None:
            rows.append(note)
    return jsonify(rows)


@app.get("/notifications/unread")
def unread_notifications():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    return jsonify({"ok": True, "unread": social.unread_count(user.email)})


@app.post("/notifications/read")
def read_notifications():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    data = request.get_json(silent=True) or {}
    note_id = data.get("id")
    if note_id in ("", None):
        note_id = None
    message = social.mark_notifications(user.email, note_id)
    if message is not None:
        status = 404 if message == "Notification not found." else 400
        return jsonify({"ok": False, "message": message}), status
    save_data()
    return jsonify({"ok": True, "unread": social.unread_count(user.email)})


@app.get("/blogs")
def list_blogs():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    rows = []
    for blog in reversed(social.blogs):
        rows.append(blog_public(blog, user.email))
    return jsonify(rows)


@app.post("/blogs")
def add_blog():
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    cover = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
        body = data.get("body", "")
    else:
        title = request.form.get("title", "")
        body = request.form.get("body", "")
        cover = save_upload(request.files.get("cover"))
        if cover is None:
            return jsonify({"ok": False, "message": "Use a jpg, png, gif, or webp under 2 MB."}), 400
    blog, message = social.create_blog(user.email, title, body, cover)
    if message is not None:
        discard_upload(cover)
        return jsonify({"ok": False, "message": message}), 400
    save_data()
    return jsonify(blog_public(blog, user.email, True))


@app.get("/blogs/<int:blog_id>")
def show_blog(blog_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    blog = social.find_blog(blog_id)
    if blog is None:
        return jsonify({"ok": False, "message": "Blog not found."}), 404
    return jsonify(blog_public(blog, user.email, True))


@app.post("/blogs/<int:blog_id>/edit")
def edit_blog(blog_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    cover = None
    uploaded = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        title = data.get("title", "")
        body = data.get("body", "")
    else:
        title = request.form.get("title", "")
        body = request.form.get("body", "")
        if request.form.get("remove_cover") == "1":
            cover = ""
        uploaded = save_upload(request.files.get("cover"))
        if uploaded is None:
            return jsonify({"ok": False, "message": "Use a jpg, png, gif, or webp under 2 MB."}), 400
        if uploaded:
            cover = uploaded
    message, old_cover = social.update_blog(user.email, blog_id, title, body, cover)
    if message is not None:
        discard_upload(uploaded)
        status = 404 if message == "Blog not found." else 400
        return jsonify({"ok": False, "message": message}), status
    if old_cover:
        discard_upload(old_cover)
    save_data()
    return jsonify(blog_public(social.find_blog(blog_id), user.email, True))


@app.post("/blogs/<int:blog_id>/delete")
def remove_blog(blog_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    message, cover = social.delete_blog(user.email, blog_id)
    if message is not None:
        status = 404 if message == "Blog not found." else 400
        return jsonify({"ok": False, "message": message}), status
    discard_upload(cover)
    save_data()
    return jsonify({"ok": True, "id": blog_id})


@app.post("/blogs/<int:blog_id>/like")
def like_blog(blog_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    message = social.like_blog(user.email, blog_id)
    if message is not None:
        status = 404 if message == "Blog not found." else 400
        return jsonify({"ok": False, "message": message}), status
    save_data()
    return jsonify(blog_public(social.find_blog(blog_id), user.email, True))


@app.post("/blogs/<int:blog_id>/comments")
def comment_blog(blog_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    data = request.get_json(silent=True) or {}
    message = social.add_blog_comment(user.email, blog_id, data.get("text", ""))
    if message is not None:
        status = 404 if message == "Blog not found." else 400
        return jsonify({"ok": False, "message": message}), status
    save_data()
    return jsonify(blog_public(social.find_blog(blog_id), user.email, True))


@app.post("/blogs/<int:blog_id>/comments/<int:comment_id>/delete")
def remove_blog_comment(blog_id, comment_id):
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    message = social.delete_blog_comment(user.email, blog_id, comment_id)
    if message is not None:
        status = 404 if message == "Blog not found." or message == "Comment not found." else 400
        return jsonify({"ok": False, "message": message}), status
    save_data()
    return jsonify(blog_public(social.find_blog(blog_id), user.email, True))


@app.get("/uploads/<filename>")
def uploaded_file(filename):
    folder, safe = stored_upload(filename)
    if folder is None:
        return jsonify({"ok": False, "message": "Not found."}), 404
    return send_from_directory(folder, safe)


@app.get("/")
def home_page():
    return send_from_directory(FRONTEND, "homepage.html")


@app.errorhandler(404)
@app.errorhandler(405)
def api_http_error(error):
    path = request.path or ""
    api = path.startswith((
        "/chats", "/groups", "/posts", "/users", "/me", "/follow", "/webinars",
        "/unfollow", "/login", "/signup", "/logout", "/uploads",
        "/notifications", "/blogs", "/premium", "/settings",
    ))
    content_type = request.headers.get("Content-Type", "")
    if api or "application/json" in content_type:
        if error.code == 405:
            message = "That action is not available."
        else:
            message = "Not found."
        return jsonify({"ok": False, "message": message}), error.code
    return error.get_response()


@app.get("/<path:name>")
def frontend_file(name):
    folder = FRONTEND
    target = os.path.abspath(os.path.join(folder, name))
    if not target.startswith(folder + os.sep) or not os.path.isfile(target):
        return jsonify({"ok": False, "message": "Not found."}), 404
    return send_from_directory(folder, name)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5000, debug=True, allow_unsafe_werkzeug=True)
