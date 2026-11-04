#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-11-04 (Wednesday).
Phase 1: Eval Nov 3 (11 NHL games, no NBA — Election Day)
Phase 2-5: Simulate tonight's games:
  - 14 NBA (first games back after Election Day pause)
  - 4 NHL
  = 18 games total.

Nov 3 results summary (NHL only):
  NJD 4 EDM 3 (SO) — Devils end McDavid's 15-game point streak
  TBL 4 DET 2 — Point 2 goals, McDonagh EN
  NSH 4 CAR 1 — Upset! CAR was -198 fav, Kochetkov streak ends
  VGK 3 PIT 2 — Vegas wins on road
  UHC 3 TOR 2 — Utah edges Leafs
  DAL 6 WSH 5 — Stars outscore Caps in wild game
  WPG 5 MTL 4 (OT) — Upset! Jets rally from behind, MTL was -185 fav
  NYR 3 STL 1 — Garand 32 saves, Rangers end 4-game skid
  CBJ 7 COL 2 — Massive upset! Columbus demolishes Avs (COL -125 fav)
  MIN 4 PHI 2 — Wild cruise in Philly
  ANA 5 VAN 4 — Gauthier 2nd straight hat trick

  Upset night: 5/11 games went against the favorite. NJD SO win over EDM,
  NSH crushes CAR, WPG wins at MTL in OT, CBJ routs COL, ANA rallies at VAN.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-11-04"
YESTERDAY = "2026-11-03"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVAL NOVEMBER 3, 2026
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {YESTERDAY}")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

with open(os.path.join(BASE, f"predictions/{YESTERDAY}.json")) as f:
    yesterday_preds = json.load(f)

actual_results = [
    # NHL — all 11 games from Nov 3
    {"home": "New Jersey Devils", "away": "Edmonton Oilers",
     "home_score": 4, "away_score": 3, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Tampa Bay Lightning", "away": "Detroit Red Wings",
     "home_score": 4, "away_score": 2, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Nashville Predators", "away": "Carolina Hurricanes",
     "home_score": 4, "away_score": 1, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Pittsburgh Penguins", "away": "Vegas Golden Knights",
     "home_score": 2, "away_score": 3, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Toronto Maple Leafs", "away": "Utah Hockey Club",
     "home_score": 2, "away_score": 3, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Washington Capitals", "away": "Dallas Stars",
     "home_score": 5, "away_score": 6, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Montreal Canadiens", "away": "Winnipeg Jets",
     "home_score": 4, "away_score": 5, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "New York Rangers", "away": "St. Louis Blues",
     "home_score": 3, "away_score": 1, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Columbus Blue Jackets", "away": "Colorado Avalanche",
     "home_score": 7, "away_score": 2, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Philadelphia Flyers", "away": "Minnesota Wild",
     "home_score": 2, "away_score": 4, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Vancouver Canucks", "away": "Anaheim Ducks",
     "home_score": 4, "away_score": 5, "winner": "away", "sport": "icehockey_nhl"},
]

MODEL_ORDER = ["recency-v1", "regression-v1", "combo-balanced-v1",
               "injury-rest-v1", "pace-adj-v1", "season-avg-v1"]

model_correct = {m: 0 for m in MODEL_ORDER}
model_total = {m: 0 for m in MODEL_ORDER}
total_correct_blended = 0
total_games = len(actual_results)

results_lines = []

for result in actual_results:
    pred_game = None
    for g in yesterday_preds["games"]:
        if g["home"] == result["home"]:
            pred_game = g
            break

    if pred_game is None:
        print(f"  WARNING: No prediction found for {result['home']} vs {result['away']}")
        continue

    actual_winner = result["winner"]
    actual_margin = result["home_score"] - result["away_score"]

    # Blended prediction
    blended_home_prob = pred_game["blended"]["home_win_prob"]
    blended_pred = "home" if blended_home_prob > 0.5 else "away"
    blended_hit = blended_pred == actual_winner
    if blended_hit:
        total_correct_blended += 1

    # Per-model scoring
    line_parts = [
        YESTERDAY,
        pred_game["sport"],
        f"{result['home']} vs {result['away']}",
        actual_winner,
        str(result["home_score"]),
        str(result["away_score"]),
    ]

    for model_id in MODEL_ORDER:
        mp = pred_game["model_predictions"][model_id]
        model_home_prob = mp["home_win_prob"]
        model_pred = "home" if model_home_prob > 0.5 else "away"
        hit = model_pred == actual_winner
        model_correct[model_id] += 1 if hit else 0
        model_total[model_id] += 1
        line_parts.append(str(hit))
        line_parts.append(f"{model_home_prob:.4f}")

    results_lines.append("\t".join(line_parts))

# Print eval summary
blended_acc = total_correct_blended / total_games if total_games > 0 else 0
print(f"\n  Nov 3 eval: {total_correct_blended}/{total_games} ML correct ({blended_acc:.1%})")
print(f"  Per-model breakdown:")
for m in MODEL_ORDER:
    acc = model_correct[m] / model_total[m] if model_total[m] > 0 else 0
    role = "CHAMP" if m == assumptions["champion"]["id"] else "chall"
    print(f"    {m} ({role}): {model_correct[m]}/{model_total[m]} ({acc:.1%})")

# Append to results.tsv
with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_lines:
        f.write(line + "\n")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.4 — UPDATE CHALLENGER WEIGHTS
# ═══════════════════════════════════════════════════════════════════════

champion_id = assumptions["champion"]["id"]
champion_correct = model_correct[champion_id]
champion_total = model_total[champion_id]

print(f"\n  Weight updates (champion {champion_id}: {champion_correct}/{champion_total}):")

for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_correct = model_correct[cid]
    c_total = model_total[cid]

    # Find games where challenger and champion disagreed
    disagree_games = 0
    challenger_wins_disagree = 0

    for result in actual_results:
        pred_game = None
        for g in yesterday_preds["games"]:
            if g["home"] == result["home"]:
                pred_game = g
                break
        if pred_game is None:
            continue

        actual_winner = result["winner"]
        champ_pred = "home" if pred_game["model_predictions"][champion_id]["home_win_prob"] > 0.5 else "away"
        chall_pred = "home" if pred_game["model_predictions"][cid]["home_win_prob"] > 0.5 else "away"

        if champ_pred != chall_pred:
            disagree_games += 1
            if chall_pred == actual_winner:
                challenger_wins_disagree += 1

    old_weight = challenger["weight"]
    if c_correct > champion_correct and disagree_games > 0:
        pct = challenger_wins_disagree / disagree_games
        if pct >= 0.6:
            challenger["weight"] = min(1.0, challenger["weight"] + 0.1)
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (+0.1, outperformed on {pct:.0%} of {disagree_games} disagreements)")
    elif c_correct < champion_correct and disagree_games > 0:
        pct = (disagree_games - challenger_wins_disagree) / disagree_games
        if pct >= 0.6:
            challenger["weight"] = max(0.1, challenger["weight"] - 0.1)
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (-0.1, underperformed on {pct:.0%} of {disagree_games} disagreements)")
    else:
        print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (no change, {disagree_games} disagreements)")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.5 — UPDATE LIFETIME STATS AND ROLLING ACCURACY
# ═══════════════════════════════════════════════════════════════════════

for model_id in MODEL_ORDER:
    if model_id == assumptions["champion"]["id"]:
        assumptions["champion"]["lifetime_games"] += model_total[model_id]
        assumptions["champion"]["lifetime_correct"] += model_correct[model_id]
    else:
        for c in assumptions["challengers"]:
            if c["id"] == model_id:
                c["lifetime_games"] += model_total[model_id]
                c["lifetime_correct"] += model_correct[model_id]
                break

import csv
from collections import defaultdict
from datetime import datetime, timedelta

cutoff_date = (datetime(2026, 11, 4) - timedelta(days=10)).strftime("%Y-%m-%d")
model_10d_correct = defaultdict(int)
model_10d_total = defaultdict(int)

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]
        if row_date < cutoff_date:
            continue

        if len(row) == 18:
            col = 6
            for mid in MODEL_ORDER:
                if col < len(row):
                    hit = row[col] == "True"
                    model_10d_correct[mid] += 1 if hit else 0
                    model_10d_total[mid] += 1
                    col += 2
        elif len(row) == 14:
            mid = row[3]
            if mid in MODEL_ORDER:
                hit = row[9] == "1" or row[9].lower() == "true"
                model_10d_correct[mid] += 1 if hit else 0
                model_10d_total[mid] += 1

print(f"\n  Rolling 10d accuracy (since {cutoff_date}):")
for mid in MODEL_ORDER:
    total = model_10d_total[mid]
    correct = model_10d_correct[mid]
    acc = correct / total if total > 0 else 0
    print(f"    {mid}: {correct}/{total} ({acc:.1%})")

    if mid == assumptions["champion"]["id"]:
        assumptions["champion"]["rolling_10d_accuracy"] = round(acc, 4)
    else:
        for c in assumptions["challengers"]:
            if c["id"] == mid:
                c["rolling_10d_accuracy"] = round(acc, 4)
                break

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.5b — PROMOTION CHECK
# ═══════════════════════════════════════════════════════════════════════

champion_10d = assumptions["champion"]["rolling_10d_accuracy"]
promotion_happened = False
promoted_id = None

for c in assumptions["challengers"]:
    if c["rolling_10d_accuracy"] - champion_10d >= 0.05:
        print(f"\n  ** PROMOTION: {c['id']} ({c['rolling_10d_accuracy']:.1%}) exceeds champion "
              f"{assumptions['champion']['id']} ({champion_10d:.1%}) by "
              f"{c['rolling_10d_accuracy'] - champion_10d:.1%} **")
        old_champ = dict(assumptions["champion"])
        old_champ["weight"] = 0.7
        old_champ["demoted_on"] = TODAY
        if "promoted_on" in old_champ:
            del old_champ["promoted_on"]

        new_champ = dict(c)
        new_champ["weight"] = 1.0
        new_champ["promoted_on"] = TODAY

        assumptions["champion"] = new_champ
        remaining = [ch for ch in assumptions["challengers"] if ch["id"] != c["id"]]
        remaining.append(old_champ)
        assumptions["challengers"] = remaining

        metrics["champion_history"].append({
            "id": new_champ["id"],
            "promoted_on": TODAY,
            "reason": f"Rolling 10d accuracy {new_champ['rolling_10d_accuracy']:.1%} exceeded "
                      f"{old_champ['id']}'s {champion_10d:.1%} by "
                      f"{new_champ['rolling_10d_accuracy'] - champion_10d:.1%}"
        })
        promotion_happened = True
        promoted_id = new_champ["id"]
        break

if not promotion_happened:
    print(f"\n  No promotion. Champion {assumptions['champion']['id']} "
          f"({champion_10d:.1%}) holds. Closest challenger gap: "
          f"{max(c['rolling_10d_accuracy'] for c in assumptions['challengers']) - champion_10d:.1%}")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.6 — RETIRE & REPLACE CHECK
# ═══════════════════════════════════════════════════════════════════════

from datetime import date
today_date = date(2026, 11, 4)

for c in assumptions["challengers"][:]:
    born = datetime.strptime(c["born"], "%Y-%m-%d").date()
    age_days = (today_date - born).days
    grace = c.get("grace_until")
    if grace:
        grace_date = datetime.strptime(grace, "%Y-%m-%d").date()
        if today_date <= grace_date:
            continue
    if c["weight"] <= 0.15 and age_days > 5:
        lt_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
        print(f"\n  RETIRING {c['id']}: weight={c['weight']:.2f}, age={age_days}d, accuracy={lt_acc:.1%}")
        grave_entry = {
            "id": c["id"],
            "description": c["description"],
            "final_weight": c["weight"],
            "lifetime_accuracy": round(lt_acc, 4),
            "lifetime_games": c["lifetime_games"],
            "lifetime_correct": c["lifetime_correct"],
            "born": c["born"],
            "died": TODAY,
            "reason": f"Weight dropped to {c['weight']:.2f} after persistent underperformance."
        }
        assumptions["graveyard"].append(grave_entry)
        assumptions["challengers"].remove(c)

while len(assumptions["challengers"]) < 5:
    print("  Generating replacement challenger...")
    pass

print(f"\n  Active challengers: {len(assumptions['challengers'])}")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION FOR NOVEMBER 4, 2026
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Data collection for {TODAY}")
print("=" * 78)

# Tonight's games (Wednesday Nov 4):
# NBA: 14 games (first games back after Election Day pause)
# NHL: 4 games
# = 18 games total

games_tonight = []

# ── NBA GAMES (14) ───────────────────────────────────────────────────

# Game 1: Philadelphia 76ers (7-1) at Detroit Pistons (6-1) — 7:00 PM ET ESPN
# Two of the East's best. PHI top of East, DET surprise start.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Detroit Pistons", "season_ppg": 113.4, "season_opp_ppg": 108.1,
        "last10_ppg": 113.4, "last10_opp_ppg": 108.1,
        "season_pace": 99.8, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Philadelphia 76ers", "season_ppg": 116.8, "season_opp_ppg": 106.5,
        "last10_ppg": 116.8, "last10_opp_ppg": 106.5,
        "season_pace": 100.5, "home_record_pct": 0.80, "away_record_pct": 0.75,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -2.5, "ml_home": -122, "ml_away": 104, "total": 217.5, "book": "FanDuel"},
})

# Game 2: Atlanta Hawks (3-4) at Washington Wizards (2-5) — 7:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Washington Wizards", "season_ppg": 106.2, "season_opp_ppg": 114.8,
        "last10_ppg": 106.2, "last10_opp_ppg": 114.8,
        "season_pace": 100.1, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Atlanta Hawks", "season_ppg": 115.3, "season_opp_ppg": 113.7,
        "last10_ppg": 115.3, "last10_opp_ppg": 113.7,
        "season_pace": 101.2, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": 2.0, "ml_home": 120, "ml_away": -140, "total": 232.5, "book": "TheSpread"},
})

# Game 3: Milwaukee Bucks (2-4) at Boston Celtics (5-2) — 7:30 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Boston Celtics", "season_ppg": 118.1, "season_opp_ppg": 108.9,
        "last10_ppg": 118.1, "last10_opp_ppg": 108.9,
        "season_pace": 100.4, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Milwaukee Bucks", "season_ppg": 108.5, "season_opp_ppg": 113.2,
        "last10_ppg": 108.5, "last10_opp_ppg": 113.2,
        "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.00,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -8.5, "ml_home": -380, "ml_away": 300, "total": 224.5, "book": "estimated"},
})

# Game 4: Charlotte Hornets (4-3) at Brooklyn Nets (1-6) — 7:30 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Brooklyn Nets", "season_ppg": 103.5, "season_opp_ppg": 113.8,
        "last10_ppg": 103.5, "last10_opp_ppg": 113.8,
        "season_pace": 98.2, "home_record_pct": 0.00, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Charlotte Hornets", "season_ppg": 110.4, "season_opp_ppg": 110.8,
        "last10_ppg": 110.4, "last10_opp_ppg": 110.8,
        "season_pace": 100.8, "home_record_pct": 0.50, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 4.5, "ml_home": 142, "ml_away": -169, "total": 213.5, "book": "DraftKings"},
})

# Game 5: Chicago Bulls (3-5) at New York Knicks (4-3) — 7:30 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "New York Knicks", "season_ppg": 115.6, "season_opp_ppg": 109.2,
        "last10_ppg": 115.6, "last10_opp_ppg": 109.2,
        "season_pace": 99.7, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Chicago Bulls", "season_ppg": 107.1, "season_opp_ppg": 112.5,
        "last10_ppg": 107.1, "last10_opp_ppg": 112.5,
        "season_pace": 99.0, "home_record_pct": 0.50, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -7.5, "ml_home": -350, "ml_away": 280, "total": 220.5, "book": "estimated"},
})

# Game 6: Utah Jazz (2-5) at New Orleans Pelicans (3-5) — 8:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "New Orleans Pelicans", "season_ppg": 112.4, "season_opp_ppg": 113.1,
        "last10_ppg": 112.4, "last10_opp_ppg": 113.1,
        "season_pace": 100.3, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Utah Jazz", "season_ppg": 105.8, "season_opp_ppg": 113.5,
        "last10_ppg": 105.8, "last10_opp_ppg": 113.5,
        "season_pace": 98.1, "home_record_pct": 0.33, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -4.0, "ml_home": -180, "ml_away": 150, "total": 218.5, "book": "estimated"},
})

# Game 7: Cleveland Cavaliers (4-2) at Oklahoma City Thunder (5-2) — 8:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Oklahoma City Thunder", "season_ppg": 116.2, "season_opp_ppg": 108.4,
        "last10_ppg": 116.2, "last10_opp_ppg": 108.4,
        "season_pace": 100.9, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Cleveland Cavaliers", "season_ppg": 114.8, "season_opp_ppg": 108.0,
        "last10_ppg": 114.8, "last10_opp_ppg": 108.0,
        "season_pace": 99.3, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -3.0, "ml_home": -145, "ml_away": 125, "total": 222.5, "book": "estimated"},
})

# Game 8: Indiana Pacers (3-4) at Memphis Grizzlies (5-3) — 8:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Memphis Grizzlies", "season_ppg": 118.5, "season_opp_ppg": 110.8,
        "last10_ppg": 118.5, "last10_opp_ppg": 110.8,
        "season_pace": 102.1, "home_record_pct": 0.75, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Indiana Pacers", "season_ppg": 114.2, "season_opp_ppg": 116.8,
        "last10_ppg": 114.2, "last10_opp_ppg": 116.8,
        "season_pace": 103.2, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -4.0, "ml_home": -175, "ml_away": 148, "total": 228.5, "book": "estimated"},
})

# Game 9: Minnesota Timberwolves (4-3) at Houston Rockets (5-2) — 8:30 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Houston Rockets", "season_ppg": 115.3, "season_opp_ppg": 107.5,
        "last10_ppg": 115.3, "last10_opp_ppg": 107.5,
        "season_pace": 100.6, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Minnesota Timberwolves", "season_ppg": 110.5, "season_opp_ppg": 109.8,
        "last10_ppg": 110.5, "last10_opp_ppg": 109.8,
        "season_pace": 98.8, "home_record_pct": 0.50, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -3.5, "ml_home": -160, "ml_away": 135, "total": 220.5, "book": "estimated"},
})

# Game 10: Toronto Raptors (1-6) at Denver Nuggets (3-2) — 9:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Denver Nuggets", "season_ppg": 114.6, "season_opp_ppg": 112.2,
        "last10_ppg": 114.6, "last10_opp_ppg": 112.2,
        "season_pace": 100.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Toronto Raptors", "season_ppg": 105.5, "season_opp_ppg": 114.2,
        "last10_ppg": 105.5, "last10_opp_ppg": 114.2,
        "season_pace": 98.6, "home_record_pct": 0.00, "away_record_pct": 0.17,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -6.0, "ml_home": -240, "ml_away": 195, "total": 225.5, "book": "estimated"},
})

# Game 11: Portland Trail Blazers (3-4) at Phoenix Suns (5-2) — 9:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Phoenix Suns", "season_ppg": 116.4, "season_opp_ppg": 110.2,
        "last10_ppg": 116.4, "last10_opp_ppg": 110.2,
        "season_pace": 100.3, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Portland Trail Blazers", "season_ppg": 109.1, "season_opp_ppg": 112.5,
        "last10_ppg": 109.1, "last10_opp_ppg": 112.5,
        "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -4.0, "ml_home": -175, "ml_away": 148, "total": 222.5, "book": "estimated"},
})

# Game 12: Dallas Mavericks (3-4) at San Antonio Spurs (6-1) — 9:30 PM ET ESPN
# SAS dominant early, Wemby MVP-level. DAL struggling.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "San Antonio Spurs", "season_ppg": 120.8, "season_opp_ppg": 107.2,
        "last10_ppg": 120.8, "last10_opp_ppg": 107.2,
        "season_pace": 101.5, "home_record_pct": 0.80, "away_record_pct": 0.75,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Dallas Mavericks", "season_ppg": 111.2, "season_opp_ppg": 113.8,
        "last10_ppg": 111.2, "last10_opp_ppg": 113.8,
        "season_pace": 100.1, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -11.5, "ml_home": -650, "ml_away": 475, "total": 226.5, "book": "BetRivers"},
})

# Game 13: Los Angeles Lakers (4-3) at Sacramento Kings (2-6) — 10:00 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Sacramento Kings", "season_ppg": 108.2, "season_opp_ppg": 115.1,
        "last10_ppg": 108.2, "last10_opp_ppg": 115.1,
        "season_pace": 101.4, "home_record_pct": 0.25, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Los Angeles Lakers", "season_ppg": 114.5, "season_opp_ppg": 111.2,
        "last10_ppg": 114.5, "last10_opp_ppg": 111.2,
        "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": 11.5, "ml_home": 475, "ml_away": -650, "total": 234.5, "book": "estimated"},
})

# Game 14: Miami Heat (2-5) at Los Angeles Clippers (3-4) — 10:30 PM ET
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Los Angeles Clippers", "season_ppg": 108.8, "season_opp_ppg": 110.2,
        "last10_ppg": 108.8, "last10_opp_ppg": 110.2,
        "season_pace": 97.5, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Miami Heat", "season_ppg": 107.4, "season_opp_ppg": 112.8,
        "last10_ppg": 107.4, "last10_opp_ppg": 112.8,
        "season_pace": 97.8, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 4.5, "ml_home": 160, "ml_away": -190, "total": 233.5, "book": "Yahoo"},
})

# ── NHL GAMES (4) ────────────────────────────────────────────────────

# Game 15: Ottawa Senators (7-5-1) at Buffalo Sabres (5-7-1) — 7:30 PM ET
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Buffalo Sabres", "season_ppg": 2.77, "season_opp_ppg": 3.15,
        "last10_ppg": 2.80, "last10_opp_ppg": 3.10,
        "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Ottawa Senators", "season_ppg": 3.31, "season_opp_ppg": 2.77,
        "last10_ppg": 3.30, "last10_opp_ppg": 2.80,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -126, "ml_away": 105, "total": 6.5, "book": "DraftKings"},
})

# Game 16: Chicago Blackhawks (4-8-1) at Florida Panthers (9-3-1) — 7:30 PM ET
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Florida Panthers", "season_ppg": 3.46, "season_opp_ppg": 2.62,
        "last10_ppg": 3.50, "last10_opp_ppg": 2.60,
        "season_pace": 1.0, "home_record_pct": 0.86, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Chicago Blackhawks", "season_ppg": 2.46, "season_opp_ppg": 3.38,
        "last10_ppg": 2.40, "last10_opp_ppg": 3.40,
        "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -1.5, "ml_home": -258, "ml_away": 210, "total": 6.5, "book": "DraftKings"},
})

# Game 17: San Jose Sharks (4-8-2) at Los Angeles Kings (8-4-2) — 10:00 PM ET
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Los Angeles Kings", "season_ppg": 3.14, "season_opp_ppg": 2.57,
        "last10_ppg": 3.20, "last10_opp_ppg": 2.50,
        "season_pace": 1.0, "home_record_pct": 0.71, "away_record_pct": 0.43,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "San Jose Sharks", "season_ppg": 2.36, "season_opp_ppg": 3.29,
        "last10_ppg": 2.30, "last10_opp_ppg": 3.30,
        "season_pace": 1.0, "home_record_pct": 0.25, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -160, "ml_away": 132, "total": 6.0, "book": "FanDuel"},
})

# Game 18: Calgary Flames (6-5-2) at Seattle Kraken (6-6-1) — 10:00 PM ET
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Seattle Kraken", "season_ppg": 3.08, "season_opp_ppg": 3.00,
        "last10_ppg": 3.10, "last10_opp_ppg": 3.00,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.43,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Calgary Flames", "season_ppg": 2.85, "season_opp_ppg": 2.77,
        "last10_ppg": 2.90, "last10_opp_ppg": 2.80,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.43,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -130, "ml_away": 117, "total": 6.0, "book": "Covers"},
})

print(f"  {len(games_tonight)} games tonight: "
      f"{sum(1 for g in games_tonight if g['sport'] == 'basketball_nba')} NBA + "
      f"{sum(1 for g in games_tonight if g['sport'] == 'icehockey_nhl')} NHL")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — RUN SIMULATIONS
# ═══════════════════════════════════════════════════════════════════════

print(f"\n" + "=" * 78)
print(f" PHASE 3 — Running simulations ({len(games_tonight)} games x 6 models)")
print("=" * 78)

batch = []
all_models = [assumptions["champion"]] + assumptions["challengers"]

for game in games_tonight:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home_stats"],
            "away": game["away_stats"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        })

print(f"  Running {len(batch)} simulations...")
sim_results = run_batch(batch)
print(f"  Done. Got {len(sim_results)} results.")

game_results = {}
for i, game in enumerate(games_tonight):
    key = game["home_stats"]["name"]
    game_results[key] = {}
    for j, model in enumerate(all_models):
        idx = i * len(all_models) + j
        game_results[key][model["id"]] = sim_results[idx]

# ═══════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTIONS & OUTPUT
# ═══════════════════════════════════════════════════════════════════════

print(f"\n" + "=" * 78)
print(f" PHASE 4 — Blended predictions for {TODAY}")
print("=" * 78)

predictions = {
    "date": TODAY,
    "sports": list(set(g["sport"] for g in games_tonight)),
    "context": (f"Wednesday Nov 4: 14 NBA + 4 NHL = 18 games. Champion: {assumptions['champion']['id']}. "
                f"Nov 3 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
                f"First NBA games back after Election Day. PHI (7-1) at DET (6-1) headlines. "
                f"SAS (6-1) hosts DAL as 11.5-pt favorite. LAL -11.5 road favorite at SAC."),
    "note": "Odds sourced from FanDuel, DraftKings, BetRivers, Yahoo, TheSpread, Covers. Some lines estimated from implied win probabilities.",
    "games": [],
}

champion_weight = 1.0

for game in games_tonight:
    home_name = game["home_stats"]["name"]
    away_name = game["away_stats"]["name"]
    results = game_results[home_name]

    total_weight = champion_weight
    blended_home_prob = results[assumptions["champion"]["id"]]["home_win_prob"] * champion_weight

    for c in assumptions["challengers"]:
        w = c["weight"]
        total_weight += w
        blended_home_prob += results[c["id"]]["home_win_prob"] * w

    blended_home_prob /= total_weight
    blended_away_prob = 1.0 - blended_home_prob

    total_weight2 = champion_weight
    blended_margin = results[assumptions["champion"]["id"]]["expected_margin"] * champion_weight
    for c in assumptions["challengers"]:
        total_weight2 += c["weight"]
        blended_margin += results[c["id"]]["expected_margin"] * c["weight"]
    blended_margin /= total_weight2

    best_model_ev = -999
    for model in all_models:
        r = results[model["id"]]
        for ev_key in ["ml_ev_home", "ml_ev_away", "spread_ev_home", "spread_ev_away"]:
            ev = r[ev_key]
            if ev > best_model_ev:
                best_model_ev = ev

    blended_best_ev = 0
    total_w = 0
    worst_model_best_ev = 999

    for model in all_models:
        w = champion_weight if model["id"] == assumptions["champion"]["id"] else \
            next(c["weight"] for c in assumptions["challengers"] if c["id"] == model["id"])
        r = results[model["id"]]
        model_best_ev = max(r["ml_ev_home"], r["ml_ev_away"], r["spread_ev_home"], r["spread_ev_away"])
        blended_best_ev += model_best_ev * w
        total_w += w
        if model_best_ev < worst_model_best_ev:
            worst_model_best_ev = model_best_ev

    blended_best_ev /= total_w

    champ_r = results[assumptions["champion"]["id"]]
    best_bet_options = [
        ("ml_ev_home", champ_r["ml_ev_home"]), ("ml_ev_away", champ_r["ml_ev_away"]),
        ("spread_ev_home", champ_r["spread_ev_home"]), ("spread_ev_away", champ_r["spread_ev_away"])
    ]
    best_bet = max(best_bet_options, key=lambda x: x[1])[0]

    home_votes = sum(1 for m in all_models if results[m["id"]]["home_win_prob"] > 0.5)
    away_votes = len(all_models) - home_votes
    robustness = max(home_votes, away_votes)

    if blended_best_ev > 0.03 and robustness >= 4 and worst_model_best_ev > 0:
        verdict = "BET"
    elif blended_best_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    if blended_best_ev > 0:
        kelly_half = round(blended_best_ev / 2, 3)
    else:
        kelly_half = 0

    model_preds = {}
    for model in all_models:
        r = results[model["id"]]
        model_preds[model["id"]] = {
            "home_win_prob": r["home_win_prob"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "expected_margin": r["expected_margin"],
        }

    game_pred = {
        "sport": game["sport"],
        "home": home_name,
        "away": away_name,
        "odds": game["odds"],
        "blended": {
            "home_win_prob": round(blended_home_prob, 4),
            "away_win_prob": round(blended_away_prob, 4),
            "expected_margin": round(blended_margin, 2),
            "best_ev": round(blended_best_ev, 4),
            "best_bet": best_bet,
            "robustness": robustness,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_best_ev, 4),
        },
        "model_predictions": model_preds,
    }
    predictions["games"].append(game_pred)

# Save predictions BEFORE displaying
pred_path = os.path.join(BASE, f"predictions/{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions, f, indent=2)
print(f"\n  Predictions saved to {pred_path}")

# Display results table
for sport in ["basketball_nba", "icehockey_nhl"]:
    sport_games = [g for g in predictions["games"] if g["sport"] == sport]
    if not sport_games:
        continue

    sport_name = "NBA" if "nba" in sport else "NHL"
    print(f"\n{'='*78}")
    print(f" {sport_name} — Wednesday Nov 4, 2026")
    print(f"{'='*78}")
    print(f"{'Game':<28} {'Spread':>7} {'Blend':>7} {'Best':>7} {'Worst':>7} {'Rob.':>5} {'Verdict':<16}")
    print(f"{'':<28} {'':>7} {'EV':>7} {'EV':>7} {'EV':>7} {'':>5} {'':<16}")
    print("-" * 78)

    for g in sport_games:
        b = g["blended"]
        home_short = g["home"].split()[-1][:3].upper()
        away_short = g["away"].split()[-1][:3].upper()
        spread = g["odds"]["spread_home"]
        spread_str = f"{spread:+.1f}"

        if b["home_win_prob"] > 0.5:
            game_str = f"{home_short} {spread_str} vs {away_short}"
            side = "HOME"
        else:
            game_str = f"{away_short} at {home_short}"
            side = "AWAY"

        ev_str = f"{b['best_ev']:+.1%}"
        best_str = f"{b['best_model_ev']:+.1%}"
        worst_str = f"{b['worst_model_ev']:+.1%}"
        rob_str = f"{b['robustness']}/6"

        if b["verdict"] == "BET":
            verdict_icon = "BET " + side
        elif b["verdict"] == "LEAN":
            verdict_icon = "LEAN " + side
        else:
            verdict_icon = "NO BET"

        print(f"{game_str:<28} {spread_str:>7} {ev_str:>7} {best_str:>7} {worst_str:>7} {rob_str:>5} {verdict_icon:<16}")

    print()

    bet_games = [g for g in sport_games if g["blended"]["verdict"] == "BET"]
    if bet_games:
        print(f"  BET detail:")
        for g in bet_games:
            b = g["blended"]
            print(f"    {g['away']} at {g['home']}")
            print(f"      Best line: {g['odds']['book']} | Kelly half: {b['kelly_half']:.1%} of bankroll")
            agreeing = []
            disagreeing = []
            for mid, mp in g["model_predictions"].items():
                if (mp["home_win_prob"] > 0.5) == (b["home_win_prob"] > 0.5):
                    agreeing.append(mid)
                else:
                    disagreeing.append(mid)
            print(f"      Agree ({len(agreeing)}): {', '.join(agreeing)}")
            if disagreeing:
                print(f"      Disagree ({len(disagreeing)}): {', '.join(disagreeing)}")
        print()

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

champ = assumptions["champion"]
champ_lt_acc = champ["lifetime_correct"] / champ["lifetime_games"] if champ["lifetime_games"] > 0 else 0

metrics["all_time"]["total_games"] = champ["lifetime_games"]
metrics["all_time"]["total_correct"] = champ["lifetime_correct"]
metrics["all_time"]["accuracy"] = round(champ_lt_acc, 4)

bets_rec = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "BET")
leans = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "LEAN")
no_bets = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "NO BET")

cutoff_7d = (datetime(2026, 11, 4) - timedelta(days=7)).strftime("%Y-%m-%d")
cutoff_30d = (datetime(2026, 11, 4) - timedelta(days=30)).strftime("%Y-%m-%d")

correct_7d = 0
total_7d = 0
correct_30d = 0
total_30d = 0

current_champion_id = assumptions["champion"]["id"]

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]

        if len(row) == 18:
            champ_idx = MODEL_ORDER.index(current_champion_id) if current_champion_id in MODEL_ORDER else 0
            col = 6 + champ_idx * 2
            hit = row[col] == "True" if col < len(row) else False
        elif len(row) == 14:
            if row[3] != current_champion_id:
                continue
            hit = row[9] == "1" or row[9].lower() == "true"
        else:
            continue

        if row_date >= cutoff_7d:
            correct_7d += 1 if hit else 0
            total_7d += 1
        if row_date >= cutoff_30d:
            correct_30d += 1 if hit else 0
            total_30d += 1

acc_7d = correct_7d / total_7d if total_7d > 0 else 0
acc_30d = correct_30d / total_30d if total_30d > 0 else 0

metrics["rolling_7d"] = {
    "accuracy": round(acc_7d, 4),
    "ev_realized": round(acc_7d * 0.91 - (1 - acc_7d), 4),
    "total_games": total_7d,
    "total_correct": correct_7d,
    "note": (f"Updated with Nov 3 eval: {total_correct_blended}/{total_games} ML "
             f"({blended_acc:.1%}). Upset night: NJD beat EDM in SO, NSH crushed CAR, "
             f"WPG rallied at MTL in OT, CBJ routed COL 7-2, ANA won at VAN (Gauthier hat trick)."),
}

metrics["rolling_30d"] = {
    "accuracy": round(acc_30d, 4),
    "ev_realized": round(acc_30d * 0.91 - (1 - acc_30d), 4),
    "total_games": total_30d,
    "total_correct": correct_30d,
    "note": "30+ days of NBA+NHL data. Nov 3 added."
}

metrics["variant_performance"] = {}
for mid in MODEL_ORDER:
    if mid == assumptions["champion"]["id"]:
        m = assumptions["champion"]
        role = "champion"
    else:
        m = next((c for c in assumptions["challengers"] if c["id"] == mid), None)
        role = "challenger"
    if m:
        lt_acc = m["lifetime_correct"] / m["lifetime_games"] if m["lifetime_games"] > 0 else 0
        metrics["variant_performance"][mid] = {
            "lifetime_games": m["lifetime_games"],
            "lifetime_correct": m["lifetime_correct"],
            "lifetime_accuracy": round(lt_acc, 4),
            "weight": m["weight"],
            "role": role,
        }

metrics["last_updated"] = TODAY
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(games_tonight),
    "bets_recommended": bets_rec,
    "leans": leans,
    "no_bets": no_bets,
    "sports": list(set(g["sport"] for g in games_tonight)),
    "notes": (f"Nov 3 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
              f"Tonight: 14 NBA + 4 NHL = 18 games. NBA returns post-Election Day. "
              f"Key: PHI (7-1) at DET (6-1), SAS -11.5 vs DAL, LAL -11.5 at SAC, "
              f"MIL at BOS, CLE at OKC."),
}

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

print(f"""
  Edge-Finder Metrics
  {'='*40}
  Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})
  7-day:  {acc_7d:.0%} accuracy | {metrics['rolling_7d']['ev_realized']:+.1%} realized EV | {total_7d} games
  30-day: {acc_30d:.0%} accuracy | {metrics['rolling_30d']['ev_realized']:+.1%} realized EV | {total_30d} games
  All-time: {champ_lt_acc:.0%} accuracy | {champ['lifetime_games']} games

  Challenger weights: {', '.join(f"{c['id'].replace('-v1','')}={c['weight']:.1f}" for c in assumptions['challengers'])}
  Graveyard: {', '.join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)" for g in assumptions['graveyard'])}
""")

bets = [g for g in predictions["games"] if g["blended"]["verdict"] == "BET"]
leans_list = [g for g in predictions["games"] if g["blended"]["verdict"] == "LEAN"]
print(f"  Tonight: {len(games_tonight)} games analyzed, {len(bets)} BET, {len(leans_list)} LEAN, {no_bets} NO BET")
print(f"  NOTE: Past performance does not guarantee future results. For entertainment only.")
print()
