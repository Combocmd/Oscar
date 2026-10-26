#!/usr/bin/env python3
"""
Oscar Backtest — VectorBT DCA Simulation
Teste la stratégie DCA hebdomadaire sur l'historique BTC/ETH (3-5 ans).
"""

import sys
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

try:
    import vectorbt as vbt
    import pandas as pd
    import numpy as np
    from datetime import datetime, timezone
except ImportError as e:
    print(f"❌ Dépendances manquantes: {e}")
    print("Installe avec: pip install vectorbt pandas numpy")
    sys.exit(1)

# ─── Configuration ───
SYMBOLS = ["BTC-USD", "ETH-USD"]  # Yahoo Finance format
START_DATE = "2021-01-01"          # 3+ ans d'historique
END_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
WEEKLY_USD = 10.0                  # Montant hebdo par asset
FEE = 0.001                        # 0.1%
SLIPPAGE = 0.0005                  # 0.05%
TOTAL_COST = FEE + SLIPPAGE        # 0.15%

# Jour d'achat: 0=Lundi (comme le bot)
BUY_WEEKDAY = 0  # Lundi


def fetch_data(symbols, start, end):
    """Télécharge données OHLCV depuis Yahoo Finance (gratuit)."""
    print(f"📥 Téléchargement {symbols} depuis {start} à {end}...")
    data = vbt.YFData.download(
        symbols,
        start=start,
        end=end,
        interval="1d",
        missing_data="drop"
    ).get("Close")
    print(f"✅ Données reçues: {data.shape[0]} jours x {data.shape[1]} assets")
    return data


def generate_dca_signals(close: pd.Series, weekday: int = 0) -> pd.Series:
    """
    Génère des signaux d'achat chaque semaine au jour donné.
    Returns: Series booléenne (True = jour d'achat)
    """
    # Resample to weekly, get first day of each week matching weekday
    # VectorBT utilise l'index datetime
    signals = pd.Series(False, index=close.index)
    # Marquer les lundis (weekday=0)
    signals[close.index.weekday == weekday] = True
    return signals


def run_dca_backtest(close: pd.Series, weekly_usd: float, symbol: str) -> dict:
    """Lance le backtest DCA pour un asset."""
    print(f"\n🔄 Backtest DCA {symbol}...")

    # Signaux d'achat hebdomadaires
    entries = generate_dca_signals(close, BUY_WEEKDAY)

    # Portfolio simulation avec VectorBT
    # On utilise from_signals avec taille de position fixe en USD
    # Note: VectorBT attend des tailles en unités d'asset, pas en USD
    # On calcule la quantité = weekly_usd / prix_du_jour

    # Méthode: simuler manuellement pour contrôle total sur frais/slippage
    cash = 0.0
    asset = 0.0
    total_invested = 0.0
    total_fees = 0.0
    portfolio_values = []

    buy_dates = close.index[entries]
    print(f"   {len(buy_dates)} achats programmés sur la période")

    for buy_date in buy_dates:
        price = close.loc[buy_date]
        if pd.isna(price) or price <= 0:
            continue

        # Prix d'exécution avec frais + slippage
        exec_price = price * (1 + TOTAL_COST)
        qty = weekly_usd / exec_price
        fees = weekly_usd * FEE
        slip = weekly_usd * SLIPPAGE

        cash -= weekly_usd
        asset += qty
        total_invested += weekly_usd
        total_fees += fees + slip

        # Valeur portfolio à cette date
        port_val = cash + asset * price
        portfolio_values.append({
            "date": buy_date,
            "price": price,
            "exec_price": exec_price,
            "qty": qty,
            "cash": cash,
            "asset": asset,
            "invested": total_invested,
            "fees": total_fees,
            "portfolio_value": port_val,
        })

    if not portfolio_values:
        return {"error": "Aucun trade exécuté"}

    df = pd.DataFrame(portfolio_values)
    df.set_index("date", inplace=True)

    # Métriques finales
    final_value = df.iloc[-1]["portfolio_value"]
    final_asset = df.iloc[-1]["asset"]
    final_invested = df.iloc[-1]["invested"]
    final_fees = df.iloc[-1]["fees"]

    pnl = final_value - final_invested
    pnl_pct = (pnl / final_invested * 100) if final_invested > 0 else 0

    # CAGR
    days = (df.index[-1] - df.index[0]).days
    years = days / 365.25
    cagr = (final_value / final_invested) ** (1 / years) - 1 if years > 0 and final_invested > 0 else 0

    # Max Drawdown
    peak = df["portfolio_value"].expanding().max()
    drawdown = (df["portfolio_value"] - peak) / peak
    max_dd = drawdown.min() * 100

    # Sharpe (approx daily returns)
    daily_returns = df["portfolio_value"].pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0

    # Stats par trade
    df["trade_pnl_pct"] = (df["portfolio_value"] - df["invested"]) / df["invested"] * 100

    return {
        "symbol": symbol,
        "trades": len(df),
        "period": f"{df.index[0].date()} → {df.index[-1].date()}",
        "years": round(years, 2),
        "final_value": round(final_value, 2),
        "final_asset": round(final_asset, 8),
        "total_invested": round(final_invested, 2),
        "total_fees": round(final_fees, 2),
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_dd_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "avg_trade_pnl_pct": round(df["trade_pnl_pct"].mean(), 2),
        "dataframe": df,
    }


def print_results(results: dict) -> None:
    """Affiche les résultats formatés."""
    if "error" in results:
        print(f"   ❌ {results['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  RÉSULTATS BACKTEST — {results['symbol']}")
    print(f"{'='*60}")
    print(f"  Période:          {results['period']} ({results['years']} ans)")
    print(f"  Achats effectués: {results['trades']}")
    print(f"  ────────────────────────────────────────────────")
    print(f"  Capital investi:  {results['total_invested']:>12,.2f} $")
    print(f"  Frais totaux:     {results['total_fees']:>12,.2f} $")
    print(f"  Valeur finale:    {results['final_value']:>12,.2f} $")
    print(f"  Asset final:      {results['final_asset']:>12.8f}")
    print(f"  ────────────────────────────────────────────────")
    print(f"  P&L net:          {results['pnl_usd']:>+12,.2f} $")
    print(f"  P&L %:            {results['pnl_pct']:>+12.2f} %")
    print(f"  CAGR:             {results['cagr_pct']:>+12.2f} %/an")
    print(f"  Max Drawdown:     {results['max_dd_pct']:>+12.2f} %")
    print(f"  Sharpe Ratio:     {results['sharpe']:>12.2f}")
    print(f"  P&L moyen/trade:  {results['avg_trade_pnl_pct']:>+12.2f} %")
    print(f"{'='*60}")


def save_equity_curves(all_results: dict, output_dir: Path) -> None:
    """Sauvegarde les courbes equity pour graphique."""
    output_dir.mkdir(exist_ok=True)
    for symbol, res in all_results.items():
        if "dataframe" in res:
            df = res["dataframe"][["portfolio_value", "invested"]].copy()
            df.columns = ["portfolio_value", "total_invested"]
            df.to_csv(output_dir / f"equity_{symbol.replace('-', '_')}.csv")
    print(f"\n💾 Courbes equity sauvées dans {output_dir}/")


def main():
    print("═══════════════════════════════════════")
    print("  OSCAR BACKTEST — DCA Historical")
    print("═══════════════════════════════════════")

    # 1. Fetch data
    close = fetch_data(SYMBOLS, START_DATE, END_DATE)

    # 2. Run backtest per symbol
    all_results = {}
    for symbol in SYMBOLS:
        if symbol in close.columns:
            res = run_dca_backtest(close[symbol].dropna(), WEEKLY_USD, symbol)
            all_results[symbol] = res
            print_results(res)
        else:
            print(f"⚠️ {symbol} non trouvé dans les données")

    # 3. Portfolio combiné (si multi-assets)
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print(f"  PORTEFEUILLE COMBINÉ (équi-pondéré hebdo)")
        print(f"{'='*60}")
        # Combine equity curves
        dfs = [res["dataframe"]["portfolio_value"] for res in all_results.values() if "dataframe" in res]
        if dfs:
            combined = pd.concat(dfs, axis=1).sum(axis=1)
            total_invested = sum(res["total_invested"] for res in all_results.values() if "total_invested" in res)
            final_val = combined.iloc[-1]
            pnl = final_val - total_invested
            pnl_pct = (pnl / total_invested * 100) if total_invested > 0 else 0
            print(f"  Investi total:    {total_invested:>12,.2f} $")
            print(f"  Valeur finale:    {final_val:>12,.2f} $")
            print(f"  P&L net:          {pnl:>+12,.2f} $ ({pnl_pct:+.2f}%)")

    # 4. Save equity curves
    save_equity_curves(all_results, Path(__file__).parent / "backtest_results")

    print("\n✅ Backtest terminé.")
    print("💡 Si P&L > 0 et Max DD acceptable → Stratégie validée pour paper trading.")


if __name__ == "__main__":
    main()