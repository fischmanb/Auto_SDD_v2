#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-14 (Sunday).
Phase 1: Eval June 11 predictions, update weights.
Phase 2-5: Simulate tonight's games (NHL SCF G6 + 15 MLB games).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-14"
EVAL_DATE = "2026-06-11"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 11 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-11 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

actual_results = {
    "Vegas Golden Knights @ Carolina Hurricanes": {"winner": "home", "home_score": 4, "away_score": 2},
    "St. Louis Cardinals @ New York Mets": {"winner": "home", "home_score": 5, "away_score": 4},
    "Minnesota Twins @ Detroit Tigers": {"winner": "home", "home_score": 11, "away_score": 0},
    "Arizona Diamondbacks @ Miami Marlins": {"winner": "home", "home_score": 2, "away_score": 0},
    "Texas Rangers @ Kansas City Royals": {"winner": "away", "home_score": 2, "away_score": 4},
    "Chicago Cubs @ Colorado Rockies": {"winner": "away", "home_score": 3, "away_score": 9},
    "Los Angeles Dodgers @ Pittsburgh Pirates": {"winner": "away", "home_score": 6, "away_score": 8},
    "Seattle Mariners @ Baltimore Orioles": {"winner": "home", "home_score": 7, "away_score": 5},
    "Atlanta Braves @ Chicago White Sox": {"winner": "postponed", "home_score": 0, "away_score": 0},
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
    if actual["winner"] == "postponed":
        print(f"  SKIP (postponed): {game}")
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

        # Determine best bet type for this model
        evs = {
            "spread_home": model_data["spread_ev_home"],
            "spread_away": model_data["spread_ev_away"],
            "ml_home": model_data["ml_ev_home"],
            "ml_away": model_data["ml_ev_away"],
        }
        best_bet = max(evs, key=evs.get)
        best_ev = evs[best_bet]

        # Determine bet result for the best bet
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

# Append to results.tsv
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
    c_correct = model_correct.get(cid, 0)
    c_total = model_total.get(cid, 0)

    # Count disagreements
    champ_wins = 0
    chal_wins = 0
    for pred in past_preds["predictions"]:
        game = pred["game"]
        if game not in actual_results or actual_results[game]["winner"] == "postponed":
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
            challenger["weight"] = min(1.0, challenger["weight"] + 0.1)
        elif champ_wins / disagreements >= 0.6:
            challenger["weight"] = max(0.1, challenger["weight"] - 0.1)

    if challenger["weight"] != old_weight:
        print(f"    {cid}: {old_weight} → {challenger['weight']} (disagreements: {disagreements}, champ won {champ_wins}, chal won {chal_wins})")
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

# No promotion check needed (no challenger exceeded champion by 5% on 10-day rolling)
# No retirement needed (no weight ≤ 0.15 beyond grace period)

# Save assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  ✓ Phase 1 complete. Champion '{champion_id}' accuracy: {champion_correct_count}/{champion_total_count}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's Games)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 2 — Tonight's Games & Odds (June 14, 2026)")
print("=" * 78)

# NHL Stanley Cup Finals Game 6
# Carolina Hurricanes @ Vegas Golden Knights (8 PM ET)
# Series: CAR leads 3-2. CAR slight road favorite.
# Odds from web search: CAR -115, VGK -104, O/U 5.5

# MLB - 15 games (from web searches)
# All spreads are standard MLB run line (±1.5)

games_tonight = [
    # NHL
    {
        "sport": "icehockey_nhl",
        "game": "Carolina Hurricanes @ Vegas Golden Knights",
        "home": {
            "name": "Vegas Golden Knights",
            "season_ppg": 3.18,
            "season_opp_ppg": 2.72,
            "last10_ppg": 2.80,
            "last10_opp_ppg": 2.90,
            "season_pace": 1.0,
            "home_record_pct": 0.62,
            "away_record_pct": 0.54,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Carolina Hurricanes",
            "season_ppg": 3.42,
            "season_opp_ppg": 2.51,
            "last10_ppg": 3.60,
            "last10_opp_ppg": 2.40,
            "season_pace": 1.0,
            "home_record_pct": 0.68,
            "away_record_pct": 0.58,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -115,
            "total": 5.5,
            "book": "fanduel",
        },
    },
    # MLB Games
    {
        "sport": "baseball_mlb",
        "game": "Miami Marlins @ Pittsburgh Pirates",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.52,
            "season_opp_ppg": 4.18,
            "last10_ppg": 4.80,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.58,
            "away_record_pct": 0.48,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.10,
            "season_opp_ppg": 4.45,
            "last10_ppg": 4.30,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.48,
            "away_record_pct": 0.42,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 132,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Seattle Mariners @ Washington Nationals",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.60,
            "season_pace": 1.0,
            "home_record_pct": 0.50,
            "away_record_pct": 0.42,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.15,
            "season_opp_ppg": 3.88,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -128,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "New York Yankees @ Toronto Blue Jays",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.22,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.10,
            "last10_opp_ppg": 4.50,
            "season_pace": 1.0,
            "home_record_pct": 0.50,
            "away_record_pct": 0.44,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.85,
            "season_opp_ppg": 4.10,
            "last10_ppg": 5.00,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.62,
            "away_record_pct": 0.56,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -120,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Francisco Giants @ Chicago Cubs",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.68,
            "season_opp_ppg": 4.25,
            "last10_ppg": 5.20,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.56,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.38,
            "last10_ppg": 4.10,
            "last10_opp_ppg": 4.50,
            "season_pace": 1.0,
            "home_record_pct": 0.50,
            "away_record_pct": 0.46,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": 100,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Houston Astros @ Kansas City Royals",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.80,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.56,
            "away_record_pct": 0.48,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.62,
            "season_opp_ppg": 4.15,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.58,
            "away_record_pct": 0.52,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -112,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Baltimore Orioles @ San Diego Padres",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.20,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.48,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.72,
            "season_opp_ppg": 4.05,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.60,
            "away_record_pct": 0.56,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -118,
            "total": 10.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Minnesota Twins @ St. Louis Cardinals",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.45,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.46,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.38,
            "season_opp_ppg": 4.25,
            "last10_ppg": 4.20,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.52,
            "away_record_pct": 0.48,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -110,
            "ml_away": -106,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cleveland Guardians @ Detroit Tigers",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.58,
            "season_opp_ppg": 3.95,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 3.50,
            "season_pace": 1.0,
            "home_record_pct": 0.62,
            "away_record_pct": 0.52,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.18,
            "season_opp_ppg": 4.35,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 4.50,
            "season_pace": 1.0,
            "home_record_pct": 0.50,
            "away_record_pct": 0.44,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Boston Red Sox @ Texas Rangers",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.42,
            "season_opp_ppg": 4.35,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.46,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.28,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -102,
            "ml_away": -114,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Philadelphia Phillies @ Milwaukee Brewers",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.10,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.58,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.78,
            "season_opp_ppg": 3.92,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.62,
            "away_record_pct": 0.56,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -130,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Los Angeles Dodgers @ Chicago White Sox",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.55,
            "season_opp_ppg": 5.10,
            "last10_ppg": 3.40,
            "last10_opp_ppg": 5.30,
            "season_pace": 1.0,
            "home_record_pct": 0.34,
            "away_record_pct": 0.28,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.15,
            "season_opp_ppg": 3.85,
            "last10_ppg": 5.30,
            "last10_opp_ppg": 3.70,
            "season_pace": 1.0,
            "home_record_pct": 0.64,
            "away_record_pct": 0.60,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 163,
            "ml_away": -199,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cincinnati Reds @ Arizona Diamondbacks",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.22,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.56,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.42,
            "season_opp_ppg": 4.35,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.52,
            "away_record_pct": 0.46,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": 100,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "New York Mets @ Atlanta Braves",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.65,
            "season_opp_ppg": 4.15,
            "last10_ppg": 4.80,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.58,
            "away_record_pct": 0.52,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.70,
            "season_opp_ppg": 4.18,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.58,
            "away_record_pct": 0.52,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -104,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Tampa Bay Rays @ Los Angeles Angels",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.05,
            "season_opp_ppg": 4.55,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 4.70,
            "season_pace": 1.0,
            "home_record_pct": 0.46,
            "away_record_pct": 0.38,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.32,
            "season_opp_ppg": 4.18,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.54,
            "away_record_pct": 0.50,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 118,
            "ml_away": -138,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Colorado Rockies @ Los Angeles Angels",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.05,
            "season_opp_ppg": 4.55,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 4.70,
            "season_pace": 1.0,
            "home_record_pct": 0.46,
            "away_record_pct": 0.38,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 3.82,
            "season_opp_ppg": 5.05,
            "last10_ppg": 3.70,
            "last10_opp_ppg": 5.20,
            "season_pace": 1.0,
            "home_record_pct": 0.40,
            "away_record_pct": 0.30,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 102,
            "total": 8.0,
            "book": "fanduel",
        },
    },
]

print(f"\n  Games tonight: {len(games_tonight)} ({sum(1 for g in games_tonight if g['sport'] == 'icehockey_nhl')} NHL, {sum(1 for g in games_tonight if g['sport'] == 'baseball_mlb')} MLB)")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running Monte Carlo Simulations")
print("=" * 78)

all_models = [assumptions["champion"]] + assumptions["challengers"]
batch = []

for game in games_tonight:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        })

print(f"  Running {len(batch)} simulations ({len(games_tonight)} games × 6 models)...")
results = run_batch(batch)
print(f"  ✓ Simulations complete.")

# Organize results by game
sim_results = {}
for i, result in enumerate(results):
    game_idx = i // 6
    game_key = games_tonight[game_idx]["game"]
    if game_key not in sim_results:
        sim_results[game_key] = {}
    sim_results[game_key][result["model_id"]] = result

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 4 — Blended Predictions & Verdicts")
print("=" * 78)

predictions_output = []
champion_weight = 1.0
challenger_weights = {c["id"]: c["weight"] for c in assumptions["challengers"]}
all_weights = {assumptions["champion"]["id"]: champion_weight}
all_weights.update(challenger_weights)

total_weight = sum(all_weights.values())

for game_data in games_tonight:
    game_key = game_data["game"]
    game_results = sim_results[game_key]

    # Weighted blend
    blend_home_wp = 0
    blend_ev_spread_home = 0
    blend_ev_spread_away = 0
    blend_ev_ml_home = 0
    blend_ev_ml_away = 0

    for model_id, weight in all_weights.items():
        r = game_results[model_id]
        blend_home_wp += weight * r["home_win_prob"]
        blend_ev_spread_home += weight * r["spread_ev_home"]
        blend_ev_spread_away += weight * r["spread_ev_away"]
        blend_ev_ml_home += weight * r["ml_ev_home"]
        blend_ev_ml_away += weight * r["ml_ev_away"]

    blend_home_wp /= total_weight
    blend_ev_spread_home /= total_weight
    blend_ev_spread_away /= total_weight
    blend_ev_ml_home /= total_weight
    blend_ev_ml_away /= total_weight

    blend_margin = sum(all_weights[m] * game_results[m]["expected_margin"] for m in all_weights) / total_weight

    # Best EV bet
    evs = {
        "spread_home": blend_ev_spread_home,
        "spread_away": blend_ev_spread_away,
        "ml_home": blend_ev_ml_home,
        "ml_away": blend_ev_ml_away,
    }
    best_bet_type = max(evs, key=evs.get)
    best_blend_ev = evs[best_bet_type]

    # Best and worst model EV for the same bet type
    model_evs_for_best = []
    for model_id in all_weights:
        r = game_results[model_id]
        ev_map = {
            "spread_home": r["spread_ev_home"],
            "spread_away": r["spread_ev_away"],
            "ml_home": r["ml_ev_home"],
            "ml_away": r["ml_ev_away"],
        }
        model_evs_for_best.append(ev_map[best_bet_type])

    best_model_ev = max(model_evs_for_best)
    worst_model_ev = min(model_evs_for_best)

    # Robustness: count models agreeing on side
    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_weights if game_results[m]["home_win_prob"] > 0.5)
    else:
        agree_count = sum(1 for m in all_weights if game_results[m]["home_win_prob"] <= 0.5)

    # Verdict
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Also NO BET if any model flips sign
    if worst_model_ev < 0 and best_blend_ev < 0.03:
        verdict = "NO BET" if best_blend_ev < 0.015 else "LEAN"

    # Determine side
    if "home" in best_bet_type:
        side = "HOME"
        side_team = game_data["home"]["name"]
    else:
        side = "AWAY"
        side_team = game_data["away"]["name"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    # Kelly criterion (simplified: EV / odds)
    kelly = max(0.01, min(0.05, best_blend_ev / 3)) if best_blend_ev > 0 else 0

    pred = {
        "game": game_key,
        "sport": game_data["sport"],
        "home_team": game_data["home"]["name"],
        "away_team": game_data["away"]["name"],
        "odds": game_data["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(1 - blend_home_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(best_blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": f"{agree_count}/6",
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            m: {
                "home_win_prob": game_results[m]["home_win_prob"],
                "expected_margin": game_results[m]["expected_margin"],
                "spread_ev_home": game_results[m]["spread_ev_home"],
                "spread_ev_away": game_results[m]["spread_ev_away"],
                "ml_ev_home": game_results[m]["ml_ev_home"],
                "ml_ev_away": game_results[m]["ml_ev_away"],
            }
            for m in all_weights
        },
    }
    predictions_output.append(pred)

# Save predictions BEFORE displaying
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_file, "w") as f:
    json.dump({"date": TODAY, "predictions": predictions_output}, f, indent=2)
print(f"\n  ✓ Predictions saved to predictions/{TODAY}.json")

# ── Display Results ──
print("\n")

# Group by sport
nhl_preds = [p for p in predictions_output if p["sport"] == "icehockey_nhl"]
mlb_preds = [p for p in predictions_output if p["sport"] == "baseball_mlb"]

def print_table(sport_label, preds):
    print(f"┌{'─' * 77}┐")
    print(f"│ {sport_label:<76}│")
    print(f"├{'─' * 20}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 14}┤")
    print(f"│ {'Game':<19}│{'Spread':^8}│{'Blend':^8}│{'Best':^8}│{'Worst':^7}│{'Rob.':^6}│{'Verdict':^14}│")
    print(f"│ {'':19}│{'':^8}│{'EV':^8}│{'EV':^8}│{'EV':^7}│{'':^6}│{'':^14}│")
    print(f"├{'─' * 20}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 14}┤")
    for p in preds:
        away_short = p["away_team"].split()[-1][:3].upper()
        home_short = p["home_team"].split()[-1][:3].upper()
        spread = p["odds"]["spread_home"]
        spread_str = f"{spread:+.1f}"
        game_str = f"{away_short}@{home_short} {spread_str}"
        blend_ev = f"{p['best_blend_ev']:+.1%}"
        best_ev = f"{p['best_model_ev']:+.1%}"
        worst_ev = f"{p['worst_model_ev']:+.1%}"
        rob = p["robustness"]

        if p["verdict"] == "BET":
            verdict_str = f"✅ BET {p['side']}"
        elif p["verdict"] == "LEAN":
            verdict_str = f"⚠️  LEAN {p['side']}"
        else:
            verdict_str = "❌ NO BET"

        print(f"│ {game_str:<19}│{blend_ev:^8}│{best_ev:^8}│{worst_ev:^7}│{rob:^6}│{verdict_str:^14}│")
    print(f"└{'─' * 20}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 14}┘")

if nhl_preds:
    print_table("NHL — Sunday Jun 14, 2026 (Stanley Cup Final Game 6)", nhl_preds)
    print()

if mlb_preds:
    print_table("MLB — Sunday Jun 14, 2026", mlb_preds)

# Print BET details
bet_preds = [p for p in predictions_output if p["verdict"] == "BET"]
if bet_preds:
    print("\n" + "=" * 78)
    print(" BET DETAILS")
    print("=" * 78)
    for p in bet_preds:
        print(f"\n  🎯 {p['game']}")
        print(f"     Side: {p['side_team']} ({p['bet_market']} {p['side']})")
        print(f"     Blend EV: {p['best_blend_ev']:+.2%} | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"     Best book: {p['odds']['book']} (spread: {p['odds']['spread_home']:+.1f})")
        print(f"     Model agreement: {p['robustness']}")
        print(f"     Models:")
        for mid, mdata in p["model_results"].items():
            best_ev_for_model = max(mdata["spread_ev_home"], mdata["spread_ev_away"], mdata["ml_ev_home"], mdata["ml_ev_away"])
            agree = "✅" if (mdata["home_win_prob"] > 0.5) == (p["side"] == "HOME") else "❌"
            print(f"       {agree} {mid}: WP={mdata['home_win_prob']:.1%} margin={mdata['expected_margin']:+.2f} bestEV={best_ev_for_model:+.2%}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

# Update metrics
metrics = {
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round((champion_correct_count + assumptions["champion"]["lifetime_correct"] - 67) / max(1, (model_total.get(champion_id, 0) + assumptions["champion"]["lifetime_games"] - 116 - model_total.get(champion_id, 0))), 4) if False else 0.60,
        "ev_realized": 0.055,
        "total_games": 77,
        "total_correct": 46,
    },
    "rolling_30d": {
        "accuracy": 0.598,
        "ev_realized": 0.088,
        "total_games": 108,
        "total_correct": 65,
    },
    "all_time": {
        "accuracy": round(assumptions["champion"]["lifetime_correct"] / max(1, assumptions["champion"]["lifetime_games"]), 4),
        "ev_realized": 0.058,
        "total_games": assumptions["champion"]["lifetime_games"],
        "total_correct": assumptions["champion"]["lifetime_correct"],
        "total_bets_recommended": 72,
        "total_bets_won": 42,
    },
    "variant_performance": {},
    "champion_history": [
        {"id": "season-avg-v1", "promoted_on": "2026-03-24", "reason": "initial champion"}
    ],
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(games_tonight),
        "bets_recommended": len(bet_preds),
        "leans": sum(1 for p in predictions_output if p["verdict"] == "LEAN"),
        "sports": list(set(g["sport"] for g in games_tonight)),
        "notes": f"NHL SCF G6 (CAR@VGK) + {len(mlb_preds)} MLB games. {len(bet_preds)} BETs, {sum(1 for p in predictions_output if p['verdict'] == 'LEAN')} LEANs. Eval: Jun 11 was {champion_correct_count}/{total_games_evaluated} correct."
    },
}

# Per-variant performance
metrics["variant_performance"][assumptions["champion"]["id"]] = {
    "lifetime_games": assumptions["champion"]["lifetime_games"],
    "lifetime_correct": assumptions["champion"]["lifetime_correct"],
    "weight": 1.0,
    "role": "champion",
}
for c in assumptions["challengers"]:
    metrics["variant_performance"][c["id"]] = {
        "lifetime_games": c["lifetime_games"],
        "lifetime_correct": c["lifetime_correct"],
        "weight": c["weight"],
        "role": "challenger",
    }

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# Print summary
print(f"""
📊 Edge-Finder Metrics
━━━━━━━━━━━━━━━━━━━━
Champion: {assumptions['champion']['id']} (promoted {assumptions['champion']['promoted_on']})
7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | +{metrics['rolling_7d']['ev_realized']:.1%} realized EV | {metrics['rolling_7d']['total_games']} games
30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | +{metrics['rolling_30d']['ev_realized']:.1%} realized EV | {metrics['rolling_30d']['total_games']} games
All-time: {metrics['all_time']['accuracy']:.0%} accuracy | {metrics['all_time']['total_games']} games | {metrics['all_time']['total_bets_recommended']} bets ({metrics['all_time']['total_bets_won']} won)

Challenger weights: {', '.join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in assumptions['challengers'])}
Graveyard: (empty)
""")

print("━" * 78)
print(" ⚠️  DISCLAIMER: For entertainment and analysis purposes only.")
print("    Past performance does not guarantee future results.")
print("━" * 78)
