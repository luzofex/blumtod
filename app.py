import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify
import threading
import os
import json
import time
from datetime import datetime
import re
from bot import BlumTod
import portalocker

# Setup Flask and logging
app = Flask(__name__)
bot_instances = {}  # Menyimpan instance bot
bot_threads = {}    # Menyimpan thread bot
bot_json_file = 'bot.json'
bot_state_file = 'bot_state.json'

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


# Load bots from bot.json with locking
def load_bots():
    if os.path.exists(bot_json_file):
        for attempt in range(5):  # Retry mechanism
            try:
                with open(bot_json_file, 'r', encoding='utf-8') as f:
                    portalocker.lock(f, portalocker.LOCK_SH)  # Shared lock for reading
                    bot_names = json.load(f)
                    portalocker.unlock(f)
                break
            except portalocker.LockException:
                logger.warning(f"Could not acquire lock for {bot_json_file}, retrying...")
                time.sleep(2)  # Retry after delay
        else:
            logger.error(f"Failed to load {bot_json_file} after 5 attempts.")
            return []

        for bot_name in bot_names:
            bot_instances[bot_name] = BlumTod(bot_name=bot_name)  # Inisialisasi bot instance
        return bot_names
    return []

# Save bots to bot.json with locking
def save_bots():
    for attempt in range(5):  # Retry mechanism
        try:
            with open(bot_json_file, 'w', encoding='utf-8') as f:
                portalocker.lock(f, portalocker.LOCK_EX)  # Exclusive lock for writing
                json.dump(list(bot_instances.keys()), f, indent=4)
                portalocker.unlock(f)
            break
        except portalocker.LockException:
            logger.warning(f"Could not acquire lock for {bot_json_file}, retrying...")
            time.sleep(2)  # Retry after delay
    else:
        logger.error(f"Failed to save {bot_json_file} after 5 attempts.")

# Function to trim the log file to the last 100 lines
def trim_log_file():
    with open(log_file, 'r') as f:
        lines = f.readlines()

    if len(lines) > 100:
        with open(log_file, 'w') as f:
            f.writelines(lines[-100:])

def log_message(message):
    logger.info(message)

# Fungsi untuk menjalankan bot
def run_bot(bot_instance):
    logger.info("Running the bot instance.")
    bot_instance.load_config()
    bot_instance.main()
    trim_log_file()

@app.route('/')
def index():
    logger.info("Accessing the index page.")
    trim_log_file()
    return render_template('index.html')


@app.route('/create_bot', methods=['POST'])
def create_bot():
    bot_name = request.json.get('bot_name')  # Ambil nama bot dari request

    if not bot_name:
        return jsonify({'status': 'failed', 'message': 'Bot name is required'}), 400

    if bot_name in bot_instances:
        return jsonify({'status': 'failed', 'message': f'Bot {bot_name} already exists'}), 400

    # Inisialisasi bot baru tanpa menjalankannya
    bot_instance = BlumTod(bot_name=bot_name)
    bot_instances[bot_name] = bot_instance

    # Simpan informasi bot ke bot.json
    save_bots()  # Make sure this is called correctly

    logger.info(f"Bot '{bot_name}' created (not started).")
    return jsonify({'status': 'success', 'message': f'Bot {bot_name} created (not started)'})
### Menghapus Bot yang Dipilih
@app.route('/delete_bot', methods=['POST'])
def delete_bot():
    bot_name = request.json.get('bot_name')

    if not bot_name or bot_name not in bot_instances:
        return jsonify({'status': 'failed', 'message': 'Bot not found or invalid name'}), 400

    # Stop the bot if running
    if bot_name in bot_threads and bot_threads[bot_name].is_alive():
        bot_instances[bot_name].stop()
        bot_threads[bot_name].join()

    # Remove bot from the dictionaries
    del bot_instances[bot_name]
    del bot_threads[bot_name]

    # Update the bot.json file
    save_bots()

    logger.info(f"Bot '{bot_name}' deleted.")
    return jsonify({'status': 'success', 'message': f'Bot {bot_name} has been deleted'})

### Menampilkan Daftar Bot yang Sedang Berjalan
@app.route('/bot_list', methods=['GET'])
def bot_list():
    bot_list = list(bot_instances.keys())  # Mengambil nama bot dari bot_instances, bukan bot_threads
    logger.info(f"Current bots: {bot_list}")  # Logging untuk melihat daftar bot
    return jsonify({'bots': bot_list})


@app.route('/start_bot', methods=['POST'])
def start_bot():
    bot_name = request.json.get('bot_name', 'DefaultBot')  # Ambil nama bot dari request POST

    if bot_name not in bot_instances:
        return jsonify({'status': 'failed', 'message': 'Bot does not exist. Please create a bot first.'}), 400

    if bot_name not in bot_threads or not bot_threads[bot_name].is_alive():
        bot_instance = bot_instances[bot_name]
        if not bot_instance.running:  # Pastikan bot belum berjalan
            bot_instance.running = True  # Atur bot untuk berjalan
            bot_thread = threading.Thread(target=run_bot, args=(bot_instance,))
            bot_thread.start()

            # Simpan bot instance dan thread ke dalam dictionary
            bot_threads[bot_name] = bot_thread

            logger.info(f"Bot '{bot_name}' started.")
            trim_log_file()
            return jsonify({'status': f"Bot '{bot_name}' started"})
        else:
            return jsonify({'status': 'failed', 'message': f'Bot {bot_name} is already running'}), 400
    else:
        logger.info(f"Attempted to start bot '{bot_name}', but it's already running.")
        trim_log_file()
        return jsonify({'status': f"Bot '{bot_name}' is already running"})


@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    bot_name = request.json.get('bot_name', 'DefaultBot')  # Ambil nama bot dari request

    if bot_name in bot_instances and bot_threads[bot_name].is_alive():
        bot_instances[bot_name].stop()  # Panggil fungsi stop pada bot yang sesuai
        bot_threads[bot_name].join()  # Tunggu hingga thread selesai
        logger.info(f"Bot '{bot_name}' stopped.")
        
        # Hapus bot instance dan thread dari dictionary setelah dihentikan
        bot_instances[bot_name] = BlumTod(bot_name=bot_name)  # Re-inisialisasi bot setelah stop
        del bot_threads[bot_name]

        trim_log_file()
        return jsonify({'status': f"Bot '{bot_name}' stopped"})
    else:
        logger.info(f"Attempted to stop bot '{bot_name}', but it was not running.")
        trim_log_file()
        return jsonify({'status': f"Bot '{bot_name}' is not running"})

@app.route('/status', methods=['GET'])
def status():
    bot_name = request.args.get('bot_name', 'DefaultBot')  # Ambil nama bot dari parameter URL

    if bot_name in bot_threads and bot_threads[bot_name].is_alive():
        running = True
    else:
        running = False
    
    logger.info(f"Checking status of bot '{bot_name}': {'running' if running else 'stopped'}.")
    trim_log_file()
    return jsonify({'bot_name': bot_name, 'running': running})


# Fungsi untuk membaca log HTTP berdasarkan bot
@app.route('/logs', methods=['GET'])
def get_logs():
    bot_name = request.args.get('bot_name', 'DefaultBot')  # Ambil nama bot dari parameter URL
    logs = {}

    # Path log file HTTP untuk setiap bot
    bot_log_path = f'bot_{bot_name}.log'  # Path log file sesuai nama bot
    http_log_path = f'http_{bot_name}.log'  # Path log HTTP sesuai nama bot

    # Baca log bot yang dipilih
    if os.path.exists(bot_log_path):
        with open(bot_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['bot_log'] = format_logs(f.readlines())
        logger.info(f"Read {bot_log_path}: {len(logs['bot_log'])} lines.")
    else:
        logs['bot_log'] = ["bot.log file not found."]
        logger.warning(f"{bot_log_path} file not found.")

    # Baca log HTTP untuk bot yang dipilih
    if os.path.exists(http_log_path):
        with open(http_log_path, 'r', encoding='utf-8', errors='replace') as f:
            logs['http_log'] = format_logs(f.readlines())
        logger.info(f"Read {http_log_path}: {len(logs['http_log'])} lines.")
    else:
        logs['http_log'] = ["http.log file not found."]
        logger.warning(f"{http_log_path} file not found.")

    return jsonify(logs)


@app.route('/bot_info', methods=['GET'])
def get_bot_info():
    try:
        # Membaca informasi dari bot_state.json
        with open(bot_state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        processed_accounts = data.get('processed_accounts', [])
        first_account_time = data.get('first_account_time', 'Not Available')
        next_restart_time = data.get('next_restart_time', 'Not Available')

        # Mengirimkan informasi sebagai JSON
        return jsonify({
            'processed_accounts': processed_accounts,
            'first_account_time': first_account_time,
            'next_restart_time': next_restart_time
        })
    
    except FileNotFoundError:
        return jsonify({
            'error': 'bot_state.json not found',
            'processed_accounts': [],
            'first_account_time': None,
            'next_restart_time': None
        }), 404

    except Exception as e:
        logger.error(f"Error while loading bot_state.json: {str(e)}")
        return jsonify({'error': 'An error occurred while reading bot_state.json'}), 500


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

def post_edit_cleanup(file_path):
    remove_empty_lines(file_path)

def clean_all_files():
    files_to_clean = ['data.txt', 'user-agent.txt', 'proxies.txt', 'config.json']
    for file in files_to_clean:
        remove_empty_lines(file)

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


@app.route('/total_balance', methods=['GET'])
def total_balance():
    balances_file = 'balances.json'

    # Cek apakah file balances.json ada
    if os.path.exists(balances_file):
        try:
            # Baca file balances.json
            with open(balances_file, 'r', encoding='utf-8') as f:
                balances = json.load(f)

            total_balance = 0.0

            # Loop melalui setiap balance dan tambahkan ke total_balance
            for user, balance in balances.items():
                try:
                    # Pastikan balance bisa dikonversi ke float
                    float_balance = float(balance)
                    total_balance += float_balance
                except ValueError as e:
                    logger.error(f"Invalid balance value for user {user}: {balance}. Error: {str(e)}")
                    return jsonify({'error': f'Invalid balance value for user {user}'}), 500

            # Kembalikan total balance
            logger.info(f"Total balance calculated: {total_balance}")
            return jsonify({'total_balance': total_balance})

        except json.JSONDecodeError as e:
            logger.error(f"Error reading balances.json: {str(e)}")
            return jsonify({'error': 'Failed to parse balances.json'}), 500

    else:
        # Jika balances.json tidak ditemukan, kembalikan total balance 0
        logger.warning(f"{balances_file} not found.")
        return jsonify({'total_balance': 0}), 404




@app.route('/bot_count', methods=['GET'])
def bot_count():
    running_bots = len([bot for bot in bot_threads.values() if bot.is_alive()])  # Menghitung bot yang sedang berjalan
    return jsonify({'running_bots': running_bots})

@app.route('/start_all_bots', methods=['POST'])
def start_all_bots():
    for bot_name, bot_instance in bot_instances.items():
        if bot_name not in bot_threads or not bot_threads[bot_name].is_alive():
            bot_thread = threading.Thread(target=run_bot, args=(bot_instance,))
            bot_thread.start()
            bot_threads[bot_name] = bot_thread
            logger.info(f"Bot '{bot_name}' started.")
            
            # Jeda 2 detik sebelum memulai bot berikutnya
            time.sleep(2)
        else:
            logger.info(f"Bot '{bot_name}' is already running.")
    
    return jsonify({'status': 'All bots started'})


# Endpoint untuk menghentikan semua bot
@app.route('/stop_all_bots', methods=['POST'])
def stop_all_bots():
    for bot_name, bot_thread in bot_threads.items():
        if bot_thread.is_alive():
            bot_instances[bot_name].stop()
            bot_thread.join()
            logger.info(f"Bot '{bot_name}' stopped.")
    # Hapus semua thread dari dictionary setelah dihentikan
    bot_threads.clear()
    return jsonify({'status': 'All bots stopped'})

# Endpoint untuk mendapatkan IP bot
@app.route('/get_bot_ip', methods=['GET'])
def get_bot_ip():
    bot_name = request.args.get('bot_name')
    
    if not bot_name or bot_name not in bot_instances:
        return jsonify({'status': 'failed', 'message': 'Bot not found'}), 404
    
    bot_instance = bot_instances[bot_name]
    bot_ip = bot_instance.get_ip()  # Pastikan Anda memiliki fungsi get_ip di BlumTod
    
    return jsonify({'bot_name': bot_name, 'ip': bot_ip})

# Endpoint untuk mendapatkan akun yang sedang diproses oleh bot
@app.route('/get_processing_account', methods=['GET'])
def get_processing_account():
    bot_name = request.args.get('bot_name')
    
    if not bot_name or bot_name not in bot_instances:
        return jsonify({'status': 'failed', 'message': 'Bot not found'}), 404
    
    bot_instance = bot_instances[bot_name]
    processing_account = bot_instance.get_current_account()  # Pastikan Anda memiliki fungsi get_current_account di BlumTod
    
    return jsonify({'bot_name': bot_name, 'processing_account': processing_account})


# Modifikasi metode reset bot untuk menggunakan retry mechanism yang sama
@app.route('/reset_bot', methods=['POST'])
def reset_bot():
    # Cek apakah ada bot yang sedang berjalan
    if any(bot_thread.is_alive() for bot_thread in bot_threads.values()):
        return jsonify({'status': 'failed', 'message': 'Cannot reset. Stop all bots first.'}), 400

    # Reset semua log file dan bot_state.json dengan penguncian
    for attempt in range(5):  # Retry mechanism untuk penguncian
        try:
            with open(bot_state_file, 'w', encoding='utf-8') as f:
                portalocker.lock(f, portalocker.LOCK_EX)  # Penguncian eksklusif
                json.dump({}, f, indent=4)  # Reset bot_state.json
                portalocker.unlock(f)
            logger.info(f"{bot_state_file} reset successfully.")
            break
        except portalocker.LockException:
            logger.warning(f"Attempt {attempt + 1}: Could not acquire lock for {bot_state_file}, retrying...")
            time.sleep(2)  # Coba ulang setelah jeda waktu
    else:
        # Jika gagal setelah 5 kali percobaan
        logger.error(f"Failed to reset {bot_state_file} after 5 attempts.")
        return jsonify({'status': 'failed', 'message': f'Failed to reset {bot_state_file}'}), 500

    # Reset log file untuk setiap bot
    for bot_name in bot_instances.keys():
        bot_log_file = f'bot_{bot_name}.log'
        http_log_file = f'http_{bot_name}.log'

        if os.path.exists(bot_log_file):
            open(bot_log_file, 'w').close()  # Mengosongkan log file
            logger.info(f"Log file {bot_log_file} reset.")

        if os.path.exists(http_log_file):
            open(http_log_file, 'w').close()  # Mengosongkan HTTP log file
            logger.info(f"HTTP log file {http_log_file} reset.")

    # Hapus isi file tokens.json dengan menulis {}
    tokens_file = 'tokens.json'
    if os.path.exists(tokens_file):
        with open(tokens_file, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=4)  # Mengosongkan isi dengan {}
        logger.info(f"{tokens_file} has been reset to an empty object.")

    logger.info("All bot states, log files, and tokens.json have been reset.")
    return jsonify({'status': 'success', 'message': 'All bot states, log files, and tokens.json have been reset.'})

@app.route('/refresh_balance', methods=['POST'])
def refresh_balance():
    balances_file = 'balances.json'  # Menggunakan balances.json umum untuk semua bot

    # Cek apakah ada bot yang sedang berjalan
    if any(bot_thread.is_alive() for bot_thread in bot_threads.values()):
        return jsonify({'status': 'failed', 'message': 'Cannot refresh balance while bots are running. Stop all bots first.'}), 400

    # Lakukan penguncian dan reset balances.json
    for attempt in range(5):  # Retry mechanism untuk penguncian
        try:
            with open(balances_file, 'w', encoding='utf-8') as f:
                portalocker.lock(f, portalocker.LOCK_EX)  # Penguncian eksklusif
                json.dump({}, f, indent=4)  # Reset isi balances.json
                portalocker.unlock(f)
            logger.info(f"Balances file {balances_file} reset successfully.")
            break  # Jika sukses, keluar dari loop
        except portalocker.LockException:
            logger.warning(f"Attempt {attempt + 1}: Could not acquire lock for {balances_file}, retrying...")
            time.sleep(2)  # Coba ulang setelah jeda waktu
    else:
        # Jika gagal setelah 5 kali percobaan
        logger.error(f"Failed to reset balances after 5 attempts.")
        return jsonify({'status': 'failed', 'message': 'Failed to reset balances after multiple attempts.'}), 500
 
    return jsonify({'status': 'success', 'message': 'Balances have been reset successfully'})

 
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

    # Load bots from bot.json before starting the app
    bots = load_bots()
    for bot_name in bots:
        bot_instances[bot_name] = BlumTod(bot_name=bot_name)  # Bot tersedia tetapi tidak dimulai

    # Clean all files before starting the app
    clean_all_files()

    host = '0.0.0.0'
    port = 5000
    url = f"http://{host}:{port}/"
    
    logger.info(f"Starting server on {url}")
    print(f"Server running at {url}")  # Menampilkan IP dan Port di terminal

    app.run(debug=True, host=host, port=port)
