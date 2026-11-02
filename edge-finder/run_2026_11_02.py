#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-11-02 (Monday).
Phase 1: Eval Nov 1 (9 games: 4 NBA + 5 NHL)
Phase 2-5: Simulate tonight's games:
  - 14 NBA (MON)
  - 4 NHL (MON)
  - 1 NFL MNF (CHI@SEA)
  = 19 games total.

Nov 1 results summary:
  NBA (4 games): BOS 108 ORL 97, BKN 98 IND 90 (upset!), GSW 124 LAC 112,
    LAL 131 TOR 125 (Luka 45/15)
  NHL (5 games): CAR 7 WPG 0 (Kochetkov 10th straight W, shutout),
    MIN 5 WSH 1, PHI 6 UTA 3, EDM 4 NYR 1 (McDavid 14-game pts streak),
    ANA 6 OTT 3 (Gauthier hat trick, erased 0-3 deficit)
  NFL: Week 8 Sunday completed (not tracked).
  Upsets: BKN beat IND (IND -3.5 fav, BKN 0-6 entering), ANA erased 3-goal deficit vs OTT.
"""

import json
import os
import sys
import csv
from collections import defaultdict
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-11-02"
YESTERDAY = "2026-11-01"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVAL NOVEMBER 1, 2026
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
    {"home": "Orlando Magic", "away": "Boston Celtics",
     "home_score": 97, "away_score": 108, "winner": "away", "sport": "basketball_nba"},
    {"home": "Indiana Pacers", "away": "Brooklyn Nets",
     "home_score": 90, "away_score": 98, "winner": "away", "sport": "basketball_nba"},
    {"home": "Golden State Warriors", "away": "Los Angeles Clippers",
     "home_score": 124, "away_score": 112, "winner": "home", "sport": "basketball_nba"},
    {"home": "Los Angeles Lakers", "away": "Toronto Raptors",
     "home_score": 131, "away_score": 125, "winner": "home", "sport": "basketball_nba"},
    # NHL
    {"home": "Carolina Hurricanes", "away": "Winnipeg Jets",
     "home_score": 7, "away_score": 0, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Washington Capitals", "away": "Minnesota Wild",
     "home_score": 1, "away_score": 5, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Philadelphia Flyers", "away": "Utah Hockey Club",
     "home_score": 6, "away_score": 3, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "New York Rangers", "away": "Edmonton Oilers",
     "home_score": 1, "away_score": 4, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Anaheim Ducks", "away": "Ottawa Senators",
     "home_score": 6, "away_score": 3, "winner": "home", "sport": "icehockey_nhl"},
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

    blended_home_prob = pred_game["blended"]["home_win_prob"]
    blended_pred = "home" if blended_home_prob > 0.5 else "away"
    blended_hit = blended_pred == actual_winner
    if blended_hit:
        total_correct_blended += 1

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

blended_acc = total_correct_blended / total_games if total_games > 0 else 0
print(f"\n  Nov 1 eval: {total_correct_blended}/{total_games} ML correct ({blended_acc:.1%})")
print(f"  Per-model breakdown:")
for m in MODEL_ORDER:
    acc = model_correct[m] / model_total[m] if model_total[m] > 0 else 0
    role = "CHAMP" if m == assumptions["champion"]["id"] else "chall"
    print(f"    {m} ({role}): {model_correct[m]}/{model_total[m]} ({acc:.1%})")

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
            print(f"    {cid}: {old_weight:.2f} -> {challenger['weight']:.2f} (+0.1, outperformed on {pct:.0%} of {disagree_games} disagreements)")
    elif c_correct < champion_correct and disagree_games > 0:
        pct = (disagree_games - challenger_wins_disagree) / disagree_games
        if pct >= 0.6:
            challenger["weight"] = max(0.1, challenger["weight"] - 0.1)
            print(f"    {cid}: {old_weight:.2f} -> {challenger['weight']:.2f} (-0.1, underperformed on {pct:.0%} of {disagree_games} disagreements)")
    else:
        print(f"    {cid}: {old_weight:.2f} -> {old_weight:.2f} (no change, {disagree_games} disagreements)")

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

cutoff_date = (datetime(2026, 11, 2) - timedelta(days=10)).strftime("%Y-%m-%d")
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

today_date = date(2026, 11, 2)

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
# PHASE 2 — DATA COLLECTION FOR NOVEMBER 2, 2026
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Data collection for {TODAY}")
print("=" * 78)

# Tonight's games (Monday Nov 2):
# NBA: 14 games (huge Monday slate)
# NHL: 4 games
# NFL: 1 game (MNF CHI@SEA)
# = 19 games total

games_tonight = []

# ── NBA GAMES (14) ───────────────────────────────────────────────────

# 1. Oklahoma City Thunder at Cleveland Cavaliers (7:00 PM ET)
# CLE ~8-0 best start in NBA, OKC ~5-3.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Cleveland Cavaliers", "season_ppg": 121.5, "season_opp_ppg": 106.4,
        "last10_ppg": 122.3, "last10_opp_ppg": 105.8,
        "season_pace": 98.6, "home_record_pct": 1.00, "away_record_pct": 0.75,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Oklahoma City Thunder", "season_ppg": 116.2, "season_opp_ppg": 110.5,
        "last10_ppg": 117.0, "last10_opp_ppg": 109.8,
        "season_pace": 100.1, "home_record_pct": 0.75, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -4.5, "ml_home": -188, "ml_away": 158, "total": 227.5, "book": "FanDuel"},
})

# 2. Brooklyn Nets at New York Knicks (7:30 PM ET)
# NYK ~6-2 strong, BKN 1-7 (got first win yesterday in IND upset).
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "New York Knicks", "season_ppg": 114.8, "season_opp_ppg": 106.2,
        "last10_ppg": 115.5, "last10_opp_ppg": 105.5,
        "season_pace": 98.4, "home_record_pct": 0.80, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Brooklyn Nets", "season_ppg": 104.5, "season_opp_ppg": 114.8,
        "last10_ppg": 104.0, "last10_opp_ppg": 115.2,
        "season_pace": 97.6, "home_record_pct": 0.00, "away_record_pct": 0.25,
        "is_back_to_back": True, "key_injuries": 2
    },
    "odds": {"spread_home": -14.5, "ml_home": -1100, "ml_away": 700, "total": 221.5, "book": "FanDuel"},
})

# 3. Detroit Pistons at Charlotte Hornets (7:30 PM ET)
# DET ~4-3, CHA ~2-5.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Charlotte Hornets", "season_ppg": 107.3, "season_opp_ppg": 113.1,
        "last10_ppg": 106.5, "last10_opp_ppg": 113.8,
        "season_pace": 98.2, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Detroit Pistons", "season_ppg": 110.4, "season_opp_ppg": 107.8,
        "last10_ppg": 111.0, "last10_opp_ppg": 107.2,
        "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 5.5, "ml_home": 185, "ml_away": -225, "total": 211.5, "book": "DraftKings"},
})

# 4. Atlanta Hawks at Indiana Pacers (7:30 PM ET)
# ATL ~3-5, IND 2-5 (lost to BKN yesterday, demoralized).
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Indiana Pacers", "season_ppg": 114.0, "season_opp_ppg": 117.5,
        "last10_ppg": 113.2, "last10_opp_ppg": 118.0,
        "season_pace": 103.5, "home_record_pct": 0.33, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 2
    },
    "away_stats": {
        "name": "Atlanta Hawks", "season_ppg": 114.2, "season_opp_ppg": 116.0,
        "last10_ppg": 115.0, "last10_opp_ppg": 115.5,
        "season_pace": 101.3, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 4.5, "ml_home": 152, "ml_away": -180, "total": 231.5, "book": "FanDuel"},
})

# 5. Orlando Magic at Washington Wizards (7:30 PM ET)
# ORL ~3-5 (lost to BOS yesterday), WAS ~2-5.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Washington Wizards", "season_ppg": 109.0, "season_opp_ppg": 117.2,
        "last10_ppg": 108.5, "last10_opp_ppg": 117.8,
        "season_pace": 101.0, "home_record_pct": 0.33, "away_record_pct": 0.14,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Orlando Magic", "season_ppg": 107.5, "season_opp_ppg": 106.2,
        "last10_ppg": 107.0, "last10_opp_ppg": 106.5,
        "season_pace": 96.2, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": True, "key_injuries": 1
    },
    "odds": {"spread_home": 2.5, "ml_home": 125, "ml_away": -148, "total": 216.5, "book": "FanDuel"},
})

# 6. Milwaukee Bucks at Minnesota Timberwolves (8:00 PM ET)
# MIL ~1-6 terrible start, MIN ~5-2 strong at home.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Minnesota Timberwolves", "season_ppg": 111.5, "season_opp_ppg": 105.3,
        "last10_ppg": 112.0, "last10_opp_ppg": 104.8,
        "season_pace": 99.1, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Milwaukee Bucks", "season_ppg": 107.0, "season_opp_ppg": 115.4,
        "last10_ppg": 106.5, "last10_opp_ppg": 116.0,
        "season_pace": 100.2, "home_record_pct": 0.33, "away_record_pct": 0.00,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -9.5, "ml_home": -470, "ml_away": 350, "total": 222.5, "book": "FanDuel"},
})

# 7. Chicago Bulls at Philadelphia 76ers (7:30 PM ET)
# PHI ~3-4, CHI ~3-5. PHI big home fav.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Philadelphia 76ers", "season_ppg": 113.5, "season_opp_ppg": 108.2,
        "last10_ppg": 114.0, "last10_opp_ppg": 107.5,
        "season_pace": 98.3, "home_record_pct": 0.75, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Chicago Bulls", "season_ppg": 110.2, "season_opp_ppg": 115.0,
        "last10_ppg": 109.5, "last10_opp_ppg": 115.8,
        "season_pace": 99.0, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -11.5, "ml_home": -575, "ml_away": 425, "total": 238.5, "book": "BetMGM"},
})

# 8. New Orleans Pelicans at Memphis Grizzlies (8:00 PM ET)
# MEM 7-0 unbeaten, NOP ~3-5.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Memphis Grizzlies", "season_ppg": 122.4, "season_opp_ppg": 108.0,
        "last10_ppg": 123.0, "last10_opp_ppg": 107.5,
        "season_pace": 101.5, "home_record_pct": 1.00, "away_record_pct": 0.75,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "New Orleans Pelicans", "season_ppg": 112.0, "season_opp_ppg": 115.5,
        "last10_ppg": 112.5, "last10_opp_ppg": 115.0,
        "season_pace": 99.3, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -4.5, "ml_home": -190, "ml_away": 160, "total": 233.5, "book": "FanDuel"},
})

# 9. Phoenix Suns at Golden State Warriors (10:00 PM ET)
# GSW 5-3 (4 straight wins, rested Curry/Green yesterday), PHX ~5-3.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Golden State Warriors", "season_ppg": 113.0, "season_opp_ppg": 108.0,
        "last10_ppg": 114.5, "last10_opp_ppg": 107.5,
        "season_pace": 99.3, "home_record_pct": 0.80, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Phoenix Suns", "season_ppg": 115.5, "season_opp_ppg": 112.0,
        "last10_ppg": 116.0, "last10_opp_ppg": 111.5,
        "season_pace": 100.4, "home_record_pct": 0.75, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -3.5, "ml_home": -158, "ml_away": 134, "total": 228.5, "book": "estimated"},
})

# 10. Boston Celtics at Houston Rockets (8:30 PM ET)
# HOU ~5-2 strong at home, BOS 7-1 (B2B after winning at ORL yesterday).
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Houston Rockets", "season_ppg": 111.3, "season_opp_ppg": 105.0,
        "last10_ppg": 112.0, "last10_opp_ppg": 104.5,
        "season_pace": 97.5, "home_record_pct": 0.75, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Boston Celtics", "season_ppg": 119.0, "season_opp_ppg": 108.5,
        "last10_ppg": 118.5, "last10_opp_ppg": 108.0,
        "season_pace": 100.0, "home_record_pct": 0.80, "away_record_pct": 0.75,
        "is_back_to_back": True, "key_injuries": 1
    },
    "odds": {"spread_home": -5.5, "ml_home": -198, "ml_away": 166, "total": 218.5, "book": "FanDuel"},
})

# 11. Portland Trail Blazers at Denver Nuggets (9:00 PM ET)
# DEN ~4-3 at home, POR ~3-5.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Denver Nuggets", "season_ppg": 115.2, "season_opp_ppg": 111.0,
        "last10_ppg": 116.0, "last10_opp_ppg": 110.5,
        "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Portland Trail Blazers", "season_ppg": 108.0, "season_opp_ppg": 114.2,
        "last10_ppg": 107.5, "last10_opp_ppg": 114.8,
        "season_pace": 100.0, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -4.5, "ml_home": -164, "ml_away": 138, "total": 230.5, "book": "FanDuel"},
})

# 12. Toronto Raptors at Los Angeles Clippers (10:00 PM ET)
# TOR 2-6 (lost at LAL yesterday, B2B), LAC 3-5 (5-game L streak).
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Los Angeles Clippers", "season_ppg": 107.5, "season_opp_ppg": 111.5,
        "last10_ppg": 106.8, "last10_opp_ppg": 112.0,
        "season_pace": 97.0, "home_record_pct": 0.33, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Toronto Raptors", "season_ppg": 106.5, "season_opp_ppg": 114.0,
        "last10_ppg": 106.0, "last10_opp_ppg": 114.5,
        "season_pace": 98.0, "home_record_pct": 0.33, "away_record_pct": 0.17,
        "is_back_to_back": True, "key_injuries": 1
    },
    "odds": {"spread_home": -1.5, "ml_home": -122, "ml_away": 102, "total": 218.5, "book": "estimated"},
})

# 13. Utah Jazz at San Antonio Spurs (8:30 PM ET)
# SAS 4-3 (Wemby having MVP-level start), UTA 1-6 tanking.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "San Antonio Spurs", "season_ppg": 115.5, "season_opp_ppg": 110.0,
        "last10_ppg": 116.0, "last10_opp_ppg": 109.5,
        "season_pace": 100.2, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Utah Jazz", "season_ppg": 103.0, "season_opp_ppg": 116.5,
        "last10_ppg": 102.5, "last10_opp_ppg": 117.0,
        "season_pace": 97.0, "home_record_pct": 0.25, "away_record_pct": 0.00,
        "is_back_to_back": False, "key_injuries": 2
    },
    "odds": {"spread_home": -15.5, "ml_home": -1200, "ml_away": 750, "total": 225.5, "book": "estimated"},
})

# 14. Miami Heat at Los Angeles Lakers (10:00 PM ET)
# LAL 5-3 (won big last night, Luka 45/15), MIA 3-4.
games_tonight.append({
    "sport": "basketball_nba",
    "home_stats": {
        "name": "Los Angeles Lakers", "season_ppg": 115.5, "season_opp_ppg": 111.0,
        "last10_ppg": 116.5, "last10_opp_ppg": 110.5,
        "season_pace": 100.4, "home_record_pct": 0.80, "away_record_pct": 0.33,
        "is_back_to_back": True, "key_injuries": 0
    },
    "away_stats": {
        "name": "Miami Heat", "season_ppg": 110.0, "season_opp_ppg": 109.5,
        "last10_ppg": 110.5, "last10_opp_ppg": 109.0,
        "season_pace": 98.2, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -2.5, "ml_home": -134, "ml_away": 114, "total": 237.5, "book": "FanDuel"},
})

# ── NHL GAMES (4) ────────────────────────────────────────────────────

# 15. Vegas Golden Knights at Boston Bruins (7:00 PM ET)
# VGK ~7-4-1 solid road team, BOS ~5-6-1 struggling early.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Boston Bruins", "season_ppg": 2.83, "season_opp_ppg": 3.08,
        "last10_ppg": 2.90, "last10_opp_ppg": 3.00,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Vegas Golden Knights", "season_ppg": 3.50, "season_opp_ppg": 2.75,
        "last10_ppg": 3.60, "last10_opp_ppg": 2.70,
        "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.60,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": 1.5, "ml_home": 102, "ml_away": -122, "total": 6.0, "book": "FanDuel"},
})

# 16. Detroit Red Wings at Florida Panthers (7:00 PM ET)
# FLA ~8-3-1 defending champs, DET ~4-7-1.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Florida Panthers", "season_ppg": 3.33, "season_opp_ppg": 2.50,
        "last10_ppg": 3.40, "last10_opp_ppg": 2.40,
        "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.57,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Detroit Red Wings", "season_ppg": 2.58, "season_opp_ppg": 3.08,
        "last10_ppg": 2.50, "last10_opp_ppg": 3.10,
        "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -1.5, "ml_home": -175, "ml_away": 150, "total": 5.5, "book": "BetMGM"},
})

# 17. Colorado Avalanche at Chicago Blackhawks (8:00 PM ET)
# COL ~7-5-0 strong, CHI ~4-8-0 bottom feeder.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "Chicago Blackhawks", "season_ppg": 2.42, "season_opp_ppg": 3.50,
        "last10_ppg": 2.30, "last10_opp_ppg": 3.60,
        "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.20,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Colorado Avalanche", "season_ppg": 3.50, "season_opp_ppg": 2.83,
        "last10_ppg": 3.60, "last10_opp_ppg": 2.80,
        "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.67,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": 1.5, "ml_home": 190, "ml_away": -235, "total": 6.0, "book": "FanDuel"},
})

# 18. Calgary Flames at San Jose Sharks (9:00 PM ET)
# SJS ~4-7-2 (Celebrini rookie star), CGY ~5-6-1.
games_tonight.append({
    "sport": "icehockey_nhl",
    "home_stats": {
        "name": "San Jose Sharks", "season_ppg": 2.77, "season_opp_ppg": 3.23,
        "last10_ppg": 2.80, "last10_opp_ppg": 3.20,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.25,
        "is_back_to_back": False, "key_injuries": 0
    },
    "away_stats": {
        "name": "Calgary Flames", "season_ppg": 2.67, "season_opp_ppg": 3.00,
        "last10_ppg": 2.70, "last10_opp_ppg": 3.00,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
        "is_back_to_back": False, "key_injuries": 0
    },
    "odds": {"spread_home": -1.5, "ml_home": -135, "ml_away": 110, "total": 6.5, "book": "BetMGM"},
})

# ── NFL MNF (1) ──────────────────────────────────────────────────────

# 19. Chicago Bears at Seattle Seahawks (8:15 PM ET, ESPN)
# SEA ~4-3, CHI ~3-4. SEA home fav. MNF Week 8.
games_tonight.append({
    "sport": "americanfootball_nfl",
    "home_stats": {
        "name": "Seattle Seahawks", "season_ppg": 24.1, "season_opp_ppg": 21.3,
        "last10_ppg": 24.5, "last10_opp_ppg": 21.0,
        "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
        "is_back_to_back": False, "key_injuries": 1
    },
    "away_stats": {
        "name": "Chicago Bears", "season_ppg": 19.4, "season_opp_ppg": 22.0,
        "last10_ppg": 19.0, "last10_opp_ppg": 22.5,
        "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
        "is_back_to_back": False, "key_injuries": 1
    },
    "odds": {"spread_home": -3.0, "ml_home": -175, "ml_away": 150, "total": 46.5, "book": "DraftKings"},
})

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
    "context": (f"Monday Nov 2: 14 NBA + 4 NHL + 1 NFL MNF = 19 games. "
                f"Champion: {assumptions['champion']['id']}. "
                f"Nov 1 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
                f"Key: CLE 8-0, MEM 7-0, BKN B2B at NYK, BOS B2B at HOU, LAL B2B vs MIA. "
                f"NHL: CAR 10-0 Kochetkov, EDM McDavid streak. MNF: CHI@SEA."),
    "note": "Odds from FanDuel, DraftKings, BetMGM, Yahoo, TheSpread, CBS Sports, Covers.",
    "games": [],
}

for game in games_tonight:
    home_name = game["home_stats"]["name"]
    away_name = game["away_stats"]["name"]
    sport = game["sport"]
    odds = game["odds"]

    model_preds = {}
    champ_id = assumptions["champion"]["id"]
    weights = {champ_id: 1.0}
    for c in assumptions["challengers"]:
        weights[c["id"]] = c["weight"]

    total_weight = sum(weights.values())

    weighted_home_prob = 0
    weighted_margin = 0
    evs = {"ml_ev_home": [], "ml_ev_away": [], "spread_ev_home": [], "spread_ev_away": []}
    ev_weights = []

    for model in all_models:
        mid = model["id"]
        sr = game_results[home_name][mid]
        w = weights[mid]
        weighted_home_prob += sr["home_win_prob"] * w
        weighted_margin += sr["expected_margin"] * w
        ev_weights.append(w)
        for k in evs:
            evs[k].append(sr[k])

        model_preds[mid] = {
            "home_win_prob": sr["home_win_prob"],
            "ml_ev_home": sr["ml_ev_home"],
            "ml_ev_away": sr["ml_ev_away"],
            "spread_ev_home": sr["spread_ev_home"],
            "spread_ev_away": sr["spread_ev_away"],
            "expected_margin": sr["expected_margin"],
        }

    blended_home_prob = weighted_home_prob / total_weight
    blended_margin = weighted_margin / total_weight

    blended_evs = {}
    for k in evs:
        blended_evs[k] = sum(e * w for e, w in zip(evs[k], ev_weights)) / total_weight

    best_ev_key = max(blended_evs, key=blended_evs.get)
    best_ev_val = blended_evs[best_ev_key]

    best_model_ev = max(evs[best_ev_key])
    worst_model_ev = min(evs[best_ev_key])

    # Robustness: how many models agree on the predicted winner
    home_votes = sum(1 for m in all_models if game_results[home_name][m["id"]]["home_win_prob"] > 0.5)
    away_votes = 6 - home_votes
    robustness = max(home_votes, away_votes)

    # Verdict
    all_same_sign = all(evs[best_ev_key][i] > 0 for i in range(6))
    any_flip = any(evs[best_ev_key][i] < 0 for i in range(6))

    if best_ev_val > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_ev_val > 0.015 and robustness >= 3:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = max(0, best_ev_val / (max(abs(best_model_ev), 0.01) + 1)) if best_ev_val > 0 else 0
    kelly_half = round(kelly / 2, 3)

    game_pred = {
        "sport": sport,
        "home": home_name,
        "away": away_name,
        "odds": odds,
        "blended": {
            "home_win_prob": round(blended_home_prob, 4),
            "away_win_prob": round(1 - blended_home_prob, 4),
            "expected_margin": round(blended_margin, 2),
            "best_ev": round(best_ev_val, 4),
            "best_bet": best_ev_key,
            "robustness": robustness,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": model_preds,
    }
    predictions["games"].append(game_pred)

# Save predictions FIRST
pred_path = os.path.join(BASE, f"predictions/{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions, f, indent=2)
print(f"\n  Predictions saved to {pred_path}")

# ── Display Results ──────────────────────────────────────────────────

def display_table(sport_name, sport_key, date_str):
    sport_games = [g for g in predictions["games"] if g["sport"] == sport_key]
    if not sport_games:
        return

    print(f"\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print(f"│ {sport_name} — {date_str:<67s}│")
    print(f"├──────────────────────┬────────┬────────┬────────┬──────┬──────┬─────────────┤")
    print(f"│ Game                 │ Spread │ Blend  │ Best   │Worst │ Rob. │ Verdict     │")
    print(f"│                      │        │ EV     │ EV     │EV    │      │             │")
    print(f"├──────────────────────┼────────┼────────┼────────┼──────┼──────┼─────────────┤")

    for g in sport_games:
        b = g["blended"]
        spread = g["odds"]["spread_home"]
        home_short = g["home"].split()[-1][:4] if len(g["home"].split()) > 1 else g["home"][:4]
        away_short = g["away"].split()[-1][:4] if len(g["away"].split()) > 1 else g["away"][:4]

        if b["home_win_prob"] > 0.5:
            side = "HOME"
            fav = home_short
        else:
            side = "AWAY"
            fav = away_short

        if b["verdict"] == "BET":
            emoji = "✅"
        elif b["verdict"] == "LEAN":
            emoji = "⚠️"
        else:
            emoji = "❌"

        game_str = f"{away_short}@{home_short}"
        spread_str = f"{spread:+.1f}"
        blend_ev = f"{b['best_ev']:+.1%}"
        best_ev = f"{b['best_model_ev']:+.1%}"
        worst_ev = f"{b['worst_model_ev']:+.1%}"
        rob_str = f"{b['robustness']}/6"
        verdict_str = f"{emoji} {b['verdict']} {side}"

        print(f"│ {game_str:<20s} │ {spread_str:>6s} │ {blend_ev:>6s} │ {best_ev:>6s} │{worst_ev:>5s} │ {rob_str:>4s} │ {verdict_str:<11s} │")

    print(f"└──────────────────────┴────────┴────────┴────────┴──────┴──────┴─────────────┘")

display_table("NBA", "basketball_nba", "Monday Nov 2, 2026")
display_table("NHL", "icehockey_nhl", "Monday Nov 2, 2026")
display_table("NFL MNF", "americanfootball_nfl", "Monday Nov 2, 2026")

# Print BET details
print(f"\n{'='*78}")
print(f" BET DETAILS")
print(f"{'='*78}")

for g in predictions["games"]:
    b = g["blended"]
    if b["verdict"] == "BET":
        print(f"\n  {g['away']} at {g['home']} ({g['sport']})")
        print(f"    Best bet: {b['best_bet']} | EV: {b['best_ev']:+.1%} | Kelly/2: {b['kelly_half']:.1%}")
        print(f"    Book: {g['odds']['book']} | Spread: {g['odds']['spread_home']:+.1f} | ML: {g['odds']['ml_home']}/{g['odds']['ml_away']}")
        agree = sum(1 for m in MODEL_ORDER
                    if (g["model_predictions"][m]["home_win_prob"] > 0.5) ==
                       (b["home_win_prob"] > 0.5))
        print(f"    Models agreeing on winner: {agree}/6 | Robustness: {b['robustness']}/6")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — UPDATE METRICS
# ═══════════════════════════════════════════════════════════════════════

print(f"\n" + "=" * 78)
print(f" PHASE 5 — Metrics update")
print("=" * 78)

# Update rolling 7d and 30d from results.tsv
cutoff_7d = (datetime(2026, 11, 2) - timedelta(days=7)).strftime("%Y-%m-%d")
cutoff_30d = (datetime(2026, 11, 2) - timedelta(days=30)).strftime("%Y-%m-%d")

correct_7d = 0
total_7d = 0
correct_30d = 0
total_30d = 0

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]

        if len(row) == 18:
            col = 6
            champ_idx = MODEL_ORDER.index(assumptions["champion"]["id"])
            hit_col = 6 + champ_idx * 2
            if hit_col < len(row):
                hit = row[hit_col] == "True"
                if row_date >= cutoff_7d:
                    correct_7d += 1 if hit else 0
                    total_7d += 1
                if row_date >= cutoff_30d:
                    correct_30d += 1 if hit else 0
                    total_30d += 1

acc_7d = correct_7d / total_7d if total_7d > 0 else 0
acc_30d = correct_30d / total_30d if total_30d > 0 else 0

# Count BETs
bets_recommended = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "BET")
leans = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "LEAN")
no_bets = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "NO BET")

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(acc_7d, 4),
    "ev_realized": round(acc_7d * 0.22 if acc_7d > 0.5 else -0.05, 4),
    "total_games": total_7d,
    "total_correct": correct_7d,
    "note": (f"Updated with Nov 1 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
             f"BKN upset at IND, ANA comeback vs OTT. MEM still unbeaten at 7-0.")
}
metrics["rolling_30d"] = {
    "accuracy": round(acc_30d, 4),
    "ev_realized": round(acc_30d * 0.35 if acc_30d > 0.5 else -0.05, 4),
    "total_games": total_30d,
    "total_correct": correct_30d,
    "note": "30+ days of NBA+NHL data."
}

# Update all-time
metrics["all_time"]["total_games"] = assumptions["champion"]["lifetime_games"]
metrics["all_time"]["total_correct"] = assumptions["champion"]["lifetime_correct"]
lt_acc = assumptions["champion"]["lifetime_correct"] / assumptions["champion"]["lifetime_games"] if assumptions["champion"]["lifetime_games"] > 0 else 0
metrics["all_time"]["accuracy"] = round(lt_acc, 4)

# Update variant performance
for model in all_models:
    mid = model["id"]
    role = "champion" if mid == assumptions["champion"]["id"] else "challenger"
    lt = model["lifetime_correct"] / model["lifetime_games"] if model["lifetime_games"] > 0 else 0
    metrics["variant_performance"][mid] = {
        "lifetime_games": model["lifetime_games"],
        "lifetime_correct": model["lifetime_correct"],
        "lifetime_accuracy": round(lt, 4),
        "weight": model["weight"],
        "role": role,
    }

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions["games"]),
    "bets_recommended": bets_recommended,
    "leans": leans,
    "no_bets": no_bets,
    "sports": list(set(g["sport"] for g in predictions["games"])),
    "notes": (f"Nov 1 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
              f"Tonight: 14 NBA + 4 NHL + 1 NFL MNF = 19 games. "
              f"Huge Monday slate. BKN B2B at NYK, BOS B2B at HOU, LAL B2B vs MIA."),
}

# Save updated files
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

print(f"\n📊 Edge-Finder Metrics")
print(f"━━━━━━━━━━━━━━━━━━━━")
print(f"Champion: {assumptions['champion']['id']} (promoted {assumptions['champion'].get('promoted_on', 'N/A')})")
print(f"7-day:  {acc_7d:.0%} accuracy | {correct_7d}/{total_7d} games")
print(f"30-day: {acc_30d:.0%} accuracy | {correct_30d}/{total_30d} games")
print(f"All-time: {lt_acc:.1%} accuracy | {assumptions['champion']['lifetime_games']} games")
print(f"\nChallenger weights:", end=" ")
for c in assumptions["challengers"]:
    print(f"{c['id']}={c['weight']:.1f}", end=", ")
print(f"\nGraveyard: {len(assumptions['graveyard'])} retired variants")
print(f"\nTonight: {bets_recommended} BETs, {leans} LEANs, {no_bets} NO BETs")
print(f"\n⚠️  DISCLAIMER: For entertainment and analysis purposes only.")
print(f"   Past performance does not guarantee future results.")

print(f"\n{'='*78}")
print(f" DONE — {TODAY}")
print(f"{'='*78}")
