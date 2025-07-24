from dataclasses import dataclass
from typing import Optional, Dict, List, Set
from datetime import datetime
import json

@dataclass
class IRCUser:
    """Klasa reprezentująca użytkownika IRC"""
    nickname: str
    ident: str
    realname: str
    hostname: str
    server: str
    channels: Set[str]
    is_operator: bool = False
    is_voice: bool = False
    away_message: Optional[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if isinstance(self.channels, list):
            self.channels = set(self.channels)

@dataclass
class IRCChannel:
    """Klasa reprezentująca kanał IRC"""
    name: str
    topic: str = ""
    modes: Dict[str, bool] = None
    users: Set[str] = None
    operators: Set[str] = None
    voiced: Set[str] = None
    banned: Set[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.modes is None:
            self.modes = {}
        if self.users is None:
            self.users = set()
        if self.operators is None:
            self.operators = set()
        if self.voiced is None:
            self.voiced = set()
        if self.banned is None:
            self.banned = set()

@dataclass
class IRCMessage:
    """Klasa reprezentująca wiadomość IRC"""
    timestamp: datetime
    sender: str
    target: str  # kanał lub użytkownik
    content: str
    message_type: str = "PRIVMSG"  # PRIVMSG, NOTICE, ACTION, JOIN, PART, QUIT, etc.
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'sender': self.sender,
            'target': self.target,
            'content': self.content,
            'type': self.message_type
        }

@dataclass
class IRCServer:
    """Klasa reprezentująca serwer IRC"""
    name: str
    host: str
    port: int
    ssl: bool = False
    ipv6: bool = False
    encoding: str = "utf-8"
    
    def get_address(self):
        return f"{self.host}:{self.port}"

@dataclass
class UserProfile:
    """Profil użytkownika aplikacji"""
    username: str
    email: str
    preferred_nickname: str
    preferred_ident: str
    preferred_realname: str
    servers: List[IRCServer]
    auto_join_channels: List[str]
    preferences: Dict
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if not self.preferences:
            self.preferences = {
                'theme': 'dark',
                'notifications': True,
                'sound_notifications': False,
                'timestamp_format': 'HH:MM:SS',
                'font_size': 'medium',
                'auto_reconnect': True,
                'highlight_keywords': []
            }

class IRCConnection:
    """Klasa zarządzająca połączeniem IRC"""
    def __init__(self, server: IRCServer, user_profile: UserProfile):
        self.server = server
        self.user_profile = user_profile
        self.is_connected = False
        self.current_nickname = user_profile.preferred_nickname
        self.channels = {}
        self.users = {}
        self.connection_start = None
        self.last_ping = None
        
    def get_connection_info(self):
        return {
            'server': self.server.name,
            'host': self.server.host,
            'port': self.server.port,
            'ssl': self.server.ssl,
            'ipv6': self.server.ipv6,
            'nickname': self.current_nickname,
            'connected': self.is_connected,
            'channels': list(self.channels.keys())
        }
