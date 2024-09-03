import os
import sys
import time
import json
import random
import requests
import argparse
from json import dumps as dp, loads as ld
from datetime import datetime, timedelta
from colorama import *
from urllib.parse import unquote, parse_qs
from base64 import b64decode
import pytz
import re
import signal
import socket

init(autoreset=True)

# Definisikan timezone untuk Waktu Indonesia Barat (WIB)
WIB = pytz.timezone('Asia/Jakarta')

# Warna untuk output terminal
merah = Fore.LIGHTRED_EX
putih = Fore.LIGHTWHITE_EX
hijau = Fore.LIGHTGREEN_EX
kuning = Fore.LIGHTYELLOW_EX
biru = Fore.LIGHTBLUE_EX
reset = Style.RESET_ALL
hitam = Fore.LIGHTBLACK_EX
magenta = Fore.LIGHTMAGENTA_EX

retry_counter = 0
required_files = ['user-agent.txt', 'data.txt', 'proxies.txt']

# Cek dan buat file jika belum ada
for file_path in required_files:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            pass  # Buat file kosong
        print(f"{file_path} created.")
    else:
        print(f"{file_path} already exists.")


def stop(self):
    """Menghentikan bot dengan mengirimkan sinyal SIGINT, seperti menekan Ctrl+C."""
    self.log(f"Stopping the bot...")
    self.running = False
    os.kill(os.getpid(), signal.SIGINT)

def is_connected(hostname="8.8.8.8", port=53, timeout=3):
    """Fungsi untuk memeriksa apakah ada koneksi internet"""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((hostname, port))
        return True
    except socket.error as ex:
        return False

# Fungsi untuk membaca file dan mengabaikan baris kosong
def load_file_lines(file_path):
    """Membaca baris dari file dan mengabaikan baris kosong."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

# Mengimpor User-Agent dari file
def load_user_agents(file_path='user-agent.txt'):
    return load_file_lines(file_path)

# Menyimpan User-Agent yang dipilih untuk setiap akun
account_user_agents = {}

def random_delay(min_delay=2, max_delay=5):
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

class BlumTod:
    def __init__(self):
        self.running = True
        self.stop_requested = False
        self.restart_requested = False
        self.base_headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://telegram.blum.codes",
            "x-requested-with": "org.telegram.messenger",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://telegram.blum.codes/",
            "accept-encoding": "gzip, deflate",
            "accept-language": "en,en-US;q=0.9",
        }
        self.garis = putih + "~" * 50
        self.state_file = "bot_state.json"
        self.processed_accounts = set()
        self.first_account_time = None
        self.next_restart_time = None
        self.remaining_delay = None
        self.user_agents = load_user_agents()
        self.use_proxy = False
        self.proxies = []

    def restart_bot(self):
        self.log("Restarting the bot...")
        self.save_state()
       # self.main()  # Panggil ulang fungsi main
        self.running = True
        self.main() 
       # os.execl(sys.executable, sys.executable, *sys.argv)  # Restart bot dengan menjalankan ulang script


    def stop(self):
        self.running = False
        self.log(f"Stopping the bot...")
        self.log(f"Bot stopped")

    def save_state(self):
        """Menyimpan status akun yang sudah diproses ke file"""
        state = {
            "processed_accounts": list(self.processed_accounts),
            "first_account_time": self.first_account_time.isoformat() if self.first_account_time else None,
            "next_restart_time": self.next_restart_time.isoformat() if self.next_restart_time else None
        }
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f)

    def request_stop(self):
        """Mengatur flag untuk menghentikan bot segera."""
        self.stop_requested = True
        self.log("Stop requested. The bot will stop immediately.")
        self.running = False

    def check_for_stop(self):
        """Periksa apakah stop telah diminta dan keluar jika iya."""
        if self.stop_requested:
            self.log("Stopping the bot immediately.")
            sys.exit(0)

    def load_state(self):
        """Memuat status akun yang sudah diproses dari file"""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                self.processed_accounts = set(state.get("processed_accounts", []))

                first_account_time_str = state.get("first_account_time", None)
                if first_account_time_str:
                    self.first_account_time = datetime.fromisoformat(first_account_time_str).astimezone(WIB)

                next_restart_time_str = state.get("next_restart_time", None)
                if next_restart_time_str:
                    self.next_restart_time = datetime.fromisoformat(next_restart_time_str).astimezone(WIB)
        else:
            self.save_state()

    def get_user_agent_for_account(self, account_number):
        """Mengembalikan User-Agent yang sama untuk setiap akun"""
        if not self.user_agents:
            self.log(f"{merah}Error: User-agent list is empty.")
            return None
        
        if account_number not in account_user_agents:
            account_user_agents[account_number] = self.user_agents[account_number % len(self.user_agents)]
        return account_user_agents[account_number]

    def renew_access_token(self, tg_data):
        headers = self.base_headers.copy()
        data = dp({"query": tg_data})
        headers["Content-Length"] = str(len(data))
        url = "https://gateway.blum.codes/v1/auth/provider/PROVIDER_TELEGRAM_MINI_APP"
        res = self.http(url, headers, data)
        if res is None:
            self.log(f"{merah}Failed to fetch token from gateway.")
            return False

        try:
            token = res.json().get("token")
        except ValueError:
            self.log(f"{merah}Failed to parse JSON response for token.")
            return False

        if token is None:
            self.log(f"{merah}'token' is not found in response, check your data !!")
            return False

        access_token = token["access"]
        self.log(f"{hijau}success get access token ")
        return access_token

    def solve_task(self, access_token):
        if not self.running:
            return
        url_task = "https://game-domain.blum.codes/api/v1/tasks"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url_task, headers)
        if res is None:
            self.log(f"{merah}Failed to fetch tasks.")
            return

        try:
            tasks_list = res.json()
        except ValueError:
            self.log(f"{merah}Failed to parse task list.")
            return

        for tasks in tasks_list:
            if not self.running:
                break
            if isinstance(tasks, str):
                self.log(f"{kuning}failed get task list !")
                return
            for task in tasks.get("tasks", []):
                if not self.running:
                    break
                task_id = task.get("id")
                task_status = task.get("status")
                if task_status == "NOT_STARTED":
                    self.start_and_claim_task(task_id, headers)
                else:
                    self.log(f"{kuning}already complete task {task_id} !")

    def start_and_claim_task(self, task_id, headers):
        url_start = f"https://game-domain.blum.codes/api/v1/tasks/{task_id}/start"
        res = self.http(url_start, headers, "")
        if res is None or "message" in res.text:
            return

        url_claim = f"https://game-domain.blum.codes/api/v1/tasks/{task_id}/claim"
        res = self.http(url_claim, headers, "")
        if res is None or "message" in res.text:
            return

        status = res.json().get("status")
        if status == "CLAIMED":
            self.log(f"{hijau}success complete task {task_id} !")
            random_delay(1, 3)

    def set_proxy(self, proxy=None):
        self.ses = requests.Session()
        if proxy is not None:
            self.ses.proxies.update({"http": proxy, "https": proxy})

    def claim_farming(self, access_token):
        if not self.running:
            return 0
        url = "https://game-domain.blum.codes/api/v1/farming/claim"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers, "")
        if res is None:
            self.log(f"{merah}Failed to claim farming balance.")
            return 0

        balance = res.json().get("availableBalance", 0)
        self.log(f"{hijau}balance after claim : {putih}{balance}")
        return balance

    def get_balance(self, access_token, only_show_balance=False):
        if not self.running:
            return 0
        url = "https://game-domain.blum.codes/api/v1/user/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        
        while True:
            res = self.http(url, headers)
            if res is None:
                self.log(f"{merah}Failed to fetch balance, retrying...")
                self.countdown(3)
                continue

            balance = res.json().get("availableBalance", 0)
            self.log(f"{hijau}balance : {putih}{balance}")
            
            if only_show_balance:
                return balance

            timestamp = res.json().get("timestamp")
            if timestamp is None:
                self.countdown(3)
                continue
            
            timestamp = round(timestamp / 1000)
            
            if "farming" not in res.json().keys():
                return False, "not_started", balance

            end_farming = res.json().get("farming", {}).get("endTime")
            if end_farming is None:
                self.countdown(3)
                continue

            end_farming = round(end_farming / 1000)
            
            if timestamp > end_farming:
                self.log(f"{hijau}now is time to claim farming !")
                return True, end_farming, balance

            self.log(f"{kuning}not time to claim farming !")
            end_date = datetime.fromtimestamp(end_farming)
            self.log(f"{hijau}end farming : {putih}{end_date}")
            random_delay(1, 3)
            return False, end_farming, balance

    def start_farming(self, access_token):
        if not self.running:
            return 0
        url = "https://game-domain.blum.codes/api/v1/farming/start"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        
        while True:
            res = self.http(url, headers, "")
            if res is None:
                self.log(f"{merah}Failed to start farming, retrying...")
                self.countdown(3)
                continue

            try:
                end = res.json().get("endTime")
            except ValueError:
                self.log(f"{merah}Failed to parse JSON response for farming.")
                self.countdown(3)
                continue

            if end is None:
                self.countdown(3)
                continue
            break

        end_date = datetime.fromtimestamp(end / 1000)
        self.log(f"{hijau}start farming successfully !")
        self.log(f"{hijau}end farming : {putih}{end_date}")
        random_delay(1, 3)
        return round(end / 1000)

    def get_friend(self, access_token):
        if not self.running:
            return
        url = "https://gateway.blum.codes/v1/friends/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers)
        if res is None:
            self.log(f"{merah}Failed to fetch friend balance.")
            return

        try:
            can_claim = res.json().get("canClaim", False)
            limit_invite = res.json().get("limitInvitation", 0)
            amount_claim = res.json().get("amountForClaim")
        except ValueError:
            self.log(f"{merah}Failed to parse JSON response for friend balance.")
            return

        self.log(f"{putih}limit invitation : {hijau}{limit_invite}")
        self.log(f"{hijau}referral balance : {putih}{amount_claim}")
        self.log(f"{putih}can claim referral : {hijau}{can_claim}")
        if can_claim:
            url_claim = "https://gateway.blum.codes/v1/friends/claim"
            res = self.http(url_claim, headers, "")
            if res is None or res.json().get("claimBalance") is None:
                self.log(f"{merah}failed claim referral bonus !")
            else:
                self.log(f"{hijau}success claim referral bonus !")
            random_delay(1, 3)
        random_delay(1, 3)

    def checkin(self, access_token):
        if not self.running:
            return
        url = "https://game-domain.blum.codes/api/v1/daily-reward?offset=-420"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers)
        if res is None:
            self.log(f"{merah}Failed to perform daily check-in.")
            return

        if res.status_code == 404:
            self.log(f"{kuning}already check in today !")
            return

        res = self.http(url, headers, "")
        if res is None or "ok" not in res.text.lower():
            self.log(f"{merah}failed check in today !")
        else:
            self.log(f"{hijau}success check in today !")
        random_delay(1, 3)

    def playgame(self, access_token):
        if not self.running:
            return

        url_play = "https://game-domain.blum.codes/api/v1/game/play"
        url_claim = "https://game-domain.blum.codes/api/v1/game/claim"
        url_balance = "https://game-domain.blum.codes/api/v1/user/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        
        max_retries = 5
        retries = 0

        while self.running:
            res = self.http(url_balance, headers)
            if res is None or res.status_code != 200:
                self.log(f"{merah}Failed to fetch balance, skipping playgame.")
                return

            try:
                play = res.json().get("playPasses")
            except ValueError:
                self.log(f"{merah}Failed to parse JSON response for balance. Raw response: {res.text}")
                return

            if play is None or play <= 0:
                self.log(f"{kuning}No game tickets available.")
                return

            self.log(f"{hijau}You have {putih}{play}{hijau} game ticket(s).")

            for _ in range(play):
                if not self.running:
                    break

                if self.is_expired(access_token):
                    return True

                res = self.http(url_play, headers, "")
                if res is None or res.status_code != 200:
                    self.log(f"{merah}Failed to start game, skipping.")
                    retries += 1
                    if retries >= max_retries:
                        self.log(f"{merah}Max retries reached, exiting game loop.")
                        return
                    random_delay(1, 3)
                    continue

                try:
                    game_id = res.json().get("gameId")
                except ValueError:
                    self.log(f"{merah}Failed to parse JSON response for game play. Raw response: {res.text}")
                    retries += 1
                    if retries >= max_retries:
                        self.log(f"{merah}Max retries reached, exiting game loop.")
                        return
                    continue

                if game_id is None:
                    message = res.json().get("message", "")
                    self.log(f"{kuning}{message}, will try again in the next round.")
                    retries += 1
                    if retries >= max_retries:
                        self.log(f"{merah}Max retries reached, exiting game loop.")
                        return
                    random_delay(1, 3)
                    continue

                retries = 0
                while True:
                    self.countdown(30)

                    point = random.randint(self.MIN_WIN, self.MAX_WIN)
                    data = json.dumps({"gameId": game_id, "points": point})
                    res = self.http(url_claim, headers, data)

                    if res is None or res.status_code != 200:
                        self.log(f"{merah}Failed to claim points. Moving to the next game.")
                        break

                    try:
                        if "OK" in res.text:
                            self.log(f"{hijau}Successfully earned {putih}{point}{hijau} points!")
                            break
                        else:
                            message = res.json().get("message", "")
                            if message == "game session not found" or message == "game session not finished":
                                self.log(f"{merah}{message}, moving to the next game.")
                                break
                    except ValueError:
                        self.log(f"{merah}Failed to parse JSON response for claim. Raw response: {res.text}")
                        break

                    random_delay(1, 3)
                    break

    def data_parsing(self, data):
        return {k: v[0] for k, v in parse_qs(data).items()}

    def log(self, message):
        now = datetime.now(WIB).isoformat(" ").split(".")[0]
        log_message = f"{now} {message}"
        print(f"{hitam}[{now}]{reset} {message}")
        clean_message = re.sub(r'\x1b\[[0-9;]*m', '', log_message)
        with open("bot.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"{clean_message}\n")
        self.trim_log_file()

    def trim_log_file(self):
        """Trim the bot.log file to only keep the last 100 lines."""
        log_file = "bot.log"
        try:
            with open(log_file, 'r', encoding="utf-8", errors='replace') as file:
                lines = file.readlines()

            if len(lines) > 100:
                with open(log_file, 'w', encoding="utf-8") as file:
                    file.writelines(lines[-100:])
        except Exception as e:
            print(f"Failed to trim log file: {str(e)}")
            self.log(f"{merah}Failed to trim log file: {str(e)}")

    def get_local_token(self, userid):
        if not os.path.exists("tokens.json"):
            open("tokens.json", "w", encoding="utf-8").write(json.dumps({}))
        tokens = json.loads(open("tokens.json", "r", encoding="utf-8").read())
        return tokens.get(str(userid), False)

    def save_local_token(self, userid, token):
        tokens = json.loads(open("tokens.json", "r", encoding="utf-8").read())
        tokens[str(userid)] = token
        open("tokens.json", "w", encoding="utf-8").write(json.dumps(tokens, indent=4))

    def is_expired(self, token):
        try:
            header, payload, sign = token.split(".")
            payload = b64decode(payload + "==").decode()
            jload = json.loads(payload)
            now = round(datetime.now().timestamp()) + 300
            exp = jload["exp"]
            if now > exp:
                return True
        except Exception as e:
            self.log(f"{merah}Invalid JWT token detected: {str(e)}")
            return True
        return False

    def save_failed_token(self, userid, data):
        file = "auth_failed.json"
        if not os.path.exists(file):
            open(file, "w", encoding="utf-8").write(json.dumps({}))
        acc = json.loads(open(file, "r", encoding="utf-8").read())
        if str(userid) not in acc:
            acc[str(userid)] = data
            open(file, "w", encoding="utf-8").write(json.dumps(acc, indent=4))

    def save_account_balance(self, account_name, balance):
        """Simpan balance ke balances.json menggunakan nama akun sebagai kunci."""
        if not os.path.exists("balances.json"):
            open("balances.json", "w", encoding="utf-8").write(json.dumps({}))
        balances = json.loads(open("balances.json", "r", encoding="utf-8").read())
        balances[account_name] = balance or 0
        with open("balances.json", "w", encoding="utf-8") as f:
            json.dump(balances, f, indent=4)

    def update_balance(self, access_token, new_balance):
        """Update balances.json with the new balance for the user."""
        try:
            userid = self.get_user_id_from_token(access_token)
            if userid:
                self.save_account_balance(userid, new_balance)
        except Exception as e:
            self.log(f"{merah}Failed to update balance in balances.json: {str(e)}")

    def get_user_id_from_token(self, token):
        """Extract user ID from the access token."""
        try:
            payload = json.loads(b64decode(token.split(".")[1] + "==").decode())
            return str(payload.get("sub"))
        except Exception as e:
            self.log(f"{merah}Failed to parse user ID from token: {str(e)}")
            return None

    def check_and_save_balance(self, access_token, account_name):
        """Mengirim permintaan ke server untuk mengecek balance akun dan menyimpannya."""
        balance = self.get_balance(access_token, only_show_balance=True)
        if balance is not None:
            self.save_account_balance(account_name, balance)
            self.log(f"{hijau}Balance for {account_name} saved: {putih}{balance}")
        else:
            self.log(f"{merah}Failed to retrieve balance for {account_name}")

    def process_account(self, account, access_token, save_state_callback):
        try:
            account_name = account['user']['first_name']
            self.log(f"Processing account for user: {account_name}")

            session_user_agent = self.get_user_agent_for_account(account['query_id'])
            if session_user_agent:
                self.base_headers["user-agent"] = session_user_agent
                self.log(f"Using User-Agent: {session_user_agent}")
            else:
                self.log(f"Skipping account due to empty user-agent list.")
                return {"status": "error", "message": "User-Agent list is empty."}

            if self.use_proxy:
                proxy = self.proxies[account['query_id'] % len(self.proxies)]
                self.set_proxy(proxy)
                self.ipinfo()

            if not access_token:
                access_token = self.renew_access_token(account['user'])
                if not access_token:
                    self.save_failed_token(account_name, account)
                    return {"status": "error", "message": "Failed to renew access token"}

                self.save_local_token(account['user']['id'], access_token)

            if self.is_expired(access_token):
                self.log(f"{merah}Access token is expired or invalid. Moving to the next account.")
                return {"status": "error", "message": "Access token expired"}

            self.checkin(access_token)
            self.get_friend(access_token)
            if self.AUTOTASK:
                self.solve_task(access_token)

            status, res_bal, balance = self.get_balance(access_token)
            if status:
                res_bal = self.claim_farming(access_token)
                self.start_farming(access_token)
            if isinstance(res_bal, str):
                self.start_farming(access_token)
            if self.AUTOGAME:
                balance = self.playgame(access_token)

            self.check_and_save_balance(access_token, account_name)
            save_state_callback(account_name, {"balance": balance})

            return {"status": "success", "balance": balance}

        except Exception as e:
            self.log(f"Error processing account for {account_name}: {str(e)}")
            return {"status": "error", "message": str(e)}

    def sum_all_balances(self):
        """Menjumlahkan semua balance yang ada di balances.json."""
        if not os.path.exists("balances.json"):
            return 0
        balances = json.loads(open("balances.json", "r", encoding="utf-8").read())
        total_balance = sum(float(balance) for balance in balances.values())
        return total_balance

    def calculate_remaining_delay(self):
        """Menghitung jeda yang tersisa hingga mencapai 8-10 jam dari waktu mulai."""
        if self.first_account_time is None:
            self.remaining_delay = 0
            return self.remaining_delay
        
        self.remaining_delay = random.uniform(8 * 3600, 10 * 3600)
        return self.remaining_delay

    def get_next_restart_time(self):
        """Menghitung waktu restart berikutnya berdasarkan first_account_time dan interval restart."""
        if self.first_account_time is None:
            return None

        self.calculate_remaining_delay()
        self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)
        formatted_restart_time = self.next_restart_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
        self.save_state()
        return formatted_restart_time

    def load_config(self):
        try:
            config = json.loads(open("config.json", "r", encoding="utf-8").read())
            self.AUTOTASK = config["auto_complete_task"]
            self.AUTOGAME = config["auto_play_game"]
            self.DEFAULT_INTERVAL = config["interval"]
            self.MIN_WIN = config["game_point"]["low"]
            self.MAX_WIN = config["game_point"]["high"]
            if self.MIN_WIN > self.MAX_WIN:
                self.log(f"{kuning}high value must be higher than lower value")
                sys.exit()
        except json.decoder.JSONDecodeError:
            self.log(f"{merah}failed decode config.json")
            sys.exit()

    def ipinfo(self):
        if not self.running:
            return
        res = self.http("https://ipinfo.io/json", {"content-type": "application/json"})
        if res is False:
            return False
        if res.status_code != 200:
            self.log(f"{merah}failed fetch ipinfo !")
            return False
        city = res.json().get("city")
        country = res.json().get("country")
        region = res.json().get("region")
        self.log(
            f"{hijau}country : {putih}{country} {hijau}region : {putih}{region} {hijau}city : {putih}{city}"
        )
        random_delay(1, 3)
        return True

    def http(self, url, headers, data=None):
        global retry_counter
        retry_count = 0
        proxy_switch_count = 0
        max_retries = 5
        max_proxy_switches = 3
        max_looping_errors = 3  # Batas looping error sebelum restart

        while self.running:
            try:
                logfile = "http.log"
                if not os.path.exists(logfile):
                    open(logfile, "a", encoding="utf-8").close()
                logsize = os.path.getsize(logfile)
                if logsize > (1024 * 2):
                    open(logfile, "w", encoding="utf-8").write("")

                if not is_connected():  # Cek koneksi sebelum membuat request
                    self.log(f"{merah}No internet connection! Waiting to reconnect...")
                    self.countdown(30)  # Tunggu sebelum mencoba kembali
                    continue

                if data is None:
                    res = self.ses.get(url, headers=headers, timeout=30)
                elif data == "":
                    res = self.ses.post(url, headers=headers, timeout=30)
                else:
                    res = self.ses.post(url, headers=headers, data=data, timeout=30)

                open("http.log", "a", encoding="utf-8").write(res.text + "\n")
                if "<title>" in res.text:
                    self.log(f"{merah}Failed to fetch JSON response!")
                    time.sleep(2)
                    continue

                retry_counter = 0
                return res

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                self.log(f"{merah}Connection error/connection timeout!")
                retry_count += 1
                retry_counter += 1

                if retry_counter >= max_looping_errors:
                    self.log(f"{merah}Max looping errors reached. Restarting bot...")
                    self.restart_bot()  # Panggil fungsi restart bot alih-alih menghentikan bot

                if retry_count >= max_retries:
                    self.log(f"{kuning}Switching proxy...")
                    self.switch_proxy()
                    time.sleep(30)
                    retry_count = 0
                    proxy_switch_count += 1
                    if proxy_switch_count >= max_proxy_switches:
                        self.log(f"{merah}Max proxy switches reached, restarting main process...")
                        return None  # Mengembalikan None untuk menghentikan loop utama

            except requests.exceptions.ProxyError:
                self.log(f"{merah}Bad proxy!")
                self.switch_proxy()
                time.sleep(30)
                retry_count = 0
                proxy_switch_count += 1
                if proxy_switch_count >= max_proxy_switches:
                    self.log(f"{merah}Max proxy switches reached, restarting main process...")
                    return None  # Mengembalikan None untuk menghentikan loop utama

        self.log(f"{merah}Max retries reached, moving to the next process.")
        return None


    def switch_proxy(self):
        """Ganti proxy dengan salah satu dari daftar proxy yang ada."""
        if not self.running:
            return
        if self.proxies:
            new_proxy = random.choice(self.proxies)
            self.set_proxy(new_proxy)
            random_delay(1, 3)
        else:
            self.log(f"{merah}No proxies available, exiting...")
            sys.exit()

    def reset_first_account_time_if_needed(self):
        """Reset first_account_time jika sudah lebih dari 10 jam."""
        if not self.running or self.first_account_time is None:
            return

        now = datetime.now(WIB)

        if now >= self.next_restart_time:
            self.log(f"{kuning}Now is greater than or equal to the next restart time. Clearing processed accounts.")
            self.processed_accounts.clear()
            self.first_account_time = now
            self.calculate_remaining_delay()
            self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)
            self.save_state()

        if now > (self.first_account_time + timedelta(hours=10)):
            self.first_account_time = now
            self.processed_accounts.clear()
            self.log(f"{kuning}Resetting first account time because it's been more than 10 hours.")
            self.calculate_remaining_delay()
            self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)
            self.save_state()

    def countdown(self, t):
        while self.running and t:
            menit, detik = divmod(t, 60)
            jam, menit = divmod(menit, 60)
            jam = str(jam).zfill(2)
            menit = str(menit).zfill(2)
            detik = str(detik).zfill(2)
            print(f"{putih}waiting until {jam}:{menit}:{detik} ", flush=True, end="\r")
            t -= 1
            time.sleep(1)
        print("                          ", flush=True, end="\r")

    def main(self):
        banner = f"""
    {hijau}AUTO CLAIM FOR {putih}BLUM {hijau}/ {biru}@BlumCryptoBot

    {hijau}By : {putih}t.me/AkasakaID
    {putih}Github : {hijau}@AkasakaID

    {hijau}Message : {putih}Dont forget to 'git pull' maybe I update the bot !
        """
        arg = argparse.ArgumentParser()
        arg.add_argument(
            "--marinkitagawa", action="store_true", help="no clear the terminal !"
        )
        arg.add_argument(
            "--data", help="Custom data input (default: data.txt)", default="data.txt"
        )
        arg.add_argument(
            "--proxy",
            help="custom proxy file input (default: proxies.txt)",
            default="proxies.txt",
        )
        args = arg.parse_args()
        if not args.marinkitagawa:
            os.system("cls" if os.name == "nt" else "clear")

        print(banner)
        if not os.path.exists(args.data):
            self.log(f"{merah}{args.data} not found, please input valid file name !")
            sys.exit()

        datas = load_file_lines(args.data)
        proxies = load_file_lines(args.proxy)
        self.use_proxy = len(proxies) > 0
        self.proxies = proxies

        self.log(f"{hijau}total account : {putih}{len(datas)}")
        self.log(f"{biru}use proxy : {putih}{self.use_proxy}")
        if len(datas) <= 0:
            self.log(f"{merah}add data account in {args.data} first")
            sys.exit()

        self.load_state()

        if self.first_account_time is None:
            self.first_account_time = datetime.now(WIB)
            self.calculate_remaining_delay()
            self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)
            self.save_state()

        while self.running:
            self.check_for_stop()
            self.reset_first_account_time_if_needed()

            remaining_accounts = [
                (index, data) for index, data in enumerate(datas)
                if index not in self.processed_accounts
            ]
            random.shuffle(remaining_accounts)

            print(self.garis)
            while remaining_accounts and self.running:
                for index, data in remaining_accounts:
                    self.check_for_stop()

                    if not self.running:
                        break
                    if self.first_account_time is None:
                        self.first_account_time = datetime.now(WIB)

                    self.log(f"{hijau}account number - {putih}{index + 1}")
                    try:
                        data_parse = self.data_parsing(data)
                        user = json.loads(data_parse["user"])
                        userid = user["id"]
                        self.log(f"{hijau}login as : {putih}{user['first_name']}")

                        session_user_agent = self.get_user_agent_for_account(index)
                        if session_user_agent is None:
                            self.log(f"{merah}Skipping account {index + 1} due to empty user-agent list.")
                            continue

                        self.base_headers["user-agent"] = session_user_agent
                        self.log(f"{kuning}Using User-Agent: {session_user_agent}")

                        if self.use_proxy:
                            proxy = proxies[index % len(proxies)]
                        self.set_proxy(proxy if self.use_proxy else None)
                        self.ipinfo() if self.use_proxy else None
                        access_token = self.get_local_token(userid)
                        failed_fetch_token = False
                        while self.running:
                            self.check_for_stop()

                            if access_token is False:
                                access_token = self.renew_access_token(data)
                                if access_token is False:
                                    self.save_failed_token(userid, data)
                                    failed_fetch_token = True
                                    break
                                self.save_local_token(userid, access_token)
                            expired = self.is_expired(access_token)
                            if expired:
                                access_token = False
                                continue
                            break
                        if failed_fetch_token:
                            continue
                        self.checkin(access_token)
                        self.get_friend(access_token)
                        if self.AUTOTASK:
                            self.solve_task(access_token)
                        status, res_bal, balance = self.get_balance(access_token)
                        if status:
                            res_bal = self.claim_farming(access_token)
                            self.start_farming(access_token)
                        if isinstance(res_bal, str):
                            self.start_farming(access_token)
                        if self.AUTOGAME:
                            balance = self.playgame(access_token)

                        self.save_account_balance(userid, balance)
                        print(self.garis)
                        self.countdown(self.DEFAULT_INTERVAL)

                        self.processed_accounts.add(index)
                        self.save_state()

                    except Exception as e:
                        self.log(f"{merah}Error processing account {index + 1}: {str(e)}")
                        self.log(f"{merah}Skipping account {index + 1} and moving to the next one.")

                    self.check_for_stop()

                remaining_accounts = [
                    (index, data) for index, data in remaining_accounts
                    if index not in self.processed_accounts
                ]

            if not remaining_accounts and self.running:
                self.save_state()
                self.log(f"{hijau}All accounts processed. Restarting...")

                # Logika restart ketika proxy sudah gagal diganti 3 kali
                if self.next_restart_time is not None:
                    formatted_end_time = self.next_restart_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
                    print(f"{kuning}Waiting until {formatted_end_time} before restarting...", flush=True)

                    remaining_time = (self.next_restart_time - datetime.now(WIB)).total_seconds()
                    if remaining_time > 0:
                        self.countdown(int(remaining_time))

                now = datetime.now(WIB)
                random_delay(1, 3)
                if now >= self.next_restart_time:
                    self.log(f"{kuning}Now is greater than or equal to the next restart time. Clearing processed accounts.")
                    self.processed_accounts.clear()

                self.first_account_time = datetime.now(WIB)

                self.calculate_remaining_delay()
                self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)

                if now > (self.first_account_time + timedelta(hours=10)):
                    self.first_account_time = now
                    self.log(f"{kuning}Resetting first account time because it's been more than 10 hours.")
                    random_delay(1, 3)
                    self.processed_accounts.clear()

                self.calculate_remaining_delay()
                self.next_restart_time = self.first_account_time + timedelta(seconds=self.remaining_delay)
                self.save_state()

                random.shuffle(datas)

                continue

if __name__ == "__main__":
    while True:
        try:
            app = BlumTod()
            app.load_config()

            while app.running:  # Loop utama untuk menjalankan bot
                app.main()

            if not app.restart_requested:  # Cek apakah restart diminta
                break  # Keluar dari loop utama jika tidak ada restart

        except KeyboardInterrupt:
            sys.exit()
        except Exception as e:
            print(f"{merah}Unexpected error: {str(e)}. Restarting bot in 10 seconds...")
            time.sleep(10)
