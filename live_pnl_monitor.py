#!/usr/bin/env python3
"""
Oscar Live P&L Monitor — Met à jour live_pnl.txt toutes les 30s
Usage: python live_pnl_monitor.py  (laisse tourner dans un terminal à part)
"""

import json
import time
import signal
import sys
from datetime import datetime
from pathlib import Path

import ccxt

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
LIVE_PNL_FILE = BASE_DIR / "live_pnl.txt"

# Config
SYMBOL = "BTC/USDT"
STARTING_BALANCE = 30.0
UPDATE_INTERVAL = 30  # secondes

exchange = ccxt.binance({"enableRateLimit": True})
_shutdown = False


def signal_handler(signum, frame):
    global _shutdown
    print("\n🛑 Arrêt demandé...")
    _shutdown = True


def fetch_price() -> float:
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        return float(ticker.get("last") or ticker.get("close") or 0)
    except Exception as e:
        return 0.0


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "balance_usdt": STARTING_BALANCE,
        "total_asset": 0.0,
        "total_invested": 0.0,
    }


def calculate_pnl(state: dict, price: float) -> dict:
    cash = state.get("balance_usdt", 0.0)
    btc = state.get("total_asset", 0.0)
    invested = state.get("total_invested", 0.0)
    fees = state.get("total_fees_paid", 0.0)
    buy_count = state.get("buy_count", 0)

    btc_value = btc * price
    total = cash + btc_value
    pnl = total - STARTING_BALANCE
    pnl_pct = (pnl / STARTING_BALANCE * 100) if STARTING_BALANCE > 0 else 0

    if pnl > 0.01:
        status = "[GAIN]"
    elif pnl < -0.01:
        status = "[PERTE]"
    else:
        status = "[NEUTRE]"

    return {
        "cash": cash,
        "btc": btc,
        "btc_value": btc_value,
        "total": total,
        "invested": invested,
        "fees": fees,
        "buy_count": buy_count,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "status": status,
    }


def format_usd(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def write_live_pnl(pnl_data: dict, price: float) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "========================================",
        "  OSCAR — P&L TEMPS RÉEL",
        "========================================",
        f"Dernière MAJ: {now}",
        f"Prix BTC:     {format_usd(price)} USDT",
        "────────────────────────────────────────",
        f"Cash USDT:    {format_usd(pnl_data['cash'])}",
        f"BTC:          {pnl_data['btc']:.8f}",
        f"Valeur BTC:   {format_usd(pnl_data['btc_value'])} USDT",
        f"TOTAL:        {format_usd(pnl_data['total'])} USDT",
        f"Investi:      {format_usd(pnl_data['invested'])} USDT",
        f"Frais cumulés:{format_usd(pnl_data['fees'])} USDT",
        f"Achats:       {pnl_data['buy_count']}",
        f"P&L:          {format_usd(pnl_data['pnl'])} USDT ({pnl_data['pnl_pct']:+.2f}%)",
        f"STATUS:       {pnl_data['status']}",
        "========================================",
        f"Prochaine MAJ dans ~{UPDATE_INTERVAL}s (Ctrl+C pour arrêter)",
    ]
    content = "\n".join(lines) + "\n"

    # Atomic write
    tmp = LIVE_PNL_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    tmp.replace(LIVE_PNL_FILE)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("========================================")
    print("  OSCAR Live P&L Monitor")
    print("========================================")
    print(f"Fichier de sortie: {LIVE_PNL_FILE}")
    print(f"Intervalle: {UPDATE_INTERVAL}s")
    print("Appuie sur Ctrl+C pour arrêter\n")

    while not _shutdown:
        state = load_state()
        price = fetch_price()

        if price > 0:
            pnl_data = calculate_pnl(state, price)
            write_live_pnl(pnl_data, price)

            # Affichage console bref
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"BTC: {price:,.0f} | Total: {pnl_data['total']:,.2f} | "
                  f"P&L: {pnl_data['pnl']:+.2f} ({pnl_data['pnl_pct']:+.2f}%) {pnl_data['status']}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Erreur prix")

        # Attente avec vérification shutdown toutes les secondes
        for _ in range(UPDATE_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)

    # Dernière écriture avant sortie
    state = load_state()
    price = fetch_price()
    if price > 0:
        pnl_data = calculate_pnl(state, price)
        write_live_pnl(pnl_data, price)

    print("\n✅ Moniteur arrêté. live_pnl.txt à jour.")
    print(f"Ouvre {LIVE_PNL_FILE} pour voir le dernier P&L.")


if __name__ == "__main__":
    main()