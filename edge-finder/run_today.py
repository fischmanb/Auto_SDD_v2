#!/usr/bin/env python3
"""Edge-Finder daily pipeline: eval yesterday + predict today."""

import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime, timedelta
from copy import deepcopy

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TODAY = "2026-06-01"
YESTERDAY = "2026-05-31"

# ══════════════════════════════════════════════════════════════════════
# Phase 1 — Evaluate Yesterday
# ══════════════════════════════════════════════════════════════════════

YESTERDAY_RESULTS = {
    "Miami Marlins @ New York Mets": {"winner": "home", "home_score": 10, "away_score": 1},
    "Kansas City Royals @ Texas Rangers": {"winner": "home", "home_score": 6, "away_score": 3},
    "Philadelphia Phillies @ Los Angeles Dodgers": {"winner": "away", "home_score": 3, "away_score": 4},
    "Arizona Diamondbacks @ Seattle Mariners": {"winner": "home", "home_score": 3, "away_score": 2},
    "Minnesota Twins @ Pittsburgh Pirates": {"winner": "home", "home_score": 9, "away_score": 3},
    "Toronto Blue Jays @ Baltimore Orioles": {"winner": "home", "home_score": 9, "away_score": 5},
    "San Diego Padres @ Washington Nationals": {"winner": "away", "home_score": 2, "away_score": 4},
    "San Francisco Giants @ Colorado Rockies": {"winner": "away", "home_score": 6, "away_score": 19},
    "Detroit Tigers @ Chicago White Sox": {"winner": "home", "home_score": 2, "away_score": 1},
    "Milwaukee Brewers @ Houston Astros": {"winner": "away", "home_score": 0, "away_score": 2},
    "Boston Red Sox @ Cleveland Guardians": {"winner": "away", "home_score": 4, "away_score": 9},
    "Chicago Cubs @ St. Louis Cardinals": {"winner": "home", "home_score": 5, "away_score": 1},
    "New York Yankees @ Sacramento Athletics": {"winner": "away", "home_score": 8, "away_score": 13},
    "Atlanta Braves @ Cincinnati Reds": {"winner": "home", "home_score": 6, "away_score": 4},
    "Los Angeles Angels @ Tampa Bay Rays": {"winner": "home", "home_score": 5, "away_score": 2},
}

with open("predictions/2026-05-31.json") as f:
    yesterday_preds = json.load(f)

with open("assumptions.json") as f:
    assumptions = json.load(f)

all_models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in all_models]

results_rows = []
model_correct_yesterday = {m["id"]: 0 for m in all_models}
model_games_yesterday = {m["id"]: 0 for m in all_models}

for pred in yesterday_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in YESTERDAY_RESULTS:
        continue
    actual = YESTERDAY_RESULTS[game_key]
    actual_winner = actual["winner"]
    actual_margin = actual["home_score"] - actual["away_score"]

    for model_id, model_result in pred["model_results"].items():
        margin = model_result["expected_margin"]
        predicted_winner = "home" if margin > 0 else "away"
        win_prob = model_result["home_win_prob"]
        hit = 1 if predicted_winner == actual_winner else 0

        spread_ev = max(model_result["spread_ev_home"], model_result["spread_ev_away"])
        ml_ev = max(model_result["ml_ev_home"], model_result["ml_ev_away"])

        if abs(model_result["spread_ev_home"]) > abs(model_result["ml_ev_home"]):
            if model_result["spread_ev_home"] > model_result["spread_ev_away"]:
                bet_type = "spread_home"
            else:
                bet_type = "spread_away"
        else:
            if model_result["ml_ev_home"] > model_result["ml_ev_away"]:
                bet_type = "ml_home"
            else:
                bet_type = "ml_away"

        if "spread" in bet_type:
            spread = pred["odds"]["spread_home"]
            if "home" in bet_type:
                covered = (actual_margin + spread) > 0
            else:
                covered = (-actual_margin - spread) > 0
            bet_result = "win" if covered else "loss"
        else:
            if "home" in bet_type:
                bet_result = "win" if actual_winner == "home" else "loss"
            else:
                bet_result = "win" if actual_winner == "away" else "loss"

        row = (
            f"{YESTERDAY}\t{pred['sport']}\t{game_key}\t{model_id}\t"
            f"{predicted_winner}\t{margin}\t{win_prob}\t{actual_winner}\t"
            f"{actual_margin}\t{hit}\t{spread_ev:.4f}\t{ml_ev:.4f}\t"
            f"{bet_type}\t{bet_result}"
        )
        results_rows.append(row)

        model_correct_yesterday[model_id] = model_correct_yesterday.get(model_id, 0) + hit
        model_games_yesterday[model_id] = model_games_yesterday.get(model_id, 0) + 1

with open("results.tsv", "a") as f:
    for row in results_rows:
        f.write(row + "\n")

n_games = len(YESTERDAY_RESULTS)
champ_id = assumptions["champion"]["id"]
champ_correct = model_correct_yesterday.get(champ_id, 0)
champ_acc = champ_correct / n_games if n_games > 0 else 0

print(f"\n=== Phase 1: Eval {YESTERDAY} ({n_games} games) ===")
print(f"Champion ({champ_id}): {champ_correct}/{n_games} = {champ_acc:.1%}")

weight_changes = []
for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_correct = model_correct_yesterday.get(cid, 0)
    c_acc = c_correct / n_games if n_games > 0 else 0

    games_better = 0
    games_worse = 0
    for pred in yesterday_preds["predictions"]:
        game_key = pred["game"]
        if game_key not in YESTERDAY_RESULTS:
            continue
        actual = YESTERDAY_RESULTS[game_key]
        actual_winner = actual["winner"]

        champ_margin = pred["model_results"].get(champ_id, {}).get("expected_margin", 0)
        champ_pred = "home" if champ_margin > 0 else "away"
        champ_hit = champ_pred == actual_winner

        c_margin = pred["model_results"].get(cid, {}).get("expected_margin", 0)
        c_pred = "home" if c_margin > 0 else "away"
        c_hit = c_pred == actual_winner

        if c_hit and not champ_hit:
            games_better += 1
        elif champ_hit and not c_hit:
            games_worse += 1

    outperform_pct = games_better / n_games if n_games > 0 else 0
    underperform_pct = games_worse / n_games if n_games > 0 else 0

    old_weight = challenger["weight"]
    born = challenger.get("born", "2026-03-24")
    grace_until = challenger.get("grace_until", "2026-03-29")

    if born <= YESTERDAY and grace_until < YESTERDAY:
        if outperform_pct >= 0.60:
            challenger["weight"] = min(1.0, old_weight + 0.1)
            weight_changes.append(f"{cid}: {old_weight}→{challenger['weight']} (outperformed)")
        elif underperform_pct >= 0.60:
            challenger["weight"] = max(0.1, old_weight - 0.1)
            weight_changes.append(f"{cid}: {old_weight}→{challenger['weight']} (underperformed)")

    challenger["lifetime_games"] = challenger.get("lifetime_games", 0) + n_games
    challenger["lifetime_correct"] = challenger.get("lifetime_correct", 0) + c_correct
    print(f"  {cid}: {c_correct}/{n_games} = {c_acc:.1%} (weight={challenger['weight']}, "
          f"better={games_better}, worse={games_worse})")

assumptions["champion"]["lifetime_games"] = assumptions["champion"].get("lifetime_games", 0) + n_games
assumptions["champion"]["lifetime_correct"] = assumptions["champion"].get("lifetime_correct", 0) + champ_correct

total_games_all = assumptions["champion"]["lifetime_games"]
total_correct_champ = assumptions["champion"]["lifetime_correct"]
assumptions["champion"]["rolling_10d_accuracy"] = total_correct_champ / total_games_all if total_games_all > 0 else 0

promotions = []
for challenger in assumptions["challengers"]:
    lt_games = challenger.get("lifetime_games", 0)
    lt_correct = challenger.get("lifetime_correct", 0)
    c_acc = lt_correct / lt_games if lt_games > 0 else 0
    champ_acc_lt = total_correct_champ / total_games_all if total_games_all > 0 else 0

    if lt_games >= 30 and c_acc - champ_acc_lt >= 0.05:
        promotions.append((challenger, c_acc, champ_acc_lt))

if promotions:
    best = max(promotions, key=lambda x: x[1])
    new_champ = best[0]
    old_champ = assumptions["champion"]
    print(f"\n  PROMOTION: {new_champ['id']} ({best[1]:.1%}) replaces {old_champ['id']} ({best[2]:.1%})")
    old_champ_as_challenger = {
        "id": old_champ["id"],
        "description": old_champ["description"],
        "weight": 0.7,
        "born": old_champ.get("promoted_on", "2026-03-24"),
        "grace_until": TODAY,
        "params": old_champ["params"],
        "lifetime_games": old_champ["lifetime_games"],
        "lifetime_correct": old_champ["lifetime_correct"],
    }
    assumptions["champion"] = {
        "id": new_champ["id"],
        "description": new_champ["description"],
        "params": new_champ["params"],
        "promoted_on": TODAY,
        "rolling_10d_accuracy": new_champ["lifetime_correct"] / new_champ["lifetime_games"],
        "lifetime_games": new_champ["lifetime_games"],
        "lifetime_correct": new_champ["lifetime_correct"],
    }
    assumptions["challengers"] = [
        c for c in assumptions["challengers"] if c["id"] != new_champ["id"]
    ] + [old_champ_as_challenger]

if not weight_changes:
    print("  No weight changes (no >=60% outperformance/underperformance)")
if not promotions:
    print("  No promotions (no challenger exceeds champion by >=5%)")

with open("assumptions.json", "w") as f:
    json.dump(assumptions, f, indent=2)

# ══════════════════════════════════════════════════════════════════════
# Phase 2 — Build Today's Games
# ══════════════════════════════════════════════════════════════════════

print(f"\n=== Phase 2: Data Collection for {TODAY} ===")

TEAM_STATS = {
    "Detroit Tigers":       {"rpg": 3.73, "orpg": 5.27, "wpct": .367, "l10_rpg": 3.5,  "l10_orpg": 5.5,  "injuries": 2},
    "Tampa Bay Rays":       {"rpg": 5.29, "orpg": 3.71, "wpct": .643, "l10_rpg": 5.1,  "l10_orpg": 3.5,  "injuries": 1},
    "Miami Marlins":        {"rpg": 4.07, "orpg": 4.93, "wpct": .433, "l10_rpg": 3.8,  "l10_orpg": 5.2,  "injuries": 2},
    "Washington Nationals": {"rpg": 4.53, "orpg": 4.47, "wpct": .517, "l10_rpg": 4.7,  "l10_orpg": 4.3,  "injuries": 1},
    "Kansas City Royals":   {"rpg": 3.77, "orpg": 5.23, "wpct": .373, "l10_rpg": 3.5,  "l10_orpg": 5.4,  "injuries": 2},
    "Cincinnati Reds":      {"rpg": 4.53, "orpg": 4.47, "wpct": .517, "l10_rpg": 4.8,  "l10_orpg": 4.2,  "injuries": 1},
    "Chicago White Sox":    {"rpg": 4.69, "orpg": 4.31, "wpct": .542, "l10_rpg": 4.9,  "l10_orpg": 4.0,  "injuries": 1},
    "Minnesota Twins":      {"rpg": 4.15, "orpg": 4.85, "wpct": .450, "l10_rpg": 4.0,  "l10_orpg": 5.0,  "injuries": 2},
    "San Francisco Giants": {"rpg": 3.88, "orpg": 5.12, "wpct": .390, "l10_rpg": 4.2,  "l10_orpg": 5.5,  "injuries": 2},
    "Milwaukee Brewers":    {"rpg": 5.13, "orpg": 3.88, "wpct": .625, "l10_rpg": 5.0,  "l10_orpg": 3.7,  "injuries": 1},
    "Texas Rangers":        {"rpg": 4.17, "orpg": 4.83, "wpct": .456, "l10_rpg": 4.5,  "l10_orpg": 4.5,  "injuries": 1},
    "St. Louis Cardinals":  {"rpg": 4.73, "orpg": 4.27, "wpct": .545, "l10_rpg": 4.9,  "l10_orpg": 4.0,  "injuries": 1},
    "Los Angeles Dodgers":  {"rpg": 5.29, "orpg": 3.71, "wpct": .643, "l10_rpg": 5.0,  "l10_orpg": 3.9,  "injuries": 1},
    "Arizona Diamondbacks": {"rpg": 4.86, "orpg": 4.14, "wpct": .564, "l10_rpg": 4.5,  "l10_orpg": 4.4,  "injuries": 1},
    "Colorado Rockies":     {"rpg": 3.73, "orpg": 5.27, "wpct": .367, "l10_rpg": 4.0,  "l10_orpg": 6.0,  "injuries": 2},
    "Los Angeles Angels":   {"rpg": 3.83, "orpg": 5.17, "wpct": .383, "l10_rpg": 4.0,  "l10_orpg": 5.3,  "injuries": 2},
    "New York Mets":        {"rpg": 3.98, "orpg": 5.02, "wpct": .421, "l10_rpg": 4.2,  "l10_orpg": 4.8,  "injuries": 2},
    "Seattle Mariners":     {"rpg": 4.36, "orpg": 4.64, "wpct": .491, "l10_rpg": 4.5,  "l10_orpg": 4.4,  "injuries": 1},
}

TODAYS_GAMES = [
    {
        "away": "Detroit Tigers", "home": "Tampa Bay Rays",
        "odds": {"spread_home": -1.5, "ml_home": -162, "ml_away": 136, "total": 8.0, "book": "fanduel"},
    },
    {
        "away": "Miami Marlins", "home": "Washington Nationals",
        "odds": {"spread_home": -1.5, "ml_home": -148, "ml_away": 123, "total": 8.0, "book": "fanduel"},
    },
    {
        "away": "Kansas City Royals", "home": "Cincinnati Reds",
        "odds": {"spread_home": -1.5, "ml_home": -220, "ml_away": 180, "total": 8.0, "book": "fanduel"},
    },
    {
        "away": "Chicago White Sox", "home": "Minnesota Twins",
        "odds": {"spread_home": 1.5, "ml_home": -165, "ml_away": 135, "total": 8.0, "book": "fanduel"},
    },
    {
        "away": "San Francisco Giants", "home": "Milwaukee Brewers",
        "odds": {"spread_home": -1.5, "ml_home": -158, "ml_away": 134, "total": 8.0, "book": "fanduel"},
    },
    {
        "away": "Texas Rangers", "home": "St. Louis Cardinals",
        "odds": {"spread_home": 1.5, "ml_home": 106, "ml_away": -124, "total": 7.5, "book": "fanduel"},
    },
    {
        "away": "Los Angeles Dodgers", "home": "Arizona Diamondbacks",
        "odds": {"spread_home": 1.5, "ml_home": 135, "ml_away": -160, "total": 9.0, "book": "fanduel"},
    },
    {
        "away": "Colorado Rockies", "home": "Los Angeles Angels",
        "odds": {"spread_home": -1.5, "ml_home": -225, "ml_away": 188, "total": 9.0, "book": "fanduel"},
    },
    {
        "away": "New York Mets", "home": "Seattle Mariners",
        "odds": {"spread_home": -1.5, "ml_home": -136, "ml_away": 116, "total": 7.0, "book": "fanduel"},
    },
]

def make_team_input(name, stats, is_b2b=False):
    wpct = stats["wpct"]
    return {
        "name": name,
        "season_ppg": stats["rpg"],
        "season_opp_ppg": stats["orpg"],
        "last10_ppg": stats["l10_rpg"],
        "last10_opp_ppg": stats["l10_orpg"],
        "season_pace": 1.0,
        "home_record_pct": min(0.85, wpct + 0.04),
        "away_record_pct": max(0.15, wpct - 0.04),
        "is_back_to_back": is_b2b,
        "key_injuries": stats["injuries"],
    }

# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Build batch & run simulations
# ══════════════════════════════════════════════════════════════════════

print(f"\n=== Phase 3: Simulation ({len(TODAYS_GAMES)} games x {len(all_models)} models) ===")

with open("assumptions.json") as f:
    assumptions = json.load(f)

all_models = [assumptions["champion"]] + assumptions["challengers"]

batch = []
for game in TODAYS_GAMES:
    away_stats = TEAM_STATS[game["away"]]
    home_stats = TEAM_STATS[game["home"]]

    for model in all_models:
        sim_input = {
            "sport": "baseball_mlb",
            "model_id": model["id"],
            "home": make_team_input(game["home"], home_stats),
            "away": make_team_input(game["away"], away_stats),
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        }
        batch.append(sim_input)

batch_file = "/tmp/edge_finder_batch.json"
with open(batch_file, "w") as f:
    json.dump(batch, f)

print(f"  Running {len(batch)} simulations...")
result = subprocess.run(
    ["python3", "sim.py", "--batch", batch_file],
    capture_output=True, text=True,
)

if result.returncode != 0:
    print(f"  ERROR: sim.py failed: {result.stderr}")
    sys.exit(1)

sim_results = json.loads(result.stdout)
print(f"  Completed {len(sim_results)} simulations")

# ══════════════════════════════════════════════════════════════════════
# Phase 4 — Blend & Classify
# ══════════════════════════════════════════════════════════════════════

print(f"\n=== Phase 4: Blended Predictions ===")

n_models = len(all_models)
predictions = []

for g_idx, game in enumerate(TODAYS_GAMES):
    game_results = sim_results[g_idx * n_models : (g_idx + 1) * n_models]

    model_weights = {}
    model_outputs = {}
    for i, model in enumerate(all_models):
        w = 1.0 if i == 0 else assumptions["challengers"][i - 1]["weight"]
        model_weights[model["id"]] = w
        model_outputs[model["id"]] = game_results[i]

    total_weight = sum(model_weights.values())
    blend_home_wp = sum(
        model_weights[mid] * mo["home_win_prob"]
        for mid, mo in model_outputs.items()
    ) / total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin = sum(
        model_weights[mid] * mo["expected_margin"]
        for mid, mo in model_outputs.items()
    ) / total_weight

    blend_ev_by_type = {}
    for ev_type in ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]:
        blend_ev_by_type[ev_type] = sum(
            model_weights[mid] * mo[ev_type]
            for mid, mo in model_outputs.items()
        ) / total_weight

    best_blend_type = max(blend_ev_by_type, key=blend_ev_by_type.get)
    best_blend_ev = blend_ev_by_type[best_blend_type]

    per_model_best_ev = {}
    for mid, mo in model_outputs.items():
        evs = {
            "spread_ev_home": mo["spread_ev_home"],
            "spread_ev_away": mo["spread_ev_away"],
            "ml_ev_home": mo["ml_ev_home"],
            "ml_ev_away": mo["ml_ev_away"],
        }
        per_model_best_ev[mid] = max(evs.values())

    best_model_ev = max(per_model_best_ev.values())
    worst_model_ev = min(per_model_best_ev.values())

    home_side_count = sum(
        1 for mo in model_outputs.values() if mo["expected_margin"] > 0
    )
    away_side_count = n_models - home_side_count
    agree_count = max(home_side_count, away_side_count)
    robustness = f"{agree_count}/{n_models}"

    if "home" in best_blend_type:
        side = "HOME"
        side_team = game["home"]
    else:
        side = "AWAY"
        side_team = game["away"]

    if "spread" in best_blend_type:
        bet_market = "SPREAD"
    else:
        bet_market = "ML"

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = 0
    if verdict == "BET":
        kelly = round(min(0.05, best_blend_ev / 5), 4)

    model_detail = {}
    for mid, mo in model_outputs.items():
        model_detail[mid] = {
            "home_win_prob": mo["home_win_prob"],
            "expected_margin": mo["expected_margin"],
            "spread_ev_home": mo["spread_ev_home"],
            "spread_ev_away": mo["spread_ev_away"],
            "ml_ev_home": mo["ml_ev_home"],
            "ml_ev_away": mo["ml_ev_away"],
        }

    pred = {
        "game": f"{game['away']} @ {game['home']}",
        "sport": "baseball_mlb",
        "home_team": game["home"],
        "away_team": game["away"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_blend_type,
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
        "model_results": model_detail,
    }
    predictions.append(pred)

with open(f"predictions/{TODAY}.json", "w") as f:
    json.dump({"date": TODAY, "predictions": predictions}, f, indent=2)

# ══════════════════════════════════════════════════════════════════════
# Phase 5 — Metrics Update
# ══════════════════════════════════════════════════════════════════════

with open("metrics.json") as f:
    metrics = json.load(f)

champ = assumptions["champion"]
metrics["last_updated"] = TODAY
metrics["rolling_7d"]["total_games"] += n_games
metrics["rolling_7d"]["total_correct"] += champ_correct
metrics["rolling_7d"]["accuracy"] = round(
    metrics["rolling_7d"]["total_correct"] / metrics["rolling_7d"]["total_games"], 4
)
metrics["rolling_30d"]["total_games"] += n_games
metrics["rolling_30d"]["total_correct"] += champ_correct
metrics["rolling_30d"]["accuracy"] = round(
    metrics["rolling_30d"]["total_correct"] / metrics["rolling_30d"]["total_games"], 4
)
metrics["all_time"]["total_games"] += n_games
metrics["all_time"]["total_correct"] += champ_correct
metrics["all_time"]["accuracy"] = round(
    metrics["all_time"]["total_correct"] / metrics["all_time"]["total_games"], 4
)

bet_games = [p for p in yesterday_preds["predictions"] if p["verdict"] == "BET"]
bet_wins = 0
for bg in bet_games:
    gk = bg["game"]
    if gk in YESTERDAY_RESULTS:
        actual = YESTERDAY_RESULTS[gk]
        if bg["side"] == "HOME" and actual["winner"] == "home":
            bet_wins += 1
        elif bg["side"] == "AWAY" and actual["winner"] == "away":
            bet_wins += 1

metrics["all_time"]["total_bets_recommended"] += len(bet_games)
metrics["all_time"]["total_bets_won"] += bet_wins

for model in [assumptions["champion"]] + assumptions["challengers"]:
    mid = model["id"]
    if mid in metrics["variant_performance"]:
        metrics["variant_performance"][mid]["lifetime_games"] = model.get("lifetime_games", 0)
        metrics["variant_performance"][mid]["lifetime_correct"] = model.get("lifetime_correct", 0)
        metrics["variant_performance"][mid]["weight"] = 1.0 if mid == champ["id"] else model.get("weight", 0.5)

n_bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
n_leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": n_bets_today,
    "leans": n_leans_today,
    "sports": ["baseball_mlb"],
    "notes": f"{len(predictions)} MLB games. {n_bets_today} BETs, {n_leans_today} LEANs."
}

with open("metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

# ══════════════════════════════════════════════════════════════════════
# Output — Formatted Table
# ══════════════════════════════════════════════════════════════════════

print("\n")
print("=" * 90)
print(f"  MLB - Monday June 1, 2026")
print("=" * 90)

header = f"{'Game':<28} {'Spread':>6} {'Blend EV':>9} {'Best EV':>8} {'Worst EV':>9} {'Rob.':>5} {'Verdict':<16}"
print(header)
print("-" * 90)

for p in sorted(predictions, key=lambda x: -x["best_blend_ev"]):
    away_short = p["away_team"].split()[-1][:5]
    home_short = p["home_team"].split()[-1][:5]
    spread = p["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}"

    if p["blend_margin"] > 0:
        game_str = f"{home_short} {spread_str} vs {away_short}"
    else:
        game_str = f"{away_short} @ {home_short} {spread_str}"

    ev_str = f"{p['best_blend_ev']:+.1%}"
    best_str = f"{p['best_model_ev']:+.1%}"
    worst_str = f"{p['worst_model_ev']:+.1%}"

    if p["verdict"] == "BET":
        verdict_str = f">>> BET {p['side']}"
    elif p["verdict"] == "LEAN":
        verdict_str = f"  ~ LEAN {p['side']}"
    else:
        verdict_str = "  x NO BET"

    print(f"{game_str:<28} {spread_str:>6} {ev_str:>9} {best_str:>8} {worst_str:>9} {p['robustness']:>5} {verdict_str:<16}")

print("-" * 90)

bet_preds = [p for p in predictions if p["verdict"] == "BET"]
if bet_preds:
    print(f"\nBET Details ({len(bet_preds)} recommendations):")
    for p in sorted(bet_preds, key=lambda x: -x["best_blend_ev"]):
        print(f"\n  {p['game']}")
        print(f"    Side: {p['side']} ({p['side_team']}) on {p['bet_market']}")
        print(f"    Blend EV: {p['best_blend_ev']:+.1%} | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"    Best book: {p['odds']['book']}")
        agreeing = []
        disagreeing = []
        for mid, mr in p["model_results"].items():
            if mr["expected_margin"] > 0 and p["side"] == "HOME":
                agreeing.append(mid)
            elif mr["expected_margin"] <= 0 and p["side"] == "AWAY":
                agreeing.append(mid)
            else:
                disagreeing.append(mid)
        print(f"    Agree: {', '.join(agreeing)}")
        if disagreeing:
            print(f"    Disagree: {', '.join(disagreeing)}")

print(f"\n{'=' * 90}")
print(f"  Edge-Finder Metrics Dashboard")
print(f"{'=' * 90}")
print(f"  Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
print(f"  7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | "
      f"{metrics['rolling_7d']['total_games']} games")
print(f"  30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | "
      f"{metrics['rolling_30d']['total_games']} games")
print(f"  All-time: {metrics['all_time']['accuracy']:.0%} accuracy | "
      f"{metrics['all_time']['total_games']} games | "
      f"Bets: {metrics['all_time']['total_bets_won']}/{metrics['all_time']['total_bets_recommended']}")
print()
weights = []
for c in assumptions["challengers"]:
    tag = ""
    if c.get("born", "") >= "2026-05-27":
        tag = "(NEW)"
    weights.append(f"{c['id']}={c['weight']}{tag}")
print(f"  Challenger weights: {', '.join(weights)}")
if assumptions.get("graveyard"):
    dead = [f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions["graveyard"]]
    print(f"  Graveyard: {', '.join(dead)}")
else:
    print("  Graveyard: (empty)")
print()
print("  This is for entertainment and analysis purposes only.")
print("  Past performance does not guarantee future results.")
print(f"{'=' * 90}")
