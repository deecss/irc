from typing import Dict, List, Optional, Callable
import threading
import logging
from datetime import datetime
from app.models import IRCServer, UserProfile, IRCConnection
from app.services.irc_client import IRCClient
from app.services.database import db

logger = logging.getLogger(__name__)

class IRCConnectionManager:
    """Menedżer połączeń IRC dla wielu serwerów z persistent storage"""
    
    def __init__(self, socketio_callback: Callable = None):
        self.connections: Dict[str, IRCClient] = {}
        self.session_users: Dict[str, int] = {}  # session_id -> user_id mapping
        self.user_sessions: Dict[int, str] = {}  # user_id -> session_id mapping
        self.socketio_callback = socketio_callback
        self.lock = threading.Lock()
        
        # Cleanup old connections on startup
        db.cleanup_old_connections()
    
    def register_user_session(self, session_id: str, username: str) -> Optional[UserProfile]:
        """Rejestruje sesję użytkownika i zwraca jego profil"""
        with self.lock:
            # Pobierz użytkownika z bazy danych
            user_data = db.get_user_by_username(username)
            if not user_data:
                return None
            
            user_id = user_data['id']
            
            # Aktualizuj mapowania sesji
            self.session_users[session_id] = user_id
            self.user_sessions[user_id] = session_id
            
            # Aktualizuj session_id w bazie
            db.update_session_id(username, session_id)
            
            # Utwórz obiekt UserProfile
            auto_join_channels = []
            preferences = {}
            
            if user_data['auto_join_channels']:
                import json
                auto_join_channels = json.loads(user_data['auto_join_channels'])
            
            if user_data['preferences']:
                import json
                preferences = json.loads(user_data['preferences'])
            
            profile = UserProfile(
                username=user_data['username'],
                email=user_data['email'] or '',
                preferred_nickname=user_data['preferred_nickname'],
                preferred_ident=user_data['preferred_ident'],
                preferred_realname=user_data['preferred_realname'],
                servers=[],  # Będą załadowane przy połączeniu
                auto_join_channels=auto_join_channels,
                preferences=preferences
            )
            
            logger.info(f"Zarejestrowano sesję {session_id} dla użytkownika {username}")
            return profile
    
    def get_user_profile_by_session(self, session_id: str) -> Optional[UserProfile]:
        """Pobiera profil użytkownika na podstawie session_id"""
        with self.lock:
            if session_id not in self.session_users:
                # Spróbuj załadować z bazy danych
                user_data = db.get_user_by_session(session_id)
                if user_data:
                    return self.register_user_session(session_id, user_data['username'])
                return None
            
            user_id = self.session_users[session_id]
            user_data = db.get_user_by_username(
                next((k for k, v in self.user_sessions.items() if v == session_id), None)
            )
            
            if not user_data:
                return None
            
            import json
            auto_join_channels = []
            preferences = {}
            
            if user_data['auto_join_channels']:
                auto_join_channels = json.loads(user_data['auto_join_channels'])
            
            if user_data['preferences']:
                preferences = json.loads(user_data['preferences'])
            
            return UserProfile(
                username=user_data['username'],
                email=user_data['email'] or '',
                preferred_nickname=user_data['preferred_nickname'],
                preferred_ident=user_data['preferred_ident'],
                preferred_realname=user_data['preferred_realname'],
                servers=[],
                auto_join_channels=auto_join_channels,
                preferences=preferences
            )
    
    def save_user_profile(self, profile: UserProfile, session_id: str) -> int:
        """Zapisuje profil użytkownika do bazy danych"""
        user_id = db.save_user_profile(profile, session_id)
        
        with self.lock:
            self.session_users[session_id] = user_id
            self.user_sessions[user_id] = session_id
        
        logger.info(f"Zapisano profil użytkownika {profile.username}")
        return user_id
    
    def add_user_profile(self, session_id: str, profile: UserProfile):
        """Dodaje profil użytkownika (kompatybilność wsteczna)"""
        self.save_user_profile(profile, session_id)
    
    def remove_user_profile(self, session_id: str):
        """Usuwa sesję użytkownika ale NIE rozłącza połączeń IRC (persistent connections)"""
        with self.lock:
            if session_id in self.session_users:
                user_id = self.session_users[session_id]
                
                # Usuń mapowania sesji
                del self.session_users[session_id]
                if user_id in self.user_sessions:
                    del self.user_sessions[user_id]
                
                # Oznacz połączenia jako nieaktywne w pamięci, ale NIE rozłączaj
                # Połączenia IRC będą kontynuowane w tle
                connections_to_keep = []
                for conn_id, client in self.connections.items():
                    if conn_id.startswith(f"{session_id}_"):
                        # Aktualizuj status w bazie danych
                        db.update_connection_status(conn_id, True)  # Nadal połączone
                        connections_to_keep.append(conn_id)
                
                logger.info(f"Usunięto sesję {session_id}, zachowano {len(connections_to_keep)} połączeń IRC")
    
    def reconnect_user_connections(self, session_id: str) -> List[str]:
        """Przywraca połączenia IRC użytkownika po ponownym zalogowaniu"""
        with self.lock:
            if session_id not in self.session_users:
                return []
            
            user_id = self.session_users[session_id]
            active_connections = db.get_user_connections(user_id)
            
            reconnected = []
            for conn_data in active_connections:
                connection_id = conn_data['connection_id']
                
                # Sprawdź czy połączenie nadal istnieje w pamięci
                if connection_id in self.connections:
                    client = self.connections[connection_id]
                    if client.is_connected:
                        reconnected.append(connection_id)
                        logger.info(f"Przywrócono połączenie {connection_id}")
            
            return reconnected
    
    def connect_to_server(self, session_id: str, server: IRCServer) -> str:
        """Łączy z serwerem IRC"""
        profile = self.get_user_profile_by_session(session_id)
        if not profile:
            raise ValueError("Brak profilu użytkownika")
        
        user_id = self.session_users.get(session_id)
        if not user_id:
            raise ValueError("Nie można określić użytkownika")
        
        connection_id = f"{session_id}_{server.name}_{datetime.now().timestamp()}"
        
        # Callback dla wiadomości IRC
        def message_callback(event_type: str, target: str, data):
            if self.socketio_callback:
                # Sprawdź czy użytkownik ma aktywną sesję
                current_session = self.user_sessions.get(user_id)
                if current_session:
                    self.socketio_callback(current_session, event_type, target, data)
        
        # Utwórz klienta IRC
        client = IRCClient(server, profile, message_callback)
        
        # Spróbuj połączyć
        if client.connect():
            with self.lock:
                self.connections[connection_id] = client
            
            # Zapisz połączenie do bazy danych
            # Znajdź server_id (lub utwórz nowy serwer jeśli nie istnieje)
            servers = db.get_user_servers(user_id)
            server_id = None
            
            for srv in servers:
                if (srv['host'] == server.host and srv['port'] == server.port and 
                    srv['ssl'] == server.ssl):
                    server_id = srv['id']
                    break
            
            if server_id is None:
                # Utwórz nowy serwer
                server_id = db.save_user_server(user_id, server)
            
            # Zapisz aktywne połączenie
            db.save_active_connection(user_id, server_id, connection_id, profile.preferred_nickname)
            
            logger.info(f"Połączono z serwerem {server.name} dla sesji {session_id}")
            return connection_id
        else:
            raise ConnectionError(f"Nie udało się połączyć z serwerem {server.name}")
    
    def disconnect_from_server(self, connection_id: str):
        """Rozłącza z serwerem IRC"""
        with self.lock:
            if connection_id in self.connections:
                client = self.connections[connection_id]
                client.disconnect()
                del self.connections[connection_id]
                
                # Aktualizuj status w bazie danych
                db.update_connection_status(connection_id, False)
                
                logger.info(f"Rozłączono połączenie {connection_id}")
    
    def get_user_servers(self, session_id: str) -> List[Dict]:
        """Pobiera listę serwerów użytkownika z bazy danych"""
        user_id = self.session_users.get(session_id)
        if not user_id:
            return []
        
        return db.get_user_servers(user_id)
    
    def save_user_server(self, session_id: str, server: IRCServer, auto_connect: bool = False) -> int:
        """Zapisuje nowy serwer użytkownika"""
        user_id = self.session_users.get(session_id)
        if not user_id:
            raise ValueError("Brak aktywnej sesji użytkownika")
        
        return db.save_user_server(user_id, server, auto_connect)
    
    def update_user_server(self, session_id: str, server_id: int, server: IRCServer, auto_connect: bool = None):
        """Aktualizuje serwer użytkownika"""
        user_id = self.session_users.get(session_id)
        if not user_id:
            raise ValueError("Brak aktywnej sesji użytkownika")
        
        # Sprawdź czy serwer należy do użytkownika
        user_servers = db.get_user_servers(user_id)
        if not any(srv['id'] == server_id for srv in user_servers):
            raise ValueError("Serwer nie należy do użytkownika")
        
        db.update_user_server(server_id, server, auto_connect)
    
    def delete_user_server(self, session_id: str, server_id: int):
        """Usuwa serwer użytkownika"""
        user_id = self.session_users.get(session_id)
        if not user_id:
            raise ValueError("Brak aktywnej sesji użytkownika")
        
        # Sprawdź czy serwer należy do użytkownika
        user_servers = db.get_user_servers(user_id)
        if not any(srv['id'] == server_id for srv in user_servers):
            raise ValueError("Serwer nie należy do użytkownika")
        
        db.delete_user_server(server_id)
    
    def get_client(self, connection_id: str) -> Optional[IRCClient]:
        """Zwraca klienta IRC dla danego połączenia"""
        return self.connections.get(connection_id)
    
    def get_user_connections(self, session_id: str) -> List[str]:
        """Zwraca listę połączeń dla użytkownika"""
        connections = []
        for conn_id in self.connections.keys():
            if conn_id.startswith(session_id):
                connections.append(conn_id)
        return connections
    
    def send_message(self, connection_id: str, target: str, message: str) -> bool:
        """Wysyła wiadomość przez określone połączenie"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.send_message(target, message)
            return True
        return False
    
    def send_action(self, connection_id: str, target: str, action: str) -> bool:
        """Wysyła akcję (/me) przez określone połączenie"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.send_action(target, action)
            return True
        return False
    
    def join_channel(self, connection_id: str, channel: str, key: str = None) -> bool:
        """Dołącza do kanału"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.join_channel(channel, key)
            return True
        return False
    
    def part_channel(self, connection_id: str, channel: str, reason: str = None) -> bool:
        """Opuszcza kanał"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.part_channel(channel, reason)
            return True
        return False
    
    def change_nick(self, connection_id: str, new_nick: str) -> bool:
        """Zmienia nick"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.change_nick(new_nick)
            return True
        return False
    
    def set_topic(self, connection_id: str, channel: str, topic: str) -> bool:
        """Ustawia temat kanału"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.set_topic(channel, topic)
            return True
        return False
    
    def kick_user(self, connection_id: str, channel: str, nick: str, reason: str = None) -> bool:
        """Wyrzuca użytkownika z kanału"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.kick_user(channel, nick, reason)
            return True
        return False
    
    def set_mode(self, connection_id: str, target: str, modes: str, params: str = None) -> bool:
        """Ustawia tryby"""
        client = self.get_client(connection_id)
        if client and client.is_connected:
            client.set_mode(target, modes, params)
            return True
        return False
    
    def get_connection_status(self, connection_id: str) -> Optional[Dict]:
        """Zwraca status połączenia"""
        client = self.get_client(connection_id)
        if client:
            return client.get_connection_status()
        return None
    
    def get_all_connections_status(self, session_id: str) -> List[Dict]:
        """Zwraca status wszystkich połączeń użytkownika"""
        user_id = self.session_users.get(session_id)
        if not user_id:
            return []
        
        # Pobierz z bazy danych i połącz z aktywnymi połączeniami w pamięci
        db_connections = db.get_user_connections(user_id)
        status_list = []
        
        for conn in db_connections:
            connection_id = conn['connection_id']
            status = {
                'connection_id': connection_id,
                'server': conn['server_name'],
                'host': conn['host'],
                'port': conn['port'],
                'ssl': bool(conn['ssl']),
                'ipv6': bool(conn['ipv6']),
                'nickname': conn['current_nickname'],
                'channels': conn.get('channels', []),
                'connected_at': conn['connected_at'],
                'connected': False
            }
            
            # Sprawdź czy połączenie jest aktywne w pamięci
            if connection_id in self.connections:
                client = self.connections[connection_id]
                status['connected'] = client.is_connected
                if hasattr(client, 'get_connection_status'):
                    client_status = client.get_connection_status()
                    if client_status:
                        status.update(client_status)
            
            status_list.append(status)
        
        return status_list

# Globalna instancja menedżera
irc_manager = IRCConnectionManager()
