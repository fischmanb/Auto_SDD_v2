#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-06-13.
Phase 1: Evaluate 2026-06-11 predictions.
Phase 2-5: Simulate tonight's games (NBA Finals G5 + 15 MLB), produce blended predictions.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(os.path.abspath(__file__))
TODAY = "2026-06-13"
EVAL_DATE = "2026-06-11"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-06-11 PREDICTIONS
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

# Actual results from June 11, 2026 (fetched via web search)
actual_results = {
    "Vegas Golden Knights @ Carolina Hurricanes": {
        "winner": "home",  # CAR 4, VGK 2
        "home_score": 4,
        "away_score": 2,
        "margin": 2,
        "note": "CAR 4-2, Svechnikov/Aho PP goals, CAR takes 3-2 series lead"
    },
    "St. Louis Cardinals @ New York Mets": {
        "winner": "home",  # NYM 5, STL 4
        "home_score": 5,
        "away_score": 4,
        "margin": 1,
        "note": "NYM 5-4, Mets avoid sweep"
    },
    "Minnesota Twins @ Detroit Tigers": {
        "winner": "home",  # DET 11, MIN 0
        "home_score": 11,
        "away_score": 0,
        "margin": 11,
        "note": "DET 11-0 shutout"
    },
    "Arizona Diamondbacks @ Miami Marlins": {
        "winner": "home",  # MIA 2, ARI 0
        "home_score": 2,
        "away_score": 0,
        "margin": 2,
        "note": "MIA 2-0, Marlins win 5th straight, 3-hit shutout"
    },
    "Texas Rangers @ Kansas City Royals": {
        "winner": "away",  # TEX 4, KC 2
        "home_score": 2,
        "away_score": 4,
        "margin": -2,
        "note": "TEX 4-2"
    },
    "Chicago Cubs @ Colorado Rockies": {
        "winner": "away",  # CHC 9, COL 3
        "home_score": 3,
        "away_score": 9,
        "margin": -6,
        "note": "CHC 9-3"
    },
    "Los Angeles Dodgers @ Pittsburgh Pirates": {
        "winner": "away",  # LAD 8, PIT 6
        "home_score": 6,
        "away_score": 8,
        "margin": -2,
        "note": "LAD 8-6"
    },
    "Seattle Mariners @ Baltimore Orioles": {
        "winner": "home",  # BAL 7, SEA 5
        "home_score": 7,
        "away_score": 5,
        "margin": 2,
        "note": "BAL 7-5"
    },
    "Atlanta Braves @ Chicago White Sox": {
        "winner": "postponed",
        "note": "Postponed due to rain, makeup August 20"
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
    disagree_total = outperformed + underperformed
    if disagree_total > 0:
        out_pct = outperformed / disagree_total
        under_pct = underperformed / disagree_total
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
    old_champ = dict(champion)
    champion.update({
        "id": promotion["id"],
        "description": promotion["description"],
        "params": promotion["params"],
        "promoted_on": TODAY,
        "rolling_10d_accuracy": c_acc,
    })
    new_challenger = {
        "id": old_champ["id"],
        "description": old_champ["description"],
        "weight": 0.7,
        "born": old_champ.get("promoted_on", "2026-03-24"),
        "grace_until": "2026-03-29",
        "params": old_champ["params"],
    }
    for i, ch in enumerate(challengers):
        if ch["id"] == promotion["id"]:
            challengers[i] = new_challenger
            break
else:
    print(f"  No promotions. Champion {champ_id} accuracy: {champ_acc:.0%}")

# ── Step 1.6: Explore — retire & replace ──────────────────────────────
print(f"\n  --- Retirement Check ---")
retired = []
for c in challengers:
    if c["weight"] <= 0.15 and c["born"] < "2026-06-08":
        retired.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, born={c['born']})")

if not retired:
    print("  No retirements needed.")

# Update lifetime stats
for m in all_models:
    mid = m["id"]
    m["lifetime_games"] = m.get("lifetime_games", 0) + model_total.get(mid, 0)
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + model_correct.get(mid, 0)

# Save assumptions
assumptions["champion"] = champion
assumptions["challengers"] = challengers
with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

print(f"\n  Updated assumptions.json with eval results.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (June 13, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 90}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f"{'=' * 90}")

# Sports in season:
# NBA: Finals Game 5 — NYK @ SAS (Knicks lead 3-1)
# MLB: Regular season (15 games)
# NHL: Off today (SCF Game 6 is Sunday June 14)
# NFL: Offseason

# Re-read assumptions after eval updates
with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Team stats estimates ──────────────────────────────────────────────
# NBA: Knicks 53-29 reg season, Spurs 62-20 reg season
# Finals so far: G1 NYK 105-95, G2 SAS win, G3 NYK win, G4 NYK 107-106 (29-pt comeback)
# Knicks lead 3-1. Game 5 at San Antonio.
# MLB: Records adjusted through June 12 based on June 11 results + estimated June 12 results.
# Formula for MLB PPG: ppg ≈ 4.5 + (win_pct - 0.5) * 3.0

games_raw = [
    # === NBA Finals Game 5: New York Knicks @ San Antonio Spurs ===
    # Knicks lead series 3-1. Game at Frost Bank Center.
    # SAS -192 / NYK +160. Spread: SAS -5.5. O/U: 216.5
    # Spurs 62-20 reg season (best in NBA), dominant at home ~35-6.
    # Knicks 53-29, strong defense, Brunson 26 PPG.
    # Spurs desperate — elimination game at home.
    {
        "sport": "basketball_nba",
        "home": {
            "name": "San Antonio Spurs",
            "season_ppg": 117.5,
            "season_opp_ppg": 110.2,
            "last10_ppg": 108.0,
            "last10_opp_ppg": 104.5,
            "season_pace": 100.8,
            "home_record_pct": 0.854,
            "away_record_pct": 0.659,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Knicks",
            "season_ppg": 113.2,
            "season_opp_ppg": 107.8,
            "last10_ppg": 107.0,
            "last10_opp_ppg": 101.5,
            "season_pace": 98.5,
            "home_record_pct": 0.732,
            "away_record_pct": 0.561,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -5.5,
            "ml_home": -192,
            "ml_away": 160,
            "total": 216.5,
            "book": "fanduel"
        }
    },

    # === MLB Games (15 games) ===

    # 1. St. Louis Cardinals (~38-29, .567) @ Minnesota Twins (~32-38, .457)
    # STL +100 / MIN -118. RL: MIN -1.5. O/U: 9.0
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Minnesota Twins",
            "season_ppg": 4.37,
            "season_opp_ppg": 4.63,
            "last10_ppg": 4.0,
            "last10_opp_ppg": 5.1,
            "season_pace": 1.0,
            "home_record_pct": 0.470,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Cardinals",
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
            "spread_home": -1.5,
            "ml_home": -118,
            "ml_away": 100,
            "total": 9.0,
            "book": "fanduel"
        }
    },

    # 2. Houston Astros (~37-31, .544) @ Kansas City Royals (~29-41, .414)
    # HOU +108 / KC -126. RL: KC -1.5. O/U: 9.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Kansas City Royals",
            "season_ppg": 4.25,
            "season_opp_ppg": 4.75,
            "last10_ppg": 4.3,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.440,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Houston Astros",
            "season_ppg": 4.63,
            "season_opp_ppg": 4.37,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.570,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -126,
            "ml_away": 108,
            "total": 9.5,
            "book": "fanduel"
        }
    },

    # 3. San Diego Padres (~36-33, .522) @ Baltimore Orioles (~32-38, .457)
    # SD +109 / BAL -131. RL: BAL -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Baltimore Orioles",
            "season_ppg": 4.37,
            "season_opp_ppg": 4.63,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.57,
            "season_opp_ppg": 4.43,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -131,
            "ml_away": 109,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 4. Seattle Mariners (~38-33, .535) @ Washington Nationals (~30-38, .441)
    # SEA -107 / WSH -112. Nearly pick'em. RL: WSH -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Washington Nationals",
            "season_ppg": 4.32,
            "season_opp_ppg": 4.68,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Seattle Mariners",
            "season_ppg": 4.60,
            "season_opp_ppg": 4.40,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -107,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 5. Atlanta Braves (~40-28, .588) @ New York Mets (~31-38, .449)
    # ATL -108 / NYM -112. RL: NYM -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "New York Mets",
            "season_ppg": 4.35,
            "season_opp_ppg": 4.65,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.480,
            "away_record_pct": 0.390,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Atlanta Braves",
            "season_ppg": 4.76,
            "season_opp_ppg": 4.24,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -112,
            "ml_away": -108,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 6. Los Angeles Dodgers (~45-24, .652) @ Chicago White Sox (~24-46, .343)
    # LAD -210 / CHW +170. RL: LAD -1.5 (-122). O/U: 8.0
    # Yamamoto (6-4, 2.68) vs Burke (3-3, 3.88)
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Chicago White Sox",
            "season_ppg": 3.95,
            "season_opp_ppg": 5.05,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 5.2,
            "season_pace": 1.0,
            "home_record_pct": 0.380,
            "away_record_pct": 0.300,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Dodgers",
            "season_ppg": 4.96,
            "season_opp_ppg": 4.04,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.710,
            "away_record_pct": 0.590,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 170,
            "ml_away": -210,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 7. Miami Marlins (~35-35, .500) @ Pittsburgh Pirates (~35-35, .500)
    # MIA +120 / PIT -142. RL: PIT -1.5. O/U: 8.5
    # Chandler vs Bachar
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Pittsburgh Pirates",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Miami Marlins",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 120,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 8. New York Yankees (~38-30, .559) @ Toronto Blue Jays (~33-35, .485)
    # NYY -122 / TOR +104. RL: TOR -1.5 (implied). O/U: 7.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 4.46,
            "season_opp_ppg": 4.54,
            "last10_ppg": 4.4,
            "last10_opp_ppg": 4.6,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.440,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "New York Yankees",
            "season_ppg": 4.68,
            "season_opp_ppg": 4.32,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.590,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 104,
            "ml_away": -122,
            "total": 7.5,
            "book": "fanduel"
        }
    },

    # 9. Philadelphia Phillies (~36-32, .529) @ Milwaukee Brewers (~40-28, .588)
    # PHI +119 / MIL -143. RL: MIL -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Milwaukee Brewers",
            "season_ppg": 4.76,
            "season_opp_ppg": 4.24,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.540,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Philadelphia Phillies",
            "season_ppg": 4.59,
            "season_opp_ppg": 4.41,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.490,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -143,
            "ml_away": 119,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 10. Detroit Tigers (~30-40, .429) @ Cleveland Guardians (~36-32, .529)
    # DET -136 / CLE +113. RL: DET -1.5 (+114). O/U: 7.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.59,
            "season_opp_ppg": 4.41,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.500,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Detroit Tigers",
            "season_ppg": 4.28,
            "season_opp_ppg": 4.72,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.450,
            "away_record_pct": 0.390,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 113,
            "ml_away": -136,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 11. Texas Rangers (~34-34, .500) @ Boston Red Sox (~35-33, .515)
    # TEX +100 / BOS -120. RL: BOS -1.5. O/U: 8.0
    # deGrom (5-4) vs Suarez (2-3)
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Boston Red Sox",
            "season_ppg": 4.55,
            "season_opp_ppg": 4.45,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.540,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Texas Rangers",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.530,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -120,
            "ml_away": 100,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 12. Arizona Diamondbacks (~34-34, .500) @ Cincinnati Reds (~32-36, .471)
    # ARI -142 / CIN +120. RL: ARI -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cincinnati Reds",
            "season_ppg": 4.41,
            "season_opp_ppg": 4.59,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.50,
            "season_opp_ppg": 4.50,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.550,
            "away_record_pct": 0.450,
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

    # 13. Tampa Bay Rays (~40-26, .606) @ Los Angeles Angels (~28-42, .400)
    # TB -116 / LAA ~even. RL: implied. O/U: 8.0
    # Soriano (7-4, 2.96) for LAA vs Jax (1-4, 4.15) for TB
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Los Angeles Angels",
            "season_ppg": 4.20,
            "season_opp_ppg": 4.80,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.420,
            "away_record_pct": 0.370,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.82,
            "season_opp_ppg": 4.18,
            "last10_ppg": 4.7,
            "last10_opp_ppg": 4.3,
            "season_pace": 1.0,
            "home_record_pct": 0.620,
            "away_record_pct": 0.580,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -102,
            "ml_away": -116,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 14. Chicago Cubs (~36-34, .514) @ San Francisco Giants (~30-38, .441)
    # CHC -125 / SF +104. RL: SF +1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "San Francisco Giants",
            "season_ppg": 4.32,
            "season_opp_ppg": 4.68,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 4.7,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Chicago Cubs",
            "season_ppg": 4.54,
            "season_opp_ppg": 4.46,
            "last10_ppg": 4.6,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.480,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 104,
            "ml_away": -125,
            "total": 8.5,
            "book": "fanduel"
        }
    },

    # 15. Colorado Rockies (~26-43, .377) @ Sacramento Athletics (~32-36, .471)
    # COL +144 / OAK -175. RL: OAK -1.5. O/U: 8.5
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Sacramento Athletics",
            "season_ppg": 4.41,
            "season_opp_ppg": 4.59,
            "last10_ppg": 4.5,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Colorado Rockies",
            "season_ppg": 4.13,
            "season_opp_ppg": 4.87,
            "last10_ppg": 4.2,
            "last10_opp_ppg": 5.3,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.310,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -175,
            "ml_away": 144,
            "total": 8.5,
            "book": "fanduel"
        }
    },
]

# ── Build batch for simulation ──────────────────────────────────────────

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

print(f"\n  Running {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

# Run simulations
results = run_batch(batch)

print(f"  Simulations complete.")

# ── Organize results by game ────────────────────────────────────────────

game_results = {}
for i, game in enumerate(games_raw):
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key] = {
        "game_data": game,
        "model_results": {},
    }
    for j, model in enumerate(all_models):
        idx = i * len(all_models) + j
        game_results[game_key]["model_results"][model["id"]] = results[idx]

# ── Phase 4: Blended predictions ────────────────────────────────────────

predictions = []
for game_key, gdata in game_results.items():
    game = gdata["game_data"]
    model_outputs = gdata["model_results"]

    # Compute blended prediction
    total_weight = 0
    blend_home_wp = 0
    blend_margin = 0
    blend_spread_ev_home = 0
    blend_spread_ev_away = 0
    blend_ml_ev_home = 0
    blend_ml_ev_away = 0

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champion["id"] else next(
            (c["weight"] for c in challengers if c["id"] == mid), 0.5
        )
        mr = model_outputs[mid]
        total_weight += w
        blend_home_wp += w * mr["home_win_prob"]
        blend_margin += w * mr["expected_margin"]
        blend_spread_ev_home += w * mr["spread_ev_home"]
        blend_spread_ev_away += w * mr["spread_ev_away"]
        blend_ml_ev_home += w * mr["ml_ev_home"]
        blend_ml_ev_away += w * mr["ml_ev_away"]

    blend_home_wp /= total_weight
    blend_away_wp = 1.0 - blend_home_wp
    blend_margin /= total_weight
    blend_spread_ev_home /= total_weight
    blend_spread_ev_away /= total_weight
    blend_ml_ev_home /= total_weight
    blend_ml_ev_away /= total_weight

    # Best bet type
    evs = {
        "spread_home": blend_spread_ev_home,
        "spread_away": blend_spread_ev_away,
        "ml_home": blend_ml_ev_home,
        "ml_away": blend_ml_ev_away,
    }
    best_bet_type = max(evs, key=evs.get)
    best_blend_ev = evs[best_bet_type]

    # Find best/worst model EVs on the best bet type
    model_evs_on_best = []
    for model in all_models:
        mid = model["id"]
        mr = model_outputs[mid]
        ev_map = {
            "spread_home": mr["spread_ev_home"],
            "spread_away": mr["spread_ev_away"],
            "ml_home": mr["ml_ev_home"],
            "ml_away": mr["ml_ev_away"],
        }
        model_evs_on_best.append(ev_map[best_bet_type])

    best_model_ev = max(model_evs_on_best)
    worst_model_ev = min(model_evs_on_best)

    # Robustness: how many models agree on the SIDE (home or away ML winner)
    if "home" in best_bet_type:
        agree_side = "home"
    else:
        agree_side = "away"

    agree_count = 0
    for model in all_models:
        mid = model["id"]
        mr = model_outputs[mid]
        model_side = "home" if mr["home_win_prob"] > 0.5 else "away"
        if model_side == agree_side:
            agree_count += 1

    robustness = f"{agree_count}/{len(all_models)}"

    # Verdict
    if best_blend_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # If any model flips sign, cap at LEAN
    if worst_model_ev < 0 and verdict == "BET":
        verdict = "LEAN"

    side = "HOME" if "home" in best_bet_type else "AWAY"
    side_team = game["home"]["name"] if side == "HOME" else game["away"]["name"]
    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    # Kelly criterion (simplified)
    if best_blend_ev > 0:
        implied_odds = 0.5  # simplified
        kelly = max(0.01, min(0.05, best_blend_ev / 2))
    else:
        kelly = 0

    pred = {
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
        "robustness": robustness,
        "agree_count": agree_count,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": round(kelly, 4),
        "model_results": {
            model["id"]: {
                "home_win_prob": model_outputs[model["id"]]["home_win_prob"],
                "expected_margin": model_outputs[model["id"]]["expected_margin"],
                "spread_ev_home": model_outputs[model["id"]]["spread_ev_home"],
                "spread_ev_away": model_outputs[model["id"]]["spread_ev_away"],
                "ml_ev_home": model_outputs[model["id"]]["ml_ev_home"],
                "ml_ev_away": model_outputs[model["id"]]["ml_ev_away"],
            }
            for model in all_models
        },
    }
    predictions.append(pred)

# ── Save predictions ────────────────────────────────────────────────────

pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {"date": TODAY, "predictions": predictions}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\n  Saved predictions to {pred_file}")

# ── Phase 5: Metrics dashboard ─────────────────────────────────────────

# Read existing results.tsv to compute rolling metrics
all_results_lines = []
with open(os.path.join(BASE, "results.tsv")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("date"):
            all_results_lines.append(line)

# Parse results for champion
champ_total = 0
champ_correct = 0
champ_7d_total = 0
champ_7d_correct = 0
champ_30d_total = 0
champ_30d_correct = 0
bet_total = 0
bet_won = 0

for line in all_results_lines:
    parts = line.split("\t")
    if len(parts) < 14:
        continue
    d = parts[0]
    model_id = parts[3]
    hit = int(parts[9]) if parts[9].isdigit() else 0
    bet_result = parts[13] if len(parts) > 13 else ""

    if model_id == champion["id"]:
        champ_total += 1
        champ_correct += hit
        if d >= "2026-06-06":
            champ_7d_total += 1
            champ_7d_correct += hit
        if d >= "2026-05-14":
            champ_30d_total += 1
            champ_30d_correct += hit

    if model_id == champion["id"] and bet_result in ("win", "loss"):
        bet_total += 1
        if bet_result == "win":
            bet_won += 1

# Update metrics.json
metrics = {
    "last_updated": TODAY,
    "rolling_7d": {
        "accuracy": round(champ_7d_correct / champ_7d_total, 4) if champ_7d_total > 0 else 0,
        "ev_realized": round((champ_7d_correct / champ_7d_total - 0.5) * 2, 4) if champ_7d_total > 0 else 0,
        "total_games": champ_7d_total,
        "total_correct": champ_7d_correct,
    },
    "rolling_30d": {
        "accuracy": round(champ_30d_correct / champ_30d_total, 4) if champ_30d_total > 0 else 0,
        "ev_realized": round((champ_30d_correct / champ_30d_total - 0.5) * 2, 4) if champ_30d_total > 0 else 0,
        "total_games": champ_30d_total,
        "total_correct": champ_30d_correct,
    },
    "all_time": {
        "accuracy": round(champ_correct / champ_total, 4) if champ_total > 0 else 0,
        "ev_realized": round((champ_correct / champ_total - 0.5) * 2, 4) if champ_total > 0 else 0,
        "total_games": champ_total,
        "total_correct": champ_correct,
        "total_bets_recommended": bet_total,
        "total_bets_won": bet_won,
    },
    "variant_performance": {},
    "champion_history": [
        {"id": "season-avg-v1", "promoted_on": "2026-03-24", "reason": "initial champion"},
    ],
    "today_summary": {
        "date": TODAY,
        "games_analyzed": len(games_raw),
        "bets_recommended": sum(1 for p in predictions if p["verdict"] == "BET"),
        "leans": sum(1 for p in predictions if p["verdict"] == "LEAN"),
        "sports": list(set(g["sport"] for g in games_raw)),
        "notes": "",
    },
}

# Variant performance
for model in all_models:
    mid = model["id"]
    m_total = 0
    m_correct = 0
    for line in all_results_lines:
        parts = line.split("\t")
        if len(parts) >= 10 and parts[3] == mid:
            m_total += 1
            m_correct += int(parts[9]) if parts[9].isdigit() else 0
    metrics["variant_performance"][mid] = {
        "lifetime_games": m_total,
        "lifetime_correct": m_correct,
        "weight": 1.0 if mid == champion["id"] else next(
            (c["weight"] for c in challengers if c["id"] == mid), 0.5
        ),
        "role": "champion" if mid == champion["id"] else "challenger",
    }

bets = [p for p in predictions if p["verdict"] == "BET"]
leans = [p for p in predictions if p["verdict"] == "LEAN"]
nobets = [p for p in predictions if p["verdict"] == "NO BET"]

notes = f"NBA Finals G5 (NYK@SAS) + 15 MLB games. {len(bets)} BETs, {len(leans)} LEANs, {len(nobets)} NO BETs. Eval: Jun 11 was {sum(1 for p in eval_preds['predictions'] if actual_results.get(p['game'], {}).get('winner') != 'postponed')}-game eval."
metrics["today_summary"]["notes"] = notes

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# ── Display results ─────────────────────────────────────────────────────

print(f"\n{'=' * 90}")
print(f" RESULTS — {TODAY}")
print(f"{'=' * 90}")

# Group by sport
from collections import defaultdict
by_sport = defaultdict(list)
for p in predictions:
    by_sport[p["sport"]].append(p)

sport_labels = {
    "basketball_nba": "NBA",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "americanfootball_nfl": "NFL",
}

for sport, preds_list in by_sport.items():
    label = sport_labels.get(sport, sport)
    print(f"\n┌{'─' * 87}┐")
    print(f"│ {label} — Saturday Jun 13, 2026{' ' * (60 - len(label))}│")
    print(f"├{'─' * 20}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 14}┬{'─' * 8}┤")
    print(f"│ {'Game':<18} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │ {'Worst':>5} │ {'Rob.':>4} │ {'Verdict':<12} │ {'Kelly':>6} │")
    print(f"│ {'':18} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │ {'EV':>5} │ {'':>4} │ {'':12} │ {'':>6} │")
    print(f"├{'─' * 20}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 14}┼{'─' * 8}┤")

    for p in preds_list:
        spread = p["odds"]["spread_home"]
        home_short = p["home_team"].split()[-1][:8]
        away_short = p["away_team"].split()[-1][:8]

        if spread < 0:
            game_str = f"{home_short} {spread} v {away_short}"
        else:
            game_str = f"{away_short} {-spread} @ {home_short}"

        verdict_icon = {"BET": "✅ BET", "LEAN": "⚠️  LEAN", "NO BET": "❌ PASS"}
        verdict_str = f"{verdict_icon.get(p['verdict'], p['verdict'])} {p['side']}"

        print(f"│ {game_str:<18} │ {spread:>+6.1f} │ {p['best_blend_ev']:>+5.1%} │ {p['best_model_ev']:>+5.1%} │ {p['worst_model_ev']:>+4.1%} │ {p['robustness']:>4} │ {verdict_str:<12} │ {p['kelly']:>5.1%} │")

    print(f"└{'─' * 20}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 14}┴{'─' * 8}┘")

# Show BET details
if bets:
    print(f"\n{'=' * 90}")
    print(f" BET DETAILS")
    print(f"{'=' * 90}")
    for p in bets:
        print(f"\n  🎯 {p['game']}")
        print(f"     Side: {p['side']} ({p['side_team']}) via {p['bet_market']}")
        print(f"     Blended EV: {p['best_blend_ev']:+.1%} | Best model EV: {p['best_model_ev']:+.1%} | Worst: {p['worst_model_ev']:+.1%}")
        print(f"     Robustness: {p['robustness']} models agree")
        print(f"     Kelly: {p['kelly']:.1%} of bankroll")
        print(f"     Book: {p['odds']['book']} | Spread: {p['odds']['spread_home']:+.1f} | ML: {p['odds']['ml_home']}/{p['odds']['ml_away']}")
        print(f"     Model breakdown:")
        for mid, mr in p["model_results"].items():
            side = "HOME" if mr["home_win_prob"] > 0.5 else "AWAY"
            print(f"       {mid:<20} WP={mr['home_win_prob']:.1%} home | margin={mr['expected_margin']:+.2f} | best EV={max(mr['spread_ev_home'], mr['spread_ev_away'], mr['ml_ev_home'], mr['ml_ev_away']):+.4f} → {side}")

# Print metrics summary
print(f"\n{'=' * 90}")
print(f" 📊 Edge-Finder Metrics")
print(f"{'━' * 40}")
print(f" Champion: {champion['id']} (promoted {champion.get('promoted_on', 'N/A')})")
acc_7d = metrics["rolling_7d"]["accuracy"]
ev_7d = metrics["rolling_7d"]["ev_realized"]
games_7d = metrics["rolling_7d"]["total_games"]
acc_30d = metrics["rolling_30d"]["accuracy"]
ev_30d = metrics["rolling_30d"]["ev_realized"]
games_30d = metrics["rolling_30d"]["total_games"]
print(f" 7-day:  {acc_7d:.0%} accuracy | {ev_7d:+.1%} realized EV | {games_7d} games")
print(f" 30-day: {acc_30d:.0%} accuracy | {ev_30d:+.1%} realized EV | {games_30d} games")
chall_str = ", ".join(f"{c['id']}={c['weight']:.1f}" for c in challengers)
print(f" Challenger weights: {chall_str}")
if assumptions.get("graveyard"):
    grave_str = ", ".join(f"{g['id']} (died {g.get('died', '?')}, {g.get('lifetime_accuracy', '?'):.0%})" for g in assumptions["graveyard"])
    print(f" Graveyard: {grave_str}")
else:
    print(f" Graveyard: empty")

print(f"\n ⚠️  This is for entertainment and analysis purposes only.")
print(f"    Past performance does not guarantee future results.")
print(f"{'=' * 90}")
