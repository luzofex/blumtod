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
import pytz  # Tambahkan import untuk timezone

init(autoreset=True)

# Definisikan timezone untuk Waktu Indonesia Barat (WIB)
WIB = pytz.timezone('Asia/Jakarta')

merah = Fore.LIGHTRED_EX
putih = Fore.LIGHTWHITE_EX
hijau = Fore.LIGHTGREEN_EX
kuning = Fore.LIGHTYELLOW_EX
biru = Fore.LIGHTBLUE_EX
reset = Style.RESET_ALL
hitam = Fore.LIGHTBLACK_EX

# Mengimpor User-Agent dari file
def load_user_agents(file_path='user-agent.txt'):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f.readlines()]

# Mengimpor daftar User-Agent
user_agents = load_user_agents()

# Menyimpan User-Agent yang dipilih untuk setiap akun
account_user_agents = {}

def random_delay(min_delay=2, max_delay=5):
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

def calculate_remaining_delay(start_time, min_hours=8, max_hours=10):
    """Menghitung jeda yang tersisa hingga mencapai 8-10 jam dari waktu mulai."""
    min_time = start_time + timedelta(hours=min_hours)
    max_time = start_time + timedelta(hours=max_hours)
    now = datetime.now(WIB)
    
    if now < min_time:
        return (min_time - now).total_seconds()
    elif now > max_time:
        return 0
    else:
        return random.uniform(0, (max_time - now).total_seconds())

class BlumTod:
    def stop(self):
        self.running = False  # Metode untuk menghentikan bot
        self.log(f"Stopping the bot...")  # Menulis pesan "Stopping the bot..." ke log
        self.log(f"Bot stopped")  # Menulis pesan "Bot stopped" ke log

    def __init__(self):
        self.running = True  # Tambahkan flag running untuk mengontrol loop
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
        self.processed_accounts = set()  # Set to track processed accounts
        self.first_account_time = None  # Waktu pemrosesan akun pertama

    def save_state(self):
        """Menyimpan status akun yang sudah diproses ke file"""
        with open(self.state_file, 'w') as f:
            state = {
                "processed_accounts": list(self.processed_accounts),
                "first_account_time": self.first_account_time.isoformat() if self.first_account_time else None
            }
            json.dump(state, f)

    def load_state(self):
        """Memuat status akun yang sudah diproses dari file"""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.processed_accounts = set(state.get("processed_accounts", []))
                first_account_time_str = state.get("first_account_time", None)
                if first_account_time_str:
                    self.first_account_time = datetime.fromisoformat(first_account_time_str).astimezone(WIB)

    def get_user_agent_for_account(self, account_number):
        # Mengembalikan User-Agent yang sama untuk setiap akun
        if account_number not in account_user_agents:
            account_user_agents[account_number] = user_agents[account_number % len(user_agents)]
        return account_user_agents[account_number]

    def renew_access_token(self, tg_data):
        headers = self.base_headers.copy()
        data = dp({"query": tg_data})
        headers["Content-Length"] = str(len(data))
        url = "https://gateway.blum.codes/v1/auth/provider/PROVIDER_TELEGRAM_MINI_APP"
        res = self.http(url, headers, data)
        token = res.json().get("token")
        if token is None:
            self.log(f"{merah}'token' is not found in response, check your data !!")
            return False

        access_token = res.json()["token"]["access"]
        self.log(f"{hijau}success get access token ")
        return access_token

    def solve_task(self, access_token):
        if not self.running:
            return
        url_task = "https://game-domain.blum.codes/api/v1/tasks"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url_task, headers)
        for tasks in res.json():
            if not self.running:
                break
            if isinstance(tasks, str):
                self.log(f'{kuning}failed get task list !')
                return
            for task in tasks.get("tasks"):
                if not self.running:
                    break
                task_id = task.get("id")
                task_title = task.get("title")
                task_status = task.get("status")
                if task_status == "NOT_STARTED":
                    url_start = f"https://game-domain.blum.codes/api/v1/tasks/{task_id}/start"
                    res = self.http(url_start, headers, "")
                    if "message" in res.text:
                        continue

                    url_claim = f"https://game-domain.blum.codes/api/v1/tasks/{task_id}/claim"
                    res = self.http(url_claim, headers, "")
                    if "message" in res.text:
                        continue

                    status = res.json().get("status")
                    if status == "CLAIMED":
                        self.log(f"{hijau}success complete task {task_title} !")
                        random_delay(1, 3)  # Tunda setelah menyelesaikan tugas
                        continue

                self.log(f"{kuning}already complete task {task_title} !")

    def set_proxy(self, proxy=None):
        self.ses = requests.Session()
        if proxy is not None:
            self.ses.proxies.update({"http": proxy, "https": proxy})

    def claim_farming(self, access_token):
        if not self.running:
            return
        url = "https://game-domain.blum.codes/api/v1/farming/claim"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers, "")
        balance = res.json()["availableBalance"]
        self.log(f"{hijau}balance after claim : {putih}{balance}")
        random_delay(1, 3)  # Tunda setelah klaim
        return balance

    def get_balance(self, access_token, only_show_balance=False):
        if not self.running:
            return
        url = "https://game-domain.blum.codes/api/v1/user/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers)
        balance = res.json()["availableBalance"]
        self.log(f"{hijau}balance : {putih}{balance}")
        if only_show_balance:
            return balance
        timestamp = round(res.json()["timestamp"] / 1000)
        if "farming" not in res.json().keys():
            return False, "not_started", balance
        end_farming = round(res.json()["farming"]["endTime"] / 1000)
        if timestamp > end_farming:
            self.log(f"{hijau}now is time to claim farming !")
            return True, end_farming, balance

        self.log(f"{kuning}not time to claim farming !")
        end_date = datetime.fromtimestamp(end_farming)
        self.log(f"{hijau}end farming : {putih}{end_date}")
        random_delay(1, 3)  # Tunda setelah pengecekan balance
        return False, end_farming, balance

    def start_farming(self, access_token):
        if not self.running:
            return
        url = "https://game-domain.blum.codes/api/v1/farming/start"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers, "")
        end = res.json()["endTime"]
        end_date = datetime.fromtimestamp(end / 1000)
        self.log(f"{hijau}start farming successfully !")
        self.log(f"{hijau}end farming : {putih}{end_date}")
        random_delay(1, 3)  # Tunda setelah memulai farming
        return round(end / 1000)

    def get_friend(self, access_token):
        if not self.running:
            return
        url = "https://gateway.blum.codes/v1/friends/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers)
        can_claim = res.json().get("canClaim", False)
        limit_invite = res.json().get("limitInvitation", 0)
        amount_claim = res.json().get("amountForClaim")
        self.log(f"{putih}limit invitation : {hijau}{limit_invite}")
        self.log(f"{hijau}claim amount : {putih}{amount_claim}")
        self.log(f"{putih}can claim : {hijau}{can_claim}")
        if can_claim:
            url_claim = "https://gateway.blum.codes/v1/friends/claim"
            res = self.http(url_claim, headers, "")
            if res.json().get("claimBalance") is not None:
                self.log(f"{hijau}success claim referral bonus !")
                random_delay(1, 3)  # Tunda setelah klaim
                return
            self.log(f"{merah}failed claim referral bonus !")
        random_delay(1, 3)  # Tunda setelah pengecekan teman

    def checkin(self, access_token):
        if not self.running:
            return
        url = "https://game-domain.blum.codes/api/v1/daily-reward?offset=-420"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        res = self.http(url, headers)
        if res.status_code == 404:
            self.log(f"{kuning}already check in today !")
            return
        res = self.http(url, headers, "")
        if "ok" in res.text.lower():
            self.log(f"{hijau}success check in today !")
            random_delay(1, 3)  # Tunda setelah check-in
            return

        self.log(f"{merah}failed check in today !")
        random_delay(1, 3)  # Tunda setelah check-in gagal
        return

    def playgame(self, access_token):
        if not self.running:
            return
        url_play = "https://game-domain.blum.codes/api/v1/game/play"
        url_claim = "https://game-domain.blum.codes/api/v1/game/claim"
        url_balance = "https://game-domain.blum.codes/api/v1/user/balance"
        headers = self.base_headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"

        while self.running:
            # Dapatkan jumlah tiket yang tersedia
            res = self.http(url_balance, headers)
            play = res.json().get("playPasses", 0)
            balance = res.json().get("availableBalance", 0)  # Ambil balance terakhir

            self.log(f"{hijau}you have {putih}{play}{hijau} game ticket(s)")
            self.log(f"{hijau}current balance : {putih}{balance}")

            if play == 0:
                self.log(f"{kuning}No more game tickets left, saving balance and moving to next step.")
                return balance  # Kembalikan balance terakhir untuk disimpan
                break  # Keluar dari loop jika tidak ada tiket yang tersisa

            for _ in range(play):
                if not self.running:
                    break
                if self.is_expired(access_token):
                    return True

                # Memulai game
                res = self.http(url_play, headers, "")
                game_id = res.json().get("gameId")

                if game_id is None:
                    message = res.json().get("message", "")
                    if message == "cannot start game":
                        continue
                    self.log(f"{kuning}{message}")
                    random_delay(1, 3)  # Tunda jika tidak bisa memulai game
                    continue

                self.countdown(30)

                # Klaim poin setelah bermain
                point = random.randint(self.MIN_WIN, self.MAX_WIN)
                data = json.dumps({"gameId": game_id, "points": point})
                res = self.http(url_claim, headers, data)

                if "OK" in res.text:
                    self.log(f"{hijau}success earn {putih}{point}{hijau} from game !")
                    balance = self.get_balance(access_token, only_show_balance=True)  # Update balance setelah tiap game
                    random_delay(1, 3)  # Tunda setelah mengklaim poin
                else:
                    self.log(f"{merah}failed earn {putih}{point}{merah} from game !")
                    random_delay(1, 3)  # Tunda setelah gagal mengklaim poin
        return balance  # Pastikan balance terakhir selalu dikembalikan

    def data_parsing(self, data):
        return {k: v[0] for k, v in parse_qs(data).items()}

    def log(self, message):
        now = datetime.now(WIB).isoformat(" ").split(".")[0]
        log_message = f"{now} {message}"
        
        # Cetak ke terminal
        print(f"{hitam}[{now}]{reset} {message}")
        
        # Simpan log ke file bot.log
        with open("bot.log", "a") as log_file:
            log_file.write(f"{log_message}\n")


    def get_local_token(self, userid):
        if not os.path.exists("tokens.json"):
            open("tokens.json", "w").write(json.dumps({}))
        tokens = json.loads(open("tokens.json", "r").read())
        if str(userid) not in tokens.keys():
            return False

        return tokens[str(userid)]

    def save_local_token(self, userid, token):
        tokens = json.loads(open("tokens.json", "r").read())
        tokens[str(userid)] = token
        open("tokens.json", "w").write(json.dumps(tokens, indent=4))

    def is_expired(self, token):
        header, payload, sign = token.split(".")
        payload = b64decode(payload + "==").decode()
        jload = json.loads(payload)
        now = round(datetime.now().timestamp()) + 300
        exp = jload["exp"]
        if now > exp:
            return True

        return False

    def save_failed_token(self, userid, data):
        file = "auth_failed.json"
        if not os.path.exists(file):
            open(file, "w").write(json.dumps({}))

        acc = json.loads(open(file, "r").read())
        if str(userid) in acc.keys():
            return

        acc[str(userid)] = data
        open(file, "w").write(json.dumps(acc, indent=4))

    def save_account_balance(self, userid, balance):
        if not os.path.exists("balances.json"):
            open("balances.json", "w").write(json.dumps({}))
        balances = json.loads(open("balances.json", "r").read())
        balances[str(userid)] = balance
        open("balances.json", "w").write(json.dumps(balances, indent=4))

    def sum_all_balances(self):
        """Menjumlahkan semua balance yang ada di balances.json."""
        if not os.path.exists("balances.json"):
            return 0

        balances = json.loads(open("balances.json", "r").read())
        # Konversi semua nilai balance ke float sebelum dijumlahkan
        total_balance = sum(float(balance) for balance in balances.values())
        self.log(f"{hijau}Total balance for all accounts: {putih}{total_balance}")
        return total_balance


    def load_config(self):
        config = json.loads(open("config.json", "r").read())
        self.AUTOTASK = config["auto_complete_task"]
        self.AUTOGAME = config["auto_play_game"]
        self.DEFAULT_INTERVAL = config["interval"]
        self.MIN_WIN = config["game_point"]["low"]
        self.MAX_WIN = config["game_point"]["high"]
        if self.MIN_WIN > self.MAX_WIN:
            self.log(f"{kuning}high value must be higher than lower value")
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
        random_delay(1, 3)  # Tunda setelah mendapatkan info IP
        return True

    def http(self, url, headers, data=None):
        retry_count = 0
        max_retries = 5  # Batas percobaan ulang sebelum mengganti proxy

        while self.running and retry_count < max_retries:
            try:
                logfile = "http.log"
                if not os.path.exists(logfile):
                    open(logfile, "a")
                logsize = os.path.getsize(logfile)
                if logsize > (1024 * 2) > 1:
                    open(logfile, "w").write("")

                if data is None:
                    res = self.ses.get(url, headers=headers, timeout=30)
                elif data == "":
                    res = self.ses.post(url, headers=headers, timeout=30)
                else:
                    res = self.ses.post(url, headers=headers, data=data, timeout=30)

                open("http.log", "a", encoding="utf-8").write(res.text + "\n")
                if "<title>" in res.text:
                    self.log(f"{merah}failed fetch json response !")
                    time.sleep(2)
                    continue

                return res

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                self.log(f"{merah}connection error/connection timeout!")
                retry_count += 1
                if retry_count >= max_retries:
                    self.log(f"{kuning}Switching proxy...")
                    self.switch_proxy()
                    retry_count = 0  # Reset retry count setelah switching proxy

            except requests.exceptions.ProxyError:
                self.log(f"{merah}bad proxy")
                self.switch_proxy()
                retry_count = 0  # Reset retry count setelah switching proxy

        self.log(f"{merah}max retries reached, exiting...")
        sys.exit()

    def switch_proxy(self):
        """Ganti proxy dengan salah satu dari daftar proxy yang ada."""
        if not self.running:
            return
        if self.proxies:
            new_proxy = random.choice(self.proxies)
            self.set_proxy(new_proxy)
            self.log(f"{kuning}Proxy changed to: {new_proxy}")
            random_delay(1, 3)  # Tunda setelah mengganti proxy
        else:
            self.log(f"{merah}No proxies available, exiting...")
            sys.exit()

    def reset_first_account_time_if_needed(self):
        """Reset first_account_time jika sudah lebih dari 10 jam."""
        if not self.running or self.first_account_time is None:
            return

        now = datetime.now(WIB)
        if now > (self.first_account_time + timedelta(hours=10)):
            self.first_account_time = now
            self.log(f"{kuning}Resetting first account time because it's been more than 10 hours.")

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

        datas = [i for i in open(args.data, "r").read().splitlines() if len(i) > 0]
        proxies = [i for i in open(args.proxy).read().splitlines() if len(i) > 0]
        use_proxy = True if len(proxies) > 0 else False
        self.log(f"{hijau}total account : {putih}{len(datas)}")
        self.log(f"{biru}use proxy : {putih}{use_proxy}")
        if len(datas) <= 0:
            self.log(f"{merah}add data account in {args.data} first")
            sys.exit()

        self.use_proxy = use_proxy
        self.proxies = proxies  # Menyimpan daftar proxy yang tersedia

        # Muat status terakhir dan data akun yang sudah diproses
        self.load_state()

        while self.running:  # Loop tak terbatas
            # Reset first_account_time jika sudah lebih dari 10 jam
            self.reset_first_account_time_if_needed()

            # Acak urutan akun, tetapi jangan memproses ulang akun yang sudah selesai
            remaining_accounts = [
                (index, data) for index, data in enumerate(datas)
                if index not in self.processed_accounts
            ]
            random.shuffle(remaining_accounts)

            print(self.garis)
            while remaining_accounts and self.running:
                for index, data in remaining_accounts:
                    if not self.running:
                        break
                    if self.first_account_time is None:
                        self.first_account_time = datetime.now(WIB)  # Catat waktu mulai akun pertama dalam WIB

                    self.log(f"{hijau}account number - {putih}{index + 1}")
                    try:
                        data_parse = self.data_parsing(data)
                        user = json.loads(data_parse["user"])
                        userid = user["id"]
                        self.log(f"{hijau}login as : {putih}{user['first_name']}")

                        # Pilih User-Agent yang tetap untuk akun ini
                        session_user_agent = self.get_user_agent_for_account(index)
                        self.base_headers["user-agent"] = session_user_agent
                        self.log(f"{kuning}Using User-Agent: {session_user_agent}")

                        if use_proxy:
                            proxy = proxies[index % len(proxies)]
                        self.set_proxy(proxy if use_proxy else None)
                        self.ipinfo() if use_proxy else None
                        access_token = self.get_local_token(userid)
                        failed_fetch_token = False
                        while self.running:
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

                        # Simpan balance setelah semua proses untuk akun selesai
                        self.save_account_balance(userid, balance)
                        print(self.garis)
                        self.countdown(self.DEFAULT_INTERVAL)
                        
                        # Tandai akun ini sebagai sudah diproses dan simpan status
                        self.processed_accounts.add(index)
                        self.save_state()

                    except Exception as e:
                        self.log(f"{merah}Error processing account {index + 1}: {str(e)}")
                        self.log(f"{merah}Skipping account {index + 1} and moving to the next one.")

                # Perbarui remaining_accounts untuk menghapus akun yang sudah diproses
                remaining_accounts = [
                    (index, data) for index, data in remaining_accounts
                    if index not in self.processed_accounts
                ]

            # Jika semua akun sudah diproses, reset processed_accounts dan mulai lagi
            if not remaining_accounts and self.running:
                self.processed_accounts.clear()
                self.save_state()  # Simpan status yang telah di-reset
                self.log(f"{hijau}All accounts processed. Restarting...")
                
                # Tampilkan total balance dari semua akun
                self.sum_all_balances()
                
                # Hitung jeda yang tersisa hingga mencapai 8-10 jam dari waktu mulai akun pertama
                remaining_delay = calculate_remaining_delay(self.first_account_time, 8, 10)
                
                if remaining_delay > 0:
                    end_time = datetime.now(WIB) + timedelta(seconds=remaining_delay)
                    formatted_end_time = end_time.strftime("%Y-%m-%d %H:%M:%S %Z%z")
                    print(f"{kuning}Waiting until {formatted_end_time} before restarting...", flush=True)
                    time.sleep(remaining_delay)
                
                self.first_account_time = None  # Reset waktu mulai untuk siklus berikutnya
                random.shuffle(datas)  # Acak ulang semua akun


if __name__ == "__main__":
    try:
        app = BlumTod()
        app.load_config()
        app.main()
    except KeyboardInterrupt:
        sys.exit()
