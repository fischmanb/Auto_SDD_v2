#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-17.
Phase 1: Eval July 16 predictions (NYM @ PHI), update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-17"
EVAL_DATE = "2026-07-16"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 16 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-16 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 16, 2026 (sourced via web search from ESPN/MLB.com)
# Only 1 MLB game post-All-Star break: NYM 4, PHI 1
# Francisco Alvarez homered twice, Brett Baty also went deep.
actual_results = {
    "New York Mets @ Philadelphia Phillies": {"winner": "away", "home_score": 1, "away_score": 4},
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
    days_alive = (date(2026, 7, 17) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 17, 2026)
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

# ── Tonight's games with odds from web searches ──────────────────────
# Friday July 17, 2026 — MLB only (NBA/NHL/NFL off-season)
# 13 games (TB@BOS doubleheader = 2 games).
# Odds sourced from FanDuel/DraftKings/BetMGM/ESPN/Covers via web search.
# Records through July 16. Stats estimated from standings and recent form.

games_raw = [
    # 1. TB Rays @ BOS Red Sox — Game 1, 1:35 PM ET
    # TB 56-38 (1st AL East), BOS 46-48. TB slight road favorites.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -126,
            "ml_away": 104,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 2. LAD Dodgers @ NYY Yankees — 7:05 PM ET
    # LAD 58-31 (best MLB), NYY 49-38. Sasaki (5.33 ERA) vs Cole (4.04 ERA).
    # Near pick'em: LAD -111, NYY -108. Total 9.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.7,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 5.2,
            "season_opp_ppg": 3.6,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.680,
            "away_record_pct": 0.620,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -108,
            "ml_away": -111,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 3. PIT Pirates @ CLE Guardians — 7:10 PM ET
    # PIT 44-45, CLE 47-42. Jones (4.37 ERA, pitch limit) vs Williams (10-4, 3.81 ERA).
    # CLE -124, PIT +109.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.1,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -124,
            "ml_away": 109,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 4. TB Rays @ BOS Red Sox — Game 2, 7:10 PM ET
    # Same teams, G2 of doubleheader. Englert (3.82 ERA) for TB. BOS -144.
    # Both teams on back-to-back (second game of DH).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.470,
            "is_back_to_back": True,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.600,
            "is_back_to_back": True,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -144,
            "ml_away": 120,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 5. TEX Rangers @ ATL Braves — 7:15 PM ET
    # TEX 49-47, ATL 55-40 (27-18 at home). Quantrill (2.12 ERA) vs Sale (9-6, 2.20 ERA).
    # ATL -210, TEX +170. Sale vs Quantrill = elite SP matchup.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.8,
            "last10_ppg": 4.9,
            "last10_opp_ppg": 3.7,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.2,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -210,
            "ml_away": 170,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 6. CHW White Sox @ TOR Blue Jays — 7:15 PM ET
    # CHW 45-42 (1st-place form), TOR 42-46. Kay (6-4, 4.33 ERA) vs Miles (4-1, 2.85 ERA).
    # TOR -134, CHW +114. Total 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.0,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Chicago White Sox",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -134,
            "ml_away": 114,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 7. MIA Marlins @ MIL Brewers — 7:40 PM ET
    # MIA 47-42, MIL 54-32. Alcantara vs Henderson (2.47 FIP, 30.6% K rate).
    # MIL -155, MIA +132. Total 8. 98% of handle on Over.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.7,
            "season_opp_ppg": 3.6,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.600,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -155,
            "ml_away": 132,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 8. MIN Twins @ CHC Cubs — 8:05 PM ET
    # MIN 42-47, CHC 49-39. Ober (6-3, 4.40 ERA, 7.11 FIP away) vs Rea (7-5, 4.75 ERA).
    # CHC -137, MIN +115.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago Cubs",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -137,
            "ml_away": 115,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 9. SD Padres @ KC Royals — 8:10 PM ET
    # SD 43-44, KC 35-53. King (6-7, 3.41 ERA) vs Lugo (3-6, 4.56 ERA).
    # SD -112, KC -104. Total 10.5. 79% tickets + 95% handle on SD.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.7,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.410,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.3,
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
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -112,
            "total": 10.5,
            "book": "fanduel"
        }
    },

    # 10. BAL Orioles @ HOU Astros — 8:10 PM ET
    # BAL ~46-51, HOU ~47-51. Kremer vs Lambert. Genuine pick'em.
    # BAL -108, HOU -108. BAL 7-3 last 10 SU.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.4,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -108,
            "ml_away": -108,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 11. CIN Reds @ COL Rockies — 8:40 PM ET (Coors Field)
    # CIN 40-47, COL 36-53. Singer (3-9, 4.72 ERA) vs Hughes (0-0, 3.00 ERA).
    # COL -116, CIN -102. Total 12 (Coors inflated). Reds 51.7% win prob.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.5,
            "season_opp_ppg": 5.4,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 5.6,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.360,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -116,
            "ml_away": -102,
            "total": 12.0,
            "book": "fanduel"
        }
    },

    # 12. DET Tigers @ LAA Angels — 9:38 PM ET
    # DET 38-50, LAA 36-53. Melton (5-1, 1.82 ERA) vs Detmers (3-6, 4.39 ERA).
    # DET -115, LAA -104. 86% tickets + 98% handle on DET. Strong pitcher edge.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 3.7,
            "season_opp_ppg": 4.8,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.5,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -115,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 13. STL Cardinals @ ARI Diamondbacks — 9:40 PM ET
    # STL 46-39, ARI 43-44. STL -112, ARI -104.
    # Spread: STL -1.5 (+146), ARI +1.5 (-178).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.4,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.3,
            "season_opp_ppg": 4.0,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 3.9,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -112,
            "total": 8.5,
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
pred_data = {
    "date": TODAY,
    "predictions": predictions,
    "metadata": {
        "sports_checked": ["baseball_mlb"],
        "sports_skipped": ["basketball_nba (off-season)", "icehockey_nhl (off-season)", "americanfootball_nfl (off-season)"],
        "total_games": len(predictions),
        "total_bets": sum(1 for p in predictions if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "data_sources": ["web search (ESPN, MLB.com, FanDuel, DraftKings, BetMGM, Covers)"],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. TB@BOS doubleheader modeled as 2 separate games (G2 with b2b flag)."
    }
}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Display results ──────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" MLB — Friday July 17, 2026")
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
eval_acc = eval_correct / eval_games if eval_games > 0 else 0.5

prev_all = metrics["all_time"]

jul16_bets = [p for p in past_preds["predictions"] if p["verdict"] == "BET"]
jul16_bet_wins = 0
jul16_bet_total = len(jul16_bets)
for bp in jul16_bets:
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
        jul16_bet_wins += 1

new_all_games = prev_all["total_games"] + eval_games
new_all_correct = prev_all["total_correct"] + eval_correct
new_all_bets = prev_all["total_bets_recommended"] + jul16_bet_total
new_all_bets_won = prev_all["total_bets_won"] + jul16_bet_wins

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_games, 4) if eval_games > 0 else 0.5,
    "ev_realized": round((jul16_bet_wins * 0.909 - (jul16_bet_total - jul16_bet_wins)) / max(jul16_bet_total, 1), 4),
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
    "notes": f"MLB Friday slate (13 games, TB@BOS DH). Eval Jul 16: {eval_correct}/{eval_games} correct (NYM upset PHI 4-1). {total_bets_today} BETs, {total_leans_today} LEANs. All 6 models wrong on yesterday's PHI ML bet."
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
