#!/usr/bin/env python3
"""
Oscar - DCA Bot for Crypto Spot Trading
Stratégie : Dollar Cost Averaging hebdomadaire (BTC/USDT + option ETH)
Mode : Paper trading (DRY_RUN=True) par défaut, passage réel possible
"""

import os
import sys
import time
import json
import logging
import signal
import threading
import csv
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import ccxt
import pandas as pd
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ─── Configuration des chemins ───
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
TRADES_FILE = BASE_DIR / "trades.csv"
LOG_FILE = BASE_DIR / "oscar.log"

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("oscar")

# ─── Constantes ───
FEE_RATE = 0.001      # 0.1% frais Binance spot
SLIPPAGE_RATE = 0.0005  # 0.05% slippage estimé
TOTAL_COST_RATE = FEE_RATE + SLIPPAGE_RATE  # 0.15% total
RETRY_MAX = 3
RETRY_DELAY = 5  # secondes


class PaperExchange:
    """Simule un exchange pour le paper trading avec frais et slippage réalistes."""

    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange

    def fetch_price(self, symbol: str) -> Optional[float]:
        """Récupère le prix spot réel depuis l'exchange."""
        for attempt in range(RETRY_MAX):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                price = ticker.get("last") or ticker.get("close")
                if price and price > 0:
                    return float(price)
                logger.warning(f"Prix invalide reçu: {price}, tentative {attempt+1}/{RETRY_MAX}")
            except ccxt.NetworkError as e:
                logger.warning(f"Erreur réseau ({attempt+1}/{RETRY_MAX}): {e}")
            except ccxt.ExchangeError as e:
                logger.error(f"Erreur exchange: {e}")
                break
            except Exception as e:
                logger.error(f"Erreur inattendue fetch_price: {e}")
            if attempt < RETRY_MAX - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        return None

    def execute_buy(self, symbol: str, usd_amount: float, price: float) -> float:
        """
        Simule un achat MARKET.
        Returns: quantité d'asset reçue (après frais + slippage)
        """
        execution_price = price * (1 + TOTAL_COST_RATE)
        quantity = usd_amount / execution_price
        return quantity


class StateManager:
    """Gère la persistance de l'état (balance, positions, historique)."""

    def __init__(self, state_file: Path, starting_balance: float):
        self.state_file = state_file
        self.starting_balance = starting_balance
        self.state = self.load()

    def load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info(f"État chargé: balance={state.get('balance_usdt', 0):.2f} USDT, "
                           f"asset={state.get('total_asset', 0):.8f}")
                defaults = self.default_state()
                for key, value in defaults.items():
                    state.setdefault(key, value)
                return state
            except Exception as e:
                logger.error(f"Erreur lecture state.json: {e}. Nouveau state créé.")
        return self.default_state()

    def default_state(self) -> Dict[str, Any]:
        return {
            "balance_usdt": self.starting_balance,
            "total_asset": 0.0,
            "total_invested": 0.0,
            "last_buy_date": None,
            "total_fees_paid": 0.0,
            "buy_count": 0,
        }

    def save(self) -> None:
        try:
            # Atomic write: write to temp then rename
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"Erreur sauvegarde state: {e}")

    def update_after_buy(self, usd_spent: float, quantity: float, fees: float, price: float) -> None:
        self.state["balance_usdt"] -= usd_spent
        self.state["total_asset"] += quantity
        self.state["total_invested"] += usd_spent
        self.state["total_fees_paid"] += fees
        self.state["last_buy_date"] = datetime.now(timezone.utc).isoformat()
        self.state["buy_count"] += 1
        self.save()

    def get_portfolio_value(self, current_price: float) -> Dict[str, float]:
        """Calcule la valeur actuelle du portefeuille."""
        asset_value = self.state["total_asset"] * current_price
        total_value = self.state["balance_usdt"] + asset_value
        pnl = total_value - self.starting_balance
        pnl_pct = (pnl / self.starting_balance * 100) if self.starting_balance > 0 else 0
        return {
            "cash": self.state["balance_usdt"],
            "asset_value": asset_value,
            "total_value": total_value,
            "pnl_usd": pnl,
            "pnl_pct": pnl_pct,
            "total_invested": self.state["total_invested"],
            "total_fees": self.state["total_fees_paid"],
        }


class TradeLogger:
    """Enregistre chaque trade dans un CSV avec P&L temps réel."""

    def __init__(self, trades_file: Path):
        self.trades_file = trades_file
        self.headers = [
            "timestamp", "pair", "price", "quantity", "cost_usdt",
            "fees_usdt", "slippage_usdt", "balance_usdt", "total_asset",
            "total_invested", "portfolio_value", "pnl_usd", "pnl_pct"
        ]

    def log(self, pair: str, price: float, quantity: float, cost_usdt: float,
            fees: float, slippage: float, state: StateManager, current_price: float) -> None:
        portfolio = state.get_portfolio_value(current_price)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "price": round(price, 2),
            "quantity": round(quantity, 8),
            "cost_usdt": round(cost_usdt, 2),
            "fees_usdt": round(fees, 4),
            "slippage_usdt": round(slippage, 4),
            "balance_usdt": round(state.state["balance_usdt"], 2),
            "total_asset": round(state.state["total_asset"], 8),
            "total_invested": round(state.state["total_invested"], 2),
            "portfolio_value": round(portfolio["total_value"], 2),
            "pnl_usd": round(portfolio["pnl_usd"], 2),
            "pnl_pct": round(portfolio["pnl_pct"], 2),
        }

        # csv.writer avec newline="" évite les lignes collées sur Windows.
        write_header = not self.trades_file.exists() or self.trades_file.stat().st_size == 0
        with open(self.trades_file, "a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.headers)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        logger.info(f"Trade loggé: {quantity:.8f} {pair.split('/')[0]} @ {price:.2f} | P&L: {portfolio['pnl_pct']:+.2f}%")


class Notifier:
    """Notifications Telegram (optionnel)."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled:
            return False
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            requests.post(url, json={"chat_id": self.chat_id, "text": message}, timeout=10)
            return True
        except Exception as e:
            logger.warning(f"Échec envoi Telegram: {e}")
            return False

    def notify_buy(self, pair: str, quantity: float, price: float, portfolio: Dict) -> None:
        msg = (
            f"🤖 <b>Oscar - Achat exécuté</b>\n"
            f"📊 {pair}: <code>{quantity:.8f}</code> @ <code>{price:,.2f} $</code>\n"
            f"💰 Portefeuille: <code>{portfolio['total_value']:,.2f} $</code> "
            f"({portfolio['pnl_pct']:+.2f}%)\n"
            f"📈 Investi total: <code>{portfolio['total_invested']:,.2f} $</code>"
        )
        self.send(msg)

    def notify_error(self, error: str) -> None:
        msg = f"🚨 <b>Oscar - Erreur</b>\n<code>{error}</code>"
        self.send(msg)

    def notify_startup(self, mode: str, pair: str, weekly: float) -> None:
        msg = (
            f"🤖 <b>Oscar démarré</b>\n"
            f"Mode: <b>{mode}</b>\n"
            f"Paire: {pair} | Hebdo: {weekly} $"
        )
        self.send(msg)

    def notify_shutdown(self) -> None:
        self.send("🛑 <b>Oscar arrêté</b>")


class OscarBot:
    """Bot DCA principal - Oscar."""

    def __init__(self):
        load_dotenv()

        # Config depuis .env
        self.dry_run = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
        self.symbol = os.getenv("SYMBOL", "BTC/USDT")
        self.weekly_amount = float(os.getenv("WEEKLY_AMOUNT", "7.5"))
        self.starting_balance = float(os.getenv("STARTING_BALANCE", "30"))
        self.buy_day = int(os.getenv("BUY_DAY", "0"))  # 0=Lundi
        self.buy_hour = int(os.getenv("BUY_HOUR", "0"))
        self.buy_minute = int(os.getenv("BUY_MINUTE", "0"))

        if not self.dry_run:
            raise RuntimeError(
                "Mode réel désactivé par sécurité : Oscar ne place pas encore de vrais ordres. "
                "Laisse DRY_RUN=True."
            )
        if self.weekly_amount <= 0 or self.starting_balance <= 0:
            raise ValueError("WEEKLY_AMOUNT et STARTING_BALANCE doivent être positifs.")
        if self.weekly_amount > self.starting_balance:
            raise ValueError("WEEKLY_AMOUNT ne peut pas dépasser STARTING_BALANCE.")

        # Telegram (optionnel)
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        # Exchange (lecture prix seulement, même en mode réel pour l'instant)
        self.exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"}
        })
        self.paper_exchange = PaperExchange(self.exchange)

        # Composants
        self.state = StateManager(STATE_FILE, self.starting_balance)
        self.trade_logger = TradeLogger(TRADES_FILE)
        self.notifier = Notifier(self.telegram_token, self.telegram_chat_id)

        # Scheduler
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self._shutdown = threading.Event()

        mode_str = "SIMULATION (Paper)" if self.dry_run else "RÉEL ⚠️"
        logger.info(f"═══════════════════════════════════")
        logger.info(f"  OSCAR - DCA Bot v1.0")
        logger.info(f"  Mode: {mode_str}")
        logger.info(f"  Paire: {self.symbol} | Hebdo: {self.weekly_amount} USDT")
        logger.info(f"  Jour/Heure: {self.buy_day} (0=Lun) à {self.buy_hour:02d}:{self.buy_minute:02d} UTC")
        logger.info(f"  Capital initial: {self.starting_balance} USDT")
        logger.info(f"═══════════════════════════════════")

    def print_status(self) -> None:
        """Affiche un résumé rapide en console."""
        price = self.paper_exchange.fetch_price(self.symbol)
        if price:
            portfolio = self.state.get_portfolio_value(price)
            print(f"\n{'='*50}")
            print(f"  OSCAR - STATUS")
            print(f"{'='*50}")
            print(f"  Prix {self.symbol}: {price:,.2f} USDT")
            print(f"  Cash: {portfolio['cash']:,.2f} USDT")
            print(f"  {self.symbol.split('/')[0]}: {self.state.state['total_asset']:.8f} "
                  f"({portfolio['asset_value']:,.2f} USDT)")
            print(f"  Valeur totale: {portfolio['total_value']:,.2f} USDT")
            print(f"  Investi: {portfolio['total_invested']:,.2f} USDT")
            print(f"  Frais cumulés: {portfolio['total_fees']:,.2f} USDT")
            print(f"  P&L: {portfolio['pnl_usd']:+,.2f} USDT ({portfolio['pnl_pct']:+.2f}%)")
            print(f"  Achats effectués: {self.state.state['buy_count']}")
            print(f"  Dernier achat: {self.state.state['last_buy_date'] or 'Jamais'}")
            print(f"{'='*50}\n")

    def execute_buy(self) -> bool:
        """Exécute l'achat hebdomadaire. Returns True si succès."""
        # Protection idempotente : un lancement manuel et le cron GitHub
        # dans la même semaine ne peuvent pas créer deux achats.
        last_buy = self.state.state.get("last_buy_date")
        if last_buy:
            try:
                last_week = datetime.fromisoformat(last_buy).isocalendar()[:2]
                current_week = datetime.now(timezone.utc).isocalendar()[:2]
                if last_week == current_week:
                    logger.info("Achat ignoré : un achat existe déjà pour cette semaine.")
                    return True  # no-op idempotent, pas une erreur de workflow
            except ValueError:
                logger.warning("last_buy_date invalide; poursuite avec prudence.")

        logger.info(f"🛒 Tentative d'achat {self.symbol}...")

        # 1. Récupérer prix réel
        price = self.paper_exchange.fetch_price(self.symbol)
        if price is None:
            logger.error("Impossible de récupérer le prix. Achat annulé.")
            self.notifier.notify_error("Impossible de récupérer le prix BTC/USDT")
            return False

        # 2. Vérifier balance
        if self.state.state["balance_usdt"] < self.weekly_amount:
            logger.warning(f"Balance insuffisante: {self.state.state['balance_usdt']:.2f} < {self.weekly_amount}")
            self.notifier.notify_error(f"Balance USDT insuffisante ({self.state.state['balance_usdt']:.2f} $)")
            return False

        # 3. Calculer quantité (avec frais + slippage simulés)
        execution_price = price * (1 + TOTAL_COST_RATE)
        quantity = self.weekly_amount / execution_price
        fees = self.weekly_amount * FEE_RATE
        slippage = self.weekly_amount * SLIPPAGE_RATE

        # 4. Mettre à jour l'état
        self.state.update_after_buy(self.weekly_amount, quantity, fees + slippage, price)

        # 5. Logger le trade
        current_price = self.paper_exchange.fetch_price(self.symbol) or price
        self.trade_logger.log(self.symbol, execution_price, quantity, self.weekly_amount,
                              fees, slippage, self.state, current_price)

        # 6. Notification
        portfolio = self.state.get_portfolio_value(current_price)
        logger.info(f"✅ ACHAT RÉUSSI: {quantity:.8f} {self.symbol.split('/')[0]} "
                    f"@ {execution_price:,.2f} (prix marché: {price:,.2f})")
        logger.info(f"   Portfolio: {portfolio['total_value']:,.2f} USDT ({portfolio['pnl_pct']:+.2f}%)")
        self.notifier.notify_buy(self.symbol, quantity, execution_price, portfolio)

        return True

    def run_scheduler(self) -> None:
        """Lance le scheduler APScheduler."""
        trigger = CronTrigger(
            day_of_week=self.buy_day,
            hour=self.buy_hour,
            minute=self.buy_minute,
            timezone="UTC"
        )
        self.scheduler.add_job(self.execute_buy, trigger, id="weekly_buy", max_instances=1)
        self.scheduler.start()

        # Calculer prochain run
        next_run = self.scheduler.get_job("weekly_buy").next_run_time
        logger.info(f"⏰ Scheduler démarré. Prochain achat: {next_run.strftime('%Y-%m-%d %H:%M UTC') if next_run else 'N/A'}")

        # Notifier démarrage
        mode = "Paper" if self.dry_run else "LIVE"
        self.notifier.notify_startup(mode, self.symbol, self.weekly_amount)

        # Boucle principale avec gestion signaux
        logger.info("🔄 Bot en attente... (Ctrl+C pour arrêter)")
        try:
            while not self._shutdown.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Signal d'arrêt reçu...")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Arrêt propre."""
        logger.info("🛑 Arrêt en cours...")
        self.scheduler.shutdown(wait=False)
        self.notifier.notify_shutdown()
        self.print_status()
        logger.info("✅ Oscar arrêté proprement.")

    def handle_signal(self, signum, frame) -> None:
        """Gestionnaire signaux Unix/Windows."""
        logger.info(f"Signal {signum} reçu")
        self._shutdown.set()


def run_once() -> bool:
    """Mode one-shot : exécute un seul achat et quitte. Pour GitHub Actions / cron."""
    bot = OscarBot()
    logger.info("🎯 Mode ONE-SHOT (GitHub Actions / cron)")
    
    # Exécuter l'achat
    success = bot.execute_buy()
    
    # Afficher status final
    bot.print_status()
    
    if success:
        logger.info("✅ One-shot terminé avec succès")
    else:
        logger.error("❌ One-shot échoué")
    
    return success


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(description="Oscar - DCA Bot")
    parser.add_argument("--once", action="store_true", 
                        help="Mode one-shot : un seul achat puis exit (pour GitHub Actions / cron)")
    args = parser.parse_args()
    
    if args.once:
        success = run_once()
        sys.exit(0 if success else 1)
    
    # Mode normal (scheduler continu)
    bot = OscarBot()

    # Gestion signaux pour arrêt propre
    signal.signal(signal.SIGINT, bot.handle_signal)
    signal.signal(signal.SIGTERM, bot.handle_signal)
    if hasattr(signal, "SIGBREAK"):  # Windows
        signal.signal(signal.SIGBREAK, bot.handle_signal)

    # Premier achat immédiat si jamais acheté (premier lancement)
    if bot.state.state["last_buy_date"] is None:
        logger.info("🎯 Premier lancement détecté - Achat initial...")
        bot.execute_buy()

    # Afficher status initial
    bot.print_status()

    # Lancer le scheduler
    bot.run_scheduler()


if __name__ == "__main__":
    main()
