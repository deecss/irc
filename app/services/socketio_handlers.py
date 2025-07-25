from flask_socketio import emit, disconnect, join_room, leave_room
from flask import session, request
import logging
import json
from datetime import datetime
from app.models import IRCServer, UserProfile
from app.services.connection_manager import irc_manager

logger = logging.getLogger(__name__)

def register_socketio_handlers(socketio):
    """Rejestruje handlery SocketIO"""
    
    @socketio.on('connect')
    def handle_connect():
        """Obsługuje połączenie klienta"""
        session_id = request.sid
        logger.info(f"Klient połączony: {session_id}")
        
        # Sprawdź czy użytkownik ma zapisaną sesję w bazie danych
        user_data = irc_manager.get_user_profile_by_session(session_id)
        if user_data:
            # Przywróć połączenia IRC użytkownika
            reconnected = irc_manager.reconnect_user_connections(session_id)
            emit('status', {
                'connected': True, 
                'session_id': session_id,
                'user': {
                    'username': user_data.username,
                    'nickname': user_data.preferred_nickname,
                    'reconnected_connections': reconnected
                }
            })
        else:
            emit('status', {'connected': True, 'session_id': session_id})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Obsługuje rozłączenie klienta - NIE usuwa profilu ani połączeń IRC"""
        session_id = request.sid
        logger.info(f"Klient rozłączony: {session_id}")
        
        # Usuń tylko sesję, ale zachowaj połączenia IRC (persistent connections)
        irc_manager.remove_user_profile(session_id)
    
    @socketio.on('register_user')
    def handle_register_user(data):
        """Rejestruje profil użytkownika"""
        try:
            from app.routes.auth import hash_password
            
            session_id = request.sid
            
            # Walidacja danych
            required_fields = ['username', 'preferred_nickname', 'preferred_ident', 'preferred_realname', 'password']
            for field in required_fields:
                if field not in data or not data[field]:
                    emit('error', {'message': f'Pole {field} jest wymagane'})
                    return
            
            # Hashuj hasło
            password_hash = hash_password(data['password'])
            
            # Utworzenie profilu użytkownika
            profile = UserProfile(
                username=data['username'],
                email=data.get('email', ''),
                preferred_nickname=data['preferred_nickname'],
                preferred_ident=data['preferred_ident'],
                preferred_realname=data['preferred_realname'],
                servers=[],
                auto_join_channels=data.get('auto_join_channels', []),
                preferences=data.get('preferences', {})
            )
            
            # Zapisanie profilu do bazy danych z hasłem
            user_id = irc_manager.save_user_profile(profile, session_id, password_hash)
            
            emit('user_registered', {
                'success': True,
                'user_id': user_id,
                'profile': {
                    'username': profile.username,
                    'email': profile.email,
                    'nickname': profile.preferred_nickname,
                    'ident': profile.preferred_ident,
                    'realname': profile.preferred_realname,
                    'preferred_nickname': profile.preferred_nickname,
                    'preferred_ident': profile.preferred_ident,
                    'preferred_realname': profile.preferred_realname,
                    'auto_join_channels': profile.auto_join_channels,
                    'preferences': profile.preferences
                }
            })
            
        except Exception as e:
            logger.error(f"Błąd rejestracji użytkownika: {e}")
            emit('error', {'message': f'Błąd rejestracji: {str(e)}'})
    
    @socketio.on('login_user')
    def handle_login_user(data):
        """Loguje użytkownika"""
        try:
            from app.services.database import db
            from app.routes.auth import verify_password
            
            session_id = request.sid
            
            # Walidacja danych
            if not data.get('username') or not data.get('password'):
                emit('login_error', {'message': 'Nazwa użytkownika i hasło są wymagane'})
                return
            
            username = data['username'].strip()
            password = data['password']
            
            # Sprawdź użytkownika w bazie
            user_data = db.get_user_by_username(username)
            
            if not user_data:
                emit('login_error', {'message': 'Nieprawidłowa nazwa użytkownika lub hasło'})
                return
            
            # Sprawdź czy użytkownik ma ustawione hasło
            if 'password_hash' not in user_data or not user_data['password_hash']:
                emit('login_error', {'message': 'Konto nie ma ustawionego hasła. Proszę zarejestrować się ponownie.'})
                return
            
            # Weryfikuj hasło
            if not verify_password(password, user_data['password_hash']):
                emit('login_error', {'message': 'Nieprawidłowa nazwa użytkownika lub hasło'})
                return
            
            # Aktualizuj ostatnie logowanie
            db.update_last_login(user_data['username'])
            
            # Utwórz profil użytkownika w sesji
            profile = UserProfile(
                username=user_data['username'],
                email=user_data.get('email', ''),
                preferred_nickname=user_data['preferred_nickname'],
                preferred_ident=user_data['preferred_ident'],
                preferred_realname=user_data['preferred_realname'],
                servers=[],
                auto_join_channels=json.loads(user_data.get('auto_join_channels', '[]')),
                preferences=json.loads(user_data.get('preferences', '{}'))
            )
            
            # Zapisz profil w connection manager
            irc_manager.add_user_profile(session_id, profile)
            
            emit('login_success', {
                'success': True,
                'message': 'Zalogowano pomyślnie',
                'user': {
                    'username': profile.username,
                    'email': profile.email,
                    'nickname': profile.preferred_nickname,
                    'preferred_nickname': profile.preferred_nickname,
                    'preferred_ident': profile.preferred_ident,
                    'preferred_realname': profile.preferred_realname
                }
            })
            
        except Exception as e:
            logger.error(f"Błąd logowania użytkownika: {e}")
            emit('login_error', {'message': f'Błąd logowania: {str(e)}'})
    
    @socketio.on('connect_to_server')
    def handle_connect_to_server(data):
        """Łączy z serwerem IRC"""
        try:
            session_id = request.sid
            
            # Walidacja danych
            required_fields = ['name', 'host', 'port']
            for field in required_fields:
                if field not in data or not data[field]:
                    emit('error', {'message': f'Pole {field} jest wymagane'})
                    return
            
            # Utworzenie obiektu serwera
            server = IRCServer(
                name=data['name'],
                host=data['host'],
                port=int(data['port']),
                ssl=data.get('ssl', False),
                ipv6=data.get('ipv6', False),
                encoding=data.get('encoding', 'utf-8')
            )
            
            # Callback dla wiadomości IRC
            def socketio_callback(sess_id, event_type, target, message_data):
                socketio.emit('irc_message', {
                    'event_type': event_type,
                    'target': target,
                    'data': message_data
                }, room=sess_id)
            
            # Ustawienie callback'a w menedżerze
            irc_manager.socketio_callback = socketio_callback
            
            # Próba połączenia
            connection_id = irc_manager.connect_to_server(session_id, server)
            
            emit('server_connected', {
                'success': True,
                'connection_id': connection_id,
                'server': {
                    'name': server.name,
                    'host': server.host,
                    'port': server.port,
                    'ssl': server.ssl,
                    'ipv6': server.ipv6
                }
            })
            
        except Exception as e:
            logger.error(f"Błąd połączenia z serwerem: {e}")
            emit('error', {'message': f'Błąd połączenia: {str(e)}'})
    
    @socketio.on('disconnect_from_server')
    def handle_disconnect_from_server(data):
        """Rozłącza z serwerem IRC"""
        try:
            connection_id = data.get('connection_id')
            if not connection_id:
                emit('error', {'message': 'Brak connection_id'})
                return
            
            irc_manager.disconnect_from_server(connection_id)
            emit('server_disconnected', {'connection_id': connection_id})
            
        except Exception as e:
            logger.error(f"Błąd rozłączania z serwerem: {e}")
            emit('error', {'message': f'Błąd rozłączania: {str(e)}'})
    
    @socketio.on('send_message')
    def handle_send_message(data):
        """Wysyła wiadomość IRC"""
        try:
            connection_id = data.get('connection_id')
            target = data.get('target')
            message = data.get('message')
            
            if not all([connection_id, target, message]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.send_message(connection_id, target, message):
                emit('message_sent', {
                    'connection_id': connection_id,
                    'target': target,
                    'message': message
                })
            else:
                emit('error', {'message': 'Nie udało się wysłać wiadomości'})
                
        except Exception as e:
            logger.error(f"Błąd wysyłania wiadomości: {e}")
            emit('error', {'message': f'Błąd wysyłania wiadomości: {str(e)}'})
    
    @socketio.on('send_action')
    def handle_send_action(data):
        """Wysyła akcję (/me)"""
        try:
            connection_id = data.get('connection_id')
            target = data.get('target')
            action = data.get('action')
            
            if not all([connection_id, target, action]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.send_action(connection_id, target, action):
                emit('action_sent', {
                    'connection_id': connection_id,
                    'target': target,
                    'action': action
                })
            else:
                emit('error', {'message': 'Nie udało się wysłać akcji'})
                
        except Exception as e:
            logger.error(f"Błąd wysyłania akcji: {e}")
            emit('error', {'message': f'Błąd wysyłania akcji: {str(e)}'})
    
    @socketio.on('join_channel')
    def handle_join_channel(data):
        """Dołącza do kanału"""
        try:
            connection_id = data.get('connection_id')
            channel = data.get('channel')
            key = data.get('key')
            
            if not all([connection_id, channel]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.join_channel(connection_id, channel, key):
                emit('join_requested', {
                    'connection_id': connection_id,
                    'channel': channel
                })
            else:
                emit('error', {'message': 'Nie udało się dołączyć do kanału'})
                
        except Exception as e:
            logger.error(f"Błąd dołączania do kanału: {e}")
            emit('error', {'message': f'Błąd dołączania do kanału: {str(e)}'})
    
    @socketio.on('part_channel')
    def handle_part_channel(data):
        """Opuszcza kanał"""
        try:
            connection_id = data.get('connection_id')
            channel = data.get('channel')
            reason = data.get('reason')
            
            if not all([connection_id, channel]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.part_channel(connection_id, channel, reason):
                emit('part_requested', {
                    'connection_id': connection_id,
                    'channel': channel
                })
            else:
                emit('error', {'message': 'Nie udało się opuścić kanału'})
                
        except Exception as e:
            logger.error(f"Błąd opuszczania kanału: {e}")
            emit('error', {'message': f'Błąd opuszczania kanału: {str(e)}'})
    
    @socketio.on('change_nick')
    def handle_change_nick(data):
        """Zmienia nick"""
        try:
            connection_id = data.get('connection_id')
            new_nick = data.get('new_nick')
            
            if not all([connection_id, new_nick]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.change_nick(connection_id, new_nick):
                emit('nick_change_requested', {
                    'connection_id': connection_id,
                    'new_nick': new_nick
                })
            else:
                emit('error', {'message': 'Nie udało się zmienić nicka'})
                
        except Exception as e:
            logger.error(f"Błąd zmiany nicka: {e}")
            emit('error', {'message': f'Błąd zmiany nicka: {str(e)}'})
    
    @socketio.on('set_topic')
    def handle_set_topic(data):
        """Ustawia temat kanału"""
        try:
            connection_id = data.get('connection_id')
            channel = data.get('channel')
            topic = data.get('topic')
            
            if not all([connection_id, channel, topic is not None]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.set_topic(connection_id, channel, topic):
                emit('topic_set_requested', {
                    'connection_id': connection_id,
                    'channel': channel,
                    'topic': topic
                })
            else:
                emit('error', {'message': 'Nie udało się ustawić tematu'})
                
        except Exception as e:
            logger.error(f"Błąd ustawiania tematu: {e}")
            emit('error', {'message': f'Błąd ustawiania tematu: {str(e)}'})
    
    @socketio.on('kick_user')
    def handle_kick_user(data):
        """Wyrzuca użytkownika z kanału"""
        try:
            connection_id = data.get('connection_id')
            channel = data.get('channel')
            nick = data.get('nick')
            reason = data.get('reason')
            
            if not all([connection_id, channel, nick]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.kick_user(connection_id, channel, nick, reason):
                emit('kick_requested', {
                    'connection_id': connection_id,
                    'channel': channel,
                    'nick': nick,
                    'reason': reason
                })
            else:
                emit('error', {'message': 'Nie udało się wykopać użytkownika'})
                
        except Exception as e:
            logger.error(f"Błąd wykopywania użytkownika: {e}")
            emit('error', {'message': f'Błąd wykopywania użytkownika: {str(e)}'})
    
    @socketio.on('set_mode')
    def handle_set_mode(data):
        """Ustawia tryby"""
        try:
            connection_id = data.get('connection_id')
            target = data.get('target')
            modes = data.get('modes')
            params = data.get('params')
            
            if not all([connection_id, target, modes]):
                emit('error', {'message': 'Brak wymaganych danych'})
                return
            
            if irc_manager.set_mode(connection_id, target, modes, params):
                emit('mode_set_requested', {
                    'connection_id': connection_id,
                    'target': target,
                    'modes': modes,
                    'params': params
                })
            else:
                emit('error', {'message': 'Nie udało się ustawić trybu'})
                
        except Exception as e:
            logger.error(f"Błąd ustawiania trybu: {e}")
            emit('error', {'message': f'Błąd ustawiania trybu: {str(e)}'})
    
    @socketio.on('get_connections')
    def handle_get_connections():
        """Zwraca listę połączeń użytkownika"""
        try:
            session_id = request.sid
            connections = irc_manager.get_all_connections_status(session_id)
            emit('connections_list', {'connections': connections})
            
        except Exception as e:
            logger.error(f"Błąd pobierania listy połączeń: {e}")
            emit('error', {'message': f'Błąd pobierania połączeń: {str(e)}'})
    
    @socketio.on('get_user_servers')
    def handle_get_user_servers():
        """Zwraca listę serwerów użytkownika"""
        try:
            session_id = request.sid
            servers = irc_manager.get_user_servers(session_id)
            emit('user_servers_list', {'servers': servers})
            
        except Exception as e:
            logger.error(f"Błąd pobierania listy serwerów: {e}")
            emit('error', {'message': f'Błąd pobierania serwerów: {str(e)}'})
    
    @socketio.on('save_user_server')
    def handle_save_user_server(data):
        """Zapisuje nowy serwer użytkownika"""
        try:
            session_id = request.sid
            
            # Walidacja danych
            required_fields = ['name', 'host', 'port']
            for field in required_fields:
                if field not in data or not data[field]:
                    emit('error', {'message': f'Pole {field} jest wymagane'})
                    return
            
            # Utworzenie obiektu serwera
            server = IRCServer(
                name=data['name'],
                host=data['host'],
                port=int(data['port']),
                ssl=data.get('ssl', False),
                ipv6=data.get('ipv6', False),
                encoding=data.get('encoding', 'utf-8')
            )
            
            auto_connect = data.get('auto_connect', False)
            server_id = irc_manager.save_user_server(session_id, server, auto_connect)
            
            emit('server_saved', {
                'success': True,
                'server_id': server_id,
                'message': f'Serwer {server.name} został zapisany'
            })
            
        except Exception as e:
            logger.error(f"Błąd zapisywania serwera: {e}")
            emit('error', {'message': f'Błąd zapisywania serwera: {str(e)}'})
    
    @socketio.on('update_user_server')
    def handle_update_user_server(data):
        """Aktualizuje serwer użytkownika"""
        try:
            session_id = request.sid
            
            # Walidacja danych
            required_fields = ['server_id', 'name', 'host', 'port']
            for field in required_fields:
                if field not in data or data[field] is None:
                    emit('error', {'message': f'Pole {field} jest wymagane'})
                    return
            
            # Utworzenie obiektu serwera
            server = IRCServer(
                name=data['name'],
                host=data['host'],
                port=int(data['port']),
                ssl=data.get('ssl', False),
                ipv6=data.get('ipv6', False),
                encoding=data.get('encoding', 'utf-8')
            )
            
            auto_connect = data.get('auto_connect')
            irc_manager.update_user_server(session_id, data['server_id'], server, auto_connect)
            
            emit('server_updated', {
                'success': True,
                'server_id': data['server_id'],
                'message': f'Serwer {server.name} został zaktualizowany'
            })
            
        except Exception as e:
            logger.error(f"Błąd aktualizacji serwera: {e}")
            emit('error', {'message': f'Błąd aktualizacji serwera: {str(e)}'})
    
    @socketio.on('delete_user_server')
    def handle_delete_user_server(data):
        """Usuwa serwer użytkownika"""
        try:
            session_id = request.sid
            server_id = data.get('server_id')
            
            if not server_id:
                emit('error', {'message': 'Brak ID serwera'})
                return
            
            irc_manager.delete_user_server(session_id, server_id)
            
            emit('server_deleted', {
                'success': True,
                'server_id': server_id,
                'message': 'Serwer został usunięty'
            })
            
        except Exception as e:
            logger.error(f"Błąd usuwania serwera: {e}")
            emit('error', {'message': f'Błąd usuwania serwera: {str(e)}'})
    
    @socketio.on('get_user_profile')
    def handle_get_user_profile():
        """Zwraca profil aktualnego użytkownika"""
        try:
            session_id = request.sid
            profile = irc_manager.get_user_profile_by_session(session_id)
            
            if profile:
                emit('user_profile', {
                    'success': True,
                    'profile': {
                        'username': profile.username,
                        'email': profile.email,
                        'nickname': profile.preferred_nickname,
                        'ident': profile.preferred_ident,
                        'realname': profile.preferred_realname,
                        'preferred_nickname': profile.preferred_nickname,
                        'preferred_ident': profile.preferred_ident,
                        'preferred_realname': profile.preferred_realname,
                        'auto_join_channels': profile.auto_join_channels,
                        'preferences': profile.preferences
                    }
                })
            else:
                emit('user_profile', {'success': False, 'message': 'Brak profilu użytkownika'})
                
        except Exception as e:
            logger.error(f"Błąd pobierania profilu: {e}")
            emit('error', {'message': f'Błąd pobierania profilu: {str(e)}'})
    
    @socketio.on('get_connection_status')
    def handle_get_connection_status(data):
        """Zwraca status konkretnego połączenia"""
        try:
            connection_id = data.get('connection_id')
            if not connection_id:
                emit('error', {'message': 'Brak connection_id'})
                return
            
            status = irc_manager.get_connection_status(connection_id)
            if status:
                emit('connection_status', {
                    'connection_id': connection_id,
                    'status': status
                })
            else:
                emit('error', {'message': 'Połączenie nie znalezione'})
                
        except Exception as e:
            logger.error(f"Błąd pobierania statusu połączenia: {e}")
            emit('error', {'message': f'Błąd pobierania statusu: {str(e)}'})
    
    return socketio
