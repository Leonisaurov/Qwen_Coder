from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import hashlib
import os
import logging
import json
import secrets
import html
from functools import wraps

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Archivos de persistencia
USUARIOS_FILE = 'usuarios.json'
MENSAJES_FILE = 'mensajes.json'

# Base de datos en memoria con caché
usuarios = {}  # {username: {password_hash, salt, fecha_registro, mensajes_enviados}}
mensajes = []  # [{username, mensaje, timestamp}]

def cargar_datos():
    """Cargar datos desde archivos JSON"""
    global usuarios, mensajes
    try:
        if os.path.exists(USUARIOS_FILE):
            with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
                usuarios = json.load(f)
            logger.info(f"Cargados {len(usuarios)} usuarios")
    except Exception as e:
        logger.error(f"Error cargando usuarios: {e}")
        usuarios = {}
    
    try:
        if os.path.exists(MENSAJES_FILE):
            with open(MENSAJES_FILE, 'r', encoding='utf-8') as f:
                mensajes = json.load(f)
            logger.info(f"Cargados {len(mensajes)} mensajes")
    except Exception as e:
        logger.error(f"Error cargando mensajes: {e}")
        mensajes = []

def guardar_usuarios():
    """Guardar usuarios en archivo JSON"""
    try:
        with open(USUARIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(usuarios, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando usuarios: {e}")

def guardar_mensajes():
    """Guardar mensajes en archivo JSON"""
    try:
        with open(MENSAJES_FILE, 'w', encoding='utf-8') as f:
            json.dump(mensajes[-100:], f, indent=2, ensure_ascii=False)  # Últimos 100
    except Exception as e:
        logger.error(f"Error guardando mensajes: {e}")

def hash_password(password, salt=None):
    """Hashear contraseña con salt usando PBKDF2"""
    if salt is None:
        salt = secrets.token_hex(16)
    # Usar PBKDF2 para mayor seguridad
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # Iteraciones
    ).hex()
    return password_hash, salt

def verify_password(password, stored_hash, salt):
    """Verificar contraseña"""
    password_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(password_hash, stored_hash)

def sanitize_input(text):
    """Sanitizar input para prevenir XSS"""
    if not text:
        return ''
    # Escapar caracteres HTML
    return html.escape(str(text).strip())[:500]  # Limitar longitud

def login_required(f):
    """Decorator para requerir login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({'error': 'No autorizado'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Cargar datos al iniciar
cargar_datos()

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', usuario=session['usuario'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Validaciones de seguridad
        if not username or not password:
            error = 'Por favor completa todos los campos'
        elif len(username) < 3 or len(username) > 20:
            error = 'El nombre de usuario debe tener entre 3 y 20 caracteres'
        elif len(password) < 4:
            error = 'La contraseña debe tener al menos 4 caracteres'
        elif not username.isalnum():
            error = 'El nombre de usuario solo puede contener letras y números'
        else:
            username = sanitize_input(username)
            
            if username in usuarios:
                # Usuario existente, verificar contraseña
                user_data = usuarios[username]
                if verify_password(password, user_data['password_hash'], user_data['salt']):
                    session['usuario'] = username
                    return redirect(url_for('index'))
                else:
                    error = 'Contraseña incorrecta'
            else:
                # Nuevo usuario, registrarlo automáticamente
                password_hash, salt = hash_password(password)
                usuarios[username] = {
                    'password_hash': password_hash,
                    'salt': salt,
                    'fecha_registro': datetime.now().isoformat(),
                    'mensajes_enviados': 0
                }
                guardar_usuarios()
                session['usuario'] = username
                return redirect(url_for('index'))
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/mensajes')
@login_required
def get_mensajes():
    """Endpoint para obtener mensajes históricos"""
    return jsonify(mensajes[-50:])  # Últimos 50 mensajes

@app.route('/api/perfil/<username>')
@login_required
def get_perfil(username):
    """Obtener perfil público de un usuario"""
    username = sanitize_input(username)
    
    if username not in usuarios:
        abort(404)
    
    user_data = usuarios[username]
    
    # Generar color de avatar basado en el username
    color_hash = hashlib.md5(username.encode()).hexdigest()[:6]
    avatar_color = f"#{color_hash}"
    
    # Calcular mensajes enviados (contando en el historial)
    mensajes_count = sum(1 for msg in mensajes if msg.get('username') == username)
    
    return jsonify({
        'username': username,
        'fecha_registro': user_data.get('fecha_registro', datetime.now().isoformat()),
        'mensajes_enviados': mensajes_count,
        'avatar_color': avatar_color
    })

# Eventos WebSocket
@socketio.on('connect')
def handle_connect():
    logger.info(f'Cliente conectado: {request.sid}')
    emit('connected', {'status': 'ok'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f'Cliente desconectado: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username')
    if not username:
        return
    
    username = sanitize_input(username)
    join_room('global')
    logger.info(f'{username} se unió al chat desde {request.sid}')
    
    # Enviar mensajes históricos al nuevo usuario
    for msg in mensajes[-20:]:  # Últimos 20 mensajes
        emit('receive_message', msg, room=request.sid)
    
    emit('system_message', {'text': f'{username} se ha unido al chat'}, room='global', include_self=False)
    logger.info(f'Mensajes históricos enviados a {username}')

@socketio.on('send_message')
def handle_message(data):
    username = data.get('username')
    mensaje = data.get('mensaje')
    
    if not username or not mensaje:
        return
    
    username = sanitize_input(username)
    mensaje = sanitize_input(mensaje)
    
    logger.info(f'Mensaje recibido de {username}: {mensaje}')
    
    if mensaje and username:
        msg_data = {
            'username': username,
            'mensaje': mensaje,
            'timestamp': datetime.now().strftime('%H:%M')
        }
        mensajes.append(msg_data)
        
        # Actualizar contador de mensajes del usuario
        if username in usuarios:
            usuarios[username]['mensajes_enviados'] = usuarios[username].get('mensajes_enviados', 0) + 1
            guardar_usuarios()
        
        # Mantener solo los últimos 100 mensajes
        if len(mensajes) > 100:
            mensajes.pop(0)
        
        # Guardar mensajes periódicamente
        if len(mensajes) % 10 == 0:
            guardar_mensajes()
        
        # Emitir a todos en la sala global
        emit('receive_message', msg_data, room='global')
        logger.info(f'Mensaje broadcasteado a la sala global')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"Iniciando servidor en puerto {port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
    
    # Guardar datos al cerrar
    import atexit
    @atexit.register
    def guardar_al_salir():
        logger.info("Guardando datos antes de salir...")
        guardar_usuarios()
        guardar_mensajes()
