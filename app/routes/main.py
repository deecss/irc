from flask import Blueprint, render_template, request, jsonify, session

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Strona główna aplikacji IRC"""
    return render_template('index.html')

@main_bp.route('/chat')
def chat():
    """Interfejs czatu IRC"""
    # Sprawdź czy użytkownik jest zalogowany (podstawowa implementacja)
    # TODO: Dodać właściwą autoryzację sesji
    return render_template('chat.html')

@main_bp.route('/settings')
def settings():
    """Ustawienia aplikacji"""
    return render_template('settings.html')

@main_bp.route('/about')
def about():
    """Informacje o aplikacji"""
    return render_template('about.html')

@main_bp.route('/api/ircnet_servers')
def get_ircnet_servers():
    """Zwraca listę serwerów IRCNet z obsługą IPv6"""
    servers = [
        {
            'name': 'irc.ircnet.com',
            'host': 'irc.ircnet.com',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': True,
            'country': 'Global',
            'description': 'Główny serwer IRCNet'
        },
        {
            'name': 'efnet.port80.se',
            'host': 'efnet.port80.se',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': True,
            'country': 'Sweden',
            'description': 'Serwer szwedzki z obsługą IPv6'
        },
        {
            'name': 'irc.dkom.at',
            'host': 'irc.dkom.at',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': True,
            'country': 'Austria',
            'description': 'Serwer austriacki z obsługą IPv6'
        },
        {
            'name': 'irc.easynet.fr',
            'host': 'irc.easynet.fr',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': False,
            'country': 'France',
            'description': 'Serwer francuski'
        },
        {
            'name': 'irc.ircnet.net',
            'host': 'irc.ircnet.net',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': True,
            'country': 'Global',
            'description': 'Alternatywny serwer globalny'
        },
        {
            'name': 'open.ircnet.net',
            'host': 'open.ircnet.net',
            'port': 6667,
            'ssl_port': 6697,
            'ipv6': True,
            'country': 'Global',
            'description': 'Otwarty serwer IRCNet'
        }
    ]
    
    return jsonify({
        'success': True,
        'servers': servers
    })

@main_bp.route('/api/popular_channels')
def get_popular_channels():
    """Zwraca listę popularnych kanałów IRCNet"""
    channels = [
        {'name': '#lobby', 'description': 'Główny kanał społecznościowy'},
        {'name': '#help', 'description': 'Pomoc dla nowych użytkowników'},
        {'name': '#chat', 'description': 'Ogólny czat'},
        {'name': '#programming', 'description': 'Programowanie i rozwój'},
        {'name': '#linux', 'description': 'Dyskusje o systemie Linux'},
        {'name': '#python', 'description': 'Język programowania Python'},
        {'name': '#javascript', 'description': 'JavaScript i web development'},
        {'name': '#games', 'description': 'Gry komputerowe'},
        {'name': '#music', 'description': 'Muzyka i audio'},
        {'name': '#art', 'description': 'Sztuka i kreatywność'},
        {'name': '#science', 'description': 'Nauka i technologia'},
        {'name': '#books', 'description': 'Literatura i książki'},
        {'name': '#news', 'description': 'Aktualności i wydarzenia'},
        {'name': '#polish', 'description': 'Kanał dla użytkowników polskich'},
        {'name': '#english', 'description': 'English speaking channel'}
    ]
    
    return jsonify({
        'success': True,
        'channels': channels
    })
