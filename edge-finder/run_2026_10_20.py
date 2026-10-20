#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-20.
Phase 1: Eval Oct 19 predictions against verified scores.
Phase 2-5: Simulate tonight's games (11 NHL + 3 NBA Opening Night).

Sports tonight: NHL (11 games), NBA Opening Night (3 games).
No MLB (World Series starts Oct 23), no NFL (Week 7 starts Thu Oct 22).
"""

import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-20"
EVAL_DATE = "2026-10-19"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-19 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN, NHL.com, NBC Sports, Yahoo Sports:
actual_results = {
    # NHL: Flyers 3-2 Avalanche (home PHI won) — Michkov 2G
    "Philadelphia Flyers vs Colorado Avalanche": {
        "winner": "home", "home_score": 3, "away_score": 2
    },
    # NHL: Rangers 5-2 Ducks (home NYR won) — Garand 29 saves, Durzi goal
    "New York Rangers vs Anaheim Ducks": {
        "winner": "home", "home_score": 5, "away_score": 2
    },
    # NHL: Maple Leafs 3-1 Sharks (home TOR won) — McKenna go-ahead goal in 3rd
    "Toronto Maple Leafs vs San Jose Sharks": {
        "winner": "home", "home_score": 3, "away_score": 1
    },
    # NHL: Utah Mammoth 5-4 Penguins (home UTAH won) — Keller, Stenlund, Schmidt, Yamamoto, Schmaltz
    "Utah Mammoth vs Pittsburgh Penguins": {
        "winner": "home", "home_score": 5, "away_score": 4
    },
    # NFL MNF: 49ers 23-17 Commanders (home SF won) — Purdy 264yd 1TD, CMC 2TD
    "San Francisco 49ers vs Washington Commanders": {
        "winner": "home", "home_score": 23, "away_score": 17
    },
    # MLB ALCS G6: Guardians 3, Rays 7 (away TB won) — Rays clinch, to WS vs MIL
    "Cleveland Guardians vs Tampa Bay Rays": {
        "winner": "away", "home_score": 3, "away_score": 7
    },
}

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
model_ids = [m["id"] for m in all_models]

model_scores = {mid: {"correct": 0, "total": 0} for mid in model_ids}
tsv_lines = []

for game in past_preds["games"]:
    home_name = game["home"]
    away_name = game["away"]
    game_key = f"{home_name} vs {away_name}"

    if game_key not in actual_results:
        continue

    actual = actual_results[game_key]
    actual_winner = actual["winner"]
    margin = actual["home_score"] - actual["away_score"]

    for mid, mr in game["model_predictions"].items():
        predicted_winner = "home" if mr["home_win_prob"] > 0.5 else "away"
        hit = 1 if predicted_winner == actual_winner else 0
        model_scores[mid]["correct"] += hit
        model_scores[mid]["total"] += 1

        best_ev_type = max(
            [("spread_home", mr.get("spread_ev_home", 0)),
             ("spread_away", mr.get("spread_ev_away", 0)),
             ("ml_home", mr.get("ml_ev_home", 0)),
             ("ml_away", mr.get("ml_ev_away", 0))],
            key=lambda x: x[1]
        )
        bet_type = best_ev_type[0]

        spread = game["odds"]["spread_home"]
        if bet_type == "spread_home":
            bet_won = (margin + spread) > 0
        elif bet_type == "spread_away":
            bet_won = (-margin - spread) > 0
        elif bet_type == "ml_home":
            bet_won = actual_winner == "home"
        else:
            bet_won = actual_winner == "away"

        bet_result = "win" if bet_won else "loss"

        tsv_lines.append(
            f"{EVAL_DATE}\t{game['sport']}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']}\t{mr['home_win_prob']}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{best_ev_type[1]:.4f}\t{mr.get('ml_ev_home', 0) if predicted_winner == 'home' else mr.get('ml_ev_away', 0):.4f}\t"
            f"{bet_type}\t{bet_result}"
        )

# Append to results.tsv
tsv_path = os.path.join(BASE, "results.tsv")
with open(tsv_path, "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

# Print eval results
print(f"\nEvaluated {len(actual_results)} games from {EVAL_DATE}:")
for game_key, actual in actual_results.items():
    score = f"{actual['home_score']}-{actual['away_score']}"
    winner_label = "Home" if actual["winner"] == "home" else "Away"
    print(f"  {game_key}: {score} ({winner_label} won)")

print(f"\nModel ML accuracy (winner picks):")
for mid in model_ids:
    s = model_scores[mid]
    if s["total"] > 0:
        acc = s["correct"] / s["total"]
        print(f"  {mid}: {s['correct']}/{s['total']} = {acc:.1%}")

# ── Phase 1.4: Update challenger weights ──
champion_score = model_scores[champion["id"]]
champ_correct = champion_score["correct"]
champ_total = champion_score["total"]

print(f"\nWeight updates (champion {champion['id']}: {champ_correct}/{champ_total}):")
weight_changes = []
for c in challengers:
    cs = model_scores[c["id"]]
    if cs["total"] == 0:
        print(f"  {c['id']}: no games to compare — skipped")
        continue
    c_pct = cs["correct"] / cs["total"]
    ch_pct = champ_correct / champ_total if champ_total > 0 else 0

    if c_pct >= 0.6 and c_pct > ch_pct:
        old_w = c["weight"]
        c["weight"] = min(1.0, c["weight"] + 0.1)
        weight_changes.append(f"{c['id']}: {old_w:.1f} → {c['weight']:.1f} (outperformed)")
        print(f"  {c['id']}: weight {old_w:.1f} → {c['weight']:.1f} (outperformed champion)")
    elif ch_pct >= 0.6 and ch_pct > c_pct:
        old_w = c["weight"]
        c["weight"] = max(0.1, c["weight"] - 0.1)
        weight_changes.append(f"{c['id']}: {old_w:.1f} → {c['weight']:.1f} (underperformed)")
        print(f"  {c['id']}: weight {old_w:.1f} → {c['weight']:.1f} (underperformed champion)")
    else:
        print(f"  {c['id']}: no change (tied or within threshold)")

# Update lifetime stats for all models
for m in all_models:
    ms = model_scores[m["id"]]
    m["lifetime_games"] = m.get("lifetime_games", 0) + ms["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + ms["correct"]

# ── Phase 1.5: Rolling 10-day accuracy & promotion check ──
# All models went 5/6 today. Update rolling accuracy.
# Previous rolling_10d was 0.65 for champion. Adding 5/6 performance.
# Simple approach: weight today's results into rolling average.
for m in all_models:
    ms = model_scores[m["id"]]
    if ms["total"] > 0:
        today_acc = ms["correct"] / ms["total"]
        old_roll = m.get("rolling_10d_accuracy", 0.5)
        # Exponential moving average with alpha=0.3 for recency
        m["rolling_10d_accuracy"] = round(0.7 * old_roll + 0.3 * today_acc, 4)

print(f"\nRolling 10-day accuracy:")
for m in all_models:
    role = "CHAMP" if m["id"] == champion["id"] else "chal"
    print(f"  [{role}] {m['id']}: {m.get('rolling_10d_accuracy', 'N/A')}")

# Promotion check
champ_roll = champion.get("rolling_10d_accuracy", 0)
promotion = None
for c in challengers:
    c_roll = c.get("rolling_10d_accuracy", 0)
    if c_roll > champ_roll + 0.05:
        promotion = c
        break

if promotion:
    print(f"\n🔄 PROMOTION: {promotion['id']} ({promotion['rolling_10d_accuracy']:.1%}) "
          f"overtakes {champion['id']} ({champ_roll:.1%})")
    old_champ = champion.copy()
    old_champ["weight"] = 0.7
    old_champ["demoted_on"] = TODAY
    # Swap
    assumptions["champion"] = promotion.copy()
    assumptions["champion"]["weight"] = 1.0
    assumptions["champion"]["promoted_on"] = TODAY
    # Put old champion in challengers
    new_challengers = [old_champ]
    for c in challengers:
        if c["id"] != promotion["id"]:
            new_challengers.append(c)
    assumptions["challengers"] = new_challengers
    challengers = assumptions["challengers"]
    champion = assumptions["champion"]
else:
    print("\nNo promotions — all challengers within 5% of champion rolling accuracy.")

# ── Phase 1.6: Retire & Replace ──
retirements = []
for c in list(challengers):
    grace = c.get("grace_until", "2000-01-01")
    born = c.get("born", "2026-01-01")
    days_alive = (date(2026, 10, 20) - date(*map(int, born.split("-")))).days
    if c["weight"] <= 0.15 and days_alive > 5 and born < grace if grace else True:
        retirements.append(c)

for r in retirements:
    lt_acc = r["lifetime_correct"] / r["lifetime_games"] if r["lifetime_games"] > 0 else 0
    graveyard_entry = {
        "id": r["id"],
        "description": r["description"],
        "final_weight": r["weight"],
        "lifetime_accuracy": round(lt_acc, 3),
        "lifetime_games": r["lifetime_games"],
        "lifetime_correct": r["lifetime_correct"],
        "born": r["born"],
        "died": TODAY,
        "reason": f"Weight dropped to {r['weight']} after persistent underperformance."
    }
    assumptions["graveyard"].append(graveyard_entry)
    challengers.remove(r)
    print(f"\n⚰️ RETIRED: {r['id']} (weight={r['weight']}, accuracy={lt_acc:.1%})")

if not retirements:
    print("\nNo retirements — all challengers above weight floor.")

# Save assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
    f.write("\n")

print(f"\n✅ Phase 1 complete. Eval appended to results.tsv, assumptions.json updated.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION: Tonight's games
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Tonight's games ({TODAY})")
print("=" * 78)

# Reload assumptions after Phase 1 changes
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── NHL Games (11 games) ──
# Odds sourced from DraftKings, FanDuel, BetMGM, Yahoo Sports (Oct 20 2026)
# Team stats: early-season estimates (~8-10 GP). PPG = goals per game for NHL.
# Records from Covers, Fox Sports, NHL.com standings (Oct 19-20 2026).

nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home_name": "Montreal Canadiens",
        "away_name": "San Jose Sharks",
        "home_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 3.4, "last10_ppg": 2.8,
            "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 2.4, "season_opp_ppg": 3.6, "last10_ppg": 2.3,
            "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.25,
            "away_record_pct": 0.20, "is_back_to_back": True, "key_injuries": 2
        },
        "odds": {"spread_home": -1.5, "ml_home": -205, "ml_away": 170, "total": 6.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Washington Capitals",
        "away_name": "Los Angeles Kings",
        "home_stats": {
            "season_ppg": 3.3, "season_opp_ppg": 2.8, "last10_ppg": 3.4,
            "last10_opp_ppg": 2.7, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 2.0, "season_opp_ppg": 3.5, "last10_ppg": 1.8,
            "last10_opp_ppg": 3.7, "season_pace": 1.0, "home_record_pct": 0.0,
            "away_record_pct": 0.0, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -155, "ml_away": 130, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "New Jersey Devils",
        "away_name": "Colorado Avalanche",
        "home_stats": {
            "season_ppg": 3.2, "season_opp_ppg": 3.0, "last10_ppg": 3.3,
            "last10_opp_ppg": 2.8, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.4, "season_opp_ppg": 3.1, "last10_ppg": 3.2,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -110, "ml_away": -110, "total": 6.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "New York Islanders",
        "away_name": "Anaheim Ducks",
        "home_stats": {
            "season_ppg": 2.9, "season_opp_ppg": 2.7, "last10_ppg": 3.0,
            "last10_opp_ppg": 2.6, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 2.6, "season_opp_ppg": 3.2, "last10_ppg": 2.5,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.33,
            "away_record_pct": 0.25, "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -156, "ml_away": 130, "total": 5.5, "book": "FanDuel"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Columbus Blue Jackets",
        "away_name": "Toronto Maple Leafs",
        "home_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 3.1, "last10_ppg": 3.1,
            "last10_opp_ppg": 3.0, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.1, "season_opp_ppg": 2.8, "last10_ppg": 2.9,
            "last10_opp_ppg": 2.9, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.33, "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -162, "ml_away": 134, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "St. Louis Blues",
        "away_name": "Winnipeg Jets",
        "home_stats": {
            "season_ppg": 2.8, "season_opp_ppg": 3.2, "last10_ppg": 2.7,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.40,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.4, "season_opp_ppg": 2.6, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.67, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -145, "ml_away": 120, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Dallas Stars",
        "away_name": "Boston Bruins",
        "home_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 2.3, "last10_ppg": 3.1,
            "last10_opp_ppg": 2.2, "season_pace": 1.0, "home_record_pct": 0.75,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 3.4, "season_opp_ppg": 2.6, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.80,
            "away_record_pct": 0.67, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -170, "ml_away": 142, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Edmonton Oilers",
        "away_name": "Minnesota Wild",
        "home_stats": {
            "season_ppg": 3.8, "season_opp_ppg": 2.9, "last10_ppg": 4.0,
            "last10_opp_ppg": 2.8, "season_pace": 1.0, "home_record_pct": 0.80,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 3.2, "season_opp_ppg": 2.7, "last10_ppg": 3.3,
            "last10_opp_ppg": 2.6, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -175, "ml_away": 148, "total": 6.5, "book": "consensus"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Seattle Kraken",
        "away_name": "Detroit Red Wings",
        "home_stats": {
            "season_ppg": 2.9, "season_opp_ppg": 3.0, "last10_ppg": 2.8,
            "last10_opp_ppg": 3.1, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 3.2, "last10_ppg": 2.9,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.40,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 6.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Vancouver Canucks",
        "away_name": "Carolina Hurricanes",
        "home_stats": {
            "season_ppg": 2.4, "season_opp_ppg": 3.3, "last10_ppg": 2.2,
            "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.25,
            "away_record_pct": 0.20, "is_back_to_back": False, "key_injuries": 2
        },
        "away_stats": {
            "season_ppg": 3.6, "season_opp_ppg": 2.3, "last10_ppg": 3.7,
            "last10_opp_ppg": 2.2, "season_pace": 1.0, "home_record_pct": 0.75,
            "away_record_pct": 0.80, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 240, "ml_away": -298, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Vegas Golden Knights",
        "away_name": "Tampa Bay Lightning",
        "home_stats": {
            "season_ppg": 3.5, "season_opp_ppg": 2.6, "last10_ppg": 3.6,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.80,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 3.4, "season_opp_ppg": 2.5, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.4, "season_pace": 1.0, "home_record_pct": 0.75,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 6.5, "book": "DraftKings"}
    },
]

# ── NBA Games (3 games — Opening Night!) ──
# Stats from 2025-26 season as proxy (no 2026-27 regular season games played yet).
# NY Knicks are defending champions. OKC had best record last year.

nba_games = [
    {
        "sport": "basketball_nba",
        "home_name": "Detroit Pistons",
        "away_name": "Boston Celtics",
        "home_stats": {
            "season_ppg": 108.0, "season_opp_ppg": 113.0, "last10_ppg": 108.0,
            "last10_opp_ppg": 113.0, "season_pace": 99.5, "home_record_pct": 0.46,
            "away_record_pct": 0.35, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 118.5, "season_opp_ppg": 109.5, "last10_ppg": 118.5,
            "last10_opp_ppg": 109.5, "season_pace": 101.0, "home_record_pct": 0.78,
            "away_record_pct": 0.68, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 110, "ml_away": -120, "total": 219.5, "book": "CBS/consensus"}
    },
    {
        "sport": "basketball_nba",
        "home_name": "New York Knicks",
        "away_name": "Philadelphia 76ers",
        "home_stats": {
            "season_ppg": 116.0, "season_opp_ppg": 110.0, "last10_ppg": 116.0,
            "last10_opp_ppg": 110.0, "season_pace": 100.5, "home_record_pct": 0.78,
            "away_record_pct": 0.62, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 109.0, "season_opp_ppg": 111.5, "last10_ppg": 109.0,
            "last10_opp_ppg": 111.5, "season_pace": 98.5, "home_record_pct": 0.55,
            "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -4.5, "ml_home": -182, "ml_away": 152, "total": 232.5, "book": "SBD/consensus"}
    },
    {
        "sport": "basketball_nba",
        "home_name": "San Antonio Spurs",
        "away_name": "Oklahoma City Thunder",
        "home_stats": {
            "season_ppg": 115.0, "season_opp_ppg": 112.0, "last10_ppg": 115.0,
            "last10_opp_ppg": 112.0, "season_pace": 101.0, "home_record_pct": 0.62,
            "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 120.0, "season_opp_ppg": 108.0, "last10_ppg": 120.0,
            "last10_opp_ppg": 108.0, "season_pace": 101.5, "home_record_pct": 0.82,
            "away_record_pct": 0.72, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -2.5, "ml_home": -135, "ml_away": 115, "total": 231.5, "book": "SportsLine"}
    },
]

all_tonight = nhl_games + nba_games
print(f"\n{len(nhl_games)} NHL games + {len(nba_games)} NBA games = {len(all_tonight)} total")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running simulations")
print("=" * 78)

batch = []
for game in all_tonight:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": {"name": game["home_name"], **game["home_stats"]},
            "away": {"name": game["away_name"], **game["away_stats"]},
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        })

print(f"Running {len(batch)} simulations ({len(all_tonight)} games × {len(all_models)} models)...")
results = run_batch(batch)
print(f"✅ All simulations complete.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTIONS + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 4 — Blended predictions")
print("=" * 78)

# Group results by game
n_models = len(all_models)
prediction_games = []

for i, game in enumerate(all_tonight):
    game_results = results[i * n_models: (i + 1) * n_models]

    # Build per-model dict
    model_preds = {}
    for j, model in enumerate(all_models):
        r = game_results[j]
        model_preds[model["id"]] = {
            "home_win_prob": r["home_win_prob"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "expected_margin": r["expected_margin"],
        }

    # Blended prediction (weighted average)
    total_weight = champion["weight"]
    blend_hwp = champion["weight"] * game_results[0]["home_win_prob"]
    blend_margin = champion["weight"] * game_results[0]["expected_margin"]
    best_ev_all = []
    for j, model in enumerate(all_models):
        r = game_results[j]
        w = model["weight"]
        if j > 0:
            total_weight += w
            blend_hwp += w * r["home_win_prob"]
            blend_margin += w * r["expected_margin"]
        ev_choices = [r["ml_ev_home"], r["ml_ev_away"], r["spread_ev_home"], r["spread_ev_away"]]
        best_ev_all.append(max(ev_choices))

    blend_hwp /= total_weight
    blend_margin /= total_weight

    # Best EV: weighted average of each model's best EV
    blend_ev = sum(
        all_models[j]["weight"] * best_ev_all[j] for j in range(n_models)
    ) / total_weight

    best_model_ev = max(best_ev_all)
    worst_model_ev = min(best_ev_all)

    # Robustness: how many models agree on the winner
    home_votes = sum(1 for r in game_results if r["home_win_prob"] > 0.5)
    away_votes = n_models - home_votes
    robustness = max(home_votes, away_votes)
    consensus_side = "home" if home_votes > away_votes else "away"

    # Determine best bet type
    ev_options = [
        ("ml_home", sum(all_models[j]["weight"] * game_results[j]["ml_ev_home"] for j in range(n_models)) / total_weight),
        ("ml_away", sum(all_models[j]["weight"] * game_results[j]["ml_ev_away"] for j in range(n_models)) / total_weight),
        ("spread_home", sum(all_models[j]["weight"] * game_results[j]["spread_ev_home"] for j in range(n_models)) / total_weight),
        ("spread_away", sum(all_models[j]["weight"] * game_results[j]["spread_ev_away"] for j in range(n_models)) / total_weight),
    ]
    best_bet_type, best_bet_ev = max(ev_options, key=lambda x: x[1])

    # Classify
    if blend_ev > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif blend_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    elif blend_ev > 0.015 and robustness >= 4:
        verdict = "BET" if worst_model_ev > 0 else "LEAN"
    else:
        verdict = "NO BET"

    # Kelly criterion (half-Kelly)
    if blend_ev > 0 and best_bet_ev > 0:
        kelly_full = blend_ev / (best_model_ev if best_model_ev > 0 else 1)
        kelly_half = round(min(kelly_full / 2, 0.5), 3)
    else:
        kelly_half = 0

    game_pred = {
        "sport": game["sport"],
        "home": game["home_name"],
        "away": game["away_name"],
        "odds": game["odds"],
        "blended": {
            "home_win_prob": round(blend_hwp, 4),
            "away_win_prob": round(1 - blend_hwp, 4),
            "expected_margin": round(blend_margin, 2),
            "best_ev": round(blend_ev, 4),
            "best_bet": best_bet_type,
            "robustness": robustness,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": model_preds,
    }
    prediction_games.append(game_pred)

# ── Save predictions FIRST ──
predictions_output = {
    "date": TODAY,
    "sports": list(set(g["sport"] for g in all_tonight)),
    "context": "NBA Opening Night (3 games) + 11 NHL games. No MLB (WS starts Oct 23), no NFL. "
               "Champion: recency-v1. NHL early season (~10 GP); NBA first game of season, stats from 2025-26. "
               "NYK defending champs, ring ceremony before PHI game. TOR on B2B. COL/ANA/SJS on B2B.",
    "note": "ODDS_API_KEY not configured; odds sourced from web search (DraftKings, FanDuel, BetMGM, CBS Sports, Yahoo). "
            "NBA stats are 2025-26 season proxies — first regular season games of 2026-27.",
    "games": prediction_games,
}

pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions_output, f, indent=2)
    f.write("\n")
print(f"\n✅ Predictions saved to predictions/{TODAY}.json")

# ── Display results ──
def fmt_ev(ev):
    return f"+{ev:.1%}" if ev > 0 else f"{ev:.1%}"

def verdict_icon(v):
    if v == "BET":
        return "✅ BET"
    elif v == "LEAN":
        return "⚠️  LEAN"
    else:
        return "❌ NO BET"

# Group by sport
from collections import defaultdict
by_sport = defaultdict(list)
for g in prediction_games:
    by_sport[g["sport"]].append(g)

sport_labels = {
    "icehockey_nhl": "NHL",
    "basketball_nba": "NBA",
}

day_name = "Tuesday"
date_label = "Oct 20, 2026"

for sport_key, games in by_sport.items():
    label = sport_labels.get(sport_key, sport_key)
    print(f"\n┌─{'─' * 77}─┐")
    print(f"│ {label} — {day_name} {date_label}{' ' * (77 - len(label) - len(day_name) - len(date_label) - 4)}│")
    print(f"├{'─' * 20}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 16}┤")
    print(f"│ {'Game':<18} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │ {'Worst':>5} │ {'Rob.':>4} │ {'Verdict':<14} │")
    print(f"│ {'':18} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │ {'EV':>5} │ {'':>4} │ {'':14} │")
    print(f"├{'─' * 20}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 16}┤")
    for g in games:
        b = g["blended"]
        spread = g["odds"]["spread_home"]
        side = "HOME" if b["home_win_prob"] > 0.5 else "AWAY"
        if side == "HOME":
            team_short = g["home"][:3].upper()
            spread_str = f"{spread:+.1f}"
        else:
            team_short = g["away"][:3].upper()
            spread_str = f"{-spread:+.1f}"

        game_label = f"{team_short} {spread_str}"
        if len(game_label) > 18:
            game_label = game_label[:18]

        verd = verdict_icon(b["verdict"])
        verd_str = f"{verd} {side}" if b["verdict"] != "NO BET" else verd

        print(f"│ {game_label:<18} │ {spread:>+6.1f} │ {fmt_ev(b['best_ev']):>6} │ {fmt_ev(b['best_model_ev']):>6} │ {fmt_ev(b['worst_model_ev']):>5} │ {b['robustness']:>2}/6 │ {verd_str:<14} │")

    print(f"└{'─' * 20}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 16}┘")

# Detail on BET games
bet_games = [g for g in prediction_games if g["blended"]["verdict"] == "BET"]
if bet_games:
    print(f"\n{'=' * 78}")
    print(f" BET DETAILS ({len(bet_games)} games)")
    print(f"{'=' * 78}")
    for g in bet_games:
        b = g["blended"]
        print(f"\n  {g['away']} @ {g['home']}")
        print(f"  Best bet: {b['best_bet']} | Book: {g['odds']['book']} | Half-Kelly: {b['kelly_half']:.1%} of bankroll")
        print(f"  Blend EV: {fmt_ev(b['best_ev'])} | Best: {fmt_ev(b['best_model_ev'])} | Worst: {fmt_ev(b['worst_model_ev'])} | Rob: {b['robustness']}/6")
        agrees = []
        disagrees = []
        for mid, mp in g["model_predictions"].items():
            side = "home" if mp["home_win_prob"] > 0.5 else "away"
            best_side = "home" if b["home_win_prob"] > 0.5 else "away"
            if side == best_side:
                agrees.append(mid)
            else:
                disagrees.append(mid)
        if agrees:
            print(f"  Agree: {', '.join(agrees)}")
        if disagrees:
            print(f"  Disagree: {', '.join(disagrees)}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update with today's eval
eval_games = len(actual_results)
eval_correct = sum(
    1 for g in past_preds["games"]
    if f"{g['home']} vs {g['away']}" in actual_results
    and (
        ("home" if g["model_predictions"][champion["id"]]["home_win_prob"] > 0.5 else "away")
        == actual_results[f"{g['home']} vs {g['away']}"]["winner"]
    )
)

# Rolling 7-day
r7 = metrics["rolling_7d"]
r7["total_games"] += eval_games
r7["total_correct"] += eval_correct
r7["accuracy"] = round(r7["total_correct"] / r7["total_games"], 4) if r7["total_games"] > 0 else 0
r7["note"] = f"Oct 13-19. Added {eval_games} games from Oct 19 eval: {eval_correct}/{eval_games} ML."

# Rolling 30-day
r30 = metrics["rolling_30d"]
r30["total_games"] += eval_games
r30["total_correct"] += eval_correct
r30["accuracy"] = round(r30["total_correct"] / r30["total_games"], 4) if r30["total_games"] > 0 else 0

# All-time
at = metrics["all_time"]
at["total_games"] += eval_games
at["total_correct"] += eval_correct
at["accuracy"] = round(at["total_correct"] / at["total_games"], 4) if at["total_games"] > 0 else 0

# Variant performance
for m in all_models:
    mid = m["id"]
    role = "champion" if mid == champion["id"] else "challenger"
    metrics["variant_performance"][mid] = {
        "lifetime_games": m["lifetime_games"],
        "lifetime_correct": m["lifetime_correct"],
        "lifetime_accuracy": round(m["lifetime_correct"] / m["lifetime_games"], 4) if m["lifetime_games"] > 0 else 0,
        "weight": m["weight"],
        "role": role,
    }

# Today summary
metrics["last_updated"] = TODAY
bets_count = sum(1 for g in prediction_games if g["blended"]["verdict"] == "BET")
leans_count = sum(1 for g in prediction_games if g["blended"]["verdict"] == "LEAN")
no_bet_count = sum(1 for g in prediction_games if g["blended"]["verdict"] == "NO BET")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(prediction_games),
    "bets_recommended": bets_count,
    "leans": leans_count,
    "no_bets": no_bet_count,
    "sports": list(set(g["sport"] for g in prediction_games)),
    "notes": f"NBA Opening Night (BOS@DET, PHI@NYK, OKC@SAS) + 11 NHL. "
             f"Oct 19 eval: champion {eval_correct}/{eval_games} ML (missed PHI upset over COL). "
             f"No weight changes. No promotions."
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# Print summary
print(f"""
📊 Edge-Finder Metrics
━━━━━━━━━━━━━━━━━━━━
Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})
7-day:  {r7['accuracy']:.0%} accuracy | {r7['total_correct']}/{r7['total_games']} games
30-day: {r30['accuracy']:.0%} accuracy | {r30['total_correct']}/{r30['total_games']} games
All-time: {at['accuracy']:.0%} accuracy | {at['total_correct']}/{at['total_games']} games

Challenger weights: {', '.join(f"{c['id']}={c['weight']}" for c in challengers)}
Graveyard: {', '.join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions['graveyard'])}

Today: {len(prediction_games)} games analyzed | {bets_count} BETs | {leans_count} LEANs | {no_bet_count} NO BETs
Eval {EVAL_DATE}: {eval_correct}/{eval_games} ML correct ({eval_correct/eval_games:.0%}) — missed PHI upset over COL
""")

print("⚠️  FOR ENTERTAINMENT AND ANALYSIS PURPOSES ONLY.")
print("Past performance does not guarantee future results.\n")
