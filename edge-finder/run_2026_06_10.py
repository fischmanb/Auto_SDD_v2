#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-10.
Phase 1: Evaluate 2026-06-09 predictions.
Phase 2-5: Simulate tonight's games (NBA Finals G4 + ~14 MLB), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-06-10"
EVAL_DATE = "2026-06-09"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-06-09 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 90)
print(f" PHASE 1 — Evaluating predictions from {EVAL_DATE}")
print("=" * 90)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    eval_preds = json.load(f)

actual_results = {
    "Carolina Hurricanes @ Vegas Golden Knights": {
        "winner": "away",
        "home_score": 3, "away_score": 5, "margin": -2,
        "note": "CAR 5-3, Staal 2G incl GWG, series tied 2-2"
    },
    "Seattle Mariners @ Baltimore Orioles": {
        "winner": "away",
        "home_score": 2, "away_score": 4, "margin": -2,
        "note": "SEA 4-2"
    },
    "Los Angeles Dodgers @ Pittsburgh Pirates": {
        "winner": "away",
        "home_score": 2, "away_score": 12, "margin": -10,
        "note": "LAD 12-2"
    },
    "Boston Red Sox @ Tampa Bay Rays": {
        "winner": "home",
        "home_score": 4, "away_score": 3, "margin": 1,
        "note": "TB 4-3"
    },
    "Minnesota Twins @ Detroit Tigers": {
        "winner": "home",
        "home_score": 10, "away_score": 4, "margin": 6,
        "note": "DET 10-4"
    },
    "Arizona Diamondbacks @ Miami Marlins": {
        "winner": "home",
        "home_score": 6, "away_score": 3, "margin": 3,
        "note": "MIA 6-3"
    },
    "New York Yankees @ Cleveland Guardians": {
        "winner": "away",
        "home_score": 2, "away_score": 3, "margin": -1,
        "note": "NYY 3-2"
    },
    "Oakland Athletics @ Milwaukee Brewers": {
        "winner": "away",
        "home_score": 5, "away_score": 7, "margin": -2,
        "note": "ATH 7-5 at Las Vegas"
    },
    "Atlanta Braves @ Chicago White Sox": {
        "winner": "away",
        "home_score": 3, "away_score": 4, "margin": -1,
        "note": "ATL 4-3"
    },
    "St. Louis Cardinals @ New York Mets": {
        "winner": "away",
        "home_score": 0, "away_score": 7, "margin": -7,
        "note": "STL 7-0"
    },
    "Houston Astros @ Los Angeles Angels": {
        "winner": "home",
        "home_score": 10, "away_score": 1, "margin": 9,
        "note": "LAA 10-1"
    },
    "Chicago Cubs @ Colorado Rockies": {
        "winner": "home",
        "home_score": 5, "away_score": 0, "margin": 5,
        "note": "COL 5-0"
    },
    "Cincinnati Reds @ San Diego Padres": {
        "winner": "away",
        "home_score": 3, "away_score": 5, "margin": -2,
        "note": "CIN 5-3"
    },
    "Philadelphia Phillies @ Toronto Blue Jays": {
        "winner": "home",
        "home_score": 3, "away_score": 2, "margin": 1,
        "note": "TOR 3-2"
    },
    "Washington Nationals @ San Francisco Giants": {
        "winner": "away",
        "home_score": 3, "away_score": 4, "margin": -1,
        "note": "WSH 4-3"
    },
    "Texas Rangers @ Kansas City Royals": {
        "winner": "home",
        "home_score": 5, "away_score": 3, "margin": 2,
        "note": "KC 5-3"
    },
}

results_tsv_lines = []
model_correct = {m["id"]: 0 for m in all_models}
model_total = {m["id"]: 0 for m in all_models}
eval_games_played = 0

for pred in eval_preds["predictions"]:
    game_key = pred["game"]
    actual = actual_results.get(game_key)
    if not actual or actual.get("winner") == "postponed":
        print(f"  SKIP: {game_key} — postponed or missing")
        continue

    eval_games_played += 1
    actual_winner = actual["winner"]
    actual_margin = actual["margin"]

    for model in all_models:
        mid = model["id"]
        mr = pred["model_results"][mid]
        predicted_winner = "home" if mr["home_win_prob"] > 0.5 else "away"
        predicted_margin = mr["expected_margin"]

        hit = 1 if predicted_winner == actual_winner else 0
        model_correct[mid] += hit
        model_total[mid] += 1

        evs = {
            "spread_home": mr["spread_ev_home"],
            "spread_away": mr["spread_ev_away"],
            "ml_home": mr["ml_ev_home"],
            "ml_away": mr["ml_ev_away"],
        }
        best_bet = max(evs, key=evs.get)
        best_ev = evs[best_bet]

        spread = pred["odds"]["spread_home"]
        spread_covered_home = (actual_margin + spread) > 0
        if "spread_home" in best_bet:
            bet_result = "win" if spread_covered_home else "loss"
        elif "spread_away" in best_bet:
            bet_result = "win" if not spread_covered_home else "loss"
        elif "ml_home" in best_bet:
            bet_result = "win" if actual_winner == "home" else "loss"
        else:
            bet_result = "win" if actual_winner == "away" else "loss"

        line = f"{EVAL_DATE}\t{pred['sport']}\t{game_key}\t{mid}\t{predicted_winner}\t{predicted_margin:.2f}\t{mr['home_win_prob']}\t{actual_winner}\t{actual_margin}\t{hit}\t{best_ev:.4f}\t{evs.get('ml_home' if predicted_winner=='home' else 'ml_away', 0):.4f}\t{best_bet}\t{bet_result}"
        results_tsv_lines.append(line)

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_tsv_lines:
        f.write(line + "\n")

print(f"\n  Games evaluated: {eval_games_played}")
for m in all_models:
    mid = m["id"]
    total = model_total[mid]
    correct = model_correct[mid]
    pct = correct / total if total > 0 else 0
    role = "CHAMP" if mid == champion["id"] else "chall"
    print(f"  {role} {mid:<20} {correct}/{total} = {pct:.0%}")

# ── Step 1.4: Update challenger weights ────────────────────────────────
print(f"\n  --- Weight Updates ---")
champ_id = champion["id"]
champ_correct_set = set()
champ_wrong_set = set()
for pred in eval_preds["predictions"]:
    game_key = pred["game"]
    actual = actual_results.get(game_key)
    if not actual or actual.get("winner") == "postponed":
        continue
    mr = pred["model_results"][champ_id]
    predicted = "home" if mr["home_win_prob"] > 0.5 else "away"
    if predicted == actual["winner"]:
        champ_correct_set.add(game_key)
    else:
        champ_wrong_set.add(game_key)

weight_changes = []
for c in challengers:
    cid = c["id"]
    outperformed = 0
    underperformed = 0
    for pred in eval_preds["predictions"]:
        game_key = pred["game"]
        actual = actual_results.get(game_key)
        if not actual or actual.get("winner") == "postponed":
            continue
        mr = pred["model_results"][cid]
        c_predicted = "home" if mr["home_win_prob"] > 0.5 else "away"
        c_hit = c_predicted == actual["winner"]
        champ_hit = game_key in champ_correct_set
        if c_hit and not champ_hit:
            outperformed += 1
        elif champ_hit and not c_hit:
            underperformed += 1

    old_weight = c["weight"]
    if eval_games_played > 0:
        out_pct = outperformed / eval_games_played
        under_pct = underperformed / eval_games_played
        if out_pct >= 0.6:
            c["weight"] = min(1.0, c["weight"] + 0.1)
        elif under_pct >= 0.6:
            c["weight"] = max(0.1, c["weight"] - 0.1)

    if c["weight"] != old_weight:
        weight_changes.append(f"  {cid}: {old_weight:.1f} -> {c['weight']:.1f}")
        print(f"  {cid}: {old_weight:.1f} -> {c['weight']:.1f}")
    else:
        print(f"  {cid}: {old_weight:.1f} (no change)")

# ── Step 1.5: Promotion check ──────────────────────────────────────────
print(f"\n  --- Promotion Check ---")
champ_acc = model_correct[champ_id] / model_total[champ_id] if model_total[champ_id] > 0 else 0
promotion = None
for c in challengers:
    c_acc = model_correct[c["id"]] / model_total[c["id"]] if model_total[c["id"]] > 0 else 0
    if c_acc - champ_acc >= 0.05:
        promotion = c
        break

if promotion:
    print(f"  PROMOTION: {promotion['id']} -> champion!")
else:
    print(f"  No promotions. Champion {champ_id} accuracy: {champ_acc:.0%}")

# ── Step 1.6: Explore — retire & replace ──────────────────────────────
print(f"\n  --- Retirement Check ---")
retired = []
for c in challengers:
    if c["weight"] <= 0.15 and c["born"] < "2026-06-05":
        retired.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, born={c['born']})")

if not retired:
    print("  No retirements needed.")

# Update lifetime stats
for m in all_models:
    mid = m["id"]
    m["lifetime_games"] = m.get("lifetime_games", 0) + model_total.get(mid, 0)
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + model_correct.get(mid, 0)

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  Updated assumptions.json with eval results.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (June 10, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 90}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 90}")

# Sports in season: NBA Finals (Game 4), MLB (regular season)
# NHL: Off tonight (SCF G5 is June 11 in Raleigh)
# NFL: Offseason

games_raw = [
    # === NBA Finals Game 4: San Antonio Spurs @ New York Knicks ===
    # Series: NYK leads 2-1. SAS won G3 115-111. Game at MSG.
    # NYK -2.5, ML: NYK -130, SAS +110, O/U 216.5
    # Knicks: Brunson, Bridges, OG. Robinson questionable (1 injury).
    # Spurs: Wembanyama, Harper, Johnson.
    {
        "sport": "basketball_nba",
        "home": {
            "name": "New York Knicks",
            "season_ppg": 115.5,
            "season_opp_ppg": 108.2,
            "last10_ppg": 113.8,
            "last10_opp_ppg": 109.0,
            "season_pace": 99.0,
            "home_record_pct": 0.780,
            "away_record_pct": 0.536,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Antonio Spurs",
            "season_ppg": 116.0,
            "season_opp_ppg": 112.0,
            "last10_ppg": 114.5,
            "last10_opp_ppg": 110.5,
            "season_pace": 101.0,
            "home_record_pct": 0.707,
            "away_record_pct": 0.512,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -2.5,
            "ml_home": -130,
            "ml_away": 110,
            "total": 216.5,
            "book": "fanduel"
        }
    },

    # === MLB Games (14 games) ===

    # 1. Seattle Mariners (36-32) @ Baltimore Orioles (31-37)
    # Continuing series. SEA -110, BAL -106. O/U 9.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.37,
            "season_opp_ppg": 4.63,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.59,
            "season_opp_ppg": 4.41,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -106,
            "ml_away": -110,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 2. Los Angeles Dodgers (43-24) @ Pittsburgh Pirates (34-33)
    # Continuing series. LAD -196, PIT +164. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.53,
            "season_opp_ppg": 4.47,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 4.95,
            "season_opp_ppg": 4.05,
            "last10_ppg": 5.3,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.710,
            "away_record_pct": 0.590,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 164,
            "ml_away": -196,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 3. Boston Red Sox (27-38) @ Tampa Bay Rays (39-25)
    # Continuing series. TB -130, BOS +110. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.83,
            "season_opp_ppg": 4.17,
            "last10_ppg": 4.9,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Boston Red Sox",
            "season_ppg": 4.27,
            "season_opp_ppg": 4.73,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.9,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -130,
            "ml_away": 110,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 4. Atlanta Braves (40-26) @ Chicago White Sox (22-44)
    # Continuing series. Sale on mound. ATL -156, CWS +132. O/U 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 4.00,
            "season_opp_ppg": 5.00,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.370,
            "away_record_pct": 0.290,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.82,
            "season_opp_ppg": 4.18,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.630,
            "away_record_pct": 0.570,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 132,
            "ml_away": -156,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. Arizona Diamondbacks (34-32) @ Miami Marlins (32-35)
    # Continuing series. MIA -132, AZ +112. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.43,
            "season_opp_ppg": 4.57,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.57,
            "season_opp_ppg": 4.43,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -132,
            "ml_away": 112,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 6. Cleveland Guardians (37-29) @ New York Yankees (40-26)
    # New series at Yankee Stadium. CLE -120, NYY +100. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Yankees",
            "season_ppg": 4.79,
            "season_opp_ppg": 4.21,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.1,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.550,
            "is_back_to_back": False,
            "key_injuries": 3
        },
        "away": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.70,
            "season_opp_ppg": 4.30,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -120,
            "total": 8.0,
            "book": "draftkings"
        }
    },

    # 7. Chicago Cubs (34-33) @ Colorado Rockies (25-42)
    # Continuing series at Coors. CHC -154, COL +130. O/U 12.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.13,
            "season_opp_ppg": 4.87,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 5.4,
            "season_pace": 1.0,
            "home_record_pct": 0.410,
            "away_record_pct": 0.310,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.45,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 130,
            "ml_away": -154,
            "total": 12.0,
            "book": "fanduel"
        }
    },

    # 8. Cincinnati Reds (34-31) @ San Diego Padres (32-33)
    # Continuing series. CIN -118, SD +100. O/U 7.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Diego Padres",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.57,
            "season_opp_ppg": 4.43,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 100,
            "ml_away": -118,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 9. Philadelphia Phillies (34-31) @ Toronto Blue Jays (31-34)
    # Continuing series. PHI -112, TOR -104. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.43,
            "season_opp_ppg": 4.57,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.59,
            "season_opp_ppg": 4.41,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -104,
            "ml_away": -112,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 10. Washington Nationals (30-36) @ San Francisco Giants (28-38)
    # Continuing series. SF -120, WSH +100. O/U 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.72,
            "last10_ppg": 4.1,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Washington Nationals",
            "season_ppg": 4.36,
            "season_opp_ppg": 4.64,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.410,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 100,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 11. Detroit Tigers (28-39) @ Minnesota Twins (30-38)
    # New series at Target Field. DET -130, MIN +110. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.34,
            "season_opp_ppg": 4.66,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.390,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.70,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -130,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. New York Mets (33-32) @ St. Louis Cardinals (28-38)
    # New series at Busch Stadium. NYM -130, STL +110. O/U 8.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.70,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Mets",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.45,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 110,
            "ml_away": -130,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 13. Los Angeles Angels (27-39) @ Houston Astros (32-34)
    # New series at Minute Maid. LAA -122, HOU +104. O/U 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Houston Astros",
            "season_ppg": 4.47,
            "season_opp_ppg": 4.53,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.72,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.350,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 104,
            "ml_away": -122,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 14. Texas Rangers (31-35) @ Kansas City Royals (29-37)
    # Continuing series. TEX -126, KC +108. O/U 9.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.32,
            "season_opp_ppg": 4.68,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.43,
            "season_opp_ppg": 4.57,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 108,
            "ml_away": -126,
            "total": 9.5,
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
sports_order = ["basketball_nba", "baseball_mlb"]
sport_names = {"basketball_nba": "NBA", "baseball_mlb": "MLB"}
sport_dates = {"basketball_nba": "Wednesday June 10, 2026", "baseball_mlb": "Wednesday June 10, 2026"}

for sport in sports_order:
    sport_preds = [p for p in predictions if p["sport"] == sport]
    if not sport_preds:
        continue

    name = sport_names[sport]
    print(f"\n{'=' * 90}")
    print(f" {name} — {sport_dates[sport]}")
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

eval_correct_blend = 0
eval_total_blend = 0
for pred_item in eval_preds["predictions"]:
    game_key = pred_item["game"]
    actual = actual_results.get(game_key)
    if not actual or actual.get("winner") == "postponed":
        continue
    eval_total_blend += 1
    blend_predicted = "home" if pred_item["blend_home_wp"] > 0.5 else "away"
    if blend_predicted == actual["winner"]:
        eval_correct_blend += 1

metrics["all_time"]["total_games"] += eval_total_blend
metrics["all_time"]["total_correct"] += eval_correct_blend
metrics["all_time"]["accuracy"] = round(metrics["all_time"]["total_correct"] / metrics["all_time"]["total_games"], 4) if metrics["all_time"]["total_games"] > 0 else 0

bet_preds_eval = [p for p in eval_preds["predictions"] if p["verdict"] == "BET"]
bets_won_today = 0
for bp in bet_preds_eval:
    game_key = bp["game"]
    actual = actual_results.get(game_key)
    if not actual or actual.get("winner") == "postponed":
        continue
    metrics["all_time"]["total_bets_recommended"] += 1
    spread = bp["odds"]["spread_home"]
    actual_margin = actual["margin"]
    if bp["bet_market"] == "SPREAD":
        if bp["side"] == "HOME":
            won = (actual_margin + spread) > 0
        else:
            won = (actual_margin + spread) <= 0
    else:
        if bp["side"] == "HOME":
            won = actual["winner"] == "home"
        else:
            won = actual["winner"] == "away"
    if won:
        bets_won_today += 1
        metrics["all_time"]["total_bets_won"] += 1

metrics["rolling_7d"]["total_games"] += eval_total_blend
metrics["rolling_7d"]["total_correct"] += eval_correct_blend
metrics["rolling_7d"]["accuracy"] = round(metrics["rolling_7d"]["total_correct"] / metrics["rolling_7d"]["total_games"], 4) if metrics["rolling_7d"]["total_games"] > 0 else 0
metrics["rolling_30d"]["total_games"] += eval_total_blend
metrics["rolling_30d"]["total_correct"] += eval_correct_blend
metrics["rolling_30d"]["accuracy"] = round(metrics["rolling_30d"]["total_correct"] / metrics["rolling_30d"]["total_games"], 4) if metrics["rolling_30d"]["total_games"] > 0 else 0

for m in all_models:
    mid = m["id"]
    if mid in metrics["variant_performance"]:
        metrics["variant_performance"][mid]["lifetime_games"] = m.get("lifetime_games", 0)
        metrics["variant_performance"][mid]["lifetime_correct"] = m.get("lifetime_correct", 0)
        if mid == champion["id"]:
            metrics["variant_performance"][mid]["weight"] = 1.0
        else:
            c_data = next((c for c in challengers if c["id"] == mid), None)
            if c_data:
                metrics["variant_performance"][mid]["weight"] = c_data["weight"]

total_bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
total_leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")
total_no_today = sum(1 for p in predictions if p["verdict"] == "NO BET")

metrics["last_updated"] = TODAY
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": total_bets_today,
    "leans": total_leans_today,
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"NBA Finals G4 (SAS@NYK) + {sum(1 for p in predictions if p['sport']=='baseball_mlb')} MLB games. {total_bets_today} BETs, {total_leans_today} LEANs, {total_no_today} NO BETs. Eval: Jun 9 was {eval_correct_blend}/{eval_total_blend} blended correct, {bets_won_today}/{len([p for p in bet_preds_eval if actual_results.get(p['game'],{}).get('winner','')!='postponed'])} BETs won."
}

with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=2)

# ── Summary stats ───────────────────────────────────────────────────
print(f"\n{'=' * 90}")
print(f" EVAL RECAP: Jun 9 predictions — {eval_correct_blend}/{eval_total_blend} blended correct, {bets_won_today}/{len([p for p in bet_preds_eval if actual_results.get(p['game'],{}).get('winner','')!='postponed'])} BETs won")
print(f"{'=' * 90}")

print(f"\n{'=' * 90}")
print(f" TONIGHT: {len(predictions)} games analyzed | {total_bets_today} BETs | {total_leans_today} LEANs | {total_no_today} NO BETs")
print(f"{'=' * 90}")

print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 50}")
print(f"  Champion: {champion['id']} (promoted {champion['promoted_on']})")
print(f"  All-time: {metrics['all_time']['total_correct']}/{metrics['all_time']['total_games']} = {metrics['all_time']['accuracy']:.1%} accuracy")
print(f"  All-time bets: {metrics['all_time']['total_bets_won']}/{metrics['all_time']['total_bets_recommended']} won")
cw = ", ".join(f"{c['id'].replace('-v1','')}={c['weight']}" for c in challengers)
print(f"  Challengers: {cw}")
gcount = len(assumptions.get("graveyard", []))
print(f"  Graveyard: {gcount} retired variants")

print(f"\n  NOTE: This analysis is for entertainment purposes only.")
print(f"  Past performance does not guarantee future results.")
