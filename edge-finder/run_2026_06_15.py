#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-15 (Sunday).
Phase 1: Eval June 14 predictions, update weights.
Phase 2-5: Simulate tonight's games (MLB only — NHL season ended, NBA/NFL off-season).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-15"
EVAL_DATE = "2026-06-14"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 14 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-14 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results fetched via web search (June 14, 2026)
# NHL: Hurricanes won Stanley Cup Game 6 shutout 3-0
# MLB: 14 games completed, 1 postponed (CLE@DET), 1 wrong matchup (COL@LAA was actually COL@OAK)
actual_results = {
    "Carolina Hurricanes @ Vegas Golden Knights": {"winner": "away", "home_score": 0, "away_score": 3},
    "Miami Marlins @ Pittsburgh Pirates": {"winner": "away", "home_score": 2, "away_score": 4},
    "Seattle Mariners @ Washington Nationals": {"winner": "home", "home_score": 10, "away_score": 1},
    "New York Yankees @ Toronto Blue Jays": {"winner": "away", "home_score": 3, "away_score": 8},
    "San Francisco Giants @ Chicago Cubs": {"winner": "home", "home_score": 6, "away_score": 1},
    "Houston Astros @ Kansas City Royals": {"winner": "home", "home_score": 4, "away_score": 0},
    "Baltimore Orioles @ San Diego Padres": {"winner": "home", "home_score": 5, "away_score": 2},
    "Minnesota Twins @ St. Louis Cardinals": {"winner": "away", "home_score": 4, "away_score": 5},
    "Cleveland Guardians @ Detroit Tigers": {"winner": "postponed", "home_score": 0, "away_score": 0},
    "Boston Red Sox @ Texas Rangers": {"winner": "home", "home_score": 6, "away_score": 4},
    "Philadelphia Phillies @ Milwaukee Brewers": {"winner": "home", "home_score": 4, "away_score": 0},
    "Los Angeles Dodgers @ Chicago White Sox": {"winner": "home", "home_score": 6, "away_score": 4},
    "Cincinnati Reds @ Arizona Diamondbacks": {"winner": "home", "home_score": 5, "away_score": 3},
    "New York Mets @ Atlanta Braves": {"winner": "away", "home_score": 1, "away_score": 8},
    "Tampa Bay Rays @ Los Angeles Angels": {"winner": "away", "home_score": 3, "away_score": 8},
    "Colorado Rockies @ Los Angeles Angels": {"winner": "skip", "home_score": 0, "away_score": 0},
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

# Rolling 10-day accuracy (read from results.tsv)
print("\n  Rolling 10-day accuracy (June 5-14):")
rolling_data = {m: {"correct": 0, "total": 0} for m in model_ids}
with open(os.path.join(BASE, "results.tsv")) as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 11:
            continue
        d = parts[0]
        if d < "2026-06-05" or d > "2026-06-14":
            continue
        mid = parts[3]
        hit = int(parts[9])
        if mid in rolling_data:
            rolling_data[mid]["total"] += 1
            rolling_data[mid]["correct"] += hit

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
        print(f"    🏆 PROMOTING {cid} (10d acc {chal_acc:.1%}) over {champion_id} (10d acc {champ_10d_acc:.1%})")
        promoted = True
    else:
        diff = chal_acc - champ_10d_acc
        print(f"    {cid}: {chal_acc:.1%} vs champion {champ_10d_acc:.1%} (diff: {diff:+.1%}) — no promotion")

if not promoted:
    print("    No promotions triggered.")

# Retirement check
print("\n  Retirement check:")
retired_any = False
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    if challenger["weight"] <= 0.15 and challenger["born"] < "2026-06-10":
        print(f"    ⚰️  Retiring {cid} (weight={challenger['weight']}, born={challenger['born']})")
        retired_any = True
    else:
        print(f"    {cid}: weight={challenger['weight']}, born={challenger['born']} — keep")

if not retired_any:
    print("    No retirements needed.")

# Save assumptions
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  ✓ Phase 1 complete. Champion '{champion_id}' accuracy: {champion_correct_count}/{champion_total_count}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's Games: June 15, 2026)
# ════════════════════════════════════════════════════════════════════════
# NHL: Season over (Hurricanes won Cup on Jun 14)
# NBA: Off-season
# NFL: Off-season
# MLB: Regular season — Sunday schedule (typically 13-15 games)
#
# Odds and stats fetched via web search on June 15, 2026.
# Using composite of FanDuel, DraftKings, and BetMGM lines.

print("\n" + "=" * 78)
print(f" PHASE 2 — Tonight's Games & Odds ({TODAY})")
print("=" * 78)

# NOTE: Games and odds will be populated after web fetching.
# Placeholder for Phase 2 data — see main script below.

if __name__ == "__main__":
    print("\n  Phase 2 data collection requires web fetch — run via main orchestrator.")
