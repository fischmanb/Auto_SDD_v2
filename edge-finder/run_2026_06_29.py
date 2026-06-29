#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-29.
Phase 1: Eval June 28 predictions, update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-06-29"
EVAL_DATE = "2026-06-28"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JUNE 28 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-06-28 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

actual_results = {
    "Houston Astros @ Detroit Tigers": {"winner": "away", "home_score": 5, "away_score": 7},
    "Cincinnati Reds @ Pittsburgh Pirates": {"winner": "home", "home_score": 9, "away_score": 4},
    "Washington Nationals @ Baltimore Orioles": {"winner": "away", "home_score": 4, "away_score": 6},
    "Texas Rangers @ Toronto Blue Jays": {"winner": "away", "home_score": 2, "away_score": 3},
    "Seattle Mariners @ Cleveland Guardians": {"winner": "home", "home_score": 6, "away_score": 5},
    "Arizona Diamondbacks @ Tampa Bay Rays": {"winner": "home", "home_score": 5, "away_score": 1},
    "Philadelphia Phillies @ New York Mets": {"winner": "away", "home_score": 4, "away_score": 5},
    "New York Yankees @ Boston Red Sox": {"winner": "home", "home_score": 5, "away_score": 4},
    "Kansas City Royals @ Chicago White Sox": {"winner": "away", "home_score": 4, "away_score": 5},
    "Chicago Cubs @ Milwaukee Brewers": {"winner": "away", "home_score": 3, "away_score": 4},
    "Colorado Rockies @ Minnesota Twins": {"winner": "home", "home_score": 3, "away_score": 2},
    "Miami Marlins @ St. Louis Cardinals": {"winner": "home", "home_score": 2, "away_score": 1},
    "Sacramento Athletics @ Los Angeles Angels": {"winner": "home", "home_score": 4, "away_score": 1},
    "Los Angeles Dodgers @ San Diego Padres": {"winner": "away", "home_score": 2, "away_score": 4},
    "Atlanta Braves @ San Francisco Giants": {"winner": "home", "home_score": 3, "away_score": 2},
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
        bet_type = best_ev_type[0]

        spread = pred["odds"]["spread_home"]
        if bet_type == "spread_home":
            bet_won = (margin + spread) > 0
        elif bet_type == "spread_away":
            bet_won = (-margin - spread) > 0
        elif bet_type == "ml_home":
            bet_won = actual_winner == "home"
        else:
            bet_won = actual_winner == "away"

        bet_result = "win" if bet_won else "loss"

        tsv_lines.append(
            f"{EVAL_DATE}\t{pred['sport']}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']:.2f}\t{mr['home_win_prob']:.4f}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{mr['spread_ev_home']:.4f}\t{mr['ml_ev_home']:.4f}\t{bet_type}\t{bet_result}"
        )

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

total_games = model_scores[champion["id"]]["total"]
print(f"\nEvaluated {total_games} games from {EVAL_DATE}")
print(f"\nModel accuracy on {EVAL_DATE}:")
for mid in model_ids:
    s = model_scores[mid]
    pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
    if mid == champion["id"]:
        role = "CHAMP"
    else:
        role = f"w={next(c['weight'] for c in challengers if c['id'] == mid)}"
    print(f"  {mid:<20} {s['correct']}/{s['total']} = {pct:.1f}% [{role}]")

# ── Step 1.4: Update challenger weights ──────────────────────────────
champ_hits = set()
champ_misses = set()
champ_id = champion["id"]

for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        continue
    actual_winner = actual_results[game_key]["winner"]
    champ_mr = pred["model_results"][champ_id]
    champ_pred = "home" if champ_mr["home_win_prob"] > 0.5 else "away"
    if champ_pred == actual_winner:
        champ_hits.add(game_key)
    else:
        champ_misses.add(game_key)

weight_changes = []
for c in challengers:
    cid = c["id"]
    c_hits = set()
    c_misses = set()
    for pred in past_preds["predictions"]:
        game_key = pred["game"]
        if game_key not in actual_results:
            continue
        actual_winner = actual_results[game_key]["winner"]
        c_mr = pred["model_results"][cid]
        c_pred = "home" if c_mr["home_win_prob"] > 0.5 else "away"
        if c_pred == actual_winner:
            c_hits.add(game_key)
        else:
            c_misses.add(game_key)

    outperformed = c_hits - champ_hits
    underperformed = champ_hits - c_hits
    disagreements = len(outperformed) + len(underperformed)

    old_weight = c["weight"]
    if disagreements > 0:
        if len(outperformed) / disagreements >= 0.6:
            c["weight"] = min(1.0, round(c["weight"] + 0.1, 1))
        elif len(underperformed) / disagreements >= 0.6:
            c["weight"] = max(0.1, round(c["weight"] - 0.1, 1))

    c["lifetime_games"] = c.get("lifetime_games", 0) + model_scores[cid]["total"]
    c["lifetime_correct"] = c.get("lifetime_correct", 0) + model_scores[cid]["correct"]

    if c["weight"] != old_weight:
        weight_changes.append(f"{cid}: {old_weight} -> {c['weight']}")
        print(f"  Weight change: {cid} {old_weight} -> {c['weight']} (outperformed {len(outperformed)}, underperformed {len(underperformed)} in {disagreements} disagreements)")

champion["lifetime_games"] = champion.get("lifetime_games", 0) + model_scores[champ_id]["total"]
champion["lifetime_correct"] = champion.get("lifetime_correct", 0) + model_scores[champ_id]["correct"]
champion["rolling_10d_accuracy"] = model_scores[champ_id]["correct"] / model_scores[champ_id]["total"] if model_scores[champ_id]["total"] > 0 else 0.5

# ── Step 1.5: Promotion check ──────────────────────────────────────
promotion_msg = ""
for c in challengers:
    cid = c["id"]
    c_lifetime_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
    champ_lifetime_acc = champion["lifetime_correct"] / champion["lifetime_games"] if champion["lifetime_games"] > 0 else 0.5
    c["rolling_10d_accuracy"] = model_scores.get(cid, {}).get("correct", 0) / max(model_scores.get(cid, {}).get("total", 1), 1)

    if c_lifetime_acc - champ_lifetime_acc >= 0.05:
        promotion_msg = f"PROMOTION: {cid} replaces {champ_id} as champion"
        print(f"\n  *** {promotion_msg} ***")

        old_champ = dict(champion)
        champion.update({
            "id": c["id"],
            "description": c["description"],
            "params": c["params"],
            "weight": 1.0,
            "born": c.get("born", "2026-03-24"),
            "lifetime_games": c["lifetime_games"],
            "lifetime_correct": c["lifetime_correct"],
            "promoted_on": TODAY,
            "rolling_10d_accuracy": c.get("rolling_10d_accuracy", 0.5),
        })
        if "grace_until" in c:
            champion["grace_until"] = c["grace_until"]

        c.update({
            "id": old_champ["id"],
            "description": old_champ["description"],
            "params": old_champ["params"],
            "weight": 0.7,
            "born": old_champ.get("born", "2026-03-24"),
            "lifetime_games": old_champ.get("lifetime_games", 0),
            "lifetime_correct": old_champ.get("lifetime_correct", 0),
            "promoted_on": old_champ.get("promoted_on"),
            "rolling_10d_accuracy": old_champ.get("rolling_10d_accuracy", 0.5),
        })

        assumptions["champion"] = champion
        break

if not promotion_msg:
    print("\n  No promotions triggered.")

# ── Step 1.6: Retirement check ──────────────────────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 6, 29) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ════════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (June 29, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Tonight's games with odds from web searches ─────────────────────

games_raw = [
    # 1. Washington Nationals @ Boston Red Sox
    # WAS 43-42, BOS 36-46. BOS swept NYY last 4 games.
    # Mikolas vs TBD. BOS big home fav despite losing record.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -170,
            "ml_away": 145,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. Chicago White Sox @ Baltimore Orioles
    # BAL -137, CHW +114. Shane Baz vs Sean Burke.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.300,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -137,
            "ml_away": 114,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 3. Pittsburgh Pirates @ Philadelphia Phillies
    # PHI -116, PIT -102. Aaron Nola vs Braxton Ashcraft.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.7,
            "season_opp_ppg": 3.5,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -116,
            "ml_away": -102,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. Detroit Tigers @ New York Yankees
    # NYY -149, DET +124. Run line NYY -1.5. Total 7.5.
    # NYY swept by BOS (3-7 L10), DET 14 games under .500.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.8,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.1,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -149,
            "ml_away": 124,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 5. New York Mets @ Toronto Blue Jays
    # TOR -130, NYM +107. Manaea vs Yesavage. Total 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 107,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 6. Texas Rangers @ Cleveland Guardians
    # CLE -142, TEX +120. Alexander (1-1, 2.65) vs Messick (7-4, 2.70).
    # CLE 44-40, TEX 42-42. Progressive Field.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 7. Cincinnati Reds @ Milwaukee Brewers
    # MIL fav (~-152), CIN +128.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -152,
            "ml_away": 128,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. San Diego Padres @ Chicago Cubs
    # CHC -154, SD +130. Cubs home fav.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -154,
            "ml_away": 130,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 9. Minnesota Twins @ Houston Astros
    # HOU -132, MIN +110.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -132,
            "ml_away": 110,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 10. Miami Marlins @ Colorado Rockies
    # MIA -142 road fav, COL +116 home dog. Coors Field.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 3.9,
            "season_opp_ppg": 5.0,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.260,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 116,
            "ml_away": -142,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 11. San Francisco Giants @ Arizona Diamondbacks
    # ARI -132, SF +110.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -132,
            "ml_away": 110,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. Los Angeles Angels @ Seattle Mariners
    # SEA -220 big fav, LAA +184 big dog.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.5,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.320,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -220,
            "ml_away": 184,
            "total": 7.0,
            "book": "fanduel"
        }
    },

    # 13. Los Angeles Dodgers @ Sacramento Athletics
    # LAD -126 road fav, SAC +106 home dog.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 106,
            "ml_away": -126,
            "total": 8.5,
            "book": "fanduel"
        }
    },
]

# ── Build batch ─────────────────────────────────────────────────────
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

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

results = run_batch(batch)

# ── Organize results by game ────────────────────────────────────────
games_results = {}
for i, result in enumerate(results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game_key = f"{games_raw[game_idx]['away']['name']} @ {games_raw[game_idx]['home']['name']}"

    if game_key not in games_results:
        games_results[game_key] = {
            "game_data": games_raw[game_idx],
            "model_results": {}
        }
    games_results[game_key]["model_results"][all_models[model_idx]["id"]] = result

# ── Compute blended predictions ─────────────────────────────────────
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
        w = 1.0 if mid == champion["id"] else next(c["weight"] for c in challengers if c["id"] == mid)
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
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

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
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
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
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Display results ─────────────────────────────────────────────────
sport_preds = [p for p in predictions if p["sport"] == "baseball_mlb"]

print(f"\n{'=' * 90}")
print(f" MLB — Monday June 29, 2026")
print(f"{'=' * 90}")
print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5}  {'Verdict':<16}")
print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*5}  {'-'*16}")

bets = []
for p in sport_preds:
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


# ── Update metrics.json ─────────────────────────────────────────────
metrics_file = os.path.join(BASE, "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

eval_games = model_scores[champion["id"]]["total"]
eval_correct = model_scores[champion["id"]]["correct"]
eval_acc = eval_correct / eval_games if eval_games > 0 else 0.5

prev_all = metrics["all_time"]

jun28_bets = [p for p in past_preds["predictions"] if p["verdict"] == "BET"]
jun28_bet_wins = 0
jun28_bet_total = len(jun28_bets)
for bp in jun28_bets:
    gk = bp["game"]
    if gk not in actual_results:
        continue
    actual = actual_results[gk]
    margin = actual["home_score"] - actual["away_score"]
    bt = bp["best_bet_type"]
    spread = bp["odds"]["spread_home"]
    if bt == "spread_home":
        won = (margin + spread) > 0
    elif bt == "spread_away":
        won = (-margin - spread) > 0
    elif bt == "ml_home":
        won = actual["winner"] == "home"
    else:
        won = actual["winner"] == "away"
    if won:
        jun28_bet_wins += 1

new_all_games = prev_all["total_games"] + eval_games
new_all_correct = prev_all["total_correct"] + eval_correct
new_all_bets = prev_all["total_bets_recommended"] + jun28_bet_total
new_all_bets_won = prev_all["total_bets_won"] + jun28_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_games, 4) if eval_games > 0 else 0.5,
    "ev_realized": round((jun28_bet_wins * 0.909 - (jun28_bet_total - jun28_bet_wins)) / max(jun28_bet_total, 1), 4),
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
    s = model_scores.get(mid, {"correct": 0, "total": 0})
    vp = metrics.get("variant_performance", {}).get(mid, {})
    metrics.setdefault("variant_performance", {})[mid] = {
        "lifetime_games": vp.get("lifetime_games", 0) + s["total"],
        "lifetime_correct": vp.get("lifetime_correct", 0) + s["correct"],
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
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"MLB only ({len(predictions)} games). {total_bets_today} BETs, {total_leans_today} LEANs. Eval Jun 28: {eval_correct}/{eval_games} correct."
}

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Summary stats ───────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" SUMMARY: {len(predictions)} games analyzed | {total_bets_today} BETs | {total_leans_today} LEANs | {total_no_today} NO BETs")
print(f"{'=' * 90}")

print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  Jun 28 eval: {eval_correct}/{eval_games} = {eval_acc:.1%} accuracy")
print(f"  Jun 28 bets: {jun28_bet_wins}/{jun28_bet_total} = {jun28_bet_wins/max(jun28_bet_total,1):.1%} hit rate")
print(f"  All-time: {new_all_correct}/{new_all_games} = {new_all_correct/new_all_games:.1%} accuracy | {new_all_bets_won}/{new_all_bets} bets won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
