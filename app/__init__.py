# Główny pakiet aplikacji IRC Web Client

# Najpierw monkey patch dla eventlet - MUSI być przed wszystkimi importami
import eventlet
eventlet.monkey_patch()

import os
import sys
from pathlib import Path

# Dodaj główny katalog projektu do PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask
from flask_socketio import SocketIO

def create_app():
    # Uzyskaj ścieżkę do katalogu głównego projektu
    base_dir = Path(__file__).parent.parent
    template_dir = base_dir / 'app' / 'templates'
    static_dir = base_dir / 'app' / 'static'
    
    app = Flask(__name__, 
                template_folder=str(template_dir),
                static_folder=str(static_dir))
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
    from .routes.main import main_bp
    from .routes.auth import auth_bp
    from .routes.irc import irc_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(irc_bp, url_prefix='/irc')
    
    # Rejestracja event handlerów SocketIO
    from .services.socketio_handlers import register_socketio_handlers
    register_socketio_handlers(socketio)
    
    return app, socketio
