#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-04.
Phase 1: Eval July 3 predictions, update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-04"
EVAL_DATE = "2026-07-03"

# ════════════════════════���═══════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 3 PREDICTIONS
# ═══════════════════════���═══════════════════════════════���════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-03 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

actual_results = {
    "St. Louis Cardinals @ Chicago Cubs": {"winner": "away", "home_score": 1, "away_score": 17},
    "Pittsburgh Pirates @ Washington Nationals": {"winner": "home", "home_score": 9, "away_score": 5},
    "Minnesota Twins @ New York Yankees": {"winner": "home", "home_score": 5, "away_score": 2},
    "Baltimore Orioles @ Cincinnati Reds": {"winner": "away", "home_score": 0, "away_score": 3},
    "Chicago White Sox @ Cleveland Guardians": {"winner": "home", "home_score": 4, "away_score": 3},
    "New York Mets @ Atlanta Braves": {"winner": "home", "home_score": 5, "away_score": 3},
    "San Francisco Giants @ Colorado Rockies": {"winner": "home", "home_score": 15, "away_score": 3},
    "Tampa Bay Rays @ Houston Astros": {"winner": "away", "home_score": 1, "away_score": 3},
    "Boston Red Sox @ Los Angeles Angels": {"winner": "away", "home_score": 2, "away_score": 5},
    "Miami Marlins @ Sacramento Athletics": {"winner": "away", "home_score": 5, "away_score": 12},
    "Milwaukee Brewers @ Arizona Diamondbacks": {"winner": "away", "home_score": 4, "away_score": 7},
    "San Diego Padres @ Los Angeles Dodgers": {"winner": "home", "home_score": 4, "away_score": 3},
    "Toronto Blue Jays @ Seattle Mariners": {"winner": "away", "home_score": 0, "away_score": 2},
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

# ── Step 1.6: Retirement check ─────────────────���────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 7, 4) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════��══════════════════════════════��═════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 4, 2026)
# ═══════════════════════════════���═════════════════════════════��══════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Tonight's games with live odds ─────────────────────────────────
# MLB only — NBA and NHL seasons are over. 15-game July 4th slate.

games_raw = [
    # 1. Pittsburgh Pirates @ Washington Nationals (11:05 AM ET)
    # Pirates -160 / Nationals +134. O/U 8.5.
    # Ashcraft (8-3, 3.33 ERA) vs Littell (7-6, 5.29 ERA). PIT road fav.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 134,
            "ml_away": -160,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. Minnesota Twins @ New York Yankees (1:35 PM ET)
    # Yankees -158 / Twins +140. O/U 8.5.
    # Matthews (4-5, 4.15) vs Beck (0-0, 6.00). NYY home fav despite weaker arm.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.7,
            "last10_ppg": 5.3,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.630,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.390,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -158,
            "ml_away": 140,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. St. Louis Cardinals @ Chicago Cubs (4:05 PM ET)
    # Cubs -156 / Cardinals +135. O/U 8.5.
    # Imanaga (5-6, 4.30) vs Leahy (6-4, 4.09). Cubs home fav.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 135,
            "total": 8.5,
            "book": "draftkings"
        }
    },

    # 4. New York Mets @ Atlanta Braves (4:05 PM ET)
    # Braves -171 / Mets +141. O/U 8.0.
    # Chris Sale (8-6, 2.10 ERA) on mound for ATL. ATL 50-34.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -171,
            "ml_away": 141,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 5. Chicago White Sox @ Cleveland Guardians (4:10 PM ET)
    # Guardians -145 / White Sox +118. O/U 7.5.
    # G3 of series. CLE won G1, G2 in tight fashion.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -145,
            "ml_away": 118,
            "total": 7.5,
            "book": "bet365"
        }
    },

    # 6. Baltimore Orioles @ Cincinnati Reds (4:10 PM ET)
    # Reds -125 / Orioles +105. O/U 9.0.
    # Great American Ball Park plays as hitter-friendly.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 9.0,
            "book": "bet365"
        }
    },

    # 7. Philadelphia Phillies @ Kansas City Royals (4:10 PM ET)
    # Phillies -156 / Royals +132. O/U 9.0.
    # Luzardo for PHI. PHI ~47-38.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 132,
            "ml_away": -156,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 8. Detroit Tigers @ Texas Rangers (4:10 PM ET)
    # Rangers favored. Spread -1.5. O/U 7.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.1,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -135,
            "ml_away": 115,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 9. Houston Astros @ Tampa Bay Rays (7:10 PM ET)
    # Pick'em: Rays -108 / Astros -108. O/U 9.0.
    # TB 52-33 best AL record, 9-game win streak. HOU 43-47.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.9,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.630,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 10. San Francisco Giants @ Colorado Rockies (8:10 PM ET)
    # Giants -130 / Rockies +110. O/U 11.5.
    # Coors Field. Ray (7-6) vs Sugano (8-4). COL won 15-3 yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.0,
            "season_opp_ppg": 5.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.390,
            "away_record_pct": 0.260,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -130,
            "total": 11.5,
            "book": "fanduel"
        }
    },

    # 11. Boston Red Sox @ Los Angeles Angels (9:38 PM ET)
    # Red Sox -164 / Angels +138. O/U 8.5.
    # Sonny Gray (9-1, 2.69) vs Aldegheri (3-3, 4.85).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.340,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 138,
            "ml_away": -164,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 12. Miami Marlins @ Sacramento Athletics (9:40 PM ET)
    # Marlins -120 / Athletics +102. O/U 11.0.
    # MIA won 12-5 yesterday. Tyler Phillips for SAC.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 102,
            "ml_away": -120,
            "total": 11.0,
            "book": "fanduel"
        }
    },

    # 13. Milwaukee Brewers @ Arizona Diamondbacks (9:45 PM ET)
    # Brewers -149 / D-Backs +123. O/U 9.0.
    # MIL 52-31 (best NL). ARI ~42-43.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.550,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 123,
            "ml_away": -149,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 14. San Diego Padres @ Los Angeles Dodgers (10:10 PM ET)
    # Dodgers -250 / Padres +200. O/U 8.0.
    # Yamamoto (8-5, 2.67) vs Canning (1-5, 7.09). LAD 57-31.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.1,
            "season_opp_ppg": 3.4,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.710,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -250,
            "ml_away": 200,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 15. Toronto Blue Jays @ Seattle Mariners (10:10 PM ET)
    # Mariners -160 / Blue Jays +134. O/U 7.0.
    # SEA 45-43 with strong pitching. TOR 41-44.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -160,
            "ml_away": 134,
            "total": 7.0,
            "book": "fanduel"
        }
    },
]

# ── Build batch ─────────────────────���───────────────────────────────
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

# ── Display results ────────────��───────────────────��────────────────
print(f"\n{'=' * 90}")
print(f" MLB — Saturday July 4, 2026 (Independence Day)")
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


# ── Update metrics.json ─────────────────────────────────────────────
metrics_file = os.path.join(BASE, "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

eval_games = model_scores[champion["id"]]["total"]
eval_correct = model_scores[champion["id"]]["correct"]
eval_acc = eval_correct / eval_games if eval_games > 0 else 0.5

prev_all = metrics["all_time"]

jul3_bets = [p for p in past_preds["predictions"] if p["verdict"] == "BET"]
jul3_bet_wins = 0
jul3_bet_total = len(jul3_bets)
for bp in jul3_bets:
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
        jul3_bet_wins += 1

new_all_games = prev_all["total_games"] + eval_games
new_all_correct = prev_all["total_correct"] + eval_correct
new_all_bets = prev_all["total_bets_recommended"] + jul3_bet_total
new_all_bets_won = prev_all["total_bets_won"] + jul3_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_games, 4) if eval_games > 0 else 0.5,
    "ev_realized": round((jul3_bet_wins * 0.909 - (jul3_bet_total - jul3_bet_wins)) / max(jul3_bet_total, 1), 4),
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
    "sports": ["baseball_mlb"],
    "notes": f"MLB July 4th ({len(predictions)} games). {total_bets_today} BETs, {total_leans_today} LEANs. Eval Jul 3: {eval_correct}/{eval_games} correct."
}

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Summary stats ────────────────────────────���──────────────────────
print(f"\n{'=' * 90}")
print(f" SUMMARY: {len(predictions)} games analyzed | {total_bets_today} BETs | {total_leans_today} LEANs | {total_no_today} NO BETs")
print(f"{'=' * 90}")

print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  Jul 3 eval: {eval_correct}/{eval_games} = {eval_acc:.1%} accuracy")
print(f"  Jul 3 bets: {jul3_bet_wins}/{jul3_bet_total} = {jul3_bet_wins/max(jul3_bet_total,1):.1%} hit rate")
print(f"  All-time: {new_all_correct}/{new_all_games} = {new_all_correct/new_all_games:.1%} accuracy | {new_all_bets_won}/{new_all_bets} bets won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
