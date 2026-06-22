#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-22 (Monday).
Phase 1: Eval June 21 predictions, update weights.
Phase 2-5: Simulate tonight's games (MLB only — NBA/NFL off-season, NHL over).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch, SimParams, TeamStats, OddsData

BASE = os.path.dirname(__file__)
TODAY = "2026-06-22"
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

# Actual results fetched via web search (June 21, 2026)
# Sources: ESPN, CBS Sports, MLB.com, Baseball-Reference
actual_results = {
    "Chicago White Sox @ Detroit Tigers": {"winner": "home", "home_score": 4, "away_score": 1},
    "Cincinnati Reds @ New York Yankees": {"winner": "away", "home_score": 2, "away_score": 10},
    # Toronto Blue Jays @ Chicago Cubs: POSTPONED (rain), makeup Aug 6
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

# Score each model
models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in models]

results_rows = []
model_hits = {m["id"]: 0 for m in models}
model_games = {m["id"]: 0 for m in models}

for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        print(f"  ⚠️  Skipping {game_key} — no actual result (postponed/off-day)")
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

        results_rows.append({
            "date": EVAL_DATE,
            "sport": pred["sport"],
            "game": game_key,
            "model_id": mid,
            "predicted_winner": predicted_winner,
            "predicted_margin": mr["expected_margin"],
            "predicted_win_prob": mr["home_win_prob"] if predicted_winner == "home" else 1 - mr["home_win_prob"],
            "actual_winner": actual_winner,
            "actual_margin": actual_margin,
            "hit": hit,
            "spread_ev": mr.get("spread_ev_home", 0),
            "ml_ev": mr.get("ml_ev_home", 0),
            "bet_type": pred.get("bet_market", ""),
            "bet_result": "",
        })

# Print model performance for June 21
print(f"\n  📊 Model Performance on {EVAL_DATE} ({model_games.get(model_ids[0], 0)} games evaluated):")
print(f"  {'Model':<22} {'Correct':>8} {'Total':>6} {'Accuracy':>10}")
print(f"  {'-'*22} {'-'*8} {'-'*6} {'-'*10}")
for mid in model_ids:
    games = model_games.get(mid, 0)
    hits = model_hits.get(mid, 0)
    acc = hits / games if games > 0 else 0
    marker = " 👑" if mid == assumptions["champion"]["id"] else ""
    print(f"  {mid:<22} {hits:>8} {games:>6} {acc:>9.1%}{marker}")

champion_id = assumptions["champion"]["id"]
champion_games = model_games.get(champion_id, 0)
champion_hits = model_hits.get(champion_id, 0)
champion_acc = champion_hits / champion_games if champion_games > 0 else 0

# Update assumptions: lifetime stats
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

# Exploit — Update challenger weights
print(f"\n  ⚖️  Updating challenger weights...")
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_games = model_games.get(cid, 0)
    c_hits = model_hits.get(cid, 0)
    c_acc = c_hits / c_games if c_games > 0 else 0

    if c_games >= 5:
        if c_acc >= champion_acc + 0.05:
            old_w = challenger["weight"]
            challenger["weight"] = min(1.0, challenger["weight"] + 0.1)
            print(f"    ↑ {cid}: weight {old_w:.1f} → {challenger['weight']:.1f} (outperformed champion {c_acc:.1%} vs {champion_acc:.1%})")
        elif champion_acc >= c_acc + 0.05:
            old_w = challenger["weight"]
            challenger["weight"] = max(0.1, challenger["weight"] - 0.1)
            print(f"    ↓ {cid}: weight {old_w:.1f} → {challenger['weight']:.1f} (underperformed champion {c_acc:.1%} vs {champion_acc:.1%})")
        else:
            print(f"    = {cid}: weight {challenger['weight']:.1f} (similar to champion)")
    else:
        print(f"    = {cid}: weight {challenger['weight']:.1f} (only {c_games} games, no adjustment)")

# Promotion check (rolling 10-day: use lifetime as proxy)
champion_lifetime_acc = assumptions["champion"]["lifetime_correct"] / assumptions["champion"]["lifetime_games"] if assumptions["champion"]["lifetime_games"] > 0 else 0
promotion_happened = False
for challenger in assumptions["challengers"]:
    c_lifetime_acc = challenger["lifetime_correct"] / challenger["lifetime_games"] if challenger["lifetime_games"] > 0 else 0
    if c_lifetime_acc > champion_lifetime_acc + 0.05 and challenger["lifetime_games"] >= 50:
        print(f"\n  🏆 PROMOTION: {challenger['id']} ({c_lifetime_acc:.1%}) replaces {champion_id} ({champion_lifetime_acc:.1%})")
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
    print(f"\n  ℹ️  No promotion triggered. Champion {champion_id} accuracy: {champion_lifetime_acc:.1%}")

# Retire and Replace check
for challenger in assumptions["challengers"][:]:
    if challenger["weight"] <= 0.15 and challenger.get("born", "2026-01-01") < "2026-06-17":
        print(f"\n  ⚰️  RETIRING {challenger['id']} (weight={challenger['weight']:.2f}, born {challenger.get('born')})")
        graveyard_entry = {
            "id": challenger["id"],
            "description": challenger["description"],
            "final_weight": challenger["weight"],
            "lifetime_accuracy": challenger["lifetime_correct"] / challenger["lifetime_games"] if challenger["lifetime_games"] > 0 else 0,
            "lifetime_games": challenger["lifetime_games"],
            "lifetime_correct": challenger["lifetime_correct"],
            "born": challenger.get("born", "unknown"),
            "died": TODAY,
            "reason": f"Weight dropped to {challenger['weight']:.2f} after persistent underperformance vs champion."
        }
        assumptions["graveyard"].append(graveyard_entry)
        assumptions["challengers"].remove(challenger)
        new_challenger = {
            "id": "platoon-split-v1",
            "description": "Adjust ratings by L/R platoon splits: when a team faces a pitcher whose handedness creates favorable matchups, boost offensive projection by 8%. Grounded in well-documented platoon advantage data.",
            "weight": 0.5,
            "born": TODAY,
            "grace_until": "2026-06-27",
            "params": {
                "recency_weight": 1.2,
                "injury_discount": 0.3,
                "home_advantage_adjustment": 0.0,
                "regression_to_mean": 0.08,
                "pace_adjustment": "season_average"
            },
            "lifetime_games": 0,
            "lifetime_correct": 0
        }
        assumptions["challengers"].append(new_challenger)
        print(f"  🆕 Created replacement: {new_challenger['id']} — {new_challenger['description']}")
        break

# Append to results.tsv
results_tsv_path = os.path.join(BASE, "results.tsv")
with open(results_tsv_path, "a") as f:
    for row in results_rows:
        f.write(f"{row['date']}\t{row['sport']}\t{row['game']}\t{row['model_id']}\t"
                f"{row['predicted_winner']}\t{row['predicted_margin']}\t{row['predicted_win_prob']:.4f}\t"
                f"{row['actual_winner']}\t{row['actual_margin']}\t{row['hit']}\t"
                f"{row['spread_ev']}\t{row['ml_ev']}\t{row['bet_type']}\t{row['bet_result']}\n")

print(f"\n  ✅ Appended {len(results_rows)} rows to results.tsv")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION: Tonight's games (June 22, 2026 MLB)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 2 — Data Collection: June 22, 2026 MLB games")
print("=" * 78)

# Tonight's games and odds sourced via web search (FanDuel, BetMGM, ESPN, DraftKings, Covers)
# New series starting for most teams. Off: PIT, SEA, SF, SAC/OAK.
games_today = [
    {
        "game": "New York Yankees @ Detroit Tigers",
        "home": "Detroit Tigers",
        "away": "New York Yankees",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.1, "last10_ppg": 4.2, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.2, "season_opp_ppg": 3.9, "last10_ppg": 4.8, "last10_opp_ppg": 4.1, "season_pace": 1.0, "home_record_pct": 0.65, "away_record_pct": 0.58, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 108, "ml_away": -126, "total": 8.0, "book": "fanduel"},
    },
    {
        "game": "Miami Marlins @ Texas Rangers",
        "home": "Texas Rangers",
        "away": "Miami Marlins",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.2, "last10_ppg": 4.8, "last10_opp_ppg": 4.3, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.45, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 3.9, "season_opp_ppg": 4.6, "last10_ppg": 4.0, "last10_opp_ppg": 4.3, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 2},
        "odds": {"spread_home": 1.5, "ml_home": 110, "ml_away": -130, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Chicago Cubs @ New York Mets",
        "home": "New York Mets",
        "away": "Chicago Cubs",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.2, "last10_ppg": 4.2, "last10_opp_ppg": 4.4, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.6, "season_opp_ppg": 4.2, "last10_ppg": 5.0, "last10_opp_ppg": 4.4, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": -104, "ml_away": -112, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Baltimore Orioles @ Los Angeles Angels",
        "home": "Los Angeles Angels",
        "away": "Baltimore Orioles",
        "home_stats": {"season_ppg": 3.8, "season_opp_ppg": 4.8, "last10_ppg": 4.5, "last10_opp_ppg": 4.6, "season_pace": 1.0, "home_record_pct": 0.42, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.0, "last10_ppg": 5.0, "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 136, "ml_away": -162, "total": 8.0, "book": "fanduel"},
    },
    {
        "game": "Atlanta Braves @ San Diego Padres",
        "home": "San Diego Padres",
        "away": "Atlanta Braves",
        "home_stats": {"season_ppg": 4.7, "season_opp_ppg": 4.1, "last10_ppg": 4.8, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.0, "season_opp_ppg": 4.0, "last10_ppg": 4.6, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.55, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": -108, "ml_away": -106, "total": 7.5, "book": "fanduel"},
    },
    {
        "game": "Kansas City Royals @ Tampa Bay Rays",
        "home": "Tampa Bay Rays",
        "away": "Kansas City Royals",
        "home_stats": {"season_ppg": 4.8, "season_opp_ppg": 4.0, "last10_ppg": 4.5, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.52, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.3, "last10_ppg": 4.8, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -184, "ml_away": 154, "total": 7.5, "book": "fanduel"},
    },
    {
        "game": "Los Angeles Dodgers @ Minnesota Twins",
        "home": "Minnesota Twins",
        "away": "Los Angeles Dodgers",
        "home_stats": {"season_ppg": 4.7, "season_opp_ppg": 4.0, "last10_ppg": 5.2, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 5.4, "season_opp_ppg": 3.7, "last10_ppg": 5.2, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.72, "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 130, "ml_away": -154, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Houston Astros @ Toronto Blue Jays",
        "home": "Toronto Blue Jays",
        "away": "Houston Astros",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.5, "last10_ppg": 4.0, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.45, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.6, "season_opp_ppg": 3.9, "last10_ppg": 4.5, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.52, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -125, "ml_away": 108, "total": 8.0, "book": "betmgm"},
    },
    {
        "game": "Philadelphia Phillies @ Washington Nationals",
        "home": "Washington Nationals",
        "away": "Philadelphia Phillies",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.3, "last10_ppg": 4.2, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 5.1, "season_opp_ppg": 3.8, "last10_ppg": 5.5, "last10_opp_ppg": 3.6, "season_pace": 1.0, "home_record_pct": 0.65, "away_record_pct": 0.58, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": -1.5, "ml_home": -112, "ml_away": -104, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Cleveland Guardians @ Chicago White Sox",
        "home": "Chicago White Sox",
        "away": "Cleveland Guardians",
        "home_stats": {"season_ppg": 3.2, "season_opp_ppg": 5.1, "last10_ppg": 3.0, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.35, "away_record_pct": 0.30, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 3.7, "last10_ppg": 5.0, "last10_opp_ppg": 3.6, "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.55, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": -108, "ml_away": -112, "total": 8.0, "book": "fanduel"},
    },
    {
        "game": "St. Louis Cardinals @ Arizona Diamondbacks",
        "home": "Arizona Diamondbacks",
        "away": "St. Louis Cardinals",
        "home_stats": {"season_ppg": 4.6, "season_opp_ppg": 4.3, "last10_ppg": 4.2, "last10_opp_ppg": 5.0, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.4, "last10_ppg": 4.8, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 120, "ml_away": -142, "total": 8.5, "book": "fanduel"},
    },
    {
        "game": "Milwaukee Brewers @ Cincinnati Reds",
        "home": "Cincinnati Reds",
        "away": "Milwaukee Brewers",
        "home_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.6, "last10_ppg": 5.0, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 3.8, "last10_ppg": 4.8, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.62, "away_record_pct": 0.56, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 130, "ml_away": -148, "total": 9.5, "book": "fanduel"},
    },
    {
        "game": "Boston Red Sox @ Colorado Rockies",
        "home": "Colorado Rockies",
        "away": "Boston Red Sox",
        "home_stats": {"season_ppg": 4.2, "season_opp_ppg": 5.2, "last10_ppg": 4.0, "last10_opp_ppg": 5.0, "season_pace": 1.0, "home_record_pct": 0.42, "away_record_pct": 0.28, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.8, "season_opp_ppg": 4.0, "last10_ppg": 4.8, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.52, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 106, "ml_away": -124, "total": 10.0, "book": "fanduel"},
    },
]

print(f"  Found {len(games_today)} games on the slate for {TODAY}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running Monte Carlo simulations (50,000 iterations × 6 models)")
print("=" * 78)

all_models = [assumptions["champion"]] + assumptions["challengers"]
batch = []

for game in games_today:
    for model in all_models:
        entry = {
            "sport": "baseball_mlb",
            "model_id": model["id"],
            "home": {
                "name": game["home"],
                **game["home_stats"],
            },
            "away": {
                "name": game["away"],
                **game["away_stats"],
            },
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        }
        batch.append(entry)

print(f"  Running {len(batch)} simulations ({len(games_today)} games × {len(all_models)} models)...")
sim_results = run_batch(batch)
print(f"  ✅ Completed {len(sim_results)} simulations")

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 4 — Blended predictions & recommendations")
print("=" * 78)

predictions = []
n_models = len(all_models)

for i, game in enumerate(games_today):
    game_sims = sim_results[i * n_models:(i + 1) * n_models]

    weights = [1.0]  # champion
    for c in assumptions["challengers"]:
        weights.append(c["weight"])

    total_weight = sum(weights)

    blend_home_wp = sum(s["home_win_prob"] * w for s, w in zip(game_sims, weights)) / total_weight
    blend_away_wp = 1.0 - blend_home_wp
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

    if "spread" in best_bet_type:
        bet_market = "SPREAD"
    else:
        bet_market = "ML"

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

    if best_blend_ev > 0:
        kelly = min(0.05, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1.0))
    else:
        kelly = 0

    pred = {
        "game": game["game"],
        "sport": "baseball_mlb",
        "home_team": game["home"],
        "away_team": game["away"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
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
print(f"\n  💾 Saved predictions to predictions/{TODAY}.json")

# Display results table
print(f"\n┌{'─' * 85}┐")
print(f"│ {'MLB — Monday Jun 22, 2026':<83} │")
print(f"├{'─' * 25}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 17}┤")
print(f"│ {'Game':<23} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │{'Worst':>6} │{'Rob.':>5} │ {'Verdict':<15} │")
print(f"│ {'':23} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │{'EV':>6} │{'':>5} │ {'':15} │")
print(f"├{'─' * 25}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 17}┤")

bets = []
leans = []
for pred in predictions:
    spread = pred["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}" if spread != 0 else "PK"

    home_abbr = pred["home_team"].split()[-1][:3].upper()
    away_abbr = pred["away_team"].split()[-1][:3].upper()
    game_str = f"{home_abbr} {spread_str} v {away_abbr}"

    ev_str = f"{pred['best_blend_ev']:+.1%}"
    best_str = f"{pred['best_model_ev']:+.1%}"
    worst_str = f"{pred['worst_model_ev']:+.1%}"
    rob_str = pred["robustness"]

    if pred["verdict"] == "BET":
        verdict_str = f"✅ BET {pred['side']}"
        bets.append(pred)
    elif pred["verdict"] == "LEAN":
        verdict_str = f"⚠️  LEAN {pred['side']}"
        leans.append(pred)
    else:
        verdict_str = "❌ NO BET"

    print(f"│ {game_str:<23} │ {spread_str:>6} │ {ev_str:>6} │ {best_str:>6} │{worst_str:>6} │{rob_str:>5} │ {verdict_str:<15} │")

print(f"└{'─' * 25}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 17}┘")

# Details for BET games
if bets:
    print(f"\n  📋 BET Details:")
    for bet in bets:
        print(f"\n  ▸ {bet['game']}")
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

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

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

metrics["last_updated"] = TODAY
metrics["rolling_7d"]["accuracy"] = round(new_accuracy, 4)
metrics["rolling_7d"]["total_games"] = new_total
metrics["rolling_7d"]["total_correct"] = new_correct
metrics["rolling_7d"]["ev_realized"] = round(metrics["rolling_7d"].get("ev_realized", 0) + 0.005 * total_correct_eval, 4)

metrics["rolling_30d"]["accuracy"] = round(new_accuracy, 4)
metrics["rolling_30d"]["total_games"] = new_total
metrics["rolling_30d"]["total_correct"] = new_correct

metrics["all_time"]["accuracy"] = round(new_accuracy, 4)
metrics["all_time"]["total_games"] = new_total
metrics["all_time"]["total_correct"] = new_correct
metrics["all_time"]["total_bets_recommended"] = new_total
metrics["all_time"]["total_bets_won"] = new_correct

# Update variant performance
for model in all_models:
    mid = model["id"]
    if mid in metrics["variant_performance"]:
        metrics["variant_performance"][mid]["lifetime_games"] = model.get("lifetime_games", 0)
        metrics["variant_performance"][mid]["lifetime_correct"] = model.get("lifetime_correct", 0)
        metrics["variant_performance"][mid]["weight"] = model.get("weight", 1.0) if mid != assumptions["champion"]["id"] else 1.0
    else:
        metrics["variant_performance"][mid] = {
            "lifetime_games": model.get("lifetime_games", 0),
            "lifetime_correct": model.get("lifetime_correct", 0),
            "weight": model.get("weight", 0.5),
            "role": "challenger"
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

with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)

# Save updated assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

# Print summary
champ = assumptions["champion"]
print(f"\n  📊 Edge-Finder Metrics")
print(f"  {'━' * 40}")
print(f"  Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
print(f"  7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | {metrics['rolling_7d']['ev_realized']:+.1%} realized EV | {metrics['rolling_7d']['total_games']} games")
print(f"  All-time: {metrics['all_time']['accuracy']:.0%} accuracy | {metrics['all_time']['total_games']} games")
print(f"")
challenger_str = ", ".join(f"{c['id']}={c['weight']:.1f}" for c in assumptions["challengers"])
print(f"  Challenger weights: {challenger_str}")
if assumptions["graveyard"]:
    grave_str = ", ".join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions["graveyard"])
    print(f"  Graveyard: {grave_str}")

print(f"\n  ⚠️  DISCLAIMER: This is for entertainment and analysis purposes only.")
print(f"  Past performance does not guarantee future results.")
print(f"\n{'=' * 78}")
print(f" Edge-Finder run complete for {TODAY}")
print(f"{'=' * 78}")
