#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-28 (Sunday).
Phase 1: Eval June 26 predictions, update weights.
Phase 2-5: Simulate tonight's games (MLB only — 15 games).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-28"
EVAL_DATE = "2026-06-26"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 26 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-26 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from June 26, 2026 — verified via ESPN/MLB.com search results
actual_results = {
    "Houston Astros @ Detroit Tigers": {"winner": "home", "home_score": 8, "away_score": 0},
    "Cincinnati Reds @ Pittsburgh Pirates": {"winner": "away", "home_score": 4, "away_score": 6},
    "Washington Nationals @ Baltimore Orioles": {"winner": "away", "home_score": 3, "away_score": 4},
    "Texas Rangers @ Toronto Blue Jays": {"winner": "away", "home_score": 4, "away_score": 5},
    "Seattle Mariners @ Cleveland Guardians": {"winner": "away", "home_score": 1, "away_score": 3},
    "Arizona Diamondbacks @ Tampa Bay Rays": {"winner": "home", "home_score": 6, "away_score": 1},
    "Philadelphia Phillies @ New York Mets": {"winner": "away", "home_score": 1, "away_score": 2},
    "New York Yankees @ Boston Red Sox": {"winner": "home", "home_score": 6, "away_score": 1},
    "Kansas City Royals @ Chicago White Sox": {"winner": "home", "home_score": 22, "away_score": 1},
    "Chicago Cubs @ Milwaukee Brewers": {"winner": "home", "home_score": 6, "away_score": 2},
    "Colorado Rockies @ Minnesota Twins": {"winner": "home", "home_score": 9, "away_score": 8},
    "Miami Marlins @ St. Louis Cardinals": {"winner": "away", "home_score": 0, "away_score": 4},
    "Sacramento Athletics @ Los Angeles Angels": {"winner": "away", "home_score": 3, "away_score": 9},
    "Los Angeles Dodgers @ San Diego Padres": {"winner": "home", "home_score": 7, "away_score": 1},
    "Atlanta Braves @ San Francisco Giants": {"winner": "away", "home_score": 1, "away_score": 3},
}

models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in models]

results_rows = []
model_hits = {m["id"]: 0 for m in models}
model_games = {m["id"]: 0 for m in models}

for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        print(f"  Skipping {game_key} (no result)")
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
            f"{predicted_winner}\t{mr['expected_margin']:.2f}\t"
            f"{mr.get('home_win_prob', 0.5):.4f}\t"
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
    if challenger["weight"] <= 0.15 and challenger.get("born", "2026-01-01") < "2026-06-23":
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
        graveyard_ideas = [g["id"] for g in assumptions.get("graveyard", [])]
        new_challenger = {
            "id": "series-momentum-v1",
            "description": "Series momentum adjustment: teams that won the previous game in a series get a 3% boost to win probability. Hypothesis: pitching staff sequencing and clubhouse energy create carry-over effects within a series.",
            "weight": 0.5,
            "born": TODAY,
            "grace_until": "2026-07-03",
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
# PHASE 2 — DATA COLLECTION: Tonight's games (June 28, 2026 MLB)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2 — Data Collection: June 28, 2026 MLB games (15 games)")
print(f"{'=' * 78}")

# Reload assumptions after Phase 1 updates
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# Tonight's 15 games and odds sourced via web search (FanDuel, ESPN, BetMGM, DraftKings)
# Standings: LAD 52-30, MIL 50-29, ATL 49-31, NYY 48-33, PHI 46-37, TB 46-33,
#            SD 43-37, SEA 42-41, CLE 42-40, CHW 42-38, HOU 40-44, ATH 40-42,
#            STL 38-42, PIT 40-42, CIN 37-43, BAL 39-42, MIN 40-41, WAS 36-44,
#            DET 35-47, NYM 35-48, TOR 34-46, BOS 34-46, KC 34-48, LAA 34-48,
#            SF 33-47, COL 28-53, MIA 30-50, TEX 36-45, ARI 38-43, CHC 35-44

games_today = [
    # 1. HOU @ DET — 4th game at Detroit. HOU -124, DET +106.
    {
        "game": "Houston Astros @ Detroit Tigers",
        "home": "Detroit Tigers",
        "away": "Houston Astros",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.2, "last10_ppg": 4.5, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.1, "last10_ppg": 4.3, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 106, "ml_away": -124, "total": 8.5, "book": "fanduel"},
    },
    # 2. CIN @ PIT — Sunday finale. PIT -132, CIN +112, O/U 9.0. Keller vs Singer.
    {
        "game": "Cincinnati Reds @ Pittsburgh Pirates",
        "home": "Pittsburgh Pirates",
        "away": "Cincinnati Reds",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.0, "last10_ppg": 4.4, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.1, "season_opp_ppg": 4.4, "last10_ppg": 4.5, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.46, "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -132, "ml_away": 112, "total": 9.0, "book": "fanduel"},
    },
    # 3. WAS @ BAL — Bradish vs Littell. BAL -198, WAS +166.
    {
        "game": "Washington Nationals @ Baltimore Orioles",
        "home": "Baltimore Orioles",
        "away": "Washington Nationals",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.1, "last10_ppg": 4.4, "last10_opp_ppg": 3.9, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.46, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.6, "last10_ppg": 4.2, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.48, "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -198, "ml_away": 166, "total": 8.0, "book": "fanduel"},
    },
    # 4. TEX @ TOR — TOR -134, TEX +114, O/U 8.5.
    {
        "game": "Texas Rangers @ Toronto Blue Jays",
        "home": "Toronto Blue Jays",
        "away": "Texas Rangers",
        "home_stats": {"season_ppg": 4.2, "season_opp_ppg": 4.5, "last10_ppg": 4.0, "last10_opp_ppg": 4.6, "season_pace": 1.0, "home_record_pct": 0.48, "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.0, "season_opp_ppg": 4.3, "last10_ppg": 4.4, "last10_opp_ppg": 4.1, "season_pace": 1.0, "home_record_pct": 0.46, "away_record_pct": 0.40, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -134, "ml_away": 114, "total": 8.5, "book": "fanduel"},
    },
    # 5. SEA @ CLE — CLE -115, SEA -105. Close game, at Progressive Field.
    {
        "game": "Seattle Mariners @ Cleveland Guardians",
        "home": "Cleveland Guardians",
        "away": "Seattle Mariners",
        "home_stats": {"season_ppg": 4.4, "season_opp_ppg": 3.8, "last10_ppg": 4.2, "last10_opp_ppg": 3.7, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.0, "season_opp_ppg": 3.7, "last10_ppg": 3.8, "last10_opp_ppg": 3.4, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 7.5, "book": "fanduel"},
    },
    # 6. ARI @ TB — TB -184, ARI +154. Kelly vs Rasmussen. At Tropicana.
    {
        "game": "Arizona Diamondbacks @ Tampa Bay Rays",
        "home": "Tampa Bay Rays",
        "away": "Arizona Diamondbacks",
        "home_stats": {"season_ppg": 4.6, "season_opp_ppg": 3.8, "last10_ppg": 5.1, "last10_opp_ppg": 3.6, "season_pace": 1.0, "home_record_pct": 0.62, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.4, "last10_ppg": 4.3, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.42, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -184, "ml_away": 154, "total": 7.5, "book": "fanduel"},
    },
    # 7. PHI @ NYM — PHI -144, NYM +122. Luzardo vs Perez.
    {
        "game": "Philadelphia Phillies @ New York Mets",
        "home": "New York Mets",
        "away": "Philadelphia Phillies",
        "home_stats": {"season_ppg": 4.4, "season_opp_ppg": 4.3, "last10_ppg": 3.4, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.0, "season_opp_ppg": 3.8, "last10_ppg": 5.2, "last10_opp_ppg": 3.5, "season_pace": 1.0, "home_record_pct": 0.64, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 122, "ml_away": -144, "total": 8.0, "book": "fanduel"},
    },
    # 8. NYY @ BOS — BOS -118, NYY +100. At Fenway Park.
    {
        "game": "New York Yankees @ Boston Red Sox",
        "home": "Boston Red Sox",
        "away": "New York Yankees",
        "home_stats": {"season_ppg": 4.0, "season_opp_ppg": 4.4, "last10_ppg": 4.8, "last10_opp_ppg": 3.8, "season_pace": 1.0, "home_record_pct": 0.48, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 5.0, "season_opp_ppg": 3.9, "last10_ppg": 4.6, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.62, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": -118, "ml_away": 100, "total": 8.5, "book": "fanduel"},
    },
    # 9. KC @ CHW — CHW -125, KC +105. At Guaranteed Rate.
    {
        "game": "Kansas City Royals @ Chicago White Sox",
        "home": "Chicago White Sox",
        "away": "Kansas City Royals",
        "home_stats": {"season_ppg": 4.0, "season_opp_ppg": 4.0, "last10_ppg": 5.5, "last10_opp_ppg": 3.2, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.48, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 3.8, "season_opp_ppg": 4.5, "last10_ppg": 3.4, "last10_opp_ppg": 4.8, "season_pace": 1.0, "home_record_pct": 0.44, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -125, "ml_away": 105, "total": 8.5, "book": "fanduel"},
    },
    # 10. CHC @ MIL — MIL -210, CHC +176. At American Family Field.
    {
        "game": "Chicago Cubs @ Milwaukee Brewers",
        "home": "Milwaukee Brewers",
        "away": "Chicago Cubs",
        "home_stats": {"season_ppg": 4.8, "season_opp_ppg": 3.6, "last10_ppg": 5.0, "last10_opp_ppg": 3.4, "season_pace": 1.0, "home_record_pct": 0.68, "away_record_pct": 0.58, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 3.7, "season_opp_ppg": 4.3, "last10_ppg": 3.4, "last10_opp_ppg": 4.5, "season_pace": 1.0, "home_record_pct": 0.44, "away_record_pct": 0.36, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": -1.5, "ml_home": -210, "ml_away": 176, "total": 8.0, "book": "fanduel"},
    },
    # 11. COL @ MIN — MIN -185, COL +155. At Target Field.
    {
        "game": "Colorado Rockies @ Minnesota Twins",
        "home": "Minnesota Twins",
        "away": "Colorado Rockies",
        "home_stats": {"season_ppg": 4.5, "season_opp_ppg": 4.0, "last10_ppg": 4.8, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.54, "away_record_pct": 0.46, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 3.8, "season_opp_ppg": 5.0, "last10_ppg": 4.0, "last10_opp_ppg": 5.2, "season_pace": 1.0, "home_record_pct": 0.38, "away_record_pct": 0.26, "is_back_to_back": False, "key_injuries": 2},
        "odds": {"spread_home": -1.5, "ml_home": -185, "ml_away": 155, "total": 9.0, "book": "fanduel"},
    },
    # 12. MIA @ STL — STL -134, MIA +114, O/U 9.5. At Busch Stadium.
    {
        "game": "Miami Marlins @ St. Louis Cardinals",
        "home": "St. Louis Cardinals",
        "away": "Miami Marlins",
        "home_stats": {"season_ppg": 4.0, "season_opp_ppg": 4.2, "last10_ppg": 3.6, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.44, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 3.6, "season_opp_ppg": 4.6, "last10_ppg": 3.8, "last10_opp_ppg": 4.4, "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.34, "is_back_to_back": False, "key_injuries": 2},
        "odds": {"spread_home": -1.5, "ml_home": -134, "ml_away": 114, "total": 9.5, "book": "fanduel"},
    },
    # 13. SAC(ATH) @ LAA — ATH -118, LAA +100. At Angel Stadium.
    {
        "game": "Sacramento Athletics @ Los Angeles Angels",
        "home": "Los Angeles Angels",
        "away": "Sacramento Athletics",
        "home_stats": {"season_ppg": 3.9, "season_opp_ppg": 4.5, "last10_ppg": 3.8, "last10_opp_ppg": 4.6, "season_pace": 1.0, "home_record_pct": 0.44, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 2},
        "away_stats": {"season_ppg": 4.2, "season_opp_ppg": 4.2, "last10_ppg": 4.5, "last10_opp_ppg": 4.0, "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.46, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 100, "ml_away": -118, "total": 8.0, "book": "fanduel"},
    },
    # 14. LAD @ SD — LAD -149, SD +123. At Petco Park.
    {
        "game": "Los Angeles Dodgers @ San Diego Padres",
        "home": "San Diego Padres",
        "away": "Los Angeles Dodgers",
        "home_stats": {"season_ppg": 4.3, "season_opp_ppg": 4.0, "last10_ppg": 4.5, "last10_opp_ppg": 4.2, "season_pace": 1.0, "home_record_pct": 0.56, "away_record_pct": 0.50, "is_back_to_back": False, "key_injuries": 0},
        "away_stats": {"season_ppg": 5.2, "season_opp_ppg": 3.5, "last10_ppg": 5.0, "last10_opp_ppg": 3.6, "season_pace": 1.0, "home_record_pct": 0.68, "away_record_pct": 0.60, "is_back_to_back": False, "key_injuries": 1},
        "odds": {"spread_home": 1.5, "ml_home": 123, "ml_away": -149, "total": 7.5, "book": "fanduel"},
    },
    # 15. ATL @ SF — ATL -156, SF +132. At Oracle Park.
    {
        "game": "Atlanta Braves @ San Francisco Giants",
        "home": "San Francisco Giants",
        "away": "Atlanta Braves",
        "home_stats": {"season_ppg": 3.8, "season_opp_ppg": 4.4, "last10_ppg": 3.5, "last10_opp_ppg": 4.6, "season_pace": 1.0, "home_record_pct": 0.46, "away_record_pct": 0.38, "is_back_to_back": False, "key_injuries": 1},
        "away_stats": {"season_ppg": 4.9, "season_opp_ppg": 3.5, "last10_ppg": 4.6, "last10_opp_ppg": 3.4, "season_pace": 1.0, "home_record_pct": 0.66, "away_record_pct": 0.54, "is_back_to_back": False, "key_injuries": 0},
        "odds": {"spread_home": 1.5, "ml_home": 132, "ml_away": -156, "total": 7.5, "book": "fanduel"},
    },
]

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATION
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 3 — Running simulations")
print(f"{'=' * 78}")

# Build batch: each game x each model
games_raw = []
for g in games_today:
    games_raw.append({
        "sport": "baseball_mlb",
        "home": {
            "name": g["home"],
            **g["home_stats"]
        },
        "away": {
            "name": g["away"],
            **g["away_stats"]
        },
        "odds": g["odds"],
    })

batch = []
for game in games_raw:
    for model in all_models:
        entry = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        }
        batch.append(entry)

print(f"\n  Running {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

results = run_batch(batch)

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTIONS & OUTPUT
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 4 — Blended Predictions")
print(f"{'=' * 78}")

# Organize results by game
games_results = {}
for i, result in enumerate(results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game_key = games_today[game_idx]["game"]

    if game_key not in games_results:
        games_results[game_key] = {
            "game_data": games_today[game_idx],
            "model_results": {}
        }
    games_results[game_key]["model_results"][all_models[model_idx]["id"]] = result

# Compute blended predictions
predictions = []
for game_key, data in games_results.items():
    game = data["game_data"]
    model_res = data["model_results"]

    total_weight = 0
    blend_home_wp = 0
    blend_margin = 0
    blend_spread_ev_home = 0
    blend_spread_ev_away = 0
    blend_ml_ev_home = 0
    blend_ml_ev_away = 0

    evs_by_model = {}

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champion["id"] else next((c["weight"] for c in challengers if c["id"] == mid), 0.5)
        r = model_res[mid]

        total_weight += w
        blend_home_wp += w * r["home_win_prob"]
        blend_margin += w * r["expected_margin"]
        blend_spread_ev_home += w * r["spread_ev_home"]
        blend_spread_ev_away += w * r["spread_ev_away"]
        blend_ml_ev_home += w * r["ml_ev_home"]
        blend_ml_ev_away += w * r["ml_ev_away"]

        best_ev = max(r["spread_ev_home"], r["spread_ev_away"],
                      r["ml_ev_home"], r["ml_ev_away"])
        evs_by_model[mid] = {
            "best_ev": best_ev,
            "home_win_prob": r["home_win_prob"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
            "expected_margin": r["expected_margin"],
        }

    blend_home_wp /= total_weight
    blend_margin /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight

    ev_options = {
        "spread_home": blend_spread_ev_home,
        "spread_away": blend_spread_ev_away,
        "ml_home": blend_ml_ev_home,
        "ml_away": blend_ml_ev_away,
    }
    best_bet_type = max(ev_options, key=ev_options.get)
    best_blend_ev = ev_options[best_bet_type]

    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]
    else:
        side = "AWAY"
        side_team = game["away"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    agree_count = 0
    best_evs = []
    for mid, info in evs_by_model.items():
        if side == "HOME":
            model_best = max(info["spread_ev_home"], info["ml_ev_home"])
            model_alt = max(info["spread_ev_away"], info["ml_ev_away"])
        else:
            model_best = max(info["spread_ev_away"], info["ml_ev_away"])
            model_alt = max(info["spread_ev_home"], info["ml_ev_home"])

        if model_best > model_alt:
            agree_count += 1
        best_evs.append(info["best_ev"])

    best_model_ev = max(best_evs)
    worst_model_ev = min(best_evs)

    robustness = f"{agree_count}/6"

    any_flips = False
    for mid, info in evs_by_model.items():
        if best_bet_type == "spread_home" and info["spread_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "spread_away" and info["spread_ev_away"] < 0:
            any_flips = True
        elif best_bet_type == "ml_home" and info["ml_ev_home"] < 0:
            any_flips = True
        elif best_bet_type == "ml_away" and info["ml_ev_away"] < 0:
            any_flips = True

    if best_blend_ev > 0.03 and agree_count >= 4 and not any_flips:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count >= 3:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = min(0.05, max(0, best_blend_ev / 2.0))

    pred = {
        "game": game_key,
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
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            mid: {
                "home_win_prob": info["home_win_prob"],
                "expected_margin": info["expected_margin"],
                "spread_ev_home": info["spread_ev_home"],
                "spread_ev_away": info["spread_ev_away"],
                "ml_ev_home": info["ml_ev_home"],
                "ml_ev_away": info["ml_ev_away"],
            }
            for mid, info in evs_by_model.items()
        }
    }
    predictions.append(pred)

# ── Save predictions BEFORE displaying ──────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\n  Predictions saved to predictions/{TODAY}.json")

# ── Display results ─────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" MLB — Sunday June 28, 2026")
print(f"{'=' * 90}")
print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5}  {'Verdict':<16}")
print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*5}  {'-'*16}")

bets = []
for p in predictions:
    spread = p["odds"]["spread_home"]
    home_short = p["home_team"].split()[-1][:6]
    away_short = p["away_team"].split()[-1][:6]

    if spread < 0:
        game_str = f"{home_short} {spread:+.1f} vs {away_short}"
    elif spread > 0:
        game_str = f"{away_short} @ {home_short} (+{spread:.1f})"
    else:
        game_str = f"{away_short} @ {home_short}"

    if p["verdict"] == "BET":
        icon = " >>>"
    elif p["verdict"] == "LEAN":
        icon = "  > "
    else:
        icon = "  - "

    verdict_str = f"{icon} {p['verdict']} {p['side']}"

    print(f" {game_str:<32} {spread:>+7.1f} {p['best_blend_ev']:>+8.1%} {p['best_model_ev']:>+7.1%} {p['worst_model_ev']:>+6.1%} {p['robustness']:>5} {verdict_str:<16}")

    if p["verdict"] == "BET":
        bets.append(p)

if bets:
    print(f"\n  --- BET Details ---")
    for p in bets:
        print(f"\n  {p['side_team']} ({p['bet_market']}) | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"  Blended EV: {p['best_blend_ev']:+.1%} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")
        print(f"  Models agreeing: {p['agree_count']}/6 | Best book: {p['odds']['book']}")
        for mid, mr in p["model_results"].items():
            agree = "Y" if (p["side"] == "HOME" and max(mr["spread_ev_home"], mr["ml_ev_home"]) > max(mr["spread_ev_away"], mr["ml_ev_away"])) or \
                           (p["side"] == "AWAY" and max(mr["spread_ev_away"], mr["ml_ev_away"]) > max(mr["spread_ev_home"], mr["ml_ev_home"])) else "N"
            best = max(mr["spread_ev_home"], mr["spread_ev_away"], mr["ml_ev_home"], mr["ml_ev_away"])
            print(f"    {mid:<20} WP={mr['home_win_prob']:.1%} Mrgn={mr['expected_margin']:+.1f} BestEV={best:+.1%} Agree={agree}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 5 — Metrics Dashboard")
print(f"{'=' * 78}")

metrics_file = os.path.join(BASE, "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

eval_games = model_games[champion_id]
eval_correct = model_hits[champion_id]
eval_acc = eval_correct / eval_games if eval_games > 0 else 0.5

# Count bet results from June 26
jun26_bets = [p for p in past_preds["predictions"] if p["verdict"] == "BET"]
jun26_bet_wins = 0
jun26_bet_total = len(jun26_bets)
for bp in jun26_bets:
    gk = bp["game"]
    if gk not in actual_results:
        continue
    actual = actual_results[gk]
    actual_margin = actual["home_score"] - actual["away_score"]
    bt = bp["best_bet_type"]
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
        jun26_bet_wins += 1

prev_all = metrics["all_time"]
new_all_games = prev_all["total_games"] + eval_games
new_all_correct = prev_all["total_correct"] + eval_correct
new_all_bets = prev_all["total_bets_recommended"] + jun26_bet_total
new_all_bets_won = prev_all["total_bets_won"] + jun26_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_games, 4) if eval_games > 0 else 0.5,
    "ev_realized": round((jun26_bet_wins * 0.909 - (jun26_bet_total - jun26_bet_wins)) / max(jun26_bet_total, 1), 4),
    "total_games": eval_games,
    "total_correct": eval_correct
}
metrics["rolling_30d"] = {
    "accuracy": round(new_all_correct / new_all_games, 4) if new_all_games > 0 else 0.5,
    "ev_realized": round((new_all_bets_won * 0.909 - (new_all_bets - new_all_bets_won)) / max(new_all_bets, 1), 4),
    "total_games": new_all_games,
    "total_correct": new_all_correct
}
metrics["all_time"] = {
    "accuracy": round(new_all_correct / new_all_games, 4) if new_all_games > 0 else 0.5,
    "ev_realized": round((new_all_bets_won * 0.909 - (new_all_bets - new_all_bets_won)) / max(new_all_bets, 1), 4),
    "total_games": new_all_games,
    "total_correct": new_all_correct,
    "total_bets_recommended": new_all_bets,
    "total_bets_won": new_all_bets_won
}

for model in all_models:
    mid = model["id"]
    s_hits = model_hits.get(mid, 0)
    s_games = model_games.get(mid, 0)
    vp = metrics.get("variant_performance", {}).get(mid, {})
    metrics.setdefault("variant_performance", {})[mid] = {
        "lifetime_games": vp.get("lifetime_games", 0) + s_games,
        "lifetime_correct": vp.get("lifetime_correct", 0) + s_hits,
        "weight": 1.0 if mid == champion["id"] else next((c["weight"] for c in challengers if c["id"] == mid), 0.5),
        "role": "champion" if mid == champion["id"] else "challenger"
    }

total_bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")
total_no_today = sum(1 for p in predictions if p["verdict"] == "NO BET")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets_today,
    "leans": total_leans_today,
    "sports": ["baseball_mlb"],
    "notes": f"MLB only (15 games). {total_bets_today} BETs, {total_leans_today} LEANs. Eval Jun 26: {eval_correct}/{eval_games} correct."
}

if promotion_happened:
    metrics.setdefault("champion_history", []).append({
        "id": assumptions["champion"]["id"],
        "promoted_on": TODAY,
        "reason": f"Rolling accuracy exceeded predecessor by >=5%"
    })

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# Print summary
print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  Jun 26 eval: {eval_correct}/{eval_games} = {eval_acc:.1%} accuracy")
print(f"  Jun 26 bets: {jun26_bet_wins}/{jun26_bet_total} = {jun26_bet_wins/max(jun26_bet_total,1):.1%} hit rate")
print(f"  All-time: {new_all_correct}/{new_all_games} = {new_all_correct/new_all_games:.1%} accuracy | {new_all_bets_won}/{new_all_bets} bets won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

# Summary
print(f"\n{'=' * 90}")
print(f" SUMMARY: {len(predictions)} games analyzed | {total_bets_today} BETs | {total_leans_today} LEANs | {total_no_today} NO BETs")
print(f"{'=' * 90}")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
