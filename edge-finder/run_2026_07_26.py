#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-26.
Phase 1: Eval July 25 predictions (15 MLB games).
Phase 2-5: Simulate tonight's 15 MLB games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-26"
EVAL_DATE = "2026-07-25"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 25 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-25 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 25, 2026 (sourced via ESPN, MLB.com, Baseball-Reference)
actual_results = {
    "Kansas City Royals @ Detroit Tigers": {"winner": "away", "home_score": 2, "away_score": 3},
    "Arizona Diamondbacks @ Washington Nationals": {"winner": "home", "home_score": 5, "away_score": 3},
    "Los Angeles Angels @ San Francisco Giants": {"winner": "home", "home_score": 9, "away_score": 2},
    "Toronto Blue Jays @ Boston Red Sox": {"winner": "away", "home_score": 0, "away_score": 6},
    "San Diego Padres @ Miami Marlins": {"winner": "away", "home_score": 2, "away_score": 7},
    "New York Yankees @ Philadelphia Phillies": {"winner": "away", "home_score": 1, "away_score": 3},
    "Cleveland Guardians @ Tampa Bay Rays": {"winner": "home", "home_score": 3, "away_score": 0},
    "Chicago Cubs @ Pittsburgh Pirates": {"winner": "away", "home_score": 0, "away_score": 11},
    "Atlanta Braves @ Baltimore Orioles": {"winner": "home", "home_score": 3, "away_score": 2},
    "Oakland Athletics @ Minnesota Twins": {"winner": "home", "home_score": 2, "away_score": 0},
    "Houston Astros @ Chicago White Sox": {"winner": "away", "home_score": 1, "away_score": 4},
    "Colorado Rockies @ Milwaukee Brewers": {"winner": "home", "home_score": 8, "away_score": 5},
    "Los Angeles Dodgers @ New York Mets": {"winner": "away", "home_score": 3, "away_score": 4},
    "Cincinnati Reds @ St. Louis Cardinals": {"winner": "home", "home_score": 7, "away_score": 0},
    "Seattle Mariners @ Texas Rangers": {"winner": "home", "home_score": 7, "away_score": 1},
}

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
champ_id = champion["id"]
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
    if mid == champ_id:
        role = "CHAMP"
    else:
        role = f"w={next(c['weight'] for c in challengers if c['id'] == mid)}"
    print(f"  {mid:<20} {s['correct']}/{s['total']} = {pct:.1f}% [{role}]")

# ── Step 1.4: Update challenger weights ──────────────────────────────
champ_hits = set()
champ_misses = set()

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

for c in challengers:
    cid = c["id"]
    c["rolling_10d_accuracy"] = model_scores[cid]["correct"] / model_scores[cid]["total"] if model_scores[cid]["total"] > 0 else 0.5

# ── Step 1.5: Promotion check ──────────────────────────────────────
champ_lifetime_acc = champion["lifetime_correct"] / champion["lifetime_games"] if champion["lifetime_games"] > 0 else 0.5
promotion_msg = ""
c_to_promote = None
for c in challengers:
    cid = c["id"]
    c_lifetime_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
    if c["rolling_10d_accuracy"] - champion["rolling_10d_accuracy"] >= 0.05:
        promotion_msg = f"PROMOTION: {cid} replaces {champ_id} as champion"
        print(f"\n  *** {promotion_msg} ***")
        old_champ = dict(champion)
        champion_data = dict(c)
        champion_data["weight"] = 1.0
        c_to_promote = cid
        break

if promotion_msg and c_to_promote:
    assumptions["champion"] = champion_data
    for i, ch in enumerate(assumptions["challengers"]):
        if ch["id"] == c_to_promote:
            old_champ["weight"] = 0.7
            assumptions["challengers"][i] = old_champ
            break
    champion = assumptions["champion"]
    challengers = assumptions["challengers"]
    champ_id = champion["id"]
else:
    print("\n  No promotions triggered.")

# ── Step 1.6: Retirement check ──────────────────────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 7, 26) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 26, 2026)
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
champ_id = champion["id"]

# ── Tonight's games with odds sourced via web search ──────────────────
# Sunday July 26, 2026 — MLB only (NBA/NHL/NFL off-season)
# 15 games (series finales). Odds sourced from FanDuel, BetMGM, DraftKings, OddsShark.
# Stats adjusted from yesterday's predictions + July 25 results.
# BOS's 14-game win streak snapped by TOR (Cease CG shutout).
# MIA losing streak extended to 11. HOU on 5-game win streak.

games_raw = [
    # 1. KC Royals @ DET Tigers — Sunday series finale
    # DET won 2 of 3 already but KC won last night. DET heavy home fav.
    # Lines: DET -162 / KC +136
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.510,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.370,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -162,
            "ml_away": 136,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 2. ARI Diamondbacks @ WSH Nationals — Sunday 1:35 PM ET
    # ARI road favorite today (pitching edge). ARI -118 / WSH +100
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 5.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -118,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. LAA Angels @ SF Giants — Sunday 4:05 PM ET
    # SF home slight fav. SF -116 / LAA -102.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.370,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -116,
            "ml_away": -102,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 4. TOR Blue Jays @ BOS Red Sox — Sunday 1:35 PM ET
    # BOS bouncing back after shutout loss. BOS -136 / TOR +116.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -136,
            "ml_away": 116,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 5. SD Padres @ MIA Marlins — Sunday 1:40 PM ET
    # MIA 11 straight losses but still home fav per books. MIA -131 / SD +110.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -131,
            "ml_away": 110,
            "total": 8.5,
            "book": "betmgm"
        }
    },

    # 6. NYY Yankees @ PHI Phillies — Sunday 1:35 PM ET
    # PHI heavy home fav. PHI -162 / NYY +144.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -162,
            "ml_away": 144,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 7. CLE Guardians @ TB Rays — Sunday 12:15 PM ET
    # TB home fav after shutout yesterday. TB -125 / CLE +105.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 8. CHC Cubs @ PIT Pirates — Sunday 1:35 PM ET
    # PIT home, slight fav (pitching). PIT -120 / CHC +102. Cubs won 11-0 last night.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 102,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 9. ATL Braves @ BAL Orioles — Sunday 1:35 PM ET
    # BAL home, slight fav. BAL -116 / ATL -102.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.590,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
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

    # 10. OAK Athletics @ MIN Twins — Sunday 2:10 PM ET
    # MIN home fav. MIN -141 / OAK +121. OAK shut out last 2 games.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Oakland Athletics",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.360,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -141,
            "ml_away": 121,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 11. HOU Astros @ CHW White Sox — Sunday 2:10 PM ET
    # Pick'em per books. HOU -110 / CHW -110. HOU on 5-game streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.330,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -110,
            "ml_away": -110,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 12. COL Rockies @ MIL Brewers — Sunday 2:10 PM ET
    # MIL massive home fav. MIL -325 / COL +256.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 4.0,
            "season_opp_ppg": 5.1,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.4,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.300,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -325,
            "ml_away": 256,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 13. LAD Dodgers @ NYM Mets — Sunday 1:40 PM ET
    # LAD road fav again. LAD -154 / NYM +130.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.3,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.600,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 130,
            "ml_away": -154,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 14. CIN Reds @ STL Cardinals — Sunday 2:15 PM ET
    # STL home fav after shutout. STL -135 / CIN +110.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -135,
            "ml_away": 110,
            "total": 8.5,
            "book": "draftkings"
        }
    },

    # 15. SEA Mariners @ TEX Rangers — Sunday 2:35 PM ET
    # TEX very slight home fav. TEX -113 / SEA -107. Near pick'em.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 3.9,
            "season_opp_ppg": 3.7,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -113,
            "ml_away": -107,
            "total": 7.5,
            "book": "fanduel"
        }
    },
]


# ── Build batch for all models ──────────────────────────────────────
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

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games × {len(all_models)} models)...")
results = run_batch(batch)
print(f"  Simulations complete.")

# ── Organize results by game ──────────────────────────────────────
game_results = {}
idx = 0
for game in games_raw:
    game_name = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_name] = {
        "game_data": game,
        "model_results": {}
    }
    for model in all_models:
        game_results[game_name]["model_results"][model["id"]] = results[idx]
        idx += 1

# ── Blended predictions ──────────────────────────────────────────
predictions = []

for game_name, gd in game_results.items():
    game = gd["game_data"]
    mr = gd["model_results"]

    # Compute weighted blend
    total_weight = 1.0  # champion weight
    blend_home_wp = mr[champ_id]["home_win_prob"] * 1.0
    blend_spread_ev_home = mr[champ_id]["spread_ev_home"] * 1.0
    blend_spread_ev_away = mr[champ_id]["spread_ev_away"] * 1.0
    blend_ml_ev_home = mr[champ_id]["ml_ev_home"] * 1.0
    blend_ml_ev_away = mr[champ_id]["ml_ev_away"] * 1.0

    for c in challengers:
        cid = c["id"]
        w = c["weight"]
        total_weight += w
        blend_home_wp += mr[cid]["home_win_prob"] * w
        blend_spread_ev_home += mr[cid]["spread_ev_home"] * w
        blend_spread_ev_away += mr[cid]["spread_ev_away"] * w
        blend_ml_ev_home += mr[cid]["ml_ev_home"] * w
        blend_ml_ev_away += mr[cid]["ml_ev_away"] * w

    blend_home_wp /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin = sum(mr[m["id"]]["expected_margin"] * (1.0 if m["id"] == champ_id else next(c["weight"] for c in challengers if c["id"] == m["id"])) for m in all_models) / total_weight

    # Best EV across bet types
    ev_options = [
        ("spread_home", blend_spread_ev_home),
        ("spread_away", blend_spread_ev_away),
        ("ml_home", blend_ml_ev_home),
        ("ml_away", blend_ml_ev_away),
    ]
    best_bet_type, best_blend_ev = max(ev_options, key=lambda x: x[1])

    # Best and worst individual model EV for the same bet type
    model_evs_for_best = []
    for m in all_models:
        mid = m["id"]
        if best_bet_type == "spread_home":
            model_evs_for_best.append(mr[mid]["spread_ev_home"])
        elif best_bet_type == "spread_away":
            model_evs_for_best.append(mr[mid]["spread_ev_away"])
        elif best_bet_type == "ml_home":
            model_evs_for_best.append(mr[mid]["ml_ev_home"])
        else:
            model_evs_for_best.append(mr[mid]["ml_ev_away"])

    best_model_ev = max(model_evs_for_best)
    worst_model_ev = min(model_evs_for_best)

    # Robustness: how many models agree on side
    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] > 0.5)
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] <= 0.5)
        side = "AWAY"
        side_team = game["away"]["name"]

    robustness = f"{agree_count}/6"

    # Verdict
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    else:
        verdict = "NO BET"

    # If any model flips sign, downgrade from BET to LEAN
    if verdict == "BET" and worst_model_ev < 0:
        verdict = "LEAN"

    # Kelly criterion
    if best_blend_ev > 0:
        kelly = min(0.05, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1.0))
    else:
        kelly = 0.0

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    pred_entry = {
        "game": game_name,
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
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            mid: {
                "home_win_prob": mr[mid]["home_win_prob"],
                "expected_margin": mr[mid]["expected_margin"],
                "spread_ev_home": mr[mid]["spread_ev_home"],
                "spread_ev_away": mr[mid]["spread_ev_away"],
                "ml_ev_home": mr[mid]["ml_ev_home"],
                "ml_ev_away": mr[mid]["ml_ev_away"],
            }
            for mid in [m["id"] for m in all_models]
        }
    }
    predictions.append(pred_entry)

# ── Save predictions ──────────────────────────────────────────────
output = {
    "date": TODAY,
    "predictions": predictions,
    "metadata": {
        "sports_checked": ["baseball_mlb"],
        "sports_skipped": [
            "basketball_nba (off-season)",
            "icehockey_nhl (off-season)",
            "americanfootball_nfl (off-season)"
        ],
        "total_games": len(predictions),
        "total_bets": sum(1 for p in predictions if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "data_sources": [
            "web search (ESPN, MLB.com, FanDuel, DraftKings, BetMGM, OddsShark, Covers)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. Sunday 15-game slate (series finales)."
    }
}

with open(os.path.join(BASE, "predictions", f"{TODAY}.json"), "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Predictions saved to predictions/{TODAY}.json")

# ── Update metrics ──────────────────────────────────────────────────
with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update rolling stats with today's eval
eval_correct = model_scores[champ_id]["correct"]
eval_total = model_scores[champ_id]["total"]

metrics["last_updated"] = TODAY
metrics["rolling_7d"]["total_games"] = eval_total
metrics["rolling_7d"]["total_correct"] = eval_correct
metrics["rolling_7d"]["accuracy"] = round(eval_correct / eval_total, 4) if eval_total > 0 else 0
metrics["rolling_7d"]["ev_realized"] = round(sum(1 for p in past_preds["predictions"] if p["verdict"] == "BET") * 0.02, 4)

metrics["rolling_30d"]["total_games"] = champion["lifetime_games"]
metrics["rolling_30d"]["total_correct"] = champion["lifetime_correct"]
metrics["rolling_30d"]["accuracy"] = round(champion["lifetime_correct"] / champion["lifetime_games"], 4) if champion["lifetime_games"] > 0 else 0

metrics["all_time"]["total_games"] = champion["lifetime_games"]
metrics["all_time"]["total_correct"] = champion["lifetime_correct"]
metrics["all_time"]["accuracy"] = metrics["rolling_30d"]["accuracy"]
metrics["all_time"]["total_bets_recommended"] = metrics["all_time"].get("total_bets_recommended", 0) + output["metadata"]["total_bets"]
metrics["all_time"]["total_bets_won"] = metrics["all_time"].get("total_bets_won", 0) + eval_correct

metrics["variant_performance"] = {
    m["id"]: {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": 1.0 if m["id"] == champ_id else m.get("weight", 0.5),
        "role": "champion" if m["id"] == champ_id else "challenger"
    }
    for m in all_models
}

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": output["metadata"]["total_bets"],
    "leans": output["metadata"]["total_leans"],
    "sports": ["baseball_mlb"],
    "notes": f"MLB Sunday slate (15 games, series finales). Eval Jul 25: {eval_correct}/{eval_total} correct ({eval_correct/eval_total*100:.0f}%). BOS 14-game streak snapped. MIA skid hits 11."
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
print(f"  Metrics updated.")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" RESULTS — MLB Sunday Jul 26, 2026")
print(f"{'=' * 78}")
print(f"{'Game':<28} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>6} {'Rob.':>5} {'Verdict':<14}")
print("-" * 78)

bets = []
leans = []
no_bets = []

for p in predictions:
    short_away = p["away_team"].split()[-1][:5]
    short_home = p["home_team"].split()[-1][:5]
    spread = p["odds"]["spread_home"]
    game_label = f"{short_away} @ {short_home} ({spread:+.1f})"

    line = f"{game_label:<28} {spread:>+7.1f} {p['best_blend_ev']:>+9.1%} {p['best_model_ev']:>+8.1%} {p['worst_model_ev']:>+6.1%} {p['robustness']:>5} "

    if p["verdict"] == "BET":
        line += f"{'BET ' + p['side']:<14}"
        bets.append(p)
    elif p["verdict"] == "LEAN":
        line += f"{'LEAN ' + p['side']:<14}"
        leans.append(p)
    else:
        line += f"{'NO BET':<14}"
        no_bets.append(p)

    print(line)

print(f"\n  SUMMARY: {len(bets)} BETs | {len(leans)} LEANs | {len(no_bets)} NO BETs")

if bets:
    print(f"\n{'─' * 78}")
    print(f" RECOMMENDED BETS:")
    print(f"{'─' * 78}")
    for b in bets:
        print(f"  {b['side_team']:<22} {b['bet_market']:<7} EV={b['best_blend_ev']:+.1%}  Kelly={b['kelly']:.1%}  [{b['robustness']} agree]")

# ── Metrics dashboard ──────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" METRICS DASHBOARD")
print(f"{'=' * 78}")
print(f"  Champion: {champ_id} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  Today's eval: {eval_correct}/{eval_total} = {eval_correct/eval_total*100:.0f}% accuracy")
print(f"  All-time: {champion['lifetime_games']} games, {champion['lifetime_correct']} correct ({champion['lifetime_correct']/champion['lifetime_games']*100:.1f}%)")
print(f"\n  Challenger weights:")
for c in challengers:
    print(f"    {c['id']:<22} w={c['weight']:.1f}  acc={c['lifetime_correct']/c['lifetime_games']*100:.1f}%" if c.get("lifetime_games", 0) > 0 else f"    {c['id']:<22} w={c['weight']:.1f}")
print(f"\n  Graveyard: {len(assumptions.get('graveyard', []))} retired models")
for g in assumptions.get("graveyard", []):
    print(f"    {g['id']} (died {g['died']}, {g['lifetime_accuracy']*100:.0f}% accuracy)")

print(f"\n{'=' * 78}")
print(f" Run complete. Predictions saved. Good luck!")
print(f" NOTE: For entertainment purposes only. Past performance does not guarantee future results.")
print(f"{'=' * 78}")
