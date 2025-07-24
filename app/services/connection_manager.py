from typing import Dict, List, Optional, Callable
import threading
import logging
from datetime import datetime
from app.models import IRCServer, UserProfile, IRCConnection
from app.services.irc_client import IRCClient

logger = logging.getLogger(__name__)

class IRCConnectionManager:
    """Menedżer połączeń IRC dla wielu serwerów"""
    
    def __init__(self, socketio_callback: Callable = None):
        self.connections: Dict[str, IRCClient] = {}
        self.user_profiles: Dict[str, UserProfile] = {}
        self.socketio_callback = socketio_callback
        self.lock = threading.Lock()
    
    def add_user_profile(self, session_id: str, profile: UserProfile):
        """Dodaje profil użytkownika"""
        with self.lock:
            self.user_profiles[session_id] = profile
            logger.info(f"Dodano profil użytkownika dla sesji {session_id}")
    
    def remove_user_profile(self, session_id: str):
        """Usuwa profil użytkownika i rozłącza wszystkie połączenia"""
        with self.lock:
            if session_id in self.user_profiles:
                # Rozłącz wszystkie połączenia użytkownika
                connections_to_remove = []
                for conn_id, client in self.connections.items():
                    if conn_id.startswith(session_id):
                        connections_to_remove.append(conn_id)
                
                for conn_id in connections_to_remove:
                    self.disconnect_from_server(conn_id)
                
                # Usuń profil
                del self.user_profiles[session_id]
                logger.info(f"Usunięto profil użytkownika dla sesji {session_id}")
    
    def connect_to_server(self, session_id: str, server: IRCServer) -> str:
        """Łączy z serwerem IRC"""
        if session_id not in self.user_profiles:
            raise ValueError("Brak profilu użytkownika")
        
        profile = self.user_profiles[session_id]
        connection_id = f"{session_id}_{server.name}_{datetime.now().timestamp()}"
        
        # Callback dla wiadomości IRC
        def message_callback(event_type: str, target: str, data):
            if self.socketio_callback:
                self.socketio_callback(session_id, event_type, target, data)
        
        # Utwórz klienta IRC
        client = IRCClient(server, profile, message_callback)
        
        # Spróbuj połączyć
        if client.connect():
            with self.lock:
                self.connections[connection_id] = client
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
                logger.info(f"Rozłączono połączenie {connection_id}")
    
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
        connections = []
        for conn_id in self.get_user_connections(session_id):
            status = self.get_connection_status(conn_id)
            if status:
                status['connection_id'] = conn_id
                connections.append(status)
        return connections

# Globalna instancja menedżera
irc_manager = IRCConnectionManager()
