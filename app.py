from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from uuid import uuid4

import os

from flask import (
    Flask,
    Response,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mini-telegram-secret-key-2024")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///telegram.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SITE_URL"] = os.environ.get("SITE_URL", "https://uzgram.pythonanywhere.com").rstrip("/")
app.config["GOOGLE_SITE_VERIFICATION"] = os.environ.get(
    "GOOGLE_SITE_VERIFICATION",
    "googleef6572d0f05659ed",
).strip()
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

SITE_OWNER_NAME = "Asilbek Mirolimov"
SITE_NAME = "Uzgram Mini Chat"
SITE_TAGLINE = "Python, Flask va Socket.IO asosidagi real-time chat loyihasi"
GOOGLE_VERIFICATION_FILENAME = "googleef6572d0f05659ed.html"
DEFAULT_SITE_DESCRIPTION = (
    "Uzgram Mini Chat - Asilbek Mirolimov tomonidan Flask, SQLAlchemy va Socket.IO bilan "
    "yaratilgan zamonaviy real-time chat web ilovasi."
)

PRIMARY_SEO_KEYWORDS = [
    "Asilbek Mirolimov",
    "Asilbek Mirolimov project",
    "Asilbek Mirolimov flask project",
    "Asilbek Mirolimov python project",
    "uzgram",
    "uzgram chat",
    "uzgram mini chat",
    "Mini Chat",
    "mini telegram",
    "telegram clone flask",
    "instagram chat clone",
    "chat app uzbekistan",
    "uzbek chat app",
    "online chat uzbekistan",
    "messenger app uzbekistan",
    "real-time chat uzbekistan",
    "Python chat app",
    "python flask chat app",
    "online chat python flask",
    "Flask chat",
    "flask realtime app",
    "flask websocket chat",
    "Socket.IO chat",
    "socket io flask project",
    "SQLAlchemy loyiha",
    "real-time chat",
    "real-time messaging app",
    "web chat platform",
    "live chat web app",
    "web dasturlash",
    "python web development",
    "flask web development",
    "chat platforma",
    "Python web loyiha",
    "python anywhere flask app",
    "uzbek developer project",
    "uzbekiston chat sayti",
    "online messaging platform",
    "simple chat system flask",
    "google searchable flask app",
]

HOME_KEYWORDS = PRIMARY_SEO_KEYWORDS
LOGIN_KEYWORDS = [
    "uzgram login",
    "mini chat login",
    "chat account login",
    "flask chat sign in",
]
REGISTER_KEYWORDS = [
    "uzgram register",
    "mini chat register",
    "chat account create",
    "flask chat sign up",
]
CHAT_KEYWORDS = [
    "uzgram chat panel",
    "mini chat dashboard",
    "real time chat panel",
    "online messaging dashboard",
]

NOINDEX_PATH_PREFIXES = (
    "/login",
    "/register",
    "/chat",
    "/logout",
    "/get_messages",
    "/get_group_messages",
    "/create_group",
    "/update_avatar",
    "/api/",
)
PRIVATE_PATH_PREFIXES = (
    "/chat",
    "/logout",
    "/get_messages",
    "/get_group_messages",
    "/create_group",
    "/update_avatar",
    "/api/",
)

DEFAULT_AVATAR_FILENAME = "default.svg"
DEFAULT_GROUP_AVATAR_FILENAME = "group.svg"
MESSAGE_FETCH_LIMIT = 150
MAX_GROUP_MEMBERS = 20

ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a", "aac", "webm"}
ALLOWED_ATTACHMENT_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_AUDIO_EXTENSIONS

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
login_manager = LoginManager(app)
login_manager.login_view = "login"

STATIC_DIR = Path(app.static_folder)
AVATAR_DIR = STATIC_DIR / "avatars"
MESSAGE_UPLOAD_DIR = STATIC_DIR / "uploads" / "messages"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
MESSAGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.utcnow()


def as_utc_iso(dt):
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


def get_site_base_url():
    configured_url = app.config["SITE_URL"]
    if configured_url and configured_url != "http://localhost:5000":
        return configured_url
    if has_request_context():
        return request.url_root.rstrip("/")
    return configured_url


def build_absolute_url(endpoint, **values):
    relative_url = url_for(endpoint, _external=False, **values)
    return urljoin(f"{get_site_base_url()}/", relative_url.lstrip("/"))


def build_seo_context(title, description=None, keywords=None, canonical=None, robots="index, follow"):
    return {
        "title": title,
        "description": description or DEFAULT_SITE_DESCRIPTION,
        "keywords": keywords or PRIMARY_SEO_KEYWORDS,
        "canonical": canonical or build_absolute_url("index"),
        "robots": robots,
        "og_type": "website",
        "image": build_absolute_url("static", filename="seo/og-image.svg"),
        "image_alt": "Uzgram Mini Chat preview image",
        "site_name": SITE_NAME,
    }


def file_extension(filename):
    return Path(filename or "").suffix.lower().lstrip(".")


def allowed_avatar_file(filename):
    return file_extension(filename) in ALLOWED_AVATAR_EXTENSIONS


def allowed_attachment_file(filename):
    return file_extension(filename) in ALLOWED_ATTACHMENT_EXTENSIONS


def attachment_kind_from_filename(filename):
    extension = file_extension(filename)
    if extension in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if extension in ALLOWED_AUDIO_EXTENSIONS:
        return "audio"
    return "file"


def safe_media_filename(original_name):
    extension = Path(secure_filename(original_name)).suffix.lower()
    return f"{uuid4().hex}{extension}"


def safe_avatar_filename(username, original_name):
    extension = Path(secure_filename(original_name)).suffix.lower()
    base = secure_filename(username or "user")
    return f"{base}_{uuid4().hex}{extension}"


def static_file_exists(relative_path):
    return (STATIC_DIR / relative_path).exists()


def avatar_filename(filename):
    candidate = filename or DEFAULT_AVATAR_FILENAME
    if candidate == "default.png":
        candidate = DEFAULT_AVATAR_FILENAME
    if static_file_exists(f"avatars/{candidate}"):
        return candidate
    return DEFAULT_AVATAR_FILENAME


def group_avatar_filename(filename):
    candidate = filename or DEFAULT_GROUP_AVATAR_FILENAME
    if candidate == "group.png":
        candidate = DEFAULT_GROUP_AVATAR_FILENAME
    if static_file_exists(f"avatars/{candidate}"):
        return candidate
    return DEFAULT_GROUP_AVATAR_FILENAME


def status_label(user):
    if user.status == "online":
        return "Online"
    if not user.last_seen:
        return "Offline"
    return user.last_seen.strftime("Last seen %H:%M")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default=DEFAULT_AVATAR_FILENAME)
    status = db.Column(db.String(20), default="online")
    last_seen = db.Column(db.DateTime, default=utc_now)
    created_at = db.Column(db.DateTime, default=utc_now)

    sent_messages = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        backref="sender",
        lazy=True,
    )
    received_messages = db.relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        backref="receiver",
        lazy=True,
    )
    groups_created = db.relationship("Group", backref="creator", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar_url(self):
        return url_for("static", filename=f"avatars/{avatar_filename(self.avatar)}")

    def to_public_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "avatar_url": self.avatar_url(),
            "status": self.status,
            "status_label": status_label(self),
            "last_seen": as_utc_iso(self.last_seen),
            "created_at": as_utc_iso(self.created_at),
        }


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False, default="")
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    is_read = db.Column(db.Boolean, default=False)
    file_url = db.Column(db.String(255))
    attachment_kind = db.Column(db.String(20), default="text")
    attachment_name = db.Column(db.String(255))
    attachment_mime = db.Column(db.String(120))

    def to_dict(self, client_token=None):
        sender = self.sender
        receiver = self.receiver
        return {
            "id": self.id,
            "client_token": client_token,
            "content": self.content or "",
            "timestamp": as_utc_iso(self.timestamp),
            "sender_id": self.sender_id,
            "sender_name": sender.username if sender else "Unknown",
            "sender_avatar": sender.avatar_url() if sender else url_for("static", filename=f"avatars/{DEFAULT_AVATAR_FILENAME}"),
            "receiver_id": self.receiver_id,
            "receiver_name": receiver.username if receiver else "Unknown",
            "receiver_avatar": receiver.avatar_url() if receiver else url_for("static", filename=f"avatars/{DEFAULT_AVATAR_FILENAME}"),
            "is_read": bool(self.is_read),
            "file_url": self.file_url,
            "attachment_kind": self.attachment_kind or ("image" if self.file_url else "text"),
            "attachment_name": self.attachment_name,
            "attachment_mime": self.attachment_mime,
        }


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    avatar = db.Column(db.String(200), default=DEFAULT_GROUP_AVATAR_FILENAME)

    def avatar_url(self):
        return url_for("static", filename=f"avatars/{group_avatar_filename(self.avatar)}")

    def to_sidebar_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "avatar_url": self.avatar_url(),
            "created_at": as_utc_iso(self.created_at),
        }


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=utc_now)
    role = db.Column(db.String(20), default="member")

    user = db.relationship("User", backref="group_memberships")
    group = db.relationship("Group", backref="members")


class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False, default="")
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id"), nullable=False, index=True)
    file_url = db.Column(db.String(255))
    attachment_kind = db.Column(db.String(20), default="text")
    attachment_name = db.Column(db.String(255))
    attachment_mime = db.Column(db.String(120))

    user = db.relationship("User", backref="group_messages")
    group = db.relationship("Group", backref="messages")

    def to_dict(self, client_token=None):
        author = self.user
        return {
            "id": self.id,
            "client_token": client_token,
            "content": self.content or "",
            "timestamp": as_utc_iso(self.timestamp),
            "user_id": self.user_id,
            "username": author.username if author else "Unknown",
            "user_avatar": author.avatar_url() if author else url_for("static", filename=f"avatars/{DEFAULT_AVATAR_FILENAME}"),
            "group_id": self.group_id,
            "file_url": self.file_url,
            "attachment_kind": self.attachment_kind or ("image" if self.file_url else "text"),
            "attachment_name": self.attachment_name,
            "attachment_mime": self.attachment_mime,
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_site_defaults():
    return {
        "site_owner_name": SITE_OWNER_NAME,
        "site_name": SITE_NAME,
        "site_tagline": SITE_TAGLINE,
        "google_site_verification": app.config["GOOGLE_SITE_VERIFICATION"],
        "homepage_keywords": HOME_KEYWORDS,
        "default_seo": build_seo_context(title=f"{SITE_NAME} | Simple real-time chat app"),
    }


@app.after_request
def add_search_headers(response):
    if request.path.startswith(NOINDEX_PATH_PREFIXES):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def ensure_database_schema():
    db.create_all()

    inspector = inspect(db.engine)
    statements = []

    message_columns = {column["name"] for column in inspector.get_columns("message")}
    if "attachment_kind" not in message_columns:
        statements.append("ALTER TABLE message ADD COLUMN attachment_kind VARCHAR(20) DEFAULT 'text'")
    if "attachment_name" not in message_columns:
        statements.append("ALTER TABLE message ADD COLUMN attachment_name VARCHAR(255)")
    if "attachment_mime" not in message_columns:
        statements.append("ALTER TABLE message ADD COLUMN attachment_mime VARCHAR(120)")
    if "file_url" in message_columns:
        statements.append(
            "UPDATE message SET attachment_kind = 'image' "
            "WHERE file_url IS NOT NULL AND file_url != '' AND (attachment_kind IS NULL OR attachment_kind = '')"
        )

    group_message_columns = {column["name"] for column in inspector.get_columns("group_message")}
    if "attachment_kind" not in group_message_columns:
        statements.append("ALTER TABLE group_message ADD COLUMN attachment_kind VARCHAR(20) DEFAULT 'text'")
    if "attachment_name" not in group_message_columns:
        statements.append("ALTER TABLE group_message ADD COLUMN attachment_name VARCHAR(255)")
    if "attachment_mime" not in group_message_columns:
        statements.append("ALTER TABLE group_message ADD COLUMN attachment_mime VARCHAR(120)")
    if "file_url" in group_message_columns:
        statements.append(
            "UPDATE group_message SET attachment_kind = 'image' "
            "WHERE file_url IS NOT NULL AND file_url != '' AND (attachment_kind IS NULL OR attachment_kind = '')"
        )

    for statement in statements:
        try:
            db.session.execute(text(statement))
        except OperationalError as error:
            db.session.rollback()
            if "duplicate column name" not in str(error).lower():
                raise

    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_message_sender_receiver_time "
            "ON message (sender_id, receiver_id, timestamp DESC)"
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_message_receiver_sender_time "
            "ON message (receiver_id, sender_id, timestamp DESC)"
        )
    )
    db.session.execute(
        text("CREATE INDEX IF NOT EXISTS idx_message_unread ON message (receiver_id, is_read)")
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_group_message_group_time "
            "ON group_message (group_id, timestamp DESC)"
        )
    )
    db.session.execute(
        text(
            f"UPDATE user SET avatar = '{DEFAULT_AVATAR_FILENAME}' "
            "WHERE avatar IS NULL OR avatar = '' OR avatar = 'default.png'"
        )
    )
    db.session.execute(
        text(
            f"UPDATE \"group\" SET avatar = '{DEFAULT_GROUP_AVATAR_FILENAME}' "
            "WHERE avatar IS NULL OR avatar = '' OR avatar = 'group.png'"
        )
    )
    db.session.commit()

    if User.query.count() == 0:
        for username, email, password in [
            ("test", "test@test.com", "test12345"),
            ("ali", "ali@test.com", "ali12345"),
            ("ibrohim", "ibrohim@test.com", "ibrohim12345"),
        ]:
            user = User(username=username, email=email, avatar=DEFAULT_AVATAR_FILENAME)
            user.set_password(password)
            db.session.add(user)
        db.session.commit()


with app.app_context():
    ensure_database_schema()


def conversation_messages_query(other_user_id):
    return Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user_id))
        | ((Message.sender_id == other_user_id) & (Message.receiver_id == current_user.id))
    )


def latest_messages_for_query(query, limit=MESSAGE_FETCH_LIMIT):
    messages = query.order_by(Message.timestamp.desc()).limit(limit).all()
    messages.reverse()
    return messages


def latest_group_messages(group_id, limit=MESSAGE_FETCH_LIMIT):
    messages = (
        GroupMessage.query.filter_by(group_id=group_id)
        .order_by(GroupMessage.timestamp.desc())
        .limit(limit)
        .all()
    )
    messages.reverse()
    return messages


def message_preview(content, attachment_kind, current_side=False):
    prefix = "Siz: " if current_side else ""
    text_value = (content or "").strip()
    if text_value:
        return f"{prefix}{text_value[:44]}"
    if attachment_kind == "image":
        return f"{prefix}Rasm yuborildi"
    if attachment_kind == "audio":
        return f"{prefix}Audio yuborildi"
    return f"{prefix}Fayl yuborildi"


def save_avatar(file_storage, username):
    if not file_storage or not file_storage.filename:
        return DEFAULT_AVATAR_FILENAME
    if not allowed_avatar_file(file_storage.filename):
        raise ValueError("Faqat rasm avatar yuklash mumkin.")

    filename = safe_avatar_filename(username, file_storage.filename)
    file_storage.save(AVATAR_DIR / filename)
    return filename


def save_chat_attachment(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_attachment_file(file_storage.filename):
        raise ValueError("Faqat rasm yoki audio yuborish mumkin.")

    stored_name = safe_media_filename(file_storage.filename)
    file_storage.save(MESSAGE_UPLOAD_DIR / stored_name)
    return {
        "file_url": url_for("static", filename=f"uploads/messages/{stored_name}"),
        "attachment_kind": attachment_kind_from_filename(file_storage.filename),
        "attachment_name": secure_filename(file_storage.filename),
        "attachment_mime": file_storage.mimetype or "application/octet-stream",
    }


def create_direct_message(receiver, content="", attachment=None):
    payload = attachment or {}
    message = Message(
        content=(content or "").strip(),
        sender_id=current_user.id,
        receiver_id=receiver.id,
        file_url=payload.get("file_url"),
        attachment_kind=payload.get("attachment_kind", "text"),
        attachment_name=payload.get("attachment_name"),
        attachment_mime=payload.get("attachment_mime"),
    )
    db.session.add(message)
    db.session.commit()
    return message


def create_group_message(group, content="", attachment=None):
    payload = attachment or {}
    message = GroupMessage(
        content=(content or "").strip(),
        user_id=current_user.id,
        group_id=group.id,
        file_url=payload.get("file_url"),
        attachment_kind=payload.get("attachment_kind", "text"),
        attachment_name=payload.get("attachment_name"),
        attachment_mime=payload.get("attachment_mime"),
    )
    db.session.add(message)
    db.session.commit()
    return message


def mark_direct_messages_as_read(other_user_id):
    unread_messages = Message.query.filter_by(
        sender_id=other_user_id,
        receiver_id=current_user.id,
        is_read=False,
    ).all()
    if not unread_messages:
        return []

    read_ids = []
    for message in unread_messages:
        message.is_read = True
        read_ids.append(message.id)

    db.session.commit()
    socketio.emit(
        "messages_read",
        {"message_ids": read_ids, "user_id": current_user.id},
        room=f"user_{other_user_id}",
    )
    return read_ids


def serialize_private_contact(user):
    last_message = (
        conversation_messages_query(user.id).order_by(Message.timestamp.desc()).first()
    )
    unread_count = Message.query.filter_by(
        sender_id=user.id,
        receiver_id=current_user.id,
        is_read=False,
    ).count()
    last_activity = last_message.timestamp if last_message else user.last_seen or user.created_at

    return {
        **user.to_public_dict(),
        "conversation_type": "direct",
        "has_history": bool(last_message),
        "unread_count": unread_count,
        "last_message_preview": (
            message_preview(
                last_message.content,
                last_message.attachment_kind,
                current_side=last_message.sender_id == current_user.id,
            )
            if last_message
            else "Yangi suhbatni boshlang"
        ),
        "last_message_at": as_utc_iso(last_activity),
    }


def serialize_group(group):
    last_message = (
        GroupMessage.query.filter_by(group_id=group.id)
        .order_by(GroupMessage.timestamp.desc())
        .first()
    )
    member_count = GroupMember.query.filter_by(group_id=group.id).count()
    last_activity = last_message.timestamp if last_message else group.created_at

    return {
        **group.to_sidebar_dict(),
        "conversation_type": "group",
        "has_history": bool(last_message),
        "member_count": member_count,
        "last_message_preview": (
            message_preview(last_message.content, last_message.attachment_kind)
            if last_message
            else "Guruhni jonlantiring"
        ),
        "last_message_at": as_utc_iso(last_activity),
    }


def current_chat_bootstrap():
    users = (
        User.query.filter(User.id != current_user.id)
        .order_by(User.status.desc(), User.last_seen.desc(), User.username.asc())
        .all()
    )
    groups = (
        Group.query.join(GroupMember)
        .filter(GroupMember.user_id == current_user.id)
        .order_by(Group.created_at.desc())
        .all()
    )

    direct_contacts = [serialize_private_contact(user) for user in users]
    group_contacts = [serialize_group(group) for group in groups]
    sorted_targets = sorted(
        [
            *(("direct", contact["id"], contact["last_message_at"] or "") for contact in direct_contacts),
            *(("group", group["id"], group["last_message_at"] or "") for group in group_contacts),
        ],
        key=lambda item: item[2],
        reverse=True,
    )
    initial_target = None
    if sorted_targets:
        initial_target = {"type": sorted_targets[0][0], "id": sorted_targets[0][1]}

    return {
        "current_user": current_user.to_public_dict(),
        "direct_contacts": direct_contacts,
        "group_contacts": group_contacts,
        "available_group_members": [user.to_public_dict() for user in users],
        "initial_target": initial_target,
        "limits": {
            "max_group_members": MAX_GROUP_MEMBERS,
            "max_upload_size_mb": app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
        },
    }


@app.route("/")
def index():
    seo = build_seo_context(
        title="Uzgram Mini Chat | Simple real-time web chat",
        description=(
            "Uzgram Mini Chat - real-time xabarlar, guruh chatlari va sodda muloqot uchun yaratilgan "
            "tezkor Flask web chat ilovasi."
        ),
        keywords=HOME_KEYWORDS,
        canonical=build_absolute_url("index"),
    )
    structured_data = [
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": SITE_OWNER_NAME,
            "url": build_absolute_url("index"),
            "description": DEFAULT_SITE_DESCRIPTION,
            "knowsAbout": [
                "Python",
                "Flask",
                "Socket.IO",
                "SQLAlchemy",
                "Web Development",
                "Real-time Chat Applications",
            ],
            "mainEntityOfPage": build_absolute_url("index"),
        },
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": SITE_NAME,
            "applicationCategory": "CommunicationApplication",
            "operatingSystem": "Web",
            "author": {"@type": "Person", "name": SITE_OWNER_NAME},
            "description": DEFAULT_SITE_DESCRIPTION,
            "url": build_absolute_url("index"),
            "keywords": ", ".join(HOME_KEYWORDS),
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        },
    ]
    return render_template("index.html", seo=seo, structured_data=structured_data)


@app.route(f"/{GOOGLE_VERIFICATION_FILENAME}")
def google_verify():
    return send_from_directory("static", GOOGLE_VERIFICATION_FILENAME)


@app.route("/robots.txt")
def robots():
    lines = ["User-agent: *", "Allow: /"]
    lines.extend(f"Disallow: {path}" for path in PRIVATE_PATH_PREFIXES)
    lines.append(f"Sitemap: {build_absolute_url('sitemap')}")
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    pages = [
        {
            "loc": build_absolute_url("index"),
            "lastmod": datetime.utcnow().date().isoformat(),
            "changefreq": "weekly",
            "priority": "1.0",
        }
    ]
    return Response(render_template("sitemap.xml", pages=pages), mimetype="application/xml")


@app.route("/register", methods=["GET", "POST"])
def register():
    seo = build_seo_context(
        title="Ro'yxatdan o'tish | Uzgram Mini Chat",
        description="Uzgram Mini Chat platformasida yangi chat account yaratish sahifasi.",
        keywords=REGISTER_KEYWORDS,
        canonical=build_absolute_url("register"),
        robots="noindex, nofollow",
    )
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if len(username) < 3:
            flash("Username kamida 3 ta belgidan iborat bo'lishi kerak.")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Parol kamida 6 ta belgidan iborat bo'lishi kerak.")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Bu username allaqachon mavjud.")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Bu email allaqachon mavjud.")
            return redirect(url_for("register"))

        avatar_filename_value = DEFAULT_AVATAR_FILENAME
        avatar_file = request.files.get("avatar")
        if avatar_file and avatar_file.filename:
            try:
                avatar_filename_value = save_avatar(avatar_file, username)
            except ValueError as error:
                flash(str(error))
                return redirect(url_for("register"))

        user = User(username=username, email=email, avatar=avatar_filename_value)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Muvaffaqiyatli ro'yxatdan o'tdingiz.")
        return redirect(url_for("login"))

    return render_template("register.html", seo=seo)


@app.route("/login", methods=["GET", "POST"])
def login():
    seo = build_seo_context(
        title="Kirish | Uzgram Mini Chat",
        description="Uzgram Mini Chat foydalanuvchilari uchun tizimga kirish sahifasi.",
        keywords=LOGIN_KEYWORDS,
        canonical=build_absolute_url("login"),
        robots="noindex, nofollow",
    )
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            user.status = "online"
            user.last_seen = utc_now()
            db.session.commit()
            return redirect(url_for("chat"))

        flash("Username yoki parol noto'g'ri.")

    return render_template("login.html", seo=seo)


@app.route("/logout")
@login_required
def logout():
    current_user.status = "offline"
    current_user.last_seen = utc_now()
    db.session.commit()
    logout_user()
    return redirect(url_for("index"))


@app.route("/chat")
@login_required
def chat():
    seo = build_seo_context(
        title="Chat Panel | Uzgram Mini Chat",
        description="Uzgram Mini Chat foydalanuvchi paneli va real-time yozishmalar sahifasi.",
        keywords=CHAT_KEYWORDS,
        canonical=build_absolute_url("chat"),
        robots="noindex, nofollow",
    )
    return render_template("chat.html", seo=seo, chat_bootstrap=current_chat_bootstrap())


@app.route("/get_messages/<int:user_id>")
@login_required
def get_messages(user_id):
    other_user = User.query.get_or_404(user_id)
    limit = min(request.args.get("limit", MESSAGE_FETCH_LIMIT, type=int), 300)
    messages = latest_messages_for_query(conversation_messages_query(other_user.id), limit=limit)
    mark_direct_messages_as_read(other_user.id)
    return jsonify([message.to_dict() for message in messages])


@app.route("/get_group_messages/<int:group_id>")
@login_required
def get_group_messages(group_id):
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group_id).first()
    if not membership:
        return jsonify({"error": "Bu guruhga siz kirmagansiz."}), 403
    limit = min(request.args.get("limit", MESSAGE_FETCH_LIMIT, type=int), 300)
    messages = latest_group_messages(group_id, limit=limit)
    return jsonify([message.to_dict() for message in messages])


@app.route("/api/conversations/direct/<int:user_id>/messages", methods=["POST"])
@login_required
def send_direct_message_to_user(user_id):
    receiver = User.query.get_or_404(user_id)
    content = request.form.get("content", "").strip()
    client_token = request.form.get("client_token")
    attachment_file = request.files.get("attachment")

    attachment = None
    if attachment_file and attachment_file.filename:
        try:
            attachment = save_chat_attachment(attachment_file)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    if not content and not attachment:
        return jsonify({"error": "Bo'sh xabar yuborib bo'lmaydi."}), 400

    message = create_direct_message(receiver, content=content, attachment=attachment)
    payload = message.to_dict(client_token=client_token)

    socketio.emit("new_message", payload, room=f"user_{receiver.id}")
    socketio.emit("new_message", payload, room=f"user_{current_user.id}")
    return jsonify(payload), 201


@app.route("/api/conversations/direct/<int:user_id>/read", methods=["POST"])
@login_required
def mark_direct_read(user_id):
    User.query.get_or_404(user_id)
    return jsonify({"success": True, "message_ids": mark_direct_messages_as_read(user_id)})


@app.route("/api/conversations/group/<int:group_id>/messages", methods=["POST"])
@login_required
def send_group_message_to_group(group_id):
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group_id).first()
    if not membership:
        return jsonify({"error": "Bu guruhga siz kirmagansiz."}), 403

    group = Group.query.get_or_404(group_id)
    content = request.form.get("content", "").strip()
    client_token = request.form.get("client_token")
    attachment_file = request.files.get("attachment")

    attachment = None
    if attachment_file and attachment_file.filename:
        try:
            attachment = save_chat_attachment(attachment_file)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    if not content and not attachment:
        return jsonify({"error": "Bo'sh xabar yuborib bo'lmaydi."}), 400

    message = create_group_message(group, content=content, attachment=attachment)
    payload = message.to_dict(client_token=client_token)
    socketio.emit("new_group_message", payload, room=f"group_{group_id}")
    return jsonify(payload), 201


@app.route("/create_group", methods=["POST"])
@login_required
def create_group():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        group_name = (data.get("group_name") or "").strip()
        member_ids = data.get("member_ids") or []
    else:
        group_name = (request.form.get("group_name") or "").strip()
        member_ids = request.form.getlist("member_ids[]") or request.form.getlist("member_ids")

    cleaned_member_ids = []
    for member_id in member_ids:
        try:
            cleaned_member_ids.append(int(member_id))
        except (TypeError, ValueError):
            continue

    unique_member_ids = list(dict.fromkeys([current_user.id, *cleaned_member_ids]))

    if not group_name:
        return jsonify({"error": "Guruh nomi kiritilmagan."}), 400
    if len(unique_member_ids) > MAX_GROUP_MEMBERS:
        return jsonify({"error": f"Guruhga maksimal {MAX_GROUP_MEMBERS} ta a'zo qo'shish mumkin."}), 400

    users = User.query.filter(User.id.in_(unique_member_ids)).all()
    found_ids = {user.id for user in users}
    if len(found_ids) != len(set(unique_member_ids)):
        return jsonify({"error": "Ba'zi foydalanuvchilar topilmadi."}), 400

    group = Group(name=group_name, created_by=current_user.id, avatar=DEFAULT_GROUP_AVATAR_FILENAME)
    db.session.add(group)
    db.session.flush()

    for user_id in unique_member_ids:
        role = "admin" if user_id == current_user.id else "member"
        db.session.add(GroupMember(user_id=user_id, group_id=group.id, role=role))

    db.session.commit()

    group_payload = serialize_group(group)
    for user_id in unique_member_ids:
        socketio.emit("group_created", group_payload, room=f"user_{user_id}")

    return jsonify({"success": True, "group": group_payload}), 201


@app.route("/update_avatar", methods=["POST"])
@login_required
def update_avatar():
    avatar_file = request.files.get("avatar")
    if not avatar_file or not avatar_file.filename:
        return jsonify({"error": "Yangi avatar tanlanmagan."}), 400

    try:
        new_avatar = save_avatar(avatar_file, current_user.username)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    old_avatar = avatar_filename(current_user.avatar)
    current_user.avatar = new_avatar
    current_user.last_seen = utc_now()
    db.session.commit()

    if old_avatar not in {DEFAULT_AVATAR_FILENAME, new_avatar}:
        old_path = AVATAR_DIR / old_avatar
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    return jsonify({"success": True, "avatar_url": current_user.avatar_url()})


@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        current_user.status = "online"
        current_user.last_seen = utc_now()
        db.session.commit()
        join_room(f"user_{current_user.id}")


@socketio.on("disconnect")
def handle_disconnect():
    if current_user.is_authenticated:
        current_user.status = "offline"
        current_user.last_seen = utc_now()
        db.session.commit()
        socketio.emit(
            "presence_update",
            {"user_id": current_user.id, "status": current_user.status, "status_label": status_label(current_user)},
        )


@socketio.on("join")
def handle_join():
    if not current_user.is_authenticated:
        return

    join_room(f"user_{current_user.id}")
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    for membership in memberships:
        join_room(f"group_{membership.group_id}")

    socketio.emit(
        "presence_update",
        {"user_id": current_user.id, "status": "online", "status_label": "Online"},
    )


@socketio.on("join_group")
def handle_join_group(data):
    if not current_user.is_authenticated:
        return

    group_id = (data or {}).get("group_id")
    if not group_id:
        return

    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group_id).first()
    if membership:
        join_room(f"group_{group_id}")


@socketio.on("typing")
def handle_typing(data):
    if not current_user.is_authenticated:
        return

    receiver_id = (data or {}).get("receiver_id")
    is_typing = bool((data or {}).get("is_typing", True))
    if not receiver_id:
        return

    emit(
        "user_typing",
        {"user_id": current_user.id, "username": current_user.username, "is_typing": is_typing},
        room=f"user_{receiver_id}",
    )


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)
