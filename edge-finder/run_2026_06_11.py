#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-11.
Phase 1: Evaluate 2026-06-09 predictions.
Phase 2-5: Simulate tonight's games (NHL SCF Game 5 + 8 MLB), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-06-11"
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

# Actual results from June 9, 2026 (fetched via web search)
actual_results = {
    "Carolina Hurricanes @ Vegas Golden Knights": {
        "winner": "away",  # CAR 5, VGK 3
        "home_score": 3,
        "away_score": 5,
        "margin": -2,
        "note": "CAR 5-3, Jordan Staal 2G, series tied 2-2"
    },
    "Seattle Mariners @ Baltimore Orioles": {
        "winner": "away",  # SEA 6, BAL 5
        "home_score": 5,
        "away_score": 6,
        "margin": -1,
        "note": "SEA 6-5 (10 inn), Arozarena HR"
    },
    "Los Angeles Dodgers @ Pittsburgh Pirates": {
        "winner": "away",  # LAD 12, PIT 3
        "home_score": 3,
        "away_score": 12,
        "margin": -9,
        "note": "LAD 12-3, Pages 2-run HR, Skenes chased"
    },
    "Boston Red Sox @ Tampa Bay Rays": {
        "winner": "home",  # TB 4, BOS 3
        "home_score": 4,
        "away_score": 3,
        "margin": 1,
        "note": "TB 4-3, Martinez 7IP 6H"
    },
    "Minnesota Twins @ Detroit Tigers": {
        "winner": "home",  # DET 10, MIN 4
        "home_score": 10,
        "away_score": 4,
        "margin": 6,
        "note": "DET 10-4"
    },
    "Arizona Diamondbacks @ Miami Marlins": {
        "winner": "home",  # MIA 10, ARI 6
        "home_score": 10,
        "away_score": 6,
        "margin": 4,
        "note": "MIA 10-6, Mack 4-for-4"
    },
    "New York Yankees @ Cleveland Guardians": {
        "winner": "away",  # NYY 3, CLE 2
        "home_score": 2,
        "away_score": 3,
        "margin": -1,
        "note": "NYY 3-2"
    },
    "Oakland Athletics @ Milwaukee Brewers": {
        "winner": "away",  # OAK 7, MIL 5 (A's won but listed as away in predictions)
        "home_score": 5,
        "away_score": 7,
        "margin": -2,
        "note": "OAK 7-5, Bolte 1st career HR + 5 more HRs"
    },
    "Atlanta Braves @ Chicago White Sox": {
        "winner": "home",  # CWS 2, ATL 1
        "home_score": 2,
        "away_score": 1,
        "margin": 1,
        "note": "CWS 2-1, Martin 6 scoreless IP"
    },
    "St. Louis Cardinals @ New York Mets": {
        "winner": "away",  # STL 7, NYM 0
        "home_score": 0,
        "away_score": 7,
        "margin": -7,
        "note": "STL 7-0, Burleson HR + 3 RBI"
    },
    "Houston Astros @ Los Angeles Angels": {
        "winner": "home",  # LAA 10, HOU 1
        "home_score": 10,
        "away_score": 1,
        "margin": 9,
        "note": "LAA 10-1, Meckler/Adell 2-run doubles, Urena 5 shutout IP"
    },
    "Chicago Cubs @ Colorado Rockies": {
        "winner": "home",  # COL 7, CHC 3
        "home_score": 7,
        "away_score": 3,
        "margin": 4,
        "note": "COL 7-3, Goodman 2-run HR"
    },
    "Cincinnati Reds @ San Diego Padres": {
        "winner": "away",  # CIN 5, SD 3 (11 inn)
        "home_score": 3,
        "away_score": 5,
        "margin": -2,
        "note": "CIN 5-3 (11 inn), Stewart tiebreaking 2-run HR"
    },
    "Philadelphia Phillies @ Toronto Blue Jays": {
        "winner": "away",  # PHI 7, TOR 4
        "home_score": 4,
        "away_score": 7,
        "margin": -3,
        "note": "PHI 7-4, Bohm 3-run HR, Schwarber/Harper HR"
    },
    "Washington Nationals @ San Francisco Giants": {
        "winner": "away",  # WAS 6, SF 3
        "home_score": 3,
        "away_score": 6,
        "margin": -3,
        "note": "WAS 6-3, Garcia Jr 2-run HR"
    },
    "Texas Rangers @ Kansas City Royals": {
        "winner": "home",  # KC 5, TEX 3
        "home_score": 5,
        "away_score": 3,
        "margin": 2,
        "note": "KC 5-3"
    },
}

# Score each model per game
results_tsv_lines = []
model_correct = {m["id"]: 0 for m in all_models}
model_total = {m["id"]: 0 for m in all_models}
eval_games_played = 0

for pred in eval_preds["predictions"]:
    game_key = pred["game"]
    actual = actual_results.get(game_key)
    if not actual or actual.get("winner") == "postponed":
        print(f"  SKIP: {game_key} — postponed")
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

        line = f"{EVAL_DATE}\t{pred['sport']}\t{game_key}\t{mid}\t{predicted_winner}\t{predicted_margin:.2f}\t{mr['home_win_prob']}\t{actual_winner}\t{actual_margin}\t{hit}\t{best_ev:.4f}\t{evs['ml_home' if predicted_winner=='home' else 'ml_away']:.4f}\t{best_bet}\t{bet_result}"
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
    print(f"  PROMOTION: {promotion['id']} ({model_correct[promotion['id']]}/{model_total[promotion['id']]}) -> champion!")
else:
    print(f"  No promotions. Champion {champ_id} accuracy: {champ_acc:.0%}")

# ── Step 1.6: Explore — retire & replace ──────────────────────────────
print(f"\n  --- Retirement Check ---")
retired = []
for c in challengers:
    if c["weight"] <= 0.15 and c["born"] < "2026-06-06":
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
# PHASE 2-5 — TONIGHT'S PREDICTIONS (June 11, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 90}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 90}")

# Sports in season: NHL (Stanley Cup Finals Game 5), MLB (regular season)
# NBA: off (conference finals done)
# NFL: offseason

# Team stats derived from records via formula: ppg = 4.5 + (win_pct - 0.5) * 3.0
# Updated with latest results through June 10

games_raw = [
    # === NHL Stanley Cup Finals Game 5: Vegas Golden Knights @ Carolina Hurricanes ===
    # Series tied 2-2. G4: CAR 5-3 (Staal 2G). Game 5 at Lenovo Center, Raleigh.
    # CAR -155 / VGK +130. PL: VGK +1.5 (-198). O/U: 6.5
    # Carolina has home-ice advantage, won G1 on road, G4 at VGK.
    # VGK won G2 and G3.
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Carolina Hurricanes",
            "season_ppg": 3.20,
            "season_opp_ppg": 2.70,
            "last10_ppg": 3.50,
            "last10_opp_ppg": 2.80,
            "season_pace": 1.0,
            "home_record_pct": 0.640,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Vegas Golden Knights",
            "season_ppg": 3.30,
            "season_opp_ppg": 2.80,
            "last10_ppg": 3.30,
            "last10_opp_ppg": 3.00,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.530,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -155,
            "ml_away": 130,
            "total": 6.5,
            "book": "fanduel"
        }
    },

    # === MLB Games (8 games) ===

    # 1. St. Louis Cardinals (37-28) @ New York Mets (29-38)
    # STL on 6-game win streak, swept first 2 of this series (7-0, 9-2).
    # NYM -144 / STL +122. RL: NYM -1.5. O/U: 9. Dobbins (1-0, 2.77) vs Scott (2-0, 2.50).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.30,
            "season_opp_ppg": 4.70,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.71,
            "season_opp_ppg": 4.29,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -144,
            "ml_away": 122,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 2. Minnesota Twins (31-38) @ Detroit Tigers (28-40)
    # DET won 10-4 on June 9. DET -124 / MIN +106. RL: DET -1.5. O/U: 9.5.
    # Matthews (2-3, 4.15) vs Montero (2-4, 3.95).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.24,
            "season_opp_ppg": 4.76,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.35,
            "season_opp_ppg": 4.65,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -124,
            "ml_away": 106,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 3. Arizona Diamondbacks (34-33) @ Miami Marlins (33-35)
    # MIA won 10-6 on June 9. MIA -112 / ARI -104. RL: ARI +1.5. O/U: 8.5.
    # Kelly (MIA) vs Phillips (ARI).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Miami Marlins",
            "season_ppg": 4.46,
            "season_opp_ppg": 4.54,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.52,
            "season_opp_ppg": 4.48,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -104,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. Texas Rangers (33-34) @ Kansas City Royals (28-40)
    # KC won 5-3 on June 9, TEX won 6-4 on June 10. KC -122 / TEX +104. O/U: 10.
    # Rocker vs Wacha.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.24,
            "season_opp_ppg": 4.76,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.48,
            "season_opp_ppg": 4.52,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.450,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -122,
            "ml_away": 104,
            "total": 10.0,
            "book": "fanduel"
        }
    },

    # 5. Chicago Cubs (34-34) @ Colorado Rockies (26-42)
    # COL won 7-3 on June 9, COL won 3-2 on June 10. Coors Field.
    # CHC -172 / COL +144. RL: COL +1.5. O/U: 12.
    # Cabrera vs Feltner.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Colorado Rockies",
            "season_ppg": 4.15,
            "season_opp_ppg": 4.85,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.310,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 144,
            "ml_away": -172,
            "total": 12.0,
            "book": "fanduel"
        }
    },

    # 6. Los Angeles Dodgers (44-24) @ Pittsburgh Pirates (35-33)
    # LAD won 12-3 on June 9, PIT won 9-8 on June 10.
    # LAD -166 / PIT +140. RL: LAD -1.5. O/U: 9.5.
    # Wrobleski (7-2) vs Keller (5-3).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.45,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 4.94,
            "season_opp_ppg": 4.06,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.710,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 140,
            "ml_away": -166,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 7. Seattle Mariners (37-32) @ Baltimore Orioles (31-38)
    # SEA won 6-5 on June 9, BAL won 7-2 on June 10.
    # SEA -118 / BAL +100. RL: BAL +1.5. O/U: 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.35,
            "season_opp_ppg": 4.65,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.490,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.61,
            "season_opp_ppg": 4.39,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
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

    # 8. Atlanta Braves (39-28) @ Chicago White Sox (24-43)
    # CWS upset ATL 2-1 on June 9. ATL -118 / CWS -102. RL: ATL -1.5. O/U: 8.5.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 4.07,
            "season_opp_ppg": 4.93,
            "last10_ppg": 3.9,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.390,
            "away_record_pct": 0.290,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.75,
            "season_opp_ppg": 4.25,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.630,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -102,
            "ml_away": -118,
            "total": 8.5,
            "book": "fanduel"
        }
    },
]

# Reload assumptions (was updated by Phase 1)
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# Build sim batch: 9 games × 6 models = 54 simulations
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

print(f"\n  Running {len(batch)} simulations ({len(games_raw)} games × {len(all_models)} models)...")
results = run_batch(batch)
print(f"  Simulations complete.")

# Organize results by game
game_results = {}
idx = 0
for game in games_raw:
    gkey = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[gkey] = {
        "game_data": game,
        "model_results": {},
    }
    for model in all_models:
        game_results[gkey]["model_results"][model["id"]] = results[idx]
        idx += 1

# ── Phase 4: Blend & Classify ─────────────────────────────────────────

predictions = []

for gkey, gdata in game_results.items():
    game = gdata["game_data"]
    mrs = gdata["model_results"]

    # Blended prediction (weighted average)
    total_weight = 0
    blend_home_wp = 0
    blend_margin = 0
    blend_spread_ev_home = 0
    blend_spread_ev_away = 0
    blend_ml_ev_home = 0
    blend_ml_ev_away = 0

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champion["id"] else model.get("weight", 0.5)
        r = mrs[mid]
        blend_home_wp += w * r["home_win_prob"]
        blend_margin += w * r["expected_margin"]
        blend_spread_ev_home += w * r["spread_ev_home"]
        blend_spread_ev_away += w * r["spread_ev_away"]
        blend_ml_ev_home += w * r["ml_ev_home"]
        blend_ml_ev_away += w * r["ml_ev_away"]
        total_weight += w

    blend_home_wp /= total_weight
    blend_away_wp = 1 - blend_home_wp
    blend_margin /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight

    # Best blended bet
    blend_evs = {
        "spread_home": blend_spread_ev_home,
        "spread_away": blend_spread_ev_away,
        "ml_home": blend_ml_ev_home,
        "ml_away": blend_ml_ev_away,
    }
    best_bet_type = max(blend_evs, key=blend_evs.get)
    best_blend_ev = blend_evs[best_bet_type]

    # Per-model best EV for same bet type
    model_evs_for_best = []
    for model in all_models:
        mid = model["id"]
        r = mrs[mid]
        model_ev = {
            "spread_home": r["spread_ev_home"],
            "spread_away": r["spread_ev_away"],
            "ml_home": r["ml_ev_home"],
            "ml_away": r["ml_ev_away"],
        }
        model_evs_for_best.append(model_ev[best_bet_type])

    best_model_ev = max(model_evs_for_best)
    worst_model_ev = min(model_evs_for_best)

    # Robustness: how many models agree on the predicted side
    if "home" in best_bet_type:
        agree_count = sum(1 for m in all_models if mrs[m["id"]]["home_win_prob"] > 0.5)
    else:
        agree_count = sum(1 for m in all_models if mrs[m["id"]]["home_win_prob"] <= 0.5)

    # Classify
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015:
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

    # Kelly criterion (simplified)
    if best_blend_ev > 0 and verdict in ("BET", "LEAN"):
        kelly = min(0.05, best_blend_ev / 2)
    else:
        kelly = 0

    pred = {
        "game": gkey,
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
        "model_results": {
            m["id"]: {
                "home_win_prob": mrs[m["id"]]["home_win_prob"],
                "expected_margin": mrs[m["id"]]["expected_margin"],
                "spread_ev_home": mrs[m["id"]]["spread_ev_home"],
                "spread_ev_away": mrs[m["id"]]["spread_ev_away"],
                "ml_ev_home": mrs[m["id"]]["ml_ev_home"],
                "ml_ev_away": mrs[m["id"]]["ml_ev_away"],
            }
            for m in all_models
        },
    }
    predictions.append(pred)

# ── Save predictions ───────────────────────────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\n  Saved predictions to predictions/{TODAY}.json")

# ── Phase 5: Metrics ──────────────────────────────────────────────────

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update with today's eval
prev_all_time = metrics["all_time"]
new_total_games = prev_all_time["total_games"] + eval_games_played
champ_total_correct = prev_all_time["total_correct"] + model_correct.get(champ_id, 0)

# Count bets recommended today and verdicts
bets_today = sum(1 for p in predictions if p["verdict"] == "BET")
leans_today = sum(1 for p in predictions if p["verdict"] == "LEAN")
no_bets_today = sum(1 for p in predictions if p["verdict"] == "NO BET")

# Update rolling stats
metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(champ_total_correct / new_total_games, 4) if new_total_games > 0 else 0,
    "ev_realized": round(prev_all_time.get("ev_realized", 0.06), 4),
    "total_games": eval_games_played + metrics["rolling_7d"].get("total_games", 0),
    "total_correct": model_correct.get(champ_id, 0) + metrics["rolling_7d"].get("total_correct", 0),
}
metrics["all_time"]["total_games"] = new_total_games
metrics["all_time"]["total_correct"] = champ_total_correct
metrics["all_time"]["accuracy"] = round(champ_total_correct / new_total_games, 4)
metrics["all_time"]["total_bets_recommended"] = prev_all_time.get("total_bets_recommended", 0) + bets_today

# Update variant performance
for m in all_models:
    mid = m["id"]
    metrics["variant_performance"][mid] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": 1.0 if mid == champion["id"] else m.get("weight", 0.5),
        "role": "champion" if mid == champion["id"] else "challenger",
    }

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": bets_today,
    "leans": leans_today,
    "sports": list(set(p["sport"] for p in predictions)),
    "notes": f"NHL SCF G5 (VGK@CAR) + {len(predictions)-1} MLB games. {bets_today} BETs, {leans_today} LEANs, {no_bets_today} NO BETs. Eval: Jun 9 was {model_correct.get(champ_id,0)}/{eval_games_played} correct."
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# ── Display Results ────────────────────────────────────────────────────

print(f"\n{'=' * 90}")
print(f" EDGE-FINDER PREDICTIONS — {TODAY}")
print(f"{'=' * 90}")

# Group by sport
sports = {}
for p in predictions:
    s = p["sport"]
    if s not in sports:
        sports[s] = []
    sports[s].append(p)

sport_labels = {
    "icehockey_nhl": "NHL",
    "baseball_mlb": "MLB",
}

for sport_key, sport_preds in sports.items():
    label = sport_labels.get(sport_key, sport_key)
    print(f"\n┌─────────────────────────────────────────────────────────────────────────────────┐")
    print(f"│ {label} — Thursday Jun 11, 2026{' ' * (55 - len(label))}│")
    print(f"├────────────────────────────┬────────┬────────┬───────┬───────┬──────┬───────────┤")
    print(f"│ Game                       │ Spread │ Blend  │ Best  │ Worst │ Rob. │ Verdict   │")
    print(f"│                            │        │ EV     │ EV    │ EV    │      │           │")
    print(f"├────────────────────────────┼────────┼────────┼───────┼───────┼──────┼───────────┤")

    for p in sport_preds:
        # Shorten game name
        home_short = p["home_team"].split()[-1][:4]
        away_short = p["away_team"].split()[-1][:4]
        spread = p["odds"]["spread_home"]
        spread_str = f"{spread:+.1f}"

        if p["side"] == "HOME":
            game_str = f"{home_short} {spread_str} vs {away_short}"
        else:
            game_str = f"{away_short} {-spread:+.1f} vs {home_short}"

        game_str = game_str[:26].ljust(26)
        blend_ev = f"{p['best_blend_ev']:+.1%}"[:7].ljust(7)
        best_ev = f"{p['best_model_ev']:+.1%}"[:6].ljust(6)
        worst_ev = f"{p['worst_model_ev']:+.1%}"[:6].ljust(6)
        rob = p["robustness"].ljust(4)

        if p["verdict"] == "BET":
            verdict = f"✅ BET {p['side']}"[:10].ljust(9)
        elif p["verdict"] == "LEAN":
            verdict = f"⚠️ LEAN {p['side']}"[:11].ljust(9)
        else:
            verdict = "❌ NO BET".ljust(9)

        print(f"│ {game_str} │ {spread_str:>6} │ {blend_ev} │ {best_ev}│ {worst_ev}│ {rob} │ {verdict} │")

    print(f"└────────────────────────────┴────────┴────────┴───────┴───────┴──────┴───────────┘")

# Detail for BET games
print(f"\n{'─' * 90}")
print(f" BET DETAILS")
print(f"{'─' * 90}")

bet_games = [p for p in predictions if p["verdict"] == "BET"]
if not bet_games:
    print("  No strong BET recommendations today.")
else:
    for p in bet_games:
        print(f"\n  {p['game']}")
        print(f"  Side: {p['side']} ({p['side_team']}) | Market: {p['bet_market']} | Book: {p['odds']['book']}")
        print(f"  Blended EV: {p['best_blend_ev']:+.2%} | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"  Models agreeing: {p['robustness']}")
        for mid, mr in p["model_results"].items():
            wp = mr["home_win_prob"]
            margin = mr["expected_margin"]
            agrees = "✓" if (wp > 0.5 and p["side"] == "HOME") or (wp <= 0.5 and p["side"] == "AWAY") else "✗"
            print(f"    {agrees} {mid:<20} WP={wp:.1%}  margin={margin:+.2f}")

# ── Metrics Dashboard ─────────────────────────────────────────────────

print(f"\n📊 Edge-Finder Metrics")
print(f"━━━━━━━━━━━━━━━━━━━━")
print(f"Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
acc_7d = metrics["rolling_7d"]["accuracy"]
acc_all = metrics["all_time"]["accuracy"]
print(f"7-day:  {metrics['rolling_7d']['total_correct']}/{metrics['rolling_7d']['total_games']} = {acc_7d:.0%} accuracy")
print(f"All-time: {metrics['all_time']['total_correct']}/{metrics['all_time']['total_games']} = {acc_all:.0%} accuracy | {metrics['all_time']['total_bets_recommended']} bets recommended")
print(f"\nChallenger weights: ", end="")
cw = [f"{c['id'].replace('-v1','')}={c['weight']:.1f}" for c in challengers]
print(", ".join(cw))
if assumptions.get("graveyard"):
    grav = [f"{g['id']} (died {g.get('died','?')}, {g.get('lifetime_accuracy',0):.0%})" for g in assumptions["graveyard"]]
    print(f"Graveyard: {', '.join(grav)}")
else:
    print("Graveyard: empty")

print(f"\n⚠️ Disclaimer: For entertainment and analysis purposes only. Past performance does not guarantee future results.")
