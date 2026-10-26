#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-26 (Monday).
Phase 1: Eval Oct 25 predictions against verified scores (23 games).
Phase 2-5: Simulate tonight's games:
  - 9 NBA (Day 7 of 2026-27)
  - 3 NHL
  - 1 NFL MNF (DAL @ PHI)
  - 1 MLB WS G3 (MIL @ TB)
  = 14 games total.

Sports context:
  NFL Week 7: SNF was KC@SEA (SEA 20-3 upset). MNF is DAL@PHI.
  MLB WS: Brewers lead Rays 2-0. G3 at Tropicana Field.
  NBA: Early season — OKC undefeated (6-0), DET 4-0, MIA/MIL/NYK all 0-3+.
  NHL: Winnipeg Jets league-best start.
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-26"
EVAL_DATE = "2026-10-25"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-25 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN, CBS Sports, NFL.com, NHL.com, Yahoo Sports,
# Fox Sports, Basketball-Reference (Oct 25, 2026):
actual_results = {
    # ── NBA (7 games) ──
    # Lakers 132-123 Jazz — Luka Doncic 52 pts season-high. LAL cruises.
    "Utah Jazz vs Los Angeles Lakers": {
        "winner": "away", "home_score": 123, "away_score": 132
    },
    # Thunder 108-101 Clippers — SGA 34 pts, OKC stays unbeaten at 6-0.
    "Oklahoma City Thunder vs Los Angeles Clippers": {
        "winner": "home", "home_score": 108, "away_score": 101
    },
    # Timberwolves 117-94 Raptors — MIN dominant at home.
    "Minnesota Timberwolves vs Toronto Raptors": {
        "winner": "home", "home_score": 117, "away_score": 94
    },
    # Magic 111-102 Knicks — ORL upsets NYK on the road. NYK falls to 1-5.
    "New York Knicks vs Orlando Magic": {
        "winner": "away", "home_score": 102, "away_score": 111
    },
    # Pistons 106-93 76ers — Cade 26 pts, DET stays unbeaten (4-0). PHI on B2B.
    "Detroit Pistons vs Philadelphia 76ers": {
        "winner": "home", "home_score": 106, "away_score": 93
    },
    # Pacers 136-109 Nets — IND blowout road win. BKN falls further.
    "Brooklyn Nets vs Indiana Pacers": {
        "winner": "away", "home_score": 109, "away_score": 136
    },
    # Grizzlies 123-112 Kings — Ty Jerome 31 pts, MEM road win.
    "Sacramento Kings vs Memphis Grizzlies": {
        "winner": "away", "home_score": 112, "away_score": 123
    },

    # ── NHL (4 scoreable games; DAL vs NYR SKIPPED — actual opponent was NYI) ──
    # Panthers 3-2 Blackhawks — Lars Eller late winner with 2:23 left. FLA road win.
    "Chicago Blackhawks vs Florida Panthers": {
        "winner": "away", "home_score": 2, "away_score": 3
    },
    # Dallas Stars vs New York Rangers: SKIP — actual game was DAL vs NYI (Islanders 3-6 loss).
    # The prediction had NYR as opponent but Stars actually hosted NYI on Oct 25.
    # Canadiens 2-1 Jets — Heritage Classic outdoor game. Fowler 33 saves. MTL upset.
    "Winnipeg Jets vs Montreal Canadiens": {
        "winner": "away", "home_score": 1, "away_score": 2
    },
    # Predators 6-2 Avalanche — O'Reilly & Stamkos each 2G. NSH home rout, B2B energy.
    "Nashville Predators vs Colorado Avalanche": {
        "winner": "home", "home_score": 6, "away_score": 2
    },
    # Wild 4-2 Canucks — Coleman 2G, MIN wins on the road.
    "Vancouver Canucks vs Minnesota Wild": {
        "winner": "away", "home_score": 2, "away_score": 4
    },

    # ── NFL Week 7 (12 games: 11 Sunday + SNF) ──
    # Steelers 16-10 Saints — PIT defense dominates. NO's injury woes (3 key out) show.
    "New Orleans Saints vs Pittsburgh Steelers": {
        "winner": "away", "home_score": 10, "away_score": 16
    },
    # Lions 20-17 Packers — Jake Bates walk-off FG. DET wins NFC North battle.
    "Detroit Lions vs Green Bay Packers": {
        "winner": "home", "home_score": 20, "away_score": 17
    },
    # Dolphins 28-25 Jets — MIA road upset. NYJ favored but MIA rallies.
    "New York Jets vs Miami Dolphins": {
        "winner": "away", "home_score": 25, "away_score": 28
    },
    # Giants 27-21 Texans (OT) — NYG massive road upset. HOU was -10 favorite.
    "Houston Texans vs New York Giants": {
        "winner": "away", "home_score": 21, "away_score": 27
    },
    # Falcons 29-20 49ers — ATL hands SF their first loss of the season.
    "Atlanta Falcons vs San Francisco 49ers": {
        "winner": "home", "home_score": 29, "away_score": 20
    },
    # Bengals 35-13 Ravens — CIN blowout road win at Baltimore. Huge upset.
    "Baltimore Ravens vs Cincinnati Bengals": {
        "winner": "away", "home_score": 13, "away_score": 35
    },
    # Browns 27-24 Titans — CLE road win in close game.
    "Tennessee Titans vs Cleveland Browns": {
        "winner": "away", "home_score": 24, "away_score": 27
    },
    # Vikings 16-10 Colts — MIN defense dominates at home.
    "Minnesota Vikings vs Indianapolis Colts": {
        "winner": "home", "home_score": 16, "away_score": 10
    },
    # Buccaneers 43-13 Panthers — TB demolishes CAR on the road.
    "Carolina Panthers vs Tampa Bay Buccaneers": {
        "winner": "away", "home_score": 13, "away_score": 43
    },
    # Broncos 30-16 Cardinals — DEN road blowout.
    "Arizona Cardinals vs Denver Broncos": {
        "winner": "away", "home_score": 16, "away_score": 30
    },
    # Rams 35-21 Raiders — Stafford 3 TD, LAR road win.
    "Las Vegas Raiders vs Los Angeles Rams": {
        "winner": "away", "home_score": 21, "away_score": 35
    },
    # Seahawks 20-3 Chiefs (SNF) — SEA shuts down unbeaten KC. Mahomes 165 yds, 1 INT.
    # Smith-Njigba TD, Emanuel Wilson 21-yd TD run. SEA 4-3, KC gets first loss (5-1).
    "Seattle Seahawks vs Kansas City Chiefs": {
        "winner": "home", "home_score": 20, "away_score": 3
    },
}

# Score each model
all_models = [assumptions["champion"]] + assumptions["challengers"]
model_ids = [m["id"] for m in all_models]

game_results_rows = []
model_scores = {m["id"]: {"correct": 0, "total": 0} for m in all_models}

for game in past_preds["games"]:
    matchup_key = f"{game['home']} vs {game['away']}"
    if matchup_key not in actual_results:
        # DAL vs NYR mismatch — actual was DAL vs NYI
        print(f"  ⚠️  No result found for: {matchup_key} (matchup mismatch or not played)")
        continue

    actual = actual_results[matchup_key]
    actual_winner = actual["winner"]  # "home" or "away"

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
    days_old = (date(2026, 10, 26) - date(*map(int, born.split("-")))).days
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
print(f"  Oct 25 champion accuracy: {champion_correct}/{champion_total} = {champion_acc:.1%}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's games: Oct 26, 2026)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Collecting data for {TODAY}")
print("=" * 78)
print("  Odds sourced from web search: FanDuel, BetMGM, DraftKings, SI, ESPN, Covers")

tonight_games = []

# ── NBA (9 games, Day 7 of 2026-27 season) ──
# Stats from early season (6 games played) + Oct 25 results.

nba_games = [
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Cleveland Cavaliers", "season_ppg": 118.0, "season_opp_ppg": 112.5,
            "last10_ppg": 118.0, "last10_opp_ppg": 112.5,
            "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Minnesota Timberwolves", "season_ppg": 112.5, "season_opp_ppg": 108.0,
            "last10_ppg": 112.5, "last10_opp_ppg": 108.0,
            "season_pace": 98.5, "home_record_pct": 0.67, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -4.5, "ml_home": -200, "ml_away": 168, "total": 228.0, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Charlotte Hornets", "season_ppg": 112.0, "season_opp_ppg": 112.5,
            "last10_ppg": 112.0, "last10_opp_ppg": 112.5,
            "season_pace": 99.5, "home_record_pct": 0.60, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Washington Wizards", "season_ppg": 110.5, "season_opp_ppg": 116.0,
            "last10_ppg": 110.5, "last10_opp_ppg": 116.0,
            "season_pace": 100.0, "home_record_pct": 0.33, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -2.5, "ml_home": -135, "ml_away": 114, "total": 230.0, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Boston Celtics", "season_ppg": 116.0, "season_opp_ppg": 108.5,
            "last10_ppg": 116.0, "last10_opp_ppg": 108.5,
            "season_pace": 100.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Chicago Bulls", "season_ppg": 104.0, "season_opp_ppg": 118.0,
            "last10_ppg": 104.0, "last10_opp_ppg": 118.0,
            "season_pace": 99.0, "home_record_pct": 0.33, "away_record_pct": 0.20,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -13.5, "ml_home": -800, "ml_away": 550, "total": 233.0, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Miami Heat", "season_ppg": 106.5, "season_opp_ppg": 114.0,
            "last10_ppg": 106.5, "last10_opp_ppg": 114.0,
            "season_pace": 98.0, "home_record_pct": 0.33, "away_record_pct": 0.0,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Dallas Mavericks", "season_ppg": 108.0, "season_opp_ppg": 113.5,
            "last10_ppg": 108.0, "last10_opp_ppg": 113.5,
            "season_pace": 99.5, "home_record_pct": 0.50, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -8.5, "ml_home": -330, "ml_away": 265, "total": 237.0, "book": "BetMGM"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Milwaukee Bucks", "season_ppg": 108.0, "season_opp_ppg": 116.5,
            "last10_ppg": 108.0, "last10_opp_ppg": 116.5,
            "season_pace": 99.5, "home_record_pct": 0.33, "away_record_pct": 0.0,
            "is_back_to_back": False, "key_injuries": 3
        },
        "away": {
            "name": "Indiana Pacers", "season_ppg": 119.0, "season_opp_ppg": 112.0,
            "last10_ppg": 119.0, "last10_opp_ppg": 112.0,
            "season_pace": 102.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 4.5, "ml_home": 140, "ml_away": -166, "total": 234.0, "book": "DraftKings"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Oklahoma City Thunder", "season_ppg": 120.0, "season_opp_ppg": 104.0,
            "last10_ppg": 120.0, "last10_opp_ppg": 104.0,
            "season_pace": 100.8, "home_record_pct": 0.80, "away_record_pct": 0.75,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Phoenix Suns", "season_ppg": 118.0, "season_opp_ppg": 115.5,
            "last10_ppg": 118.0, "last10_opp_ppg": 115.5,
            "season_pace": 100.0, "home_record_pct": 0.67, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -8.5, "ml_home": -380, "ml_away": 300, "total": 228.0, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Houston Rockets", "season_ppg": 118.5, "season_opp_ppg": 111.0,
            "last10_ppg": 118.5, "last10_opp_ppg": 111.0,
            "season_pace": 100.5, "home_record_pct": 0.75, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Atlanta Hawks", "season_ppg": 120.0, "season_opp_ppg": 116.5,
            "last10_ppg": 120.0, "last10_opp_ppg": 116.5,
            "season_pace": 101.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -5.5, "ml_home": -220, "ml_away": 185, "total": 235.0, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Utah Jazz", "season_ppg": 107.5, "season_opp_ppg": 116.0,
            "last10_ppg": 107.5, "last10_opp_ppg": 116.0,
            "season_pace": 99.0, "home_record_pct": 0.50, "away_record_pct": 0.25,
            "is_back_to_back": True, "key_injuries": 2
        },
        "away": {
            "name": "Memphis Grizzlies", "season_ppg": 117.5, "season_opp_ppg": 111.0,
            "last10_ppg": 117.5, "last10_opp_ppg": 111.0,
            "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 238.5, "book": "BetMGM"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Denver Nuggets", "season_ppg": 119.5, "season_opp_ppg": 113.0,
            "last10_ppg": 119.5, "last10_opp_ppg": 113.0,
            "season_pace": 101.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Golden State Warriors", "season_ppg": 108.0, "season_opp_ppg": 118.5,
            "last10_ppg": 108.0, "last10_opp_ppg": 118.5,
            "season_pace": 100.0, "home_record_pct": 0.33, "away_record_pct": 0.0,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -9.5, "ml_home": -420, "ml_away": 330, "total": 232.0, "book": "ESPN"},
    },
]
tonight_games.extend(nba_games)

# ── NHL (3 games — light Monday slate) ──

nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "New York Rangers", "season_ppg": 2.8, "season_opp_ppg": 3.0,
            "last10_ppg": 2.8, "last10_opp_ppg": 3.0,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Los Angeles Kings", "season_ppg": 3.0, "season_opp_ppg": 2.8,
            "last10_ppg": 3.0, "last10_opp_ppg": 2.8,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -1.5, "ml_home": -145, "ml_away": 125, "total": 5.5, "book": "FanDuel"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Calgary Flames", "season_ppg": 2.9, "season_opp_ppg": 3.0,
            "last10_ppg": 2.9, "last10_opp_ppg": 3.0,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Toronto Maple Leafs", "season_ppg": 3.8, "season_opp_ppg": 2.5,
            "last10_ppg": 3.8, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 145, "ml_away": -170, "total": 6.0, "book": "ESPN"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Edmonton Oilers", "season_ppg": 3.0, "season_opp_ppg": 3.4,
            "last10_ppg": 3.0, "last10_opp_ppg": 3.4,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Detroit Red Wings", "season_ppg": 2.7, "season_opp_ppg": 3.1,
            "last10_ppg": 2.7, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.40, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -165, "ml_away": 140, "total": 6.5, "book": "ESPN"},
    },
]
tonight_games.extend(nhl_games)

# ── NFL MNF Week 7: Dallas Cowboys at Philadelphia Eagles ──

nfl_games = [
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Philadelphia Eagles", "season_ppg": 19.5, "season_opp_ppg": 22.8,
            "last10_ppg": 19.5, "last10_opp_ppg": 22.8,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 4
        },
        "away": {
            "name": "Dallas Cowboys", "season_ppg": 24.5, "season_opp_ppg": 20.5,
            "last10_ppg": 24.5, "last10_opp_ppg": 20.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 4.5, "ml_home": 185, "ml_away": -225, "total": 44.5, "book": "DraftKings"},
    },
]
tonight_games.extend(nfl_games)

# ── MLB World Series Game 3: Milwaukee Brewers at Tampa Bay Rays ──
# Brewers lead series 2-0. Gasser vs Peralta. TB desperate at home.

mlb_games = [
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Tampa Bay Rays", "season_ppg": 4.2, "season_opp_ppg": 3.8,
            "last10_ppg": 3.5, "last10_opp_ppg": 4.2,
            "season_pace": 1.0, "home_record_pct": 0.55, "away_record_pct": 0.48,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Milwaukee Brewers", "season_ppg": 4.5, "season_opp_ppg": 3.6,
            "last10_ppg": 4.8, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.58, "away_record_pct": 0.52,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": -121, "ml_away": 101, "total": 7.5, "book": "DraftKings"},
    },
]
tonight_games.extend(mlb_games)

print(f"  Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(nfl_games)} NFL MNF + {len(mlb_games)} MLB WS = {len(tonight_games)} games")

# ════════════════════════════════════════════════════════════════════════
# PHASE 3 — SIMULATE (Champion + 5 Challengers)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 3 — Running simulations ({len(tonight_games)} games × 6 models = {len(tonight_games)*6} sims)")
print("=" * 78)

all_models_current = [assumptions["champion"]] + assumptions["challengers"]
batch_input = []

for game in tonight_games:
    for model in all_models_current:
        batch_input.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000,
        })

print(f"  Running {len(batch_input)} simulations...")
sim_results = run_batch(batch_input)
print(f"  Done. {len(sim_results)} results.")

# ════════════════════════════════════════════════════════════════════════
# PHASE 4 — BLENDED PREDICTION + OUTPUT
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 4 — Blended predictions")
print("=" * 78)

# Organize results by game
results_by_game = {}
for i, sim_r in enumerate(sim_results):
    game_idx = i // len(all_models_current)
    model_idx = i % len(all_models_current)
    model = all_models_current[model_idx]

    if game_idx not in results_by_game:
        results_by_game[game_idx] = {}
    results_by_game[game_idx][model["id"]] = sim_r

# Build predictions
predictions = {
    "date": TODAY,
    "sports": list(set(g["sport"] for g in tonight_games)),
    "context": (
        f"Monday slate: 9 NBA + 3 NHL + MNF (DAL@PHI) + MLB WS G3 (MIL@TB). "
        f"Champion: {assumptions['champion']['id']}. "
        f"Oct 25 eval: {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        f"Headlines: SEA shut down unbeaten KC 20-3 on SNF. OKC 6-0. "
        f"Jalen Hurts out for season — PHI starts Tanner McKee vs DAL."
    ),
    "note": "Odds sourced from web search (FanDuel, BetMGM, DraftKings, SI, ESPN, Covers).",
    "games": [],
}

for game_idx, game in enumerate(tonight_games):
    model_results = results_by_game[game_idx]

    total_weight = 0
    weighted_hwp = 0
    weighted_ml_ev_home = 0
    weighted_ml_ev_away = 0
    weighted_spread_ev_home = 0
    weighted_spread_ev_away = 0
    weighted_margin = 0

    model_preds = {}
    for model in all_models_current:
        mid = model["id"]
        r = model_results[mid]
        w = model["weight"] if mid != assumptions["champion"]["id"] else 1.0

        total_weight += w
        weighted_hwp += r["home_win_prob"] * w
        weighted_ml_ev_home += r["ml_ev_home"] * w
        weighted_ml_ev_away += r["ml_ev_away"] * w
        weighted_spread_ev_home += r["spread_ev_home"] * w
        weighted_spread_ev_away += r["spread_ev_away"] * w
        weighted_margin += r["expected_margin"] * w

        model_preds[mid] = {
            "home_win_prob": r["home_win_prob"],
            "ml_ev_home": r["ml_ev_home"],
            "ml_ev_away": r["ml_ev_away"],
            "spread_ev_home": r["spread_ev_home"],
            "spread_ev_away": r["spread_ev_away"],
            "expected_margin": r["expected_margin"],
        }

    blend_hwp = round(weighted_hwp / total_weight, 4)
    blend_awp = round(1 - blend_hwp, 4)
    blend_ml_ev_home = round(weighted_ml_ev_home / total_weight, 4)
    blend_ml_ev_away = round(weighted_ml_ev_away / total_weight, 4)
    blend_spread_ev_home = round(weighted_spread_ev_home / total_weight, 4)
    blend_spread_ev_away = round(weighted_spread_ev_away / total_weight, 4)
    blend_margin = round(weighted_margin / total_weight, 2)

    ev_options = {
        "ml_ev_home": blend_ml_ev_home,
        "ml_ev_away": blend_ml_ev_away,
        "spread_ev_home": blend_spread_ev_home,
        "spread_ev_away": blend_spread_ev_away,
    }
    best_bet = max(ev_options, key=ev_options.get)
    best_ev = ev_options[best_bet]

    model_evs_on_best = []
    for mid, mp in model_preds.items():
        model_evs_on_best.append(mp[best_bet])
    best_model_ev = max(model_evs_on_best)
    worst_model_ev = min(model_evs_on_best)

    home_votes = sum(1 for mp in model_preds.values() if mp["home_win_prob"] > 0.5)
    away_votes = len(model_preds) - home_votes
    robustness = max(home_votes, away_votes)

    if best_ev > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif best_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    elif any(mp[best_bet] < 0 for mp in model_preds.values()):
        verdict = "NO BET"
    elif best_ev < 0.015:
        verdict = "NO BET"
    else:
        verdict = "LEAN"

    kelly_half = round(max(0, best_ev / (best_model_ev if best_model_ev > 0 else 1)) * 0.5, 3)
    kelly_half = min(kelly_half, 0.5)

    game_pred = {
        "sport": game["sport"],
        "home": game["home"]["name"],
        "away": game["away"]["name"],
        "odds": game["odds"],
        "blended": {
            "home_win_prob": blend_hwp,
            "away_win_prob": blend_awp,
            "expected_margin": blend_margin,
            "best_ev": round(best_ev, 4),
            "best_bet": best_bet,
            "robustness": robustness,
            "verdict": verdict,
            "kelly_half": kelly_half,
            "best_model_ev": round(best_model_ev, 4),
            "worst_model_ev": round(worst_model_ev, 4),
        },
        "model_predictions": model_preds,
    }
    predictions["games"].append(game_pred)

# Save predictions FIRST
pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions, f, indent=2)
    f.write("\n")
print(f"\n  Saved predictions to {pred_path}")

# ── Display results ──
def display_sport(sport_key, sport_label, games_list):
    sport_games = [g for g in games_list if g["sport"] == sport_key]
    if not sport_games:
        return
    print(f"\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print(f"│ {sport_label} — Monday Oct 26, 2026{' ' * (51 - len(sport_label))}│")
    print(f"├────────────────────────┬────────┬────────┬────────┬──────┬──────┬───────────┤")
    print(f"│ Game                   │ Spread │ Blend  │ Best   │Worst │ Rob. │ Verdict   │")
    print(f"│                        │        │ EV     │ EV     │ EV   │      │           │")
    print(f"├────────────────────────┼────────┼────────┼────────┼──────┼──────┼───────────┤")

    bets = []
    for g in sport_games:
        b = g["blended"]
        spread = g["odds"]["spread_home"]
        spread_str = f"{spread:+.1f}" if spread != 0 else "PK"
        home_abbr = g["home"][:3].upper()
        away_abbr = g["away"][:3].upper()

        if b["home_win_prob"] > 0.5:
            game_str = f"{home_abbr} {spread_str} vs {away_abbr}"
        else:
            game_str = f"{away_abbr} {-spread:.1f} @ {home_abbr}"

        game_str = game_str[:22].ljust(22)

        ev_str = f"{b['best_ev']:+.1%}"
        best_str = f"{b['best_model_ev']:+.1%}"
        worst_str = f"{b['worst_model_ev']:+.1%}"
        rob_str = f"{b['robustness']}/6"

        if b["verdict"] == "BET":
            side = "HOME" if "home" in b["best_bet"] else "AWAY"
            v_str = f"✅ BET {side}"
        elif b["verdict"] == "LEAN":
            side = "HOME" if "home" in b["best_bet"] else "AWAY"
            v_str = f"⚠️  LEAN {side}"
        else:
            v_str = "❌ NO BET"

        v_str = v_str[:9].ljust(9)

        print(f"│ {game_str} │ {spread_str:>6s} │ {ev_str:>6s} │ {best_str:>6s} │{worst_str:>5s} │ {rob_str:>4s} │ {v_str} │")

        if b["verdict"] == "BET":
            bets.append(g)

    print(f"└────────────────────────┴────────┴────────┴────────┴──────┴──────┴───────────┘")

    for g in bets:
        b = g["blended"]
        side = "HOME" if "home" in b["best_bet"] else "AWAY"
        team = g["home"] if side == "HOME" else g["away"]
        bet_type = "ML" if "ml" in b["best_bet"] else "Spread"
        print(f"\n  🎯 {team} ({bet_type} {side}) — EV: {b['best_ev']:+.1%}, Kelly: {b['kelly_half']:.1%}")
        print(f"     Book: {g['odds']['book']} | Models agree: {b['robustness']}/6")
        agrees = []
        disagrees = []
        for mid, mp in g["model_predictions"].items():
            if mp[b["best_bet"]] > 0:
                agrees.append(f"{mid}({mp[b['best_bet']]:+.1%})")
            else:
                disagrees.append(f"{mid}({mp[b['best_bet']]:+.1%})")
        if agrees:
            print(f"     Agree: {', '.join(agrees)}")
        if disagrees:
            print(f"     Disagree: {', '.join(disagrees)}")

display_sport("basketball_nba", "NBA", predictions["games"])
display_sport("icehockey_nhl", "NHL", predictions["games"])
display_sport("americanfootball_nfl", "NFL MNF Week 7", predictions["games"])
display_sport("baseball_mlb", "MLB World Series G3", predictions["games"])

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 5 — Metrics Dashboard")
print("=" * 78)

metrics_path = os.path.join(BASE, "metrics.json")
with open(metrics_path) as f:
    metrics = json.load(f)

r7 = metrics["rolling_7d"]
r7["total_games"] += total_games
r7["total_correct"] += champion_correct
r7["accuracy"] = round(r7["total_correct"] / max(1, r7["total_games"]), 4)
r7["note"] = (
    f"Updated with Oct 25 eval: {champion_correct}/{total_games} ML. "
    f"NBA: LAL beat UTA (Luka 52), OKC 6-0, ORL upset NYK, DET 4-0, IND 136-109 BKN, MEM beat SAC. "
    f"NHL: FLA 3-2 CHI (Eller late), MTL 2-1 WPG Heritage Classic, NSH 6-2 COL surprise, MIN 4-2 VAN. "
    f"NFL: SEA 20-3 KC upset (first KC loss), CIN 35-13 BAL, NYG 27-21 HOU OT upset, "
    f"TB 43-13 CAR, ATL beat undefeated SF 29-20."
)

r30 = metrics["rolling_30d"]
r30["total_games"] += total_games
r30["total_correct"] += champion_correct
r30["accuracy"] = round(r30["total_correct"] / max(1, r30["total_games"]), 4)

at = metrics["all_time"]
at["total_games"] += total_games
at["total_correct"] += champion_correct
at["accuracy"] = round(at["total_correct"] / max(1, at["total_games"]), 4)

for m in all_models_current:
    mid = m["id"]
    role = "champion" if mid == assumptions["champion"]["id"] else "challenger"
    metrics["variant_performance"][mid] = {
        "lifetime_games": m["lifetime_games"],
        "lifetime_correct": m["lifetime_correct"],
        "lifetime_accuracy": round(m["lifetime_correct"] / max(1, m["lifetime_games"]), 4),
        "weight": m["weight"],
        "role": role,
    }

n_bets = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "BET")
n_leans = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "LEAN")
n_no = sum(1 for g in predictions["games"] if g["blended"]["verdict"] == "NO BET")

metrics["last_updated"] = TODAY
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(tonight_games),
    "bets_recommended": n_bets,
    "leans": n_leans,
    "no_bets": n_no,
    "sports": list(set(g["sport"] for g in tonight_games)),
    "notes": (
        f"Oct 25 eval: champion {champion_id} {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        f"Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(nfl_games)} NFL MNF + "
        f"{len(mlb_games)} MLB WS G3 = {len(tonight_games)} games. "
        f"Upsets dominated Oct 25: SEA crushed KC, CIN routed BAL, NYG upset HOU in OT, "
        f"ATL handed SF first loss. Road teams won 15 of 23 evaluated games."
    ),
}

with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

champ = assumptions["champion"]
print(f"""
📊 Edge-Finder Metrics
━━━━━━━━━━━━━━━━━━━━
Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})
7-day:  {r7['accuracy']:.0%} accuracy | {r7['total_games']} games
30-day: {r30['accuracy']:.0%} accuracy | {r30['total_games']} games
All-time: {at['accuracy']:.0%} accuracy | {at['total_games']} games

Challenger weights: {', '.join(f"{c['id']}={c['weight']:.1f}" for c in assumptions['challengers'])}
Graveyard: {', '.join(f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%})" for g in assumptions.get('graveyard', []))}

Tonight: {len(tonight_games)} games analyzed, {n_bets} BET, {n_leans} LEAN, {n_no} NO BET
""")

print("⚠️  DISCLAIMER: For entertainment and analysis purposes only.")
print("    Past performance does not guarantee future results.")
print("    All monetary values in terms of $100 unit bets.")
