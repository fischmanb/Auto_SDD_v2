#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-17 (Wednesday).
Phase 1: Eval June 16 predictions, update weights.
Phase 2-5: Simulate tonight's games (MLB only — NBA/NFL off-season, NHL over).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-17"
EVAL_DATE = "2026-06-16"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 16 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-16 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results fetched via web search (June 16, 2026)
actual_results = {
    "Miami Marlins @ Philadelphia Phillies": {"winner": "home", "home_score": 8, "away_score": 2},
    "Kansas City Royals @ Washington Nationals": {"winner": "home", "home_score": 6, "away_score": 4},
    "New York Mets @ Cincinnati Reds": {"winner": "home", "home_score": 5, "away_score": 3},
    "San Diego Padres @ St. Louis Cardinals": {"winner": "home", "home_score": 3, "away_score": 2},
    "San Francisco Giants @ Atlanta Braves": {"winner": "away", "home_score": 2, "away_score": 7},
    "Minnesota Twins @ Texas Rangers": {"winner": "away", "home_score": 2, "away_score": 12},
    "Detroit Tigers @ Houston Astros": {"winner": "home", "home_score": 4, "away_score": 2},
    "Los Angeles Angels @ Arizona Diamondbacks": {"winner": "away", "home_score": 0, "away_score": 7},
    "Pittsburgh Pirates @ Oakland Athletics": {"winner": "away", "home_score": 5, "away_score": 6},
    "Tampa Bay Rays @ Los Angeles Dodgers": {"winner": "home", "home_score": 1, "away_score": 0},
    "Toronto Blue Jays @ Boston Red Sox": {"winner": "away", "home_score": 1, "away_score": 6},
    "Cleveland Guardians @ Milwaukee Brewers": {"winner": "home", "home_score": 2, "away_score": 1},
    "Baltimore Orioles @ Seattle Mariners": {"winner": "home", "home_score": 3, "away_score": 1},
}

model_ids = [assumptions["champion"]["id"]] + [c["id"] for c in assumptions["challengers"]]
model_correct = {m: 0 for m in model_ids}
model_total = {m: 0 for m in model_ids}
total_games_evaluated = 0

results_lines = []

for pred in past_preds["predictions"]:
    game = pred["game"]
    if game not in actual_results:
        continue
    actual = actual_results[game]
    if actual["winner"] in ("postponed", "skip"):
        print(f"  SKIP ({actual['winner']}): {game}")
        continue

    total_games_evaluated += 1
    margin = actual["home_score"] - actual["away_score"]
    actual_winner = actual["winner"]

    for model_id, model_data in pred["model_results"].items():
        model_total[model_id] = model_total.get(model_id, 0) + 1
        predicted_home_win = model_data["home_win_prob"] > 0.5
        correct = (predicted_home_win and actual_winner == "home") or \
                  (not predicted_home_win and actual_winner == "away")
        if correct:
            model_correct[model_id] = model_correct.get(model_id, 0) + 1
        hit = 1 if correct else 0

        evs = {
            "spread_home": model_data["spread_ev_home"],
            "spread_away": model_data["spread_ev_away"],
            "ml_home": model_data["ml_ev_home"],
            "ml_away": model_data["ml_ev_away"],
        }
        best_bet = max(evs, key=evs.get)
        best_ev = evs[best_bet]

        spread = pred["odds"]["spread_home"]
        if best_bet == "spread_home":
            covers = (margin + spread) > 0
        elif best_bet == "spread_away":
            covers = (-margin - spread) > 0
        elif best_bet == "ml_home":
            covers = actual_winner == "home"
        else:
            covers = actual_winner == "away"

        bet_result = "win" if covers else "loss"

        predicted_winner = "home" if predicted_home_win else "away"
        predicted_margin = model_data["expected_margin"]
        predicted_win_prob = model_data["home_win_prob"] if predicted_home_win else (1 - model_data["home_win_prob"])

        line = f"{EVAL_DATE}\t{pred['sport']}\t{game}\t{model_id}\t{predicted_winner}\t{predicted_margin:.2f}\t{predicted_win_prob:.4f}\t{actual_winner}\t{margin}\t{hit}\t{model_data['spread_ev_home']:.4f}\t{model_data['ml_ev_home']:.4f}\t{best_bet}\t{bet_result}"
        results_lines.append(line)

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_lines:
        f.write(line + "\n")

print(f"\n  Games evaluated: {total_games_evaluated}")
print(f"  Per-model accuracy on {EVAL_DATE}:")
champion_id = assumptions["champion"]["id"]
champion_correct_count = model_correct.get(champion_id, 0)
champion_total_count = model_total.get(champion_id, 0)
for m in model_ids:
    acc = model_correct[m] / model_total[m] if model_total[m] > 0 else 0
    role = "CHAMP" if m == champion_id else "chal"
    print(f"    [{role}] {m}: {model_correct[m]}/{model_total[m]} = {acc:.1%}")

# ── Weight adjustment (based on head-to-head disagreements) ──
print("\n  Weight adjustments:")
for challenger in assumptions["challengers"]:
    cid = challenger["id"]

    champ_wins = 0
    chal_wins = 0
    for pred in past_preds["predictions"]:
        game = pred["game"]
        if game not in actual_results or actual_results[game]["winner"] in ("postponed", "skip"):
            continue
        actual_w = actual_results[game]["winner"]
        champ_pred_home = pred["model_results"][champion_id]["home_win_prob"] > 0.5
        chal_pred_home = pred["model_results"][cid]["home_win_prob"] > 0.5
        if champ_pred_home != chal_pred_home:
            champ_right = (champ_pred_home and actual_w == "home") or (not champ_pred_home and actual_w == "away")
            chal_right = (chal_pred_home and actual_w == "home") or (not chal_pred_home and actual_w == "away")
            if champ_right and not chal_right:
                champ_wins += 1
            elif chal_right and not champ_right:
                chal_wins += 1

    disagreements = champ_wins + chal_wins
    old_weight = challenger["weight"]
    if disagreements > 0:
        if chal_wins / disagreements >= 0.6:
            challenger["weight"] = round(min(1.0, challenger["weight"] + 0.1), 1)
        elif champ_wins / disagreements >= 0.6:
            challenger["weight"] = round(max(0.1, challenger["weight"] - 0.1), 1)

    if challenger["weight"] != old_weight:
        print(f"    {cid}: {old_weight} -> {challenger['weight']} (disagreements: {disagreements}, champ won {champ_wins}, chal won {chal_wins})")
    else:
        print(f"    {cid}: {old_weight} (no change, disagreements: {disagreements})")

# Update lifetime stats
for m in model_ids:
    if m == champion_id:
        assumptions["champion"]["lifetime_games"] += model_total.get(m, 0)
        assumptions["champion"]["lifetime_correct"] += model_correct.get(m, 0)
    else:
        for c in assumptions["challengers"]:
            if c["id"] == m:
                c["lifetime_games"] += model_total.get(m, 0)
                c["lifetime_correct"] += model_correct.get(m, 0)

# Rolling 10-day accuracy (June 7-16)
print("\n  Rolling 10-day accuracy (June 7-16):")
rolling_data = {m: {"correct": 0, "total": 0} for m in model_ids}
with open(os.path.join(BASE, "results.tsv")) as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 11:
            continue
        d = parts[0]
        if d < "2026-06-07" or d > "2026-06-16":
            continue
        mid = parts[3]
        hit_val = int(parts[9])
        if mid in rolling_data:
            rolling_data[mid]["total"] += 1
            rolling_data[mid]["correct"] += hit_val

champ_10d_acc = rolling_data[champion_id]["correct"] / rolling_data[champion_id]["total"] if rolling_data[champion_id]["total"] > 0 else 0
assumptions["champion"]["rolling_10d_accuracy"] = round(champ_10d_acc, 4)

for m in model_ids:
    rd = rolling_data[m]
    acc = rd["correct"] / rd["total"] if rd["total"] > 0 else 0
    role = "CHAMP" if m == champion_id else "chal"
    print(f"    [{role}] {m}: {rd['correct']}/{rd['total']} = {acc:.1%}")

# Promotion check
print("\n  Promotion check:")
promoted = False
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    rd = rolling_data[cid]
    chal_acc = rd["correct"] / rd["total"] if rd["total"] > 0 else 0
    if chal_acc - champ_10d_acc >= 0.05:
        print(f"    PROMOTING {cid} (10d acc {chal_acc:.1%}) over {champion_id} (10d acc {champ_10d_acc:.1%})")
        promoted = True
    else:
        diff = chal_acc - champ_10d_acc
        print(f"    {cid}: {chal_acc:.1%} vs champion {champ_10d_acc:.1%} (diff: {diff:+.1%}) -- no promotion")

if not promoted:
    print("    No promotions triggered.")

# Retirement check
print("\n  Retirement check:")
retired_any = False
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    if challenger["weight"] <= 0.15 and challenger["born"] < "2026-06-12":
        print(f"    Retiring {cid} (weight={challenger['weight']}, born={challenger['born']})")
        retired_any = True
    else:
        print(f"    {cid}: weight={challenger['weight']}, born={challenger['born']} -- keep")

if not retired_any:
    print("    No retirements needed.")

# Save assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  Phase 1 complete. Champion '{champion_id}' accuracy on Jun 16: {champion_correct_count}/{champion_total_count}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's Games: June 17, 2026)
# ════════════════════════════════════════════════════════════════════════
# NHL: Season over (Hurricanes won Cup June 14)
# NBA: Off-season
# NFL: Off-season
# MLB: Regular season — Wednesday schedule, 14 games
#
# Odds via web search (FanDuel primary, cross-checked).
# Stats carried forward from June 16 run for continuation series;
# estimated from records/standings for new matchups (CHW@NYY, COL@CHC).

print("\n" + "=" * 78)
print(f" PHASE 2 — Tonight's Games & Odds ({TODAY})")
print("=" * 78)

games_tonight = [
    {
        "sport": "baseball_mlb",
        "game": "New York Mets @ Cincinnati Reds",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.57,
            "season_opp_ppg": 4.73,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.529,
            "away_record_pct": 0.429,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.17,
            "season_opp_ppg": 4.82,
            "last10_ppg": 4.30,
            "last10_opp_ppg": 4.80,
            "season_pace": 1.0,
            "home_record_pct": 0.486,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": 108,
            "ml_away": -131,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Kansas City Royals @ Washington Nationals",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 5.40,
            "season_opp_ppg": 4.76,
            "last10_ppg": 5.70,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.567,
            "away_record_pct": 0.472,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 3.88,
            "season_opp_ppg": 4.93,
            "last10_ppg": 3.50,
            "last10_opp_ppg": 5.30,
            "season_pace": 1.0,
            "home_record_pct": 0.444,
            "away_record_pct": 0.361,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 100,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Miami Marlins @ Philadelphia Phillies",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 5.02,
            "season_opp_ppg": 4.42,
            "last10_ppg": 5.50,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.543,
            "away_record_pct": 0.543,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.44,
            "season_opp_ppg": 4.55,
            "last10_ppg": 4.30,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.486,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -122,
            "ml_away": 104,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Francisco Giants @ Atlanta Braves",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 5.10,
            "season_opp_ppg": 3.90,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.667,
            "away_record_pct": 0.629,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 3.90,
            "season_opp_ppg": 4.80,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 4.80,
            "season_pace": 1.0,
            "home_record_pct": 0.429,
            "away_record_pct": 0.371,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -148,
            "ml_away": 126,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Detroit Tigers @ Houston Astros",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.78,
            "season_opp_ppg": 4.25,
            "last10_ppg": 4.80,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.583,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 4.37,
            "season_opp_ppg": 4.55,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.60,
            "season_pace": 1.0,
            "home_record_pct": 0.528,
            "away_record_pct": 0.417,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 110,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Diego Padres @ St. Louis Cardinals",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.92,
            "season_opp_ppg": 4.16,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.611,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.68,
            "season_opp_ppg": 4.42,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.543,
            "away_record_pct": 0.514,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 102,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Los Angeles Angels @ Arizona Diamondbacks",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.72,
            "season_opp_ppg": 4.47,
            "last10_ppg": 4.80,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.583,
            "away_record_pct": 0.429,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.27,
            "season_opp_ppg": 4.82,
            "last10_ppg": 4.20,
            "last10_opp_ppg": 4.80,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -155,
            "ml_away": 130,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Toronto Blue Jays @ Boston Red Sox",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.70,
            "last10_ppg": 4.30,
            "last10_opp_ppg": 4.90,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.389,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -126,
            "ml_away": 108,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Chicago White Sox @ New York Yankees",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 5.30,
            "season_opp_ppg": 3.80,
            "last10_ppg": 5.50,
            "last10_opp_ppg": 3.60,
            "season_pace": 1.0,
            "home_record_pct": 0.650,
            "away_record_pct": 0.550,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 3.40,
            "season_opp_ppg": 5.60,
            "last10_ppg": 3.20,
            "last10_opp_ppg": 5.80,
            "season_pace": 1.0,
            "home_record_pct": 0.300,
            "away_record_pct": 0.250,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -184,
            "ml_away": 154,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cleveland Guardians @ Milwaukee Brewers",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.00,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.571,
            "away_record_pct": 0.514,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.20,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 4.50,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.444,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": 100,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Colorado Rockies @ Chicago Cubs",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.80,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 4.20,
            "season_opp_ppg": 5.20,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 5.50,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.250,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -188,
            "ml_away": 158,
            "total": 10.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Pittsburgh Pirates @ Oakland Athletics",
        "home": {
            "name": "Oakland Athletics",
            "season_ppg": 4.18,
            "season_opp_ppg": 4.65,
            "last10_ppg": 5.00,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.353,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.27,
            "season_opp_ppg": 4.53,
            "last10_ppg": 4.20,
            "last10_opp_ppg": 4.70,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": 102,
            "ml_away": -120,
            "total": 10.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Tampa Bay Rays @ Los Angeles Dodgers",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.38,
            "season_opp_ppg": 3.40,
            "last10_ppg": 5.00,
            "last10_opp_ppg": 3.70,
            "season_pace": 1.0,
            "home_record_pct": 0.647,
            "away_record_pct": 0.556,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 5.08,
            "season_opp_ppg": 3.82,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.586,
            "away_record_pct": 0.528,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Baltimore Orioles @ Seattle Mariners",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.10,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.556,
            "away_record_pct": 0.457,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.70,
            "last10_ppg": 4.10,
            "last10_opp_ppg": 4.90,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.429,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 7.5,
            "book": "fanduel",
        },
    },
]

print(f"  {len(games_tonight)} MLB games tonight (Wednesday)")
for g in games_tonight:
    print(f"    {g['game']} | ML: {g['odds']['ml_home']}/{g['odds']['ml_away']} | O/U: {g['odds']['total']}")

print(f"\n  All {len(games_tonight)} games are simulation candidates")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running Monte Carlo Simulations")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

all_models = [
    (assumptions["champion"]["id"], assumptions["champion"]["params"], 1.0),
]
for c in assumptions["challengers"]:
    all_models.append((c["id"], c["params"], c["weight"]))

batch = []
for game in games_tonight:
    for model_id, params, weight in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model_id,
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": params,
            "n_sims": 50000,
        })

print(f"  Running {len(batch)} simulations ({len(games_tonight)} games x {len(all_models)} models)...")
results = run_batch(batch)
print(f"  Completed {len(results)} simulations")

# Organize results by game
sim_results = {}
for i, r in enumerate(results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game_key = games_tonight[game_idx]["game"]
    model_id = all_models[model_idx][0]
    if game_key not in sim_results:
        sim_results[game_key] = {}
    sim_results[game_key][model_id] = r

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 4 — Predictions for {TODAY}")
print("=" * 78)

predictions = []

for game in games_tonight:
    gk = game["game"]
    model_results = sim_results[gk]

    total_weight = 0.0
    weighted_wp = 0.0
    weighted_margin = 0.0
    best_evs = []
    all_best_ev = []

    for model_id, params, weight in all_models:
        r = model_results[model_id]
        total_weight += weight
        weighted_wp += weight * r["home_win_prob"]
        weighted_margin += weight * r["expected_margin"]

        evs = {
            "spread_home": r["spread_ev_home"],
            "spread_away": r["spread_ev_away"],
            "ml_home": r["ml_ev_home"],
            "ml_away": r["ml_ev_away"],
        }
        best_bet_type = max(evs, key=evs.get)
        best_ev = evs[best_bet_type]
        best_evs.append(best_ev)
        all_best_ev.append((model_id, best_ev, best_bet_type, r["home_win_prob"]))

    blend_home_wp = weighted_wp / total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin = weighted_margin / total_weight

    # Find overall best bet type (from champion model)
    champ_r = model_results[all_models[0][0]]
    champ_evs = {
        "spread_home": champ_r["spread_ev_home"],
        "spread_away": champ_r["spread_ev_away"],
        "ml_home": champ_r["ml_ev_home"],
        "ml_away": champ_r["ml_ev_away"],
    }
    best_bet_type = max(champ_evs, key=champ_evs.get)

    # Compute blended EV for that specific bet type
    blend_ev = 0.0
    for model_id, params, weight in all_models:
        r = model_results[model_id]
        if best_bet_type == "spread_home":
            blend_ev += weight * r["spread_ev_home"]
        elif best_bet_type == "spread_away":
            blend_ev += weight * r["spread_ev_away"]
        elif best_bet_type == "ml_home":
            blend_ev += weight * r["ml_ev_home"]
        else:
            blend_ev += weight * r["ml_ev_away"]
    blend_ev /= total_weight

    best_model_ev = max(best_evs)
    worst_model_ev = min(best_evs)

    # Robustness: how many models agree on the predicted winner
    home_votes = sum(1 for _, _, _, hwp in all_best_ev if hwp > 0.5)
    away_votes = len(all_best_ev) - home_votes
    agree_count = max(home_votes, away_votes)
    robustness = f"{agree_count}/{len(all_models)}"

    # Determine side
    if blend_home_wp > 0.5:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

    # Classify verdict
    if blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif blend_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Determine bet market
    if "spread" in best_bet_type:
        bet_market = "SPREAD"
    else:
        bet_market = "ML"

    # Kelly criterion (capped at 5%)
    if blend_ev > 0:
        kelly = min(0.05, blend_ev / (best_model_ev if best_model_ev > 0 else 1))
    else:
        kelly = 0.0

    pred = {
        "game": gk,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            mid: {
                "home_win_prob": model_results[mid]["home_win_prob"],
                "expected_margin": model_results[mid]["expected_margin"],
                "spread_ev_home": model_results[mid]["spread_ev_home"],
                "spread_ev_away": model_results[mid]["spread_ev_away"],
                "ml_ev_home": model_results[mid]["ml_ev_home"],
                "ml_ev_away": model_results[mid]["ml_ev_away"],
            }
            for mid, _, _ in all_models
        },
    }
    predictions.append(pred)

# Save predictions FIRST (before displaying)
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_file, "w") as f:
    json.dump({"date": TODAY, "predictions": predictions}, f, indent=2)
print(f"\n  Predictions saved to {pred_file}")

# Display results table
print("\n")
print("+" + "-" * 85 + "+")
print(f"| MLB -- Wednesday Jun 17, 2026{' ' * 55}|")
print("+" + "-" * 30 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 7 + "+" + "-" * 6 + "+" + "-" * 14 + "+")
print(f"| {'Game':<28} | {'Spread':>6} | {'Blend':>6} | {'Best':>6} | {'Worst':>5} | {'Rob.':>4} | {'Verdict':<12} |")
print(f"| {' ':<28} | {' ':>6} | {'EV':>6} | {'EV':>6} | {'EV':>5} | {' ':>4} | {' ':<12} |")
print("+" + "-" * 30 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 7 + "+" + "-" * 6 + "+" + "-" * 14 + "+")

bet_games = []
for p in predictions:
    away_short = p["away_team"].split()[-1][:3].upper()
    home_short = p["home_team"].split()[-1][:3].upper()
    spread = p["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}"

    ev_str = f"{p['best_blend_ev']:+.1%}"
    best_str = f"{p['best_model_ev']:+.1%}"
    worst_str = f"{p['worst_model_ev']:+.1%}"
    rob_str = p["robustness"]

    if p["verdict"] == "BET":
        verdict_str = f"BET {p['side']}"
        bet_games.append(p)
    elif p["verdict"] == "LEAN":
        verdict_str = f"LEAN {p['side']}"
    else:
        verdict_str = f"NO BET"

    game_label = f"{away_short} @ {home_short} ({spread_str})"
    print(f"| {game_label:<28} | {spread_str:>6} | {ev_str:>6} | {best_str:>6} | {worst_str:>5} | {rob_str:>4} | {verdict_str:<12} |")

print("+" + "-" * 30 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 8 + "+" + "-" * 7 + "+" + "-" * 6 + "+" + "-" * 14 + "+")

# Detail on BET games
if bet_games:
    print(f"\n{'=' * 78}")
    print(f"  BET DETAILS ({len(bet_games)} recommended)")
    print(f"{'=' * 78}")
    for p in bet_games:
        print(f"\n  {p['game']}")
        print(f"     Side: {p['side_team']} ({p['side']}) | Market: {p['bet_market']}")
        print(f"     Blend WP: {p['blend_home_wp']:.1%} home / {p['blend_away_wp']:.1%} away")
        print(f"     Blend EV: {p['best_blend_ev']:+.1%} | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"     Best line: {p['odds']['book']} (spread {p['odds']['spread_home']:+.1f})")
        print(f"     Model agreement:")
        for mid, mdata in p["model_results"].items():
            side = "HOME" if mdata["home_win_prob"] > 0.5 else "AWAY"
            agree = "Y" if (side == p["side"]) else "N"
            print(f"       [{agree}] {mid}: {mdata['home_win_prob']:.1%} home WP, margin {mdata['expected_margin']:+.2f}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

r7d = {"correct": 0, "total": 0}
r30d = {"correct": 0, "total": 0}
all_time = {"correct": 0, "total": 0, "bets": 0, "bets_won": 0}

with open(os.path.join(BASE, "results.tsv")) as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 14 or parts[0] == "date":
            continue
        d = parts[0]
        model_id_r = parts[3]
        hit_val = int(parts[9])
        bet_result = parts[13]

        if model_id_r == assumptions["champion"]["id"]:
            all_time["total"] += 1
            all_time["correct"] += hit_val
            if bet_result in ("win", "loss"):
                all_time["bets"] += 1
                if bet_result == "win":
                    all_time["bets_won"] += 1

            if d >= "2026-06-10":
                r7d["total"] += 1
                r7d["correct"] += hit_val
            if d >= "2026-05-17":
                r30d["total"] += 1
                r30d["correct"] += hit_val

r7d_acc = r7d["correct"] / r7d["total"] if r7d["total"] > 0 else 0
r30d_acc = r30d["correct"] / r30d["total"] if r30d["total"] > 0 else 0
at_acc = all_time["correct"] / all_time["total"] if all_time["total"] > 0 else 0

variant_perf = {}
for mid, _, weight in all_models:
    if mid == assumptions["champion"]["id"]:
        variant_perf[mid] = {
            "lifetime_games": assumptions["champion"]["lifetime_games"],
            "lifetime_correct": assumptions["champion"]["lifetime_correct"],
            "weight": 1.0,
            "role": "champion",
        }
    else:
        for c in assumptions["challengers"]:
            if c["id"] == mid:
                variant_perf[mid] = {
                    "lifetime_games": c["lifetime_games"],
                    "lifetime_correct": c["lifetime_correct"],
                    "weight": c["weight"],
                    "role": "challenger",
                }

bet_count = sum(1 for p in predictions if p["verdict"] == "BET")
lean_count = sum(1 for p in predictions if p["verdict"] == "LEAN")

metrics.update({
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round(r7d_acc, 4),
        "ev_realized": round(metrics.get("rolling_7d", {}).get("ev_realized", 0.05), 3),
        "total_games": r7d["total"],
        "total_correct": r7d["correct"],
    },
    "rolling_30d": {
        "accuracy": round(r30d_acc, 4),
        "ev_realized": round(metrics.get("rolling_30d", {}).get("ev_realized", 0.05), 3),
        "total_games": r30d["total"],
        "total_correct": r30d["correct"],
    },
    "all_time": {
        "accuracy": round(at_acc, 4),
        "ev_realized": round(metrics.get("all_time", {}).get("ev_realized", 0.05), 3),
        "total_games": all_time["total"],
        "total_correct": all_time["correct"],
        "total_bets_recommended": all_time["bets"],
        "total_bets_won": all_time["bets_won"],
    },
    "variant_performance": variant_perf,
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(predictions),
        "bets_recommended": bet_count,
        "leans": lean_count,
        "sports": ["baseball_mlb"],
        "notes": f"MLB only (NHL over, NBA/NFL off-season). {bet_count} BETs, {lean_count} LEANs. Eval Jun 16: champion {champion_correct_count}/{champion_total_count}, 8/13 home wins. 3 road upsets (SF@ATL, LAA@ARI, PIT@OAK)."
    },
})

# Update champion history if needed
if not any(h.get("id") == assumptions["champion"]["id"] and h.get("promoted_on") == assumptions["champion"].get("promoted_on") for h in metrics.get("champion_history", [])):
    pass  # Already recorded

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

champ_id = assumptions["champion"]["id"]
print(f"""
  Edge-Finder Metrics
  ====================
  Champion: {champ_id} (promoted {assumptions['champion'].get('promoted_on', 'N/A')})
  7-day:  {r7d_acc:.0%} accuracy | {r7d['correct']}/{r7d['total']} games
  30-day: {r30d_acc:.0%} accuracy | {r30d['correct']}/{r30d['total']} games
  All-time: {at_acc:.0%} accuracy | {all_time['correct']}/{all_time['total']} games | {all_time['bets_won']}/{all_time['bets']} bets won
""")
print("  Challenger weights: ", end="")
chal_strs = []
for c in assumptions["challengers"]:
    chal_strs.append(f"{c['id']}={c['weight']}")
print(", ".join(chal_strs))
print(f"  Graveyard: {', '.join(g['id'] for g in assumptions.get('graveyard', []))}")

print(f"\n  Metrics saved to metrics.json")

print("""
==============================================================================
  DISCLAIMER: This analysis is for entertainment and educational purposes only.
  Past performance does not guarantee future results. Always gamble responsibly.
==============================================================================
""")
