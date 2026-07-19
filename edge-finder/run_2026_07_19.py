#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-19.
Phase 1: Eval July 18 predictions (14 MLB games; LAD@NYY postponed).
Phase 2-5: Simulate tonight's 16 MLB games (incl LAD@NYY DH), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-19"
EVAL_DATE = "2026-07-18"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 18 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-18 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 18, 2026 (sourced via ESPN, MLB.com, web search)
# LAD @ NYY postponed (rain); makeup DH on July 19.
# 14 games completed. Red Sox rally 7-6 over Rays for 12th straight. Rangers 7-6 in ATL.
actual_results = {
    "Minnesota Twins @ Chicago Cubs": {"winner": "home", "home_score": 6, "away_score": 2},
    "Chicago White Sox @ Toronto Blue Jays": {"winner": "home", "home_score": 1, "away_score": 0},
    "Cincinnati Reds @ Colorado Rockies": {"winner": "home", "home_score": 10, "away_score": 3},
    "New York Mets @ Philadelphia Phillies": {"winner": "home", "home_score": 6, "away_score": 1},
    "Baltimore Orioles @ Houston Astros": {"winner": "away", "home_score": 2, "away_score": 4},
    "Pittsburgh Pirates @ Cleveland Guardians": {"winner": "away", "home_score": 1, "away_score": 7},
    "San Diego Padres @ Kansas City Royals": {"winner": "home", "home_score": 6, "away_score": 1},
    "Tampa Bay Rays @ Boston Red Sox": {"winner": "home", "home_score": 7, "away_score": 6},
    "Texas Rangers @ Atlanta Braves": {"winner": "away", "home_score": 6, "away_score": 7},
    "Miami Marlins @ Milwaukee Brewers": {"winner": "home", "home_score": 8, "away_score": 6},
    "St. Louis Cardinals @ Arizona Diamondbacks": {"winner": "home", "home_score": 5, "away_score": 3},
    "San Francisco Giants @ Seattle Mariners": {"winner": "home", "home_score": 4, "away_score": 3},
    "Washington Nationals @ Oakland Athletics": {"winner": "home", "home_score": 15, "away_score": 1},
    "Detroit Tigers @ Los Angeles Angels": {"winner": "away", "home_score": 0, "away_score": 7},
    # "Los Angeles Dodgers @ New York Yankees": POSTPONED
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
    if c_lifetime_acc - champ_lifetime_acc >= 0.05:
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
    days_alive = (date(2026, 7, 19) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 19, 2026)
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
# Sunday July 19, 2026 — MLB only (NBA/NHL/NFL off-season)
# 16 games including LAD@NYY doubleheader (makeup from Jul 18 postponement).
# Odds sourced from FanDuel, DraftKings, BetMGM, ESPN, Covers, OddsShark.
# Records through July 18. Stats updated from Jul 18 scores.

games_raw = [
    # 1. CWS White Sox @ TOR Blue Jays — 12:15 PM ET
    # CWS 51-46, TOR 46-51. TOR won 1-0 yesterday (Bieber gem). CWS 4-game win streak snapped.
    # Burke (7-4, 3.20) vs Yesavage (4-5, 3.78).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.475,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -114,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 2. LAD Dodgers @ NYY Yankees — 12:35 PM ET (Game 1 of DH, makeup from Jul 18)
    # LAD 62-36 (best in MLB), NYY 47-52. Dodgers road favorite.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.4,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.660,
            "away_record_pct": 0.620,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 3. TB Rays @ BOS Red Sox — 1:35 PM ET
    # TB 57-40, BOS 48-49 (12-game win streak). BOS rallied 7-6 yesterday.
    # McClanahan (8-6, 3.07) for TB. BOS hot.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.590,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. NYM Mets @ PHI Phillies — 1:35 PM ET
    # NYM 41-58, PHI 55-44. Phillies won 6-1 yesterday (Schwarber HR #33).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -135,
            "ml_away": 115,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. TEX Rangers @ ATL Braves — 1:35 PM ET
    # TEX 50-48, ATL 56-41. Rangers upset 7-6 yesterday. Series rubber match.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.8,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.9,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 6. PIT Pirates @ CLE Guardians — 1:40 PM ET
    # PIT 51-47 (won 7-1 yesterday, 3-game streak), CLE 47-43.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.9,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.1,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 110,
            "total": 7.0,
            "book": "fanduel"
        }
    },

    # 7. BAL Orioles @ HOU Astros — 2:10 PM ET
    # BAL 49-51 (won 4-2 in 11 yesterday), HOU 47-53. BAL slight favorite.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": -102,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 8. SD Padres @ KC Royals — 2:10 PM ET
    # SD 43-45, KC 37-53. KC upset 6-1 yesterday. KC home again.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.7,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.430,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -131,
            "ml_away": 110,
            "total": 10.0,
            "book": "fanduel"
        }
    },

    # 9. MIA Marlins @ MIL Brewers — 2:10 PM ET
    # MIA 28-70, MIL 62-37 (1st NL Central). Brewers won 8-6 yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 3.6,
            "season_opp_ppg": 5.0,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.300,
            "away_record_pct": 0.270,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -135,
            "ml_away": 110,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 10. MIN Twins @ CHC Cubs — 2:20 PM ET
    # MIN 49-50, CHC 55-43. Cubs won 6-2 yesterday. CHC clear favorite.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -169,
            "ml_away": 139,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 11. CIN Reds @ COL Rockies — 3:10 PM ET (Coors Field)
    # CIN 41-48, COL 37-54. Rockies blew up for 10 runs yesterday at Coors.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.6,
            "season_opp_ppg": 5.4,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 5.5,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 125,
            "ml_away": -155,
            "total": 12.5,
            "book": "fanduel"
        }
    },

    # 12. WSH Nationals @ OAK Athletics — 4:05 PM ET
    # WSH 45-52, OAK 27-69. WSH heavy favorite. OAK routed WSH 15-1 yesterday though.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Oakland Athletics",
            "season_ppg": 3.8,
            "season_opp_ppg": 5.3,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 5.8,
            "season_pace": 1.0,
            "home_record_pct": 0.330,
            "away_record_pct": 0.240,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 5.3,
            "season_opp_ppg": 4.8,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -140,
            "total": 11.0,
            "book": "fanduel"
        }
    },

    # 13. DET Tigers @ LAA Angels — 4:07 PM ET
    # DET 53-42, LAA 36-62. Tigers won 7-0 yesterday. DET heavy road favorite.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.3,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 135,
            "ml_away": -160,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 14. SF Giants @ SEA Mariners — 4:10 PM ET
    # SF 40-55, SEA 47-52. Mariners walked off 4-3 in 10 yesterday.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Seattle Mariners",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -178,
            "ml_away": 150,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 15. STL Cardinals @ ARI Diamondbacks — 4:10 PM ET
    # STL 42-56, ARI 49-46. D-backs won 5-3 yesterday. ARI moderate home favorite.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 104,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 16. LAD Dodgers @ NYY Yankees — 7:20 PM ET (Game 2 / SNB)
    # Yamamoto (9-6, 2.85) vs Schlittler (9-5, 2.05). Marquee pitching matchup.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.4,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.660,
            "away_record_pct": 0.620,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -130,
            "total": 9.0,
            "book": "fanduel"
        }
    },
]

# ── Run simulations for all models ──────────────────────────────────────

batch = []
for game in games_raw:
    for model in all_models:
        sim_input = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        }
        batch.append(sim_input)

print(f"\nSimulating {len(games_raw)} games × {len(all_models)} models = {len(batch)} sims...")
results = run_batch(batch)
print("Simulations complete.")

# ── Organize results by game ─────────────────────────────────────────

games_per_model = len(all_models)
predictions = []

for i, game in enumerate(games_raw):
    game_results = {}
    for j, model in enumerate(all_models):
        idx = i * games_per_model + j
        r = results[idx]
        game_results[model["id"]] = {
            "home_win_prob": r["home_win_prob"],
            "expected_margin": r["expected_margin"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
        }

    model_weights = {champion["id"]: 1.0}
    for c in challengers:
        model_weights[c["id"]] = c["weight"]

    total_w = sum(model_weights.values())
    blend_hp = sum(game_results[mid]["home_win_prob"] * model_weights[mid] for mid in model_weights) / total_w
    blend_ap = 1.0 - blend_hp
    blend_margin = sum(game_results[mid]["expected_margin"] * model_weights[mid] for mid in model_weights) / total_w

    ev_types = ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]
    blend_evs = {}
    for et in ev_types:
        blend_evs[et] = sum(game_results[mid][et] * model_weights[mid] for mid in model_weights) / total_w

    best_bet_type = max(blend_evs, key=blend_evs.get)
    best_blend_ev = blend_evs[best_bet_type]
    best_model_ev = max(game_results[mid][best_bet_type] for mid in model_weights)
    worst_model_ev = min(game_results[mid][best_bet_type] for mid in model_weights)

    agree_home = sum(1 for mid in model_weights if game_results[mid]["home_win_prob"] > 0.5)
    agree_away = len(model_weights) - agree_home
    agree_count = max(agree_home, agree_away)
    robustness = f"{agree_count}/{len(model_weights)}"

    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]
    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    any_ev_negative = worst_model_ev < 0
    if best_blend_ev > 0.03 and agree_count >= 4 and not any_ev_negative:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and any_ev_negative:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly_fraction = max(0, min(0.05, best_blend_ev / (best_model_ev if best_model_ev > 0 else 1)))

    pred = {
        "game": f"{game['away']['name']} @ {game['home']['name']}",
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_hp, 4),
        "blend_away_wp": round(blend_ap, 4),
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
        "kelly": round(kelly_fraction, 4),
        "model_results": game_results,
    }
    predictions.append(pred)

# ── Save predictions ─────────────────────────────────────────────────

pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {
    "date": TODAY,
    "predictions": predictions,
    "metadata": {
        "sports_checked": ["baseball_mlb"],
        "sports_skipped": [
            "basketball_nba (off-season)",
            "icehockey_nhl (off-season)",
            "americanfootball_nfl (off-season)",
        ],
        "total_games": len(predictions),
        "total_bets": sum(1 for p in predictions if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "data_sources": [
            "web search (ESPN, MLB.com, FanDuel, DraftKings, BetMGM, OddsShark, Covers)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. LAD@NYY DH makeup from Jul 18 postponement.",
    },
}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\nPredictions saved to {pred_file}")

# ── Display results ──────────────────────────────────────────────────

print(f"\n{'━' * 78}")
print(f"  MLB — Sunday Jul 19, 2026")
print(f"{'━' * 78}")
print(f"{'Game':<28} {'Spread':>6} {'Blend':>7} {'Best':>6} {'Worst':>6} {'Rob.':>5} {'Verdict':<14}")
print(f"{'':28} {'':>6} {'EV':>7} {'EV':>6} {'EV':>6} {'':>5} {'':14}")
print(f"{'─' * 78}")

bets = []
for p in predictions:
    spread_str = f"{p['odds']['spread_home']:+.1f}"
    blend_ev_str = f"{p['best_blend_ev']:+.1%}"
    best_ev_str = f"{p['best_model_ev']:+.1%}"
    worst_ev_str = f"{p['worst_model_ev']:+.1%}"

    if p["verdict"] == "BET":
        verdict_str = f"✅ BET {p['side']}"
        bets.append(p)
    elif p["verdict"] == "LEAN":
        verdict_str = f"⚠️  LEAN {p['side']}"
    else:
        verdict_str = "❌ NO BET"

    away_abbr = p["away_team"].split()[-1][:3].upper()
    home_abbr = p["home_team"].split()[-1][:3].upper()
    game_str = f"{away_abbr} @ {home_abbr} ({spread_str})"

    print(f"{game_str:<28} {spread_str:>6} {blend_ev_str:>7} {best_ev_str:>6} {worst_ev_str:>6} {p['robustness']:>5} {verdict_str:<14}")

print(f"{'─' * 78}")
print(f"  Total: {len(predictions)} games | {sum(1 for p in predictions if p['verdict'] == 'BET')} BETs | {sum(1 for p in predictions if p['verdict'] == 'LEAN')} LEANs | {sum(1 for p in predictions if p['verdict'] == 'NO BET')} NO BETs")

if bets:
    print(f"\n{'━' * 78}")
    print("  BET Details")
    print(f"{'━' * 78}")
    for b in bets:
        print(f"\n  {b['game']}")
        print(f"  Side: {b['side_team']} ({b['bet_market']})")
        print(f"  Blended EV: {b['best_blend_ev']:+.1%} | Kelly: {b['kelly']:.1%} of bankroll")
        print(f"  Book: {b['odds']['book']} | Spread: {b['odds']['spread_home']:+.1f} | ML: {b['odds']['ml_home']}/{b['odds']['ml_away']}")
        agree_mids = [mid for mid, mr in b["model_results"].items() if (mr["home_win_prob"] > 0.5) == (b["side"] == "HOME")]
        disagree_mids = [mid for mid in b["model_results"] if mid not in agree_mids]
        print(f"  Agree ({len(agree_mids)}): {', '.join(agree_mids)}")
        if disagree_mids:
            print(f"  Disagree ({len(disagree_mids)}): {', '.join(disagree_mids)}")

# ── Update metrics ───────────────────────────────────────────────────

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

eval_correct = model_scores[champ_id]["correct"]
eval_total = model_scores[champ_id]["total"]

metrics["last_updated"] = TODAY

metrics["rolling_7d"]["total_games"] = eval_total
metrics["rolling_7d"]["total_correct"] = eval_correct
metrics["rolling_7d"]["accuracy"] = round(eval_correct / eval_total, 4) if eval_total > 0 else 0

metrics["all_time"]["total_games"] = champion["lifetime_games"]
metrics["all_time"]["total_correct"] = champion["lifetime_correct"]
metrics["all_time"]["accuracy"] = round(champion["lifetime_correct"] / champion["lifetime_games"], 4) if champion["lifetime_games"] > 0 else 0

metrics["rolling_30d"]["total_games"] = champion["lifetime_games"]
metrics["rolling_30d"]["total_correct"] = champion["lifetime_correct"]
metrics["rolling_30d"]["accuracy"] = round(champion["lifetime_correct"] / champion["lifetime_games"], 4) if champion["lifetime_games"] > 0 else 0

bet_wins = 0
bet_total = 0
for pred in past_preds["predictions"]:
    gk = pred["game"]
    if gk not in actual_results:
        continue
    actual = actual_results[gk]
    actual_winner = actual["winner"]
    margin = actual["home_score"] - actual["away_score"]

    if pred["verdict"] in ("BET", "LEAN"):
        bet_total += 1
        spread = pred["odds"]["spread_home"]
        bt = pred["best_bet_type"]
        if bt == "spread_home":
            if (margin + spread) > 0:
                bet_wins += 1
        elif bt == "spread_away":
            if (-margin - spread) > 0:
                bet_wins += 1
        elif bt == "ml_home":
            if actual_winner == "home":
                bet_wins += 1
        else:
            if actual_winner == "away":
                bet_wins += 1

metrics["all_time"]["total_bets_recommended"] = metrics["all_time"].get("total_bets_recommended", 0) + bet_total
metrics["all_time"]["total_bets_won"] = metrics["all_time"].get("total_bets_won", 0) + bet_wins

metrics["variant_performance"] = {}
for model in all_models:
    mid = model["id"]
    role = "champion" if mid == champ_id else "challenger"
    metrics["variant_performance"][mid] = {
        "lifetime_games": model.get("lifetime_games", 0),
        "lifetime_correct": model.get("lifetime_correct", 0),
        "weight": model.get("weight", 0.5),
        "role": role,
    }

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": sum(1 for p in predictions if p["verdict"] == "BET"),
    "leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
    "sports": ["baseball_mlb"],
    "notes": f"MLB Sunday slate (16 games incl LAD@NYY DH). Eval Jul 18: {eval_correct}/{eval_total} correct ({eval_correct/eval_total*100:.0f}%). Rough day — all models agreed on all picks, only 5 correct. BOS 12-game win streak. Rangers upset Braves 7-6.",
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# ── Print summary ────────────────────────────────────────────────────

print(f"\n{'━' * 78}")
print("  📊 Edge-Finder Metrics")
print(f"{'━' * 78}")
print(f"  Champion: {champ_id} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"  7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | {eval_correct}/{eval_total} games")
print(f"  30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | {metrics['rolling_30d']['total_games']} games")
print(f"  All-time: {metrics['all_time']['accuracy']:.0%} accuracy | {metrics['all_time']['total_games']} games")
print(f"  All-time bets: {metrics['all_time']['total_bets_won']}/{metrics['all_time']['total_bets_recommended']} won")
print()
challenger_weights = ", ".join(f"{c['id']}={c['weight']}" for c in challengers)
print(f"  Challenger weights: {challenger_weights}")
if assumptions.get("graveyard"):
    graveyard_str = ", ".join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions["graveyard"])
    print(f"  Graveyard: {graveyard_str}")

print(f"\n{'━' * 78}")
print("  ⚠️  Disclaimer: For entertainment and analysis purposes only.")
print("  Past performance does not guarantee future results.")
print(f"{'━' * 78}")
