from flask import Blueprint, render_template, request, jsonify
from app.services.connection_manager import irc_manager

irc_bp = Blueprint('irc', __name__)

@irc_bp.route('/connect')
def connect_page():
    """Strona łączenia z serwerem IRC"""
    return render_template('irc/connect.html')

@irc_bp.route('/channels')
def channels_page():
    """Strona zarządzania kanałami"""
    return render_template('irc/channels.html')

@irc_bp.route('/users')
def users_page():
    """Strona zarządzania użytkownikami"""
    return render_template('irc/users.html')

@irc_bp.route('/api/server_info', methods=['POST'])
def get_server_info():
    """Zwraca informacje o serwerze IRC"""
    data = request.get_json()
    host = data.get('host')
    port = data.get('port', 6667)
    
    if not host:
        return jsonify({
            'success': False,
            'message': 'Brak hosta serwera'
        }), 400
    
    # TODO: Implementuj sprawdzanie dostępności serwera
    # Na razie zwróć podstawowe informacje
    
    return jsonify({
        'success': True,
        'server_info': {
            'host': host,
            'port': port,
            'available': True,
            'supports_ssl': port in [6697, 6670, 9999],
            'supports_ipv6': True,  # Zakładamy obsługę IPv6
            'network': 'IRCNet',
            'description': f'Serwer IRC {host}'
        }
    })

@irc_bp.route('/api/test_connection', methods=['POST'])
def test_connection():
    """Testuje połączenie z serwerem IRC"""
    data = request.get_json()
    
    host = data.get('host')
    port = data.get('port', 6667)
    ssl = data.get('ssl', False)
    ipv6 = data.get('ipv6', False)
    
    if not host:
        return jsonify({
            'success': False,
            'message': 'Brak hosta serwera'
        }), 400
    
    import socket
    import ssl as ssl_module
    
    try:
        # Wybór rodziny adresów
        family = socket.AF_INET6 if ipv6 else socket.AF_INET
        
        # Test połączenia
        test_socket = socket.socket(family, socket.SOCK_STREAM)
        test_socket.settimeout(10)
        
        if ssl:
            context = ssl_module.create_default_context()
            test_socket = context.wrap_socket(test_socket, server_hostname=host)
        
        test_socket.connect((host, port))
        test_socket.close()
        
        return jsonify({
            'success': True,
            'message': 'Połączenie pomyślne',
            'connection_info': {
                'host': host,
                'port': port,
                'ssl': ssl,
                'ipv6': ipv6,
                'latency': 'OK'
            }
        })
        
    except socket.gaierror:
        return jsonify({
            'success': False,
            'message': 'Nie można rozwiązać nazwy hosta'
        }), 400
        
    except socket.timeout:
        return jsonify({
            'success': False,
            'message': 'Timeout połączenia'
        }), 400
        
    except ConnectionRefusedError:
        return jsonify({
            'success': False,
            'message': 'Połączenie odrzucone'
        }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Błąd połączenia: {str(e)}'
        }), 400

@irc_bp.route('/api/channel_info/<channel_name>')
def get_channel_info(channel_name):
    """Zwraca informacje o kanale"""
    if not channel_name.startswith('#'):
        channel_name = '#' + channel_name
    
    # TODO: Pobierz rzeczywiste informacje o kanale z aktywnych połączeń
    
    return jsonify({
        'success': True,
        'channel_info': {
            'name': channel_name,
            'topic': 'Brak tematu',
            'user_count': 0,
            'modes': '',
            'created': None
        }
    })

@irc_bp.route('/api/commands_help')
def get_commands_help():
    """Zwraca listę dostępnych komend IRC"""
    commands = {
        'basic': {
            '/join <kanał> [klucz]': 'Dołącza do kanału',
            '/part <kanał> [powód]': 'Opuszcza kanał',
            '/quit [powód]': 'Rozłącza z serwerem',
            '/nick <nowy_nick>': 'Zmienia nickname',
            '/msg <cel> <wiadomość>': 'Wysyła prywatną wiadomość',
            '/me <akcja>': 'Wysyła akcję'
        },
        'channel': {
            '/topic <kanał> <temat>': 'Ustawia temat kanału',
            '/kick <kanał> <nick> [powód]': 'Wyrzuca użytkownika z kanału',
            '/ban <kanał> <maska>': 'Banuje użytkownika',
            '/unban <kanał> <maska>': 'Usuwa bana',
            '/mode <cel> <tryby> [parametry]': 'Ustawia tryby',
            '/invite <nick> <kanał>': 'Zaprasza użytkownika na kanał'
        },
        'info': {
            '/who <cel>': 'Pokazuje informacje o użytkownikach',
            '/whois <nick>': 'Pokazuje szczegółowe info o użytkowniku',
            '/list [wzorzec]': 'Lista kanałów',
            '/names <kanał>': 'Lista użytkowników kanału',
            '/time [serwer]': 'Czas serwera',
            '/version [nick]': 'Wersja klienta użytkownika'
        },
        'operator': {
            '/oper <login> <hasło>': 'Logowanie jako operator',
            '/kill <nick> <powód>': 'Rozłącza użytkownika',
            '/kline <maska> <powód>': 'Banuje na poziomie serwera',
            '/rehash': 'Przeładowuje konfigurację serwera'
        }
    }
    
    return jsonify({
        'success': True,
        'commands': commands
    })
