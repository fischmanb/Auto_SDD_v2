#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-23 (Tuesday).
Phase 1: Eval June 21 predictions (June 22 had no predictions), update weights.
Phase 2-5: Simulate tonight's games (MLB only).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-23"
EVAL_DATE = "2026-06-21"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 21 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-21 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from June 21, 2026 — verified via ESPN game pages
actual_results = {
    "Chicago White Sox @ Detroit Tigers": {"winner": "home", "home_score": 5, "away_score": 4},
    "Cincinnati Reds @ New York Yankees": {"winner": "away", "home_score": 1, "away_score": 4},
    # Toronto Blue Jays @ Chicago Cubs: POSTPONED (rain) — skip
    "Washington Nationals @ Tampa Bay Rays": {"winner": "home", "home_score": 4, "away_score": 3},
    "San Francisco Giants @ Miami Marlins": {"winner": "home", "home_score": 2, "away_score": 1},
    "Milwaukee Brewers @ Atlanta Braves": {"winner": "away", "home_score": 4, "away_score": 9},
    "Texas Rangers @ San Diego Padres": {"winner": "away", "home_score": 3, "away_score": 4},
    "Cleveland Guardians @ Houston Astros": {"winner": "home", "home_score": 2, "away_score": 1},
    "St. Louis Cardinals @ Kansas City Royals": {"winner": "away", "home_score": 10, "away_score": 12},
    "New York Mets @ Philadelphia Phillies": {"winner": "home", "home_score": 6, "away_score": 2},
    "Pittsburgh Pirates @ Colorado Rockies": {"winner": "away", "home_score": 6, "away_score": 8},
    "Los Angeles Angels @ Sacramento Athletics": {"winner": "away", "home_score": 7, "away_score": 9},
    "Minnesota Twins @ Arizona Diamondbacks": {"winner": "away", "home_score": 2, "away_score": 4},
    "Baltimore Orioles @ Los Angeles Dodgers": {"winner": "away", "home_score": 1, "away_score": 12},
    "Boston Red Sox @ Seattle Mariners": {"winner": "home", "home_score": 3, "away_score": 1},
}

models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in models]

results_rows = []
model_hits = {m["id"]: 0 for m in models}
model_games = {m["id"]: 0 for m in models}

for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        print(f"  Skipping {game_key} (postponed or no result)")
        continue

    actual = actual_results[game_key]
    actual_winner = actual["winner"]
    actual_margin = actual["home_score"] - actual["away_score"]

    for mid in model_ids:
        if mid not in pred["model_results"]:
            continue
        mr = pred["model_results"][mid]
        predicted_winner = "home" if mr["expected_margin"] > 0 else "away"
        hit = 1 if predicted_winner == actual_winner else 0

        model_hits[mid] = model_hits.get(mid, 0) + hit
        model_games[mid] = model_games.get(mid, 0) + 1

        best_ev_type = max(
            [("spread_home", mr["spread_ev_home"]),
             ("spread_away", mr["spread_ev_away"]),
             ("ml_home", mr["ml_ev_home"]),
             ("ml_away", mr["ml_ev_away"])],
            key=lambda x: x[1]
        )
        bet_type = best_ev_type[0]

        spread = pred["odds"]["spread_home"]
        if bet_type == "spread_home":
            bet_won = (actual_margin + spread) > 0
        elif bet_type == "spread_away":
            bet_won = (-actual_margin - spread) > 0
        elif bet_type == "ml_home":
            bet_won = actual_winner == "home"
        else:
            bet_won = actual_winner == "away"

        bet_result = "win" if bet_won else "loss"

        results_rows.append(
            f"{EVAL_DATE}\tbaseball_mlb\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']:.2f}\t{mr['home_win_prob']:.4f}\t"
            f"{actual_winner}\t{actual_margin}\t{hit}\t"
            f"{mr['spread_ev_home']:.4f}\t{mr['ml_ev_home']:.4f}\t{bet_type}\t{bet_result}"
        )

# Print model performance
print(f"\n  Model Performance on {EVAL_DATE} ({model_games.get(model_ids[0], 0)} games evaluated):")
print(f"  {'Model':<22} {'Correct':>8} {'Total':>6} {'Accuracy':>10}")
print(f"  {'-'*22} {'-'*8} {'-'*6} {'-'*10}")
for mid in model_ids:
    games = model_games.get(mid, 0)
    hits = model_hits.get(mid, 0)
    acc = hits / games if games > 0 else 0
    marker = " CHAMP" if mid == assumptions["champion"]["id"] else ""
    print(f"  {mid:<22} {hits:>8} {games:>6} {acc:>9.1%}{marker}")

champion_id = assumptions["champion"]["id"]
champion_games = model_games.get(champion_id, 0)
champion_hits = model_hits.get(champion_id, 0)
champion_acc = champion_hits / champion_games if champion_games > 0 else 0

# Update lifetime stats
for pred_game in past_preds["predictions"]:
    game_key = pred_game["game"]
    if game_key not in actual_results:
        continue
    actual = actual_results[game_key]
    actual_winner = actual["winner"]
    for model in models:
        mid = model["id"]
        if mid in pred_game["model_results"]:
            mr = pred_game["model_results"][mid]
            predicted_winner = "home" if mr["expected_margin"] > 0 else "away"
            model["lifetime_games"] = model.get("lifetime_games", 0) + 1
            if predicted_winner == actual_winner:
                model["lifetime_correct"] = model.get("lifetime_correct", 0) + 1

# Step 1.4: Update challenger weights
print(f"\n  Updating challenger weights...")
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_games = model_games.get(cid, 0)
    c_hits = model_hits.get(cid, 0)
    c_acc = c_hits / c_games if c_games > 0 else 0

    if c_games >= 5:
        if c_acc >= champion_acc + 0.05:
            old_w = challenger["weight"]
            challenger["weight"] = min(1.0, round(challenger["weight"] + 0.1, 2))
            print(f"    UP {cid}: weight {old_w:.1f} -> {challenger['weight']:.1f} (outperformed champion {c_acc:.1%} vs {champion_acc:.1%})")
        elif champion_acc >= c_acc + 0.05:
            old_w = challenger["weight"]
            challenger["weight"] = max(0.1, round(challenger["weight"] - 0.1, 2))
            print(f"    DN {cid}: weight {old_w:.1f} -> {challenger['weight']:.1f} (underperformed champion {c_acc:.1%} vs {champion_acc:.1%})")
        else:
            print(f"    == {cid}: weight {challenger['weight']:.1f} (similar to champion)")
    else:
        print(f"    == {cid}: weight {challenger['weight']:.1f} (only {c_games} games, no adjustment)")

# Step 1.5: Promotion check
champion_lifetime_acc = assumptions["champion"]["lifetime_correct"] / assumptions["champion"]["lifetime_games"] if assumptions["champion"]["lifetime_games"] > 0 else 0
promotion_happened = False
for challenger in assumptions["challengers"]:
    c_lifetime_acc = challenger["lifetime_correct"] / challenger["lifetime_games"] if challenger["lifetime_games"] > 0 else 0
    if c_lifetime_acc > champion_lifetime_acc + 0.05 and challenger["lifetime_games"] >= 50:
        print(f"\n  PROMOTION: {challenger['id']} ({c_lifetime_acc:.1%}) replaces {champion_id} ({champion_lifetime_acc:.1%})")
        old_champion = assumptions["champion"].copy()
        old_champion["weight"] = 0.7
        assumptions["challengers"] = [c for c in assumptions["challengers"] if c["id"] != challenger["id"]]
        assumptions["challengers"].append(old_champion)
        challenger["promoted_on"] = TODAY
        challenger["rolling_10d_accuracy"] = c_lifetime_acc
        assumptions["champion"] = challenger
        promotion_happened = True
        break

if not promotion_happened:
    print(f"\n  No promotion triggered. Champion {champion_id} accuracy: {champion_lifetime_acc:.1%}")

# Step 1.6: Retire and Replace
for challenger in assumptions["challengers"][:]:
    if challenger["weight"] <= 0.15 and challenger.get("born", "2026-01-01") < "2026-06-18":
        print(f"\n  RETIRING {challenger['id']} (weight={challenger['weight']:.2f}, born {challenger.get('born')})")
        graveyard_entry = {
            "id": challenger["id"],
            "description": challenger["description"],
            "final_weight": challenger["weight"],
            "lifetime_accuracy": round(challenger["lifetime_correct"] / challenger["lifetime_games"], 4) if challenger["lifetime_games"] > 0 else 0,
            "lifetime_games": challenger["lifetime_games"],
            "lifetime_correct": challenger["lifetime_correct"],
            "born": challenger.get("born", "unknown"),
            "died": TODAY,
            "reason": f"Weight dropped to {challenger['weight']:.2f} after persistent underperformance vs champion."
        }
        assumptions["graveyard"].append(graveyard_entry)
        assumptions["challengers"].remove(challenger)
        new_challenger = {
            "id": "rest-days-v1",
            "description": "Adjust for days of rest between games: teams on 2+ days rest get a small boost (+0.15 runs), teams on 0 days rest (day games after night games) get a penalty. Based on fatigue research showing measurable decline in batting averages and exit velocity in compressed schedules.",
            "weight": 0.5,
            "born": TODAY,
            "grace_until": "2026-06-28",
            "params": {
                "recency_weight": 1.2,
                "injury_discount": 0.3,
                "home_advantage_adjustment": 0.0,
                "regression_to_mean": 0.05,
                "pace_adjustment": "season_average"
            },
            "lifetime_games": 0,
            "lifetime_correct": 0
        }
        assumptions["challengers"].append(new_challenger)
        print(f"  NEW: {new_challenger['id']} -- {new_challenger['description'][:80]}...")
        break

# Append to results.tsv
results_tsv_path = os.path.join(BASE, "results.tsv")
with open(results_tsv_path, "a") as f:
    for row in results_rows:
        f.write(row + "\n")

print(f"\n  Appended {len(results_rows)} rows to results.tsv")

# Save updated assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("  assumptions.json updated.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION: Tonight's games (June 23, 2026 MLB)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2 — Data Collection: June 23, 2026 MLB games")
print(f"{'=' * 78}")

# Tonight's games and odds sourced via web search (ESPN, FanDuel, BetMGM, Covers, DraftKings)
games_today = [
    {
        "game": "Houston Astros @ Toronto Blue Jays",
        "home": "Toronto Blue Jays",
        "away": "Houston Astros",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.3, "last10_ppg": 4.8, "last10_opp_ppg": 4.3, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.45, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.0, "last10_ppg": 4.2, "last10_opp_ppg": 4.1, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -132, "ml_away": 112, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "New York Yankees @ Detroit Tigers",
        "home": "Detroit Tigers",
        "away": "New York Yankees",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.1, "last10_ppg": 4.5, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.0, "season_opp_ppg": 3.9, "last10_ppg": 4.5, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.66, "away_record_pct": 0.56, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": -104, "ml_away": -112, "total": 7.5, "book": "fanduel"},
    },
    {
        "game": "Kansas City Royals @ Tampa Bay Rays",
        "home": "Tampa Bay Rays",
        "away": "Kansas City Royals",
        "home_stats": {"season_ppg": 4.6, "season_opp_ppg": 3.9, "last10_ppg": 4.5, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.55, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.2, "season_opp_ppg": 4.4, "last10_ppg": 4.0, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -190, "ml_away": 155, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Philadelphia Phillies @ Washington Nationals",
        "home": "Washington Nationals",
        "away": "Philadelphia Phillies",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.3, "last10_ppg": 4.2, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 5.1, "season_opp_ppg": 3.8, "last10_ppg": 5.5, "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.68, "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 145, "ml_away": -173, "total": 8.0, "book": "fanduel"},
    },
    {
        "game": "Chicago Cubs @ New York Mets",
        "home": "New York Mets",
        "away": "Chicago Cubs",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.2, "last10_ppg": 4.0, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.6, "season_opp_ppg": 4.2, "last10_ppg": 5.1, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -120, "ml_away": 102, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Cleveland Guardians @ Chicago White Sox",
        "home": "Chicago White Sox",
        "away": "Cleveland Guardians",
        "home_stats": {"season_ppg": 3.2, "season_opp_ppg": 5.1, "last10_ppg": 3.0, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.35, "away_record_pct": 0.30, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 3.7, "last10_ppg": 5.0, "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.55, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": -106, "ml_away": -110, "total": 7.5, "book": "fanduel"},
    },
    {
        "game": "Seattle Mariners @ Pittsburgh Pirates",
        "home": "Pittsburgh Pirates",
        "away": "Seattle Mariners",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.1, "last10_ppg": 4.2, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.0, "season_opp_ppg": 3.8, "last10_ppg": 3.5, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 104, "ml_away": -122, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Milwaukee Brewers @ Cincinnati Reds",
        "home": "Cincinnati Reds",
        "away": "Milwaukee Brewers",
        "home_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.6, "last10_ppg": 5.0, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 3.8, "last10_ppg": 4.6, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.62, "away_record_pct": 0.58, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 104, "ml_away": -122, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Los Angeles Dodgers @ Minnesota Twins",
        "home": "Minnesota Twins",
        "away": "Los Angeles Dodgers",
        "home_stats": {"season_ppg": 4.7, "season_opp_ppg": 4.0, "last10_ppg": 5.2, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.52, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 5.4, "season_opp_ppg": 3.7, "last10_ppg": 5.0, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.72, "away_record_pct": 0.62, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 140, "ml_away": -166, "total": 9.0, "book": "fanduel"},
    },
    {
        "game": "Arizona Diamondbacks @ St. Louis Cardinals",
        "home": "St. Louis Cardinals",
        "away": "Arizona Diamondbacks",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.2, "last10_ppg": 4.5, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.6, "season_opp_ppg": 4.3, "last10_ppg": 4.5, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.45, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -112, "ml_away": -104, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Boston Red Sox @ Colorado Rockies",
        "home": "Colorado Rockies",
        "away": "Boston Red Sox",
        "home_stats": {"season_ppg": 4.2, "season_opp_ppg": 5.2, "last10_ppg": 3.8, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.42, "away_record_pct": 0.28, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 4.0, "last10_ppg": 5.2, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 136, "ml_away": -162, "total": 10.5, "book": "betmgm"},
    },
    {
        "game": "Atlanta Braves @ San Diego Padres",
        "home": "San Diego Padres",
        "away": "Atlanta Braves",
        "home_stats": {"season_ppg": 4.7, "season_opp_ppg": 4.1, "last10_ppg": 4.8, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.0, "season_opp_ppg": 4.0, "last10_ppg": 4.5, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.66, "away_record_pct": 0.58, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": -110, "ml_away": -110, "total": 8.0, "book": "fanduel"},
    },
    {
        "game": "Baltimore Orioles @ Los Angeles Angels",
        "home": "Los Angeles Angels",
        "away": "Baltimore Orioles",
        "home_stats": {"season_ppg": 3.8, "season_opp_ppg": 4.8, "last10_ppg": 4.0, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.36, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.6, "season_opp_ppg": 4.0, "last10_ppg": 5.0, "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 125, "ml_away": -155, "total": 8.0, "book": "betmgm"},
    },
]

print(f"  Found {len(games_today)} games on the slate for {TODAY}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 3 — Running Monte Carlo simulations (50,000 iterations x 6 models)")
print(f"{'=' * 78}")

# Reload assumptions after Phase 1 updates
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

all_models = [assumptions["champion"]] + assumptions["challengers"]
batch = []

for game in games_today:
    for model in all_models:
        entry = {
            "sport": "baseball_mlb",
            "model_id": model["id"],
            "home": {"name": game["home"], **game["home_stats"]},
            "away": {"name": game["away"], **game["away_stats"]},
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        }
        batch.append(entry)

print(f"  Running {len(batch)} simulations ({len(games_today)} games x {len(all_models)} models)...")
sim_results = run_batch(batch)
print(f"  Completed {len(sim_results)} simulations")

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 4 — Blended predictions & recommendations")
print(f"{'=' * 78}")

predictions = []
n_models = len(all_models)

for i, game in enumerate(games_today):
    game_sims = sim_results[i * n_models:(i + 1) * n_models]

    weights = [1.0]
    for c in assumptions["challengers"]:
        weights.append(c["weight"])

    total_weight = sum(weights)

    blend_home_wp = sum(s["home_win_prob"] * w for s, w in zip(game_sims, weights)) / total_weight
    blend_margin = sum(s["expected_margin"] * w for s, w in zip(game_sims, weights)) / total_weight

    model_results = {}
    evs_by_model = []
    for s, m in zip(game_sims, all_models):
        model_results[m["id"]] = {
            "home_win_prob": s["home_win_prob"],
            "expected_margin": s["expected_margin"],
            "spread_ev_home": s["spread_ev_home"],
            "spread_ev_away": s["spread_ev_away"],
            "ml_ev_home": s["ml_ev_home"],
            "ml_ev_away": s["ml_ev_away"],
        }
        best_ev = max(s["spread_ev_home"], s["spread_ev_away"], s["ml_ev_home"], s["ml_ev_away"])
        evs_by_model.append(best_ev)

    all_spread_ev_home = [s["spread_ev_home"] for s in game_sims]
    all_spread_ev_away = [s["spread_ev_away"] for s in game_sims]
    all_ml_ev_home = [s["ml_ev_home"] for s in game_sims]
    all_ml_ev_away = [s["ml_ev_away"] for s in game_sims]

    blend_spread_ev_home = sum(e * w for e, w in zip(all_spread_ev_home, weights)) / total_weight
    blend_spread_ev_away = sum(e * w for e, w in zip(all_spread_ev_away, weights)) / total_weight
    blend_ml_ev_home = sum(e * w for e, w in zip(all_ml_ev_home, weights)) / total_weight
    blend_ml_ev_away = sum(e * w for e, w in zip(all_ml_ev_away, weights)) / total_weight

    ev_options = [
        ("spread_home", blend_spread_ev_home),
        ("spread_away", blend_spread_ev_away),
        ("ml_home", blend_ml_ev_home),
        ("ml_away", blend_ml_ev_away),
    ]
    best_bet_type, best_blend_ev = max(ev_options, key=lambda x: x[1])
    best_model_ev = max(evs_by_model)
    worst_model_ev = min(evs_by_model)

    predicted_side = "home" if blend_margin > 0 else "away"
    agree_count = sum(1 for s in game_sims if (s["expected_margin"] > 0) == (predicted_side == "home"))

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"
    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]
    else:
        side = "AWAY"
        side_team = game["away"]

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count >= 3:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = min(0.05, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1.0)) if best_blend_ev > 0 else 0

    pred = {
        "game": game["game"],
        "sport": "baseball_mlb",
        "home_team": game["home"],
        "away_team": game["away"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(1 - blend_home_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(best_blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": f"{agree_count}/{n_models}",
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": model_results,
    }
    predictions.append(pred)

# Save predictions BEFORE displaying
pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump({"date": TODAY, "predictions": predictions}, f, indent=2)
print(f"\n  Saved predictions to predictions/{TODAY}.json")

# Display results table
print(f"\n{'=' * 90}")
print(f" MLB -- Tuesday Jun 23, 2026")
print(f"{'=' * 90}")
print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5}  {'Verdict':<16}")
print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*5}  {'-'*16}")

bets = []
leans = []
for pred in predictions:
    spread = pred["odds"]["spread_home"]
    home_short = pred["home_team"].split()[-1][:6]
    away_short = pred["away_team"].split()[-1][:6]

    if spread < 0:
        game_str = f"{home_short} {spread:+.1f} vs {away_short}"
    elif spread > 0:
        game_str = f"{away_short} @ {home_short} (+{spread:.1f})"
    else:
        game_str = f"{away_short} @ {home_short}"

    if pred["verdict"] == "BET":
        icon = " >>>"
        bets.append(pred)
    elif pred["verdict"] == "LEAN":
        icon = "  > "
        leans.append(pred)
    else:
        icon = "  - "

    verdict_str = f"{icon} {pred['verdict']} {pred['side']}"

    print(f" {game_str:<32} {spread:>+7.1f} {pred['best_blend_ev']:>+8.1%} {pred['best_model_ev']:>+7.1%} {pred['worst_model_ev']:>+6.1%} {pred['robustness']:>5} {verdict_str:<16}")

print(f"{'=' * 90}")

# Details for BET games
if bets:
    print(f"\n  BET Details:")
    for bet in bets:
        print(f"\n  > {bet['game']}")
        print(f"    Side: {bet['side']} ({bet['side_team']}) | Market: {bet['bet_market']} | Book: {bet['odds']['book']}")
        print(f"    Blended EV: {bet['best_blend_ev']:+.2%} | Kelly: {bet['kelly']:.4f} units")
        agreeing = [mid for mid, mr in bet['model_results'].items() if (mr['expected_margin'] > 0) == (bet['side'] == 'HOME')]
        disagreeing = [mid for mid, mr in bet['model_results'].items() if mid not in agreeing]
        print(f"    Agreeing models: {', '.join(agreeing)}")
        if disagreeing:
            print(f"    Disagreeing models: {', '.join(disagreeing)}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 5 — Metrics Dashboard")
print(f"{'=' * 78}")

total_games_eval = model_games.get(champion_id, 0)
total_correct_eval = model_hits.get(champion_id, 0)

metrics_path = os.path.join(BASE, "metrics.json")
with open(metrics_path) as f:
    metrics = json.load(f)

old_total = metrics["all_time"]["total_games"]
old_correct = metrics["all_time"]["total_correct"]

new_total = old_total + total_games_eval
new_correct = old_correct + total_correct_eval
new_accuracy = new_correct / new_total if new_total > 0 else 0

# Score BET results from Jun 21
jun21_bets = [p for p in past_preds["predictions"] if p.get("verdict") == "BET"]
jun21_bet_wins = 0
jun21_bet_total = len(jun21_bets)
for bp in jun21_bets:
    gk = bp["game"]
    if gk not in actual_results:
        continue
    actual = actual_results[gk]
    actual_margin = actual["home_score"] - actual["away_score"]
    bt = bp.get("best_bet_type", "ml_home")
    spread = bp["odds"]["spread_home"]
    if bt == "spread_home":
        won = (actual_margin + spread) > 0
    elif bt == "spread_away":
        won = (-actual_margin - spread) > 0
    elif bt == "ml_home":
        won = actual["winner"] == "home"
    else:
        won = actual["winner"] == "away"
    if won:
        jun21_bet_wins += 1

old_bets = metrics["all_time"].get("total_bets_recommended", 0)
old_bets_won = metrics["all_time"].get("total_bets_won", 0)
new_bets = old_bets + jun21_bet_total
new_bets_won = old_bets_won + jun21_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(total_correct_eval / total_games_eval, 4) if total_games_eval > 0 else 0.5,
    "ev_realized": round((jun21_bet_wins * 0.909 - (jun21_bet_total - jun21_bet_wins)) / max(jun21_bet_total, 1), 4),
    "total_games": total_games_eval,
    "total_correct": total_correct_eval
}
metrics["rolling_30d"] = {
    "accuracy": round(new_accuracy, 4),
    "ev_realized": round((new_bets_won * 0.909 - (new_bets - new_bets_won)) / max(new_bets, 1), 4),
    "total_games": new_total,
    "total_correct": new_correct
}
metrics["all_time"] = {
    "accuracy": round(new_accuracy, 4),
    "ev_realized": round((new_bets_won * 0.909 - (new_bets - new_bets_won)) / max(new_bets, 1), 4),
    "total_games": new_total,
    "total_correct": new_correct,
    "total_bets_recommended": new_bets,
    "total_bets_won": new_bets_won
}

# Update variant performance
for model in all_models:
    mid = model["id"]
    if mid in metrics.get("variant_performance", {}):
        metrics["variant_performance"][mid]["lifetime_games"] = model.get("lifetime_games", 0)
        metrics["variant_performance"][mid]["lifetime_correct"] = model.get("lifetime_correct", 0)
        metrics["variant_performance"][mid]["weight"] = 1.0 if mid == assumptions["champion"]["id"] else model.get("weight", 0.5)
    else:
        metrics.setdefault("variant_performance", {})[mid] = {
            "lifetime_games": model.get("lifetime_games", 0),
            "lifetime_correct": model.get("lifetime_correct", 0),
            "weight": 1.0 if mid == assumptions["champion"]["id"] else model.get("weight", 0.5),
            "role": "champion" if mid == assumptions["champion"]["id"] else "challenger"
        }

metrics["variant_performance"][assumptions["champion"]["id"]]["role"] = "champion"
metrics["variant_performance"][assumptions["champion"]["id"]]["weight"] = 1.0

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(games_today),
    "bets_recommended": len(bets),
    "leans": len(leans),
    "sports": ["baseball_mlb"],
    "notes": f"MLB only. {len(bets)} BETs, {len(leans)} LEANs. Eval Jun 21: {total_correct_eval}/{total_games_eval} correct."
}

# Add champion history if promotion happened
if promotion_happened:
    metrics.setdefault("champion_history", []).append({
        "id": assumptions["champion"]["id"],
        "promoted_on": TODAY,
        "reason": f"Rolling accuracy exceeded predecessor by >=5%"
    })

with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

# Print summary
champ = assumptions["champion"]
print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
print(f"  Jun 21 eval: {total_correct_eval}/{total_games_eval} = {total_correct_eval/max(total_games_eval,1):.1%} accuracy")
print(f"  Jun 21 bets: {jun21_bet_wins}/{jun21_bet_total} = {jun21_bet_wins/max(jun21_bet_total,1):.1%} hit rate")
print(f"  All-time: {new_correct}/{new_total} = {new_accuracy:.1%} accuracy | {new_bets_won}/{new_bets} bets won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in assumptions["challengers"])
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
print(f"\n{'=' * 78}")
print(f" Edge-Finder run complete for {TODAY}")
print(f"{'=' * 78}")
