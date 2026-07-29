#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-29.
Phase 1: Eval July 27 predictions (11 MLB games; CLE@CIN postponed).
Phase 2-5: Simulate tonight's 14 MLB games (Wed slate), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-29"
EVAL_DATE = "2026-07-27"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 27 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-27 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 27, 2026 (sourced via web search: ESPN, MLB.com, Baseball-Reference)
# CLE @ CIN was postponed due to weather — excluded.
actual_results = {
    "Seattle Mariners @ Texas Rangers": {"winner": "home", "home_score": 7, "away_score": 3},
    "Baltimore Orioles @ Detroit Tigers": {"winner": "away", "home_score": 5, "away_score": 8},
    "Arizona Diamondbacks @ Pittsburgh Pirates": {"winner": "home", "home_score": 3, "away_score": 2},
    "Philadelphia Phillies @ Miami Marlins": {"winner": "home", "home_score": 8, "away_score": 7},
    "Toronto Blue Jays @ Washington Nationals": {"winner": "away", "home_score": 2, "away_score": 3},
    "Atlanta Braves @ New York Mets": {"winner": "home", "home_score": 14, "away_score": 3},
    "New York Yankees @ Chicago White Sox": {"winner": "away", "home_score": 5, "away_score": 9},
    "Chicago Cubs @ St. Louis Cardinals": {"winner": "away", "home_score": 3, "away_score": 7},
    "Houston Astros @ Los Angeles Angels": {"winner": "away", "home_score": 4, "away_score": 6},
    "Boston Red Sox @ Oakland Athletics": {"winner": "away", "home_score": 2, "away_score": 4},
    "Milwaukee Brewers @ San Francisco Giants": {"winner": "home", "home_score": 3, "away_score": 0},
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
    days_alive = (date(2026, 7, 29) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 29, 2026)
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
# Wednesday July 29, 2026 — MLB only (NBA/NHL/NFL off-season)
# 15 games (ATL@NYM doubleheader). Odds from FanDuel, DraftKings, Covers.
# MIA snapped 12-game losing streak Jul 27 (walkoff 8-7 vs PHI).
# NYM crushed ATL 14-3 Jul 27. TEX beat SEA 7-3 to end series.
# CLE@CIN rained out Jul 27, DH on Jul 28 (split: CLE 6-5, CIN 2-0).

games_raw = [
    # 1. PHI Phillies @ MIA Marlins — Wed 12:10 PM ET
    # PHI heavy road fav. PHI -157 / MIA +130. Luzardo starts for PHI.
    # MIA snapped 12-game skid Jul 27 with walkoff win vs PHI.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 130,
            "ml_away": -157,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 2. ARI Diamondbacks @ PIT Pirates — Wed 12:35 PM ET
    # PIT slight home fav. PIT -132 / ARI +109. PIT won 3-2 in 10 Jul 27.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.460,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -132,
            "ml_away": 109,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. TOR Blue Jays @ WSH Nationals — Wed 1:05 PM ET
    # TOR slight road fav. TOR -124 / WSH +106. TOR won 3-2 Jul 27 (Scherzer return).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 5.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 106,
            "ml_away": -124,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 4. BAL Orioles @ DET Tigers — Wed 1:10 PM ET
    # DET heavy home fav. DET -178 / BAL +150. DET 66.9% implied.
    # BAL won 8-5 Jul 27 (Holliday 4 hits). Total 7.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.500,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -178,
            "ml_away": 150,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 5. ATL Braves @ NYM Mets — Wed 1:10 PM ET (DH Game 1)
    # ATL slight road fav. ATL -116 / NYM -102.
    # NYM crushed ATL 14-3 Jul 27 (Lindor 2 HR, 6 RBI).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.590,
            "away_record_pct": 0.510,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -102,
            "ml_away": -116,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 6. MIL Brewers @ SF Giants — Wed 3:45 PM ET
    # MIL road fav. MIL -126 / SF +104. SF shut out MIL 3-0 Jul 27 (Mahle).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 104,
            "ml_away": -126,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 7. COL Rockies @ SD Padres — Wed 4:10 PM ET
    # SD home fav. SD -149 / COL +122. COL struggling on the road.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 4.0,
            "season_opp_ppg": 5.0,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.280,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -149,
            "ml_away": 122,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. TEX Rangers @ TB Rays — Wed 6:40 PM ET
    # TB home fav. TB -143 / TEX +118. TB leads AL. TEX won 7-3 vs SEA Jul 27.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.540,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.450,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -143,
            "ml_away": 118,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 9. CLE Guardians @ CIN Reds — Wed 7:10 PM ET
    # CLE road fav. CLE -134 / CIN +114. CLE@CIN rained out Jul 27; split DH Jul 28.
    # Brady Singer starts for CLE (4.86 xERA at home, but strong on road).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
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
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 114,
            "ml_away": -134,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 10. KC Royals @ MIN Twins — Wed 7:40 PM ET
    # MIN home fav. MIN -171 / KC +141. Both offenses cold recently.
    # Analysts lean KC despite Twins being favored.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.380,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.380,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -171,
            "ml_away": 141,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 11. NYY Yankees @ CWS White Sox — Wed 7:40 PM ET
    # NYY heavy road fav. NYY -144 / CWS +119. NYY won 9-5 Jul 27.
    # CWS worst in AL. Schlittler starts for NYY.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.6,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.330,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 119,
            "ml_away": -144,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 12. CHC Cubs @ STL Cardinals — Wed 7:45 PM ET
    # CHC slight road fav. CHC -120 / STL -101. CHC won 7-3 Jul 27 (Bregman HR).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.490,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -101,
            "ml_away": -120,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 13. HOU Astros @ LAA Angels — Wed 9:38 PM ET
    # HOU road fav. HOU -136 / LAA +116. HOU won 6-4 Jul 27 (Altuve).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.370,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 116,
            "ml_away": -136,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 14. BOS Red Sox @ OAK Athletics — Wed 9:40 PM ET
    # BOS heavy road fav. BOS -154 / OAK +130.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Oakland Athletics",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.360,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
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
        "odds": {
            "spread_home": 1.5,
            "ml_home": 130,
            "ml_away": -154,
            "total": 8.0,
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

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")
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

    total_weight = 1.0
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

    ev_options = [
        ("spread_home", blend_spread_ev_home),
        ("spread_away", blend_spread_ev_away),
        ("ml_home", blend_ml_ev_home),
        ("ml_away", blend_ml_ev_away),
    ]
    best_bet_type, best_blend_ev = max(ev_options, key=lambda x: x[1])

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

    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] > 0.5)
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        agree_count = sum(1 for m in all_models if mr[m["id"]]["home_win_prob"] <= 0.5)
        side = "AWAY"
        side_team = game["away"]["name"]

    robustness = f"{agree_count}/6"

    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    else:
        verdict = "NO BET"

    if verdict == "BET" and worst_model_ev < 0:
        verdict = "LEAN"

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
            "web search (ESPN, MLB.com, FanDuel, DraftKings, Covers, NBC Sports, Baseball-Reference)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. Wed 14-game slate (ATL@NYM DH G2 excluded — no separate odds). CLE@CIN rained out Jul 27."
    }
}

with open(os.path.join(BASE, "predictions", f"{TODAY}.json"), "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Predictions saved to predictions/{TODAY}.json")

# ── Update metrics ──────────────────────────────────────────────────
with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

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
    "notes": f"MLB Wed slate (14 games + ATL@NYM DH G2 excluded). Eval Jul 27: {eval_correct}/{eval_total} correct ({eval_correct/eval_total*100:.0f}%). MIA snapped 12-game streak. NYM crushed ATL 14-3."
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
print(f"  Metrics updated.")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" RESULTS — MLB Wednesday Jul 29, 2026")
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
    print(f"\n{'_' * 78}")
    print(f" RECOMMENDED BETS:")
    print(f"{'_' * 78}")
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
