
import asyncio
import random
import traceback
import imaplib
import email as email_lib
import re
import requests
import json
import os
import time
import threading
from itertools import cycle
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from flask import Flask, render_template_string


# ===========================================
# CONFIGURAO
# ===========================================

LINKS = [
    "https://www.boomplay.com/albums/126196876?from=search",
    "https://www.boomplay.com/albums/126195111?from=search",
    "https://www.boomplay.com/albums/126195111?from=search",
    "https://www.boomplay.com/albums/126481057?from=search",
    "https://www.boomplay.com/albums/127319490?from=search",
    "https://www.boomplay.com/albums/126481057?from=search",
    "https://www.boomplay.com/albums/125145881?from=search",
    "https://www.boomplay.com/albums/125230563?from=search",
    "https://www.boomplay.com/albums/125228056?from=search",
    "https://www.boomplay.com/albums/125297033?from=search",
    "https://www.boomplay.com/albums/125260357?from=search",
    "https://www.boomplay.com/albums/125230555?from=search",
    "https://www.boomplay.com/albums/125161707?from=search",
    "https://www.boomplay.com/albums/124591923?from=search",
    "https://www.boomplay.com/albums/124485582?from=search",
    "https://www.boomplay.com/albums/123862720?from=search",
    "https://www.boomplay.com/albums/123792132?from=search",
    "https://www.boomplay.com/albums/123471430?from=search",
    "https://www.boomplay.com/albums/123119495?from=search",
    "https://www.boomplay.com/albums/122872464?from=search",
    "https://www.boomplay.com/albums/122930431?from=search",
    "https://www.boomplay.com/albums/122347713?from=search",
    "https://www.boomplay.com/albums/122747565?from=search",
    "https://www.boomplay.com/albums/121763651?from=search",
    "https://www.boomplay.com/albums/118063319?from=search",
    "https://www.boomplay.com/albums/117690293?from=search",
    "https://www.boomplay.com/albums/117646715?from=search",
    "https://www.boomplay.com/albums/116152715?from=search",
]

TIMER = 300
NUM_BROWSERS = 20

START_TIME = time.time()
STATS = {"sessions": 0, "success": 0, "errors": 0, "accounts_created": 0}
HISTORY = []
ERROR_LOG = []
URL_STATS = {}


# ===========================================
# PROXIES
# ===========================================

def load_proxies(file):
    proxies = []
    try:
        with open(file) as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) == 4:
                    ip, port, user, pwd = parts
                    proxies.append({
                        "server":   f"http://{ip}:{port}",
                        "username": user,
                        "password": pwd,
                    })
    except:
        print(" proxy.txt nao encontrado")
    return proxies

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
proxy_path = os.path.join(BASE_DIR, "vps.txt")

PROXIES = load_proxies(proxy_path)
proxy_pool = cycle(PROXIES) if PROXIES else None


# ===========================================
# BLOQUEIO DE ADS
# ===========================================

async def block_ads(context):
    async def handler(route):
        url = route.request.url
        if any(x in url for x in ["doubleclick", "googleads", "googlesyndication", "adservice"]):
            await route.abort()
        else:
            await route.continue_()
    await context.route("**/*", handler)


# ===========================================
# POPUPS
# ===========================================

async def handle_popups(page, wid):
    try:
        selectors = ["button.fc-cta-consent", "button:has-text('Accept')", "text=Accept"]
        for sel in selectors:
            btn = page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                print(f"[W{wid}]  Popup fechado")
                return
        for frame in page.frames:
            try:
                btn = frame.locator("button:has-text('Accept'), button:has-text('Close')")
                if await btn.count() > 0:
                    await btn.first.click()
                    print(f"[W{wid}]  Popup iframe fechado")
                    return
            except:
                pass
    except:
        pass


# ===========================================
# CRIAO DE CONTAS (do boom.py)
# ===========================================

def get_verification_code(imap_server, email_user, email_pass, sender_filter):
    mail = imaplib.IMAP4_SSL(imap_server, 993)
    mail.login(email_user, email_pass)
    mail.select("INBOX")

    status, messages = mail.search(None, f'(FROM "{sender_filter}")')

    if status != "OK":
        return None

    email_ids = messages[0].split()

    if not email_ids:
        return None

    latest_email_id = email_ids[-1]

    status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
    raw_email = msg_data[0][1]

    msg = email_lib.message_from_bytes(raw_email)

    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ["text/html", "text/plain"]:
                try:
                    body += part.get_payload(decode=True).decode(errors="ignore")
                except:
                    pass
    else:
        body = msg.get_payload(decode=True).decode(errors="ignore")

    lines = body.split()

    for i, line in enumerate(lines):
        if "underline" in line or "<strong" in line:
            match = re.search(r"\d{6}", line)
            if match:
                return match.group()
    return None


def generate_user():
    data = requests.get("https://randomuser.me/api/").json()
    user = data["results"][0]

    username = user["login"]["username"]
    password = user["login"]["password"]

    return {
        "username": username,
        "password": password
    }


def save_account(emaile, password):
    accounts_path = os.path.join(BASE_DIR, "accounts.json")
    try:
        with open(accounts_path, "r") as f:
            data = json.load(f)
    except:
        data = []

    data.append({
        "email": emaile,
        "password": password
    })

    with open(accounts_path, "w") as f:
        json.dump(data, f, indent=2)


def load_accounts():
    """Carrega contas salvas do accounts.json."""
    accounts_path = os.path.join(BASE_DIR, "accounts.json")
    try:
        with open(accounts_path, "r") as f:
            return json.load(f)
    except:
        return []


def get_random_account():
    """Retorna uma conta aleatria do ficheiro de contas."""
    accounts = load_accounts()
    if not accounts:
        return None
    return random.choice(accounts)


async def login_account(page, worker_id):
    """
    Faz login com uma conta salva no accounts.json.
    Retorna True se login com sucesso, False caso contrrio.
    """
    account = get_random_account()
    if not account:
        print(f"[W{worker_id}]  Nenhuma conta disponvel para login")
        return False

    email_addr = account["email"]
    password = account["password"]

    print(f"[W{worker_id}]  Fazendo login com: {email_addr}")

    try:
        # Navega para a pgina de login
        await page.goto(
            "https://www.boomplay.com/oauth/login?change=T&app_id=bpinternalprojects&redirect_uri=https%3A%2F%2Fwww.boomplay.com%2F&scope=email%2Cprofile&state=2&isPopup=F",
            wait_until="domcontentloaded",
            timeout=30000
        )

        # Espera o formulrio de login aparecer
        await page.wait_for_selector('form.logInForm', timeout=10000)
        await asyncio.sleep(2)

        form = page.locator('form.logInForm')

        # Clica no label "Email Address" para mudar de Phone para Email
        await form.locator('label:has(input[value="email"])').click()
        await asyncio.sleep(1)

        # Preenche email (dentro do bloco .only-email)
        await form.locator('.only-email input[name="email"]').fill(email_addr)
        await asyncio.sleep(0.5)

        # Preenche password
        await form.locator('input[name="pw"]').fill(password)
        await asyncio.sleep(0.5)

        # Clica no boto de login
        await form.locator('input.submit[type="submit"]').click()

        await asyncio.sleep(5)

        # Verifica se login foi bem sucedido
        current_url = page.url
        if "oauth/login" not in current_url:
            print(f"[W{worker_id}]  Login com sucesso (redirect): {email_addr}")
            return True

        logged = page.locator('.user-avatar, .userInfo, .header_login_after, img.avatar')
        if await logged.count() > 0:
            print(f"[W{worker_id}]  Login com sucesso: {email_addr}")
            return True

        print(f"[W{worker_id}]  Login pode ter falhado para: {email_addr}")
        return False

    except Exception as e:
        print(f"[W{worker_id}]  Login falhou ({type(e).__name__}), continuando sem login...")
        return False


def create_accounts(num_accounts=1):
    """Cria contas no Boomplay usando Playwright sync."""
    with sync_playwright() as p:
        for i in range(num_accounts):
            proxy = next(proxy_pool) if proxy_pool else None

            user = generate_user()
            emaile = f'{user["username"]}@checker.mobi'
            password = "Suwel2003@"

            print(f"\n[CONTA {i+1}]  Criando conta: {emaile}")

            browser = p.chromium.launch(
                headless=True,
                proxy=proxy
            )
            page = browser.new_page()

            try:
                page.goto(
                    "https://www.boomplay.com/oauth/login?change=T&app_id=bpinternalprojects&redirect_uri=https%3A%2F%2Fwww.boomplay.com%2FBFA%2F%23%2F&scope=email%2Cprofile&state=2&isPopup=F",
                    timeout=60000
                )
            except Exception as e:
                print(f"[CONTA {i+1}]  Erro ao abrir pgina: {e}")
                browser.close()
                continue

            page.wait_for_timeout(5000)
            page.get_by_role("button", name="Sign up").click()
            page.wait_for_timeout(5000)

            form = page.locator('form.signUpForm.current')
            form.wait_for()

            form.locator('input[name="email"]').fill(emaile)
            form.locator('a.getCode').click()

            page.wait_for_timeout(15000)

            code = get_verification_code(
                imap_server="imap.strato.com",
                email_user="sakaru@checker.mobi",
                email_pass="Suwel2003@",
                sender_filter="noreply.boomplay@boomplay.com"
            )

            if not code:
                print(f"[CONTA {i+1}]  Cdigo de verificao nao encontrado")
                browser.close()
                continue

            page.fill('input[name="verifyCode"]', code)
            form.locator('input[name="username"]').fill(user["username"])
            form.locator('input[name="pw"]').fill("Suwel2003@")
            form.locator('input[name="rePw"]').fill("Suwel2003@")

            page.locator('label.checkbox').click()
            page.wait_for_timeout(5000)

            form.locator('input[type="submit"]').click()
            page.wait_for_timeout(5000)

            save_account(emaile, password)
            STATS["accounts_created"] += 1
            print(f"[CONTA {i+1}]  Conta criada com sucesso!")

            browser.close()


# ===========================================
# DASHBOARD HELPERS
# ===========================================

def register_error(url, code="0", message="Erro desconhecido", tipo="conn"):
    STATS["errors"] += 1
    if url in URL_STATS:
        URL_STATS[url]["errors"] += 1
        URL_STATS[url]["last_seen"] = time.time()
    HISTORY.append({"type": "error"})
    ERROR_LOG.append({
        "time":    time.strftime("%H:%M:%S"),
        "url":     url,
        "code":    str(code),
        "message": message,
        "tipo":    tipo,
    })
    if len(ERROR_LOG) > 50:
        ERROR_LOG.pop(0)


def get_url_stats_for_dashboard():
    result = {}
    for url, data in URL_STATS.items():
        last = data.get("last_seen", time.time())
        diff = time.time() - last

        if diff < 300:
            status = "alive"
        elif diff < 900:
            status = "warn"
        else:
            status = "dead"

        s = int(diff)
        if s < 60:
            session_time = f"{s}s atrs"
        elif s < 3600:
            session_time = f"{s // 60}m {s % 60}s atrs"
        else:
            session_time = f"{s // 3600}h {(s % 3600) // 60}m atrs"

        result[url] = {
            "success":      data["success"],
            "errors":       data["errors"],
            "status":       status,
            "session_time": session_time,
        }
    return result


# ===========================================
# USER AGENTS
# ===========================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)",
    "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
] * 5


# ===========================================
# COMPORTAMENTO HUMANO
# ===========================================

async def human_behavior(page):
    for _ in range(random.randint(3, 7)):
        x = random.randint(100, 1800)
        y = random.randint(100, 900)
        await page.mouse.move(x, y, steps=random.randint(5, 20))
        await asyncio.sleep(random.uniform(0.2, 1.2))
    for _ in range(random.randint(2, 5)):
        await page.mouse.wheel(0, random.randint(200, 800))
        await asyncio.sleep(random.uniform(0.5, 1.5))
    await asyncio.sleep(random.uniform(1, 3))


# ===========================================
# WAIT UNTIL PLAY
# ===========================================

async def wait_until_play(page, worker_id, url, max_tries=5):
    for i in range(max_tries):
        try:
            content = await page.content()
            if "too many requests" in content.lower():
                print(f"[W{worker_id}]  Texto errado, tentativa {i+1}")
                await page.reload()
                await asyncio.sleep(5)
                continue

            elif "the copyright owner has not made this available" in content.lower():
                print(f"[W{worker_id}]  Conteudo bloqueado por regiao")
                await page.reload()
                await asyncio.sleep(5)
                continue

            elif "This album is not currently available in your" in content.lower():
                print(f"[W{worker_id}]  Conteudo bloqueado por regiao")
                await page.reload()
                await asyncio.sleep(5)
                continue

            btn = page.locator("button.btn_playAll.play_all.isAlbum")
            if await btn.count() > 0 and await btn.first.is_visible():
                print(f"[W{worker_id}]  Boto encontrado em {url}")
                return True
            btn2 = page.locator("text=Play")
            if await btn2.count() > 0 and await btn2.first.is_visible():
                print(f"[W{worker_id}]  Boto Play encontrado em {url}")
                return True

        except:
            pass
        await asyncio.sleep(3)
    print(f"[W{worker_id}]  Falha ao encontrar boto em {url}")
    return False


# ===========================================
# WORKER (streaming)
# ===========================================

async def worker(p, worker_id: int):
    count = 0
    print(f"[W{worker_id}]  Iniciado")

    while True:
        count += 1

        proxy = next(proxy_pool) if proxy_pool else None
        user_agent = random.choice(USER_AGENTS)
        url = random.choice(LINKS)

        if url not in URL_STATS:
            URL_STATS[url] = {
                "success": 0,
                "errors": 0,
                "last_seen": time.time()
            }

        print(f"\n[W{worker_id}]  Sesso {count} - {url}")
        print(f"[W{worker_id}]  Proxy: {proxy['server'] if proxy else 'SEM PROXY'}")

        STATS["sessions"] += 1

        browser = None
        context = None
        page = None

        try:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context = await browser.new_context(
                viewport={
                    "width": random.choice([1366, 1920, 1536]),
                    "height": random.choice([768, 1080, 864])
                },
                user_agent=user_agent,
                locale="en-US",
                timezone_id="UTC",
                ignore_https_errors=True,
            )

            await block_ads(context)

            page = await context.new_page()

            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            #  Login com conta salva (obrigatrio) 
            logged_in = await login_account(page, worker_id)
            if not logged_in:
                # Tenta de novo com outra conta
                logged_in = await login_account(page, worker_id)
                if not logged_in:
                    print(f"[W{worker_id}]  Login falhou 2x, reiniciando sesso...")
                    continue
            await asyncio.sleep(random.uniform(2, 5))

            #  Navega para o lbum 
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                register_error(
                    url,
                    code="0",
                    message=f"Timeout ao carregar: {type(e).__name__}",
                    tipo="timeout"
                )
                continue

            await handle_popups(page, worker_id)
            await human_behavior(page)

            ok = await wait_until_play(page, worker_id, url)

            if not ok:
                register_error(url, code="0", message="wait_until_play falhou", tipo="conn")
                continue

            try:
                btn = page.locator("button.btn_playAll.play_all.isAlbum")

                if await btn.count() == 0:
                    btn = page.locator("text=Play")

                await btn.wait_for(state="visible", timeout=15000)
                await btn.hover()
                await asyncio.sleep(random.uniform(0.5, 2))
                await btn.click()

                print(f"[W{worker_id}]  Play Clicado em {url}")

                STATS["success"] += 1
                URL_STATS[url]["success"] += 1
                URL_STATS[url]["last_seen"] = time.time()
                HISTORY.append({"type": "success"})

            except Exception as e:
                register_error(
                    url,
                    code="0",
                    message=f"Boto nao encontrado: {type(e).__name__}",
                    tipo="conn"
                )
                print(f"[W{worker_id}]  Boto nao encontrado em {url}")

            await human_behavior(page)
            await asyncio.sleep(TIMER + random.randint(-60, 120))

        except Exception as e:
            print(f"[W{worker_id}]  ERRO COMPLETO")
            traceback.print_exc()

            msg = str(e)[:80] if str(e) else type(e).__name__

            if "timeout" in msg.lower():
                tipo = "timeout"
            elif "connection" in msg.lower() or "refused" in msg.lower():
                tipo = "conn"
            else:
                tipo = "server"

            register_error(url, code="0", message=msg, tipo=tipo)

        finally:
            try:
                if context:
                    await context.close()
            except:
                pass
            try:
                if browser:
                    await browser.close()
            except:
                pass

        print(f"[W{worker_id}]  Reiniciando...\n")
        await asyncio.sleep(random.uniform(3, 10))


# ===========================================
# DASHBOARD HTML (carregado de ficheiro externo)
# ===========================================

_html_path = os.path.join(BASE_DIR, "dashboard.html")
with open(_html_path, "r", encoding="utf-8") as _f:
    HTML = _f.read()


app = Flask(__name__)

@app.route("/")
def dashboard():
    uptime = int(time.time() - START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60
    s = uptime % 60

    recent = HISTORY[-50:]
    success_data = [1 if x["type"] == "success" else 0 for x in recent]
    error_data   = [1 if x["type"] == "error"   else 0 for x in recent]
    labels       = list(range(len(recent)))

    total = STATS["success"] + STATS["errors"]
    rate = round((STATS["success"] / total * 100), 1) if total > 0 else 0

    return render_template_string(
        HTML,
        uptime       = f"{h}h {m}m {s}s",
        sessions     = STATS["sessions"],
        success      = STATS["success"],
        errors       = STATS["errors"],
        accounts     = STATS["accounts_created"],
        rate         = rate,
        num_browsers = NUM_BROWSERS,
        num_proxies  = len(PROXIES),
        num_accounts_total = len(load_accounts()),
        url_stats    = get_url_stats_for_dashboard(),
        error_log    = ERROR_LOG,
        labels       = labels,
        success_data = success_data,
        error_data   = error_data,
    )

def run_dashboard():
    app.run(host="0.0.0.0", port=800, debug=False, use_reloader=False)


# ===========================================
# CLOUDFLARED TUNNEL
# ===========================================

def start_cloudflared():
    os.system(
        "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && "
        "chmod +x cloudflared && "
        "nohup ./cloudflared tunnel --url http://localhost:800 > cf.log 2>&1 &"
    )


def get_cloudflared_link():
    try:
        with open("cf.log", "r") as f:
            text = f.read()
        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", text)
        if match:
            return match.group(0)
    except:
        pass
    return None


# ===========================================
# WEBHOOK
# ===========================================

WEBHOOK_URL = "https://phpstack-1534084-6390889.cloudwaysapps.com/app/webhook.php"


def send_to_webhook(link):
    try:
        requests.post(WEBHOOK_URL, json={"link": link})
        print("[WEBHOOK] Enviado:", link)
    except Exception as e:
        print("[WEBHOOK] Erro:", e)


# ===========================================
# MAIN
# ===========================================

async def main(create_accs=False, num_accounts=5):
    # Inicia cloudflared tunnel
    start_cloudflared()
    print("[CLOUDFLARED] Iniciando tunnel...")
    await asyncio.sleep(5)

    # Pega o link do tunnel e envia para webhook
    cf_link = get_cloudflared_link()
    if cf_link:
        print(f"[CLOUDFLARED] Dashboard: {cf_link}")
        send_to_webhook(cf_link)
    else:
        print("[CLOUDFLARED] Link ainda nao disponivel, tenta cf.log depois")

    # Inicia o dashboard web
    threading.Thread(target=run_dashboard, daemon=True).start()

    # So cria contas se pedido (opcao 3 - completo)
    if create_accs:
        account_thread = threading.Thread(target=create_accounts, args=(num_accounts,), daemon=True)
        account_thread.start()

    # Inicia os workers de streaming
    async with async_playwright() as p:
        await asyncio.gather(*[worker(p, i + 1) for i in range(NUM_BROWSERS)])


if __name__ == "__main__":

    def show_menu():
        print()
        print("=" * 50)
        print("  BOOMPLAY FULL - MENU PRINCIPAL")
        print("=" * 50)
        print()
        print("  [1] Criar contas")
        print("  [2] Streaming (com login + dashboard)")
        print("  [3] Completo (criar contas + streaming)")
        print("  [4] Ver contas salvas")
        print("  [0] Sair")
        print()
        print("=" * 50)

    while True:
        show_menu()
        choice = input("  Escolhe uma opcao: ").strip()

        if choice == "1":
            print()
            print("-" * 40)
            print("  CRIACAO DE CONTAS")
            print("-" * 40)
            try:
                num = int(input("  Quantas contas queres criar? "))
            except ValueError:
                print("  Numero invalido, usando 5")
                num = 5
            print(f"\n  > Criando {num} contas...\n")
            create_accounts(num)
            print("\n  OK - Processo de criacao terminado!")
            input("\n  Pressiona ENTER para voltar ao menu...")

        elif choice == "2":
            print()
            print("-" * 40)
            print("  STREAMING + DASHBOARD")
            print("-" * 40)
            try:
                num = int(input("  Quantos browsers/workers? [padrao: 20] ") or "20")
            except ValueError:
                num = 20
            NUM_BROWSERS = num
            accounts = load_accounts()
            print(f"\n  Contas disponiveis para login: {len(accounts)}")
            if not accounts:
                print("  AVISO: Nenhuma conta salva! Os workers vao rodar sem login.")
                print("  DICA: Cria contas primeiro (opcao 1) para melhor resultado.")
            print(f"  > Iniciando {NUM_BROWSERS} workers + dashboard na porta 800...\n")
            asyncio.run(main(create_accs=False))

        elif choice == "3":
            print()
            print("-" * 40)
            print("  MODO COMPLETO")
            print("-" * 40)
            try:
                num_acc = int(input("  Quantas contas criar? [padrao: 5] ") or "5")
            except ValueError:
                num_acc = 5
            try:
                num_br = int(input("  Quantos browsers/workers? [padrao: 20] ") or "20")
            except ValueError:
                num_br = 20
            NUM_BROWSERS = num_br
            print(f"\n  > Criando {num_acc} contas + {NUM_BROWSERS} workers...\n")
            asyncio.run(main(create_accs=True, num_accounts=num_acc))

        elif choice == "4":
            print()
            print("-" * 40)
            print("  CONTAS SALVAS")
            print("-" * 40)
            accounts = load_accounts()
            if not accounts:
                print("  (nenhuma conta salva)")
            else:
                for i, acc in enumerate(accounts, 1):
                    print(f"  {i:3d}. {acc['email']}  |  {acc['password']}")
                print(f"\n  Total: {len(accounts)} contas")
            input("\n  Pressiona ENTER para voltar ao menu...")

        elif choice == "0":
            print("\n  Ate logo!\n")
            break

        else:
            print("  Opcao invalida, tenta de novo.")
