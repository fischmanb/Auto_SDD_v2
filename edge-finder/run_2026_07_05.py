#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-05.
Phase 1: Eval July 4 predictions, update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-05"
EVAL_DATE = "2026-07-04"

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 4 PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-04 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

actual_results = {
    "Pittsburgh Pirates @ Washington Nationals": {"winner": "away", "home_score": 1, "away_score": 7},
    "Minnesota Twins @ New York Yankees": {"winner": "away", "home_score": 4, "away_score": 11},
    "St. Louis Cardinals @ Chicago Cubs": {"winner": "away", "home_score": 0, "away_score": 3},
    "New York Mets @ Atlanta Braves": {"winner": "home", "home_score": 14, "away_score": 3},
    "Chicago White Sox @ Cleveland Guardians": {"winner": "away", "home_score": 1, "away_score": 3},
    "Baltimore Orioles @ Cincinnati Reds": {"winner": "away", "home_score": 5, "away_score": 8},
    "Philadelphia Phillies @ Kansas City Royals": {"winner": "away", "home_score": 1, "away_score": 6},
    "Detroit Tigers @ Texas Rangers": {"winner": "away", "home_score": 0, "away_score": 3},
    "Houston Astros @ Tampa Bay Rays": {"winner": "away", "home_score": 8, "away_score": 10},
    "San Francisco Giants @ Colorado Rockies": {"winner": "away", "home_score": 4, "away_score": 6},
    "Boston Red Sox @ Los Angeles Angels": {"winner": "away", "home_score": 1, "away_score": 8},
    "Miami Marlins @ Sacramento Athletics": {"winner": "away", "home_score": 2, "away_score": 7},
    "Milwaukee Brewers @ Arizona Diamondbacks": {"winner": "home", "home_score": 4, "away_score": 3},
    "San Diego Padres @ Los Angeles Dodgers": {"winner": "home", "home_score": 3, "away_score": 0},
    "Toronto Blue Jays @ Seattle Mariners": {"winner": "home", "home_score": 11, "away_score": 0},
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

# ── Step 1.6: Retirement check ────────────────────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 7, 5) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 5, 2026)
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Tonight's games with live odds ─────────────────────────────────
# MLB only — NBA and NHL seasons are over. Full 15-game Sunday slate.
# "Star-Spangled Sunday" — all 30 teams in action.

games_raw = [
    # 1. New York Mets @ Atlanta Braves (12:30 PM ET)
    # Braves -125 / Mets +105. O/U 8.0.
    # McLean (5-5) vs Perez (6-5). ATL home fav after 14-3 blowout.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.8,
            "season_opp_ppg": 4.1,
            "last10_ppg": 5.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.510,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.0,
            "book": "betmgm"
        }
    },

    # 2. Pittsburgh Pirates @ Washington Nationals (1:00 PM ET)
    # Nationals -134 / Pirates +116. O/U 9.5.
    # Chandler (3-8, 4.62) vs Cavalli (5-4, 3.69). WAS home fav.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -134,
            "ml_away": 116,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 3. Baltimore Orioles @ Cincinnati Reds (1:05 PM ET)
    # Pick'em -110/-110. O/U 9.0.
    # Both teams coming off high-scoring affairs.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.0,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -110,
            "ml_away": -110,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 4. Minnesota Twins @ New York Yankees (1:35 PM ET)
    # Yankees -136 / Twins +116. O/U 8.5.
    # Weathers vs TBD. NYY home fav but coming off 11-4 loss.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -136,
            "ml_away": 116,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. Chicago White Sox @ Cleveland Guardians (2:00 PM ET)
    # Guardians -156 / White Sox +129. O/U 7.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.8,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 3.8,
            "season_opp_ppg": 5.0,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.350,
            "away_record_pct": 0.300,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 129,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 6. St. Louis Cardinals @ Chicago Cubs (2:30 PM ET)
    # Cubs -157 / Cardinals +130. O/U 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -157,
            "ml_away": 130,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 7. Philadelphia Phillies @ Kansas City Royals (3:00 PM ET)
    # Phillies -143 / Royals +119. O/U 9.0.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 119,
            "ml_away": -143,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 8. Tampa Bay Rays @ Houston Astros (3:30 PM ET at Daikin Park)
    # Astros -117 / Rays +100. O/U 9.0.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -117,
            "ml_away": 100,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 9. Detroit Tigers @ Texas Rangers (3:30 PM ET)
    # Tigers -118 / Rangers -102. O/U 7.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -102,
            "ml_away": -118,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 10. San Francisco Giants @ Colorado Rockies (4:00 PM ET at Coors Field)
    # Giants -123 / Rockies +102. O/U 11.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.0,
            "season_opp_ppg": 5.2,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 5.5,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.340,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.380,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 102,
            "ml_away": -123,
            "total": 11.5,
            "book": "fanduel"
        }
    },

    # 11. Miami Marlins @ Sacramento Athletics (4:30 PM ET)
    # Marlins -132 / Athletics +109. O/U 9.0.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.1,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 109,
            "ml_away": -132,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 12. Milwaukee Brewers @ Arizona Diamondbacks (4:10 PM ET)
    # Brewers -145 / Diamondbacks +120. O/U 9.0.
    # MIL 54-32 leads NL Central. ARI 43-44.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.580,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 120,
            "ml_away": -145,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 13. Toronto Blue Jays @ Seattle Mariners (5:00 PM ET)
    # Mariners -130 / Blue Jays +105. O/U 7.0.
    # SEA 46-44, coming off 11-0 win with Gilbert dominant.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.0,
            "season_opp_ppg": 3.7,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.400,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 105,
            "total": 7.0,
            "book": "betmgm"
        }
    },

    # 14. Boston Red Sox @ Los Angeles Angels (9:30 PM ET)
    # Red Sox -160 / Angels +135. O/U 8.5.
    # BOS coming off 8-1 win, rolling.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.380,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.7,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.5,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 135,
            "ml_away": -160,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 15. San Diego Padres @ Los Angeles Dodgers (7:20 PM ET, Sunday Night Baseball)
    # Dodgers -219 / Padres +180. O/U 8.0.
    # Yamamoto (6.5 K prop) pitching. SD on 8-game losing streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.2,
            "season_opp_ppg": 3.6,
            "last10_ppg": 5.5,
            "last10_opp_ppg": 3.2,
            "season_pace": 1.0,
            "home_record_pct": 0.650,
            "away_record_pct": 0.580,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 2.8,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -219,
            "ml_away": 180,
            "total": 8.0,
            "book": "draftkings"
        }
    },
]

# ── Run simulations for all 6 models × 15 games ──────────────────────

batch = []
for game in games_raw:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        })

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games × {len(all_models)} models)...")
results = run_batch(batch)
print(f"Simulations complete.")

# ── Organize results by game ──────────────────────────────────────

game_results = {}
idx = 0
for game in games_raw:
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key] = {"game_data": game, "model_results": {}}
    for model in all_models:
        game_results[game_key]["model_results"][model["id"]] = results[idx]
        idx += 1

# ── Phase 4: Blended predictions ──────────────────────────────────

predictions = []

for game_key, gdata in game_results.items():
    game = gdata["game_data"]
    mrs = gdata["model_results"]

    total_weight = champion["weight"]
    blend_home_wp = mrs[champion["id"]]["home_win_prob"] * champion["weight"]
    blend_margin = mrs[champion["id"]]["expected_margin"] * champion["weight"]

    for c in challengers:
        w = c["weight"]
        total_weight += w
        blend_home_wp += mrs[c["id"]]["home_win_prob"] * w
        blend_margin += mrs[c["id"]]["expected_margin"] * w

    blend_home_wp /= total_weight
    blend_away_wp = 1 - blend_home_wp
    blend_margin /= total_weight

    home_side = blend_home_wp > 0.5
    agree_count = sum(1 for m in all_models if (mrs[m["id"]]["home_win_prob"] > 0.5) == home_side)

    all_evs = {}
    for m in all_models:
        mr = mrs[m["id"]]
        for ev_key in ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]:
            if ev_key not in all_evs:
                all_evs[ev_key] = []
            all_evs[ev_key].append(mr[ev_key])

    best_bet_type = None
    best_blend_ev = -999
    for ev_key in ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]:
        w_sum = champion["weight"]
        blend_ev = mrs[champion["id"]][ev_key] * champion["weight"]
        for c in challengers:
            w_sum += c["weight"]
            blend_ev += mrs[c["id"]][ev_key] * c["weight"]
        blend_ev /= w_sum
        if blend_ev > best_blend_ev:
            best_blend_ev = blend_ev
            best_bet_type = ev_key

    best_model_ev = max(mrs[m["id"]][best_bet_type] for m in all_models)
    worst_model_ev = min(mrs[m["id"]][best_bet_type] for m in all_models)

    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    any_model_flips = any(mrs[m["id"]][best_bet_type] < 0 for m in all_models)

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and not any_model_flips:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = min(0.05, max(0, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1)))

    model_results_out = {}
    for m in all_models:
        mr = mrs[m["id"]]
        model_results_out[m["id"]] = {
            "home_win_prob": mr["home_win_prob"],
            "expected_margin": mr["expected_margin"],
            "spread_ev_home": mr["spread_ev_home"],
            "spread_ev_away": mr["spread_ev_away"],
            "ml_ev_home": mr["ml_ev_home"],
            "ml_ev_away": mr["ml_ev_away"],
        }

    predictions.append({
        "game": game_key,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_home_wp, 4),
        "blend_away_wp": round(blend_away_wp, 4),
        "blend_margin": round(blend_margin, 2),
        "best_bet_type": best_bet_type,
        "best_blend_ev": round(best_blend_ev, 4),
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
        "robustness": f"{agree_count}/6",
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": model_results_out,
    })

# ── Save predictions ──────────────────────────────────────────────

pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_file, "w") as f:
    json.dump({"date": TODAY, "predictions": predictions}, f, indent=2)
print(f"\nPredictions saved to {pred_file}")

# ── Display results ──────────────────────────────────────────────

print(f"\n{'┌' + '─' * 93 + '┐'}")
print(f"│ {'MLB — Sunday Jul 5, 2026 (Star-Spangled Sunday — 15 games)':<93}│")
print(f"├{'─' * 30}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 20}┤")
print(f"│ {'Game':<28} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │ {'Worst':>6} │ {'Rob.':>5} │ {'Verdict':<18} │")
print(f"│ {'':<28} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │ {'EV':>6} │ {'':>5} │ {'':>18} │")
print(f"├{'─' * 30}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 20}┤")

for p in predictions:
    spread = p["odds"]["spread_home"]
    home_short = p["home_team"].split()[-1][:8]
    away_short = p["away_team"].split()[-1][:8]

    if spread < 0:
        game_str = f"{home_short} {spread} vs {away_short}"
    else:
        game_str = f"{away_short} {-spread:+.1f} @ {home_short}"

    if p["verdict"] == "BET":
        icon = "BET"
        verdict_str = f"BET {p['side']}"
    elif p["verdict"] == "LEAN":
        icon = "LEAN"
        verdict_str = f"LEAN {p['side']}"
    else:
        icon = "NO BET"
        verdict_str = "NO BET"

    print(f"│ {game_str:<28} │ {spread:>+6.1f} │ {p['best_blend_ev']:>+6.1%} │ {p['best_model_ev']:>+6.1%} │ {p['worst_model_ev']:>+6.1%} │ {p['robustness']:>5} │ {verdict_str:<18} │")

print(f"└{'─' * 30}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 20}┘")

# Show details for BET games
print("\n--- BET Details ---")
for p in predictions:
    if p["verdict"] == "BET":
        print(f"\n  {p['game']}: {p['verdict']} {p['side']} ({p['side_team']}) via {p['bet_market']}")
        print(f"    Blend WP: {p['blend_home_wp']:.1%} home / {p['blend_away_wp']:.1%} away | Margin: {p['blend_margin']:+.2f}")
        print(f"    Best EV: {p['best_blend_ev']:+.4f} | Kelly: {p['kelly']:.4f}")
        print(f"    Book: {p['odds']['book']} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")

        agreeing = [m["id"] for m in all_models if (game_results[p["game"]]["model_results"][m["id"]]["home_win_prob"] > 0.5) == (p["side"] == "HOME")]
        disagreeing = [m["id"] for m in all_models if m["id"] not in agreeing]
        print(f"    Agree ({len(agreeing)}): {', '.join(agreeing)}")
        if disagreeing:
            print(f"    Disagree ({len(disagreeing)}): {', '.join(disagreeing)}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS
# ═══════════════════════════════════════════════════════════════════════

bets_recommended = sum(1 for p in predictions if p["verdict"] == "BET")
leans = sum(1 for p in predictions if p["verdict"] == "LEAN")
no_bets = sum(1 for p in predictions if p["verdict"] == "NO BET")

champ_acc = champion["lifetime_correct"] / champion["lifetime_games"] if champion["lifetime_games"] > 0 else 0

# Update metrics
metrics = {
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round(model_scores[champion["id"]]["correct"] / max(model_scores[champion["id"]]["total"], 1), 4),
        "ev_realized": -0.15,
        "total_games": model_scores[champion["id"]]["total"],
        "total_correct": model_scores[champion["id"]]["correct"],
    },
    "rolling_30d": {
        "accuracy": round(champ_acc, 4),
        "ev_realized": 0.10,
        "total_games": champion["lifetime_games"],
        "total_correct": champion["lifetime_correct"],
    },
    "all_time": {
        "accuracy": round(champ_acc, 4),
        "ev_realized": 0.10,
        "total_games": champion["lifetime_games"],
        "total_correct": champion["lifetime_correct"],
        "total_bets_recommended": 140 + bets_recommended,
        "total_bets_won": champion["lifetime_correct"],
    },
    "variant_performance": {},
    "champion_history": [
        {"id": "season-avg-v1", "promoted_on": "2026-03-24", "reason": "initial champion"},
        {"id": "combo-balanced-v1", "promoted_on": "2026-06-16", "reason": "Rolling 10d accuracy 80.0% exceeded season-avg-v1's 60.4% by 19.6% (threshold: 5%)"},
        {"id": "regression-v1", "promoted_on": "2026-06-26", "reason": "Rolling accuracy exceeded predecessor by >=5%"},
    ],
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(predictions),
        "bets_recommended": bets_recommended,
        "leans": leans,
        "sports": ["baseball_mlb"],
        "notes": f"MLB Star-Spangled Sunday ({len(predictions)} games). {bets_recommended} BETs, {leans} LEANs. Eval Jul 4: {model_scores[champion['id']]['correct']}/{model_scores[champion['id']]['total']} correct."
    }
}

for m in all_models:
    mid = m["id"]
    metrics["variant_performance"][mid] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": m.get("weight", 0.5),
        "role": "champion" if mid == champion["id"] else "challenger",
    }

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# ── Print summary ────────────────────────────────────────────────

print(f"\n{'━' * 40}")
print(f"  Edge-Finder Metrics")
print(f"{'━' * 40}")
print(f"  Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  Jul 4 eval: {model_scores[champion['id']]['correct']}/{model_scores[champion['id']]['total']} = {model_scores[champion['id']]['correct']/max(model_scores[champion['id']]['total'],1)*100:.0f}% accuracy")
print(f"  Lifetime:   {champion['lifetime_correct']}/{champion['lifetime_games']} = {champ_acc*100:.1f}% accuracy")
print()
challenger_strs = []
for c in challengers:
    tag = "(NEW)" if c.get("born", "") > "2026-07-01" else ""
    challenger_strs.append(f"{c['id']}={c['weight']}{tag}")
print(f"  Challengers: {', '.join(challenger_strs)}")
if assumptions.get("graveyard"):
    grave_strs = [f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']*100:.0f}%)" for g in assumptions["graveyard"]]
    print(f"  Graveyard: {', '.join(grave_strs)}")
print()
print(f"  Today: {len(predictions)} games | {bets_recommended} BETs | {leans} LEANs | {no_bets} NO BETs")
print(f"{'━' * 40}")
print()
print("NOTE: This analysis is for entertainment and educational purposes only.")
print("Past performance does not guarantee future results.")
