#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-11-05 (Thursday).
Phase 1: Eval Nov 4 (14 NBA + 4 NHL = 18 games)
Phase 2-5: Simulate tonight's games:
  - 2 NBA (ORL@PHX, MIA@GSW)
  - 11 NHL
  = 13 games total.

Nov 4 results summary:
  NBA (14 games): 5 upsets vs the line
    PHI 112 DET 106 — Sixers survive on road
    ATL 120 WAS 105 — Hawks cruise in DC
    BOS 109 MIL 102 — George 25, White 24 lead Celtics
    BKN 114 CHA 104 — UPSET: Nets rally past Hornets (CHA was favored)
    NYK 135 CHI 105 — Brunson 33, Knicks demolish Bulls
    NOP 120 UTA 113 OT — Pelicans survive in OT
    OKC 124 CLE 116 — SGA 42 pts, Thunder hold off Cavs
    IND 121 MEM 118 — UPSET: Pacers outrun Grizzlies on road (MEM -4)
    MIN 117 HOU 107 — UPSET: Wolves stun Rockets in Houston
    DEN 128 TOR 109 — Jokic triple-double (32/11/10)
    POR 132 PHX 119 — UPSET: Blazers shock Suns in Phoenix
    SAS 112 DAL 111 — Wemby 52 pts, Spurs survive by 1
    LAL 116 SAC 103 — Doncic 40, Lakers cruise
    MIA 117 LAC 116 OT — UPSET: Thompson game-winning 3, Bam 35

  NHL (4 games):
    OTT 2 BUF 1 — Amadio late winner
    FLA 5 CHI 3 — Vilmanis 2G 2A
    LAK 7 SJS 2 — Kempe hat trick
    SEA 2 CGY 1 OT — Kraken win in extras
"""

import json
import os
import sys
import csv
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-11-05"
YESTERDAY = "2026-11-04"

MODEL_ORDER = ["recency-v1", "regression-v1", "combo-balanced-v1",
               "injury-rest-v1", "pace-adj-v1", "season-avg-v1"]

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVAL NOVEMBER 4, 2026
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {YESTERDAY}")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

with open(os.path.join(BASE, f"predictions/{YESTERDAY}.json")) as f:
    yesterday_preds = json.load(f)

actual_results = [
    # NBA — 14 games from Nov 4
    {"home": "Detroit Pistons", "away": "Philadelphia 76ers",
     "home_score": 106, "away_score": 112, "winner": "away", "sport": "basketball_nba"},
    {"home": "Washington Wizards", "away": "Atlanta Hawks",
     "home_score": 105, "away_score": 120, "winner": "away", "sport": "basketball_nba"},
    {"home": "Boston Celtics", "away": "Milwaukee Bucks",
     "home_score": 109, "away_score": 102, "winner": "home", "sport": "basketball_nba"},
    {"home": "Brooklyn Nets", "away": "Charlotte Hornets",
     "home_score": 114, "away_score": 104, "winner": "home", "sport": "basketball_nba"},
    {"home": "New York Knicks", "away": "Chicago Bulls",
     "home_score": 135, "away_score": 105, "winner": "home", "sport": "basketball_nba"},
    {"home": "New Orleans Pelicans", "away": "Utah Jazz",
     "home_score": 120, "away_score": 113, "winner": "home", "sport": "basketball_nba"},
    {"home": "Oklahoma City Thunder", "away": "Cleveland Cavaliers",
     "home_score": 124, "away_score": 116, "winner": "home", "sport": "basketball_nba"},
    {"home": "Memphis Grizzlies", "away": "Indiana Pacers",
     "home_score": 118, "away_score": 121, "winner": "away", "sport": "basketball_nba"},
    {"home": "Houston Rockets", "away": "Minnesota Timberwolves",
     "home_score": 107, "away_score": 117, "winner": "away", "sport": "basketball_nba"},
    {"home": "Denver Nuggets", "away": "Toronto Raptors",
     "home_score": 128, "away_score": 109, "winner": "home", "sport": "basketball_nba"},
    {"home": "Phoenix Suns", "away": "Portland Trail Blazers",
     "home_score": 119, "away_score": 132, "winner": "away", "sport": "basketball_nba"},
    {"home": "San Antonio Spurs", "away": "Dallas Mavericks",
     "home_score": 112, "away_score": 111, "winner": "home", "sport": "basketball_nba"},
    {"home": "Sacramento Kings", "away": "Los Angeles Lakers",
     "home_score": 103, "away_score": 116, "winner": "away", "sport": "basketball_nba"},
    {"home": "Los Angeles Clippers", "away": "Miami Heat",
     "home_score": 116, "away_score": 117, "winner": "away", "sport": "basketball_nba"},
    # NHL — 4 games from Nov 4
    {"home": "Buffalo Sabres", "away": "Ottawa Senators",
     "home_score": 1, "away_score": 2, "winner": "away", "sport": "icehockey_nhl"},
    {"home": "Florida Panthers", "away": "Chicago Blackhawks",
     "home_score": 5, "away_score": 3, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Los Angeles Kings", "away": "San Jose Sharks",
     "home_score": 7, "away_score": 2, "winner": "home", "sport": "icehockey_nhl"},
    {"home": "Seattle Kraken", "away": "Calgary Flames",
     "home_score": 2, "away_score": 1, "winner": "home", "sport": "icehockey_nhl"},
]

model_correct = {m: 0 for m in MODEL_ORDER}
model_total = {m: 0 for m in MODEL_ORDER}
total_correct_blended = 0
total_games = len(actual_results)

results_lines = []

for result in actual_results:
    pred_game = None
    for g in yesterday_preds["games"]:
        if g["home"] == result["home"]:
            pred_game = g
            break

    if pred_game is None:
        print(f"  WARNING: No prediction found for {result['home']} vs {result['away']}")
        continue

    actual_winner = result["winner"]
    actual_margin = result["home_score"] - result["away_score"]

    blended_home_prob = pred_game["blended"]["home_win_prob"]
    blended_pred = "home" if blended_home_prob > 0.5 else "away"
    blended_hit = blended_pred == actual_winner
    if blended_hit:
        total_correct_blended += 1

    line_parts = [
        YESTERDAY,
        pred_game["sport"],
        f"{result['home']} vs {result['away']}",
        actual_winner,
        str(result["home_score"]),
        str(result["away_score"]),
    ]

    for model_id in MODEL_ORDER:
        mp = pred_game["model_predictions"][model_id]
        model_home_prob = mp["home_win_prob"]
        model_pred = "home" if model_home_prob > 0.5 else "away"
        hit = model_pred == actual_winner
        model_correct[model_id] += 1 if hit else 0
        model_total[model_id] += 1
        line_parts.append(str(hit))
        line_parts.append(f"{model_home_prob:.4f}")

    results_lines.append("\t".join(line_parts))

blended_acc = total_correct_blended / total_games if total_games > 0 else 0
print(f"\n  Nov 4 eval: {total_correct_blended}/{total_games} ML correct ({blended_acc:.1%})")
print(f"  Per-model breakdown:")
for m in MODEL_ORDER:
    acc = model_correct[m] / model_total[m] if model_total[m] > 0 else 0
    role = "CHAMP" if m == assumptions["champion"]["id"] else "chall"
    print(f"    {m} ({role}): {model_correct[m]}/{model_total[m]} ({acc:.1%})")

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in results_lines:
        f.write(line + "\n")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.4 — UPDATE CHALLENGER WEIGHTS
# ═══════════════════════════════════════════════════════════════════════

champion_id = assumptions["champion"]["id"]
champion_correct_count = model_correct[champion_id]
champion_total_count = model_total[champion_id]

print(f"\n  Weight updates (champion {champion_id}: {champion_correct_count}/{champion_total_count}):")

for challenger in assumptions["challengers"]:
    cid = challenger["id"]
    c_correct = model_correct[cid]
    c_total = model_total[cid]

    disagree_games = 0
    challenger_wins_disagree = 0

    for result in actual_results:
        pred_game = None
        for g in yesterday_preds["games"]:
            if g["home"] == result["home"]:
                pred_game = g
                break
        if pred_game is None:
            continue

        actual_winner = result["winner"]
        champ_pred = "home" if pred_game["model_predictions"][champion_id]["home_win_prob"] > 0.5 else "away"
        chall_pred = "home" if pred_game["model_predictions"][cid]["home_win_prob"] > 0.5 else "away"

        if champ_pred != chall_pred:
            disagree_games += 1
            if chall_pred == actual_winner:
                challenger_wins_disagree += 1

    old_weight = challenger["weight"]
    if c_correct > champion_correct_count and disagree_games > 0:
        pct = challenger_wins_disagree / disagree_games
        if pct >= 0.6:
            challenger["weight"] = min(1.0, challenger["weight"] + 0.1)
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (+0.1, outperformed on {pct:.0%} of {disagree_games} disagreements)")
        else:
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (no change, {disagree_games} disagreements)")
    elif c_correct < champion_correct_count and disagree_games > 0:
        pct = (disagree_games - challenger_wins_disagree) / disagree_games
        if pct >= 0.6:
            challenger["weight"] = max(0.1, challenger["weight"] - 0.1)
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (-0.1, underperformed on {pct:.0%} of {disagree_games} disagreements)")
        else:
            print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (no change, {disagree_games} disagreements)")
    else:
        print(f"    {cid}: {old_weight:.1f} -> {challenger['weight']:.1f} (no change, {disagree_games} disagreements)")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.5 — UPDATE LIFETIME STATS AND ROLLING ACCURACY
# ═══════════════════════════════════════════════════════════════════════

for model_id in MODEL_ORDER:
    if model_id == assumptions["champion"]["id"]:
        assumptions["champion"]["lifetime_games"] += model_total[model_id]
        assumptions["champion"]["lifetime_correct"] += model_correct[model_id]
    else:
        for c in assumptions["challengers"]:
            if c["id"] == model_id:
                c["lifetime_games"] += model_total[model_id]
                c["lifetime_correct"] += model_correct[model_id]
                break

cutoff_date = (datetime(2026, 11, 5) - timedelta(days=10)).strftime("%Y-%m-%d")
model_10d_correct = defaultdict(int)
model_10d_total = defaultdict(int)

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]
        if row_date < cutoff_date:
            continue
        if len(row) == 18:
            col = 6
            for mid in MODEL_ORDER:
                if col < len(row):
                    hit = row[col] == "True"
                    model_10d_correct[mid] += 1 if hit else 0
                    model_10d_total[mid] += 1
                    col += 2
        elif len(row) == 14:
            mid = row[3]
            if mid in MODEL_ORDER:
                hit = row[9] == "1" or row[9].lower() == "true"
                model_10d_correct[mid] += 1 if hit else 0
                model_10d_total[mid] += 1

print(f"\n  Rolling 10d accuracy (since {cutoff_date}):")
for mid in MODEL_ORDER:
    total = model_10d_total[mid]
    correct = model_10d_correct[mid]
    acc = correct / total if total > 0 else 0
    print(f"    {mid}: {correct}/{total} ({acc:.1%})")
    if mid == assumptions["champion"]["id"]:
        assumptions["champion"]["rolling_10d_accuracy"] = round(acc, 4)
    else:
        for c in assumptions["challengers"]:
            if c["id"] == mid:
                c["rolling_10d_accuracy"] = round(acc, 4)
                break

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.5b — PROMOTION CHECK
# ═══════════════════════════════════════════════════════════════════════

champion_10d = assumptions["champion"]["rolling_10d_accuracy"]
promotion_happened = False
promoted_id = None

for c in assumptions["challengers"]:
    if c["rolling_10d_accuracy"] - champion_10d >= 0.05:
        print(f"\n  ** PROMOTION: {c['id']} ({c['rolling_10d_accuracy']:.1%}) exceeds champion "
              f"{assumptions['champion']['id']} ({champion_10d:.1%}) by "
              f"{c['rolling_10d_accuracy'] - champion_10d:.1%} **")
        old_champ = dict(assumptions["champion"])
        old_champ["weight"] = 0.7
        old_champ["demoted_on"] = TODAY
        if "promoted_on" in old_champ:
            del old_champ["promoted_on"]

        new_champ = dict(c)
        new_champ["weight"] = 1.0
        new_champ["promoted_on"] = TODAY

        assumptions["champion"] = new_champ
        remaining = [ch for ch in assumptions["challengers"] if ch["id"] != c["id"]]
        remaining.append(old_champ)
        assumptions["challengers"] = remaining

        metrics["champion_history"].append({
            "id": new_champ["id"],
            "promoted_on": TODAY,
            "reason": f"Rolling 10d accuracy {new_champ['rolling_10d_accuracy']:.1%} exceeded "
                      f"{old_champ['id']}'s {champion_10d:.1%} by "
                      f"{new_champ['rolling_10d_accuracy'] - champion_10d:.1%}"
        })
        promotion_happened = True
        promoted_id = new_champ["id"]
        break

if not promotion_happened:
    print(f"\n  No promotion. Champion {assumptions['champion']['id']} holds ({champion_10d:.1%} rolling 10d)")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 1.6 — EXPLORE: RETIRE & REPLACE CHECK
# ═══════════════════════════════════════════════════════════════════════

grace_cutoff = (datetime(2026, 11, 5) - timedelta(days=5)).strftime("%Y-%m-%d")
retired = []
for c in assumptions["challengers"]:
    if c["weight"] <= 0.15 and c.get("born", "2026-01-01") < grace_cutoff:
        lifetime_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
        retired.append({
            "id": c["id"],
            "description": c["description"],
            "final_weight": c["weight"],
            "lifetime_accuracy": round(lifetime_acc, 4),
            "lifetime_games": c["lifetime_games"],
            "lifetime_correct": c["lifetime_correct"],
            "born": c["born"],
            "died": TODAY,
            "reason": f"Weight dropped to {c['weight']:.2f} after persistent underperformance vs champion."
        })
        print(f"\n  RETIRED: {c['id']} (weight={c['weight']:.2f}, accuracy={lifetime_acc:.1%})")

for r in retired:
    assumptions["graveyard"].append(r)
    assumptions["challengers"] = [c for c in assumptions["challengers"] if c["id"] != r["id"]]

if not retired:
    print(f"\n  No retirements. Lowest weight: {min(c['weight'] for c in assumptions['challengers']):.2f}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION FOR NOVEMBER 5, 2026
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Data collection for {TODAY}")
print("=" * 78)

# Tonight's games: 2 NBA + 11 NHL = 13 games
# Odds sourced from FanDuel, DraftKings, BetMGM, Yahoo, Bleacher Nation, CBS Sports
# Team stats estimated from season averages through Nov 4

games_data = []

# ── NBA Games ──────────────────────────────────────────────────────────
nba_games = [
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Phoenix Suns", "season_ppg": 114.8, "season_opp_ppg": 113.2,
            "last10_ppg": 114.8, "last10_opp_ppg": 113.2,
            "season_pace": 100.6, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Orlando Magic", "season_ppg": 108.5, "season_opp_ppg": 105.8,
            "last10_ppg": 108.5, "last10_opp_ppg": 105.8,
            "season_pace": 98.4, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {
            "spread_home": -2.5, "ml_home": -130, "ml_away": 110,
            "total": 224.5, "book": "CBS/FanDuel"
        }
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Golden State Warriors", "season_ppg": 117.2, "season_opp_ppg": 110.1,
            "last10_ppg": 119.5, "last10_opp_ppg": 109.3,
            "season_pace": 101.1, "home_record_pct": 0.80, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Miami Heat", "season_ppg": 112.4, "season_opp_ppg": 110.8,
            "last10_ppg": 113.6, "last10_opp_ppg": 111.2,
            "season_pace": 99.5, "home_record_pct": 0.60, "away_record_pct": 0.40,
            "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {
            "spread_home": -4.5, "ml_home": -190, "ml_away": 158,
            "total": 236.5, "book": "CBS/FanDuel"
        }
    },
]

# ── NHL Games ──────────────────────────────────────────────────────────
nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Montreal Canadiens", "season_ppg": 2.9, "season_opp_ppg": 3.2,
            "last10_ppg": 2.8, "last10_opp_ppg": 3.3,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Utah Hockey Club", "season_ppg": 2.7, "season_opp_ppg": 3.0,
            "last10_ppg": 2.6, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -125, "ml_away": 105,
            "total": 6.0, "book": "estimated"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Detroit Red Wings", "season_ppg": 3.0, "season_opp_ppg": 3.1,
            "last10_ppg": 2.9, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Vegas Golden Knights", "season_ppg": 3.4, "season_opp_ppg": 2.6,
            "last10_ppg": 3.5, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.57,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 140, "ml_away": -165,
            "total": 6.0, "book": "estimated"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Tampa Bay Lightning", "season_ppg": 3.5, "season_opp_ppg": 2.7,
            "last10_ppg": 3.6, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.71, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Chicago Blackhawks", "season_ppg": 2.4, "season_opp_ppg": 3.5,
            "last10_ppg": 2.3, "last10_opp_ppg": 3.6,
            "season_pace": 1.0, "home_record_pct": 0.25, "away_record_pct": 0.17,
            "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -310, "ml_away": 250,
            "total": 6.5, "book": "BetMGM"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "New Jersey Devils", "season_ppg": 3.3, "season_opp_ppg": 2.5,
            "last10_ppg": 3.4, "last10_opp_ppg": 2.4,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "St. Louis Blues", "season_ppg": 2.6, "season_opp_ppg": 3.1,
            "last10_ppg": 2.5, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.29,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -204, "ml_away": 166,
            "total": 5.5, "book": "BleacherNation"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "New York Islanders", "season_ppg": 2.6, "season_opp_ppg": 2.8,
            "last10_ppg": 2.5, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Carolina Hurricanes", "season_ppg": 3.2, "season_opp_ppg": 2.4,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.3,
            "season_pace": 1.0, "home_record_pct": 0.71, "away_record_pct": 0.57,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 146, "ml_away": -178,
            "total": 5.5, "book": "Yahoo"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "New York Rangers", "season_ppg": 2.8, "season_opp_ppg": 2.7,
            "last10_ppg": 2.9, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.43,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Philadelphia Flyers", "season_ppg": 2.7, "season_opp_ppg": 3.0,
            "last10_ppg": 2.6, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -150, "ml_away": 126,
            "total": 5.5, "book": "estimated"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Pittsburgh Penguins", "season_ppg": 2.8, "season_opp_ppg": 3.2,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.3,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.29,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Boston Bruins", "season_ppg": 2.9, "season_opp_ppg": 2.8,
            "last10_ppg": 3.0, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.57, "away_record_pct": 0.43,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": -112, "ml_away": -108,
            "total": 6.5, "book": "DraftKings"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Columbus Blue Jackets", "season_ppg": 3.1, "season_opp_ppg": 3.0,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Dallas Stars", "season_ppg": 3.1, "season_opp_ppg": 2.7,
            "last10_ppg": 3.2, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.57, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 112, "ml_away": -134,
            "total": 5.5, "book": "Yahoo"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Winnipeg Jets", "season_ppg": 3.6, "season_opp_ppg": 2.5,
            "last10_ppg": 3.5, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.71, "away_record_pct": 0.57,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Vancouver Canucks", "season_ppg": 2.8, "season_opp_ppg": 3.0,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -201, "ml_away": 179,
            "total": 6.5, "book": "Covers"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Edmonton Oilers", "season_ppg": 3.3, "season_opp_ppg": 3.0,
            "last10_ppg": 3.2, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.57, "away_record_pct": 0.43,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Anaheim Ducks", "season_ppg": 2.8, "season_opp_ppg": 3.1,
            "last10_ppg": 2.9, "last10_opp_ppg": 3.0,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -190, "ml_away": 154,
            "total": 6.5, "book": "FanDuel"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Colorado Avalanche", "season_ppg": 3.2, "season_opp_ppg": 3.1,
            "last10_ppg": 3.0, "last10_opp_ppg": 3.3,
            "season_pace": 1.0, "home_record_pct": 0.57, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Nashville Predators", "season_ppg": 2.7, "season_opp_ppg": 3.0,
            "last10_ppg": 2.8, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.43, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -165, "ml_away": 140,
            "total": 6.0, "book": "estimated"
        }
    },
]

all_games = nba_games + nhl_games
print(f"\n  Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL = {len(all_games)} games")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (CHAMPION + 5 CHALLENGERS)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 3 — Running simulations")
print("=" * 78)

all_models = [assumptions["champion"]] + assumptions["challengers"]
model_params = {m["id"]: m["params"] for m in all_models}

batch = []
for game in all_games:
    for mid, params in model_params.items():
        batch.append({
            "sport": game["sport"],
            "model_id": mid,
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": params,
            "n_sims": 50000,
        })

print(f"  Running {len(batch)} simulations ({len(all_games)} games x {len(model_params)} models)...")

batch_file = "/tmp/claude-0/-home-user-Auto-SDD-v2/04b5ea00-eb78-565a-a701-88348e20943e/scratchpad/edge_finder_batch.json"
os.makedirs(os.path.dirname(batch_file), exist_ok=True)
with open(batch_file, "w") as f:
    json.dump(batch, f)

sim_results = run_batch(batch)
print(f"  Completed {len(sim_results)} simulations.")

# Organize results by game
game_results = {}
for i, sr in enumerate(sim_results):
    game_idx = i // len(model_params)
    mid = sr["model_id"]
    if game_idx not in game_results:
        game_results[game_idx] = {}
    game_results[game_idx][mid] = sr

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 4 — Blended predictions")
print("=" * 78)

model_weights = {}
model_weights[assumptions["champion"]["id"]] = 1.0
for c in assumptions["challengers"]:
    model_weights[c["id"]] = c["weight"]

predictions = {"date": TODAY, "sports": [], "context": "", "note": "", "games": []}
sports_seen = set()

for game_idx, game in enumerate(all_games):
    gr = game_results[game_idx]

    total_weight = sum(model_weights.values())
    blended_home_prob = sum(gr[mid]["home_win_prob"] * model_weights[mid] for mid in model_weights) / total_weight
    blended_away_prob = 1.0 - blended_home_prob
    blended_margin = sum(gr[mid]["expected_margin"] * model_weights[mid] for mid in model_weights) / total_weight

    evs = {}
    for mid in model_weights:
        best_ev_mid = max(gr[mid]["ml_ev_home"], gr[mid]["ml_ev_away"],
                          gr[mid]["spread_ev_home"], gr[mid]["spread_ev_away"])
        evs[mid] = best_ev_mid

    blended_ev = sum(evs[mid] * model_weights[mid] for mid in model_weights) / total_weight
    best_model_ev = max(evs.values())
    worst_model_ev = min(evs.values())

    home_wins = sum(1 for mid in model_weights if gr[mid]["home_win_prob"] > 0.5)
    away_wins = len(model_weights) - home_wins
    robustness = max(home_wins, away_wins)

    side = "home" if blended_home_prob > 0.5 else "away"
    best_bet_key = None
    best_blended_ev = -999
    for bet_type in ["ml_ev_home", "ml_ev_away", "spread_ev_home", "spread_ev_away"]:
        bev = sum(gr[mid][bet_type] * model_weights[mid] for mid in model_weights) / total_weight
        if bev > best_blended_ev:
            best_blended_ev = bev
            best_bet_key = bet_type

    if best_blended_ev > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_blended_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    kelly = max(0, best_blended_ev / (best_model_ev if best_model_ev > 0 else 1))
    kelly_half = round(kelly / 2, 3)

    model_preds = {}
    for mid in MODEL_ORDER:
        model_preds[mid] = {
            "home_win_prob": gr[mid]["home_win_prob"],
            "ml_ev_home": gr[mid]["ml_ev_home"],
            "ml_ev_away": gr[mid]["ml_ev_away"],
            "spread_ev_home": gr[mid]["spread_ev_home"],
            "spread_ev_away": gr[mid]["spread_ev_away"],
            "expected_margin": gr[mid]["expected_margin"],
        }

    game_pred = {
        "sport": game["sport"],
        "home": game["home"]["name"],
        "away": game["away"]["name"],
        "odds": game["odds"],
        "blended": {
            "home_win_prob": round(blended_home_prob, 4),
            "away_win_prob": round(blended_away_prob, 4),
            "expected_margin": round(blended_margin, 2),
            "best_ev": round(best_blended_ev, 4),
            "best_bet": best_bet_key,
            "robustness": robustness,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": model_preds,
    }

    predictions["games"].append(game_pred)
    sports_seen.add(game["sport"])

predictions["sports"] = sorted(sports_seen)
predictions["context"] = (
    f"Thursday Nov 5: {len(nba_games)} NBA + {len(nhl_games)} NHL = {len(all_games)} games. "
    f"Champion: {assumptions['champion']['id']}. "
    f"Nov 4 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
    f"Light NBA slate (2 games). Heavy NHL night (11 games)."
)
predictions["note"] = "Odds sourced from FanDuel, DraftKings, BetMGM, Yahoo, BleacherNation, CBS Sports, Covers. Some lines estimated."

# Save predictions BEFORE displaying
pred_file = os.path.join(BASE, f"predictions/{TODAY}.json")
with open(pred_file, "w") as f:
    json.dump(predictions, f, indent=2)
print(f"\n  Saved predictions to {pred_file}")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 4.4 — DISPLAY RESULTS
# ═══════════════════════════════════════════════════════════════════════

for sport in sorted(sports_seen):
    sport_label = {"basketball_nba": "NBA", "icehockey_nhl": "NHL"}.get(sport, sport)
    sport_games = [g for g in predictions["games"] if g["sport"] == sport]

    print(f"\n{'┌' + '─' * 89 + '┐'}")
    print(f"│ {sport_label} — Thursday Nov 5, 2026{' ' * (89 - len(sport_label) - 28)}│")
    print(f"├{'─' * 24}┬{'─' * 8}┬{'─' * 9}┬{'─' * 9}┬{'─' * 9}┬{'─' * 6}┬{'─' * 20}┤")
    print(f"│ {'Game':<22} │ {'Spread':>6} │ {'Blend':>7} │ {'Best':>7} │ {'Worst':>7} │ {'Rob.':>4} │ {'Verdict':<18} │")
    print(f"│ {'':<22} │ {'':>6} │ {'EV':>7} │ {'EV':>7} │ {'EV':>7} │ {'':>4} │ {'':>18} │")
    print(f"├{'─' * 24}┼{'─' * 8}┼{'─' * 9}┼{'─' * 9}┼{'─' * 9}┼{'─' * 6}┼{'─' * 20}┤")

    for g in sport_games:
        spread = g["odds"]["spread_home"]
        home_abbr = g["home"][:3].upper()
        away_abbr = g["away"][:3].upper()

        if spread < 0:
            matchup = f"{home_abbr} {spread} vs {away_abbr}"
        else:
            matchup = f"{away_abbr} {-spread} @ {home_abbr}"

        if len(matchup) > 22:
            matchup = matchup[:22]

        ev = g["blended"]["best_ev"]
        best = g["blended"]["best_model_ev"]
        worst = g["blended"]["worst_model_ev"]
        rob = g["blended"]["robustness"]

        if g["blended"]["verdict"] == "BET":
            side = "HOME" if g["blended"]["home_win_prob"] > 0.5 else "AWAY"
            verdict_str = f"BET {side}"
        elif g["blended"]["verdict"] == "LEAN":
            side = "HOME" if g["blended"]["home_win_prob"] > 0.5 else "AWAY"
            verdict_str = f"LEAN {side}"
        else:
            verdict_str = "NO BET"

        print(f"│ {matchup:<22} │ {spread:>+6.1f} │ {ev:>+6.1%} │ {best:>+6.1%} │ {worst:>+6.1%} │ {rob:>2}/6 │ {verdict_str:<18} │")

    print(f"└{'─' * 24}┴{'─' * 8}┴{'─' * 9}┴{'─' * 9}┴{'─' * 9}┴{'─' * 6}┴{'─' * 20}┘")

# Print BET details
bet_games = [g for g in predictions["games"] if g["blended"]["verdict"] == "BET"]
if bet_games:
    print(f"\n  BET Details ({len(bet_games)} recommended):")
    for g in bet_games:
        side = "HOME" if g["blended"]["home_win_prob"] > 0.5 else "AWAY"
        team = g["home"] if side == "HOME" else g["away"]
        print(f"\n    {team} ({side}) vs {g['away'] if side == 'HOME' else g['home']}")
        print(f"      Book: {g['odds']['book']} | Spread: {g['odds']['spread_home']:+.1f} | ML: {g['odds']['ml_home']}/{g['odds']['ml_away']}")
        print(f"      Blended EV: {g['blended']['best_ev']:+.1%} | Win prob: {g['blended']['home_win_prob' if side == 'HOME' else 'away_win_prob']:.1%}")
        print(f"      Kelly half: {g['blended']['kelly_half']:.1%} of bankroll")
        agree = sum(1 for mid in MODEL_ORDER if
                    (g["model_predictions"][mid]["home_win_prob"] > 0.5) == (side == "HOME"))
        print(f"      Models: {agree}/6 agree on {side}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

# Update rolling 7d and 30d
r7_cutoff = (datetime(2026, 11, 5) - timedelta(days=7)).strftime("%Y-%m-%d")
r30_cutoff = (datetime(2026, 11, 5) - timedelta(days=30)).strftime("%Y-%m-%d")

r7_correct = 0
r7_total = 0
r30_correct = 0
r30_total = 0
all_correct = 0
all_total = 0

with open(os.path.join(BASE, "results.tsv")) as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    for row in reader:
        if len(row) < 7:
            continue
        row_date = row[0]
        champ_id_for_row = assumptions["champion"]["id"]

        if len(row) == 18:
            champ_idx = MODEL_ORDER.index(champ_id_for_row)
            col = 6 + champ_idx * 2
            if col < len(row):
                hit = row[col] == "True"
                all_total += 1
                all_correct += 1 if hit else 0
                if row_date >= r7_cutoff:
                    r7_total += 1
                    r7_correct += 1 if hit else 0
                if row_date >= r30_cutoff:
                    r30_total += 1
                    r30_correct += 1 if hit else 0
        elif len(row) == 14:
            mid = row[3]
            if mid == champ_id_for_row:
                hit = row[9] == "1" or row[9].lower() == "true"
                all_total += 1
                all_correct += 1 if hit else 0
                if row_date >= r7_cutoff:
                    r7_total += 1
                    r7_correct += 1 if hit else 0
                if row_date >= r30_cutoff:
                    r30_total += 1
                    r30_correct += 1 if hit else 0

r7_acc = r7_correct / r7_total if r7_total > 0 else 0
r30_acc = r30_correct / r30_total if r30_total > 0 else 0
all_acc = all_correct / all_total if all_total > 0 else 0

metrics["last_updated"] = TODAY
metrics["rolling_7d"] = {
    "accuracy": round(r7_acc, 4),
    "ev_realized": round(r7_acc * 0.91 - (1 - r7_acc), 4),
    "total_games": r7_total,
    "total_correct": r7_correct,
    "note": f"Updated with Nov 4 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). 5 upsets: BKN beat CHA, IND beat MEM, MIN beat HOU, POR beat PHX, MIA beat LAC."
}
metrics["rolling_30d"] = {
    "accuracy": round(r30_acc, 4),
    "ev_realized": round(r30_acc * 0.91 - (1 - r30_acc), 4),
    "total_games": r30_total,
    "total_correct": r30_correct,
    "note": "30+ days of NBA+NHL data. Nov 4 added."
}
metrics["all_time"] = {
    "accuracy": round(all_acc, 4),
    "ev_realized": round(all_acc * 0.91 - (1 - all_acc), 4),
    "total_games": all_total,
    "total_correct": all_correct,
    "total_bets_recommended": metrics["all_time"].get("total_bets_recommended", 0) + len(bet_games),
    "total_bets_won": metrics["all_time"].get("total_bets_won", 0),
}

for mid in MODEL_ORDER:
    if mid == assumptions["champion"]["id"]:
        m = assumptions["champion"]
    else:
        m = next((c for c in assumptions["challengers"] if c["id"] == mid), None)
    if m:
        lt_acc = m["lifetime_correct"] / m["lifetime_games"] if m["lifetime_games"] > 0 else 0
        metrics["variant_performance"][mid] = {
            "lifetime_games": m["lifetime_games"],
            "lifetime_correct": m["lifetime_correct"],
            "lifetime_accuracy": round(lt_acc, 4),
            "weight": m["weight"],
            "role": "champion" if mid == assumptions["champion"]["id"] else "challenger"
        }

bets_count = len(bet_games)
lean_count = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "LEAN")
no_bet_count = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "NO BET")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(all_games),
    "bets_recommended": bets_count,
    "leans": lean_count,
    "no_bets": no_bet_count,
    "sports": sorted(sports_seen),
    "notes": (f"Nov 4 eval: {total_correct_blended}/{total_games} ML ({blended_acc:.1%}). "
              f"Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL = {len(all_games)} games. "
              f"Light NBA night. Heavy NHL schedule.")
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)

# Print summary
champ = assumptions["champion"]
print(f"\n  Edge-Finder Metrics")
print(f"  {'=' * 40}")
print(f"  Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
print(f"  7-day:  {r7_acc:.0%} accuracy | {metrics['rolling_7d']['ev_realized']:+.1%} realized EV | {r7_total} games")
print(f"  30-day: {r30_acc:.0%} accuracy | {metrics['rolling_30d']['ev_realized']:+.1%} realized EV | {r30_total} games")
print(f"\n  Challenger weights: ", end="")
cw = []
for c in assumptions["challengers"]:
    tag = "(NEW)" if c.get("born", "") > (datetime(2026, 11, 5) - timedelta(days=5)).strftime("%Y-%m-%d") else ""
    cw.append(f"{c['id']}={c['weight']:.1f}{tag}")
print(", ".join(cw))
print(f"  Graveyard: {len(assumptions['graveyard'])} retired variants")

print(f"\n  Tonight: {bets_count} BETs, {lean_count} LEANs, {no_bet_count} NO BETs")
print(f"\n  ** This is for entertainment and analysis purposes only. **")
print(f"  ** Past performance does not guarantee future results. **")

print("\nDone.")
