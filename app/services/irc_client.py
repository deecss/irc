import socket
import ssl
import threading
import time
import re
from typing import Dict, List, Callable, Optional
from datetime import datetime
import logging
from app.models import IRCServer, IRCUser, IRCChannel, IRCMessage, UserProfile, IRCConnection

logger = logging.getLogger(__name__)

class IRCClient:
    """Główna klasa klienta IRC z obsługą IPv6 i SSL"""
    
    def __init__(self, server: IRCServer, user_profile: UserProfile, message_callback: Callable = None):
        self.server = server
        self.user_profile = user_profile
        self.message_callback = message_callback
        self.socket = None
        self.is_connected = False
        self.is_registered = False
        self.current_nickname = user_profile.preferred_nickname
        self.channels = {}
        self.users = {}
        self.receive_thread = None
        self.ping_thread = None
        self.buffer = ""
        
        # Regex patterns for IRC messages
        self.patterns = {
            'ping': re.compile(r'^PING\s+:(.+)$'),
            'privmsg': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+PRIVMSG\s+(.+?)\s+:(.+)$'),
            'notice': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+NOTICE\s+(.+?)\s+:(.+)$'),
            'join': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+JOIN\s+:(.+)$'),
            'part': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+PART\s+(.+?)(?:\s+:(.+))?$'),
            'quit': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+QUIT\s+:(.+)$'),
            'kick': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+KICK\s+(.+?)\s+(.+?)(?:\s+:(.+))?$'),
            'nick': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+NICK\s+:(.+)$'),
            'mode': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+MODE\s+(.+?)\s+(.+)(?:\s+(.+))?$'),
            'topic': re.compile(r'^:(.+?)!(.+?)@(.+?)\s+TOPIC\s+(.+?)\s+:(.+)$'),
            'numeric': re.compile(r'^:(.+?)\s+(\d{3})\s+(.+?)\s+:(.+)$'),
            'names': re.compile(r'^:(.+?)\s+353\s+(.+?)\s+=\s+(.+?)\s+:(.+)$'),
            'endnames': re.compile(r'^:(.+?)\s+366\s+(.+?)\s+(.+?)\s+:(.+)$')
        }
    
    def connect(self) -> bool:
        """Nawiązuje połączenie z serwerem IRC"""
        try:
            # Wybór rodziny adresów (IPv4/IPv6)
            family = socket.AF_INET6 if self.server.ipv6 else socket.AF_INET
            
            # Utworzenie socketu
            self.socket = socket.socket(family, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            
            # Włączenie SSL jeśli wymagane
            if self.server.ssl:
                context = ssl.create_default_context()
                self.socket = context.wrap_socket(self.socket, server_hostname=self.server.host)
            
            # Połączenie z serwerem
            logger.info(f"Łączenie z {self.server.host}:{self.server.port} (IPv6: {self.server.ipv6}, SSL: {self.server.ssl})")
            self.socket.connect((self.server.host, self.server.port))
            
            self.is_connected = True
            
            # Rozpoczęcie rejestracji
            self._register()
            
            # Uruchomienie wątku odbierania wiadomości
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            # Uruchomienie wątku ping
            self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self.ping_thread.start()
            
            logger.info("Pomyślnie połączono z serwerem IRC")
            return True
            
        except Exception as e:
            logger.error(f"Błąd połączenia z serwerem IRC: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Rozłącza z serwerem IRC"""
        if self.is_connected:
            self._send_raw("QUIT :Rozłączanie...")
            time.sleep(1)
            
        if self.socket:
            self.socket.close()
            
        self.is_connected = False
        self.is_registered = False
        
        logger.info("Rozłączono z serwerem IRC")
    
    def _register(self):
        """Rejestruje użytkownika na serwerze"""
        ident = self.user_profile.preferred_ident
        realname = self.user_profile.preferred_realname
        
        self._send_raw(f"USER {ident} 0 * :{realname}")
        self._send_raw(f"NICK {self.current_nickname}")
    
    def _send_raw(self, message: str):
        """Wysyła surową wiadomość do serwera"""
        if not self.is_connected or not self.socket:
            return False
            
        try:
            encoded_message = (message + '\r\n').encode(self.server.encoding)
            self.socket.send(encoded_message)
            logger.debug(f">> {message}")
            return True
        except Exception as e:
            logger.error(f"Błąd wysyłania wiadomości: {e}")
            return False
    
    def _receive_loop(self):
        """Główna pętla odbierania wiadomości"""
        while self.is_connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                    
                # Dekodowanie i dodanie do bufora
                decoded_data = data.decode(self.server.encoding, errors='ignore')
                self.buffer += decoded_data
                
                # Przetwarzanie kompletnych linii
                while '\r\n' in self.buffer:
                    line, self.buffer = self.buffer.split('\r\n', 1)
                    if line:
                        self._process_message(line)
                        
            except Exception as e:
                logger.error(f"Błąd odbierania danych: {e}")
                break
        
        self.is_connected = False
    
    def _ping_loop(self):
        """Pętla wysyłania PING do serwera"""
        while self.is_connected:
            time.sleep(60)  # PING co minutę
            if self.is_connected:
                self._send_raw(f"PING :{self.server.host}")
    
    def _process_message(self, line: str):
        """Przetwarza otrzymaną wiadomość IRC"""
        logger.debug(f"<< {line}")
        
        # PING/PONG
        ping_match = self.patterns['ping'].match(line)
        if ping_match:
            self._send_raw(f"PONG :{ping_match.group(1)}")
            return
        
        # Wiadomości numeryczne (kody odpowiedzi serwera)
        numeric_match = self.patterns['numeric'].match(line)
        if numeric_match:
            code = int(numeric_match.group(2))
            self._handle_numeric_response(code, line)
            return
        
        # PRIVMSG
        privmsg_match = self.patterns['privmsg'].match(line)
        if privmsg_match:
            self._handle_privmsg(privmsg_match)
            return
        
        # NOTICE
        notice_match = self.patterns['notice'].match(line)
        if notice_match:
            self._handle_notice(notice_match)
            return
        
        # JOIN
        join_match = self.patterns['join'].match(line)
        if join_match:
            self._handle_join(join_match)
            return
        
        # PART
        part_match = self.patterns['part'].match(line)
        if part_match:
            self._handle_part(part_match)
            return
        
        # QUIT
        quit_match = self.patterns['quit'].match(line)
        if quit_match:
            self._handle_quit(quit_match)
            return
        
        # KICK
        kick_match = self.patterns['kick'].match(line)
        if kick_match:
            self._handle_kick(kick_match)
            return
        
        # NICK
        nick_match = self.patterns['nick'].match(line)
        if nick_match:
            self._handle_nick(nick_match)
            return
        
        # MODE
        mode_match = self.patterns['mode'].match(line)
        if mode_match:
            self._handle_mode(mode_match)
            return
        
        # TOPIC
        topic_match = self.patterns['topic'].match(line)
        if topic_match:
            self._handle_topic(topic_match)
            return
        
        # Lista użytkowników kanału (353)
        names_match = self.patterns['names'].match(line)
        if names_match:
            self._handle_names(names_match)
            return
        
        # Koniec listy użytkowników (366)
        endnames_match = self.patterns['endnames'].match(line)
        if endnames_match:
            self._handle_endnames(endnames_match)
            return
    
    def _handle_numeric_response(self, code: int, line: str):
        """Obsługuje numeryczne odpowiedzi serwera"""
        if code == 1:  # RPL_WELCOME
            self.is_registered = True
            self._emit_message("system", "server", f"Zarejestrowano na serwerze: {line}")
            
            # Auto-join kanałów
            for channel in self.user_profile.auto_join_channels:
                self.join_channel(channel)
                
        elif code == 433:  # ERR_NICKNAMEINUSE
            # Nick zajęty - spróbuj z podkreśleniem
            self.current_nickname += "_"
            self._send_raw(f"NICK {self.current_nickname}")
            
        elif code in [353, 366]:  # Listy użytkowników
            pass  # Obsługiwane przez dedykowane handlery
            
        else:
            self._emit_message("system", "server", line)
    
    def _handle_privmsg(self, match):
        """Obsługuje wiadomości PRIVMSG"""
        sender = match.group(1)
        ident = match.group(2)
        host = match.group(3)
        target = match.group(4)
        content = match.group(5)
        
        # Sprawdź czy to ACTION (/me)
        if content.startswith('\x01ACTION') and content.endswith('\x01'):
            content = content[8:-1]  # Usuń \x01ACTION...\x01
            message_type = "ACTION"
        else:
            message_type = "PRIVMSG"
        
        message = IRCMessage(
            timestamp=datetime.now(),
            sender=sender,
            target=target,
            content=content,
            message_type=message_type
        )
        
        self._emit_message("message", target, message.to_dict())
    
    def _handle_notice(self, match):
        """Obsługuje wiadomości NOTICE"""
        sender = match.group(1)
        target = match.group(4)
        content = match.group(5)
        
        message = IRCMessage(
            timestamp=datetime.now(),
            sender=sender,
            target=target,
            content=content,
            message_type="NOTICE"
        )
        
        self._emit_message("notice", target, message.to_dict())
    
    def _handle_join(self, match):
        """Obsługuje JOIN"""
        nickname = match.group(1)
        channel = match.group(4)
        
        if nickname == self.current_nickname:
            # To my join
            if channel not in self.channels:
                self.channels[channel] = IRCChannel(name=channel)
        else:
            # Ktoś inny dołączył
            if channel in self.channels:
                self.channels[channel].users.add(nickname)
        
        self._emit_message("join", channel, {
            'nickname': nickname,
            'channel': channel,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_part(self, match):
        """Obsługuje PART"""
        nickname = match.group(1)
        channel = match.group(4)
        reason = match.group(5) or ""
        
        if nickname == self.current_nickname:
            # To my part
            if channel in self.channels:
                del self.channels[channel]
        else:
            # Ktoś inny opuścił
            if channel in self.channels:
                self.channels[channel].users.discard(nickname)
        
        self._emit_message("part", channel, {
            'nickname': nickname,
            'channel': channel,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_quit(self, match):
        """Obsługuje QUIT"""
        nickname = match.group(1)
        reason = match.group(4)
        
        # Usuń użytkownika ze wszystkich kanałów
        for channel in self.channels.values():
            channel.users.discard(nickname)
        
        self._emit_message("quit", "server", {
            'nickname': nickname,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_kick(self, match):
        """Obsługuje KICK"""
        kicker = match.group(1)
        channel = match.group(4)
        kicked = match.group(5)
        reason = match.group(6) or ""
        
        if kicked == self.current_nickname:
            # Zostaliśmy wykopani
            if channel in self.channels:
                del self.channels[channel]
        else:
            # Ktoś inny został wykopany
            if channel in self.channels:
                self.channels[channel].users.discard(kicked)
        
        self._emit_message("kick", channel, {
            'kicker': kicker,
            'kicked': kicked,
            'channel': channel,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_nick(self, match):
        """Obsługuje zmianę nicka"""
        old_nick = match.group(1)
        new_nick = match.group(4)
        
        if old_nick == self.current_nickname:
            self.current_nickname = new_nick
        
        # Zaktualizuj nick w kanałach
        for channel in self.channels.values():
            if old_nick in channel.users:
                channel.users.remove(old_nick)
                channel.users.add(new_nick)
            if old_nick in channel.operators:
                channel.operators.remove(old_nick)
                channel.operators.add(new_nick)
            if old_nick in channel.voiced:
                channel.voiced.remove(old_nick)
                channel.voiced.add(new_nick)
        
        self._emit_message("nick", "server", {
            'old_nick': old_nick,
            'new_nick': new_nick,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_mode(self, match):
        """Obsługuje zmiany trybów"""
        setter = match.group(1)
        target = match.group(4)
        modes = match.group(5)
        params = match.group(6) or ""
        
        self._emit_message("mode", target, {
            'setter': setter,
            'target': target,
            'modes': modes,
            'params': params,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_topic(self, match):
        """Obsługuje zmianę tematu"""
        setter = match.group(1)
        channel = match.group(4)
        topic = match.group(5)
        
        if channel in self.channels:
            self.channels[channel].topic = topic
        
        self._emit_message("topic", channel, {
            'setter': setter,
            'channel': channel,
            'topic': topic,
            'timestamp': datetime.now().isoformat()
        })
    
    def _handle_names(self, match):
        """Obsługuje listę użytkowników kanału"""
        channel = match.group(3)
        names = match.group(4).strip().split()
        
        if channel in self.channels:
            for name in names:
                # Sprawdź prefiksy (@, +, etc.)
                if name.startswith('@'):
                    nick = name[1:]
                    self.channels[channel].users.add(nick)
                    self.channels[channel].operators.add(nick)
                elif name.startswith('+'):
                    nick = name[1:]
                    self.channels[channel].users.add(nick)
                    self.channels[channel].voiced.add(nick)
                else:
                    self.channels[channel].users.add(name)
    
    def _handle_endnames(self, match):
        """Obsługuje koniec listy użytkowników"""
        channel = match.group(3)
        
        if channel in self.channels:
            self._emit_message("names", channel, {
                'channel': channel,
                'users': list(self.channels[channel].users),
                'operators': list(self.channels[channel].operators),
                'voiced': list(self.channels[channel].voiced)
            })
    
    def _emit_message(self, event_type: str, target: str, data):
        """Wysyła wiadomość do callback'a"""
        if self.message_callback:
            self.message_callback(event_type, target, data)
    
    # Publiczne metody do wysyłania wiadomości
    
    def send_message(self, target: str, message: str):
        """Wysyła wiadomość prywatną lub na kanał"""
        self._send_raw(f"PRIVMSG {target} :{message}")
        
        # Dodaj do lokalnej historii
        msg = IRCMessage(
            timestamp=datetime.now(),
            sender=self.current_nickname,
            target=target,
            content=message,
            message_type="PRIVMSG"
        )
        self._emit_message("message", target, msg.to_dict())
    
    def send_action(self, target: str, action: str):
        """Wysyła akcję (/me)"""
        self._send_raw(f"PRIVMSG {target} :\x01ACTION {action}\x01")
        
        # Dodaj do lokalnej historii
        msg = IRCMessage(
            timestamp=datetime.now(),
            sender=self.current_nickname,
            target=target,
            content=action,
            message_type="ACTION"
        )
        self._emit_message("message", target, msg.to_dict())
    
    def join_channel(self, channel: str, key: str = None):
        """Dołącza do kanału"""
        if key:
            self._send_raw(f"JOIN {channel} {key}")
        else:
            self._send_raw(f"JOIN {channel}")
    
    def part_channel(self, channel: str, reason: str = None):
        """Opuszcza kanał"""
        if reason:
            self._send_raw(f"PART {channel} :{reason}")
        else:
            self._send_raw(f"PART {channel}")
    
    def change_nick(self, new_nick: str):
        """Zmienia nick"""
        self._send_raw(f"NICK {new_nick}")
    
    def set_topic(self, channel: str, topic: str):
        """Ustawia temat kanału"""
        self._send_raw(f"TOPIC {channel} :{topic}")
    
    def kick_user(self, channel: str, nick: str, reason: str = None):
        """Wyrzuca użytkownika z kanału"""
        if reason:
            self._send_raw(f"KICK {channel} {nick} :{reason}")
        else:
            self._send_raw(f"KICK {channel} {nick}")
    
    def set_mode(self, target: str, modes: str, params: str = None):
        """Ustawia tryby"""
        if params:
            self._send_raw(f"MODE {target} {modes} {params}")
        else:
            self._send_raw(f"MODE {target} {modes}")
    
    def get_connection_status(self):
        """Zwraca status połączenia"""
        return {
            'connected': self.is_connected,
            'registered': self.is_registered,
            'nickname': self.current_nickname,
            'server': self.server.name,
            'channels': list(self.channels.keys())
        }
