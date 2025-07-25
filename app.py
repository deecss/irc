# Główny plik startowy aplikacji IRC Web Client
from app import create_app

app, socketio = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5667, debug=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5667, debug=True)
