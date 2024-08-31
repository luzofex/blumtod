from flask import Flask, render_template, request, jsonify
import threading
import os
import platform

# Impor kelas BlumTod dari bot.py yang berada di direktori yang sama
from bot import BlumTod

app = Flask(__name__)

# Inisialisasi bot di sini
app.bot_thread = None
app.bot_instance = None  # Tambahkan ini untuk menyimpan referensi ke objek bot

@app.route('/')
def index():
    # Halaman utama yang menampilkan status bot, kontrol, dan log
    return render_template('index.html')

@app.route('/start_bot', methods=['POST'])
def start_bot():
    if app.bot_thread is None or not app.bot_thread.is_alive():
        app.bot_instance = BlumTod()  # Buat instance dari BlumTod
        app.bot_thread = threading.Thread(target=run_bot, args=(app.bot_instance,))
        app.bot_thread.start()
        return jsonify({'status': 'Bot started'})
    else:
        return jsonify({'status': 'Bot is already running'})

@app.route('/stop_bot', methods=['POST'])
def stop_bot():
    if app.bot_instance is not None:
        app.bot_instance.stop()  # Panggil metode stop pada bot instance
        app.bot_thread.join()  # Tunggu thread selesai
        return jsonify({'status': 'Bot stopped'})
    else:
        return jsonify({'status': 'Bot is not running'})

@app.route('/status')
def status():
    # Kembalikan status bot, apakah sedang berjalan atau tidak
    running = app.bot_thread is not None and app.bot_thread.is_alive()
    return jsonify({'running': running})

@app.route('/log')
def log():
    # Tentukan path file bot.log secara eksplisit
    log_file_path = os.path.join(os.path.dirname(__file__), 'bot.log')
    print(f"Looking for log file at: {log_file_path}")  # Debugging tambahan untuk memastikan lokasi file

    try:
        with open(log_file_path, 'r') as f:
            log_content = f.readlines()
        return jsonify({"log": log_content})
    except FileNotFoundError:
        return jsonify({"log": ["Log file not found."]})

def run_bot(bot_instance):
    # Fungsi ini menjalankan bot Anda
    bot_instance.load_config()
    bot_instance.main()

if __name__ == '__main__':
    # Tentukan command untuk membersihkan layar sesuai dengan OS
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')

    app.run(debug=True, host='0.0.0.0', port=5000)
