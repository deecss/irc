"""
System zarządzania bazą danych dla aplikacji IRC
Wzorowany na The Lounge - persistent storage dla użytkowników i sesji IRC
"""

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from app.models import UserProfile, IRCServer

logger = logging.getLogger(__name__)

class IRCDatabase:
    """Klasa zarządzająca bazą danych dla aplikacji IRC"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Utwórz folder data jeśli nie istnieje
            data_dir = Path(__file__).parent.parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "irc_app.db"
        
        self.db_path = str(db_path)
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Inicjalizuje bazę danych z tabelami"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Tabela użytkowników
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    preferred_nickname TEXT NOT NULL,
                    preferred_ident TEXT NOT NULL,
                    preferred_realname TEXT NOT NULL,
                    auto_join_channels TEXT,  -- JSON array
                    preferences TEXT,  -- JSON object
                    session_id TEXT,  -- Ostatni session ID
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Tabela serwerów IRC użytkownika
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    ssl BOOLEAN DEFAULT 0,
                    ipv6 BOOLEAN DEFAULT 0,
                    encoding TEXT DEFAULT 'utf-8',
                    password TEXT,
                    auto_connect BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # Tabela aktywnych połączeń IRC
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    server_id INTEGER NOT NULL,
                    connection_id TEXT UNIQUE NOT NULL,
                    current_nickname TEXT NOT NULL,
                    is_connected BOOLEAN DEFAULT 0,
                    connected_at TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    channels TEXT,  -- JSON array of joined channels
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (server_id) REFERENCES user_servers (id)
                )
            ''')
            
            # Tabela konfiguracji aplikacji
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Baza danych została zainicjalizowana")
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Pobiera użytkownika po nazwie użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM users WHERE username = ? AND is_active = 1
            ''', (username,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
    
    def get_user_by_session(self, session_id: str) -> Optional[Dict]:
        """Pobiera użytkownika po session ID"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM users WHERE session_id = ? AND is_active = 1
            ''', (session_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
    
    def save_user_profile(self, profile: UserProfile, session_id: str = None) -> int:
        """Zapisuje lub aktualizuje profil użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            auto_join_channels = json.dumps(profile.auto_join_channels)
            preferences = json.dumps(profile.preferences)
            
            # Sprawdź czy użytkownik już istnieje
            cursor.execute('SELECT id FROM users WHERE username = ?', (profile.username,))
            existing = cursor.fetchone()
            
            if existing:
                # Aktualizuj istniejący profil
                cursor.execute('''
                    UPDATE users SET 
                        email = ?, preferred_nickname = ?, preferred_ident = ?,
                        preferred_realname = ?, auto_join_channels = ?, preferences = ?,
                        session_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE username = ?
                ''', (
                    profile.email, profile.preferred_nickname, profile.preferred_ident,
                    profile.preferred_realname, auto_join_channels, preferences,
                    session_id, profile.username
                ))
                user_id = existing[0]
            else:
                # Utwórz nowy profil
                cursor.execute('''
                    INSERT INTO users (
                        username, email, preferred_nickname, preferred_ident,
                        preferred_realname, auto_join_channels, preferences, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile.username, profile.email, profile.preferred_nickname,
                    profile.preferred_ident, profile.preferred_realname,
                    auto_join_channels, preferences, session_id
                ))
                user_id = cursor.lastrowid
            
            conn.commit()
            conn.close()
            logger.info(f"Zapisano profil użytkownika {profile.username} (ID: {user_id})")
            return user_id
    
    def get_user_servers(self, user_id: int) -> List[Dict]:
        """Pobiera listę serwerów użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM user_servers 
                WHERE user_id = ? AND is_active = 1
                ORDER BY name
            ''', (user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
    
    def save_user_server(self, user_id: int, server: IRCServer, auto_connect: bool = False) -> int:
        """Zapisuje serwer IRC użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_servers (
                    user_id, name, host, port, ssl, ipv6, encoding, auto_connect
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, server.name, server.host, server.port,
                server.ssl, server.ipv6, server.encoding, auto_connect
            ))
            
            server_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Zapisano serwer {server.name} dla użytkownika {user_id}")
            return server_id
    
    def update_user_server(self, server_id: int, server: IRCServer, auto_connect: bool = None):
        """Aktualizuje serwer IRC użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if auto_connect is not None:
                cursor.execute('''
                    UPDATE user_servers SET 
                        name = ?, host = ?, port = ?, ssl = ?, ipv6 = ?, 
                        encoding = ?, auto_connect = ?
                    WHERE id = ?
                ''', (
                    server.name, server.host, server.port, server.ssl,
                    server.ipv6, server.encoding, auto_connect, server_id
                ))
            else:
                cursor.execute('''
                    UPDATE user_servers SET 
                        name = ?, host = ?, port = ?, ssl = ?, ipv6 = ?, encoding = ?
                    WHERE id = ?
                ''', (
                    server.name, server.host, server.port, server.ssl,
                    server.ipv6, server.encoding, server_id
                ))
            
            conn.commit()
            conn.close()
    
    def delete_user_server(self, server_id: int):
        """Usuwa serwer IRC użytkownika (soft delete)"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('UPDATE user_servers SET is_active = 0 WHERE id = ?', (server_id,))
            conn.commit()
            conn.close()
    
    def save_active_connection(self, user_id: int, server_id: int, connection_id: str, 
                              nickname: str, channels: List[str] = None):
        """Zapisuje aktywne połączenie IRC"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            channels_json = json.dumps(channels or [])
            
            cursor.execute('''
                INSERT OR REPLACE INTO active_connections (
                    user_id, server_id, connection_id, current_nickname, 
                    is_connected, connected_at, channels
                ) VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
            ''', (user_id, server_id, connection_id, nickname, channels_json))
            
            conn.commit()
            conn.close()
    
    def update_connection_status(self, connection_id: str, is_connected: bool, 
                               channels: List[str] = None):
        """Aktualizuje status połączenia IRC"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if channels is not None:
                channels_json = json.dumps(channels)
                cursor.execute('''
                    UPDATE active_connections SET 
                        is_connected = ?, last_activity = CURRENT_TIMESTAMP, channels = ?
                    WHERE connection_id = ?
                ''', (is_connected, channels_json, connection_id))
            else:
                cursor.execute('''
                    UPDATE active_connections SET 
                        is_connected = ?, last_activity = CURRENT_TIMESTAMP
                    WHERE connection_id = ?
                ''', (is_connected, connection_id))
            
            conn.commit()
            conn.close()
    
    def get_user_connections(self, user_id: int) -> List[Dict]:
        """Pobiera aktywne połączenia użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ac.*, us.name as server_name, us.host, us.port, us.ssl, us.ipv6
                FROM active_connections ac
                JOIN user_servers us ON ac.server_id = us.id
                WHERE ac.user_id = ? AND ac.is_connected = 1
                ORDER BY ac.connected_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            connections = []
            for row in rows:
                conn_dict = dict(row)
                if conn_dict['channels']:
                    conn_dict['channels'] = json.loads(conn_dict['channels'])
                else:
                    conn_dict['channels'] = []
                connections.append(conn_dict)
            
            return connections
    
    def cleanup_old_connections(self, max_age_hours: int = 24):
        """Czyści stare nieaktywne połączenia"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM active_connections 
                WHERE is_connected = 0 
                AND datetime(last_activity) < datetime('now', '-{} hours')
            '''.format(max_age_hours))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logger.info(f"Usunięto {deleted} starych połączeń")
    
    def update_session_id(self, username: str, session_id: str):
        """Aktualizuje session ID użytkownika"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users SET session_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
            ''', (session_id, username))
            
            conn.commit()
            conn.close()

# Globalna instancja bazy danych
db = IRCDatabase()
