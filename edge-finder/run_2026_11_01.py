#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-11-01 (Sunday).
Phase 1: Eval Oct 31 (15 games: 7 NBA + 8 NHL)
Phase 2-5: Simulate tonight's games:
  - 4 NBA (SUN)
  - 5 NHL (SUN)
  = 9 games total.

Oct 31 results summary:
  NBA (7 games): POR 112 UTA 90, PHI 109 CHA 104, NOP 121 ATL 99,
    CLE 136 MIL 111, SAS 121 MIN 111 (Wemby 43!), MEM 136 SAC 105, HOU 119 OKC 98
  NHL (8 games): OTT 5 SJS 1, BOS 5 CHI 4 OT, NSH 5 TBL 4 SO,
    EDM 4 NYI 0, MTL 5 PIT 4, TOR 4 VAN 2, COL 5 CGY 2, DAL 3 CBJ 1
  Upsets: NOP blew out ATL at home (ATL -3.5 fav), NSH beat TBL in SO (TBL -176 fav)
  NFL: Week 8 Sunday games today, not tracked.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-11-01"
YESTERDAY = "2026-10-31"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVAL OCTOBER 31, 2026
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
    # NBA
    {"home": "Portland Trail Blazers", "away": "Utah Jazz",
     "home_score": 112, "away_score": 90, "winner": "home", "sport": "basketball_nba"},
    {"home": "Philadelphia 76ers", "away": "Charlotte Hornets",
     "home_score": 109, "away_score": 104, "winner": "home", "sport": "basketball_nba"},
    {"home": "Atlanta Hawks", "away": "New Orleans Pelicans",
     "home_score": 99, "away_score": 121, "winner": "away", "sport": "basketball_nba"},
    {"home": "Cleveland Cavaliers", "away": "Milwaukee Bucks",
     "home_score": 136, "away_score": 111, "winner": "home", "sport": "basketball_nba"},
    {"home": "San Antonio Spurs", "away": "Minnesota Timberwolves",
     "home_score": 121, "away_score": 111, "winner": "home", "sport": "basketball_nba"},
    {"home": "Memphis Grizzlies", "away": "Sacramento Kings",
     "home_score": 136, "away_score": 105, "winner": "home", "sport": "basketball_nba"},
    {"home": "Houston Rockets", "away": "Oklahoma City Thunder",
     "home_score": 119, "away_score": 98, "winner": "home", "sport": "basketball_nba"},
    # NHL
    {"home": "San Jose Sharks", "away": "Ottawa Senators",
     "home_score": 1, "away_score": 5, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Boston Bruins", "away": "Chicago Blackhawks",
     "home_score": 5, "away_score": 4, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Nashville Predators", "away": "Tampa Bay Lightning",
     "home_score": 5, "away_score": 4, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "New York Islanders", "away": "Edmonton Oilers",
     "home_score": 0, "away_score": 4, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Montreal Canadiens", "away": "Pittsburgh Penguins",
     "home_score": 5, "away_score": 4, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Vancouver Canucks", "away": "Toronto Maple Leafs",
     "home_score": 2, "away_score": 4, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Colorado Avalanche", "away": "Calgary Flames",
     "home_score": 5, "away_score": 2, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Dallas Stars", "away": "Columbus Blue Jackets",
     "home_score": 3, "away_score": 1, "winner": "home", "sport": "icehockey_nhl"},
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
print(f"\n  Oct 31 eval: {total_correct_blended}/{total_games} ML correct ({blended_acc:.1%})")
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

# Update rolling 10d accuracy using recent results from results.tsv
# Handle two formats: old (14 cols, one row per model) and new (18 cols, one row per game)
import csv
from collections import defaultdict
from datetime import datetime, timedelta

cutoff_date = (datetime(2026, 11, 1) - timedelta(days=10)).strftime("%Y-%m-%d")
model_10d_correct = defaultdict(int)
model_10d_total = defaultdict(int)

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)  # skip header
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]
        if row_date < cutoff_date:
            continue

        if len(row) == 18:
            # New format: one row per game, cols 6-17 = 6 model pairs (hit, prob)
            col = 6
            for mid in MODEL_ORDER:
                if col < len(row):
                    hit = row[col] == "True"
                    model_10d_correct[mid] += 1 if hit else 0
                    model_10d_total[mid] += 1
                    col += 2
        elif len(row) == 14:
            # Old format: one row per model
            mid = row[3]  # model_id column
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
        # Demote champion
        old_champ = dict(assumptions["champion"])
        old_champ["weight"] = 0.7
        old_champ["demoted_on"] = TODAY
        if "promoted_on" in old_champ:
            del old_champ["promoted_on"]

        # Promote challenger
        new_champ = dict(c)
        new_champ["weight"] = 1.0
        new_champ["promoted_on"] = TODAY

        # Swap
        assumptions["champion"] = new_champ
        remaining = [ch for ch in assumptions["challengers"] if ch["id"] != c["id"]]
        remaining.append(old_champ)
        assumptions["challengers"] = remaining

        # Record in champion history
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
today_date = date(2026, 11, 1)

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

# Check if we need replacements (maintain 5 challengers)
while len(assumptions["challengers"]) < 5:
    print("  Generating replacement challenger...")
    # This shouldn't trigger today since no retirements expected
    pass

print(f"\n  Active challengers: {len(assumptions['challengers'])}")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION FOR NOVEMBER 1, 2026
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Data collection for {TODAY}")
print("=" * 78)

# Tonight's games (Sunday Nov 1):
# NBA: 4 games
# NHL: 5 games
# NFL: Week 8 Sunday (not tracked in this system)

games_tonight = []

# ── NBA GAMES ─────────────────────────────────────────────────────────

# Game 1: Boston Celtics at Orlando Magic (3:30 PM ET)
# BOS ~6-1 early season powerhouse, ORL ~3-4 good defense
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Orlando Magic", "season_ppg": 107.2, "season_opp_ppg": 105.8,
        "last10_ppg": 106.5, "last10_opp_ppg": 106.2,
        "season_pace": 96.4, "home_record_pct": 0.60, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Boston Celtics", "season_ppg": 119.3, "season_opp_ppg": 108.4,
        "last10_ppg": 120.1, "last10_opp_ppg": 107.8,
        "season_pace": 100.2, "home_record_pct": 0.80, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 6.5, "ml_home": 205, "ml_away": -250, "total": 222.5, "book": "FanDuel"},
})

# Game 2: Brooklyn Nets at Indiana Pacers (5:00 PM ET)
# BKN 0-6 worst in league, IND 2-4 missing Haliburton
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Indiana Pacers", "season_ppg": 115.4, "season_opp_ppg": 118.2,
        "last10_ppg": 114.8, "last10_opp_ppg": 117.5,
        "season_pace": 103.5, "home_record_pct": 0.50, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Brooklyn Nets", "season_ppg": 103.8, "season_opp_ppg": 115.3,
        "last10_ppg": 102.5, "last10_opp_ppg": 116.1,
        "season_pace": 97.8, "home_record_pct": 0.00, "away_record_pct": 0.00,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -3.5, "ml_home": -170, "ml_away": 143, "total": 229.5, "book": "DraftKings"},
})

# Game 3: LA Clippers at Golden State Warriors (8:30 PM ET)
# GSW ~4-3, Curry questionable/out. LAC ~3-4
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Golden State Warriors", "season_ppg": 111.5, "season_opp_ppg": 108.3,
        "last10_ppg": 110.2, "last10_opp_ppg": 109.1,
        "season_pace": 99.1, "home_record_pct": 0.75, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Los Angeles Clippers", "season_ppg": 108.4, "season_opp_ppg": 110.7,
        "last10_ppg": 107.8, "last10_opp_ppg": 111.3,
        "season_pace": 97.2, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -2.0, "ml_home": -126, "ml_away": 108, "total": 219.5, "book": "FanDuel"},
})

# Game 4: Toronto Raptors at LA Lakers (9:00 PM ET)
# LAL ~4-3, TOR ~2-5 rebuilding
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Los Angeles Lakers", "season_ppg": 114.1, "season_opp_ppg": 111.5,
        "last10_ppg": 113.4, "last10_opp_ppg": 112.2,
        "season_pace": 100.4, "home_record_pct": 0.75, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Toronto Raptors", "season_ppg": 106.2, "season_opp_ppg": 113.4,
        "last10_ppg": 105.8, "last10_opp_ppg": 114.1,
        "season_pace": 98.3, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -3.5, "ml_home": -175, "ml_away": 148, "total": 227.5, "book": "FanDuel"},
})

# ── NHL GAMES ─────────────────────────────────────────────────────────

# Game 5: Winnipeg Jets at Carolina Hurricanes (1:00 PM ET)
# WPG 9-3-0 (hot), CAR 8-4-0 (strong home). Neither on B2B.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Carolina Hurricanes", "season_ppg": 3.50, "season_opp_ppg": 2.50,
        "last10_ppg": 3.60, "last10_opp_ppg": 2.40,
        "season_pace": 1.0, "home_record_pct": 0.83, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Winnipeg Jets", "season_ppg": 3.75, "season_opp_ppg": 2.58,
        "last10_ppg": 3.80, "last10_opp_ppg": 2.50,
        "season_pace": 1.0, "home_record_pct": 0.83, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -285, "ml_away": 225, "total": 6.5, "book": "Yahoo"},
})

# Game 6: Minnesota Wild at Washington Capitals (3:30 PM ET)
# MIN 6-5-1, WSH 7-4-1. Pick 'em.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Washington Capitals", "season_ppg": 3.17, "season_opp_ppg": 2.83,
        "last10_ppg": 3.20, "last10_opp_ppg": 2.90,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Minnesota Wild", "season_ppg": 3.00, "season_opp_ppg": 2.83,
        "last10_ppg": 2.90, "last10_opp_ppg": 2.70,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -110, "ml_away": -110, "total": 6.0, "book": "FanDuel"},
})

# Game 7: Utah Hockey Club at Philadelphia Flyers (4:00 PM ET)
# Utah 5-6-1, PHI 4-7-1. Utah slight road fav.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Philadelphia Flyers", "season_ppg": 2.58, "season_opp_ppg": 3.33,
        "last10_ppg": 2.50, "last10_opp_ppg": 3.40,
        "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Utah Hockey Club", "season_ppg": 2.83, "season_opp_ppg": 3.08,
        "last10_ppg": 2.90, "last10_opp_ppg": 3.00,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": 1.5, "ml_home": 120, "ml_away": -140, "total": 6.0, "book": "estimated"},
})

# Game 8: Edmonton Oilers at NY Rangers (6:00 PM ET)
# EDM 10-2-2 (McDavid 14-game point streak). B2B for Edmonton!
# NYR 6-5-1 at home.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "New York Rangers", "season_ppg": 3.00, "season_opp_ppg": 2.83,
        "last10_ppg": 3.10, "last10_opp_ppg": 2.80,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.40,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Edmonton Oilers", "season_ppg": 3.79, "season_opp_ppg": 2.43,
        "last10_ppg": 3.90, "last10_opp_ppg": 2.30,
        "season_pace": 1.0, "home_record_pct": 0.86, "away_record_pct": 0.71,
        "is_back_to_back": True, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -128, "ml_away": 107, "total": 6.5, "book": "TheSpread"},
})

# Game 9: Ottawa Senators at Anaheim Ducks (8:00 PM ET)
# OTT 7-4-1, ANA 4-7-1. Ottawa B2B (played Oct 31 at SJ).
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Anaheim Ducks", "season_ppg": 2.50, "season_opp_ppg": 3.25,
        "last10_ppg": 2.40, "last10_opp_ppg": 3.30,
        "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Ottawa Senators", "season_ppg": 3.25, "season_opp_ppg": 2.67,
        "last10_ppg": 3.30, "last10_opp_ppg": 2.70,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
        "is_back_to_back": True, "key_injuries": 0
    },
    "odds": {"spread_home": 1.5, "ml_home": -102, "ml_away": -118, "total": 6.5, "book": "Yahoo"},
})

# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — RUN SIMULATIONS
# ═══════════════════════════════════════════════════════════════════════

print(f"\n" + "=" * 78)
print(f" PHASE 3 — Running simulations ({len(games_tonight)} games x 6 models)")
print("=" * 78)

# Build batch
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

# Organize results by game
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
    "context": (f"Sunday Nov 1: 4 NBA + 5 NHL = 9 games. Champion: {assumptions['champion']['id']}. "
                f"Oct 31 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
                f"Key: EDM B2B at NYR, OTT B2B at ANA, BOS at ORL, Curry status for GSW vs LAC. "
                f"NFL Week 8 Sunday slate ongoing (not tracked)."),
    "note": "Odds sourced from FanDuel, DraftKings, Yahoo Sports, TheSpread, BetMGM, Covers.",
    "games": [],
}

champion_weight = 1.0

for game in games_tonight:
    home_name = game["home_stats"]["name"]
    away_name = game["away_stats"]["name"]
    results = game_results[home_name]

    # Compute blended prediction
    total_weight = champion_weight
    blended_home_prob = results[assumptions["champion"]["id"]]["home_win_prob"] * champion_weight
    blended_ev_list = []

    for c in assumptions["challengers"]:
        w = c["weight"]
        total_weight += w
        blended_home_prob += results[c["id"]]["home_win_prob"] * w

    blended_home_prob /= total_weight
    blended_away_prob = 1.0 - blended_home_prob

    # Calculate blended expected margin
    total_weight2 = champion_weight
    blended_margin = results[assumptions["champion"]["id"]]["expected_margin"] * champion_weight
    for c in assumptions["challengers"]:
        total_weight2 += c["weight"]
        blended_margin += results[c["id"]]["expected_margin"] * c["weight"]
    blended_margin /= total_weight2

    # Find best EV across all bet types
    best_ev = -999
    best_bet = None
    worst_ev = 999
    best_model_ev = -999
    worst_model_ev = 999

    for model in all_models:
        r = results[model["id"]]
        for ev_key in ["ml_ev_home", "ml_ev_away", "spread_ev_home", "spread_ev_away"]:
            ev = r[ev_key]
            if ev > best_model_ev:
                best_model_ev = ev

    # Blended EV (weighted average of each model's best EV)
    blended_best_ev = 0
    total_w = 0
    worst_model_best_ev = 999

    for model in all_models:
        w = champion_weight if model["id"] == assumptions["champion"]["id"] else \
            next(c["weight"] for c in assumptions["challengers"] if c["id"] == model["id"])
        r = results[model["id"]]
        model_best_ev = max(r["ml_ev_home"], r["ml_ev_away"], r["spread_ev_home"], r["spread_ev_away"])
        model_best_bet = max(
            [("ml_ev_home", r["ml_ev_home"]), ("ml_ev_away", r["ml_ev_away"]),
             ("spread_ev_home", r["spread_ev_home"]), ("spread_ev_away", r["spread_ev_away"])],
            key=lambda x: x[1]
        )
        blended_best_ev += model_best_ev * w
        total_w += w
        if model_best_ev < worst_model_best_ev:
            worst_model_best_ev = model_best_ev

    blended_best_ev /= total_w

    # Find best bet type from champion model
    champ_r = results[assumptions["champion"]["id"]]
    best_bet_options = [
        ("ml_ev_home", champ_r["ml_ev_home"]), ("ml_ev_away", champ_r["ml_ev_away"]),
        ("spread_ev_home", champ_r["spread_ev_home"]), ("spread_ev_away", champ_r["spread_ev_away"])
    ]
    best_bet = max(best_bet_options, key=lambda x: x[1])[0]

    # Robustness: how many models agree on the same ML side
    home_votes = sum(1 for m in all_models if results[m["id"]]["home_win_prob"] > 0.5)
    away_votes = len(all_models) - home_votes
    robustness = max(home_votes, away_votes)

    # Verdict
    if blended_best_ev > 0.03 and robustness >= 4 and worst_model_best_ev > 0:
        verdict = "BET"
    elif blended_best_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Kelly criterion (half-Kelly)
    if blended_best_ev > 0:
        kelly_half = round(blended_best_ev / 2, 3)
    else:
        kelly_half = 0

    # Build model predictions dict
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
    print(f" {sport_name} — Sunday Nov 1, 2026")
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

        # Determine predicted side
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

    # Detail for BET games
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

# Update metrics
champ = assumptions["champion"]
champ_lt_acc = champ["lifetime_correct"] / champ["lifetime_games"] if champ["lifetime_games"] > 0 else 0

# Update all-time totals
metrics["all_time"]["total_games"] = champ["lifetime_games"]
metrics["all_time"]["total_correct"] = champ["lifetime_correct"]
metrics["all_time"]["accuracy"] = round(champ_lt_acc, 4)

# Count today's bets
bets_rec = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "BET")
leans = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "LEAN")
no_bets = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "NO BET")

# Update rolling 7d and 30d from results.tsv
cutoff_7d = (datetime(2026, 11, 1) - timedelta(days=7)).strftime("%Y-%m-%d")
cutoff_30d = (datetime(2026, 11, 1) - timedelta(days=30)).strftime("%Y-%m-%d")

correct_7d = 0
total_7d = 0
correct_30d = 0
total_30d = 0

# Find champion's model_id for old-format lookup
current_champion_id = assumptions["champion"]["id"]

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]

        if len(row) == 18:
            # New format: champion is first model at col 6
            # But champion may have changed — find correct column
            champ_idx = MODEL_ORDER.index(current_champion_id) if current_champion_id in MODEL_ORDER else 0
            col = 6 + champ_idx * 2
            hit = row[col] == "True" if col < len(row) else False
        elif len(row) == 14:
            # Old format: only count rows for the current champion
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
    "note": (f"Updated with Oct 31 eval: {total_correct_blended}/{total_games} ML "
             f"({blended_acc:.1%}). Upsets: NOP blew out ATL (121-99), NSH beat TBL in SO. "
             f"Wemby 43 for SAS. MEM stays unbeaten at 6-0."),
}

metrics["rolling_30d"] = {
    "accuracy": round(acc_30d, 4),
    "ev_realized": round(acc_30d * 0.91 - (1 - acc_30d), 4),
    "total_games": total_30d,
    "total_correct": correct_30d,
    "note": "30+ days of NBA+NHL data."
}

# Update variant performance
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
    "notes": (f"Oct 31 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
              f"Tonight: 4 NBA + 5 NHL = 9 games. Sunday thin slate. "
              f"Key: EDM B2B at NYR, OTT B2B at ANA, Curry status for GSW."),
}

# Save updated files
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# Print dashboard
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
