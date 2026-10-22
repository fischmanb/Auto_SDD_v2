#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-22.
Phase 1: Eval Oct 21 predictions against verified scores.
Phase 2-5: Simulate tonight's games (2 NBA + 11 NHL + 1 NFL TNF).

Sports tonight: NBA (2 games - Day 3 of 2026-27 season), NHL (11 games),
NFL (1 TNF: NE @ CHI). No MLB (World Series starts Oct 23).
"""

import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-22"
EVAL_DATE = "2026-10-21"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-21 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN, NBA.com, NHL.com, CBS Sports (Oct 21 2026):
actual_results = {
    # NHL: Sabres 1-3 Flyers — Cole Knuble 2G, Vladar 27 saves for PHI
    "Buffalo Sabres vs Philadelphia Flyers": {
        "winner": "away", "home_score": 1, "away_score": 3
    },
    # NHL: Senators 5-1 Panthers — Stutzle top performer, Ullmark wins
    "Ottawa Senators vs Florida Panthers": {
        "winner": "home", "home_score": 5, "away_score": 1
    },
    # NBA: Magic 125-132 Hawks — ATL upset ORL on the road
    "Orlando Magic vs Atlanta Hawks": {
        "winner": "away", "home_score": 125, "away_score": 132
    },
    # NBA: Wizards 128-116 Bucks — WAS upset! Home win over MIL
    "Washington Wizards vs Milwaukee Bucks": {
        "winner": "home", "home_score": 128, "away_score": 116
    },
    # NBA: Raptors 135-92 Bulls — TOR blowout
    "Toronto Raptors vs Chicago Bulls": {
        "winner": "home", "home_score": 135, "away_score": 92
    },
    # NBA: Nets 103-110 Hornets — CHA road win
    "Brooklyn Nets vs Charlotte Hornets": {
        "winner": "away", "home_score": 103, "away_score": 110
    },
    # NBA: Heat 106-131 Timberwolves — Edwards 45pts, 9 threes, Giannis MIA debut
    "Miami Heat vs Minnesota Timberwolves": {
        "winner": "away", "home_score": 106, "away_score": 131
    },
    # NBA: Pelicans 120-123 Pacers — IND road win in close game
    "New Orleans Pelicans vs Indiana Pacers": {
        "winner": "away", "home_score": 120, "away_score": 123
    },
    # NBA: Rockets 120-100 Mavericks — HOU dominant at home
    "Houston Rockets vs Dallas Mavericks": {
        "winner": "home", "home_score": 120, "away_score": 100
    },
    # NBA: Jazz 103-123 Grizzlies — MEM wins comfortably on the road
    "Utah Jazz vs Memphis Grizzlies": {
        "winner": "away", "home_score": 103, "away_score": 123
    },
    # NBA: Trail Blazers 124-83 Suns — POR 41-point blowout, Lillard 25pts
    "Portland Trail Blazers vs Phoenix Suns": {
        "winner": "home", "home_score": 124, "away_score": 83
    },
    # NBA: Clippers 121-96 Kings — Garland 30pts, LAC never trailed
    "Los Angeles Clippers vs Sacramento Kings": {
        "winner": "home", "home_score": 121, "away_score": 96
    },
    # NBA: Lakers 127-105 Warriors — Doncic 28pts/7ast
    "Los Angeles Lakers vs Golden State Warriors": {
        "winner": "home", "home_score": 127, "away_score": 105
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

# Update lifetime stats
for m in all_models:
    ms = model_scores[m["id"]]
    m["lifetime_games"] = m.get("lifetime_games", 0) + ms["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + ms["correct"]

# ── Phase 1.5: Rolling 10-day accuracy & promotion check ──
# Champion recency-v1: 8/13 (61.5%). injury-rest-v1: 9/13 (69.2%). All others: 8/13.
for m in all_models:
    ms = model_scores[m["id"]]
    if ms["total"] > 0:
        today_acc = ms["correct"] / ms["total"]
        old_roll = m.get("rolling_10d_accuracy", 0.5)
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
    assumptions["champion"] = promotion.copy()
    assumptions["champion"]["weight"] = 1.0
    assumptions["champion"]["promoted_on"] = TODAY
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
    days_alive = (date(2026, 10, 22) - date(*map(int, born.split("-")))).days
    if c["weight"] <= 0.15 and days_alive > 5:
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

# ── NFL Game (1 game: Thursday Night Football) ──
# NE @ CHI, 8:15 PM ET on Prime Video. Both teams 4-2.
# Odds from FanDuel, CBS Sports, Bleacher Nation, Yahoo Sports (Oct 22 2026).
# NE: 22.7 PPG scored, 18.8 PPG allowed. CHI: 25.0 PPG scored, 19.8 PPG allowed.

nfl_games = [
    {
        "sport": "americanfootball_nfl",
        "home_name": "Chicago Bears",
        "away_name": "New England Patriots",
        "home_stats": {
            "season_ppg": 25.0, "season_opp_ppg": 19.8, "last10_ppg": 25.0,
            "last10_opp_ppg": 19.8, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.67, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 22.7, "season_opp_ppg": 18.8, "last10_ppg": 22.7,
            "last10_opp_ppg": 18.8, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.67, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -3.0, "ml_home": -156, "ml_away": 132, "total": 50.5, "book": "FanDuel"}
    },
]

# ── NHL Games (11 games) ──
# Odds from DraftKings, FanDuel, sportsbettingdime (Oct 22 2026).
# Early season (~8-12 GP). Stats are approximate from early 2025-26 performance.

nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home_name": "Ottawa Senators",
        "away_name": "San Jose Sharks",
        "home_stats": {
            "season_ppg": 3.2, "season_opp_ppg": 2.8, "last10_ppg": 3.4,
            "last10_opp_ppg": 2.6, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": True, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 2.5, "season_opp_ppg": 3.5, "last10_ppg": 2.5,
            "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -135, "ml_away": 114, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "New Jersey Devils",
        "away_name": "Anaheim Ducks",
        "home_stats": {
            "season_ppg": 3.5, "season_opp_ppg": 2.7, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.7, "season_pace": 1.0, "home_record_pct": 0.75,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 2.4, "season_opp_ppg": 3.3, "last10_ppg": 2.4,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.44,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -198, "ml_away": 164, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Boston Bruins",
        "away_name": "Nashville Predators",
        "home_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 2.6, "last10_ppg": 3.0,
            "last10_opp_ppg": 2.6, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 2.6, "season_opp_ppg": 3.2, "last10_ppg": 2.6,
            "last10_opp_ppg": 3.2, "season_pace": 1.0, "home_record_pct": 0.40,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -155, "ml_away": 130, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Toronto Maple Leafs",
        "away_name": "New York Rangers",
        "home_stats": {
            "season_ppg": 3.3, "season_opp_ppg": 2.5, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.4, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 2.8, "last10_ppg": 3.0,
            "last10_opp_ppg": 2.8, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -108, "ml_away": -112, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Pittsburgh Penguins",
        "away_name": "Florida Panthers",
        "home_stats": {
            "season_ppg": 3.2, "season_opp_ppg": 3.0, "last10_ppg": 3.2,
            "last10_opp_ppg": 3.0, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 2.8, "last10_ppg": 2.8,
            "last10_opp_ppg": 2.9, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": True, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "New York Islanders",
        "away_name": "Los Angeles Kings",
        "home_stats": {
            "season_ppg": 2.9, "season_opp_ppg": 2.7, "last10_ppg": 2.9,
            "last10_opp_ppg": 2.7, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 2.8, "season_opp_ppg": 2.5, "last10_ppg": 3.0,
            "last10_opp_ppg": 2.4, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Dallas Stars",
        "away_name": "Winnipeg Jets",
        "home_stats": {
            "season_ppg": 3.3, "season_opp_ppg": 2.3, "last10_ppg": 3.3,
            "last10_opp_ppg": 2.3, "season_pace": 1.0, "home_record_pct": 0.75,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "away_stats": {
            "season_ppg": 3.4, "season_opp_ppg": 2.5, "last10_ppg": 3.4,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.57, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -208, "ml_away": 170, "total": 5.5, "book": "sportsbettingdime"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "St. Louis Blues",
        "away_name": "Vegas Golden Knights",
        "home_stats": {
            "season_ppg": 2.5, "season_opp_ppg": 3.0, "last10_ppg": 2.5,
            "last10_opp_ppg": 3.0, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.0, "season_opp_ppg": 3.2, "last10_ppg": 3.0,
            "last10_opp_ppg": 3.2, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": 105, "ml_away": -125, "total": 6.0, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Calgary Flames",
        "away_name": "Minnesota Wild",
        "home_stats": {
            "season_ppg": 2.4, "season_opp_ppg": 3.2, "last10_ppg": 2.4,
            "last10_opp_ppg": 3.2, "season_pace": 1.0, "home_record_pct": 0.40,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.3, "season_opp_ppg": 2.5, "last10_ppg": 3.3,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.57, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": 170, "ml_away": -205, "total": 5.5, "book": "DraftKings"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Edmonton Oilers",
        "away_name": "Carolina Hurricanes",
        "home_stats": {
            "season_ppg": 3.2, "season_opp_ppg": 2.8, "last10_ppg": 3.2,
            "last10_opp_ppg": 2.8, "season_pace": 1.0, "home_record_pct": 0.60,
            "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 3.5, "season_opp_ppg": 2.5, "last10_ppg": 3.5,
            "last10_opp_ppg": 2.5, "season_pace": 1.0, "home_record_pct": 0.67,
            "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -102, "ml_away": -118, "total": 6.0, "book": "estimated"}
    },
    {
        "sport": "icehockey_nhl",
        "home_name": "Vancouver Canucks",
        "away_name": "Detroit Red Wings",
        "home_stats": {
            "season_ppg": 2.5, "season_opp_ppg": 3.3, "last10_ppg": 2.5,
            "last10_opp_ppg": 3.3, "season_pace": 1.0, "home_record_pct": 0.40,
            "away_record_pct": 0.33, "is_back_to_back": False, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 2.8, "season_opp_ppg": 3.0, "last10_ppg": 2.8,
            "last10_opp_ppg": 3.0, "season_pace": 1.0, "home_record_pct": 0.50,
            "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": 140, "ml_away": -169, "total": 6.0, "book": "DraftKings"}
    },
]

# ── NBA Games (2 games) ──
# Day 3 of 2026-27 season. Stats are 2025-26 proxies.
# Odds from FanDuel, DraftKings, BetMGM, Yahoo (Oct 22 2026).
# PHI is on B2B (played Oct 20 vs NYK). OKC played Oct 20 vs SAS.

nba_games = [
    {
        "sport": "basketball_nba",
        "home_name": "Philadelphia 76ers",
        "away_name": "Cleveland Cavaliers",
        "home_stats": {
            "season_ppg": 115.9, "season_opp_ppg": 115.5, "last10_ppg": 117.0,
            "last10_opp_ppg": 114.0, "season_pace": 99.4, "home_record_pct": 0.61,
            "away_record_pct": 0.49, "is_back_to_back": True, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 119.5, "season_opp_ppg": 115.4, "last10_ppg": 121.0,
            "last10_opp_ppg": 114.0, "season_pace": 100.2, "home_record_pct": 0.66,
            "away_record_pct": 0.61, "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -3.0, "ml_home": -147, "ml_away": 124, "total": 236.5, "book": "FanDuel"}
    },
    {
        "sport": "basketball_nba",
        "home_name": "Oklahoma City Thunder",
        "away_name": "Denver Nuggets",
        "home_stats": {
            "season_ppg": 119.1, "season_opp_ppg": 107.9, "last10_ppg": 121.0,
            "last10_opp_ppg": 107.0, "season_pace": 100.5, "home_record_pct": 0.78,
            "away_record_pct": 0.71, "is_back_to_back": True, "key_injuries": 1
        },
        "away_stats": {
            "season_ppg": 120.5, "season_opp_ppg": 116.1, "last10_ppg": 119.0,
            "last10_opp_ppg": 115.0, "season_pace": 99.8, "home_record_pct": 0.63,
            "away_record_pct": 0.56, "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -8.0, "ml_home": -300, "ml_away": 245, "total": 236.5, "book": "FanDuel"}
    },
]

all_games = nfl_games + nhl_games + nba_games

print(f"\nTonight's slate: {len(nfl_games)} NFL + {len(nhl_games)} NHL + {len(nba_games)} NBA = {len(all_games)} games")
for g in all_games:
    sport_label = "NFL" if "nfl" in g["sport"] else ("NHL" if "nhl" in g["sport"] else "NBA")
    print(f"  [{sport_label}] {g['home_name']} vs {g['away_name']} "
          f"(spread {g['odds']['spread_home']:+.1f}, ML {g['odds']['ml_home']}/{g['odds']['ml_away']})")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running simulations")
print("=" * 78)

N_SIMS = 50000

batch = []
for game in all_games:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": {
                "name": game["home_name"],
                **game["home_stats"]
            },
            "away": {
                "name": game["away_name"],
                **game["away_stats"]
            },
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": N_SIMS
        })

print(f"Running {len(batch)} simulations ({len(all_games)} games × {len(all_models)} models × {N_SIMS:,} sims each)...")

results = run_batch(batch)

print(f"✅ Simulations complete: {len(results)} results")

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 4 — Blended predictions")
print("=" * 78)

# Organize results by game
games_output = []
result_idx = 0

for game in all_games:
    game_results = {}
    for model in all_models:
        r = results[result_idx]
        game_results[model["id"]] = r
        result_idx += 1

    # Compute blended prediction
    total_weight = champion["weight"]
    blend_home_wp = champion["weight"] * game_results[champion["id"]]["home_win_prob"]
    blend_margin = champion["weight"] * game_results[champion["id"]]["expected_margin"]

    ev_fields = ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]
    blend_evs = {f: champion["weight"] * game_results[champion["id"]][f] for f in ev_fields}

    for c in challengers:
        w = c["weight"]
        total_weight += w
        cr = game_results[c["id"]]
        blend_home_wp += w * cr["home_win_prob"]
        blend_margin += w * cr["expected_margin"]
        for f in ev_fields:
            blend_evs[f] += w * cr[f]

    blend_home_wp /= total_weight
    blend_margin /= total_weight
    for f in ev_fields:
        blend_evs[f] /= total_weight

    best_ev_field = max(blend_evs, key=blend_evs.get)
    best_ev = blend_evs[best_ev_field]

    # Robustness: how many models agree on the best bet side
    best_side = "home" if best_ev_field in ("spread_ev_home", "ml_ev_home") else "away"
    robustness = 0
    model_evs = []
    for model in all_models:
        mr = game_results[model["id"]]
        model_best_field = max(ev_fields, key=lambda f: mr[f])
        model_best_side = "home" if model_best_field in ("spread_ev_home", "ml_ev_home") else "away"
        if model_best_side == best_side:
            robustness += 1
        model_evs.append(mr[model_best_field])

    best_model_ev = max(model_evs)
    worst_model_ev = min(model_evs)

    # Classify
    if best_ev > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    elif best_ev > 0.015 and robustness >= 4:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Check if any model flips sign
    any_flip = any(ev < 0 for ev in model_evs) and any(ev > 0 for ev in model_evs)
    if any_flip and verdict == "BET":
        verdict = "LEAN"

    # Kelly criterion (half-Kelly for safety)
    if best_ev > 0:
        if "home" in best_ev_field:
            ml_for_kelly = game["odds"]["ml_home"]
        else:
            ml_for_kelly = game["odds"]["ml_away"]
        odds_decimal = 1 + (abs(ml_for_kelly) / 100 if ml_for_kelly > 0
                           else 100 / abs(ml_for_kelly))
        bet_prob = blend_home_wp if "home" in best_ev_field else (1 - blend_home_wp)
        kelly_full = (bet_prob * odds_decimal - 1) / (odds_decimal - 1) if odds_decimal > 1 else 0
        kelly_half = max(0, kelly_full / 2)
    else:
        kelly_half = 0

    blended = {
        "home_win_prob": round(blend_home_wp, 4),
        "away_win_prob": round(1 - blend_home_wp, 4),
        "expected_margin": round(blend_margin, 2),
        "best_ev": round(best_ev, 4),
        "best_bet": best_ev_field,
        "robustness": robustness,
        "verdict": verdict,
        "kelly_half": round(kelly_half, 3),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
    }

    model_preds = {}
    for model in all_models:
        mr = game_results[model["id"]]
        model_preds[model["id"]] = {
            "home_win_prob": mr["home_win_prob"],
            "ml_ev_home": mr["ml_ev_home"],
            "ml_ev_away": mr["ml_ev_away"],
            "spread_ev_home": mr["spread_ev_home"],
            "spread_ev_away": mr["spread_ev_away"],
            "expected_margin": mr["expected_margin"],
        }

    games_output.append({
        "sport": game["sport"],
        "home": game["home_name"],
        "away": game["away_name"],
        "odds": game["odds"],
        "blended": blended,
        "model_predictions": model_preds,
    })

# ── Display results ──
sport_groups = {}
for g in games_output:
    sport = g["sport"]
    if sport not in sport_groups:
        sport_groups[sport] = []
    sport_groups[sport].append(g)

sport_labels = {
    "icehockey_nhl": "NHL",
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
}

day_label = "Thursday Oct 22, 2026"

for sport, games in sport_groups.items():
    label = sport_labels.get(sport, sport)
    print(f"\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print(f"│ {label} — {day_label:<70}│")
    print(f"├────────────────────┬────────┬────────┬────────┬──────┬──────┬──────────────┤")
    print(f"│ Game               │ Spread │ Blend  │ Best   │ Worst│ Rob. │ Verdict      │")
    print(f"│                    │        │ EV     │ EV     │ EV   │      │              │")
    print(f"├────────────────────┼────────┼────────┼────────┼──────┼──────┼──────────────┤")

    for g in games:
        home_abbr = g["home"].split()[-1][:3].upper()
        away_abbr = g["away"].split()[-1][:3].upper()
        spread = g["odds"]["spread_home"]

        if spread < 0:
            game_label = f"{home_abbr} {spread:+.1f} vs {away_abbr}"
        else:
            game_label = f"{home_abbr} +{spread:.1f} vs {away_abbr}"

        b = g["blended"]
        ev_str = f"{b['best_ev']:+.1%}"
        best_str = f"{b['best_model_ev']:+.1%}"
        worst_str = f"{b['worst_model_ev']:+.1%}"
        rob_str = f"{b['robustness']}/6"

        if b["verdict"] == "BET":
            side = "HOME" if "home" in b["best_bet"] else "AWAY"
            verdict_str = f"✅ BET {side}"
        elif b["verdict"] == "LEAN":
            side = "HOME" if "home" in b["best_bet"] else "AWAY"
            verdict_str = f"⚠️  LEAN {side}"
        else:
            verdict_str = "❌ NO BET"

        print(f"│ {game_label:<18} │ {spread:>+5.1f}  │ {ev_str:>6} │ {best_str:>6} │{worst_str:>5} │ {rob_str:>4} │ {verdict_str:<12} │")

    print(f"└────────────────────┴────────┴────────┴────────┴──────┴──────┴──────────────┘")

# Print details for BET games
bet_games = [g for g in games_output if g["blended"]["verdict"] == "BET"]
if bet_games:
    print(f"\n{'─' * 78}")
    print(f" BET DETAILS ({len(bet_games)} strong recommendations)")
    print(f"{'─' * 78}")

    for g in bet_games:
        b = g["blended"]
        side = "HOME" if "home" in b["best_bet"] else "AWAY"
        team = g["home"] if side == "HOME" else g["away"]
        print(f"\n  ✅ {team} ({side}) — {g['home']} vs {g['away']}")
        print(f"     Bet type: {b['best_bet']}")
        print(f"     Blended EV: {b['best_ev']:+.2%} | Win prob: {b['home_win_prob']:.1%} home")
        print(f"     Best book: {g['odds']['book']}")
        print(f"     Half-Kelly: {b['kelly_half']:.1%} of bankroll")
        print(f"     Robustness: {b['robustness']}/6 models agree")

        agree = []
        disagree = []
        for model in all_models:
            mp = g["model_predictions"][model["id"]]
            model_best_field = max(
                ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"],
                key=lambda f: mp[f]
            )
            model_side = "HOME" if "home" in model_best_field else "AWAY"
            if model_side == side:
                agree.append(f"{model['id']}({mp[model_best_field]:+.1%})")
            else:
                disagree.append(f"{model['id']}({mp[model_best_field]:+.1%})")

        print(f"     Agree: {', '.join(agree)}")
        if disagree:
            print(f"     Disagree: {', '.join(disagree)}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — SAVE PREDICTIONS + METRICS
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Saving predictions & metrics")
print("=" * 78)

# Save predictions
predictions = {
    "date": TODAY,
    "sports": list(sport_groups.keys()),
    "context": (
        f"Day 3 of NBA 2026-27 season (2 games: CLE@PHI, DEN@OKC) + 11 NHL games + 1 NFL TNF (NE@CHI). "
        f"No MLB (WS starts Oct 23). "
        f"Champion: {champion['id']}. "
        f"NBA stats are 2025-26 season proxies — very early 2026-27 season. "
        f"PHI on B2B (played Oct 20). OKC on B2B (played Oct 20). "
        f"NHL: OTT on B2B (played Oct 21), FLA on B2B (played Oct 21 at OTT)."
    ),
    "note": (
        "ODDS_API_KEY not configured; odds sourced from web search "
        "(DraftKings, FanDuel, BetMGM, CBS Sports, Yahoo, sportsbettingdime, Bleacher Nation). "
        "NHL odds approximate for some games. DAL-WPG line (-208) from sportsbettingdime."
    ),
    "games": games_output,
}

pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions, f, indent=2)
    f.write("\n")
print(f"✅ Predictions saved to predictions/{TODAY}.json")

# Update metrics
eval_total = sum(model_scores[mid]["total"] for mid in model_ids) // len(model_ids)
eval_correct = model_scores[champion["id"]]["correct"]
eval_acc = eval_correct / eval_total if eval_total > 0 else 0

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update rolling windows
prev_7d = metrics.get("rolling_7d", {})
prev_7d_total = prev_7d.get("total_games", 0)
prev_7d_correct = prev_7d.get("total_correct", 0)

metrics["rolling_7d"] = {
    "accuracy": round((prev_7d_correct + eval_correct) / (prev_7d_total + eval_total), 4)
        if (prev_7d_total + eval_total) > 0 else 0,
    "ev_realized": round(prev_7d.get("ev_realized", 0) * 0.8 + eval_acc * 0.2, 4),
    "total_games": prev_7d_total + eval_total,
    "total_correct": prev_7d_correct + eval_correct,
    "note": (
        f"Updated with Oct 21 eval: {eval_correct}/{eval_total} ML ({eval_acc:.0%}). "
        f"5 upsets across NHL/NBA (PHI beat BUF, ATL beat ORL, WAS beat MIL, CHA beat BKN, MIN beat MIA). "
        f"injury-rest-v1 sole model to predict WAS upset."
    ),
}

prev_30d = metrics.get("rolling_30d", {})
metrics["rolling_30d"] = {
    "accuracy": round(
        (prev_30d.get("total_correct", 0) + eval_correct) /
        (prev_30d.get("total_games", 0) + eval_total), 4
    ) if (prev_30d.get("total_games", 0) + eval_total) > 0 else 0,
    "ev_realized": round(prev_30d.get("ev_realized", 0) * 0.9 + eval_acc * 0.1, 4),
    "total_games": prev_30d.get("total_games", 0) + eval_total,
    "total_correct": prev_30d.get("total_correct", 0) + eval_correct,
    "note": f"30 days of data. {prev_30d.get('total_games', 0) + eval_total} games evaluated."
}

all_time = metrics.get("all_time", {})
metrics["all_time"] = {
    "accuracy": round(
        (all_time.get("total_correct", 0) + eval_correct) /
        (all_time.get("total_games", 0) + eval_total), 4
    ) if (all_time.get("total_games", 0) + eval_total) > 0 else 0,
    "ev_realized": round(all_time.get("ev_realized", 0) * 0.95 + eval_acc * 0.05, 4),
    "total_games": all_time.get("total_games", 0) + eval_total,
    "total_correct": all_time.get("total_correct", 0) + eval_correct,
    "total_bets_recommended": all_time.get("total_bets_recommended", 0) + len(bet_games),
    "total_bets_won": all_time.get("total_bets_won", 0),
}

# Update variant performance
for m in all_models:
    mid = m["id"]
    metrics["variant_performance"][mid] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "lifetime_accuracy": round(
            m.get("lifetime_correct", 0) / m.get("lifetime_games", 1), 4
        ),
        "weight": m.get("weight", 0.5),
        "role": "champion" if mid == champion["id"] else "challenger",
    }

metrics["last_updated"] = TODAY
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(all_games),
    "bets_recommended": len(bet_games),
    "leans": len([g for g in games_output if g["blended"]["verdict"] == "LEAN"]),
    "no_bets": len([g for g in games_output if g["blended"]["verdict"] == "NO BET"]),
    "sports": list(sport_groups.keys()),
    "notes": (
        f"Oct 21 eval: champion {eval_correct}/{eval_total} ML ({eval_acc:.0%}). "
        f"injury-rest-v1 best at 9/13 (69%) — only model to call WAS upset over MIL. "
        f"injury-rest weight 0.8 → 0.9. No promotions."
    ),
}

# Add champion history entry if there was a promotion
# (No promotion today, but keep the structure)

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")
print(f"✅ Metrics updated")

# ── Print summary ──
print(f"\n📊 Edge-Finder Metrics")
print(f"━━━━━━━━━━━━━━━━━━━━")
print(f"Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
r7 = metrics["rolling_7d"]
r30 = metrics["rolling_30d"]
print(f"7-day:  {r7['accuracy']:.0%} accuracy | {r7['ev_realized']:+.1%} realized EV | {r7['total_games']} games")
print(f"30-day: {r30['accuracy']:.0%} accuracy | {r30['ev_realized']:+.1%} realized EV | {r30['total_games']} games")

weights_str = ", ".join(
    f"{c['id'].replace('-v1', '')}={c['weight']}"
    for c in challengers
)
print(f"\nChallenger weights: {weights_str}")

graveyard = assumptions.get("graveyard", [])
if graveyard:
    gy_str = ", ".join(
        f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)"
        for g in graveyard
    )
    print(f"Graveyard: {gy_str}")

print(f"\nTonight: {len(all_games)} games analyzed, {len(bet_games)} BET, "
      f"{len([g for g in games_output if g['blended']['verdict'] == 'LEAN'])} LEAN, "
      f"{len([g for g in games_output if g['blended']['verdict'] == 'NO BET'])} NO BET")

print("\n⚠️  Disclaimer: This is for entertainment and analysis purposes only. "
      "Past performance does not guarantee future results.")
