#!/usr/bin/env python3
"""
Oscar Status — Affichage instantané de l'état du bot
Usage: python status.py
"""

import os
import sys
from pathlib import Path
import json

# Ajoute le dossier parent au path pour importer oscar.py si besoin
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import ccxt

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
TRADES_FILE = BASE_DIR / "trades.csv"

load_dotenv()

# Config
SYMBOL = os.getenv("SYMBOL", "BTC/USDT")
WEEKLY_AMOUNT = float(os.getenv("WEEKLY_AMOUNT", "7.5"))
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "30"))
BUY_DAY = int(os.getenv("BUY_DAY", "0"))
BUY_HOUR = int(os.getenv("BUY_HOUR", "0"))
BUY_MINUTE = int(os.getenv("BUY_MINUTE", "0"))

FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005
TOTAL_COST_RATE = FEE_RATE + SLIPPAGE_RATE


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "balance_usdt": STARTING_BALANCE,
        "total_asset": 0.0,
        "total_invested": 0.0,
        "last_buy_date": None,
        "total_fees_paid": 0.0,
        "buy_count": 0,
    }


def fetch_price(symbol: str) -> float:
    """Récupère le prix spot depuis Binance."""
    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker.get("last") or ticker.get("close") or 0)
    except Exception as e:
        print(f"❌ Erreur prix: {e}")
        return 0.0


def format_usd(v: float) -> str:
    return f"{v:,.2f} $".replace(",", " ").replace(".", ",")


def main():
    print("═══════════════════════════════════")
    print("  OSCAR — STATUS")
    print("═══════════════════════════════════")

    # 1. État
    state = load_state()

    # 2. Prix actuel
    price = fetch_price(SYMBOL)
    if price == 0:
        print("⚠️ Impossible de récupérer le prix. Données partielles uniquement.")
        price = None

    # 3. Calculs
    cash = state["balance_usdt"]
    asset_qty = state["total_asset"]
    total_invested = state["total_invested"]
    total_fees = state.get("total_fees_paid", 0.0)
    buy_count = state.get("buy_count", 0)
    last_buy = state.get("last_buy_date", "Jamais")

    if price:
        asset_value = asset_qty * price
        total_value = cash + asset_value
        pnl = total_value - STARTING_BALANCE
        pnl_pct = (pnl / STARTING_BALANCE * 100) if STARTING_BALANCE > 0 else 0
    else:
        asset_value = total_value = pnl = pnl_pct = 0

    # 4. Affichage
    days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    next_buy_day = days[BUY_DAY % 7]

    print(f"\n  📊 CONFIGURATION")
    print(f"  ────────────────────────────────")
    print(f"  Paire:           {SYMBOL}")
    print(f"  Achat hebdo:     {format_usd(WEEKLY_AMOUNT)}")
    print(f"  Prochain achat:  {next_buy_day} {BUY_HOUR:02d}:{BUY_MINUTE:02d} UTC")
    print(f"  Capital initial: {format_usd(STARTING_BALANCE)}")

    print(f"\n  💰 PORTEFEUILLE")
    print(f"  ────────────────────────────────")
    print(f"  Cash (USDT):     {format_usd(cash)}")
    if price:
        print(f"  {SYMBOL.split('/')[0]}:            {asset_qty:.8f} ({format_usd(asset_value)})")
        print(f"  Valeur totale:   {format_usd(total_value)}")
    else:
        print(f"  {SYMBOL.split('/')[0]}:            {asset_qty:.8f} (prix indisponible)")

    print(f"\n  📈 PERFORMANCE")
    print(f"  ────────────────────────────────")
    print(f"  Total investi:   {format_usd(total_invested)}")
    print(f"  Frais cumulés:   {format_usd(total_fees)}")
    if price:
        print(f"  P&L:             {format_usd(pnl).replace('+', '').replace('-', '')} ({pnl_pct:+.2f}%)")
    print(f"  Achats faits:    {buy_count}")
    print(f"  Dernier achat:   {last_buy}")

    # 5. Derniers trades (si fichier existe)
    if TRADES_FILE.exists():
        try:
            import pandas as pd
            df = pd.read_csv(TRADES_FILE)
            if len(df) > 0:
                print(f"\n  📋 DERNIERS TRADES ({min(5, len(df))}/{len(df)})")
                print(f"  ────────────────────────────────")
                last_trades = df.tail(5)
                for _, row in last_trades.iterrows():
                    ts = row["timestamp"][:16].replace("T", " ")
                    qty = row["quantity"]
                    cost = row["cost_usdt"]
                    pnl = row.get("pnl_pct", 0)
                    print(f"  {ts} | {qty:.8f} {SYMBOL.split('/')[0]} | {cost:.2f} $ | P&L: {pnl:+.2f}%")
        except Exception as e:
            print(f"\n  ⚠️ Erreur lecture trades.csv: {e}")

    print(f"\n═══════════════════════════════════")


if __name__ == "__main__":
    main()