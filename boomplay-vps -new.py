
import subprocess
import sys

def install_packages(packages):
    """
    Verifica e instala pacotes Python automaticamente.
    """
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            print(f"[INFO] Instalando {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        else:
            print(f"[INFO] Pacote {package} já está instalado.")

# Lista de pacotes que você usa no seu código
required_packages = [
    "asyncio",      # geralmente já vem com Python
    "playwright",
    "flask"
]

install_packages(required_packages)

# Se for Playwright, precisamos rodar o install do browser também
try:
    from playwright.async_api import async_playwright
    import playwright
    # Instala os browsers se ainda não tiver feito
    subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)
except Exception as e:
    print(f"[ERRO] Não foi possível instalar o Playwright: {e}")
    
    
import asyncio
import random
import traceback
from itertools import cycle
from playwright.async_api import async_playwright
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template_string
import time
import os    
    
# ─────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────
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
    "https://www.boomplay.com/albums/116152715?from=search"
]  # lista de URLs

TIMER = 300
NUM_BROWSERS = 30

START_TIME = time.time()
STATS = {"sessions": 0, "success": 0, "errors": 0}
HISTORY = []       # {"type": "success"|"error"}
ERROR_LOG = []     # {"time", "url", "code", "message", "tipo"}
URL_STATS = {}     # {"success": 0, "errors": 0, "last_seen": float}


# ─────────────────────────────
# BLOQUEIO DE ADS
# ─────────────────────────────
async def block_ads(context):
    async def handler(route):
        url = route.request.url
        if any(x in url for x in ["doubleclick","googleads","googlesyndication","adservice"]):
            await route.abort()
        else:
            await route.continue_()
    await context.route("**/*", handler)

# ─────────────────────────────
# POPUPS
# ─────────────────────────────
async def handle_popups(page, wid):
    try:
        selectors = ["button.fc-cta-consent","button:has-text('Accept')","text=Accept"]
        for sel in selectors:
            btn = page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                print(f"[W{wid}] ✅ Popup fechado")
                return
        for frame in page.frames:
            try:
                btn = frame.locator("button:has-text('Accept'), button:has-text('Close')")
                if await btn.count() > 0:
                    await btn.first.click()
                    print(f"[W{wid}] ✅ Popup iframe fechado")
                    return
            except:
                pass
    except:
        pass
        
        
# ─────────────────────────────
# HELPERS DE DASHBOARD
# ─────────────────────────────
def register_error(url, code="0", message="Erro desconhecido", tipo="conn"):
    """Regista um erro no log e actualiza URL_STATS."""
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
        "tipo":    tipo,   # "timeout" | "server" | "conn"
    })
    # Mantém só os últimos 50 erros
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
            session_time = f"{s}s atrás"
        elif s < 3600:
            session_time = f"{s // 60}m {s % 60}s atrás"
        else:
            session_time = f"{s // 3600}h {(s % 3600) // 60}m atrás"

        result[url] = {
            "success":      data["success"],
            "errors":       data["errors"],
            "status":       status,
            "session_time": session_time,
        }
    return result


# ─────────────────────────────
# USER AGENTS
# ─────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4)",
    "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.85 Safari/537.36",
] * 5

async def wait_until_play(page, worker_id, url, max_tries=5):
    for i in range(max_tries):
        try:
            content = await page.content()
            if "too many requests" in content.lower():
                print(f"[W{worker_id}] ⚠️ Texto errado, tentativa {i+1}")
                await page.reload()
                await asyncio.sleep(5)
                continue
           
            elif "the copyright owner has not made this available" in content.lower():
                print(f"[W{worker_id}] 🌍 Conteúdo bloqueado por região")
                await page.reload()
                await asyncio.sleep(5)
                continue

            elif "This album is not currently available in your" in content.lower():
                print(f"[W{worker_id}] 🌍 Conteúdo bloqueado por região")
                await page.reload()
                await asyncio.sleep(5)
                continue

            btn = page.locator("button.btn_playAll.play_all.isAlbum")
            if await btn.count() > 0 and await btn.first.is_visible():
                print(f"[W{worker_id}] ✅ Botão encontrado em {url}")
                return True
            btn2 = page.locator("text=Play")
            if await btn2.count() > 0 and await btn2.first.is_visible():
                print(f"[W{worker_id}] ✅ Botão Play encontrado em {url}")
                return True

        except:
            pass
        await asyncio.sleep(3)
    print(f"[W{worker_id}] ❌ Falha ao encontrar botão em {url}")
    return False

# ─────────────────────────────
# PROXIES
# ─────────────────────────────
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
        print("⚠️ proxy.txt não encontrado")
    return proxies

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
proxy_path = os.path.join(BASE_DIR, "vps.txt")

PROXIES = load_proxies(proxy_path)
proxy_pool = cycle(PROXIES) if PROXIES else None

# ─────────────────────────────
# COMPORTAMENTO HUMANO
# ─────────────────────────────
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

# ─────────────────────────────
# WORKER
# ─────────────────────────────
async def worker(p, worker_id: int):
    count = 0
    print(f"[W{worker_id}] 🚀 Iniciado")

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

        print(f"\n[W{worker_id}] 🌐 Sessão {count} - {url}")
        print(f"[W{worker_id}] 🔌 Proxy: {proxy['server'] if proxy else 'SEM PROXY'}")

        STATS["sessions"] += 1

        browser = None
        context = None
        page = None

        try:
            # ── launch browser ──
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

            # ── context ──
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

            # ── navigation ──
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            except Exception as e:
                register_error(
                    url,
                    code="0",
                    message=f"Timeout ao carregar: {type(e).__name__}",
                    tipo="timeout"
                )
                continue  # não fecha browser manualmente aqui

            await handle_popups(page, worker_id)
            await human_behavior(page)

            ok = await wait_until_play(page, worker_id, url)

            if not ok:
                register_error(url, code="0", message="wait_until_play falhou", tipo="conn")
                continue

            # ── Play click ──
            try:
                btn = page.locator("button.btn_playAll.play_all.isAlbum")

                if await btn.count() == 0:
                    btn = page.locator("text=Play")

                await btn.wait_for(state="visible", timeout=15000)

                await btn.hover()
                await asyncio.sleep(random.uniform(0.5, 2))

                await btn.click()

                print(f"[W{worker_id}] ✅ Play Clicado em {url}")

                STATS["success"] += 1
                URL_STATS[url]["success"] += 1
                URL_STATS[url]["last_seen"] = time.time()

                HISTORY.append({"type": "success"})

            except Exception as e:
                register_error(
                    url,
                    code="0",
                    message=f"Botão não encontrado: {type(e).__name__}",
                    tipo="conn"
                )
                print(f"[W{worker_id}] ⚠️ Botão não encontrado em {url}")

            await human_behavior(page)

            await asyncio.sleep(
                TIMER + random.randint(-60, 120)
            )

        except Exception as e:
            print(f"[W{worker_id}] ❌ ERRO COMPLETO")
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
            # ── cleanup seguro ──
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

        print(f"[W{worker_id}] 🔄 Reiniciando...\n")

        await asyncio.sleep(random.uniform(3, 10))

# ─────────────────────────────
# DASHBOARD HTML
# ─────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <title>Dashboard PRO MAX</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;600;800&display=swap" rel="stylesheet">
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    :root{
      --bg:#050a12; --surface:#0c1628; --border:#1a3a5c;
      --accent:#00d4ff; --accent2:#ff3d71; --success:#00e096;
      --warning:#ffaa00; --text:#c8e6f5; --muted:#4a7a9b;
    }
    body{font-family:'Exo 2',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:1.5rem;position:relative;overflow-x:hidden;}
    body::after{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,212,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,212,255,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0;}
    body::before{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.06) 2px,rgba(0,0,0,.06) 4px);pointer-events:none;z-index:1;}
    .content{position:relative;z-index:2;max-width:1100px;margin:0 auto;}
    header{display:flex;align-items:center;justify-content:space-between;margin-bottom:2rem;padding-bottom:1rem;border-bottom:1px solid var(--border);}
    .logo{display:flex;align-items:center;gap:.75rem;}
    .logo-icon{width:40px;height:40px;background:linear-gradient(135deg,#00d4ff,#0066ff);border-radius:10px;display:grid;place-items:center;font-size:1.2rem;animation:glowpulse 3s ease-in-out infinite;}
    @keyframes glowpulse{0%,100%{box-shadow:0 0 12px rgba(0,212,255,.3)}50%{box-shadow:0 0 28px rgba(0,212,255,.7)}}
    h1{font-size:1.5rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;background:linear-gradient(90deg,#00d4ff,#fff 60%,#00d4ff);background-size:200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shimmer 4s linear infinite;}
    @keyframes shimmer{0%{background-position:200% center}100%{background-position:-200% center}}
    .live{display:flex;align-items:center;gap:.5rem;background:rgba(0,224,150,.1);border:1px solid rgba(0,224,150,.35);border-radius:20px;padding:.3rem .9rem;font-size:.72rem;font-weight:600;color:var(--success);letter-spacing:.08em;}
    .dot{width:7px;height:7px;border-radius:50%;background:var(--success);animation:blink 1.2s ease-in-out infinite;}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
    .sec{font-size:.65rem;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:.9rem;display:flex;align-items:center;gap:.6rem;}
    .sec::after{content:'';flex:1;height:1px;background:var(--border);}
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:2rem;}
    .kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.3rem 1.5rem;position:relative;overflow:hidden;transition:transform .2s,border-color .2s;}
    .kpi:hover{transform:translateY(-3px);border-color:var(--accent);}
    .kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0;}
    .kpi.t::before{background:linear-gradient(90deg,#0066ff,#00d4ff);}
    .kpi.s::before{background:linear-gradient(90deg,#7b2ff7,#c044ff);}
    .kpi.ok::before{background:linear-gradient(90deg,#00b377,#00e096);}
    .kpi.er::before{background:linear-gradient(90deg,#cc2200,#ff3d71);}
    .kpi-label{font-size:.65rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:.5rem;}
    .kpi-val{font-family:'Share Tech Mono',monospace;font-size:2rem;line-height:1;color:#fff;}
    .kpi.ok .kpi-val{color:var(--success);}
    .kpi.er .kpi-val{color:var(--accent2);}
    .chart-box{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:1.5rem;margin-bottom:2rem;}
    .chart-legend{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:12px;font-size:12px;color:var(--muted);}
    .chart-legend span{display:flex;align-items:center;gap:5px;}
    .leg-dot{width:10px;height:10px;border-radius:2px;display:inline-block;}
    .tabs{display:flex;gap:.5rem;margin-bottom:1rem;}
    .tab{font-family:'Exo 2',sans-serif;font-size:.72rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;padding:.45rem 1.1rem;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:all .2s;}
    .tab:hover{border-color:var(--muted);color:var(--text);}
    .tab.active{background:var(--surface);border-color:var(--accent);color:var(--accent);}
    .tab.err-tab.active{border-color:var(--accent2);color:var(--accent2);}
    .tab-panel{display:none;}
    .tab-panel.active{display:block;}
    .url-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;}
    .url-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.2rem 1.4rem;transition:border-color .2s,transform .2s;}
    .url-card:hover{border-color:var(--muted);transform:translateY(-2px);}
    .url-card.dead{border-color:rgba(255,61,113,.5);}
    .url-name{font-family:'Share Tech Mono',monospace;font-size:.78rem;color:var(--accent);word-break:break-all;margin-bottom:.8rem;padding-bottom:.7rem;border-bottom:1px solid var(--border);}
    .url-stats{display:flex;gap:1rem;flex-wrap:wrap;align-items:center;}
    .ustat{font-size:.82rem;font-weight:600;display:flex;align-items:center;gap:.4rem;}
    .ustat.ok{color:var(--success);}
    .ustat.er{color:var(--accent2);}
    .badge{background:rgba(255,255,255,.06);border-radius:6px;padding:.12rem .45rem;font-family:'Share Tech Mono',monospace;font-size:.88rem;}
    .time-badge{display:inline-flex;align-items:center;gap:.35rem;font-family:'Share Tech Mono',monospace;font-size:.75rem;padding:.2rem .55rem;border-radius:6px;border:1px solid;margin-top:.65rem;}
    .time-badge.alive{color:var(--success);border-color:rgba(0,224,150,.35);background:rgba(0,224,150,.07);}
    .time-badge.warn{color:var(--warning);border-color:rgba(255,170,0,.35);background:rgba(255,170,0,.07);}
    .time-badge.dead{color:var(--accent2);border-color:rgba(255,61,113,.35);background:rgba(255,61,113,.07);}
    .pulse-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;}
    .alive .pulse-dot{background:var(--success);animation:blink 1.2s ease-in-out infinite;}
    .warn  .pulse-dot{background:var(--warning);animation:blink 1.8s ease-in-out infinite;}
    .dead  .pulse-dot{background:var(--accent2);}
    .err-wrap{background:var(--surface);border:1px solid var(--border);border-radius:16px;overflow:hidden;}
    .err-table{width:100%;border-collapse:collapse;font-size:.8rem;}
    .err-table th{font-size:.62rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);text-align:left;padding:.6rem .9rem;border-bottom:1px solid var(--border);}
    .err-table td{padding:.65rem .9rem;border-bottom:1px solid rgba(26,58,92,.5);vertical-align:middle;}
    .err-table tr:last-child td{border-bottom:none;}
    .err-table tr:hover td{background:rgba(255,255,255,.02);}
    .err-url{font-family:'Share Tech Mono',monospace;color:var(--accent);font-size:.75rem;}
    .err-code{font-family:'Share Tech Mono',monospace;font-size:.8rem;font-weight:600;}
    .err-code.c4{color:var(--warning);}
    .err-code.c5{color:var(--accent2);}
    .err-code.c0{color:var(--muted);}
    .err-msg{color:var(--text);max-width:260px;font-size:.78rem;}
    .err-time{color:var(--muted);font-family:'Share Tech Mono',monospace;font-size:.73rem;white-space:nowrap;}
    .err-badge{display:inline-block;font-size:.65rem;padding:.1rem .45rem;border-radius:5px;font-weight:600;}
    .err-badge.timeout{background:rgba(255,170,0,.12);color:var(--warning);border:1px solid rgba(255,170,0,.3);}
    .err-badge.server{background:rgba(255,61,113,.12);color:var(--accent2);border:1px solid rgba(255,61,113,.3);}
    .err-badge.conn{background:rgba(74,122,155,.2);color:var(--muted);border:1px solid rgba(74,122,155,.3);}
    .err-count-pill{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:rgba(255,61,113,.15);color:var(--accent2);font-size:.65rem;font-weight:700;border:1px solid rgba(255,61,113,.3);margin-left:.4rem;vertical-align:middle;}
    footer{text-align:center;margin-top:2.5rem;font-size:.65rem;color:var(--muted);letter-spacing:.1em;}
  </style>
</head>
<body>
<div class="content">

  <header>
    <div class="logo">
      <div class="logo-icon">🚀</div>
      <h1>Dashboard Pro Max</h1>
    </div>
    <div class="live"><span class="dot"></span>AO VIVO · 5s</div>
  </header>

  <p class="sec">Métricas gerais</p>
  <div class="kpi-grid">
    <div class="kpi t"> <div class="kpi-label">⏱ Tempo ativo</div><div class="kpi-val">{{ uptime }}</div></div>
    <div class="kpi s"> <div class="kpi-label">🌐 Sessões</div>   <div class="kpi-val">{{ sessions }}</div></div>
    <div class="kpi ok"><div class="kpi-label">✅ Sucesso</div>   <div class="kpi-val">{{ success }}</div></div>
    <div class="kpi er"><div class="kpi-label">❌ Erros</div>     <div class="kpi-val">{{ errors }}</div></div>
  </div>

  <p class="sec">Desempenho ao longo do tempo</p>
  <div class="chart-box">
    <div class="chart-legend">
      <span><span class="leg-dot" style="background:#00e096;"></span>Sucesso</span>
      <span><span class="leg-dot" style="background:#ff3d71;"></span>Erros</span>
    </div>
    <div style="position:relative;height:220px;">
      <canvas id="chart"></canvas>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('urls',this)">🌍 URLs</button>
    <button class="tab err-tab" onclick="switchTab('erros',this)">
      ❌ Log de Erros
      <span class="err-count-pill">{{ error_log|length }}</span>
    </button>
  </div>

  <!-- Tab: URLs -->
  <div class="tab-panel active" id="tab-urls">
    <div class="url-grid">
      {% for url, data in url_stats.items() %}
      <div class="url-card {% if data.status == 'dead' %}dead{% endif %}">
        <div class="url-name">{{ url }}</div>
        <div class="url-stats">
          <div class="ustat ok">✅ <span class="badge">{{ data.success }}</span></div>
          <div class="ustat er">❌ <span class="badge">{{ data.errors }}</span></div>
        </div>
        <div class="time-badge {{ data.status }}">
          <span class="pulse-dot"></span>
          <span>
            {% if data.status == 'alive' %}● Ativo
            {% elif data.status == 'warn' %}● Lento
            {% else %}● Inativo{% endif %}
          </span>
          <span style="opacity:.7">·</span>
          <span>{{ data.session_time }}</span>
        </div>
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- Tab: Erros -->
  <div class="tab-panel" id="tab-erros">
    <div class="err-wrap">
      <table class="err-table">
        <thead>
          <tr>
            <th>Hora</th>
            <th>URL</th>
            <th>Código</th>
            <th>Mensagem</th>
            <th>Tipo</th>
          </tr>
        </thead>
        <tbody>
          {% for err in error_log|reverse %}
          <tr>
            <td class="err-time">{{ err.time }}</td>
            <td class="err-url">{{ err.url }}</td>
            <td>
              <span class="err-code
                {% if err.code|string|first == '5' %}c5
                {% elif err.code|string|first == '4' %}c4
                {% else %}c0{% endif %}">
                {{ err.code if err.code else '—' }}
              </span>
            </td>
            <td class="err-msg">{{ err.message }}</td>
            <td>
              <span class="err-badge {{ err.tipo }}">
                {% if err.tipo == 'timeout' %}Timeout
                {% elif err.tipo == 'server' %}Servidor
                {% else %}Conexão{% endif %}
              </span>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <footer>DASHBOARD PRO MAX &nbsp;·&nbsp; Atualiza a cada 5s &nbsp;·&nbsp; © 2025</footer>
</div>

<script>
function switchTab(id, btn){
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
}
var ctx = document.getElementById('chart').getContext('2d');
new Chart(ctx, {
  type: 'line',
  data: {
    labels: {{ labels }},
    datasets: [
      {label:'Sucesso',data:{{ success_data }},borderColor:'#00e096',backgroundColor:'rgba(0,224,150,.08)',borderWidth:2,pointRadius:3,pointBackgroundColor:'#00e096',tension:.4,fill:true},
      {label:'Erros',  data:{{ error_data }},  borderColor:'#ff3d71',backgroundColor:'rgba(255,61,113,.08)',borderWidth:2,pointRadius:3,pointBackgroundColor:'#ff3d71',tension:.4,fill:true}
    ]
  },
  options:{
    responsive:true,maintainAspectRatio:false,animation:{duration:400},
    plugins:{legend:{display:false},tooltip:{backgroundColor:'#0c1628',borderColor:'#1a3a5c',borderWidth:1,titleColor:'#00d4ff',bodyColor:'#c8e6f5',padding:10}},
    scales:{
      x:{ticks:{color:'#4a7a9b',font:{size:11}},grid:{color:'rgba(26,58,92,.5)'}},
      y:{ticks:{color:'#4a7a9b',font:{size:11}},grid:{color:'rgba(26,58,92,.5)'}}
    }
  }
});
</script>
</body>
</html>
"""

# ─────────────────────────────
# FLASK
# ─────────────────────────────
app = Flask(__name__)

@app.route("/")
def dashboard():
    uptime = int(time.time() - START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60
    s = uptime % 60

    recent = HISTORY[-30:]
    success_data = [1 if x["type"] == "success" else 0 for x in recent]
    error_data   = [1 if x["type"] == "error"   else 0 for x in recent]
    labels       = list(range(len(recent)))

    return render_template_string(
        HTML,
        uptime       = f"{h}h {m}m {s}s",
        sessions     = STATS["sessions"],
        success      = STATS["success"],
        errors       = STATS["errors"],
        url_stats    = get_url_stats_for_dashboard(),
        error_log    = ERROR_LOG,
        labels       = labels,
        success_data = success_data,
        error_data   = error_data,
    )

def run_dashboard():
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)

# ─────────────────────────────
# MAIN
# ─────────────────────────────
async def main():
    threading.Thread(target=run_dashboard, daemon=True).start()
    async with async_playwright() as p:
        await asyncio.gather(*[worker(p, i + 1) for i in range(NUM_BROWSERS)])

asyncio.run(main())