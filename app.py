import os
import json
import secrets
from datetime import datetime
from flask import Flask, render_template, request, session, jsonify, abort
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
import atexit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Archivos de persistencia
USUARIOS_FILE = 'usuarios.json'
MENSAJES_FILE = 'mensajes.json'

# Variables globales
usuarios_db = {}
mensajes_db = []
usuarios_conectados = set()

def cargar_datos():
    global usuarios_db, mensajes_db
    if os.path.exists(USUARIOS_FILE):
        try:
            with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
                usuarios_db = json.load(f)
        except:
            usuarios_db = {}
    
    if os.path.exists(MENSAJES_FILE):
        try:
            with open(MENSAJES_FILE, 'r', encoding='utf-8') as f:
                mensajes_db = json.load(f)
        except:
            mensajes_db = []

def guardar_datos():
    try:
        with open(USUARIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(usuarios_db, f, ensure_ascii=False, indent=2)
        with open(MENSAJES_FILE, 'w', encoding='utf-8') as f:
            json.dump(mensajes_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando datos: {e}")

# Cargar datos al inicio
cargar_datos()

# Guardar al cerrar
@atexit.register
def guardar_al_salir():
    guardar_datos()

def sanitize_input(text):
    if not text:
        return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')

@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip() if data.get('username') else ''
    password = data.get('password', '') if data.get('password') else ''

    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña requeridos'}), 400
    
    if len(username) < 3 or len(username) > 20:
        return jsonify({'error': 'El usuario debe tener entre 3 y 20 caracteres'}), 400
    
    if len(password) < 4:
        return jsonify({'error': 'La contraseña debe tener al menos 4 caracteres'}), 400

    if not username.isalnum():
        return jsonify({'error': 'El usuario solo puede contener letras y números'}), 400

    if username in usuarios_db:
        return jsonify({'error': 'El usuario ya existe'}), 400

    usuarios_db[username] = {
        'password': generate_password_hash(password, method='pbkdf2:sha256'),
        'registered_at': datetime.now().isoformat(),
        'message_count': 0,
        'avatar_color': '#%06X' % secrets.randbelow(0xFFFFFF)
    }
    guardar_datos()
    
    return jsonify({'success': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip() if data.get('username') else ''
    password = data.get('password', '') if data.get('password') else ''

    user = usuarios_db.get(username)
    if user and check_password_hash(user['password'], password):
        session['username'] = username
        return jsonify({'success': True})
    
    return jsonify({'error': 'Credenciales inválidas'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'success': True})

@app.route('/api/profile/<username>')
def get_profile(username):
    user = usuarios_db.get(username)
    if not user:
        abort(404)
    
    try:
        reg_date = datetime.fromisoformat(user['registered_at'])
        days_active = (datetime.now() - reg_date).days + 1
    except:
        days_active = 1

    return jsonify({
        'username': username,
        'registered_at': user['registered_at'],
        'message_count': user['message_count'],
        'avatar_color': user['avatar_color'],
        'days_active': days_active
    })

@app.route('/api/messages', methods=['GET'])
def get_messages():
    return jsonify(mensajes_db[-50:])  # Últimos 50 mensajes

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    username = session.get('username')
    if username and username in usuarios_conectados:
        usuarios_conectados.discard(username)
        emit('usuario_desconectado', {'username': username}, broadcast=True)
        print(f'Usuario desconectado: {username}')

@socketio.on('unirse_chat')
def handle_join():
    username = session.get('username')
    if username:
        join_room('chat_general')
        usuarios_conectados.add(username)
        emit('usuario_conectado', {'username': username}, broadcast=True)
        # Enviar historial
        emit('historial_mensajes', mensajes_db[-50:])
        print(f'{username} se unió al chat')

@socketio.on('enviar_mensaje')
def handle_message(data):
    username = session.get('username')
    message_text = data.get('msg', '')
    
    if not username or not message_text:
        return
    
    message_text = sanitize_input(message_text.strip())
    if not message_text or len(message_text) > 500:
        return
        
    timestamp = datetime.now().strftime('%H:%M')
    
    new_message = {
        'id': secrets.token_hex(8),
        'user': username,
        'msg': message_text,
        'time': timestamp,
        'color': usuarios_db.get(username, {}).get('avatar_color', '#cccccc')
    }
    
    mensajes_db.append(new_message)
    
    if username in usuarios_db:
        usuarios_db[username]['message_count'] += 1
    
    # Mantener últimos 100 mensajes
    if len(mensajes_db) > 100:
        mensajes_db.pop(0)
    
    # Guardar periódicamente
    if len(mensajes_db) % 10 == 0:
        guardar_datos()
    
    emit('nuevo_mensaje', new_message, broadcast=True)

@socketio.on('typing')
def handle_typing():
    username = session.get('username')
    if username:
        emit('usuario_escribiendo', {'username': username}, broadcast=True, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
