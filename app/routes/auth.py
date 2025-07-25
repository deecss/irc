from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
import re
import hashlib
import secrets

def hash_password(password: str) -> str:
    """Hashuje hasło z solą"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{password_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Weryfikuje hasło"""
    try:
        salt, password_hash = stored_hash.split(':')
        computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return computed_hash == password_hash
    except:
        return False

auth_bp = Blueprint('auth', __name__)

def validate_nickname(nickname):
    """Waliduje nickname IRC"""
    if not nickname or len(nickname) < 1 or len(nickname) > 30:
        return False, "Nickname musi mieć od 1 do 30 znaków"
    
    # IRC nickname może zawierać litery, cyfry, [], {}, \, |, ^, _, -
    if not re.match(r'^[a-zA-Z\[\]{}\\|^_-][a-zA-Z0-9\[\]{}\\|^_-]*$', nickname):
        return False, "Nickname zawiera niedozwolone znaki"
    
    return True, ""

def validate_ident(ident):
    """Waliduje ident IRC"""
    if not ident or len(ident) < 1 or len(ident) > 10:
        return False, "Ident musi mieć od 1 do 10 znaków"
    
    # Ident może zawierać litery, cyfry, _, -
    if not re.match(r'^[a-zA-Z0-9_-]+$', ident):
        return False, "Ident może zawierać tylko litery, cyfry, _ i -"
    
    return True, ""

def validate_realname(realname):
    """Waliduje realname IRC"""
    if not realname or len(realname) < 1 or len(realname) > 50:
        return False, "Nazwa rzeczywista musi mieć od 1 do 50 znaków"
    
    return True, ""

@auth_bp.route('/register')
def register_form():
    """Formularz rejestracji użytkownika"""
    return render_template('auth/register.html')

@auth_bp.route('/login')
def login_form():
    """Formularz logowania użytkownika"""
    return render_template('auth/login_simple.html')

@auth_bp.route('/profile')
def profile():
    """Profil użytkownika"""
    return render_template('auth/profile.html')

@auth_bp.route('/api/validate_credentials', methods=['POST'])
def validate_credentials():
    """Waliduje dane logowania IRC"""
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'Brak danych'
        }), 400
    
    errors = {}
    
    # Walidacja nickname
    nickname = data.get('nickname', '').strip()
    valid, message = validate_nickname(nickname)
    if not valid:
        errors['nickname'] = message
    
    # Walidacja ident
    ident = data.get('ident', '').strip()
    valid, message = validate_ident(ident)
    if not valid:
        errors['ident'] = message
    
    # Walidacja realname
    realname = data.get('realname', '').strip()
    valid, message = validate_realname(realname)
    if not valid:
        errors['realname'] = message
    
    # Walidacja email (opcjonalne)
    email = data.get('email', '').strip()
    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        errors['email'] = "Nieprawidłowy format email"
    
    if errors:
        return jsonify({
            'success': False,
            'errors': errors
        }), 400
    
    return jsonify({
        'success': True,
        'message': 'Dane są prawidłowe',
        'validated_data': {
            'nickname': nickname,
            'ident': ident,
            'realname': realname,
            'email': email
        }
    })

@auth_bp.route('/api/check_nickname', methods=['POST'])
def check_nickname():
    """Sprawdza dostępność nickname"""
    data = request.get_json()
    nickname = data.get('nickname', '').strip()
    
    valid, message = validate_nickname(nickname)
    
    if not valid:
        return jsonify({
            'valid': False,
            'message': message
        })
    
    # TODO: Sprawdź w bazie danych czy nickname nie jest zajęty
    # Na razie tylko walidacja formatu
    
    return jsonify({
        'valid': True,
        'available': True,
        'message': 'Nickname jest dostępny'
    })

@auth_bp.route('/api/suggest_ident', methods=['POST'])
def suggest_ident():
    """Sugeruje ident na podstawie nickname"""
    data = request.get_json()
    nickname = data.get('nickname', '').strip()
    
    if not nickname:
        return jsonify({
            'success': False,
            'message': 'Brak nickname'
        })
    
    # Generuj ident na podstawie nickname
    # Usuń niedozwolone znaki i skróć do 10 znaków
    ident = re.sub(r'[^a-zA-Z0-9_-]', '', nickname.lower())[:10]
    
    # Jeśli ident jest pusty, użyj domyślnego
    if not ident:
        ident = 'user'
    
    return jsonify({
        'success': True,
        'suggested_ident': ident
    })

@auth_bp.route('/api/get_default_profile')
def get_default_profile():
    """Zwraca domyślny profil użytkownika"""
    return jsonify({
        'success': True,
        'profile': {
            'username': '',
            'email': '',
            'nickname': '',
            'ident': '',
            'realname': '',
            'auto_join_channels': ['#lobby', '#help'],
            'preferences': {
                'theme': 'dark',
                'notifications': True,
                'sound_notifications': False,
                'timestamp_format': 'HH:MM:SS',
                'font_size': 'medium',
                'auto_reconnect': True,
                'highlight_keywords': []
            }
        }
    })

@auth_bp.route('/api/login', methods=['POST'])
def login_user():
    """Loguje użytkownika po nazwie użytkownika i haśle"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({
            'success': False,
            'message': 'Nazwa użytkownika i hasło są wymagane'
        }), 400
    
    username = data['username'].strip()
    password = data['password']
    
    # Import tutaj aby uniknąć circular imports
    from app.services.database import db
    
    user_data = db.get_user_by_username(username)
    
    if not user_data:
        return jsonify({
            'success': False,
            'message': 'Nieprawidłowa nazwa użytkownika lub hasło'
        }), 401
    
    # Weryfikuj hasło
    if not verify_password(password, user_data['password_hash']):
        return jsonify({
            'success': False,
            'message': 'Nieprawidłowa nazwa użytkownika lub hasło'
        }), 401
    
    return jsonify({
        'success': True,
        'message': 'Zalogowano pomyślnie',
        'user': {
            'username': user_data['username'],
            'email': user_data['email'],
            'preferred_nickname': user_data['preferred_nickname'],
            'preferred_ident': user_data['preferred_ident'],
            'preferred_realname': user_data['preferred_realname']
        }
    })

@auth_bp.route('/api/check_user_exists', methods=['POST'])
def check_user_exists():
    """Sprawdza czy użytkownik istnieje"""
    data = request.get_json()
    
    if not data or not data.get('username'):
        return jsonify({
            'success': False,
            'message': 'Nazwa użytkownika jest wymagana'
        }), 400
    
    username = data['username'].strip()
    
    # Import tutaj aby uniknąć circular imports
    from app.services.database import db
    
    user_data = db.get_user_by_username(username)
    
    return jsonify({
        'exists': user_data is not None,
        'username': username
    })

@auth_bp.route('/servers')
def servers_page():
    """Strona zarządzania serwerami IRC"""
    return render_template('auth/servers.html')
