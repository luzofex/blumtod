import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify
import threading
import os
import platform
import json

from bot import BlumTod

# Check and create necessary files if they don't exist
required_files = ['proxies.txt', 'data.txt', 'user-agent.txt', 'http.log']
for file_name in required_files:
    if not os.path.exists(file_name):
        with open(file_name, 'w') as file:
            pass  # Just create an empty file
        print(f"{file_name} created.")
    else:
        print(f"{file_name} already exists.")

# Setup logging
logger = logging.getLogger('werkzeug')  # Mengambil logger Flask default
logger.setLevel(logging.INFO)  # Set level untuk logger Flask

# Create a rotating file handler
log_file = 'app.log'
rotating_handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=1)  # BackupCount=1 to keep only one backup
rotating_handler.setLevel(logging.DEBUG)  # Simpan semua log, termasuk DEBUG
file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', '%Y-%m-%d %H:%M:%S')
rotating_handler.setFormatter(file_formatter)

# Create a console handler for logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Hanya tampilkan log INFO ke atas di console
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)

# Add handlers to the logger
logger.addHandler(rotating_handler)
logger.addHandler(console_handler)

# Function to trim the log file to the last 100 lines
def trim_log_file():
    with open(log_file, 'r') as f:
        lines = f.readlines()

    if len(lines) > 100:
        with open(log_file, 'w') as f:
            f.writelines(lines[-100:])

app = Flask(__name__)

app.bot_thread = None
app.bot_instance = None

@app.route('/')
def index():
    logger.info("Accessing the index page.")
    trim_log_file()  # Trim the log file every time the index page is accessed

    next_restart_time = app.bot_instance.get_next_restart_time() if app.bot_instance else "N/A"
    
    return render_template('index.html', next_restart_time=next_restart_time)

@app.route('/next_restart')
def next_restart():
    next_restart_time = app.bot_instance.get_next_restart_time() if app.bot_instance else "N/A"
    return jsonify({'next_restart_time': next_restart_time})

@app.route('/start_bot', methods=['POST'])
def start_bot():
    if app.bot_thread is None or not app.bot_thread.is_alive():
        app.bot_instance = BlumTod()
        app.bot_thread = threading.Thread(target=run_bot, args=(app.bot_instance,))
        app.bot_thread.start()
        logger.info("Bot started.")
        trim_log_file()  # Trim the log file after starting the bot
        return jsonify({'status': 'Bot started'})
    else:
        logger.info("Attempted to start bot, but it's already running.")
        trim_log_file()  # Trim the log file after failed attempt to start the bot
        return jsonify({'status': 'Bot is already running'})

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    if app.bot_instance is not None:
        app.bot_instance.stop()
        app.bot_thread.join()
        logger.info("Bot stopped.")
        trim_log_file()  # Trim the log file after stopping the bot
        return jsonify({'status': 'Bot stopped'})
    else:
        logger.info("Attempted to stop bot, but it was not running.")
        trim_log_file()  # Trim the log file after failed attempt to stop the bot
        return jsonify({'status': 'Bot is not running'})

@app.route('/status')
def status():
    running = app.bot_thread is not None and app.bot_thread.is_alive()
    logger.info(f"Checking bot status: {'running' if running else 'stopped'}.")
    trim_log_file()  # Trim the log file after checking the status
    return jsonify({'running': running})

@app.route('/logs')
def get_logs():
    logs = {}
    
    # Baca bot.log dengan error handling
    bot_log_path = os.path.join(os.path.dirname(__file__), 'bot.log')
    try:
        with open(bot_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['bot_log'] = f.readlines()
        logger.info(f"Read bot.log: {len(logs['bot_log'])} lines.")  # Logging
    except FileNotFoundError:
        logs['bot_log'] = ["bot.log file not found."]
        logger.warning("bot.log file not found.")

    # Baca http.log dengan error handling
    http_log_path = os.path.join(os.path.dirname(__file__), 'http.log')
    try:
        with open(http_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['http_log'] = f.readlines()
        logger.info(f"Read http.log: {len(logs['http_log'])} lines.")  # Logging
    except FileNotFoundError:
        logs['http_log'] = ["http.log file not found."]
        logger.warning("http.log file not found.")

    trim_log_file()  # Trim the log file after accessing logs
    return jsonify(logs)

@app.route('/edit_files')
def edit_files():
    logger.info("Accessing the edit files page.")
    trim_log_file()  # Trim the log file every time the edit files page is accessed
    return render_template('edit_files.html')

@app.route('/edit_file', methods=['GET', 'POST'])
def edit_file():
    if request.method == 'POST':
        file_name = request.form['file_name']
        content = request.form['content']
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        if 'save' in request.form:
            with open(file_path, 'w') as file:
                file.write(content)
            logger.info(f"Saved content to {file_name}.")
            
            if file_name == 'user-agent.txt' and app.bot_instance:
                app.bot_instance.load_user_agents()  # Muat ulang user-agent jika file ini diubah
                
        elif 'delete' in request.form:
            os.remove(file_path)
            logger.info(f"Deleted file {file_name}.")
        trim_log_file()  # Trim the log file after editing a file
        return jsonify({'status': f'{file_name} updated successfully'})
    else:
        file_name = request.args.get('file_name', 'data.txt')
        file_path = os.path.join(os.path.dirname(__file__), file_name)
        try:
            with open(file_path, 'r') as file:
                content = file.read()
            logger.info(f"Read content from {file_name}.")
        except FileNotFoundError:
            content = ''
            logger.warning(f"{file_name} not found.")
        trim_log_file()  # Trim the log file after accessing a file
        return jsonify({'file_name': file_name, 'content': content})

@app.route('/edit_config', methods=['GET', 'POST'])
def edit_config_file():
    config_file_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if request.method == 'POST':
        new_config = request.json
        with open(config_file_path, 'w') as config_file:
            json.dump(new_config, config_file, indent=4)
        logger.info("Updated config.json.")
        trim_log_file()  # Trim the log file after editing the config
        return jsonify({'status': 'Config updated successfully'})
    else:
        logger.info("Accessing the edit config page.")
        trim_log_file()  # Trim the log file after accessing the config
        return render_template('edit_config.html')

@app.route('/total_balance')
def total_balance():
    if app.bot_instance is not None:
        total_balance = app.bot_instance.sum_all_balances()
        logger.info(f"Total balance calculated: {total_balance}")
        return jsonify({'total_balance': total_balance})
    else:
        logger.warning("Attempted to get total balance, but bot instance is not initialized.")
        return jsonify({'total_balance': 0})

def run_bot(bot_instance):
    logger.info("Running the bot instance.")
    bot_instance.load_config()
    bot_instance.main()
    trim_log_file()  # Trim the log file after running the bot

if __name__ == '__main__':
    host = '0.0.0.0'
    port = 5000
    logger.info(f"Starting server on http://{host}:{port}/")
    app.run(debug=True, host=host, port=port)
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')
    trim_log_file()  # Trim the log file after the server starts
