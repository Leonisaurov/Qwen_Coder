from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import hashlib
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_cambiala_en_produccion'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# Base de datos en memoria para usuarios y mensajes
usuarios = {}  # {username: hashed_password}
mensajes = []  # [{username, mensaje, timestamp}]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
        
        if not username or not password:
            error = 'Por favor completa todos los campos'
        elif username in usuarios:
            # Usuario existente, verificar contraseña
            if usuarios[username] == hash_password(password):
                session['usuario'] = username
                return redirect(url_for('index'))
            else:
                error = 'Contraseña incorrecta'
        else:
            # Nuevo usuario, registrarlo automáticamente
            usuarios[username] = hash_password(password)
            session['usuario'] = username
            return redirect(url_for('index'))
    
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/mensajes')
def get_mensajes():
    """Endpoint para obtener mensajes históricos"""
    return jsonify(mensajes)

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
    
    logger.info(f'Mensaje recibido de {username}: {mensaje}')
    
    if mensaje and username:
        msg_data = {
            'username': username,
            'mensaje': mensaje,
            'timestamp': datetime.now().strftime('%H:%M')
        }
        mensajes.append(msg_data)
        # Mantener solo los últimos 50 mensajes
        if len(mensajes) > 50:
            mensajes.pop(0)
        
        # Emitir a todos en la sala global
        emit('receive_message', msg_data, room='global')
        logger.info(f'Mensaje broadcasteado a la sala global')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    logger.info(f"Iniciando servidor en puerto {port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
