from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import hashlib
import os

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_cambiala_en_produccion'
socketio = SocketIO(app, cors_allowed_origins="*")

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

# Eventos WebSocket
@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')

@socketio.on('join_chat')
def handle_join(data):
    username = data.get('username')
    join_room('global')
    print(f'{username} se unió al chat')
    emit('system_message', {'text': f'{username} se ha unido al chat'}, room='global', broadcast=True, include_self=False)

@socketio.on('send_message')
def handle_message(data):
    username = data.get('username')
    mensaje = data.get('mensaje')
    
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
        
        # Emitir a todos en la sala
        emit('receive_message', msg_data, room='global', broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
