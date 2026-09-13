from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Lista temporal para almacenar mensajes (en memoria)
mensajes = []

@app.route('/')
def index():
    return render_template('index.html', mensajes=mensajes)

@app.route('/agregar', methods=['POST'])
def agregar():
    mensaje = request.form.get('mensaje')
    if mensaje:
        mensajes.append(mensaje)
    return redirect(url_for('index'))

@app.route('/limpiar', methods=['POST'])
def limpiar():
    mensajes.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
