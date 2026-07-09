#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-09.
Phase 1: Eval July 7 predictions, update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-09"
EVAL_DATE = "2026-07-07"

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 7 PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-07 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

actual_results = {
    "Milwaukee Brewers @ St. Louis Cardinals": {"winner": "away", "home_score": 2, "away_score": 10},
    "Chicago Cubs @ Baltimore Orioles": {"winner": "away", "home_score": 2, "away_score": 5},
    "Sacramento Athletics @ Detroit Tigers": {"winner": "home", "home_score": 6, "away_score": 2},
    "Atlanta Braves @ Pittsburgh Pirates": {"winner": "home", "home_score": 12, "away_score": 4},
    "Seattle Mariners @ Miami Marlins": {"winner": "home", "home_score": 6, "away_score": 5},
    "New York Yankees @ Tampa Bay Rays": {"winner": "home", "home_score": 6, "away_score": 4},
    "Houston Astros @ Washington Nationals": {"winner": "away", "home_score": 3, "away_score": 6},
    "Boston Red Sox @ Chicago White Sox": {"winner": "away", "home_score": 1, "away_score": 8},
    "Kansas City Royals @ New York Mets": {"winner": "away", "home_score": 12, "away_score": 16},
    "Los Angeles Angels @ Texas Rangers": {"winner": "home", "home_score": 8, "away_score": 3},
    "Arizona Diamondbacks @ San Diego Padres": {"winner": "home", "home_score": 4, "away_score": 1},
    "Toronto Blue Jays @ San Francisco Giants": {"winner": "away", "home_score": 3, "away_score": 9},
    "Colorado Rockies @ Los Angeles Dodgers": {"winner": "away", "home_score": 3, "away_score": 4},
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
        if "spread" in bet_type:
            if "home" in bet_type:
                bet_hit = 1 if margin + pred["odds"]["spread_home"] > 0 else 0
            else:
                bet_hit = 1 if -(margin + pred["odds"]["spread_home"]) > 0 else 0
        else:
            if "home" in bet_type:
                bet_hit = 1 if actual_winner == "home" else 0
            else:
                bet_hit = 1 if actual_winner == "away" else 0
        bet_result = "win" if bet_hit else "loss"

        tsv_lines.append(
            f"{EVAL_DATE}\t{pred['sport']}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']}\t{mr['home_win_prob']}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{best_ev_type[1]}\t{max(mr['ml_ev_home'], mr['ml_ev_away'])}\t"
            f"{bet_type}\t{bet_result}"
        )

# Append to results.tsv
with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

print(f"\n  Scored {len(actual_results)} games across {len(model_ids)} models.")
champ_id = champion["id"]
for mid in model_ids:
    s = model_scores[mid]
    acc = s["correct"] / s["total"] if s["total"] > 0 else 0
    tag = " (CHAMPION)" if mid == champ_id else ""
    print(f"  {mid}{tag}: {s['correct']}/{s['total']} = {acc:.1%}")

# ── Step 1.4: Update weights ──────────────────────────────────────────
print(f"\n  Updating challenger weights...")
champ_score = model_scores[champ_id]
champ_acc = champ_score["correct"] / champ_score["total"] if champ_score["total"] > 0 else 0

for c in challengers:
    cid = c["id"]
    cs = model_scores[cid]
    c_acc = cs["correct"] / cs["total"] if cs["total"] > 0 else 0
    old_w = c["weight"]

    if cs["total"] >= 5:
        if c_acc >= champ_acc + 0.1:  # outperformed by >=10%
            c["weight"] = min(1.0, c["weight"] + 0.1)
        elif c_acc <= champ_acc - 0.1:  # underperformed by >=10%
            c["weight"] = max(0.1, c["weight"] - 0.1)
    # More lenient for smaller samples
    elif cs["total"] >= 1:
        if c_acc >= 0.6 * champ_acc + 0.4:
            c["weight"] = min(1.0, c["weight"] + 0.1)
        elif c_acc <= champ_acc * 0.6:
            c["weight"] = max(0.1, c["weight"] - 0.1)

    if c["weight"] != old_w:
        print(f"    {cid}: {old_w:.1f} -> {c['weight']:.1f} (acc={c_acc:.1%} vs champ={champ_acc:.1%})")

# Update lifetime stats
for m in all_models:
    mid = m["id"]
    ms = model_scores[mid]
    m["lifetime_games"] = m.get("lifetime_games", 0) + ms["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + ms["correct"]

# ── Step 1.4b: Update rolling 10-day accuracy ──────────────────────────
# Read recent results from results.tsv to compute rolling 10d accuracy
print("\n  Computing rolling 10-day accuracy...")
import csv
from datetime import datetime, timedelta

cutoff_date = date(2026, 7, 9) - timedelta(days=10)
rolling_stats = {mid: {"correct": 0, "total": 0} for mid in model_ids}

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.DictReader(f, delimiter="\t")
    for row in reader:
        row_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        if row_date >= cutoff_date:
            mid = row["model_id"]
            if mid in rolling_stats:
                rolling_stats[mid]["total"] += 1
                rolling_stats[mid]["correct"] += int(row["hit"])

for m in all_models:
    mid = m["id"]
    rs = rolling_stats[mid]
    m["rolling_10d_accuracy"] = rs["correct"] / rs["total"] if rs["total"] > 0 else 0.5
    print(f"    {mid}: {rs['correct']}/{rs['total']} = {m['rolling_10d_accuracy']:.1%}")

# ── Step 1.5: Promotion check ──────────────────────────────────────────
print(f"\n  Checking promotions...")
champ_rolling = champion["rolling_10d_accuracy"]
promoted = False
for c in challengers:
    if c["rolling_10d_accuracy"] >= champ_rolling + 0.05:
        print(f"  PROMOTE: {c['id']} ({c['rolling_10d_accuracy']:.1%}) beats champion {champ_id} ({champ_rolling:.1%})")
        old_champ = champion.copy()
        old_champ["weight"] = 0.7
        old_champ.pop("promoted_on", None)

        c["promoted_on"] = TODAY
        assumptions["champion"] = c
        challengers.remove(c)
        challengers.append(old_champ)
        assumptions["challengers"] = challengers

        promoted = True
        champion = assumptions["champion"]
        challengers = assumptions["challengers"]
        champ_id = champion["id"]
        break
    else:
        print(f"    {c['id']}: {c['rolling_10d_accuracy']:.1%} vs champion {champ_rolling:.1%} — no promotion")

if not promoted:
    print("  No promotions triggered.")

# ── Step 1.6: Retirement check ──────────────────────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 7, 9) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 9, 2026)
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

# ── Tonight's games with odds ──────────────────────────────────────────
# Thursday July 9, 2026 — MLB only (NBA/NHL/NFL off-season)
# Odds sourced from FanDuel/ESPN/BetMGM/Covers via web search

games_raw = [
    # 1. ATL Braves @ PIT Pirates (12:35 PM ET)
    # Series rubber match. ATL 53-38, PIT 47-46. Elder (5-6) vs Keller (6-6).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.8,
            "season_opp_ppg": 4.0,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -120,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 2. KC Royals @ NYM Mets (1:10 PM ET)
    # KC +128, NYM -152. Royals on the road, Mets at home.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 4.9,
            "season_opp_ppg": 4.3,
            "last10_ppg": 5.5,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -152,
            "ml_away": 128,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 3. NYY Yankees @ TB Rays (1:10 PM ET at Tropicana Field)
    # NYY +135, TB -163, O/U 7.5. TB 54-36, NYY 50-42.
    # Rasmussen (7-4) for TB.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -163,
            "ml_away": 135,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 4. CLE Guardians @ MIN Twins (1:40 PM ET at Target Field)
    # CLE -135, MIN +110. Williams (9-4, 3.89) vs Ober (6-3, 4.59).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.6,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -135,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 5. BOS Red Sox @ CWS White Sox (2:10 PM ET at Rate Field)
    # BOS -104, CWS -112. Near pick'em.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.8,
            "season_opp_ppg": 5.1,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.350,
            "away_record_pct": 0.280,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.2,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -112,
            "ml_away": -104,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 6. CHC Cubs @ BAL Orioles (6:35 PM ET at Camden Yards)
    # CHC +104, BAL -125.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.1,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -125,
            "ml_away": 104,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 7. SAC Athletics @ DET Tigers (6:40 PM ET at Comerica Park)
    # DET -138, ATH +118. Tigers strong at home.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Sacramento Athletics",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -138,
            "ml_away": 118,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. SEA Mariners @ MIA Marlins (6:40 PM ET at loanDepot Park)
    # SEA -155, MIA +125, O/U 8. Marlins on 5-game win streak.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.410,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.3,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 125,
            "ml_away": -155,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 9. PHI Phillies @ CIN Reds (7:10 PM ET at Great American Ball Park)
    # PHI -162, CIN +134, O/U 9.5. Luzardo (7-4, 3.75) vs Singer (3-8, 5.03).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.7,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.420,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.9,
            "season_opp_ppg": 3.8,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 134,
            "ml_away": -162,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 10. MIL Brewers @ STL Cardinals (7:45 PM ET at Busch Stadium)
    # MIL -136, STL +113, O/U 8.5. Henderson (2-1, 2.74) vs Pallante (10-5, 3.60).
    # MIL 56-33, dominant. STL 47-41.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.2,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.650,
            "away_record_pct": 0.610,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 113,
            "ml_away": -136,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 11. LAA Angels @ TEX Rangers (8:05 PM ET at Globe Life Field)
    # TEX -136, LAA +116. Eovaldi (9-7) vs Detmers (3-6).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Texas Rangers",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -136,
            "ml_away": 116,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. ARI Diamondbacks @ SD Padres (9:40 PM ET at Petco Park)
    # SD -125, ARI +105, O/U 8.5. Kelly (6-8, 5.71) vs Canning.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.5,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.460,
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
]

print(f"\n  {len(games_raw)} MLB games tonight.\n")

# ── Build batch for simulation ──────────────────────────────────────────
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
            "n_sims": 50000,
        }
        batch.append(entry)

print(f"  Running {len(batch)} simulations ({len(games_raw)} games × {len(all_models)} models)...")
results = run_batch(batch)
print("  Simulations complete.\n")

# ── Organize results by game ──────────────────────────────────────────
game_results = {}
for i, game in enumerate(games_raw):
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key] = {
        "game": game,
        "model_results": {}
    }

for j, r in enumerate(results):
    game_idx = j // len(all_models)
    game = games_raw[game_idx]
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key]["model_results"][r["model_id"]] = r

# ── Phase 4: Blended predictions ──────────────────────────────────────
predictions = []
for game_key, gdata in game_results.items():
    game = gdata["game"]
    model_res = gdata["model_results"]

    # Weighted blend
    total_weight = 0
    blend_wp = 0
    blend_margin = 0
    blend_evs = {"spread_home": 0, "spread_away": 0, "ml_home": 0, "ml_away": 0}

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champ_id else model["weight"]
        mr = model_res[mid]

        blend_wp += w * mr["home_win_prob"]
        blend_margin += w * mr["expected_margin"]
        blend_evs["spread_home"] += w * mr["spread_ev_home"]
        blend_evs["spread_away"] += w * mr["spread_ev_away"]
        blend_evs["ml_home"] += w * mr["ml_ev_home"]
        blend_evs["ml_away"] += w * mr["ml_ev_away"]
        total_weight += w

    blend_wp /= total_weight
    blend_margin /= total_weight
    for k in blend_evs:
        blend_evs[k] /= total_weight

    # Best EV
    best_bet_type = max(blend_evs, key=blend_evs.get)
    best_blend_ev = blend_evs[best_bet_type]

    # Best/worst model EV for the best bet type
    best_model_ev = max(model_res[m["id"]][f"{best_bet_type.replace('ml_', 'ml_ev_').replace('spread_', 'spread_ev_')}"]
                        if best_bet_type.startswith("ml_") or best_bet_type.startswith("spread_")
                        else 0
                        for m in all_models)

    ev_key_map = {
        "spread_home": "spread_ev_home",
        "spread_away": "spread_ev_away",
        "ml_home": "ml_ev_home",
        "ml_away": "ml_ev_away",
    }
    ev_field = ev_key_map[best_bet_type]
    model_evs_for_best = [model_res[m["id"]][ev_field] for m in all_models]
    best_model_ev = max(model_evs_for_best)
    worst_model_ev = min(model_evs_for_best)

    # Robustness: how many models agree on the same side
    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_models if model_res[m["id"]].get("home_win_prob", 0.5) > 0.5)
    else:
        agree_count = sum(1 for m in all_models if model_res[m["id"]].get("home_win_prob", 0.5) < 0.5)

    robustness = f"{agree_count}/{len(all_models)}"

    # Verdict
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and agree_count >= 4 and worst_model_ev <= 0:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Side
    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    # Kelly criterion (simplified): f* = (bp - q) / b
    if best_blend_ev > 0:
        kelly = min(0.05, max(0, best_blend_ev / 3))
    else:
        kelly = 0

    pred = {
        "game": game_key,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": round(blend_wp, 4),
        "blend_away_wp": round(1 - blend_wp, 4),
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
            m["id"]: {
                "home_win_prob": model_res[m["id"]]["home_win_prob"],
                "expected_margin": model_res[m["id"]]["expected_margin"],
                "spread_ev_home": model_res[m["id"]]["spread_ev_home"],
                "spread_ev_away": model_res[m["id"]]["spread_ev_away"],
                "ml_ev_home": model_res[m["id"]]["ml_ev_home"],
                "ml_ev_away": model_res[m["id"]]["ml_ev_away"],
            }
            for m in all_models
        },
    }
    predictions.append(pred)

# ── Save predictions ──────────────────────────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"  Predictions saved to {pred_file}")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'┌' + '─' * 85 + '┐'}")
print(f"│ {'MLB — Thursday Jul 9, 2026':^83} │")
print(f"├{'─' * 24}┬{'─' * 9}┬{'─' * 9}┬{'─' * 9}┬{'─' * 9}┬{'─' * 7}┬{'─' * 15}┤")
print(f"│ {'Game':<22} │ {'Spread':>7} │ {'Blend':>7} │ {'Best':>7} │ {'Worst':>7} │ {'Rob.':>5} │ {'Verdict':<13} │")
print(f"│ {'':22} │ {'':>7} │ {'EV':>7} │ {'EV':>7} │ {'EV':>7} │ {'':>5} │ {'':13} │")
print(f"├{'─' * 24}┼{'─' * 9}┼{'─' * 9}┼{'─' * 9}┼{'─' * 9}┼{'─' * 7}┼{'─' * 15}┤")

bet_count = 0
lean_count = 0
for p in predictions:
    spread = p["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}"
    blend_ev_str = f"{p['best_blend_ev']:+.1%}"[:-1]
    best_ev_str = f"{p['best_model_ev']:+.1%}"[:-1]
    worst_ev_str = f"{p['worst_model_ev']:+.1%}"[:-1]
    rob = p["robustness"]

    if p["verdict"] == "BET":
        icon = "✅"
        bet_count += 1
        verdict_str = f"{icon} BET {p['side']}"
    elif p["verdict"] == "LEAN":
        icon = "⚠️"
        lean_count += 1
        verdict_str = f"{icon} LEAN {p['side']}"
    else:
        icon = "❌"
        verdict_str = f"{icon} NO BET"

    home_abbr = p["home_team"].split()[-1][:3].upper()
    away_abbr = p["away_team"].split()[-1][:3].upper()
    if len(p["home_team"].split()) > 1:
        home_abbr = p["home_team"].split()[-1][:3].upper()
    if len(p["away_team"].split()) > 1:
        away_abbr = p["away_team"].split()[-1][:3].upper()

    game_str = f"{away_abbr} @ {home_abbr}"

    print(f"│ {game_str:<22} │ {spread_str:>7} │ {blend_ev_str:>7} │ {best_ev_str:>7} │ {worst_ev_str:>7} │ {rob:>5} │ {verdict_str:<13} │")

print(f"└{'─' * 24}┴{'─' * 9}┴{'─' * 9}┴{'─' * 9}┴{'─' * 9}┴{'─' * 7}┴{'─' * 15}┘")

# ── Detailed BET breakdowns ──────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" DETAILED BET RECOMMENDATIONS")
print(f"{'=' * 78}")

for p in predictions:
    if p["verdict"] != "BET":
        continue
    print(f"\n  {p['game']}")
    print(f"  Verdict: BET {p['side']} ({p['side_team']}) via {p['bet_market']}")
    print(f"  Blended EV: {p['best_blend_ev']:+.1%} | Best: {p['best_model_ev']:+.1%} | Worst: {p['worst_model_ev']:+.1%}")
    print(f"  Robustness: {p['robustness']} | Kelly: {p['kelly']:.1%}")
    print(f"  Blended Win Prob: Home {p['blend_home_wp']:.1%} / Away {p['blend_away_wp']:.1%}")
    print(f"  Best book: {p['odds']['book']} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")
    print(f"  Model agreement:")
    for mid, mr in p["model_results"].items():
        agrees = "home" if mr["home_win_prob"] > 0.5 else "away"
        tag = " (CHAMP)" if mid == champ_id else ""
        best_ev = max(mr["spread_ev_home"], mr["spread_ev_away"], mr["ml_ev_home"], mr["ml_ev_away"])
        print(f"    {mid}{tag}: WP={mr['home_win_prob']:.1%} home, margin={mr['expected_margin']:+.2f}, best_ev={best_ev:+.1%}")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 5 — Metrics Dashboard")
print(f"{'=' * 78}")

# Update metrics
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models_final = [champion] + challengers

# Compute rolling stats from results.tsv
rolling_7d = {"correct": 0, "total": 0}
rolling_30d = {"correct": 0, "total": 0}
all_time = {"correct": 0, "total": 0}
cutoff_7d = date(2026, 7, 9) - timedelta(days=7)
cutoff_30d = date(2026, 7, 9) - timedelta(days=30)

champ_id_final = champion["id"]
with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.DictReader(f, delimiter="\t")
    for row in reader:
        if row["model_id"] != champ_id_final:
            continue
        row_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        hit = int(row["hit"])
        all_time["total"] += 1
        all_time["correct"] += hit
        if row_date >= cutoff_30d:
            rolling_30d["total"] += 1
            rolling_30d["correct"] += hit
        if row_date >= cutoff_7d:
            rolling_7d["total"] += 1
            rolling_7d["correct"] += hit

metrics = {
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round(rolling_7d["correct"] / rolling_7d["total"], 4) if rolling_7d["total"] > 0 else 0,
        "ev_realized": round((rolling_7d["correct"] / rolling_7d["total"] - 0.5) * rolling_7d["total"] * 0.1, 4) if rolling_7d["total"] > 0 else 0,
        "total_games": rolling_7d["total"],
        "total_correct": rolling_7d["correct"],
    },
    "rolling_30d": {
        "accuracy": round(rolling_30d["correct"] / rolling_30d["total"], 4) if rolling_30d["total"] > 0 else 0,
        "ev_realized": round((rolling_30d["correct"] / rolling_30d["total"] - 0.5) * rolling_30d["total"] * 0.1, 4) if rolling_30d["total"] > 0 else 0,
        "total_games": rolling_30d["total"],
        "total_correct": rolling_30d["correct"],
    },
    "all_time": {
        "accuracy": round(all_time["correct"] / all_time["total"], 4) if all_time["total"] > 0 else 0,
        "ev_realized": round((all_time["correct"] / all_time["total"] - 0.5) * all_time["total"] * 0.1, 4) if all_time["total"] > 0 else 0,
        "total_games": all_time["total"],
        "total_correct": all_time["correct"],
        "total_bets_recommended": bet_count,
        "total_bets_won": 0,
    },
    "variant_performance": {
        m["id"]: {
            "lifetime_games": m.get("lifetime_games", 0),
            "lifetime_correct": m.get("lifetime_correct", 0),
            "weight": 1.0 if m["id"] == champ_id_final else m.get("weight", 0.5),
            "role": "champion" if m["id"] == champ_id_final else "challenger",
        }
        for m in all_models_final
    },
    "champion_history": [
        {"id": "season-avg-v1", "promoted_on": "2026-03-24", "reason": "initial champion"},
        {"id": "combo-balanced-v1", "promoted_on": "2026-06-16", "reason": "Rolling 10d accuracy 80.0% exceeded season-avg-v1's 60.4% by 19.6% (threshold: 5%)"},
        {"id": "regression-v1", "promoted_on": "2026-06-26", "reason": "Rolling accuracy exceeded predecessor by >=5%"},
    ],
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(predictions),
        "bets_recommended": bet_count,
        "leans": lean_count,
        "sports": ["baseball_mlb"],
        "notes": f"MLB Thursday slate ({len(predictions)} games). {bet_count} BETs, {lean_count} LEANs. Eval Jul 7: {model_scores.get(champ_id_final, {}).get('correct', 0)}/{model_scores.get(champ_id_final, {}).get('total', 0)} correct.",
    },
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# Print summary
r7 = metrics["rolling_7d"]
r30 = metrics["rolling_30d"]
at = metrics["all_time"]

print(f"\n\U0001f4ca Edge-Finder Metrics")
print(f"{'━' * 40}")
print(f"Champion: {champ_id_final} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"7-day:  {r7['accuracy']:.0%} accuracy | {r7['total_correct']}/{r7['total_games']} games")
print(f"30-day: {r30['accuracy']:.0%} accuracy | {r30['total_correct']}/{r30['total_games']} games")
print(f"All-time: {at['accuracy']:.0%} accuracy | {at['total_correct']}/{at['total_games']} games")
print()
print(f"Challenger weights:", end="")
for c in challengers:
    new_tag = "(NEW)" if c.get("born", "") > "2026-07-04" else ""
    print(f" {c['id']}={c['weight']:.1f}{new_tag}", end=",")
print()

graveyard = assumptions.get("graveyard", [])
if graveyard:
    print(f"Graveyard:", end="")
    for g in graveyard:
        print(f" {g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} acc)", end=",")
    print()

print(f"\nToday: {len(predictions)} games analyzed, {bet_count} bets recommended, {lean_count} leans")
print(f"\n{'━' * 40}")
print(f"NOTE: This is for entertainment and analysis purposes only.")
print(f"Past performance does not guarantee future results.")

print("\n\nDone.")
