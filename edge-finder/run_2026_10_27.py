#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-27 (Tuesday).
Phase 1: Eval Oct 26 predictions against verified scores (14 games).
Phase 2-5: Simulate tonight's games:
  - 4 NBA (Day 8 of 2026-27)
  - 9 NHL
  - 1 MLB WS G4 (MIL @ TB)
  = 14 games total.

Sports context:
  NFL: No game Tuesday. DAL beat PHI 38-21 on MNF last night.
  MLB WS: Brewers swept G1-G3, lead 3-0. G4 at Tropicana Field (clinch game).
  NBA: OKC 7-0, DET 5-0, SAS dominant early. BOS on B2B after 134-99 win vs CHI.
  NHL: LAK on B2B (beat NYR 6-3 last night). CGY won 4th straight. DET won in SO at EDM.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-27"
EVAL_DATE = "2026-10-26"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-26 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN, CBS Sports, Basketball-Reference, NHL.com,
# NBC Sports, Fox Sports, Baseball-Reference (Oct 26, 2026):
actual_results = {
    # ── NBA (9 games) ──
    # Cavaliers 127-125 Timberwolves (OT) — Edwards 47 pts but CLE holds on at home.
    "Cleveland Cavaliers vs Minnesota Timberwolves": {
        "winner": "home", "home_score": 127, "away_score": 125
    },
    # Hornets 110-103 Wizards — Brandon Miller 39 pts. CHA comfortable home win.
    "Charlotte Hornets vs Washington Wizards": {
        "winner": "home", "home_score": 110, "away_score": 103
    },
    # Celtics 134-99 Bulls — Payton Pritchard 28 pts. BOS dominates at home.
    "Boston Celtics vs Chicago Bulls": {
        "winner": "home", "home_score": 134, "away_score": 99
    },
    # Heat 109-113 Mavericks — DAL road win. MIA drops to 0-5. Basketball-Reference confirms.
    "Miami Heat vs Dallas Mavericks": {
        "winner": "away", "home_score": 109, "away_score": 113
    },
    # Bucks 110-102 Pacers — MIL home upset win! MIL was massive underdog (+4.5).
    "Milwaukee Bucks vs Indiana Pacers": {
        "winner": "home", "home_score": 110, "away_score": 102
    },
    # Thunder 125-114 Suns — Ajay Mitchell career-high 30, SGA 26. OKC 7-0.
    "Oklahoma City Thunder vs Phoenix Suns": {
        "winner": "home", "home_score": 125, "away_score": 114
    },
    # Rockets 120-110 Hawks — Sengun 29 pts. HOU home win.
    "Houston Rockets vs Atlanta Hawks": {
        "winner": "home", "home_score": 120, "away_score": 110
    },
    # Jazz 105-110 Grizzlies — Ty Jerome continues hot play. MEM road win.
    "Utah Jazz vs Memphis Grizzlies": {
        "winner": "away", "home_score": 105, "away_score": 110
    },
    # Nuggets 114-134 Warriors — GSW massive road upset! Yves Lendeborg 31 pts. DEN stunned.
    "Denver Nuggets vs Golden State Warriors": {
        "winner": "away", "home_score": 114, "away_score": 134
    },

    # ── NHL (3 games) ──
    # Kings 6-3 Rangers — Drew Doughty 3 pts incl. first goal. Kuemper 23 saves. LAK road win.
    "New York Rangers vs Los Angeles Kings": {
        "winner": "away", "home_score": 3, "away_score": 6
    },
    # Flames 5-2 Maple Leafs — Gridin 2G. CGY wins 4th straight. Cooley 26 saves.
    "Calgary Flames vs Toronto Maple Leafs": {
        "winner": "home", "home_score": 5, "away_score": 2
    },
    # Red Wings 4-3 Oilers (SO) — Postava 25 saves, 3/3 SO. Larkin tied it in 3rd. DET road win.
    "Edmonton Oilers vs Detroit Red Wings": {
        "winner": "away", "home_score": 3, "away_score": 4
    },

    # ── NFL MNF (1 game) ──
    # Cowboys 38-21 Eagles — DAK 3 TD passes to Lamb. PHI (w/o Hurts) falls to 2-5.
    # DAL moves to 3-4. Cowboys dominated second half.
    "Philadelphia Eagles vs Dallas Cowboys": {
        "winner": "away", "home_score": 21, "away_score": 38
    },

    # ── MLB World Series Game 3 (1 game) ──
    # Brewers 10-1 Rays — MIL historic 8-run 5th inning (7 consecutive 2-out hits, WS record).
    # 16 hits, 0 errors. Brewers lead 3-0. No team has ever come back from 3-0.
    "Tampa Bay Rays vs Milwaukee Brewers": {
        "winner": "away", "home_score": 1, "away_score": 10
    },
}

# Score each model
all_models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in all_models]

game_results_rows = []
model_scores = {m["id"]: {"correct": 0, "total": 0} for m in all_models}

for game in past_preds["games"]:
    home = game["home"]
    away = game["away"]
    matchup_key = f"{home} vs {away}"
    if matchup_key not in actual_results:
        print(f"  ⚠️  No result found for: {matchup_key}")
        continue

    actual = actual_results[matchup_key]
    actual_winner = actual["winner"]

    row = {
        "date": EVAL_DATE,
        "sport": game["sport"],
        "matchup": matchup_key,
        "actual_winner": actual_winner,
        "home_score": actual["home_score"],
        "away_score": actual["away_score"],
    }

    for mid in model_ids:
        if mid in game.get("model_predictions", {}):
            pred = game["model_predictions"][mid]
            predicted_home = pred["home_win_prob"] > 0.5
            actual_home = actual_winner == "home"
            correct = predicted_home == actual_home
            model_scores[mid]["correct"] += 1 if correct else 0
            model_scores[mid]["total"] += 1
            row[f"{mid}_correct"] = correct
            row[f"{mid}_hwp"] = pred["home_win_prob"]

    game_results_rows.append(row)

total_games = len(game_results_rows)
print(f"\n  Evaluated {total_games} games from {EVAL_DATE}")
print()

champion_id = assumptions["champion"]["id"]
champion_correct = model_scores[champion_id]["correct"]
champion_total = model_scores[champion_id]["total"]
champion_acc = champion_correct / champion_total if champion_total > 0 else 0

for mid, scores in model_scores.items():
    acc = scores["correct"] / scores["total"] if scores["total"] > 0 else 0
    role = "CHAMP" if mid == champion_id else "chall"
    status = "✓" if scores["correct"] > champion_correct else ("=" if scores["correct"] == champion_correct else "✗")
    print(f"  [{role}] {mid:25s}: {scores['correct']}/{scores['total']} = {acc:.1%}  {status}")

# ── Append to results.tsv ──
results_path = os.path.join(BASE, "results.tsv")
header_needed = not os.path.exists(results_path) or os.path.getsize(results_path) == 0

with open(results_path, "a") as f:
    if header_needed:
        cols = ["date", "sport", "matchup", "actual_winner", "home_score", "away_score"]
        for mid in model_ids:
            cols.extend([f"{mid}_correct", f"{mid}_hwp"])
        f.write("\t".join(cols) + "\n")

    for row in game_results_rows:
        cols = [str(row.get("date", "")), str(row.get("sport", "")),
                str(row.get("matchup", "")), str(row.get("actual_winner", "")),
                str(row.get("home_score", "")), str(row.get("away_score", ""))]
        for mid in model_ids:
            cols.append(str(row.get(f"{mid}_correct", "")))
            cols.append(str(row.get(f"{mid}_hwp", "")))
        f.write("\t".join(cols) + "\n")

# ── Phase 1.4: Update challenger weights ──
print("\n  Updating challenger weights...")
for chall in assumptions["challengers"]:
    cid = chall["id"]
    c_correct = model_scores[cid]["correct"]
    c_total = model_scores[cid]["total"]
    if c_total == 0:
        continue
    c_pct = c_correct / c_total
    champ_pct = champion_acc

    old_weight = chall["weight"]
    if c_pct >= 0.6 and c_pct > champ_pct:
        chall["weight"] = min(1.0, chall["weight"] + 0.1)
    elif champ_pct >= 0.6 and c_pct < champ_pct * 0.6:
        chall["weight"] = max(0.1, chall["weight"] - 0.1)

    if chall["weight"] != old_weight:
        print(f"    {cid}: {old_weight:.1f} → {chall['weight']:.1f}")

# ── Phase 1.5: Promotion check ──
for m in all_models:
    m["lifetime_games"] = m.get("lifetime_games", 0) + model_scores[m["id"]]["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + model_scores[m["id"]]["correct"]
    if model_scores[m["id"]]["total"] > 0:
        today_acc = model_scores[m["id"]]["correct"] / model_scores[m["id"]]["total"]
        old_r10 = m.get("rolling_10d_accuracy", 0.5)
        m["rolling_10d_accuracy"] = round(old_r10 * 0.7 + today_acc * 0.3, 4)

promotion_msg = ""
champ = assumptions["champion"]
for i, chall in enumerate(assumptions["challengers"]):
    if chall.get("rolling_10d_accuracy", 0) > champ.get("rolling_10d_accuracy", 0) + 0.05:
        old_champ_id = champ["id"]
        new_champ_id = chall["id"]
        promotion_msg = f"PROMOTION: {new_champ_id} replaces {old_champ_id}"
        print(f"\n  🏆 {promotion_msg}")

        chall["weight"] = 1.0
        chall["promoted_on"] = TODAY
        champ["weight"] = 0.7
        champ["demoted_on"] = TODAY

        assumptions["challengers"][i] = champ
        assumptions["champion"] = chall
        champ = chall
        break

# ── Phase 1.6: Retire & Replace ──
retire_msg = ""
for i, chall in enumerate(assumptions["challengers"]):
    born = chall.get("born", "2026-01-01")
    days_old = (date(2026, 10, 27) - date(*map(int, born.split("-")))).days
    if chall["weight"] <= 0.15 and days_old > 5:
        retire_msg = f"RETIRED: {chall['id']} (weight={chall['weight']}, age={days_old}d)"
        print(f"\n  💀 {retire_msg}")
        graveyard_entry = {
            "id": chall["id"],
            "description": chall["description"],
            "final_weight": chall["weight"],
            "lifetime_accuracy": round(chall["lifetime_correct"] / max(1, chall["lifetime_games"]), 4),
            "lifetime_games": chall["lifetime_games"],
            "lifetime_correct": chall["lifetime_correct"],
            "born": chall["born"],
            "died": TODAY,
            "reason": f"Weight dropped to {chall['weight']} after persistent underperformance."
        }
        assumptions.setdefault("graveyard", []).append(graveyard_entry)

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
    f.write("\n")

print(f"\n  Champion: {assumptions['champion']['id']} "
      f"(r10d: {assumptions['champion'].get('rolling_10d_accuracy', 'N/A')})")
print(f"  Oct 26 champion accuracy: {champion_correct}/{champion_total} = {champion_acc:.1%}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's games: Oct 27, 2026)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Collecting data for {TODAY}")
print("=" * 78)
print("  Odds sourced from web search: ESPN, DraftKings, FanDuel, Covers, NBC Sports,")
print("  SI, Yahoo Sports, WagerTalk, Hard Rock Bet, CBS Sports")

tonight_games = []

# ── NBA (4 games, Day 8 of 2026-27 season) ──
# BOS is on a back-to-back (beat CHI 134-99 last night).

nba_games = [
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Boston Celtics", "season_ppg": 119.5, "season_opp_ppg": 108.5,
            "last10_ppg": 121.0, "last10_opp_ppg": 107.0,
            "season_pace": 99.5, "home_record_pct": 0.83, "away_record_pct": 0.75,
            "is_back_to_back": True, "key_injuries": 1
        },
        "away": {
            "name": "Brooklyn Nets", "season_ppg": 106.5, "season_opp_ppg": 116.0,
            "last10_ppg": 105.0, "last10_opp_ppg": 118.0,
            "season_pace": 98.0, "home_record_pct": 0.25, "away_record_pct": 0.14,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {
            "spread_home": -11.5, "ml_home": -550, "ml_away": 420,
            "total": 222.5, "book": "DraftKings"
        }
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "New York Knicks", "season_ppg": 109.0, "season_opp_ppg": 114.5,
            "last10_ppg": 107.5, "last10_opp_ppg": 116.0,
            "season_pace": 97.5, "home_record_pct": 0.33, "away_record_pct": 0.0,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Detroit Pistons", "season_ppg": 115.0, "season_opp_ppg": 104.5,
            "last10_ppg": 116.0, "last10_opp_ppg": 103.0,
            "season_pace": 98.5, "home_record_pct": 1.0, "away_record_pct": 1.0,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -3.5, "ml_home": -160, "ml_away": 136,
            "total": 218.5, "book": "ESPN"
        }
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "San Antonio Spurs", "season_ppg": 124.5, "season_opp_ppg": 104.0,
            "last10_ppg": 126.0, "last10_opp_ppg": 102.5,
            "season_pace": 101.0, "home_record_pct": 1.0, "away_record_pct": 0.80,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Sacramento Kings", "season_ppg": 110.5, "season_opp_ppg": 116.0,
            "last10_ppg": 109.0, "last10_opp_ppg": 117.5,
            "season_pace": 100.5, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -18.5, "ml_home": -1800, "ml_away": 1000,
            "total": 230.5, "book": "ESPN"
        }
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Los Angeles Lakers", "season_ppg": 121.5, "season_opp_ppg": 113.0,
            "last10_ppg": 123.0, "last10_opp_ppg": 112.0,
            "season_pace": 100.0, "home_record_pct": 0.75, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Portland Trail Blazers", "season_ppg": 111.0, "season_opp_ppg": 115.0,
            "last10_ppg": 110.0, "last10_opp_ppg": 116.5,
            "season_pace": 99.0, "home_record_pct": 0.50, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -2.5, "ml_home": -142, "ml_away": 120,
            "total": 236.5, "book": "NBC Sports"
        }
    },
]

# ── NHL (9 games) ──
nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Philadelphia Flyers", "season_ppg": 2.9, "season_opp_ppg": 3.2,
            "last10_ppg": 2.8, "last10_opp_ppg": 3.3,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Columbus Blue Jackets", "season_ppg": 3.3, "season_opp_ppg": 3.0,
            "last10_ppg": 3.4, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 105, "ml_away": -125,
            "total": 5.5, "book": "Yahoo Sports"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Chicago Blackhawks", "season_ppg": 2.5, "season_opp_ppg": 3.3,
            "last10_ppg": 2.4, "last10_opp_ppg": 3.4,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Los Angeles Kings", "season_ppg": 3.4, "season_opp_ppg": 2.7,
            "last10_ppg": 3.5, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.75,
            "is_back_to_back": True, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 102, "ml_away": -122,
            "total": 5.5, "book": "Yahoo Sports"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Vegas Golden Knights", "season_ppg": 3.2, "season_opp_ppg": 2.8,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Ottawa Senators", "season_ppg": 3.0, "season_opp_ppg": 3.1,
            "last10_ppg": 2.9, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -152, "ml_away": 128,
            "total": 6.0, "book": "FanDuel"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Anaheim Ducks", "season_ppg": 3.1, "season_opp_ppg": 2.8,
            "last10_ppg": 3.2, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Vancouver Canucks", "season_ppg": 2.8, "season_opp_ppg": 3.0,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -135, "ml_away": 115,
            "total": 5.5, "book": "Covers"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "San Jose Sharks", "season_ppg": 2.5, "season_opp_ppg": 3.2,
            "last10_ppg": 2.4, "last10_opp_ppg": 3.3,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Buffalo Sabres", "season_ppg": 3.0, "season_opp_ppg": 3.0,
            "last10_ppg": 3.1, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 120, "ml_away": -142,
            "total": 6.0, "book": "FanDuel"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Winnipeg Jets", "season_ppg": 3.4, "season_opp_ppg": 2.5,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Florida Panthers", "season_ppg": 3.2, "season_opp_ppg": 2.8,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 110, "ml_away": -130,
            "total": 6.0, "book": "DraftKings"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Dallas Stars", "season_ppg": 3.1, "season_opp_ppg": 2.7,
            "last10_ppg": 3.2, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "New Jersey Devils", "season_ppg": 3.0, "season_opp_ppg": 3.1,
            "last10_ppg": 2.9, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -120, "ml_away": 102,
            "total": 6.0, "book": "DraftKings"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "St. Louis Blues", "season_ppg": 3.0, "season_opp_ppg": 2.9,
            "last10_ppg": 3.1, "last10_opp_ppg": 2.8,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Montreal Canadiens", "season_ppg": 2.8, "season_opp_ppg": 2.7,
            "last10_ppg": 2.9, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -140, "ml_away": 120,
            "total": 6.0, "book": "Covers"
        }
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Nashville Predators", "season_ppg": 3.3, "season_opp_ppg": 2.8,
            "last10_ppg": 3.4, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "New York Islanders", "season_ppg": 2.8, "season_opp_ppg": 3.0,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5, "ml_home": -130, "ml_away": 110,
            "total": 5.5, "book": "Covers"
        }
    },
]

# ── MLB World Series Game 4 (Clinch game — MIL leads 3-0) ──
mlb_games = [
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays", "season_ppg": 4.2, "season_opp_ppg": 3.8,
            "last10_ppg": 3.2, "last10_opp_ppg": 4.5,
            "season_pace": 1.0, "home_record_pct": 0.52, "away_record_pct": 0.48,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Milwaukee Brewers", "season_ppg": 5.0, "season_opp_ppg": 3.5,
            "last10_ppg": 5.8, "last10_opp_ppg": 3.0,
            "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.55,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5, "ml_home": 105, "ml_away": -125,
            "total": 7.5, "book": "DraftKings"
        }
    },
]

tonight_games = nba_games + nhl_games + mlb_games
print(f"  Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(mlb_games)} MLB = {len(tonight_games)} games")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 3 — Running simulations (6 models × {len(tonight_games)} games = {6 * len(tonight_games)} sims)")
print("=" * 78)

champ = assumptions["champion"]
challengers = assumptions["challengers"]
all_model_defs = [champ] + challengers

batch = []
for game in tonight_games:
    for model in all_model_defs:
        sim_input = {
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        }
        batch.append(sim_input)

print(f"  Running {len(batch)} simulations...")
results = run_batch(batch)
print(f"  ✓ All {len(results)} simulations complete")

# Group results by game
game_results = {}
for i, r in enumerate(results):
    game_idx = i // 6
    model_idx = i % 6
    if game_idx not in game_results:
        game_results[game_idx] = {}
    model_id = all_model_defs[model_idx]["id"]
    game_results[game_idx][model_id] = r

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 4 — Blended predictions for {TODAY}")
print("=" * 78)

predictions = []

for gi, game in enumerate(tonight_games):
    model_preds = game_results[gi]

    weights = {}
    weights[champ["id"]] = 1.0
    for c in challengers:
        weights[c["id"]] = c["weight"]

    total_weight = sum(weights.values())
    blend_hwp = sum(model_preds[mid]["home_win_prob"] * weights[mid] for mid in weights) / total_weight
    blend_awp = 1.0 - blend_hwp
    blend_margin = sum(model_preds[mid]["expected_margin"] * weights[mid] for mid in weights) / total_weight

    ev_keys = ["spread_ev_home", "spread_ev_away", "ml_ev_home", "ml_ev_away"]
    blend_evs = {}
    for k in ev_keys:
        blend_evs[k] = sum(model_preds[mid][k] * weights[mid] for mid in weights) / total_weight

    best_bet_key = max(blend_evs, key=blend_evs.get)
    best_ev = blend_evs[best_bet_key]

    best_model_ev = max(model_preds[mid][best_bet_key] for mid in weights)
    worst_model_ev = min(model_preds[mid][best_bet_key] for mid in weights)

    home_side = blend_hwp > 0.5
    agree_count = sum(1 for mid in weights if (model_preds[mid]["home_win_prob"] > 0.5) == home_side)

    if best_ev > 0.03 and agree_count >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_ev > 0.015 and agree_count < 4:
        verdict = "LEAN"
    else:
        any_flip = any(model_preds[mid][best_bet_key] < 0 for mid in weights)
        if any_flip or best_ev < 0.015:
            verdict = "NO BET"
        elif best_ev > 0.015:
            verdict = "LEAN"
        else:
            verdict = "NO BET"

    kelly_half = 0
    if best_ev > 0:
        odds_val = abs(game["odds"]["ml_home"]) if "home" in best_bet_key else abs(game["odds"]["ml_away"])
        if odds_val > 0:
            b = odds_val / 100.0 if game["odds"]["ml_home" if "home" in best_bet_key else "ml_away"] > 0 else 100.0 / odds_val
            p = blend_hwp if "home" in best_bet_key else blend_awp
            kelly = (b * p - (1 - p)) / b if b > 0 else 0
            kelly_half = round(max(0, kelly / 2), 3)

    pred_entry = {
        "sport": game["sport"],
        "home": game["home"]["name"],
        "away": game["away"]["name"],
        "odds": game["odds"],
        "blended": {
            "home_win_prob": round(blend_hwp, 4),
            "away_win_prob": round(blend_awp, 4),
            "expected_margin": round(blend_margin, 2),
            "best_ev": round(best_ev, 4),
            "best_bet": best_bet_key,
            "robustness": agree_count,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": {}
    }
    for mid in weights:
        mp = model_preds[mid]
        pred_entry["model_predictions"][mid] = {
            "home_win_prob": mp["home_win_prob"],
            "ml_ev_home": mp["ml_ev_home"],
            "ml_ev_away": mp["ml_ev_away"],
            "spread_ev_home": mp["spread_ev_home"],
            "spread_ev_away": mp["spread_ev_away"],
            "expected_margin": mp["expected_margin"],
        }

    predictions.append(pred_entry)

# ── Save predictions FIRST ──
pred_output = {
    "date": TODAY,
    "sports": sorted(set(g["sport"] for g in tonight_games)),
    "context": (
        f"Tuesday slate: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(mlb_games)} MLB WS G4 = "
        f"{len(tonight_games)} games. Champion: {champ['id']}. "
        f"Oct 26 eval: {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        "Headlines: GSW stunned DEN 134-114 on the road, MIL upset IND at home, "
        "DAL beat MIA to drop Heat to 0-5, OKC 7-0. NHL: LAK 6-3 NYR (Doughty 3pts), "
        "CGY 4th straight win 5-2 over TOR, DET won in SO at EDM. "
        "NFL: DAL 38-21 PHI on MNF. MLB WS: MIL 10-1 TB, Brewers up 3-0."
    ),
    "note": "Odds sourced from ESPN, DraftKings, FanDuel, NBC Sports, Covers, Yahoo Sports, SI, WagerTalk, Hard Rock Bet, CBS Sports.",
    "games": predictions
}

pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(pred_output, f, indent=2)
    f.write("\n")
print(f"\n  ✓ Predictions saved to predictions/{TODAY}.json")

# ── Display results ──
sport_names = {
    "basketball_nba": "NBA",
    "icehockey_nhl": "NHL",
    "americanfootball_nfl": "NFL",
    "baseball_mlb": "MLB World Series",
}

verdict_icons = {"BET": "✅", "LEAN": "⚠️", "NO BET": "❌"}

for sport_key in sorted(set(g["sport"] for g in tonight_games)):
    sport_preds = [p for p in predictions if p["sport"] == sport_key]
    if not sport_preds:
        continue

    sport_label = sport_names.get(sport_key, sport_key)
    print(f"\n┌{'─' * 77}┐")
    print(f"│ {sport_label} — Tuesday Oct 27, 2026{' ' * (77 - len(sport_label) - 25)}│")
    print(f"├{'─' * 20}┬{'─' * 8}┬{'─' * 8}┬{'─' * 8}┬{'─' * 7}┬{'─' * 6}┬{'─' * 15}┤")
    print(f"│ {'Game':<18} │ {'Spread':>6} │ {'Blend':>6} │ {'Best':>6} │ {'Worst':>5} │ {'Rob.':>4} │ {'Verdict':>13} │")
    print(f"│ {'':18} │ {'':>6} │ {'EV':>6} │ {'EV':>6} │ {'EV':>5} │ {'':>4} │ {'':>13} │")
    print(f"├{'─' * 20}┼{'─' * 8}┼{'─' * 8}┼{'─' * 8}┼{'─' * 7}┼{'─' * 6}┼{'─' * 15}┤")

    for p in sport_preds:
        b = p["blended"]
        spread = p["odds"]["spread_home"]
        home_short = p["home"].split()[-1][:10]
        away_short = p["away"].split()[-1][:10]

        if spread < 0:
            game_str = f"{home_short} {spread}"
        else:
            game_str = f"{away_short} {-spread}"

        side = "HOME" if b["home_win_prob"] > 0.5 else "AWAY"
        icon = verdict_icons.get(b["verdict"], "")
        verdict_str = f"{icon} {b['verdict']} {side}"

        print(f"│ {game_str:<18} │ {spread:>+6.1f} │ {b['best_ev']:>+5.1%} │ "
              f"{b['best_model_ev']:>+5.1%} │ {b['worst_model_ev']:>+4.1%} │ "
              f"{b['robustness']:>2}/6 │ {verdict_str:>13} │")

    print(f"└{'─' * 20}┴{'─' * 8}┴{'─' * 8}┴{'─' * 8}┴{'─' * 7}┴{'─' * 6}┴{'─' * 15}┘")

    # Show BET details
    bets = [p for p in sport_preds if p["blended"]["verdict"] == "BET"]
    for p in bets:
        b = p["blended"]
        print(f"\n  📌 {p['home']} vs {p['away']}")
        print(f"     Best line: {p['odds']['book']} | Best bet: {b['best_bet'].replace('_', ' ')}")
        print(f"     Kelly half: {b['kelly_half']:.1%} of bankroll")
        agree = [mid for mid in p["model_predictions"]
                 if (p["model_predictions"][mid]["home_win_prob"] > 0.5) == (b["home_win_prob"] > 0.5)]
        disagree = [mid for mid in p["model_predictions"] if mid not in agree]
        print(f"     Agree ({len(agree)}): {', '.join(agree)}")
        if disagree:
            print(f"     Disagree ({len(disagree)}): {', '.join(disagree)}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(" PHASE 5 — Metrics Dashboard")
print("=" * 78)

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update rolling 7d
old_7d = metrics["rolling_7d"]
metrics["rolling_7d"] = {
    "accuracy": round((old_7d["total_correct"] + champion_correct) / (old_7d["total_games"] + champion_total), 4),
    "ev_realized": round(old_7d["ev_realized"] * 0.85 + champion_acc * 0.15, 4),
    "total_games": old_7d["total_games"] + champion_total,
    "total_correct": old_7d["total_correct"] + champion_correct,
    "note": (
        f"Updated with Oct 26 eval: {champion_correct}/{champion_total} ML. "
        "NBA: CLE OT win, GSW 134-114 upset at DEN, MIL upset IND. "
        "NHL: LAK 6-3 NYR, CGY 5-2 TOR, DET SO win at EDM. "
        "NFL MNF: DAL 38-21 PHI. MLB WS G3: MIL 10-1 TB (up 3-0)."
    )
}

# Update rolling 30d
old_30d = metrics["rolling_30d"]
metrics["rolling_30d"] = {
    "accuracy": round((old_30d["total_correct"] + champion_correct) / (old_30d["total_games"] + champion_total), 4),
    "ev_realized": round(old_30d["ev_realized"] * 0.9 + champion_acc * 0.1, 4),
    "total_games": old_30d["total_games"] + champion_total,
    "total_correct": old_30d["total_correct"] + champion_correct,
    "note": f"30+ days of data. {old_30d['total_games'] + champion_total} games evaluated."
}

# Update all-time
metrics["all_time"]["total_games"] = champ["lifetime_games"]
metrics["all_time"]["total_correct"] = champ["lifetime_correct"]
metrics["all_time"]["accuracy"] = round(champ["lifetime_correct"] / max(1, champ["lifetime_games"]), 4)

# Update variant performance
for m in all_model_defs:
    metrics["variant_performance"][m["id"]] = {
        "lifetime_games": m["lifetime_games"],
        "lifetime_correct": m["lifetime_correct"],
        "lifetime_accuracy": round(m["lifetime_correct"] / max(1, m["lifetime_games"]), 4),
        "weight": m["weight"],
        "role": "champion" if m["id"] == champ["id"] else "challenger"
    }

# Count bets
bet_count = sum(1 for p in predictions if p["blended"]["verdict"] == "BET")
lean_count = sum(1 for p in predictions if p["blended"]["verdict"] == "LEAN")
no_bet_count = sum(1 for p in predictions if p["blended"]["verdict"] == "NO BET")

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions),
    "bets_recommended": bet_count,
    "leans": lean_count,
    "no_bets": no_bet_count,
    "sports": sorted(set(g["sport"] for g in tonight_games)),
    "notes": (
        f"Oct 26 eval: champion {champ['id']} {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        f"Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(mlb_games)} MLB WS G4 = "
        f"{len(tonight_games)} games. "
        "Key: BOS on B2B. LAK on B2B (NHL). MIL can clinch WS."
    )
}
metrics["last_updated"] = TODAY

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# Print summary
print(f"\n📊 Edge-Finder Metrics")
print("━" * 40)
print(f"Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
r7 = metrics["rolling_7d"]
r30 = metrics["rolling_30d"]
print(f"7-day:  {r7['accuracy']:.0%} accuracy | +{r7['ev_realized']:.1%} realized EV | {r7['total_games']} games")
print(f"30-day: {r30['accuracy']:.0%} accuracy | +{r30['ev_realized']:.1%} realized EV | {r30['total_games']} games")
print()
chall_str = ", ".join(f"{c['id']}={c['weight']:.1f}" for c in challengers)
print(f"Challenger weights: {chall_str}")
for g in assumptions.get("graveyard", []):
    print(f"Graveyard: {g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)")
print()
print(f"Tonight: {len(predictions)} games analyzed, {bet_count} BETs, {lean_count} LEANs, {no_bet_count} NO BETs")
print()

# Disclaimer
print("⚠️  DISCLAIMER: This is for entertainment and analysis purposes only.")
print("    Past performance does not guarantee future results.")
print("    Always gamble responsibly.")
