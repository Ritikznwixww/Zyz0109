# H_railway.py - COMPLETE FIXED VERSION (NO MARKDOWN ERRORS)
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import threading
import re
import sys
import atexit
import requests

# ====================== FIX WEBHOOK CONFLICT ======================
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8487271564:AAFxXGmmIl73iflDp8EPuNn-5y-AtoH4NhQ')
OWNER_ID = int(os.environ.get('OWNER_ID', 7964730489))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 7964730489))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@XyzR9')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/Xyzr4')

# ====================== WEBHOOK DELETE ======================
print("=" * 50)
print("🔄 Checking and deleting webhook...")
try:
    webhook_url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    response = requests.get(webhook_url)
    print(f"✅ Webhook delete response: {response.json()}")
except Exception as e:
    print(f"⚠️ Error in webhook deletion: {e}")
time.sleep(2)
print("=" * 50)

# ====================== RAILWAY CONFIGURATION ======================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join('/data', 'upload_bots')
IROTECH_DIR = os.path.join('/data', 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True, mode=0o755)
os.makedirs(IROTECH_DIR, exist_ok=True, mode=0o755)

A4F_API_URL = "https://samuraiapi.in/v1/chat/completions"
A4F_API_KEY = "sk-NK6SS9tpWghyFJwkZLoCis1sMaF6RwQ5WF09mUoKKR0VKCm7"
A4F_MODEL = "provider10-claude-sonnet-4-20250514(clinesp)"

BOT_START_TIME = datetime.now()

def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

FREE_USER_LIMIT = 2
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# ====================== INITIALIZE BOT ======================
bot = telebot.TeleBot(TOKEN)
print("✅ Bot initialized successfully!")

bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

# ====================== SAFE MESSAGE FUNCTION (FIX FOR MARKDOWN ERRORS) ======================
def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    """Markdown errors से बचने के लिए safe function"""
    try:
        # पहले बिना parse_mode के भेजो
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        # अगर फिर भी error तो और simple text भेजो
        try:
            simple_text = re.sub(r'[_*[\]()~`>#+\-=|{}.!]', '', text)
            return bot.send_message(chat_id, simple_text[:3000], reply_markup=reply_markup)
        except:
            return None

# ====================== DATABASE FUNCTIONS ======================
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS file_approvals
                     (user_id INTEGER, file_name TEXT, status TEXT, 
                      reviewed_by INTEGER, review_time TEXT, file_type TEXT,
                      uploaded_time TEXT, message_id INTEGER,
                      PRIMARY KEY (user_id, file_name))''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
             c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                pass
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions")
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)

init_db()
load_data()

DB_LOCK = threading.Lock()

def save_file_approval(user_id, file_name, file_type, status=FILE_STATUS_PENDING, reviewed_by=None, message_id=None):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            uploaded_time = datetime.now().isoformat()
            review_time = datetime.now().isoformat() if reviewed_by else None
            c.execute('''INSERT OR REPLACE INTO file_approvals 
                        (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, file_name, file_type, status, reviewed_by, review_time, uploaded_time, message_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving file approval: {e}")
        finally:
            conn.close()

def get_file_status(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''SELECT status, reviewed_by, review_time, file_type 
                        FROM file_approvals WHERE user_id=? AND file_name=?''',
                     (user_id, file_name))
            result = c.fetchone()
            if result:
                return {'status': result[0], 'reviewed_by': result[1], 'review_time': result[2], 'file_type': result[3]}
            return {'status': FILE_STATUS_PENDING, 'file_type': 'zip'}
        except Exception as e:
            logger.error(f"Error getting file status: {e}")
            return {'status': FILE_STATUS_PENDING, 'file_type': 'zip'}
        finally:
            conn.close()

def update_file_status(user_id, file_name, status, admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            review_time = datetime.now().isoformat()
            c.execute('''UPDATE file_approvals 
                        SET status=?, reviewed_by=?, review_time=?
                        WHERE user_id=? AND file_name=?''',
                     (status, admin_id, review_time, user_id, file_name))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating file status: {e}")
            return False
        finally:
            conn.close()

def get_all_pending_files():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('''SELECT user_id, file_name, file_type, uploaded_time 
                        FROM file_approvals WHERE status=? 
                        ORDER BY uploaded_time DESC''', (FILE_STATUS_PENDING,))
            return c.fetchall()
        except Exception as e:
            logger.error(f"Error getting pending files: {e}")
            return []
        finally:
            conn.close()

def get_pending_files_count():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT COUNT(*) FROM file_approvals WHERE status=?', (FILE_STATUS_PENDING,))
            return c.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending files count: {e}")
            return 0
        finally:
            conn.close()

def send_file_for_approval(message, user_id, file_name, file_type):
    user = message.from_user
    file_info = (f"📄 NEW ZIP FILE FOR APPROVAL\n\n"
                 f"👤 User: {user.first_name}\n"
                 f"📛 Username: @{user.username or 'N/A'}\n"
                 f"🆔 User ID: {user_id}\n"
                 f"📁 File: {file_name}\n"
                 f"📊 Type: {file_type}\n"
                 f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                 f"Choose action:")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user_id}_{file_name}'),
        types.InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user_id}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("📋 View All Pending", callback_data='view_pending'))
    
    for admin_id in admin_ids:
        try:
            bot.forward_message(admin_id, message.chat.id, message.message_id)
            sent_msg = safe_send_message(admin_id, file_info, reply_markup=markup)
            if sent_msg:
                save_file_approval(user_id, file_name, file_type, FILE_STATUS_PENDING, None, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Failed to send file for approval to admin {admin_id}: {e}")

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True, mode=0o755)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except:
            return False
    return False

def kill_process_tree(process_info):
    try:
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            try:
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    try: child.terminate()
                    except: pass
                parent.terminate()
            except:
                pass
    except Exception as e:
        logger.error(f"Error killing process: {e}")

# ====================== FIXED INSTALL REQUIREMENTS FUNCTION (NO MARKDOWN) ======================
def install_requirements(requirements_file, message, user_folder):
    """Install Python dependencies from requirements.txt - NO MARKDOWN"""
    try:
        chat_id = message.chat.id
        safe_send_message(chat_id, "Installing Python dependencies from requirements.txt...")
        
        command = [sys.executable, '-m', 'pip', 'install', '-r', requirements_file]
        logger.info(f"Running: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            logger.info(f"Requirements installed. Output:\n{result.stdout}")
            safe_send_message(chat_id, "✅ Python dependencies installed successfully!")
            return True
        else:
            error_msg = f"Failed to install requirements.\nError: {result.stderr or result.stdout[:200]}"
            logger.error(error_msg)
            safe_send_message(chat_id, error_msg[:1000])
            return False
    except Exception as e:
        error_msg = f"Error installing requirements: {str(e)}"
        logger.error(error_msg)
        safe_send_message(message.chat.id, error_msg[:500])
        return False

def install_npm_packages(user_folder, message):
    package_json_path = os.path.join(user_folder, 'package.json')
    if not os.path.exists(package_json_path):
        return True
    
    try:
        safe_send_message(message.chat.id, "Installing Node.js dependencies from package.json...")
        command = ['npm', 'install']
        logger.info(f"Running npm install in {user_folder}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            logger.info(f"npm install completed.")
            safe_send_message(message.chat.id, "✅ Node.js dependencies installed successfully!")
            return True
        else:
            error_msg = f"Failed to install Node.js dependencies.\nError: {result.stderr or result.stdout[:200]}"
            logger.error(error_msg)
            safe_send_message(message.chat.id, error_msg[:500])
            return False
    except FileNotFoundError:
        safe_send_message(message.chat.id, "Warning: 'npm' not found. Cannot install Node.js dependencies.")
        return False
    except Exception as e:
        logger.error(f"Error installing Node.js dependencies: {e}")
        safe_send_message(message.chat.id, f"Error installing Node.js dependencies: {str(e)[:200]}")
        return False

def save_user_file(user_id, file_name, file_type='zip'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except Exception as e:
            logger.error(f"Error saving file: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
        except Exception as e:
            logger.error(f"Error removing file: {e}")
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error adding active user: {e}")
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e:
            logger.error(f"Error saving subscription: {e}")
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
        except Exception as e:
            logger.error(f"Error removing subscription: {e}")
        finally:
            conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            removed = c.rowcount > 0
            if removed: admin_ids.discard(admin_id)
            return removed
        except Exception as e:
            logger.error(f"Error removing admin: {e}")
            return False
        finally:
            conn.close()

# ====================== KEYBOARD FUNCTIONS ======================
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload ZIP', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'),
        types.InlineKeyboardButton('🤖 MPX AI', callback_data='mpx_ai')
    ]

    if user_id in admin_ids:
        pending_count = get_pending_files_count()
        pending_text = f"📋 Pending ({pending_count})" if pending_count > 0 else "📋 Pending"
        
        admin_buttons = [
            types.InlineKeyboardButton(pending_text, callback_data='view_pending'),
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('🔒 Lock' if not bot_locked else '🔓 Unlock',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All', callback_data='run_all_scripts')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(buttons[4], admin_buttons[1])
        markup.add(admin_buttons[2], admin_buttons[4])
        markup.add(admin_buttons[3])
        markup.add(buttons[5], buttons[6])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(buttons[4])
        markup.add(buttons[5], buttons[6])

    markup.add(types.InlineKeyboardButton('⏱ Uptime', callback_data='uptime'))
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if user_id in admin_ids:
        buttons = [["📢 Updates Channel", "/ping"], ["📤 Upload ZIP", "📂 Check Files"],
                   ["⚡ Bot Speed", "📊 Statistics"], ["💳 Subscriptions", "📢 Broadcast"],
                   ["🔒 Lock Bot", "🟢 Run All Projects"], ["👑 Admin Panel", "📞 Contact Owner"],
                   ["🤖 MPX Ai", "⏱ Uptime"]]
    else:
        buttons = [["📢 Updates Channel", "⏱ Uptime"], ["📤 Upload ZIP", "📂 Check Files"],
                   ["⚡ Bot Speed", "📊 Statistics"], ["📞 Contact Owner", "🤖 MPX Ai"]]
    
    for row in buttons:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    file_status = get_file_status(script_owner_id, file_name)
    
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    
    markup.add(types.InlineKeyboardButton(f"Status: {file_status['status']}", callback_data=f'status_{script_owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(
        types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'),
        types.InlineKeyboardButton('📋 Pending', callback_data='view_pending')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

# ====================== HANDLE ZIP FILE (FIXED) ======================
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    chat_id = message.chat.id
    
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        
        with open(zip_path, 'wb') as new_file: 
            new_file.write(downloaded_file_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None

        if not py_files:
            safe_send_message(chat_id, "❌ No Python (.py) files found in the ZIP!")
            return

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            if not install_requirements(req_path, message, user_folder):
                safe_send_message(chat_id, "❌ Failed to install Python dependencies. Check requirements.txt")
                return

        main_script_name = None
        for p in ['main.py', 'bot.py', 'app.py']:
            if p in py_files:
                main_script_name = p
                break
        
        if not main_script_name:
            main_script_name = py_files[0]

        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.exists(dest_path):
                if os.path.isdir(dest_path):
                    shutil.rmtree(dest_path)
                else:
                    os.remove(dest_path)
            shutil.move(src_path, dest_path)

        project_name = os.path.splitext(file_name_zip)[0]
        save_user_file(user_id, project_name, 'zip')
        save_file_approval(user_id, project_name, 'zip', FILE_STATUS_PENDING)
        send_file_for_approval(message, user_id, project_name, 'zip')
        
        success_msg = (f"✅ ZIP Uploaded Successfully!\n\n"
                       f"📁 Project: {project_name}\n"
                       f"📊 Files: {len(py_files)} Python files\n"
                       f"📋 Status: PENDING APPROVAL\n\n"
                       f"📦 Dependencies: {'✅ requirements.txt' if req_file else '❌ No requirements.txt'}\n\n"
                       f"👮 Admins have been notified.")
        safe_send_message(chat_id, success_msg)

    except zipfile.BadZipFile as e:
        safe_send_message(chat_id, f"❌ Error: Invalid or corrupted ZIP file.")
    except Exception as e:
        logger.error(f"Error processing zip: {e}")
        safe_send_message(chat_id, f"❌ Error processing zip: {str(e)[:200]}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass

# ====================== COMMAND HANDLERS ======================
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if bot_locked and user_id not in admin_ids:
        safe_send_message(chat_id, "Bot locked by admin. Try later.")
        return

    if user_id not in active_users:
        add_active_user(user_id)

    welcome_msg = (f"Welcome, {message.from_user.first_name}!\n\n"
                   f"Your User ID: {user_id}\n\n"
                   f"✅ Only ZIP files allowed\n"
                   f"✅ ZIP must contain Python (.py) files\n"
                   f"✅ requirements.txt for dependencies\n"
                   f"✅ Admin approval required\n\n"
                   f"Use buttons below 👇")
    
    safe_send_message(chat_id, welcome_msg, reply_markup=create_reply_keyboard_main_menu(user_id))

@bot.message_handler(commands=['mpx'])
def handle_mpx_command(message):
    if bot_locked and message.from_user.id not in admin_ids:
        safe_send_message(message.chat.id, "Bot is locked.")
        return

    if not message.text or len(message.text.split()) < 2:
        safe_send_message(message.chat.id, "Please provide a query after /mpx command.\nExample: /mpx What is AI?")
        return

    query = message.text.split(' ', 1)[1]
    bot.send_chat_action(message.chat.id, 'typing')

    try:
        headers = {"Authorization": f"Bearer {A4F_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": A4F_MODEL, "messages": [{"role": "user", "content": query}], "temperature": 0.7}
        response = requests.post(A4F_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        answer = result.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
        
        if len(answer) > 4000:
            for x in range(0, len(answer), 4000):
                safe_send_message(message.chat.id, answer[x:x+4000])
        else:
            safe_send_message(message.chat.id, answer)
    except Exception as e:
        safe_send_message(message.chat.id, "Error processing your request.")

@bot.message_handler(commands=['ping'])
def ping(message):
    start = time.time()
    msg = safe_send_message(message.chat.id, "Pong!")
    if msg:
        latency = round((time.time() - start) * 1000, 2)
        bot.edit_message_text(f"Pong! Latency: {latency} ms", message.chat.id, msg.message_id)

# ====================== BUTTON HANDLERS ======================
@bot.message_handler(func=lambda message: message.text in ["📤 Upload ZIP", "📂 Check Files", "⚡ Bot Speed", 
                                                          "📊 Statistics", "📢 Updates Channel", "📞 Contact Owner",
                                                          "⏱ Uptime", "💳 Subscriptions", "📢 Broadcast",
                                                          "🔒 Lock Bot", "🟢 Run All Projects", "👑 Admin Panel",
                                                          "🤖 MPX Ai", "/ping"])
def handle_buttons(message):
    text = message.text
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if text == "📤 Upload ZIP":
        if get_user_file_count(user_id) >= get_user_file_limit(user_id):
            safe_send_message(chat_id, "❌ Project limit reached. Delete existing projects first.")
            return
        safe_send_message(chat_id, "📤 Send your ZIP file containing Python code.")
    
    elif text == "📂 Check Files":
        files = user_files.get(user_id, [])
        if not files:
            safe_send_message(chat_id, "📁 Your Projects:\n\n(No projects uploaded yet)")
            return
        msg = "📁 Your Projects:\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for fname, ftype in files:
            status = get_file_status(user_id, fname)
            icon = "✅" if status['status'] == "approved" else "⏳" if status['status'] == "pending" else "❌"
            msg += f"{icon} {fname}\n"
            markup.add(types.InlineKeyboardButton(f"{icon} {fname}", callback_data=f'file_{user_id}_{fname}'))
        safe_send_message(chat_id, msg, reply_markup=markup)
    
    elif text == "⚡ Bot Speed":
        start = time.time()
        bot.send_chat_action(chat_id, 'typing')
        latency = round((time.time() - start) * 1000, 2)
        status = "Locked" if bot_locked else "Unlocked"
        safe_send_message(chat_id, f"⚡ Bot Speed\nLatency: {latency} ms\nStatus: {status}")
    
    elif text == "📊 Statistics":
        total = len(active_users)
        files = sum(len(f) for f in user_files.values())
        running = sum(1 for k in bot_scripts if is_bot_running(int(k.split('_')[0]), k.split('_')[1]))
        safe_send_message(chat_id, f"📊 Statistics\nUsers: {total}\nProjects: {files}\nRunning: {running}")
    
    elif text == "📢 Updates Channel":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
        safe_send_message(chat_id, "Visit our channel:", reply_markup=markup)
    
    elif text == "📞 Contact Owner":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
        safe_send_message(chat_id, "Click to contact:", reply_markup=markup)
    
    elif text == "⏱ Uptime":
        safe_send_message(chat_id, f"Uptime: {get_uptime()}")
    
    elif text == "🤖 MPX Ai":
        safe_send_message(chat_id, "Use /mpx command with your question.\nExample: /mpx What is Python?")
    
    # Admin only commands
    elif text in ["💳 Subscriptions", "📢 Broadcast", "🔒 Lock Bot", "🟢 Run All Projects", "👑 Admin Panel"]:
        if user_id not in admin_ids:
            safe_send_message(chat_id, "Admin only command.")
            return
        
        if text == "💳 Subscriptions":
            safe_send_message(chat_id, "Subscription Management", reply_markup=create_subscription_menu())
        
        elif text == "📢 Broadcast":
            msg = safe_send_message(chat_id, "Send message to broadcast:")
            bot.register_next_step_handler(msg, process_broadcast)
        
        elif text == "🔒 Lock Bot":
            global bot_locked
            bot_locked = not bot_locked
            safe_send_message(chat_id, f"Bot {'locked' if bot_locked else 'unlocked'}.")
        
        elif text == "🟢 Run All Projects":
            safe_send_message(chat_id, "Starting all approved projects...")
            for uid, files in user_files.items():
                for fname, _ in files:
                    if get_file_status(uid, fname)['status'] == "approved" and not is_bot_running(uid, fname):
                        safe_send_message(chat_id, f"Starting {fname} for user {uid}")
        
        elif text == "👑 Admin Panel":
            safe_send_message(chat_id, "Admin Panel", reply_markup=create_admin_panel())
    
    elif text == "/ping":
        ping(message)

# ====================== DOCUMENT HANDLER ======================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document

    if bot_locked and user_id not in admin_ids:
        safe_send_message(chat_id, "❌ Bot locked, cannot accept files.")
        return

    if get_user_file_count(user_id) >= get_user_file_limit(user_id):
        safe_send_message(chat_id, "❌ Project limit reached. Delete existing projects first.")
        return

    file_name = doc.file_name
    if not file_name or not file_name.lower().endswith('.zip'):
        safe_send_message(chat_id, "❌ Only ZIP files are allowed!")
        return

    if doc.file_size > 50 * 1024 * 1024:
        safe_send_message(chat_id, "❌ File too large (Max 50 MB).")
        return

    try:
        wait_msg = safe_send_message(chat_id, f"📥 Downloading {file_name}...")
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        if wait_msg:
            bot.edit_message_text(f"✅ Downloaded. Processing...", chat_id, wait_msg.message_id)
        
        handle_zip_file(downloaded, file_name, message)
        
    except Exception as e:
        logger.error(f"Error handling file: {e}")
        safe_send_message(chat_id, f"❌ Error: {str(e)[:200]}")

# ====================== CALLBACK HANDLERS ======================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'uptime']:
        bot.answer_callback_query(call.id, "Bot locked.", show_alert=True)
        return

    try:
        if data == 'upload':
            bot.answer_callback_query(call.id)
            safe_send_message(call.message.chat.id, "📤 Send your ZIP file.")
        
        elif data == 'check_files':
            check_files_callback(call)
        
        elif data.startswith('file_'):
            parts = data.split('_')
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = '_'.join(parts[2:])
                show_file_controls(call, owner_id, fname)
        
        elif data.startswith('start_'):
            parts = data.split('_')
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = '_'.join(parts[2:])
                start_project(call, owner_id, fname)
        
        elif data.startswith('stop_'):
            parts = data.split('_')
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = '_'.join(parts[2:])
                stop_project(call, owner_id, fname)
        
        elif data.startswith('delete_'):
            parts = data.split('_')
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = '_'.join(parts[2:])
                delete_project(call, owner_id, fname)
        
        elif data.startswith('logs_'):
            parts = data.split('_')
            if len(parts) >= 3:
                owner_id = int(parts[1])
                fname = '_'.join(parts[2:])
                show_logs(call, owner_id, fname)
        
        elif data == 'back_to_main':
            back_to_main_callback(call)
        
        elif data == 'view_pending' and user_id in admin_ids:
            pending = get_all_pending_files()
            if not pending:
                safe_send_message(call.message.chat.id, "✅ No pending files.")
            else:
                msg = "📋 Pending:\n"
                for uid, fname, ftype, time in pending:
                    msg += f"👤 {uid} | 📁 {fname}\n"
                safe_send_message(call.message.chat.id, msg)
        
        elif data.startswith('approve_') and user_id in admin_ids:
            parts = data.split('_')
            if len(parts) >= 3:
                target_id = int(parts[1])
                fname = '_'.join(parts[2:])
                if update_file_status(target_id, fname, "approved", user_id):
                    bot.answer_callback_query(call.id, "✅ Approved!")
                    safe_send_message(target_id, f"✅ Project {fname} approved!")
        
        elif data.startswith('reject_') and user_id in admin_ids:
            parts = data.split('_')
            if len(parts) >= 3:
                target_id = int(parts[1])
                fname = '_'.join(parts[2:])
                if update_file_status(target_id, fname, "rejected", user_id):
                    bot.answer_callback_query(call.id, "❌ Rejected!")
                    safe_send_message(target_id, f"❌ Project {fname} rejected.")
        
        elif data == 'speed':
            speed_callback(call)
        
        elif data == 'uptime':
            bot.answer_callback_query(call.id)
            safe_send_message(call.message.chat.id, f"Uptime: {get_uptime()}")
        
        else:
            bot.answer_callback_query(call.id, "Unknown command")
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "Error occurred", show_alert=True)

def check_files_callback(call):
    user_id = call.from_user.id
    files = user_files.get(user_id, [])
    if not files:
        bot.answer_callback_query(call.id, "No projects")
        return
    
    msg = "📁 Your Projects:\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fname, ftype in files:
        status = get_file_status(user_id, fname)
        icon = "✅" if status['status'] == "approved" else "⏳"
        markup.add(types.InlineKeyboardButton(f"{icon} {fname}", callback_data=f'file_{user_id}_{fname}'))
        msg += f"{icon} {fname}\n"
    
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except:
        safe_send_message(call.message.chat.id, msg, reply_markup=markup)

def show_file_controls(call, owner_id, fname):
    user_id = call.from_user.id
    if user_id != owner_id and user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Not your file", show_alert=True)
        return
    
    running = is_bot_running(owner_id, fname)
    status = get_file_status(owner_id, fname)
    
    msg = (f"📁 Project: {fname}\n"
           f"Status: {'Running' if running else 'Stopped'}\n"
           f"Approval: {status['status']}")
    
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id,
                            reply_markup=create_control_buttons(owner_id, fname, running))
    except:
        safe_send_message(call.message.chat.id, msg, reply_markup=create_control_buttons(owner_id, fname, running))

def start_project(call, owner_id, fname):
    user_id = call.from_user.id
    if user_id != owner_id and user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Permission denied", show_alert=True)
        return
    
    if get_file_status(owner_id, fname)['status'] != "approved":
        bot.answer_callback_query(call.id, "Not approved", show_alert=True)
        return
    
    if is_bot_running(owner_id, fname):
        bot.answer_callback_query(call.id, "Already running")
        return
    
    bot.answer_callback_query(call.id, "Starting...")
    user_folder = get_user_folder(owner_id)
    threading.Thread(target=run_script, args=(user_folder, owner_id, user_folder, fname, call.message)).start()
    time.sleep(1)
    show_file_controls(call, owner_id, fname)

def stop_project(call, owner_id, fname):
    user_id = call.from_user.id
    if user_id != owner_id and user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Permission denied", show_alert=True)
        return
    
    script_key = f"{owner_id}_{fname}"
    if script_key in bot_scripts:
        kill_process_tree(bot_scripts[script_key])
        del bot_scripts[script_key]
        bot.answer_callback_query(call.id, "Stopped")
    else:
        bot.answer_callback_query(call.id, "Not running")
    
    time.sleep(0.5)
    show_file_controls(call, owner_id, fname)

def delete_project(call, owner_id, fname):
    user_id = call.from_user.id
    if user_id != owner_id and user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Permission denied", show_alert=True)
        return
    
    script_key = f"{owner_id}_{fname}"
    if script_key in bot_scripts:
        kill_process_tree(bot_scripts[script_key])
        del bot_scripts[script_key]
    
    user_folder = get_user_folder(owner_id)
    for f in os.listdir(user_folder):
        try: os.remove(os.path.join(user_folder, f))
        except: pass
    
    remove_user_file_db(owner_id, fname)
    
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM file_approvals WHERE user_id=? AND file_name=?', (owner_id, fname))
        conn.commit()
        conn.close()
    
    bot.answer_callback_query(call.id, "✅ Deleted")
    bot.edit_message_text(f"✅ Project {fname} deleted", call.message.chat.id, call.message.message_id)

def show_logs(call, owner_id, fname):
    user_id = call.from_user.id
    if user_id != owner_id and user_id not in admin_ids:
        bot.answer_callback_query(call.id, "Permission denied", show_alert=True)
        return
    
    user_folder = get_user_folder(owner_id)
    log_path = os.path.join(user_folder, f"{os.path.splitext(fname)[0]}.log")
    
    if not os.path.exists(log_path):
        bot.answer_callback_query(call.id, "No logs")
        return
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()[-3000:]
        safe_send_message(call.message.chat.id, f"📜 Logs for {fname}:\n{content}")
    except:
        safe_send_message(call.message.chat.id, "Error reading logs")

def speed_callback(call):
    start = time.time()
    bot.answer_callback_query(call.id)
    latency = round((time.time() - start) * 1000, 2)
    status = "Locked" if bot_locked else "Unlocked"
    try:
        bot.edit_message_text(f"⚡ Speed Test\nLatency: {latency} ms\nStatus: {status}",
                            call.message.chat.id, call.message.message_id,
                            reply_markup=create_main_menu_inline(call.from_user.id))
    except:
        safe_send_message(call.message.chat.id, f"⚡ Speed Test\nLatency: {latency} ms\nStatus: {status}")

def back_to_main_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(f"Main Menu", call.message.chat.id, call.message.message_id,
                            reply_markup=create_main_menu_inline(call.from_user.id))
    except:
        safe_send_message(call.message.chat.id, "Main Menu", reply_markup=create_main_menu_inline(call.from_user.id))

# ====================== BROADCAST FUNCTION ======================
def process_broadcast(message):
    if message.from_user.id not in admin_ids:
        return
    if message.text and message.text.lower() == '/cancel':
        safe_send_message(message.chat.id, "Broadcast cancelled")
        return
    
    text = message.text or "Broadcast message"
    success = 0
    fail = 0
    
    for uid in list(active_users):
        try:
            safe_send_message(uid, text)
            success += 1
            time.sleep(0.05)
        except:
            fail += 1
    
    safe_send_message(message.chat.id, f"Broadcast complete\n✅ Sent: {success}\n❌ Failed: {fail}")

# ====================== RUN SCRIPT FUNCTION ======================
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply):
    script_key = f"{script_owner_id}_{file_name}"
    log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
    
    try:
        main_script = None
        for f in ['main.py', 'bot.py', 'app.py']:
            if os.path.exists(os.path.join(user_folder, f)):
                main_script = f
                break
        if not main_script:
            py_files = [f for f in os.listdir(user_folder) if f.endswith('.py')]
            main_script = py_files[0] if py_files else None
        
        if not main_script:
            safe_send_message(message_obj_for_reply.chat.id, "No Python script found")
            return
        
        log_file = open(log_path, 'w', encoding='utf-8')
        process = subprocess.Popen([sys.executable, os.path.join(user_folder, main_script)],
                                  cwd=user_folder, stdout=log_file, stderr=log_file)
        
        bot_scripts[script_key] = {'process': process, 'log_file': log_file, 'file_name': file_name,
                                  'script_owner_id': script_owner_id, 'start_time': datetime.now()}
        
        safe_send_message(message_obj_for_reply.chat.id, f"✅ Started {file_name}")
        
    except Exception as e:
        safe_send_message(message_obj_for_reply.chat.id, f"❌ Error: {str(e)[:200]}")

# ====================== CLEANUP ======================
def cleanup():
    logger.info("Cleaning up...")
    for script in bot_scripts.values():
        kill_process_tree(script)
atexit.register(cleanup)

# ====================== MAIN LOOP ======================
if __name__ == '__main__':
    print("="*50)
    print("🤖 BOT STARTING - FIXED VERSION")
    print("="*50)
    print(f"Owner ID: {OWNER_ID}")
    print(f"Admins: {admin_ids}")
    print("="*50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            print(f"Error: {e}, restarting in 5s...")
            time.sleep(5)