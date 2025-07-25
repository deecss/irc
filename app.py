import os
import sys
from pathlib import Path

# Dodaj główny katalog projektu do PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from flask import Flask
from flask_socketio import SocketIO
import eventlet

# Patch dla eventlet
eventlet.monkey_patch()

def create_app():
    app = Flask(__name__, 
                template_folder='app/templates',
                static_folder='app/static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['DEBUG'] = True
    
    # Inicjalizacja SocketIO
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        logger=True,
        engineio_logger=True,
        async_mode='eventlet'
    )
    
    # Rejestracja blueprintów
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.irc import irc_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(irc_bp, url_prefix='/irc')
    
    # Rejestracja event handlerów SocketIO
    from app.services.socketio_handlers import register_socketio_handlers
    register_socketio_handlers(socketio)
    
    return app, socketio

app, socketio = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5667, debug=True)
