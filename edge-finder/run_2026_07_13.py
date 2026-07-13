#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-13 (All-Star Break — eval only, no games today).
Phase 1: Eval July 10 predictions, update weights.
No Phase 2-5 (MLB All-Star break, no regular-season games scheduled).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-13"
EVAL_DATE = "2026-07-10"

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 10 PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-10 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 10, 2026 (sourced via web search from ESPN/MLB.com/Baseball-Reference)
actual_results = {
    "Milwaukee Brewers @ Pittsburgh Pirates": {"winner": "home", "home_score": 14, "away_score": 5},
    "Philadelphia Phillies @ Detroit Tigers": {"winner": "home", "home_score": 10, "away_score": 2},
    "New York Yankees @ Washington Nationals": {"winner": "away", "home_score": 3, "away_score": 5},
    "Kansas City Royals @ Baltimore Orioles": {"winner": "home", "home_score": 5, "away_score": 3},
    "Boston Red Sox @ New York Mets": {"winner": "away", "home_score": 2, "away_score": 6},
    "Sacramento Athletics @ Chicago White Sox": {"winner": "home", "home_score": 14, "away_score": 1},
    "Los Angeles Angels @ Minnesota Twins": {"winner": "away", "home_score": 3, "away_score": 4},
    "Seattle Mariners @ Tampa Bay Rays": {"winner": "home", "home_score": 7, "away_score": 2},
    "Arizona Diamondbacks @ Los Angeles Dodgers": {"winner": "away", "home_score": 3, "away_score": 9},
    "San Francisco Giants @ Colorado Rockies": {"winner": "home", "home_score": 4, "away_score": 3},
    "Atlanta Braves @ St. Louis Cardinals": {"winner": "home", "home_score": 2, "away_score": 1},
    "Toronto Blue Jays @ San Diego Padres": {"winner": "away", "home_score": 3, "away_score": 5},
    "Miami Marlins @ Cleveland Guardians": {"winner": "home", "home_score": 3, "away_score": 2},
    "Houston Astros @ Texas Rangers": {"winner": "home", "home_score": 7, "away_score": 3},
    "Chicago Cubs @ Cincinnati Reds": {"winner": "home", "home_score": 4, "away_score": 0},
}

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
model_ids = [m["id"] for m in all_models]

model_scores = {mid: {"correct": 0, "total": 0} for mid in model_ids}
tsv_lines = []

for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        continue

    actual = actual_results[game_key]
    actual_winner = actual["winner"]
    margin = actual["home_score"] - actual["away_score"]

    for mid, mr in pred["model_results"].items():
        predicted_winner = "home" if mr["home_win_prob"] > 0.5 else "away"
        hit = 1 if predicted_winner == actual_winner else 0
        model_scores[mid]["correct"] += hit
        model_scores[mid]["total"] += 1

        best_ev_type = max(
            [("spread_home", mr["spread_ev_home"]),
             ("spread_away", mr["spread_ev_away"]),
             ("ml_home", mr["ml_ev_home"]),
             ("ml_away", mr["ml_ev_away"])],
            key=lambda x: x[1]
        )

        if pred["verdict"] in ("BET", "LEAN"):
            bet_side = pred.get("side", "HOME").lower()
            bet_market = pred.get("bet_market", "SPREAD").lower()

            if bet_market == "spread":
                spread = pred["odds"]["spread_home"]
                if bet_side == "home":
                    bet_result = "win" if margin > -spread else ("push" if margin == -spread else "loss")
                else:
                    bet_result = "win" if margin < -spread else ("push" if margin == -spread else "loss")
            else:
                if bet_side == "home":
                    bet_result = "win" if actual_winner == "home" else "loss"
                else:
                    bet_result = "win" if actual_winner == "away" else "loss"
        else:
            bet_result = "no_bet"

        tsv_lines.append(
            f"{EVAL_DATE}\t{pred['sport']}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']:.2f}\t{mr['home_win_prob']:.4f}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{best_ev_type[1]:.4f}\t{mr.get('ml_ev_home', 0):.4f}\t"
            f"{best_ev_type[0]}\t{bet_result}"
        )

# Print per-model results
print("\nModel Performance on July 10 (15 games):")
print("-" * 50)
for mid in model_ids:
    s = model_scores[mid]
    pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
    role = "CHAMPION" if mid == champion["id"] else "challenger"
    print(f"  {mid:22s} [{role:10s}]: {s['correct']}/{s['total']} = {pct:.1f}%")

champion_correct = model_scores[champion["id"]]["correct"]
champion_total = model_scores[champion["id"]]["total"]
champion_pct = champion_correct / champion_total if champion_total > 0 else 0

# Append to results.tsv
with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

print(f"\nAppended {len(tsv_lines)} lines to results.tsv")

# ═══════════════════════════════════════════════════════════════════════
# STEP 1.4 — Update challenger weights
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" STEP 1.4 — Updating challenger weights")
print("=" * 78)

for ch in challengers:
    ch_id = ch["id"]
    ch_correct = model_scores[ch_id]["correct"]
    ch_total = model_scores[ch_id]["total"]
    ch_pct = ch_correct / ch_total if ch_total > 0 else 0

    if ch_total > 0 and champion_total > 0:
        ch_rate = ch_correct / ch_total
        champ_rate = champion_correct / champion_total
        outperform_pct = ch_rate

        if ch_rate >= 0.6 * 1 and ch_rate > champ_rate:
            old_w = ch["weight"]
            ch["weight"] = min(1.0, ch["weight"] + 0.1)
            print(f"  {ch_id}: outperformed champion ({ch_rate:.1%} vs {champ_rate:.1%}), weight {old_w:.1f} -> {ch['weight']:.1f}")
        elif ch_rate <= champ_rate * 0.6 / 1.0 and ch_rate < champ_rate:
            old_w = ch["weight"]
            ch["weight"] = max(0.1, ch["weight"] - 0.1)
            print(f"  {ch_id}: underperformed champion ({ch_rate:.1%} vs {champ_rate:.1%}), weight {old_w:.1f} -> {ch['weight']:.1f}")
        else:
            print(f"  {ch_id}: similar to champion ({ch_rate:.1%} vs {champ_rate:.1%}), weight unchanged at {ch['weight']:.1f}")

# Update lifetime stats
for m in all_models:
    mid = m["id"]
    m["lifetime_games"] = m.get("lifetime_games", 0) + model_scores[mid]["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + model_scores[mid]["correct"]

# ═══════════════════════════════════════════════════════════════════════
# STEP 1.5 — Promotion check (rolling 10-day accuracy)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" STEP 1.5 — Promotion check")
print("=" * 78)

# Read recent results from results.tsv for rolling 10-day calculation
import csv
from collections import defaultdict

rolling_window_dates = set()
rolling_model_stats = defaultdict(lambda: {"correct": 0, "total": 0})

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    rows = list(reader)

# Get the 10 most recent distinct dates
all_dates = sorted(set(r[0] for r in rows if len(r) > 0), reverse=True)
recent_10_dates = set(all_dates[:10])

for r in rows:
    if len(r) < 10:
        continue
    if r[0] in recent_10_dates:
        mid = r[3]
        hit = int(r[9])
        rolling_model_stats[mid]["correct"] += hit
        rolling_model_stats[mid]["total"] += 1

print(f"\nRolling 10-day window covers dates: {sorted(recent_10_dates)}")

for mid in model_ids:
    s = rolling_model_stats[mid]
    acc = s["correct"] / s["total"] if s["total"] > 0 else 0
    print(f"  {mid:22s}: {s['correct']}/{s['total']} = {acc:.1%}")

# Update rolling_10d_accuracy in assumptions
champ_rolling = rolling_model_stats[champion["id"]]
champ_rolling_acc = champ_rolling["correct"] / champ_rolling["total"] if champ_rolling["total"] > 0 else 0
champion["rolling_10d_accuracy"] = champ_rolling_acc

promotion_happened = False
for ch in challengers:
    ch_rolling = rolling_model_stats[ch["id"]]
    ch_rolling_acc = ch_rolling["correct"] / ch_rolling["total"] if ch_rolling["total"] > 0 else 0
    ch["rolling_10d_accuracy"] = ch_rolling_acc

    if ch_rolling_acc > champ_rolling_acc + 0.05:
        print(f"\n  *** PROMOTION: {ch['id']} ({ch_rolling_acc:.1%}) exceeds champion {champion['id']} ({champ_rolling_acc:.1%}) by {(ch_rolling_acc - champ_rolling_acc)*100:.1f}%!")
        old_champion = dict(champion)
        champion_data = dict(ch)
        champion_data["weight"] = 1.0
        champion_data["promoted_on"] = TODAY

        ch_slot = {"id": old_champion["id"], "description": old_champion["description"],
                   "weight": 0.7, "born": old_champion.get("born", "2026-03-24"),
                   "grace_until": old_champion.get("grace_until", "2026-03-29"),
                   "params": old_champion["params"],
                   "lifetime_games": old_champion["lifetime_games"],
                   "lifetime_correct": old_champion["lifetime_correct"],
                   "rolling_10d_accuracy": champ_rolling_acc}
        if "promoted_on" in old_champion:
            ch_slot["promoted_on"] = old_champion["promoted_on"]

        idx = challengers.index(ch)
        challengers[idx] = ch_slot
        assumptions["champion"] = champion_data
        champion = assumptions["champion"]
        promotion_happened = True
        break

if not promotion_happened:
    print("\n  No promotion triggered.")

# ═══════════════════════════════════════════════════════════════════════
# STEP 1.6 — Explore: Retire & Replace
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" STEP 1.6 — Retire & Replace check")
print("=" * 78)

from datetime import datetime

retirements = []
for ch in challengers:
    born = ch.get("born", "2026-03-24")
    born_date = datetime.strptime(born, "%Y-%m-%d").date()
    today_date = datetime.strptime(TODAY, "%Y-%m-%d").date()
    age_days = (today_date - born_date).days

    if ch["weight"] <= 0.15 and age_days > 5:
        lt_acc = ch["lifetime_correct"] / ch["lifetime_games"] if ch.get("lifetime_games", 0) > 0 else 0
        print(f"  RETIRING {ch['id']}: weight={ch['weight']:.2f}, age={age_days}d, accuracy={lt_acc:.1%}")
        retirements.append(ch)

for ch in retirements:
    lt_acc = ch["lifetime_correct"] / ch["lifetime_games"] if ch.get("lifetime_games", 0) > 0 else 0
    graveyard_entry = {
        "id": ch["id"],
        "description": ch["description"],
        "final_weight": ch["weight"],
        "lifetime_accuracy": round(lt_acc, 4),
        "lifetime_games": ch.get("lifetime_games", 0),
        "lifetime_correct": ch.get("lifetime_correct", 0),
        "born": ch.get("born", "unknown"),
        "died": TODAY,
        "reason": f"Weight dropped to {ch['weight']:.2f} after persistent underperformance. {ch['description']}"
    }
    assumptions.setdefault("graveyard", []).append(graveyard_entry)
    challengers.remove(ch)

if not retirements:
    print("  No retirements triggered.")

# Ensure exactly 5 challengers
while len(challengers) < 5:
    graveyard_ideas = [g["description"].lower() for g in assumptions.get("graveyard", [])]
    existing_ideas = [c["description"].lower() for c in challengers]

    new_challenger = {
        "id": f"new-challenger-{TODAY}",
        "description": "Placeholder — needs creative replacement",
        "weight": 0.5,
        "born": TODAY,
        "grace_until": "2026-07-18",
        "params": {
            "recency_weight": 1.0,
            "injury_discount": 0.0,
            "home_advantage_adjustment": 0.0,
            "regression_to_mean": 0.0,
            "pace_adjustment": "season_average"
        },
        "lifetime_games": 0,
        "lifetime_correct": 0,
        "rolling_10d_accuracy": 0.0
    }
    challengers.append(new_challenger)
    print(f"  Added placeholder challenger (need {5 - len(challengers) + 1} more)")

assumptions["challengers"] = challengers

# ═══════════════════════════════════════════════════════════════════════
# STEP 1.7 — Save assumptions
# ═══════════════════════════════════════════════════════════════════════

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
    f.write("\n")

print("\nSaved updated assumptions.json")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — Metrics Dashboard (eval-only update)
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Recompute rolling 7-day and 30-day from results.tsv
all_dates_sorted = sorted(set(r[0] for r in rows if len(r) > 0))
last_7_dates = set(sorted(set(r[0] for r in rows if len(r) > 0), reverse=True)[:7])
last_30_dates = set(sorted(set(r[0] for r in rows if len(r) > 0), reverse=True)[:30])

def compute_stats(date_set, rows, champion_id):
    total = 0
    correct = 0
    for r in rows:
        if len(r) < 10:
            continue
        if r[0] in date_set and r[3] == champion_id:
            total += 1
            correct += int(r[9])
    acc = correct / total if total > 0 else 0
    return {"accuracy": round(acc, 4), "total_games": total, "total_correct": correct}

champ_id = assumptions["champion"]["id"]
r7 = compute_stats(last_7_dates, rows, champ_id)
r30 = compute_stats(last_30_dates, rows, champ_id)

# Compute all-time
all_dates_set = set(r[0] for r in rows if len(r) > 0)
r_all = compute_stats(all_dates_set, rows, champ_id)

# Count BET verdicts
total_bets = sum(1 for r in rows if len(r) > 13 and r[13] in ("win", "loss") and r[3] == champ_id)
total_bets_won = sum(1 for r in rows if len(r) > 13 and r[13] == "win" and r[3] == champ_id)

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": r7["accuracy"],
    "ev_realized": metrics.get("rolling_7d", {}).get("ev_realized", 0),
    "total_games": r7["total_games"],
    "total_correct": r7["total_correct"]
}
metrics["rolling_30d"] = {
    "accuracy": r30["accuracy"],
    "ev_realized": metrics.get("rolling_30d", {}).get("ev_realized", 0),
    "total_games": r30["total_games"],
    "total_correct": r30["total_correct"]
}
metrics["all_time"] = {
    "accuracy": r_all["accuracy"],
    "ev_realized": metrics.get("all_time", {}).get("ev_realized", 0),
    "total_games": r_all["total_games"],
    "total_correct": r_all["total_correct"],
    "total_bets_recommended": total_bets,
    "total_bets_won": total_bets_won
}

# Update variant performance
metrics["variant_performance"] = {}
for m in [assumptions["champion"]] + assumptions["challengers"]:
    metrics["variant_performance"][m["id"]] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": m.get("weight", 0),
        "role": "champion" if m["id"] == champ_id else "challenger"
    }

# Champion history (keep existing)
if "champion_history" not in metrics:
    metrics["champion_history"] = []

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": 0,
    "bets_recommended": 0,
    "leans": 0,
    "sports": [],
    "notes": f"All-Star Break — no games. Eval Jul 10: {model_scores[champ_id]['correct']}/{model_scores[champ_id]['total']} correct."
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# ═══════════════════════════════════════════════════════════════════════
# Print summary
# ═══════════════════════════════════════════════════════════════════════

print(f"""
📊 Edge-Finder Metrics
━━━━━━━━━━━━━━━━━━━━
Champion: {champ_id} (promoted {assumptions['champion'].get('promoted_on', 'N/A')})
7-day:  {r7['accuracy']:.0%} accuracy | {r7['total_games']} games
30-day: {r30['accuracy']:.0%} accuracy | {r30['total_games']} games
All-time: {r_all['accuracy']:.0%} accuracy | {r_all['total_games']} games

Eval July 10: {model_scores[champ_id]['correct']}/{model_scores[champ_id]['total']} correct ({model_scores[champ_id]['correct']/model_scores[champ_id]['total']*100:.1f}%)

Challenger weights: {', '.join(f"{c['id']}={c['weight']:.1f}" for c in assumptions['challengers'])}
Graveyard: {', '.join(f"{g['id']} (died {g['died']})" for g in assumptions.get('graveyard', []))}

⚾ All-Star Break — no regular-season games today. Next games resume after the break.
⚠️ This analysis is for entertainment purposes only. Past performance does not guarantee future results.
""")
