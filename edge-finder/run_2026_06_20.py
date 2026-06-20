#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-20 (Saturday).
Phase 1: Eval June 19 predictions, update weights.
Phase 2-5: Simulate tonight's games (MLB only — NBA/NFL off-season, NHL over).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-20"
EVAL_DATE = "2026-06-19"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 19 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-19 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results fetched via web search (June 19, 2026)
# Sources: ESPN, CBS Sports, baseball-reference, theScore
# REMARKABLE: All 13 games won by the home team on June 19.
actual_results = {
    "Toronto Blue Jays @ Chicago Cubs": {"winner": "home", "home_score": 16, "away_score": 2},
    "Chicago White Sox @ Detroit Tigers": {"winner": "home", "home_score": 4, "away_score": 3},
    "Cincinnati Reds @ New York Yankees": {"winner": "home", "home_score": 5, "away_score": 0},
    "Washington Nationals @ Tampa Bay Rays": {"winner": "home", "home_score": 5, "away_score": 2},
    "San Francisco Giants @ Miami Marlins": {"winner": "home", "home_score": 4, "away_score": 3},
    "Milwaukee Brewers @ Atlanta Braves": {"winner": "home", "home_score": 3, "away_score": 2},
    "San Diego Padres @ Texas Rangers": {"winner": "home", "home_score": 9, "away_score": 7},
    "Cleveland Guardians @ Houston Astros": {"winner": "home", "home_score": 9, "away_score": 3},
    "St. Louis Cardinals @ Kansas City Royals": {"winner": "home", "home_score": 6, "away_score": 5},
    "Pittsburgh Pirates @ Colorado Rockies": {"winner": "home", "home_score": 4, "away_score": 3},
    "Los Angeles Angels @ Sacramento Athletics": {"winner": "home", "home_score": 12, "away_score": 11},
    "Minnesota Twins @ Arizona Diamondbacks": {"winner": "home", "home_score": 9, "away_score": 5},
    "Baltimore Orioles @ Los Angeles Dodgers": {"winner": "home", "home_score": 6, "away_score": 5},
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

        results_lines.append(
            f"{EVAL_DATE}\tbaseball_mlb\t{game}\t{model_id}\t"
            f"{predicted_winner}\t{predicted_margin:.2f}\t{predicted_win_prob:.4f}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{model_data['spread_ev_home']:.4f}\t{model_data['ml_ev_home']:.4f}\t"
            f"{best_bet}\t{bet_result}"
        )

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_lines:
        f.write(line + "\n")

print(f"\n  Evaluated {total_games_evaluated} games (all home wins — remarkable night)")
print(f"  Appended {len(results_lines)} result rows to results.tsv")

# Print model accuracy
print("\n  Model accuracy on June 19 predictions:")
champion_id = assumptions["champion"]["id"]
champion_correct_count = model_correct.get(champion_id, 0)
champion_total_count = model_total.get(champion_id, 0)

for mid in model_ids:
    c = model_correct.get(mid, 0)
    t = model_total.get(mid, 0)
    acc = c / t if t > 0 else 0
    marker = " (CHAMPION)" if mid == champion_id else ""
    print(f"    {mid}: {c}/{t} = {acc:.1%}{marker}")

# Update lifetime stats
assumptions["champion"]["lifetime_games"] += champion_total_count
assumptions["champion"]["lifetime_correct"] += champion_correct_count

for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    challenger["lifetime_games"] += model_total.get(cid, 0)
    challenger["lifetime_correct"] += model_correct.get(cid, 0)

# Weight updates
print("\n  Weight updates:")
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_correct = model_correct.get(cid, 0)
    c_total = model_total.get(cid, 0)
    ch_correct = champion_correct_count
    ch_total = champion_total_count

    if c_total == 0 or ch_total == 0:
        print(f"    {cid}: no games to compare -- skip")
        continue

    if c_correct > ch_correct and c_correct >= 0.6 * c_total:
        old_w = challenger["weight"]
        challenger["weight"] = min(1.0, round(challenger["weight"] + 0.1, 2))
        print(f"    {cid}: outperformed ({c_correct}/{c_total} vs {ch_correct}/{ch_total}), weight {old_w} -> {challenger['weight']}")
    elif c_correct < ch_correct and ch_correct >= 0.6 * ch_total:
        old_w = challenger["weight"]
        challenger["weight"] = max(0.1, round(challenger["weight"] - 0.1, 2))
        print(f"    {cid}: underperformed ({c_correct}/{c_total} vs {ch_correct}/{ch_total}), weight {old_w} -> {challenger['weight']}")
    else:
        print(f"    {cid}: no clear edge ({c_correct}/{c_total} vs {ch_correct}/{ch_total}), weight stays at {challenger['weight']}")

# Update champion rolling 10-day accuracy
champ_lt_games = assumptions["champion"]["lifetime_games"]
champ_lt_correct = assumptions["champion"]["lifetime_correct"]
assumptions["champion"]["rolling_10d_accuracy"] = round(champ_lt_correct / champ_lt_games, 4) if champ_lt_games > 0 else 0

# Promotion check
print("\n  Promotion check:")
promoted = False
champ_10d_acc = assumptions["champion"]["rolling_10d_accuracy"]
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    lt_games = challenger["lifetime_games"]
    lt_correct = challenger["lifetime_correct"]
    if lt_games < 10:
        print(f"    {cid}: only {lt_games} lifetime games, need 10+ for promotion check")
        continue
    chal_acc = lt_correct / lt_games if lt_games > 0 else 0
    diff = chal_acc - champ_10d_acc
    if diff >= 0.05:
        print(f"    PROMOTION: {cid} ({chal_acc:.1%}) exceeds champion ({champ_10d_acc:.1%}) by {diff:.1%}!")
        old_champ = assumptions["champion"]
        assumptions["champion"] = {
            "id": cid,
            "description": challenger["description"],
            "params": challenger["params"],
            "promoted_on": TODAY,
            "rolling_10d_accuracy": chal_acc,
            "lifetime_games": challenger["lifetime_games"],
            "lifetime_correct": challenger["lifetime_correct"],
        }
        challenger["id"] = old_champ["id"]
        challenger["description"] = old_champ["description"]
        challenger["params"] = old_champ["params"]
        challenger["weight"] = 0.7
        challenger["born"] = old_champ.get("promoted_on", TODAY)
        challenger["grace_until"] = TODAY
        challenger["lifetime_games"] = old_champ["lifetime_games"]
        challenger["lifetime_correct"] = old_champ["lifetime_correct"]
        promoted = True
        champion_id = cid
        break
    else:
        print(f"    {cid}: {chal_acc:.1%} vs champion {champ_10d_acc:.1%} (diff: {diff:+.1%}) -- no promotion")

if not promoted:
    print("    No promotions triggered.")

# Retirement check
print("\n  Retirement check:")
retired_any = False
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    if challenger["weight"] <= 0.15 and challenger["born"] < "2026-06-15":
        print(f"    Retiring {cid} (weight={challenger['weight']}, born={challenger['born']})")
        retired_any = True
    else:
        print(f"    {cid}: weight={challenger['weight']}, born={challenger['born']} -- keep")

if not retired_any:
    print("    No retirements needed.")

# Save assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  Phase 1 complete. Champion '{champion_id}' accuracy: {champion_correct_count}/{champion_total_count}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's Games: June 20, 2026)
# ════════════════════════════════════════════════════════════════════════
# NHL: Season over
# NBA: Off-season
# NFL: Off-season
# MLB: Regular season — Saturday schedule, 15 games
#
# Odds via web search (FanDuel primary, cross-checked BetMGM/DraftKings).
# Stats carried forward from June 19 run with adjustments for games
# played June 19. New matchups (NYM@PHI, BOS@SEA) estimated from
# season stats and standings.

print("\n" + "=" * 78)
print(f" PHASE 2 — Tonight's Games & Odds ({TODAY})")
print("=" * 78)

games_tonight = [
    {
        "sport": "baseball_mlb",
        "game": "Chicago White Sox @ Detroit Tigers",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.42,
            "season_opp_ppg": 3.87,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 3.60,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.540,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.37,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.556,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -146,
            "ml_away": 119,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cincinnati Reds @ New York Yankees",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 5.02,
            "season_opp_ppg": 4.03,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.660,
            "away_record_pct": 0.600,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 4.70,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.430,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -184,
            "ml_away": 154,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Toronto Blue Jays @ Chicago Cubs",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.65,
            "season_opp_ppg": 4.22,
            "last10_ppg": 5.20,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.590,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -124,
            "ml_away": 106,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Diego Padres @ Texas Rangers",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.62,
            "season_opp_ppg": 4.42,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.486,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.68,
            "season_opp_ppg": 4.12,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.510,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -164,
            "ml_away": 138,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Washington Nationals @ Tampa Bay Rays",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.22,
            "season_opp_ppg": 4.38,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.10,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.38,
            "season_opp_ppg": 4.32,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Francisco Giants @ Miami Marlins",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 3.88,
            "season_opp_ppg": 4.53,
            "last10_ppg": 3.95,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.445,
            "away_record_pct": 0.350,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 3.93,
            "season_opp_ppg": 4.77,
            "last10_ppg": 3.70,
            "last10_opp_ppg": 4.80,
            "season_pace": 1.0,
            "home_record_pct": 0.432,
            "away_record_pct": 0.378,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -136,
            "ml_away": 116,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Milwaukee Brewers @ Atlanta Braves",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.98,
            "season_opp_ppg": 4.07,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 5.00,
            "season_pace": 1.0,
            "home_record_pct": 0.625,
            "away_record_pct": 0.580,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.58,
            "season_opp_ppg": 4.02,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 3.85,
            "season_pace": 1.0,
            "home_record_pct": 0.576,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -135,
            "ml_away": 110,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cleveland Guardians @ Houston Astros",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.85,
            "season_opp_ppg": 4.08,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.585,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.18,
            "season_opp_ppg": 4.44,
            "last10_ppg": 3.90,
            "last10_opp_ppg": 4.50,
            "season_pace": 1.0,
            "home_record_pct": 0.529,
            "away_record_pct": 0.441,
            "is_back_to_back": True,
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
    {
        "sport": "baseball_mlb",
        "game": "St. Louis Cardinals @ Kansas City Royals",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.08,
            "season_opp_ppg": 4.83,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 4.90,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.370,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.90,
            "season_opp_ppg": 4.22,
            "last10_ppg": 4.90,
            "last10_opp_ppg": 4.30,
            "season_pace": 1.0,
            "home_record_pct": 0.611,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 105,
            "ml_away": -125,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "New York Mets @ Philadelphia Phillies",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.60,
            "season_opp_ppg": 3.60,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 3.50,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.10,
            "last10_opp_ppg": 4.60,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -184,
            "ml_away": 154,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Pittsburgh Pirates @ Colorado Rockies",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.57,
            "season_opp_ppg": 5.38,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 5.50,
            "season_pace": 1.0,
            "home_record_pct": 0.405,
            "away_record_pct": 0.310,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.33,
            "season_opp_ppg": 4.32,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 176,
            "ml_away": -210,
            "total": 9.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Los Angeles Angels @ Sacramento Athletics",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 4.18,
            "season_opp_ppg": 4.43,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.20,
            "season_opp_ppg": 4.90,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.469,
            "away_record_pct": 0.395,
            "is_back_to_back": True,
            "key_injuries": 2,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -164,
            "ml_away": 138,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Minnesota Twins @ Arizona Diamondbacks",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.85,
            "season_opp_ppg": 3.98,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 3.60,
            "season_pace": 1.0,
            "home_record_pct": 0.585,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.63,
            "season_opp_ppg": 4.40,
            "last10_ppg": 5.40,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.543,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -136,
            "ml_away": 113,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Baltimore Orioles @ Los Angeles Dodgers",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.22,
            "season_opp_ppg": 3.68,
            "last10_ppg": 5.50,
            "last10_opp_ppg": 3.40,
            "season_pace": 1.0,
            "home_record_pct": 0.635,
            "away_record_pct": 0.600,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.23,
            "season_opp_ppg": 4.77,
            "last10_ppg": 3.70,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.405,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -267,
            "ml_away": 214,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Boston Red Sox @ Seattle Mariners",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.10,
            "season_opp_ppg": 3.55,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 3.30,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0,
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.40,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 4.00,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -104,
            "total": 7.5,
            "book": "fanduel",
        },
    },
]

print(f"  {len(games_tonight)} MLB games tonight (all candidates — MLB only season)")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running Simulations")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

models = [
    {"id": assumptions["champion"]["id"], "params": assumptions["champion"]["params"], "weight": 1.0},
]
for c in assumptions["challengers"]:
    models.append({"id": c["id"], "params": c["params"], "weight": c["weight"]})

batch = []
for game in games_tonight:
    for model in models:
        sim_input = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        }
        batch.append(sim_input)

print(f"  Batch size: {len(batch)} simulations ({len(games_tonight)} games x {len(models)} models)")
print("  Running sim.py...", flush=True)

results = run_batch(batch)

print(f"  Done. Got {len(results)} results.")

# Organize results by game and model
game_results = {}
for i, game in enumerate(games_tonight):
    game_key = game["game"]
    game_results[game_key] = {"game_data": game, "models": {}}
    for j, model in enumerate(models):
        idx = i * len(models) + j
        game_results[game_key]["models"][model["id"]] = {
            "result": results[idx],
            "weight": model["weight"],
        }

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 4 — Blended Predictions ({TODAY})")
print("=" * 78)

predictions = []

for game_key, gdata in game_results.items():
    game_info = gdata["game_data"]
    model_data = gdata["models"]

    total_weight = sum(m["weight"] for m in model_data.values())
    blend_home_wp = sum(m["result"]["home_win_prob"] * m["weight"] for m in model_data.values()) / total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin = sum(m["result"]["expected_margin"] * m["weight"] for m in model_data.values()) / total_weight

    blend_spread_ev_home = sum(m["result"]["spread_ev_home"] * m["weight"] for m in model_data.values()) / total_weight
    blend_spread_ev_away = sum(m["result"]["spread_ev_away"] * m["weight"] for m in model_data.values()) / total_weight
    blend_ml_ev_home = sum(m["result"]["ml_ev_home"] * m["weight"] for m in model_data.values()) / total_weight
    blend_ml_ev_away = sum(m["result"]["ml_ev_away"] * m["weight"] for m in model_data.values()) / total_weight

    ev_options = {
        "spread_home": blend_spread_ev_home,
        "spread_away": blend_spread_ev_away,
        "ml_home": blend_ml_ev_home,
        "ml_away": blend_ml_ev_away,
    }
    best_bet_type = max(ev_options, key=ev_options.get)
    best_blend_ev = ev_options[best_bet_type]

    model_best_evs = []
    for mid, mdata in model_data.items():
        r = mdata["result"]
        model_ev = max(r["spread_ev_home"], r["spread_ev_away"], r["ml_ev_home"], r["ml_ev_away"])
        model_best_evs.append(model_ev)

    best_model_ev = max(model_best_evs)
    worst_model_ev = min(model_best_evs)

    home_votes = sum(1 for m in model_data.values() if m["result"]["home_win_prob"] > 0.5)
    away_votes = len(model_data) - home_votes
    agree_count = max(home_votes, away_votes)
    robustness = f"{agree_count}/{len(model_data)}"

    if blend_home_wp > 0.5:
        side = "HOME"
        side_team = game_info["home"]["name"]
    else:
        side = "AWAY"
        side_team = game_info["away"]["name"]

    if "spread" in best_bet_type:
        bet_market = "SPREAD"
    else:
        bet_market = "ML"

    any_flips = any(
        (m["result"]["home_win_prob"] > 0.5) != (blend_home_wp > 0.5)
        for m in model_data.values()
    )

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and agree_count >= 4 and worst_model_ev <= 0:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    if best_blend_ev > 0 and verdict in ("BET", "LEAN"):
        kelly = min(0.05, round(best_blend_ev / 3, 4))
    else:
        kelly = 0.0

    model_results_dict = {}
    for mid, mdata in model_data.items():
        r = mdata["result"]
        model_results_dict[mid] = {
            "home_win_prob": r["home_win_prob"],
            "expected_margin": r["expected_margin"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
        }

    pred = {
        "game": game_key,
        "sport": game_info["sport"],
        "home_team": game_info["home"]["name"],
        "away_team": game_info["away"]["name"],
        "odds": game_info["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(best_blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": kelly,
        "model_results": model_results_dict,
    }
    predictions.append(pred)

# Save predictions BEFORE displaying
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_file, "w") as f:
    json.dump({"date": TODAY, "predictions": predictions}, f, indent=2)
print(f"\n  Saved predictions to {pred_file}")

# Display results table
print("\n")
print("┌─────────────────────────────────────────────────────────────────────────────────┐")
print(f"│ MLB — Saturday Jun 20, 2026                                                    │")
print("├──────────────────────────────┬────────┬────────┬────────┬───────┬──────┬─────────┤")
print("│ Game                         │ Spread │ Blend  │ Best   │ Worst │ Rob. │ Verdict │")
print("│                              │        │ EV     │ EV     │ EV    │      │         │")
print("├──────────────────────────────┼────────┼────────┼────────┼───────┼──────┼─────────┤")

bet_count = 0
lean_count = 0

for pred in predictions:
    game_short = pred["game"]
    parts = game_short.split(" @ ")
    away_short = parts[0].split()[-1] if parts else "???"
    home_short = parts[1].split()[-1] if len(parts) > 1 else "???"
    spread = pred["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}"

    display = f"{away_short} @ {home_short} {spread_str}"

    blend_ev = pred["best_blend_ev"]
    best_ev = pred["best_model_ev"]
    worst_ev = pred["worst_model_ev"]
    rob = pred["robustness"]

    if pred["verdict"] == "BET":
        icon = "✅"
        verdict_str = f"BET {pred['side']}"
        bet_count += 1
    elif pred["verdict"] == "LEAN":
        icon = "⚠️"
        verdict_str = f"LEAN {pred['side']}"
        lean_count += 1
    else:
        icon = "❌"
        verdict_str = "NO BET"

    print(f"│ {display:<28s} │ {spread_str:>6s} │ {blend_ev:>+6.1%} │ {best_ev:>+6.1%} │{worst_ev:>+5.1%} │ {rob:>4s} │ {icon} {verdict_str:<5s} │")

print("└──────────────────────────────┴────────┴────────┴────────┴───────┴──────┴─────────┘")

# Print BET details
print("\n" + "─" * 78)
print("BET DETAILS")
print("─" * 78)

for pred in predictions:
    if pred["verdict"] != "BET":
        continue
    print(f"\n  {pred['game']}")
    print(f"    Side: {pred['side']} ({pred['side_team']})")
    print(f"    Market: {pred['bet_market']} | Best bet: {pred['best_bet_type']}")
    print(f"    Blended EV: {pred['best_blend_ev']:+.1%} | Kelly: {pred['kelly']:.1%} of bankroll")
    print(f"    Book: {pred['odds']['book']} | ML: Home {pred['odds']['ml_home']}, Away {pred['odds']['ml_away']}")
    print(f"    Model agreement: {pred['robustness']}")
    for mid, mres in pred["model_results"].items():
        side_prob = mres["home_win_prob"] if pred["side"] == "HOME" else (1 - mres["home_win_prob"])
        best_ev = max(mres["spread_ev_home"], mres["spread_ev_away"], mres["ml_ev_home"], mres["ml_ev_away"])
        agrees = (mres["home_win_prob"] > 0.5) == (pred["side"] == "HOME")
        marker = "✓" if agrees else "✗"
        print(f"      {marker} {mid}: {side_prob:.1%} win prob, best EV {best_ev:+.1%}")

print(f"\n  Summary: {bet_count} BETs, {lean_count} LEANs, {len(predictions) - bet_count - lean_count} NO BETs")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champ = assumptions["champion"]

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

metrics["last_updated"] = TODAY
prev_total = metrics["all_time"]["total_games"]
new_total = prev_total + total_games_evaluated
prev_correct = metrics["all_time"]["total_correct"]
new_correct = prev_correct + champion_correct_count

metrics["all_time"]["total_games"] = new_total
metrics["all_time"]["total_correct"] = new_correct
metrics["all_time"]["accuracy"] = round(new_correct / new_total, 4) if new_total > 0 else 0
metrics["all_time"]["total_bets_recommended"] = metrics["all_time"].get("total_bets_recommended", 0) + total_games_evaluated
metrics["all_time"]["total_bets_won"] = metrics["all_time"].get("total_bets_won", 0) + champion_correct_count

r7_games = metrics["rolling_7d"]["total_games"] + total_games_evaluated
r7_correct = metrics["rolling_7d"]["total_correct"] + champion_correct_count
metrics["rolling_7d"]["total_games"] = r7_games
metrics["rolling_7d"]["total_correct"] = r7_correct
metrics["rolling_7d"]["accuracy"] = round(r7_correct / r7_games, 4) if r7_games > 0 else 0

r30_games = metrics["rolling_30d"]["total_games"] + total_games_evaluated
r30_correct = metrics["rolling_30d"]["total_correct"] + champion_correct_count
metrics["rolling_30d"]["total_games"] = r30_games
metrics["rolling_30d"]["total_correct"] = r30_correct
metrics["rolling_30d"]["accuracy"] = round(r30_correct / r30_games, 4) if r30_games > 0 else 0

metrics["variant_performance"] = {}
metrics["variant_performance"][champ["id"]] = {
    "lifetime_games": champ["lifetime_games"],
    "lifetime_correct": champ["lifetime_correct"],
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

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": bet_count,
    "leans": lean_count,
    "sports": ["baseball_mlb"],
    "notes": f"MLB only. {bet_count} BETs, {lean_count} LEANs. Eval Jun 19: {champion_correct_count}/{champion_total_count} correct (all home wins night).",
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

champ_id = assumptions["champion"]["id"]
print(f"\n📊 Edge-Finder Metrics")
print("━" * 40)
print(f"Champion: {champ_id} (promoted {champ['promoted_on']})")
print(f"7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | {metrics['rolling_7d']['total_games']} games")
print(f"30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | {metrics['rolling_30d']['total_games']} games")
print(f"All-time: {metrics['all_time']['accuracy']:.0%} accuracy | {metrics['all_time']['total_games']} games")
print()

chal_str = ", ".join(f"{c['id']}={c['weight']}" for c in assumptions["challengers"])
print(f"Challenger weights: {chal_str}")

if assumptions.get("graveyard"):
    grave_str = ", ".join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions["graveyard"])
    print(f"Graveyard: {grave_str}")

print()
print("⚠️  This is for entertainment and analysis purposes only.")
print("    Past performance does not guarantee future results.")


if __name__ == "__main__":
    pass
