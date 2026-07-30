#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-30.
Phase 1: Eval July 29 predictions (14 MLB games).
Phase 2-5: Simulate tonight's 10 MLB games (Thu slate), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-30"
EVAL_DATE = "2026-07-29"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 29 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-29 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 29, 2026 (sourced via web search: ESPN, MLB.com, CBS Sports)
actual_results = {
    "Philadelphia Phillies @ Miami Marlins": {"winner": "home", "home_score": 8, "away_score": 6},
    "Arizona Diamondbacks @ Pittsburgh Pirates": {"winner": "away", "home_score": 0, "away_score": 3},
    "Toronto Blue Jays @ Washington Nationals": {"winner": "away", "home_score": 2, "away_score": 5},
    "Baltimore Orioles @ Detroit Tigers": {"winner": "away", "home_score": 9, "away_score": 10},
    "Atlanta Braves @ New York Mets": {"winner": "home", "home_score": 3, "away_score": 2},
    "Milwaukee Brewers @ San Francisco Giants": {"winner": "home", "home_score": 16, "away_score": 3},
    "Colorado Rockies @ San Diego Padres": {"winner": "home", "home_score": 3, "away_score": 1},
    "Texas Rangers @ Tampa Bay Rays": {"winner": "home", "home_score": 3, "away_score": 0},
    "Cleveland Guardians @ Cincinnati Reds": {"winner": "away", "home_score": 1, "away_score": 6},
    "Kansas City Royals @ Minnesota Twins": {"winner": "away", "home_score": 0, "away_score": 4},
    "New York Yankees @ Chicago White Sox": {"winner": "home", "home_score": 6, "away_score": 5},
    "Chicago Cubs @ St. Louis Cardinals": {"winner": "home", "home_score": 3, "away_score": 2},
    "Houston Astros @ Los Angeles Angels": {"winner": "away", "home_score": 4, "away_score": 7},
    "Boston Red Sox @ Oakland Athletics": {"winner": "away", "home_score": 2, "away_score": 4},
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
    days_alive = (date(2026, 7, 30) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 30, 2026)
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
# Thursday July 30, 2026 — MLB only (NBA/NHL/NFL off-season)
# 10-game Thursday slate. Odds from FanDuel, DraftKings, CBS Sports, Covers.
# BAL staged epic 10-9 comeback from 7-0 down in 12 innings Jul 29.
# CWS upset NYY 6-5. SF blasted MIL 16-3. KC shut out MIN 4-0.

games_raw = [
    # 1. TEX Rangers @ TB Rays — Thu 12:10 PM ET
    # TB solid home fav. TB -163 / TEX +122. Rays 63-44 lead AL East.
    # TEX 55-53. TB shut out TEX 3-0 Jul 29.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -163,
            "ml_away": 122,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 2. KC Royals @ MIN Twins — Thu 1:40 PM ET
    # MIN home fav. MIN -143 / KC +120. MIN 54-55, KC 46-63.
    # Pitchers: Ober (7-3) vs Cameron (5-8). KC shut out MIN 4-0 Jul 29.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.6,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.420,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -143,
            "ml_away": 120,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. NYY Yankees @ CWS White Sox — Thu 2:10 PM ET
    # Close to pick'em. NYY -130 / CWS +108. Series finale.
    # CWS pulled upset 6-5 Jul 29 vs NYY. CWS 28-80 but scrappy at home.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.5,
            "season_opp_ppg": 5.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.310,
            "away_record_pct": 0.210,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.8,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -130,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 4. CHC Cubs @ STL Cardinals — Thu 2:15 PM ET
    # STL slight home fav. STL -120 / CHC +102. Series finale.
    # STL won 3-2 Jul 29. STL 50-58, CHC 57-51.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.440,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.510,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -120,
            "ml_away": 102,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. MIA Marlins @ NYM Mets — Thu 7:10 PM ET
    # NYM home fav. NYM -131 / MIA +109. Pitchers: Eury Perez vs Nolan McLean.
    # MIA (5-8, 3.56 ERA) vs NYM (7-7, 3.32 ERA).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.9,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -131,
            "ml_away": 109,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 6. PIT Pirates @ CIN Reds — Thu 7:10 PM ET
    # PIT slight road fav. PIT -115 / CIN -105. O/U 9.5 (high).
    # CLE blew out CIN 6-1 Jul 29. CIN struggling. PIT 54-54.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 7. WSH Nationals @ ATL Braves — Thu 7:15 PM ET
    # ATL home fav. ATL -156 / WSH +129. Pitchers: WSH (2-4, 5.23) vs ATL (6-4, 3.79).
    # ATL lost 2 of 3 to NYM. WSH 54-54.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 5.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 129,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. SF Giants @ SD Padres — Thu 9:40 PM ET
    # SD home fav. SD -161 / SF +133. SD 60-48, SF 49-59.
    # SF blew out MIL 16-3 Jul 29 (hot bats). SD beat COL 3-1.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Francisco Giants",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -161,
            "ml_away": 133,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 9. BOS Red Sox @ OAK Athletics — Thu 9:40 PM ET
    # BOS heavy road fav. BOS -185 / OAK +152. BOS 60-48, OAK 37-71.
    # BOS won 4-2 Jul 29. OAK one of worst teams in MLB.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Oakland Athletics",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.370,
            "away_record_pct": 0.310,
            "is_back_to_back": True,
            "key_injuries": 2
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.530,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 152,
            "ml_away": -185,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 10. SEA Mariners @ LAD Dodgers — Thu 10:10 PM ET
    # LAD home fav. LAD -160 / SEA +135. LAD 66-42, SEA 54-54.
    # LAD beat SEA 4-2 Jul 29. Dodgers rolling at home.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.0,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.560,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.0,
            "season_opp_ppg": 3.9,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -160,
            "ml_away": 135,
            "total": 8.0,
            "book": "fanduel"
        }
    },
]

# ── Build simulation batch ───────────────────────────────────────────
batch = []
for g in games_raw:
    for m in all_models:
        batch.append({
            "sport": g["sport"],
            "model_id": m["id"],
            "home": g["home"],
            "away": g["away"],
            "odds": g["odds"],
            "params": m["params"],
            "n_sims": 50000,
        })

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games × {len(all_models)} models)...")
results = run_batch(batch)

# ── Organize results by game ─────────────────────────────────────────
game_results = {}
idx = 0
for g in games_raw:
    game_key = f"{g['away']['name']} @ {g['home']['name']}"
    game_results[game_key] = {
        "game": game_key,
        "sport": g["sport"],
        "home_team": g["home"]["name"],
        "away_team": g["away"]["name"],
        "odds": g["odds"],
        "model_results": {},
    }
    for m in all_models:
        r = results[idx]
        game_results[game_key]["model_results"][m["id"]] = {
            "home_win_prob": r["home_win_prob"],
            "expected_margin": r["expected_margin"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
        }
        idx += 1

# ── Blended predictions + verdicts ───────────────────────────────────
predictions = []
for gk, gr in game_results.items():
    total_weight = 0
    blend_home_wp = 0
    blend_margin = 0
    evs_by_type = {"spread_home": 0, "spread_away": 0, "ml_home": 0, "ml_away": 0}
    model_evs = {}

    for m in all_models:
        mid = m["id"]
        w = m["weight"]
        mr = gr["model_results"][mid]
        blend_home_wp += w * mr["home_win_prob"]
        blend_margin += w * mr["expected_margin"]
        for etype in evs_by_type:
            evs_by_type[etype] += w * mr[f"{etype.replace('_', '_ev_').replace('ev_', '')}".replace("spread", "spread_ev").replace("ml", "ml_ev")]
        total_weight += w

        best_ev = max(mr["spread_ev_home"], mr["spread_ev_away"], mr["ml_ev_home"], mr["ml_ev_away"])
        model_evs[mid] = best_ev

    blend_home_wp /= total_weight
    blend_margin /= total_weight
    for etype in evs_by_type:
        evs_by_type[etype] /= total_weight

    # Fix EV computation — recalculate from model results directly
    ev_spread_home = sum(m["weight"] * gr["model_results"][m["id"]]["spread_ev_home"] for m in all_models) / total_weight
    ev_spread_away = sum(m["weight"] * gr["model_results"][m["id"]]["spread_ev_away"] for m in all_models) / total_weight
    ev_ml_home = sum(m["weight"] * gr["model_results"][m["id"]]["ml_ev_home"] for m in all_models) / total_weight
    ev_ml_away = sum(m["weight"] * gr["model_results"][m["id"]]["ml_ev_away"] for m in all_models) / total_weight

    blended_evs = {"spread_home": ev_spread_home, "spread_away": ev_spread_away,
                   "ml_home": ev_ml_home, "ml_away": ev_ml_away}
    best_bet_type = max(blended_evs, key=blended_evs.get)
    best_blend_ev = blended_evs[best_bet_type]

    best_model_ev = max(model_evs.values())
    worst_model_ev = min(model_evs.values())

    # Robustness — agreement on side
    home_votes = sum(1 for m in all_models if gr["model_results"][m["id"]]["home_win_prob"] > 0.5)
    away_votes = len(all_models) - home_votes
    agree_count = max(home_votes, away_votes)
    robustness = f"{agree_count}/{len(all_models)}"

    # Determine side
    if blend_home_wp > 0.5:
        side = "HOME"
        side_team = gr["home_team"]
    else:
        side = "AWAY"
        side_team = gr["away_team"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    # Verdict
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and worst_model_ev > 0:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = round(min(0.05, max(0, best_blend_ev / 3)), 4) if best_blend_ev > 0 else 0

    pred = {
        "game": gk,
        "sport": gr["sport"],
        "home_team": gr["home_team"],
        "away_team": gr["away_team"],
        "odds": gr["odds"],
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
        "kelly": kelly,
        "model_results": gr["model_results"],
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
            "americanfootball_nfl (off-season)"
        ],
        "total_games": len(predictions),
        "total_bets": sum(1 for p in predictions if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "data_sources": [
            "web search (ESPN, MLB.com, FanDuel, DraftKings, CBS Sports, Covers)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. Thu 10-game slate."
    }
}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\n  Predictions saved to {pred_file}")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'─' * 78}")
print(f"  MLB — Thursday Jul 30, 2026")
print(f"{'─' * 78}")

header = f"  {'Game':<28} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5} {'Verdict':<14}"
print(header)
print(f"  {'─'*28} {'─'*7} {'─'*9} {'─'*8} {'─'*7} {'─'*5} {'─'*14}")

bet_count = 0
lean_count = 0
for p in predictions:
    spread_str = f"{p['odds']['spread_home']:+.1f}"
    if p["verdict"] == "BET":
        icon = "BET"
        bet_count += 1
    elif p["verdict"] == "LEAN":
        icon = "LEAN"
        lean_count += 1
    else:
        icon = "NO BET"

    side_str = f"{icon} {p['side']}"

    # Shorten team names
    away_short = p["away_team"].split()[-1][:4].upper()
    home_short = p["home_team"].split()[-1][:4].upper()
    game_str = f"{away_short} @ {home_short}"

    print(f"  {game_str:<28} {spread_str:>7} {p['best_blend_ev']:>+8.1%} {p['best_model_ev']:>+7.1%} {p['worst_model_ev']:>+6.1%} {p['robustness']:>5} {side_str:<14}")

print(f"\n  Summary: {bet_count} BETs, {lean_count} LEANs, {len(predictions) - bet_count - lean_count} NO BETs")

# ── BET details ──────────────────────────────────────────────────────
for p in predictions:
    if p["verdict"] == "BET":
        print(f"\n  >>> BET: {p['game']}")
        print(f"      Side: {p['side_team']} ({p['bet_market']})")
        print(f"      Blended EV: {p['best_blend_ev']:+.1%} | Kelly: {p['kelly']:.2%} of bankroll")
        print(f"      Best book: {p['odds']['book']}")
        agreeing = [m["id"] for m in all_models
                    if (gr["model_results"][m["id"]]["home_win_prob"] > 0.5) == (p["side"] == "HOME")]
        print(f"      Models agreeing: {', '.join(m['id'] for m in all_models if (p['model_results'][m['id']]['home_win_prob'] > 0.5) == (p['side'] == 'HOME'))}")

# ── Update metrics ───────────────────────────────────────────────────
metrics_path = os.path.join(BASE, "metrics.json")
with open(metrics_path) as f:
    metrics = json.load(f)

# Update rolling stats with today's eval
prev_7d_games = metrics["rolling_7d"]["total_games"]
prev_7d_correct = metrics["rolling_7d"]["total_correct"]
eval_correct = model_scores[champ_id]["correct"]
eval_total = model_scores[champ_id]["total"]

new_7d_games = prev_7d_games + eval_total
new_7d_correct = prev_7d_correct + eval_correct

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(new_7d_correct / new_7d_games, 4) if new_7d_games > 0 else 0,
    "ev_realized": round(metrics["rolling_7d"].get("ev_realized", 0), 4),
    "total_games": new_7d_games,
    "total_correct": new_7d_correct,
}

prev_30d_games = metrics["rolling_30d"]["total_games"]
prev_30d_correct = metrics["rolling_30d"]["total_correct"]
metrics["rolling_30d"] = {
    "accuracy": round((prev_30d_correct + eval_correct) / (prev_30d_games + eval_total), 4) if (prev_30d_games + eval_total) > 0 else 0,
    "ev_realized": round(metrics["rolling_30d"].get("ev_realized", 0), 4),
    "total_games": prev_30d_games + eval_total,
    "total_correct": prev_30d_correct + eval_correct,
}

metrics["all_time"]["total_games"] = prev_30d_games + eval_total
metrics["all_time"]["total_correct"] = prev_30d_correct + eval_correct
metrics["all_time"]["accuracy"] = round(metrics["all_time"]["total_correct"] / metrics["all_time"]["total_games"], 4) if metrics["all_time"]["total_games"] > 0 else 0

# Update variant performance
for m in all_models:
    mid = m["id"]
    metrics["variant_performance"][mid] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": m["weight"],
        "role": "champion" if mid == champ_id else "challenger",
    }

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": bet_count,
    "leans": lean_count,
    "sports": ["baseball_mlb"],
    "notes": f"MLB Thu slate ({len(predictions)} games). Eval Jul 29: {eval_correct}/{eval_total} correct ({eval_correct/eval_total*100:.0f}%). BAL epic 10-9 comeback. CWS upset NYY 6-5."
}

with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Print metrics dashboard ──────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f"  Edge-Finder Metrics")
print(f"{'=' * 78}")
print(f"  Champion: {champ_id}")
r7 = metrics["rolling_7d"]
r30 = metrics["rolling_30d"]
print(f"  7-day:  {r7['accuracy']:.0%} accuracy | {r7['total_games']} games")
print(f"  30-day: {r30['accuracy']:.0%} accuracy | {r30['total_games']} games")
cw_str = ', '.join(f"{c['id']}={c['weight']}" for c in challengers)
print(f"\n  Challenger weights: {cw_str}")
if assumptions.get("graveyard"):
    print(f"  Graveyard: {', '.join(g['id'] for g in assumptions['graveyard'])}")

print(f"\n  Today: {bet_count} bets, {lean_count} leans across {len(predictions)} games")
print(f"\n  *** This is for entertainment and analysis purposes only. ***")
print(f"  *** Past performance does not guarantee future results. ***")

if __name__ == "__main__":
    pass
