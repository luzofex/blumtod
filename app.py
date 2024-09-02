import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify
import threading
import os
import json
import time
from urllib.parse import parse_qs, unquote
import re
from datetime import datetime, timedelta

from bot import BlumTod

# Setup Flask and logging
app = Flask(__name__)

# Variabel global untuk menyimpan bot instance, thread, dan waktu restart berikutnya
bot_thread = None
bot_instance = None
next_restart_time = None  # Variabel untuk menyimpan waktu restart berikutnya

logger = logging.getLogger('werkzeug')
logger.setLevel(logging.INFO)

log_file = 'app.log'
rotating_handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=5)
rotating_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', '%Y-%m-%d %H:%M:%S')
rotating_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)

logger.addHandler(rotating_handler)
logger.addHandler(console_handler)

# Function to trim the log file to the last 100 lines
def trim_log_file():
    with open(log_file, 'r') as f:
        lines = f.readlines()

    if len(lines) > 100:
        with open(log_file, 'w') as f:
            f.writelines(lines[-100:])

# Function to log messages
def log_message(message):
    logger.info(message)

# Variabel global untuk menyimpan next_restart_time
next_restart_time = None

# Fungsi untuk memuat next_restart_time dari bot_state.json
def load_next_restart_time():
    global next_restart_time
    try:
        with open('bot_state.json', 'r', encoding='utf-8') as f:
            state = json.load(f)
            next_restart_time_str = state.get('next_restart_time', None)
            if next_restart_time_str:
                next_restart_time = datetime.fromisoformat(next_restart_time_str)
            else:
                next_restart_time = None
    except (FileNotFoundError, json.JSONDecodeError) as e:
        next_restart_time = None
        logger.error(f"Error loading next_restart_time from bot_state.json: {str(e)}")

@app.route('/next_restart')
def next_restart():
    global next_restart_time
    load_next_restart_time()  # Hanya membaca nilai terbaru tanpa memodifikasi
    if next_restart_time:
        return jsonify({'next_restart_time': next_restart_time.strftime('%Y-%m-%d %H:%M:%S')})
    else:
        return jsonify({'next_restart_time': 'N/A'})

# Function to save the state of processing (e.g., token or balance)
def save_state_callback(userid, data):
    tokens_file = 'tokens.json'
    if os.path.exists(tokens_file):
        with open(tokens_file, 'r', encoding='utf-8') as f:
            tokens = json.load(f)
    else:
        tokens = {}

    tokens[str(userid)] = data

    with open(tokens_file, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, indent=4)

# Function to remove empty lines from a file
def remove_empty_lines(file_path):
    if not os.path.exists(file_path):
        logger.warning(f"File {file_path} not found.")
        return

    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    cleaned_lines = [line for line in lines if line.strip()]

    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(cleaned_lines)

    logger.info(f"Removed empty lines from {file_path}.")

# Clean files at the start
def clean_all_files():
    logger.info("Cleaning all files at the start.")
    remove_empty_lines('data.txt')
    remove_empty_lines('user-agent.txt')
    remove_empty_lines('proxies.txt')
    remove_empty_lines('config.json')

# Function to be called after editing files
def post_edit_cleanup(file_path):
    logger.info(f"Cleaning up after editing {file_path}.")
    remove_empty_lines(file_path)

@app.route('/')
def index():
    logger.info("Accessing the index page.")
    trim_log_file()
    return render_template('index.html')

@app.route('/start_bot', methods=['POST'])
def start_bot():
    global bot_thread, bot_instance

    if bot_thread is None or not bot_thread.is_alive():
        bot_instance = BlumTod()  # Inisialisasi instance bot
        bot_thread = threading.Thread(target=run_bot, args=(bot_instance,))
        bot_thread.start()

        logger.info("Bot started.")
        trim_log_file()
        return jsonify({'status': 'Bot started'})
    else:
        logger.info("Attempted to start bot, but it's already running.")
        trim_log_file()
        return jsonify({'status': 'Bot is already running'})

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    global bot_thread, bot_instance

    if bot_instance is not None:
        bot_instance.stop()
        bot_thread.join()
        logger.info("Bot stopped.")
        bot_instance = None
        bot_thread = None
        trim_log_file()
        return jsonify({'status': 'Bot stopped'})
    else:
        logger.info("Attempted to stop bot, but it was not running.")
        trim_log_file()
        return jsonify({'status': 'Bot is not running'})

@app.route('/status')
def status():
    global bot_thread
    running = bot_thread is not None and bot_thread.is_alive()
    logger.info(f"Checking bot status: {'running' if running else 'stopped'}.")
    trim_log_file()
    return jsonify({'running': running})

@app.route('/logs')
def get_logs():
    logs = {}

    # Ensure bot.log exists
    bot_log_path = os.path.join(os.path.dirname(__file__), 'bot.log')
    if not os.path.exists(bot_log_path):
        with open(bot_log_path, 'w', encoding='utf-8') as f:
            f.write('')

    try:
        with open(bot_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['bot_log'] = format_logs(f.readlines())
        logger.info(f"Read bot.log: {len(logs['bot_log'])} lines.")
    except FileNotFoundError:
        logs['bot_log'] = ["bot.log file not found."]
        logger.warning("bot.log file not found.")

    # Ensure http.log exists
    http_log_path = os.path.join(os.path.dirname(__file__), 'http.log')
    if not os.path.exists(http_log_path):
        with open(http_log_path, 'w', encoding='utf-8') as f:
            f.write('')

    try:
        with open(http_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['http_log'] = format_logs(f.readlines())
        logger.info(f"Read http.log: {len(logs['http_log'])} lines.")
    except FileNotFoundError:
        logs['http_log'] = ["http.log file not found."]
        logger.warning("http.log file not found.")

    trim_log_file()
    return jsonify(logs)

def format_logs(log_lines):
    """Convert log lines to formatted HTML."""
    html_logs = []
    for line in log_lines:
        # Hapus kode warna ANSI
        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        
        # Escape HTML dan tambahkan format
        clean_line = clean_line.strip().replace(" ", "&nbsp;").replace("\n", "<br>")
        
        if "ERROR" in clean_line:
            html_line = f'<div style="color:red;">{clean_line}</div>'
        elif "WARNING" in clean_line:
            html_line = f'<div style="color:orange;">{clean_line}</div>'
        else:
            html_line = f'<div style="color:green;">{clean_line}</div>'
        
        html_logs.append(html_line)
    return "".join(html_logs)

@app.route('/edit_files')
def edit_files():
    logger.info("Accessing the edit files page.")
    trim_log_file()
    return render_template('edit_files.html')

@app.route('/edit_file', methods=['GET', 'POST'])
def edit_file():
    if request.method == 'POST':
        file_name = request.form.get('file_name')
        content = request.form.get('content')
        
        if file_name is None or content is None and 'save' in request.form:
            logger.error("File name or content missing in the request.")
            return jsonify({'status': 'failed', 'message': 'File name or content missing'}), 400
        
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        
        if 'save' in request.form:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            post_edit_cleanup(file_path)  # Remove empty lines after saving
            logger.info(f"Saved content to {file_name}.")
            
            status_message = 'success'
            
        elif 'delete' in request.form:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write('')
            logger.info(f"Cleared content of {file_name}.")
            status_message = 'cleared'
            
        else:
            status_message = 'failed'
            
        trim_log_file()
        return jsonify({'status': status_message})
    else:
        file_name = request.args.get('file_name', 'data.txt')
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        post_edit_cleanup(file_path)  # Remove empty lines before reading
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            logger.info(f"Read content from {file_name}.")
        except FileNotFoundError:
            content = ''
            logger.warning(f"{file_name} not found.")
        trim_log_file()
        return jsonify({'file_name': file_name, 'content': content})

@app.route('/edit_config', methods=['GET', 'POST'])
def edit_config_file():
    config_file_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if request.method == 'POST':
        try:
            new_config = request.json
            with open(config_file_path, 'w', encoding='utf-8') as config_file:
                json.dump(new_config, config_file, indent=4)
            post_edit_cleanup(config_file_path)  # Clean up config file after editing
            logger.info("Updated config.json.")
            trim_log_file()
            return jsonify({'status': 'Config updated successfully'})
        except Exception as e:
            logger.error(f"Error updating config: {str(e)}")
            return jsonify({'status': 'failed', 'message': str(e)}), 500
    
    else:
        try:
            post_edit_cleanup(config_file_path)  # Clean up config file before loading
            with open(config_file_path, 'r', encoding='utf-8') as config_file:
                config_data = json.load(config_file)
            logger.info("Rendering the edit config HTML page with current config data.")
            return render_template('edit_config.html', config=config_data)
        except FileNotFoundError:
            logger.warning("config.json not found.")
            return render_template('edit_config.html', config={})
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")
            return render_template('edit_config.html', config={})


@app.route('/total_balance')
def total_balance():
    balances_file = 'balances.json'
    
    if os.path.exists(balances_file):
        remove_empty_lines(balances_file)  # Clean up balances file before reading
        with open(balances_file, 'r', encoding='utf-8') as f:
            balances = json.load(f)
        try:
            total_balance = sum(float(balance) for balance in balances.values())
            logger.info(f"Total balance calculated: {total_balance}")
            return jsonify({'total_balance': total_balance})
        except ValueError as e:
            logger.error(f"Error calculating total balance: {str(e)}")
            return jsonify({'error': 'Invalid balance value in balances.json'}), 500
    else:
        logger.warning("balances.json file not found.")
        return jsonify({'total_balance': 0})

@app.route('/reset_bot', methods=['POST'])
def reset_bot():
    global bot_thread, bot_instance

    # Cek apakah bot sedang berjalan
    if bot_thread is not None and bot_thread.is_alive():
        logger.warning("Attempted to reset bot while it is running. Please stop the bot first.")
        return jsonify({'status': 'failed', 'message': 'Please stop the bot first'}), 400

    # Reset bot_state.json
    bot_state_file = 'bot_state.json'
    if os.path.exists(bot_state_file):
        with open(bot_state_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logger.info("Bot state reset successfully.")
    else:
        logger.warning(f"{bot_state_file} not found. No action taken.")
        
    # Reset tokens.json
    tokens_file = 'tokens.json'
    if os.path.exists(tokens_file):
        with open(tokens_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logger.info("Tokens reset successfully.")
    else:
        logger.warning(f"{tokens_file} not found. No action taken.")

    return jsonify({'status': 'success', 'message': 'Bot state and tokens have been reset'})

@app.route('/refresh_balance', methods=['POST'])
def refresh_balance():
    global bot_thread, bot_instance

    # Cek apakah bot sedang berjalan
    if bot_thread is not None and bot_thread.is_alive():
        logger.warning("Attempted to refresh balance while the bot is running. Please stop the bot first.")
        return jsonify({'status': 'failed', 'message': 'Please stop the bot first'}), 400

    # Reset balances.json
    balances_file = 'balances.json'
    if os.path.exists(balances_file):
        with open(balances_file, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logger.info("Balances reset successfully.")
    else:
        logger.warning(f"{balances_file} not found. No action taken.")

    return jsonify({'status': 'success', 'message': 'Balances have been reset'})

def run_bot(bot_instance):
    logger.info("Running the bot instance.")
    bot_instance.load_config()
    bot_instance.main()
    trim_log_file()

def get_access_token(userid):
    tokens_file = 'tokens.json'
    if os.path.exists(tokens_file):
        remove_empty_lines(tokens_file)  # Clean up tokens file before reading
        with open(tokens_file, 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        return tokens.get(str(userid))
    return None

def countdown(t):
    while t:
        minutes, seconds = divmod(t, 60)
        print(f"Countdown: {minutes:02d}:{seconds:02d}", flush=True, end='\r')
        time.sleep(1)
        t -= 1
    print(" " * 30, end="\r")

def load_config():
    config_file_path = 'config.json'
    remove_empty_lines(config_file_path)  # Clean up config file before loading
    with open(config_file_path, 'r', encoding='utf-8') as config_file:
        return json.load(config_file)

if __name__ == '__main__':
    # Ensure log files exist at the start
    open('bot.log', 'a').close()
    open('http.log', 'a').close()

    # Clean all files before starting the app
    clean_all_files()

    host = '0.0.0.0'
    port = 5000
    url = f"http://{host}:{port}/"
    
    logger.info(f"Starting server on {url}")
    print(f"Server running at {url}")  # Menampilkan IP dan Port di terminal

    app.run(debug=True, host=host, port=port)
