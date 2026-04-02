from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, Response, has_request_context, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from urllib.parse import urljoin

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mini-telegram-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///telegram.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SITE_URL'] = os.environ.get('SITE_URL', 'http://localhost:5000').rstrip('/')
app.config['GOOGLE_SITE_VERIFICATION'] = os.environ.get('GOOGLE_SITE_VERIFICATION', '').strip()

SITE_OWNER_NAME = 'Asilbek Mirolimov'
SITE_TAGLINE = 'Python, Flask va Socket.IO asosidagi real-time chat loyihasi'
DEFAULT_SITE_DESCRIPTION = (
    "Asilbek Mirolimovning Mini Chat loyihasi: Flask, SQLAlchemy va Socket.IO bilan "
    "yaratilgan tezkor xabar almashish platformasi."
)
DEFAULT_SITE_KEYWORDS = [
    'Asilbek Mirolimov',
    'Mini Chat',
    'mini telegram',
    'Python chat app',
    'Flask chat',
    'Socket.IO chat',
    'SQLAlchemy loyiha',
    'real-time chat',
    'web dasturlash',
    'chat platforma',
    'Python web loyiha',
]
NOINDEX_PATH_PREFIXES = (
    '/login',
    '/register',
    '/chat',
    '/logout',
    '/get_messages',
    '/get_group_messages',
    '/create_group',
    '/update_avatar',
)
PRIVATE_PATH_PREFIXES = (
    '/chat',
    '/logout',
    '/get_messages',
    '/get_group_messages',
    '/create_group',
    '/update_avatar',
)

# Avatar yuklash uchun sozlamalar
app.config['UPLOADED_AVATARS_DEST'] = 'static/avatars'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Flask-Uploads o'rniga oddiy yuklash
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_site_base_url():
    configured_url = app.config['SITE_URL']
    if configured_url and configured_url != 'http://localhost:5000':
        return configured_url
    if has_request_context():
        return request.url_root.rstrip('/')
    return configured_url

def build_absolute_url(endpoint, **values):
    relative_url = url_for(endpoint, _external=False, **values)
    return urljoin(f"{get_site_base_url()}/", relative_url.lstrip('/'))

def build_seo_context(title, description=None, keywords=None, canonical=None, robots='index, follow'):
    return {
        'title': title,
        'description': description or DEFAULT_SITE_DESCRIPTION,
        'keywords': keywords or DEFAULT_SITE_KEYWORDS,
        'canonical': canonical or build_absolute_url('index'),
        'robots': robots,
        'og_type': 'website',
        'image': build_absolute_url('static', filename='seo/og-image.svg'),
    }

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Avatar papkasini yaratish
os.makedirs(app.config['UPLOADED_AVATARS_DEST'], exist_ok=True)

# Foydalanuvchi modeli
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default='default.png')
    status = db.Column(db.String(20), default='online')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Munosabatlar
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    groups_created = db.relationship('Group', backref='creator', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def avatar_url(self):
        return url_for('static', filename=f'avatars/{self.avatar}')

# Xabar modeli
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    file_url = db.Column(db.String(200))
    
    def to_dict(self):
        sender = User.query.get(self.sender_id)
        receiver = User.query.get(self.receiver_id)
        return {
            'id': self.id,
            'content': self.content,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'sender_id': self.sender_id,
            'sender_name': sender.username if sender else 'Unknown',
            'sender_avatar': sender.avatar_url() if sender else url_for('static', filename='avatars/default.png'),
            'receiver_id': self.receiver_id,
            'receiver_name': receiver.username if receiver else 'Unknown',
            'is_read': self.is_read,
            'file_url': self.file_url
        }

# Guruh modeli
class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    avatar = db.Column(db.String(200), default='group.png')
    
    def avatar_url(self):
        return url_for('static', filename=f'avatars/{self.avatar}')

# Guruh a'zolari
class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='member')
    
    user = db.relationship('User', backref='group_memberships')
    group = db.relationship('Group', backref='members')

# Guruh xabarlari
class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    file_url = db.Column(db.String(200))
    
    def to_dict(self):
        user = User.query.get(self.user_id)
        return {
            'id': self.id,
            'content': self.content,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'user_id': self.user_id,
            'username': user.username if user else 'Unknown',
            'user_avatar': user.avatar_url() if user else url_for('static', filename='avatars/default.png'),
            'group_id': self.group_id,
            'file_url': self.file_url
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_site_defaults():
    return {
        'site_owner_name': SITE_OWNER_NAME,
        'site_tagline': SITE_TAGLINE,
        'google_site_verification': app.config['GOOGLE_SITE_VERIFICATION'],
        'default_seo': build_seo_context(
            title=f'{SITE_OWNER_NAME} | Mini Chat va Flask chat loyihasi'
        ),
    }

@app.after_request
def add_search_headers(response):
    if request.path.startswith(NOINDEX_PATH_PREFIXES):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response

# Ma'lumotlar bazasini yaratish
with app.app_context():
    db.create_all()
    
    # Test ma'lumotlari
    if User.query.count() == 0:
        users = [
            ('test', 'test@test.com', 'test123'),
            ('ali', 'ali@test.com', 'ali123'),
            ('ibrohim', 'ibrohim@test.com', 'ibrohim123')
        ]
        for username, email, password in users:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
        db.session.commit()

# Routes
@app.route('/')
def index():
    seo = build_seo_context(
        title='Asilbek Mirolimov | Mini Chat, Flask Chat App va Python Web Loyiha',
        description=(
            "Asilbek Mirolimovning Mini Chat loyihasi. Ushbu sayt Flask, SQLAlchemy va "
            "Socket.IO yordamida yaratilgan real-time chat platformasi bo'lib, Google qidiruvi "
            "uchun Asilbek Mirolimov, Mini Chat, Flask chat app va Python web loyiha kalit "
            "so'zlari bilan optimallashtirilgan."
        ),
        keywords=[
            'Asilbek Mirolimov',
            'Asilbek Mirolimov portfolio',
            'Asilbek Mirolimov loyiha',
            'Mini Chat',
            'mini telegram loyiha',
            'Flask chat app',
            'Python web loyiha',
            'real-time messaging',
            'Socket.IO loyiha',
            'chat dasturi',
            'web ilova',
            'Uzbek developer project',
        ],
        canonical=build_absolute_url('index'),
    )
    structured_data = [
        {
            '@context': 'https://schema.org',
            '@type': 'Person',
            'name': SITE_OWNER_NAME,
            'url': build_absolute_url('index'),
            'description': DEFAULT_SITE_DESCRIPTION,
            'knowsAbout': [
                'Python',
                'Flask',
                'Socket.IO',
                'SQLAlchemy',
                'Web Development',
                'Real-time Chat Applications',
            ],
            'mainEntityOfPage': build_absolute_url('index'),
        },
        {
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            'name': 'Mini Chat',
            'applicationCategory': 'CommunicationApplication',
            'operatingSystem': 'Web',
            'author': {
                '@type': 'Person',
                'name': SITE_OWNER_NAME,
            },
            'description': DEFAULT_SITE_DESCRIPTION,
            'url': build_absolute_url('index'),
            'keywords': ', '.join(DEFAULT_SITE_KEYWORDS),
            'offers': {
                '@type': 'Offer',
                'price': '0',
                'priceCurrency': 'USD',
            },
        },
    ]
    return render_template('index.html', seo=seo, structured_data=structured_data)

@app.route('/googleef6572d0f05659ed.html')
def google_verify():
    return send_from_directory('static', 'googleef6572d0f05659ed.html')

@app.route('/robots.txt')
def robots():
    lines = [
        'User-agent: *',
        'Allow: /',
    ]
    lines.extend(f'Disallow: {path}' for path in PRIVATE_PATH_PREFIXES)
    lines.append(f'Sitemap: {build_absolute_url("sitemap")}')
    return Response('\n'.join(lines), mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    pages = [
        {
            'loc': build_absolute_url('index'),
            'lastmod': datetime.utcnow().date().isoformat(),
            'changefreq': 'weekly',
            'priority': '1.0',
        },
    ]
    return Response(render_template('sitemap.xml', pages=pages), mimetype='application/xml')

@app.route('/register', methods=['GET', 'POST'])
def register():
    seo = build_seo_context(
        title='Ro‘yxatdan o‘tish | Mini Chat',
        description='Mini Chat platformasida yangi hisob yaratish sahifasi.',
        keywords=['Mini Chat register', 'ro‘yxatdan o‘tish', 'chat account yaratish'],
        canonical=build_absolute_url('register'),
        robots='noindex, nofollow',
    )
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Avatar yuklash
        avatar_filename = 'default.png'
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename and allowed_file(file.filename):
                # Fayl nomini xavfsiz qilish
                filename = secure_filename(f"{username}_{file.filename}")
                # Faylni saqlash
                file.save(os.path.join(app.config['UPLOADED_AVATARS_DEST'], filename))
                avatar_filename = filename
        
        if User.query.filter_by(username=username).first():
            flash('Bu username allaqachon mavjud')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Bu email allaqachon mavjud')
            return redirect(url_for('register'))
        
        user = User(
            username=username, 
            email=email,
            avatar=avatar_filename
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Muvaffaqiyatli ro\'yxatdan o\'tdingiz!')
        return redirect(url_for('login'))
    
    return render_template('register.html', seo=seo)

@app.route('/login', methods=['GET', 'POST'])
def login():
    seo = build_seo_context(
        title='Kirish | Mini Chat',
        description='Mini Chat foydalanuvchilari uchun tizimga kirish sahifasi.',
        keywords=['Mini Chat login', 'chat login', 'tizimga kirish'],
        canonical=build_absolute_url('login'),
        robots='noindex, nofollow',
    )
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.status = 'online'
            user.last_seen = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('chat'))
        
        flash('Username yoki parol noto\'g\'ri')
    
    return render_template('login.html', seo=seo)

@app.route('/logout')
@login_required
def logout():
    current_user.status = 'offline'
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    logout_user()
    return redirect(url_for('index'))

@app.route('/chat')
@login_required
def chat():
    users = User.query.filter(User.id != current_user.id).all()
    groups = Group.query.join(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    seo = build_seo_context(
        title='Chat Panel | Mini Chat',
        description='Mini Chat foydalanuvchi paneli va real-time yozishmalar sahifasi.',
        keywords=['Mini Chat panel', 'chat dashboard'],
        canonical=build_absolute_url('chat'),
        robots='noindex, nofollow',
    )
    return render_template('chat.html', users=users, groups=groups, seo=seo)

@app.route('/get_messages/<int:user_id>')
@login_required
def get_messages(user_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True
    
    db.session.commit()
    return jsonify([msg.to_dict() for msg in messages])

@app.route('/get_group_messages/<int:group_id>')
@login_required
def get_group_messages(group_id):
    messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.timestamp).all()
    return jsonify([msg.to_dict() for msg in messages])

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    group_name = request.form.get('group_name')
    
    if not group_name:
        return jsonify({'error': 'Guruh nomi kiritilmagan'}), 400
    
    group = Group(name=group_name, created_by=current_user.id)
    db.session.add(group)
    db.session.flush()
    
    member = GroupMember(user_id=current_user.id, group_id=group.id, role='admin')
    db.session.add(member)
    db.session.commit()
    
    return jsonify({'success': True, 'group_id': group.id, 'group_name': group.name})

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Fayl yuklanmadi'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'Fayl tanlanmadi'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Faqat rasm fayllari yuklash mumkin (png, jpg, jpeg, gif)'}), 400
    
    # Eski avatarni o'chirish (default bo'lmasa)
    if current_user.avatar != 'default.png':
        old_avatar_path = os.path.join(app.config['UPLOADED_AVATARS_DEST'], current_user.avatar)
        if os.path.exists(old_avatar_path):
            os.remove(old_avatar_path)
    
    # Yangi avatarni saqlash
    filename = secure_filename(f"{current_user.username}_{file.filename}")
    file.save(os.path.join(app.config['UPLOADED_AVATARS_DEST'], filename))
    
    current_user.avatar = filename
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'avatar_url': current_user.avatar_url()
    })

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        current_user.status = 'online'
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        current_user.status = 'offline'
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

@socketio.on('join')
def handle_join():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        
        memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
        for m in memberships:
            join_room(f"group_{m.group_id}")

@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated:
        return
    
    content = data.get('content', '').strip()
    receiver_id = data.get('receiver_id')
    
    if not content or not receiver_id:
        return
    
    msg = Message(
        content=content,
        sender_id=current_user.id,
        receiver_id=receiver_id
    )
    db.session.add(msg)
    db.session.commit()
    
    message_data = {
        'id': msg.id,
        'content': content,
        'sender_id': current_user.id,
        'sender_name': current_user.username,
        'sender_avatar': current_user.avatar_url(),
        'receiver_id': receiver_id,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'is_read': False
    }
    
    # Qabul qiluvchiga yuborish
    emit('new_message', message_data, room=f"user_{receiver_id}")

@socketio.on('send_group_message')
def handle_group_message(data):
    if not current_user.is_authenticated:
        return
    
    content = data.get('content', '').strip()
    group_id = data.get('group_id')
    
    if not content or not group_id:
        return
    
    member = GroupMember.query.filter_by(user_id=current_user.id, group_id=group_id).first()
    if not member:
        return
    
    msg = GroupMessage(
        content=content,
        user_id=current_user.id,
        group_id=group_id
    )
    db.session.add(msg)
    db.session.commit()
    
    message_data = {
        'id': msg.id,
        'content': content,
        'user_id': current_user.id,
        'username': current_user.username,
        'user_avatar': current_user.avatar_url(),
        'group_id': group_id,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Guruhdagi hammaga yuborish
    emit('new_group_message', message_data, room=f"group_{group_id}")

@socketio.on('typing')
def handle_typing(data):
    if not current_user.is_authenticated:
        return
    
    receiver_id = data.get('receiver_id')
    is_typing = data.get('is_typing', True)
    
    if receiver_id:
        emit('user_typing', {
            'user_id': current_user.id,
            'username': current_user.username,
            'is_typing': is_typing
        }, room=f"user_{receiver_id}")

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
