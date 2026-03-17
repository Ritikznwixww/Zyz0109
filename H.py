# H_railway.py - COMPLETE FIXED VERSION (NO ERRORS)
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
import logging
import threading
import re
import sys
import atexit
import requests

# ====================== CONFIGURATION ======================
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8487271564:AAFxXGmmIl73iflDp8EPuNn-5y-AtoH4NhQ')
OWNER_ID = int(os.environ.get('OWNER_ID', 7964730489))
ADMIN_ID = int(os.environ.get('ADMIN_ID', 7964730489))
YOUR_USERNAME = os.environ.get('YOUR_USERNAME', '@XyzR9')
UPDATE_CHANNEL = os.environ.get('UPDATE_CHANNEL', 'https://t.me/Xyzr4')

# Railway paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join('/data', 'upload_bots')
IROTECH_DIR = os.path.join('/data', 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# Create directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# ====================== WEBHOOK FIX ======================
print("=" * 50)
print("🔧 Fixing webhook issue...")
try:
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
    print("✅ Webhook deleted")
except:
    print("⚠️ Could not delete webhook")
time.sleep(2)
print("=" * 50)

# ====================== INITIALIZE BOT ======================
bot = telebot.TeleBot(TOKEN)
print("✅ Bot initialized")

# Global variables
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
BOT_START_TIME = datetime.now()
DB_LOCK = threading.Lock()

# File status
FILE_STATUS_PENDING = "pending"
FILE_STATUS_APPROVED = "approved"
FILE_STATUS_REJECTED = "rejected"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====================== SAFE MESSAGE FUNCTION ======================
def send_msg(chat_id, text, reply_markup=None):
    """Simple message sending without markdown"""
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            # Remove special characters if error
            clean_text = re.sub(r'[_*[\]()~`>#+\-=|{}.!]', '', text)
            return bot.send_message(chat_id, clean_text[:3000], reply_markup=reply_markup)
        except:
            return None

# ====================== DATABASE FUNCTIONS ======================
def init_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
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
                      uploaded_time TEXT, PRIMARY KEY (user_id, file_name))''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB init error: {e}")

def load_data():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for uid, exp in c.fetchall():
            try:
                user_subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except:
                pass
                
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for uid, name, ftype in c.fetchall():
            if uid not in user_files:
                user_files[uid] = []
            user_files[uid].append((name, ftype))
            
        c.execute('SELECT user_id FROM active_users')
        active_users.update([uid for uid, in c.fetchall()])
        
        c.execute('SELECT user_id FROM admins')
        admin_ids.update([uid for uid, in c.fetchall()])
        
        conn.close()
    except Exception as e:
        logger.error(f"Load error: {e}")

init_db()
load_data()

def get_file_status(user_id, file_name):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT status FROM file_approvals WHERE user_id=? AND file_name=?', (user_id, file_name))
        result = c.fetchone()
        conn.close()
        return result[0] if result else FILE_STATUS_PENDING
    except:
        return FILE_STATUS_PENDING

def update_file_status(user_id, file_name, status, admin_id):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''UPDATE file_approvals SET status=?, reviewed_by=?, review_time=?
                    WHERE user_id=? AND file_name=?''',
                 (status, admin_id, datetime.now().isoformat(), user_id, file_name))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def save_file_approval(user_id, file_name, file_type, status=FILE_STATUS_PENDING):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO file_approvals 
                    (user_id, file_name, file_type, status, uploaded_time) 
                    VALUES (?, ?, ?, ?, ?)''',
                 (user_id, file_name, file_type, status, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Save approval error: {e}")

def get_pending_files():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('SELECT user_id, file_name, file_type FROM file_approvals WHERE status=?', (FILE_STATUS_PENDING,))
        result = c.fetchall()
        conn.close()
        return result
    except:
        return []

def save_user_file(user_id, file_name, file_type='zip'):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                  (user_id, file_name, file_type))
        conn.commit()
        conn.close()
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id] = [(fn, ft) for fn, ft in user_files.get(user_id, []) if fn != file_name]
        user_files[user_id].append((file_name, file_type))
    except Exception as e:
        logger.error(f"Save file error: {e}")

def remove_user_file(user_id, file_name):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
        c.execute('DELETE FROM file_approvals WHERE user_id=? AND file_name=?', (user_id, file_name))
        conn.commit()
        conn.close()
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
    except Exception as e:
        logger.error(f"Remove error: {e}")

def add_active_user(user_id):
    active_users.add(user_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
    except:
        pass

# ====================== UTILITY FUNCTIONS ======================
def get_uptime():
    uptime = datetime.now() - BOT_START_TIME
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def get_user_folder(user_id):
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_limit(user_id):
    if user_id == OWNER_ID:
        return float('inf')
    if user_id in admin_ids:
        return 999
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return 15
    return 2

def is_running(owner_id, file_name):
    key = f"{owner_id}_{file_name}"
    if key in bot_scripts:
        try:
            proc = psutil.Process(bot_scripts[key]['process'].pid)
            return proc.is_running()
        except:
            return False
    return False

def kill_process(proc_info):
    try:
        proc = proc_info.get('process')
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(1)
            if proc.poll() is None:
                proc.kill()
        if 'log_file' in proc_info:
            proc_info['log_file'].close()
    except:
        pass

# ====================== INSTALL REQUIREMENTS (FIXED) ======================
def install_req(req_file, chat_id):
    """Install requirements.txt without markdown errors"""
    try:
        send_msg(chat_id, "Installing Python dependencies...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', req_file],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            send_msg(chat_id, "✅ Dependencies installed")
            return True
        else:
            error = result.stderr[:200] or result.stdout[:200]
            send_msg(chat_id, f"❌ Install failed: {error}")
            return False
    except Exception as e:
        send_msg(chat_id, f"❌ Error: {str(e)[:100]}")
        return False

# ====================== HANDLE ZIP FILE ======================
def handle_zip(file_data, zip_name, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, zip_name)
        
        with open(zip_path, 'wb') as f:
            f.write(file_data)
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(temp_dir)
        
        files = os.listdir(temp_dir)
        py_files = [f for f in files if f.endswith('.py')]
        
        if not py_files:
            send_msg(chat_id, "❌ No Python files in ZIP")
            return
        
        if 'requirements.txt' in files:
            req_path = os.path.join(temp_dir, 'requirements.txt')
            if not install_req(req_path, chat_id):
                return
        
        # Find main file
        main_file = None
        for name in ['main.py', 'bot.py', 'app.py']:
            if name in py_files:
                main_file = name
                break
        if not main_file:
            main_file = py_files[0]
        
        # Move files
        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        
        project_name = os.path.splitext(zip_name)[0]
        save_user_file(user_id, project_name, 'zip')
        save_file_approval(user_id, project_name, 'zip', FILE_STATUS_PENDING)
        
        # Notify admins
        user = message.from_user
        admin_msg = (f"📦 NEW ZIP\nUser: {user.first_name}\nID: {user_id}\n"
                    f"File: {zip_name}\nProject: {project_name}")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f'app_{user_id}_{project_name}'),
            types.InlineKeyboardButton("❌ Reject", callback_data=f'rej_{user_id}_{project_name}')
        )
        
        for aid in admin_ids:
            try:
                send_msg(aid, admin_msg, markup)
            except:
                pass
        
        send_msg(chat_id, f"✅ ZIP uploaded! Project: {project_name}\n⏳ Waiting for approval")
        
    except Exception as e:
        send_msg(chat_id, f"❌ Error: {str(e)[:100]}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

# ====================== RUN SCRIPT ======================
def run_script(owner_id, file_name, chat_id):
    key = f"{owner_id}_{file_name}"
    folder = get_user_folder(owner_id)
    log_path = os.path.join(folder, f"{file_name}.log")
    
    try:
        # Find main python file
        main_py = None
        for name in ['main.py', 'bot.py', 'app.py']:
            if os.path.exists(os.path.join(folder, name)):
                main_py = name
                break
        if not main_py:
            py_files = [f for f in os.listdir(folder) if f.endswith('.py')]
            main_py = py_files[0] if py_files else None
        
        if not main_py:
            send_msg(chat_id, "❌ No Python file found")
            return
        
        log_file = open(log_path, 'w')
        proc = subprocess.Popen(
            [sys.executable, os.path.join(folder, main_py)],
            cwd=folder, stdout=log_file, stderr=log_file
        )
        
        bot_scripts[key] = {
            'process': proc,
            'log_file': log_file,
            'file_name': file_name,
            'owner': owner_id,
            'start': datetime.now()
        }
        
        send_msg(chat_id, f"✅ Started {file_name}")
        
    except Exception as e:
        send_msg(chat_id, f"❌ Start error: {str(e)[:100]}")

# ====================== KEYBOARDS ======================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if user_id in admin_ids:
        buttons = [
            ["📤 Upload ZIP", "📂 My Files"],
            ["⚡ Speed", "📊 Stats"],
            ["👑 Admin", "📢 Broadcast"],
            ["🔒 Lock", "⏱ Uptime"],
            ["🤖 MPX AI"]
        ]
    else:
        buttons = [
            ["📤 Upload ZIP", "📂 My Files"],
            ["⚡ Speed", "📊 Stats"],
            ["⏱ Uptime", "🤖 MPX AI"]
        ]
    for row in buttons:
        markup.add(*row)
    return markup

def file_buttons(owner_id, file_name, running):
    markup = types.InlineKeyboardMarkup(row_width=2)
    status = get_file_status(owner_id, file_name)
    
    if running:
        markup.add(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{owner_id}_{file_name}')
        )
    else:
        if status == FILE_STATUS_APPROVED:
            markup.add(
                types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{owner_id}_{file_name}'),
                types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{owner_id}_{file_name}')
            )
        else:
            markup.add(types.InlineKeyboardButton(f"⏳ {status}", callback_data='noop'))
    
    markup.add(types.InlineKeyboardButton("🗑️ Delete", callback_data=f'del_{owner_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_files'))
    return markup

# ====================== COMMAND HANDLERS ======================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    add_active_user(uid)
    text = (f"Welcome {message.from_user.first_name}!\n"
            f"ID: {uid}\n\n"
            f"📌 Only ZIP files allowed\n"
            f"📌 Must contain Python files\n"
            f"📌 Admin approval required")
    send_msg(message.chat.id, text, main_keyboard(uid))

@bot.message_handler(func=lambda m: m.text == "📤 Upload ZIP")
def upload_btn(m):
    uid = m.from_user.id
    if len(user_files.get(uid, [])) >= get_user_limit(uid):
        send_msg(m.chat.id, "❌ Limit reached. Delete some projects first.")
        return
    send_msg(m.chat.id, "📤 Send me a ZIP file containing your Python project")

@bot.message_handler(func=lambda m: m.text == "📂 My Files")
def files_btn(m):
    uid = m.from_user.id
    files = user_files.get(uid, [])
    if not files:
        send_msg(m.chat.id, "📁 No files yet")
        return
    
    markup = types.InlineKeyboardMarkup()
    for fname, ftype in files:
        status = get_file_status(uid, fname)
        icon = "✅" if status == FILE_STATUS_APPROVED else "⏳" if status == FILE_STATUS_PENDING else "❌"
        markup.add(types.InlineKeyboardButton(f"{icon} {fname}", callback_data=f'file_{uid}_{fname}'))
    
    send_msg(m.chat.id, "📁 Your files:", markup)

@bot.message_handler(func=lambda m: m.text == "⚡ Speed")
def speed_btn(m):
    start = time.time()
    send_msg(m.chat.id, "Testing...")
    latency = round((time.time() - start) * 1000, 2)
    send_msg(m.chat.id, f"⚡ Latency: {latency}ms")

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def stats_btn(m):
    text = (f"📊 Stats\n"
            f"Users: {len(active_users)}\n"
            f"Projects: {sum(len(f) for f in user_files.values())}\n"
            f"Running: {len(bot_scripts)}")
    send_msg(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "⏱ Uptime")
def uptime_btn(m):
    send_msg(m.chat.id, f"⏱ Uptime: {get_uptime()}")

@bot.message_handler(func=lambda m: m.text == "🤖 MPX AI")
def mpx_btn(m):
    send_msg(m.chat.id, "Use /mpx your question")

@bot.message_handler(commands=['mpx'])
def mpx_cmd(m):
    if len(m.text.split()) < 2:
        send_msg(m.chat.id, "Example: /mpx what is python")
        return
    query = m.text.split(' ', 1)[1]
    send_msg(m.chat.id, "Thinking...")
    try:
        # Simple echo for demo
        send_msg(m.chat.id, f"AI response to: {query[:100]}")
    except:
        send_msg(m.chat.id, "Error")

# Admin commands
@bot.message_handler(func=lambda m: m.text == "👑 Admin" and m.from_user.id in admin_ids)
def admin_btn(m):
    pending = get_pending_files()
    text = f"👑 Admin Panel\nPending: {len(pending)}"
    markup = types.InlineKeyboardMarkup()
    if pending:
        markup.add(types.InlineKeyboardButton("📋 View Pending", callback_data='view_pending'))
    markup.add(types.InlineKeyboardButton("👥 List Admins", callback_data='list_admins'))
    send_msg(m.chat.id, text, markup)

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and m.from_user.id in admin_ids)
def broadcast_btn(m):
    msg = send_msg(m.chat.id, "Send message to broadcast:")
    bot.register_next_step_handler(msg, do_broadcast)

def do_broadcast(m):
    if m.from_user.id not in admin_ids:
        return
    text = m.text
    if not text:
        return
    success = 0
    for uid in list(active_users):
        try:
            send_msg(uid, f"📢 Broadcast:\n{text}")
            success += 1
            time.sleep(0.05)
        except:
            pass
    send_msg(m.chat.id, f"✅ Sent to {success} users")

@bot.message_handler(func=lambda m: m.text == "🔒 Lock" and m.from_user.id in admin_ids)
def lock_btn(m):
    global bot_locked
    bot_locked = not bot_locked
    send_msg(m.chat.id, f"🔒 Bot {'locked' if bot_locked else 'unlocked'}")

# Document handler
@bot.message_handler(content_types=['document'])
def doc_handler(m):
    uid = m.from_user.id
    if bot_locked and uid not in admin_ids:
        send_msg(m.chat.id, "❌ Bot locked")
        return
    
    if len(user_files.get(uid, [])) >= get_user_limit(uid):
        send_msg(m.chat.id, "❌ Limit reached")
        return
    
    doc = m.document
    if not doc.file_name.endswith('.zip'):
        send_msg(m.chat.id, "❌ Only ZIP files allowed")
        return
    
    if doc.file_size > 50 * 1024 * 1024:
        send_msg(m.chat.id, "❌ File too big (max 50MB)")
        return
    
    try:
        msg = send_msg(m.chat.id, "📥 Downloading...")
        file_info = bot.get_file(doc.file_id)
        file_data = bot.download_file(file_info.file_path)
        
        if msg:
            bot.edit_message_text("✅ Downloaded. Processing...", m.chat.id, msg.message_id)
        
        handle_zip(file_data, doc.file_name, m)
        
    except Exception as e:
        send_msg(m.chat.id, f"❌ Error: {str(e)[:100]}")

# ====================== CALLBACK HANDLERS ======================
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    uid = c.from_user.id
    data = c.data
    
    if data == 'noop':
        bot.answer_callback_query(c.id)
        return
    
    # File view
    if data.startswith('file_'):
        parts = data.split('_')
        owner = int(parts[1])
        fname = '_'.join(parts[2:])
        
        if uid != owner and uid not in admin_ids:
            bot.answer_callback_query(c.id, "Not your file", show_alert=True)
            return
        
        running = is_running(owner, fname)
        status = get_file_status(owner, fname)
        text = f"📁 {fname}\nStatus: {'Running' if running else 'Stopped'}\nApproval: {status}"
        
        bot.answer_callback_query(c.id)
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                                reply_markup=file_buttons(owner, fname, running))
        except:
            send_msg(c.message.chat.id, text, file_buttons(owner, fname, running))
    
    # Start
    elif data.startswith('start_'):
        parts = data.split('_')
        owner = int(parts[1])
        fname = '_'.join(parts[2:])
        
        if uid != owner and uid not in admin_ids:
            bot.answer_callback_query(c.id, "Permission denied", show_alert=True)
            return
        
        if get_file_status(owner, fname) != FILE_STATUS_APPROVED:
            bot.answer_callback_query(c.id, "Not approved", show_alert=True)
            return
        
        if is_running(owner, fname):
            bot.answer_callback_query(c.id, "Already running")
            return
        
        bot.answer_callback_query(c.id, "Starting...")
        threading.Thread(target=run_script, args=(owner, fname, c.message.chat.id)).start()
        time.sleep(1)
        
        # Refresh view
        running = is_running(owner, fname)
        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                        reply_markup=file_buttons(owner, fname, running))
        except:
            pass
    
    # Stop
    elif data.startswith('stop_'):
        parts = data.split('_')
        owner = int(parts[1])
        fname = '_'.join(parts[2:])
        key = f"{owner}_{fname}"
        
        if uid != owner and uid not in admin_ids:
            bot.answer_callback_query(c.id, "Permission denied", show_alert=True)
            return
        
        if key in bot_scripts:
            kill_process(bot_scripts[key])
            del bot_scripts[key]
            bot.answer_callback_query(c.id, "Stopped")
        else:
            bot.answer_callback_query(c.id, "Not running")
        
        time.sleep(1)
        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                        reply_markup=file_buttons(owner, fname, False))
        except:
            pass
    
    # Delete
    elif data.startswith('del_'):
        parts = data.split('_')
        owner = int(parts[1])
        fname = '_'.join(parts[2:])
        key = f"{owner}_{fname}"
        
        if uid != owner and uid not in admin_ids:
            bot.answer_callback_query(c.id, "Permission denied", show_alert=True)
            return
        
        if key in bot_scripts:
            kill_process(bot_scripts[key])
            del bot_scripts[key]
        
        # Delete files
        folder = get_user_folder(owner)
        for f in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, f))
            except:
                pass
        
        remove_user_file(owner, fname)
        
        bot.answer_callback_query(c.id, "✅ Deleted")
        try:
            bot.edit_message_text(f"✅ Deleted {fname}", c.message.chat.id, c.message.message_id)
        except:
            send_msg(c.message.chat.id, f"✅ Deleted {fname}")
    
    # Logs
    elif data.startswith('logs_'):
        parts = data.split('_')
        owner = int(parts[1])
        fname = '_'.join(parts[2:])
        
        if uid != owner and uid not in admin_ids:
            bot.answer_callback_query(c.id, "Permission denied", show_alert=True)
            return
        
        folder = get_user_folder(owner)
        log_path = os.path.join(folder, f"{fname}.log")
        
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    logs = f.read()[-2000:]
                send_msg(c.message.chat.id, f"📜 Logs for {fname}:\n{logs}")
            except:
                send_msg(c.message.chat.id, "❌ Cannot read logs")
        else:
            send_msg(c.message.chat.id, "📜 No logs yet")
        
        bot.answer_callback_query(c.id)
    
    # Back to files list
    elif data == 'back_files':
        uid = c.from_user.id
        files = user_files.get(uid, [])
        markup = types.InlineKeyboardMarkup()
        for fname, ftype in files:
            status = get_file_status(uid, fname)
            icon = "✅" if status == FILE_STATUS_APPROVED else "⏳"
            markup.add(types.InlineKeyboardButton(f"{icon} {fname}", callback_data=f'file_{uid}_{fname}'))
        
        try:
            bot.edit_message_text("📁 Your files:", c.message.chat.id, c.message.message_id, reply_markup=markup)
        except:
            pass
    
    # Admin: view pending
    elif data == 'view_pending' and uid in admin_ids:
        pending = get_pending_files()
        if not pending:
            bot.answer_callback_query(c.id, "No pending files")
            return
        
        text = "📋 Pending approvals:\n"
        markup = types.InlineKeyboardMarkup()
        for puid, fname, ftype in pending:
            text += f"👤 {puid} - {fname}\n"
            markup.add(types.InlineKeyboardButton(f"👤 {puid} - {fname}", callback_data=f'review_{puid}_{fname}'))
        
        bot.answer_callback_query(c.id)
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
        except:
            send_msg(c.message.chat.id, text, markup)
    
    # Admin: review specific
    elif data.startswith('review_') and uid in admin_ids:
        parts = data.split('_')
        puid = int(parts[1])
        fname = '_'.join(parts[2:])
        
        text = f"Review: {fname}\nUser: {puid}"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f'app_{puid}_{fname}'),
            types.InlineKeyboardButton("❌ Reject", callback_data=f'rej_{puid}_{fname}')
        )
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='view_pending'))
        
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
        except:
            send_msg(c.message.chat.id, text, markup)
    
    # Admin: approve
    elif data.startswith('app_') and uid in admin_ids:
        parts = data.split('_')
        puid = int(parts[1])
        fname = '_'.join(parts[2:])
        
        if update_file_status(puid, fname, FILE_STATUS_APPROVED, uid):
            bot.answer_callback_query(c.id, "✅ Approved")
            send_msg(puid, f"✅ Your project '{fname}' was approved!")
            try:
                bot.edit_message_text(f"✅ Approved {fname}", c.message.chat.id, c.message.message_id)
            except:
                pass
        else:
            bot.answer_callback_query(c.id, "Error", show_alert=True)
    
    # Admin: reject
    elif data.startswith('rej_') and uid in admin_ids:
        parts = data.split('_')
        puid = int(parts[1])
        fname = '_'.join(parts[2:])
        
        if update_file_status(puid, fname, FILE_STATUS_REJECTED, uid):
            bot.answer_callback_query(c.id, "❌ Rejected")
            send_msg(puid, f"❌ Your project '{fname}' was rejected.")
            try:
                bot.edit_message_text(f"❌ Rejected {fname}", c.message.chat.id, c.message.message_id)
            except:
                pass
        else:
            bot.answer_callback_query(c.id, "Error", show_alert=True)
    
    # Admin: list admins
    elif data == 'list_admins' and uid in admin_ids:
        text = "👑 Admins:\n"
        for aid in sorted(admin_ids):
            text += f"• {aid} {'(Owner)' if aid == OWNER_ID else ''}\n"
        bot.answer_callback_query(c.id)
        send_msg(c.message.chat.id, text)
    
    else:
        bot.answer_callback_query(c.id, "Unknown command")

# ====================== CLEANUP ======================
def cleanup():
    print("Cleaning up...")
    for key, info in list(bot_scripts.items()):
        kill_process(info)
    print("Done")

atexit.register(cleanup)

# ====================== MAIN LOOP ======================
if __name__ == '__main__':
    print("="*50)
    print("✅ BOT STARTED - FIXED VERSION")
    print("="*50)
    print(f"Owner ID: {OWNER_ID}")
    print(f"Admins: {admin_ids}")
    print("="*50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Error: {e}, restarting in 5s...")
            time.sleep(5)