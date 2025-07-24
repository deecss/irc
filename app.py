import os
from flask import Flask
from flask_socketio import SocketIO
import eventlet

# Patch dla eventlet
eventlet.monkey_patch()

def create_app():
    app = Flask(__name__)
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
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
