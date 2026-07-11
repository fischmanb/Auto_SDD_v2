#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-11.
Phase 1: Eval July 10 predictions, update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-11"
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

# Actual results from July 10, 2026 (sourced via ESPN, MLB.com, FOX Sports)
# NOTE: MIL @ PIT was POSTPONED due to inclement weather (makeup July 11)
# NOTE: SF Giants @ Colorado Rockies game was at Oracle Park (COL was visitor),
#       but predictions had COL labeled as "home". COL won 4-3.
actual_results = {
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
print(f"\nEvaluated {total_games} games from {EVAL_DATE} (1 PPD)")
print(f"\nModel accuracy on {EVAL_DATE}:")
champ_id = champion["id"]
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
    days_alive = (date(2026, 7, 11) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 11, 2026)
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

# ── Tonight's games with odds (sourced from FanDuel, DraftKings, ESPN, SportsGrid) ──
# Saturday July 11, 2026 — MLB only (NBA/NHL/NFL off-season, last day before ASB)
# 15 games. Odds sourced via web search from multiple sportsbooks.

games_raw = [
    # 1. MIL Brewers @ PIT Pirates — 12:05 PM ET (makeup + scheduled)
    # MIL 59-34 (best in MLB), PIT 47-47. Drohan (5.07) vs Chandler (4.82).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.7,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.650,
            "away_record_pct": 0.620,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 126,
            "ml_away": -152,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. PHI Phillies @ DET Tigers — 6:10 PM ET
    # PHI 52-42, DET 50-44 (after 10-2 win). Phillies road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 119,
            "ml_away": -134,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. NYY Yankees @ WAS Nationals — 4:05 PM ET
    # NYY 52-42, WAS 43-51. Schlittler (9-5, 2.01) vs Mikolas (3-7, 5.78).
    # Yankees heavy road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.9,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 162,
            "ml_away": -194,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 4. KC Royals @ BAL Orioles — 7:05 PM ET
    # KC 42-52, BAL 48-46 (after 5-3 win). Orioles home favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 130,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. BOS Red Sox @ NYM Mets — 4:10 PM ET
    # BOS 47-47 (after 6-2 win), NYM 36-53. Bello/Rivera vs Peralta (5-7, 4.68).
    # Mets home favorites despite worse record (pitcher advantage).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.4,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -152,
            "ml_away": 128,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 6. SAC Athletics @ CHW White Sox — 2:10 PM ET
    # SAC 41-48 (after 14-1 loss), CHW 46-42 (after 14-1 win).
    # Jump (3.77) vs Hudson (1.50 home ERA). Line moved to CHW favored.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Sacramento Athletics",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 7. LAA Angels @ MIN Twins — 2:10 PM ET
    # LAA 38-57 (won 4-3 upset), MIN 46-49 (lost upset at home).
    # Joe Ryan (6-5, 2.85) vs Johnson (1-4, 6.99). Twins heavy favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.5,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.4,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -156,
            "ml_away": 132,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. SEA Mariners @ TB Rays — 4:10 PM ET
    # SEA 50-45 (lost 2-7), TB 56-37 (won 7-2). Near pick'em.
    # Gilbert (7-5) vs Jax (4-6).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.590,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.6,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 9. ARI Diamondbacks @ LAD Dodgers — 9:10 PM ET
    # ARI 47-47 (after 9-3 win), LAD 61-34 (lost 3-9, Ohtani scratched/ASG skip).
    # Dodgers heavy home favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.3,
            "season_opp_ppg": 3.5,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.690,
            "away_record_pct": 0.610,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -275,
            "ml_away": 226,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 10. COL Rockies @ SF Giants — 4:05 PM ET
    # COL 39-57 (won 4-3), SF 39-54 (lost 3-4). Giants home favorites (pitching).
    # Freeland (2-7, 7.46) vs Mahle (1-8).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 4.0,
            "season_opp_ppg": 5.2,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.300,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -152,
            "ml_away": 128,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 11. ATL Braves @ STL Cardinals — 7:15 PM ET
    # ATL 48-46 (lost 1-2), STL 45-49 (won 2-1). Braves road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 138,
            "ml_away": -164,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. TOR Blue Jays @ SD Padres — 8:40 PM ET
    # TOR 44-50 (won 5-3), SD 46-48 (lost 3-5).
    # Yesavage vs Buehler. Padres slight home favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.0,
            "book": "betmgm"
        }
    },

    # 13. MIA Marlins @ CLE Guardians — 4:10 PM ET
    # MIA 52-43 (lost 2-3), CLE 49-46 (won 3-2).
    # Pérez (5-6, 3.84) vs Bibee (2-9, 4.06). Marlins road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 3
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 120,
            "ml_away": -142,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 14. HOU Astros @ TEX Rangers — 7:05 PM ET
    # HOU 48-46 (lost 3-7), TEX 43-51 (won 7-3).
    # Lambert (7-5, 3.26) vs Rocker (2-7, 3.95). Astros road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 120,
            "ml_away": -142,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 15. CHC Cubs @ CIN Reds — 7:10 PM ET
    # CHC 48-46 (lost 0-4), CIN 47-47 (won 4-0, Greene 12K).
    # Near pick'em, higher total.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -105,
            "ml_away": -115,
            "total": 9.5,
            "book": "fanduel"
        }
    },
]

# ── Build batch ──────────────────────────────────────────────────────
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

# ── Organize results by game ─────────────────────────────────────────
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

# ── Compute blended predictions ──────────────────────────────────────
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
        w = 1.0 if mid == champ_id else next(c["weight"] for c in challengers if c["id"] == mid)
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

# ── Save predictions BEFORE displaying ───────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" MLB — Saturday July 11, 2026")
print(f"{'=' * 90}")
print(f" {'Game':<32} {'Spread':>7} {'Blend EV':>9} {'Best EV':>8} {'Worst':>7} {'Rob.':>5}  {'Verdict':<16}")
print(f" {'-'*32} {'-'*7} {'-'*9} {'-'*8} {'-'*7} {'-'*5}  {'-'*16}")

bets = []
leans = []
for p in sorted(predictions, key=lambda x: -x["best_blend_ev"]):
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
    elif p["verdict"] == "LEAN":
        leans.append(p)

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


# ── Update metrics.json ──────────────────────────────────────────────
metrics_file = os.path.join(BASE, "metrics.json")
with open(metrics_file) as f:
    metrics = json.load(f)

eval_games = model_scores[champion["id"]]["total"]
eval_correct = model_scores[champion["id"]]["correct"]

prev_all = metrics["all_time"]

jul10_bets = [p for p in past_preds["predictions"] if p["verdict"] == "BET"]
jul10_bet_wins = 0
jul10_bet_total = len(jul10_bets)
for bp in jul10_bets:
    gk = bp["game"]
    if gk not in actual_results:
        continue
    actual = actual_results[gk]
    margin = actual["home_score"] - actual["away_score"]
    bt = bp["best_bet_type"]
    if bt == "spread_home":
        won = (margin + bp["odds"]["spread_home"]) > 0
    elif bt == "spread_away":
        won = (-margin - bp["odds"]["spread_home"]) > 0
    elif bt == "ml_home":
        won = actual["winner"] == "home"
    else:
        won = actual["winner"] == "away"
    if won:
        jul10_bet_wins += 1

new_all_games = prev_all["total_games"] + eval_games
new_all_correct = prev_all["total_correct"] + eval_correct
new_all_bets = prev_all["total_bets_recommended"] + jul10_bet_total
new_all_bets_won = prev_all["total_bets_won"] + jul10_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_games, 4) if eval_games > 0 else 0.5,
    "ev_realized": round((jul10_bet_wins * 0.909 - (jul10_bet_total - jul10_bet_wins)) / max(jul10_bet_total, 1), 4),
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
        "weight": 1.0 if mid == champ_id else next((c["weight"] for c in challengers if c["id"] == mid), 0.5),
        "role": "champion" if mid == champ_id else "challenger"
    }

total_bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets_today,
    "leans": total_leans_today,
    "sports": ["baseball_mlb"],
    "notes": f"MLB Saturday slate (15 games, last day before ASB). {total_bets_today} BETs, {total_leans_today} LEANs. Eval Jul 10: {eval_correct}/{eval_games} correct (1 PPD)."
}

metrics["champion_history"] = metrics.get("champion_history", [])

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Print summary ────────────────────────────────────────────────────
print(f"\n{'=' * 50}")
print(f" Edge-Finder Metrics")
print(f"{'=' * 50}")
print(f" Champion: {champ_id} (promoted {champion.get('promoted_on', 'N/A')})")
print(f" 7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | {metrics['rolling_7d']['ev_realized']:+.1%} realized EV | {metrics['rolling_7d']['total_games']} games")
print(f" 30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | {metrics['rolling_30d']['ev_realized']:+.1%} realized EV | {metrics['rolling_30d']['total_games']} games")
print(f" All-time: {metrics['all_time']['accuracy']:.0%} accuracy | {metrics['all_time']['total_games']} games | {metrics['all_time']['total_bets_won']}/{metrics['all_time']['total_bets_recommended']} bets won")
print(f"\n Challenger weights: ", end="")
print(", ".join(f"{c['id']}={c['weight']}" for c in challengers))
if assumptions.get("graveyard"):
    print(f" Graveyard: ", end="")
    print(", ".join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} acc)" for g in assumptions["graveyard"]))
print(f"\n Today: {len(predictions)} games analyzed, {total_bets_today} BETs, {total_leans_today} LEANs")
print(f"\n NOTE: This is for entertainment and analysis purposes only.")
print(f" Past performance does not guarantee future results.")
