#!/bin/bash

echo "=================================="
echo "  BOOMPLAY - INICIAR EM BACKGROUND"
echo "=================================="
echo ""
echo "  [1] Criar contas"
echo "  [2] Streaming (com login + dashboard)"
echo "  [3] Completo (criar contas + streaming)"
echo "  [4] Parar tudo"
echo "  [5] Ver logs"
echo "  [6] Ver sessoes ativas"
echo "  [7] Instalar Sofware"
echo ""
echo "=================================="
read -p "  Escolhe: " opcao


install_software() {

    echo "[1/5] Atualizando sistema..."

    echo "[2/5] Instalando dependências..."
    sudo apt install -y \
        python3 \
        python3-pip \
        git \
        curl \
        wget \
        unzip \
        screen \
        xvfb

    echo "[3/5] Atualizando pip..."
    python3 -m pip install --upgrade pip

    echo "[4/5] Instalando bibliotecas Python..."
    pip3 install -U playwright flask

    echo "[5/5] Instalando Chromium do Playwright..."
    playwright install
	playwright install-deps

    echo ""
    echo "Instalação concluída."
}
case $opcao in
  1)
    read -p "  Quantas contas? " num
    screen -dmS boom-contas bash -c "echo -e '1\n${num}' | python3 boomplay_full.py > contas.log 2>&1"
    echo ""
    echo "  OK - Criacao de contas iniciada em background"
    echo "  Ver logs: tail -f contas.log"
    echo "  Entrar na sessao: screen -r boom-contas"
    ;;
  2)
    read -p "  Quantos workers? [20] " workers
    workers=${workers:-20}
    screen -dmS boom-stream bash -c "echo -e '2\n${workers}' | python3 boomplay_full.py > stream.log 2>&1"
    echo ""
    echo "  OK - Streaming iniciado em background"
    echo "  Ver logs: tail -f stream.log"
    echo "  Entrar na sessao: screen -r boom-stream"
    ;;
  3)
    read -p "  Quantas contas? [5] " contas
    contas=${contas:-5}
    read -p "  Quantos workers? [20] " workers
    workers=${workers:-20}
    screen -dmS boom-full bash -c "echo -e '3\n${contas}\n${workers}' | python3 boomplay_full.py > full.log 2>&1"
    echo ""
    echo "  OK - Modo completo iniciado em background"
    echo "  Ver logs: tail -f full.log"
    echo "  Entrar na sessao: screen -r boom-full"
    ;;
  4)
    echo ""
    echo "  Parando todas as sessoes..."
    screen -ls | grep boom | awk '{print $1}' | xargs -I {} screen -X -S {} quit 2>/dev/null
    pkill -f boomplay_full.py 2>/dev/null
    pkill -f cloudflared 2>/dev/null
    echo "  OK - Tudo parado"
    ;;
  5)
    echo ""
    echo "  Logs disponiveis:"
    ls -la *.log 2>/dev/null || echo "  (nenhum log encontrado)"
    echo ""
    read -p "  Qual log ver? (stream/contas/full/cf): " log
    tail -50 "${log}.log" 2>/dev/null || echo "  Ficheiro nao encontrado"
    ;;
  6)
    echo ""
    echo "  Sessoes screen ativas:"
    screen -ls | grep boom || echo "  (nenhuma)"
    ;;
   7)
    install_software
    ;;
  *)
    echo "  Opcao invalida"
    ;;
esac


