# Oscar — DCA Bot Crypto Spot

> **Oscar** : Bot d'accumulation passive (Dollar Cost Averaging) pour Bitcoin/Ethereum.
> Simple, robuste, zéro promesse — juste de la discipline automatisée.

---

## 🎯 Philosophie

| Ce qu'il fait | Ce qu'il NE fait PAS |
|---|---|
| Achète **chaque semaine** au prix marché | Prédit le marché, timing, indicateurs |
| Lisse ton prix d'entrée (DCA) | Stop-loss, take-profit, levier |
| Simule frais + slippage réalistes | Grid, martingale, arbitrage |
| Loggue tout (CSV + logs) | Accès à tes fonds (mode paper) |
| Tourne 24/7 sur ton PC | Garantit des profits |

**Stratégie unique** : Achat MARKET hebdomadaire, montant fixe, horizon long terme.

---

## 📦 Installation (5 min)

### 1. Prérequis
- **Python 3.10+** installé (`python --version`)
- **Git** (optionnel)
- Compte **Binance** (pour prix temps réel, même en paper)

### 2. Clone & Setup
```bash
cd D:\projets\oscar

# Environnement virtuel (recommandé)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Dépendances
pip install -r requirements.txt
```

### 3. Configuration
```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
```

Édite `.env` avec tes valeurs :
```env
DRY_RUN=True              # Garde True pour paper trading !
WEEKLY_AMOUNT=7.5         # $ par semaine
STARTING_BALANCE=30       # Capital fictif de départ
SYMBOL=BTC/USDT           # ou ETH/USDT
BUY_DAY=0                 # 0=Lundi
BUY_HOUR=0                # 00h UTC
```

### 4. (Optionnel) Alertes Telegram
1. Parle à **@BotFather** → `/newbot` → récupère `TELEGRAM_BOT_TOKEN`
2. Parle à **@userinfobot** → récupère ton `TELEGRAM_CHAT_ID`
3. Ajoute dans `.env` :
```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=987654321
```

### 5. Lancement
```bash
python oscar.py
```

---

## 📁 Fichiers générés

| Fichier | Rôle |
|---|---|
| `state.json` | **Ne pas supprimer** — État persistant (balance, positions, compteurs) |
| `trades.csv` | Historique complet avec P&L temps réel |
| `oscar.log` | Logs détaillés (rotation manuelle si gros) |

---

## 📊 Comprendre tes résultats

### `trades.csv` — La colonne clé : `pnl_pct`

```csv
timestamp,pair,price,quantity,cost_usdt,fees_usdt,slippage_usdt,balance_usdt,total_asset,total_invested,portfolio_value,pnl_usd,pnl_pct
2026-01-15T00:00:00+00:00,BTC/USDT,43210.50,0.000173,7.5,0.0075,0.0038,22.5,0.000173,7.5,7.5,0.0,0.0
2026-01-22T00:00:00+00:00,BTC/USDT,41800.00,0.000179,7.5,0.0075,0.0038,15.0,0.000352,15.0,14.7,-0.3,-2.0
...
```

**`pnl_pct`** = `(valeur_actuelle_BTC / total_investi - 1) × 100`
- **Positif** → Tu gagnes (marché haussier)
- **Négatif** → Tu perds (marché baissier) — **normal en DCA**, tu accumules moins cher

### Console — Status rapide
```
==================================================
  OSCAR - STATUS
==================================================
  Prix BTC/USDT: 67,400.00 USDT
  Cash: 7.50 USDT
  BTC: 0.00123456 (83.22 USDT)
  Valeur totale: 90.72 USDT
  Investi: 82.50 USDT
  Frais cumulés: 0.12 USDT
  P&L: +8.22 USDT (+9.96%)
  Achats effectués: 11
  Dernier achat: 2026-03-18T00:00:00+00:00
==================================================
```

---

## 🧪 Paper Trading → Real Trading

### Phase 1 : Paper (6 mois recommandés)
- `DRY_RUN=True`
- Capital fictif (`STARTING_BALANCE`)
- Vrais prix Binance, vrais frais simulés
- Objectif : Valider que la stratégie tient la route

### Phase 2 : Passage réel (si paper concluant)
1. **Testnet d'abord** : Binance Testnet (assets fictifs, vraie API)
2. **Petit capital** : 50-100 $ max au début
3. **Clés API** : Binance → API Management → Spot trading ✅, Withdraw ❌
4. **Dans `.env`** :
```env
DRY_RUN=False
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=yyy
# STARTING_BALANCE ignoré en mode réel
```

> ⚠️ **En mode réel, le bot place de VRAIS ordres MARKET sur ton compte.**
> Commence petit, surveille les premiers achats.

---

## 🔧 Commandes utiles

### Status instantané (sans attendre le prochain achat)
```bash
python status.py
```

### Backtest historique (3 ans BTC/ETH)
```bash
python backtest.py
```
Génère : métriques (CAGR, Sharpe, Max Drawdown), courbe equity, stats par trade.

### Voir les logs en live
```bash
# PowerShell
Get-Content oscar.log -Wait -Tail 20

# Linux/Mac
tail -f oscar.log
```

### Arrêt propre
`Ctrl+C` → Oscar sauvegarde l'état, notifie Telegram, affiche le résumé final.

---

## 📈 Backtest — Ce qu'il te dit

| Métrique | Cible saine (DCA BTC 3 ans) |
|---|---|
| **CAGR** (rendement annualisé) | > 20% (marché haussier) |
| **Max Drawdown** | < 50% (tolérance risque) |
| **Sharpe Ratio** | > 1.0 |
| **Win Rate** | ~100% (DCA n'a pas de "trades perdants") |
| **Frais totaux / Capital** | < 2% |

Si backtest < 0 sur 3 ans → La DCA ne marche pas dans ce régime → Revoir hypothèses.

---

## ❓ FAQ

**Q: Mon PC doit rester allumé 24/7 ?**
R: Oui pour le scheduler. Alternative gratuite : **GitHub Actions** (cron gratuit, voir `github-action.yml` optionnel).

**Q: Que se passe-t-il si Binance est down ?**
R: Oscar retry 3× (5s, 10s, 15s). Si échec → log erreur + alerte Telegram + réessaie semaine suivante.

**Q: Puis-je changer `WEEKLY_AMOUNT` en cours de route ?**
R: Oui, modifie `.env` et redémarre. L'état (`state.json`) est préservé.

**Q: Comment ajouter ETH en plus de BTC ?**
R: Version multi-paires prévue v2. Pour l'instant : 2 dossiers `oscar-btc` + `oscar-eth` avec ports différents.

**Q: Fiscalité (France/UEMOA) ?**
R: En paper : rien. En réel : chaque achat = acquisition. Revente = plus-value. Consulte un expert-comptable.

---

## 🛠 Structure du code

```
oscar/
├── oscar.py          # Bot principal (~250 lignes)
├── backtest.py       # VectorBT backtest (optionnel)
├── status.py         # Affichage status instantané
├── requirements.txt  # Dépendances
├── .env.example      # Template config
├── .env              # Tes secrets (NE PAS COMMIT)
├── state.json        # État persistant (auto)
├── trades.csv        # Historique trades (auto)
├── oscar.log         # Logs (auto)
└── README.md         # Ce fichier
```

---

## ⚠️ Disclaimer

> **Ce logiciel est fourni "tel quel" à des fins éducatives.**
> Le trading de crypto-monnaies comporte un risque de perte en capital.
> Les performances passées ne préjugent pas des résultats futurs.
> L'auteur décline toute responsabilité en cas de perte financière.

---

## 📜 Licence

MIT — Libre d'utilisation, modification, distribution.

---

**Créé pour apprendre, accumuler, et dormir tranquille.** 🤖₿

*Oscar ne dort pas. Oscar n'hésite pas. Oscar accumule.*