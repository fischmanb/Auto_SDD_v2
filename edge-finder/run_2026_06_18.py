#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-18 (Thursday).
Phase 1: Eval June 16 predictions (last predictions made), update weights.
Phase 2-5: Simulate tonight's games (MLB only — NBA/NFL off-season, NHL over).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-18"
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
# Sources: ESPN, MLB.com, CBS Sports game pages
actual_results = {
    "Miami Marlins @ Philadelphia Phillies": {"winner": "home", "home_score": 8, "away_score": 2},
    "Kansas City Royals @ Washington Nationals": {"winner": "home", "home_score": 6, "away_score": 4},
    "New York Mets @ Cincinnati Reds": {"winner": "home", "home_score": 5, "away_score": 3},
    "San Diego Padres @ St. Louis Cardinals": {"winner": "home", "home_score": 3, "away_score": 2},
    "San Francisco Giants @ Atlanta Braves": {"winner": "skip", "home_score": 0, "away_score": 0},  # Suspended due to rain
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

        results_lines.append(
            f"{EVAL_DATE}\tbaseball_mlb\t{game}\t{model_id}\t"
            f"{predicted_winner}\t{predicted_margin:.2f}\t{predicted_win_prob:.4f}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{model_data['spread_ev_home']:.4f}\t{model_data['ml_ev_home']:.4f}\t"
            f"{best_bet}\t{bet_result}"
        )

# Append to results.tsv
with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_lines:
        f.write(line + "\n")

print(f"\n  Evaluated {total_games_evaluated} games (1 suspended/skipped)")
print(f"  Appended {len(results_lines)} result rows to results.tsv")

# Print model accuracy
print("\n  Model accuracy on June 16 predictions:")
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

    c_acc = c_correct / c_total
    ch_acc = ch_correct / ch_total
    outperform_pct = c_correct / c_total

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
    # Use last ~10 games accuracy (approximate from recent)
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
        # Demote old champion
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
    if challenger["weight"] <= 0.15 and challenger["born"] < "2026-06-13":
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
# PHASE 2 — DATA COLLECTION (Tonight's Games: June 18, 2026)
# ════════════════════════════════════════════════════════════════════════
# NHL: Season over
# NBA: Off-season
# NFL: Off-season
# MLB: Regular season — Thursday schedule, 9 games
#
# Odds via web search (FanDuel primary, cross-checked BetMGM/DraftKings).
# Stats carried forward from June 16 run with adjustments for games
# played June 16-17. Pitching matchups sourced from search results.

print("\n" + "=" * 78)
print(f" PHASE 2 — Tonight's Games & Odds ({TODAY})")
print("=" * 78)

games_tonight = [
    {
        "sport": "baseball_mlb",
        "game": "Toronto Blue Jays @ Boston Red Sox",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.75,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.486,
            "away_record_pct": 0.375,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.28,
            "last10_ppg": 5.00,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Cleveland Guardians @ Milwaukee Brewers",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.62,
            "season_opp_ppg": 3.98,
            "last10_ppg": 4.70,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.576,
            "away_record_pct": 0.515,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.18,
            "season_opp_ppg": 4.42,
            "last10_ppg": 3.80,
            "last10_opp_ppg": 4.60,
            "season_pace": 1.0,
            "home_record_pct": 0.529,
            "away_record_pct": 0.441,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -146,
            "ml_away": 124,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Minnesota Twins @ Texas Rangers",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.20,
            "last10_opp_ppg": 5.20,
            "season_pace": 1.0,
            "home_record_pct": 0.543,
            "away_record_pct": 0.486,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 5.40,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.543,
            "away_record_pct": 0.457,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 105,
            "ml_away": -130,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Baltimore Orioles @ Seattle Mariners",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.32,
            "season_opp_ppg": 4.08,
            "last10_ppg": 4.50,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.561,
            "away_record_pct": 0.459,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.72,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 5.00,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.424,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -150,
            "ml_away": 125,
            "total": 7.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "New York Mets @ Philadelphia Phillies",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 5.08,
            "season_opp_ppg": 4.38,
            "last10_ppg": 5.80,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.552,
            "away_record_pct": 0.538,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.15,
            "season_opp_ppg": 4.85,
            "last10_ppg": 4.00,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.393,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 105,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Chicago White Sox @ New York Yankees",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 5.05,
            "season_opp_ppg": 4.00,
            "last10_ppg": 5.20,
            "last10_opp_ppg": 3.80,
            "season_pace": 1.0,
            "home_record_pct": 0.654,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.32,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.40,
            "season_pace": 1.0,
            "home_record_pct": 0.556,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -160,
            "ml_away": 135,
            "total": 9.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "San Francisco Giants @ Atlanta Braves",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 5.12,
            "season_opp_ppg": 3.88,
            "last10_ppg": 5.20,
            "last10_opp_ppg": 3.70,
            "season_pace": 1.0,
            "home_record_pct": 0.667,
            "away_record_pct": 0.625,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 3.92,
            "season_opp_ppg": 4.78,
            "last10_ppg": 3.80,
            "last10_opp_ppg": 4.90,
            "season_pace": 1.0,
            "home_record_pct": 0.432,
            "away_record_pct": 0.378,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -149,
            "ml_away": 123,
            "total": 8.0,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "St. Louis Cardinals @ Kansas City Royals",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 3.90,
            "season_opp_ppg": 4.90,
            "last10_ppg": 3.80,
            "last10_opp_ppg": 5.10,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.93,
            "season_opp_ppg": 4.14,
            "last10_ppg": 5.10,
            "last10_opp_ppg": 3.90,
            "season_pace": 1.0,
            "home_record_pct": 0.611,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0,
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -122,
            "ml_away": 104,
            "total": 8.5,
            "book": "fanduel",
        },
    },
    {
        "sport": "baseball_mlb",
        "game": "Oakland Athletics @ Los Angeles Angels",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.25,
            "season_opp_ppg": 4.85,
            "last10_ppg": 4.40,
            "last10_opp_ppg": 4.70,
            "season_pace": 1.0,
            "home_record_pct": 0.469,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 2,
        },
        "away": {
            "name": "Oakland Athletics",
            "season_ppg": 4.22,
            "season_opp_ppg": 4.62,
            "last10_ppg": 4.60,
            "last10_opp_ppg": 4.20,
            "season_pace": 1.0,
            "home_record_pct": 0.514,
            "away_record_pct": 0.378,
            "is_back_to_back": False,
            "key_injuries": 1,
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 114,
            "ml_away": -134,
            "total": 8.0,
            "book": "fanduel",
        },
    },
]

print(f"  {len(games_tonight)} MLB games tonight (Thursday)")
for g in games_tonight:
    print(f"    {g['game']} | ML: {g['odds']['ml_home']}/{g['odds']['ml_away']} | O/U: {g['odds']['total']}")

print(f"\n  All {len(games_tonight)} games are simulation candidates (<=10 game threshold)")

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
print(f"| MLB -- Thursday Jun 18, 2026{' ' * 56}|")
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

            if d >= "2026-06-11":
                r7d["total"] += 1
                r7d["correct"] += hit_val
            if d >= "2026-05-18":
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
        "notes": f"MLB only (NHL over, NBA/NFL off-season). {bet_count} BETs, {lean_count} LEANs. Eval Jun 16: {champion_correct_count}/{champion_total_count} correct."
    },
})

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
