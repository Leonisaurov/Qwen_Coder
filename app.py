from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_cambiala_en_produccion'

# Base de datos en memoria para usuarios y mensajes
usuarios = {}  # {username: hashed_password}
mensajes = []  # [{username, mensaje, timestamp}]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', usuario=session['usuario'], mensajes=mensajes)

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

@app.route('/enviar', methods=['POST'])
def enviar():
    if 'usuario' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    mensaje = request.form.get('mensaje', '').strip()
    if mensaje:
        mensajes.append({
            'username': session['usuario'],
            'mensaje': mensaje,
            'timestamp': datetime.now().strftime('%H:%M')
        })
        # Mantener solo los últimos 50 mensajes
        if len(mensajes) > 50:
            mensajes.pop(0)
    
    return redirect(url_for('index'))

@app.route('/api/mensajes')
def get_mensajes():
    return jsonify(mensajes)

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
