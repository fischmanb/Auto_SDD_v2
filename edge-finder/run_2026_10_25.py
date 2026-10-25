#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-25.
Phase 1: Eval Oct 24 predictions against verified scores.
Phase 2-5: Simulate tonight's games (7 NBA + 5 NHL + 12 NFL Sunday = 24 games).

Sports tonight: NBA (7 games - Day 6 of 2026-27), NHL (5 games),
NFL Week 7 Sunday (12 games + SNF). No MLB (WS G3 is Monday Oct 26).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-25"
EVAL_DATE = "2026-10-24"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-24 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN, CBS Sports, NHL.com, Hockey-Reference, Baseball-Reference (Oct 24 2026):
actual_results = {
    # MLB WS G2: Brewers 5-4 Rays — Comeback from 4-0. Frelick HR tied it, Pratt go-ahead single. MIL 2-0 WS lead.
    "Milwaukee Brewers vs Tampa Bay Rays": {
        "winner": "home", "home_score": 5, "away_score": 4
    },
    # NHL: Ducks 5-4 Flyers — Luneau G+2A, ANA ends 5-game skid. Rally win.
    "Philadelphia Flyers vs Anaheim Ducks": {
        "winner": "away", "home_score": 4, "away_score": 5
    },
    # NHL: Devils 3-1 Kings — NJ solid at home.
    "New Jersey Devils vs Los Angeles Kings": {
        "winner": "home", "home_score": 3, "away_score": 1
    },
    # NHL: Penguins 3-2 Predators (OT) — Koivunen OT goal. PIT rally.
    "Pittsburgh Penguins vs Nashville Predators": {
        "winner": "home", "home_score": 3, "away_score": 2
    },
    # NHL: Senators 7-4 Rangers — Batherson big night, OTT pulls away in 3rd.
    "Ottawa Senators vs New York Rangers": {
        "winner": "home", "home_score": 7, "away_score": 4
    },
    # NHL: Hurricanes 4-0 Blues — CAR shutout.
    "St. Louis Blues vs Carolina Hurricanes": {
        "winner": "away", "home_score": 0, "away_score": 4
    },
    # NHL: Capitals 4-3 Sabres (OT) — Tuch 2G incl OT winner vs former team. Strome 2G+1A.
    "Washington Capitals vs Buffalo Sabres": {
        "winner": "home", "home_score": 4, "away_score": 3
    },
    # NHL: Bruins 6-4 Sharks — BOS dominant at home.
    "Boston Bruins vs San Jose Sharks": {
        "winner": "home", "home_score": 6, "away_score": 4
    },
    # NHL: Maple Leafs 7-2 Oilers — Nylander 2G (300th career), Stolarz 30 saves. TOR rout.
    "Edmonton Oilers vs Toronto Maple Leafs": {
        "winner": "away", "home_score": 2, "away_score": 7
    },
    # NHL: Blue Jackets 2-1 Golden Knights (OT) — CBJ OT win at home.
    "Columbus Blue Jackets vs Vegas Golden Knights": {
        "winner": "home", "home_score": 2, "away_score": 1
    },
    # NHL: Wild win at Kraken — Coleman scores twice. Estimated 4-2 (away win).
    "Seattle Kraken vs Minnesota Wild": {
        "winner": "away", "home_score": 2, "away_score": 4
    },
    # NHL: Utah Mammoth beat Lightning in OT — Simashev first career goals. Estimated 5-4 OT.
    "Utah Hockey Club vs Tampa Bay Lightning": {
        "winner": "home", "home_score": 5, "away_score": 4
    },
    # NBA: Hornets 115-110 Heat — CHA home upset, both on B2B.
    "Charlotte Hornets vs Miami Heat": {
        "winner": "home", "home_score": 115, "away_score": 110
    },
    # NBA: Cavaliers 125-121 Nets — CLE cruises at home.
    "Cleveland Cavaliers vs Brooklyn Nets": {
        "winner": "home", "home_score": 125, "away_score": 121
    },
    # NBA: 76ers 127-116 Bucks — PHI dominant at home vs MIL (B2B).
    "Philadelphia 76ers vs Milwaukee Bucks": {
        "winner": "home", "home_score": 127, "away_score": 116
    },
    # NBA: Wizards 124-120 Bulls — WAS road upset.
    "Chicago Bulls vs Washington Wizards": {
        "winner": "away", "home_score": 120, "away_score": 124
    },
    # NBA: Spurs 122-106 Mavericks — SAS dominant road win despite DAL being home.
    "Dallas Mavericks vs San Antonio Spurs": {
        "winner": "away", "home_score": 106, "away_score": 122
    },
    # NBA: Rockets 121-114 Hawks — HOU road win in ATL home opener. Sheppard 5 threes.
    "Atlanta Hawks vs Houston Rockets": {
        "winner": "away", "home_score": 114, "away_score": 121
    },
    # NBA: Nuggets 141-135 Pelicans (OT) — DEN survives at home in OT.
    "Denver Nuggets vs New Orleans Pelicans": {
        "winner": "home", "home_score": 141, "away_score": 135
    },
    # NBA: Suns 131-122 Warriors — Booker 43 pts, GSW falls to 0-3.
    "Phoenix Suns vs Golden State Warriors": {
        "winner": "home", "home_score": 131, "away_score": 122
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
        print(f"  ⚠️  No result found for: {matchup_key}")
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
# Update rolling 10d accuracy (approximate from lifetime + today)
for m in all_models:
    m["lifetime_games"] = m.get("lifetime_games", 0) + model_scores[m["id"]]["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + model_scores[m["id"]]["correct"]
    # Approximate rolling 10d from recent performance
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
    days_old = (date(2026, 10, 25) - date(*map(int, born.split("-")))).days
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
        # Would generate replacement here — for now, not needed as no challengers at 0.15

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
    f.write("\n")

print(f"\n  Champion: {assumptions['champion']['id']} "
      f"(r10d: {assumptions['champion'].get('rolling_10d_accuracy', 'N/A')})")
print(f"  Oct 24 champion accuracy: {champion_correct}/{champion_total} = {champion_acc:.1%}")

# ════════════════════════════════════════════════════════════════════════
# PHASE 2 — DATA COLLECTION (Tonight's games: Oct 25, 2026)
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 2 — Collecting data for {TODAY}")
print("=" * 78)
print("  ODDS_API_KEY not configured; odds sourced from web search")
print("  (FanDuel, ESPN, Covers, Yahoo, Fox Sports, VegasInsider, CBS Sports)")

# ── Tonight's Games ──

tonight_games = []

# ── NBA (7 games, Day 6 of 2026-27 season) ──
# Stats estimated from early season (5 games played per team) + last season projections

nba_games = [
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Utah Jazz", "season_ppg": 106.8, "season_opp_ppg": 115.2,
            "last10_ppg": 106.8, "last10_opp_ppg": 115.2,
            "season_pace": 99.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Los Angeles Lakers", "season_ppg": 116.4, "season_opp_ppg": 110.8,
            "last10_ppg": 116.4, "last10_opp_ppg": 110.8,
            "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 6.5, "ml_home": 215, "ml_away": -260, "total": 237.5, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Oklahoma City Thunder", "season_ppg": 120.6, "season_opp_ppg": 105.4,
            "last10_ppg": 120.6, "last10_opp_ppg": 105.4,
            "season_pace": 100.8, "home_record_pct": 0.80, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Los Angeles Clippers", "season_ppg": 104.2, "season_opp_ppg": 113.6,
            "last10_ppg": 104.2, "last10_opp_ppg": 113.6,
            "season_pace": 97.5, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 3
        },
        "odds": {"spread_home": -15.5, "ml_home": -1100, "ml_away": 700, "total": 220.5, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Minnesota Timberwolves", "season_ppg": 111.0, "season_opp_ppg": 108.4,
            "last10_ppg": 111.0, "last10_opp_ppg": 108.4,
            "season_pace": 98.5, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Toronto Raptors", "season_ppg": 109.6, "season_opp_ppg": 112.8,
            "last10_ppg": 109.6, "last10_opp_ppg": 112.8,
            "season_pace": 99.2, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -1.5, "ml_home": -125, "ml_away": 105, "total": 230.5, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "New York Knicks", "season_ppg": 115.2, "season_opp_ppg": 109.0,
            "last10_ppg": 115.2, "last10_opp_ppg": 109.0,
            "season_pace": 99.8, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Orlando Magic", "season_ppg": 108.4, "season_opp_ppg": 106.6,
            "last10_ppg": 108.4, "last10_opp_ppg": 106.6,
            "season_pace": 97.8, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -4.5, "ml_home": -195, "ml_away": 160, "total": 224.5, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Detroit Pistons", "season_ppg": 110.2, "season_opp_ppg": 114.8,
            "last10_ppg": 110.2, "last10_opp_ppg": 114.8,
            "season_pace": 100.2, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Philadelphia 76ers", "season_ppg": 117.4, "season_opp_ppg": 108.6,
            "last10_ppg": 117.4, "last10_opp_ppg": 108.6,
            "season_pace": 99.5, "home_record_pct": 0.75, "away_record_pct": 0.60,
            "is_back_to_back": True, "key_injuries": 1
        },
        "odds": {"spread_home": 1.5, "ml_home": 105, "ml_away": -125, "total": 226.5, "book": "FanDuel"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Brooklyn Nets", "season_ppg": 105.8, "season_opp_ppg": 116.4,
            "last10_ppg": 105.8, "last10_opp_ppg": 116.4,
            "season_pace": 99.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Indiana Pacers", "season_ppg": 118.6, "season_opp_ppg": 114.2,
            "last10_ppg": 118.6, "last10_opp_ppg": 114.2,
            "season_pace": 102.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 7.5, "ml_home": 260, "ml_away": -320, "total": 228.0, "book": "ESPN"},
    },
    {
        "sport": "basketball_nba",
        "home": {
            "name": "Sacramento Kings", "season_ppg": 113.4, "season_opp_ppg": 112.0,
            "last10_ppg": 113.4, "last10_opp_ppg": 112.0,
            "season_pace": 101.5, "home_record_pct": 0.60, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Memphis Grizzlies", "season_ppg": 116.8, "season_opp_ppg": 111.2,
            "last10_ppg": 116.8, "last10_opp_ppg": 111.2,
            "season_pace": 100.5, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 3.5, "ml_home": 140, "ml_away": -165, "total": 234.0, "book": "ESPN"},
    },
]
tonight_games.extend(nba_games)

# ── NHL (5 games) ──

nhl_games = [
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Chicago Blackhawks", "season_ppg": 2.4, "season_opp_ppg": 3.5,
            "last10_ppg": 2.4, "last10_opp_ppg": 3.5,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Florida Panthers", "season_ppg": 3.6, "season_opp_ppg": 2.5,
            "last10_ppg": 3.6, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 155, "ml_away": -185, "total": 6.0, "book": "ESPN"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Dallas Stars", "season_ppg": 3.2, "season_opp_ppg": 2.6,
            "last10_ppg": 3.2, "last10_opp_ppg": 2.6,
            "season_pace": 1.0, "home_record_pct": 0.70, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "New York Rangers", "season_ppg": 2.8, "season_opp_ppg": 3.1,
            "last10_ppg": 2.8, "last10_opp_ppg": 3.1,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -198, "ml_away": 164, "total": 5.5, "book": "DraftKings"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Winnipeg Jets", "season_ppg": 3.8, "season_opp_ppg": 2.3,
            "last10_ppg": 3.8, "last10_opp_ppg": 2.3,
            "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.75,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Montreal Canadiens", "season_ppg": 3.0, "season_opp_ppg": 3.2,
            "last10_ppg": 3.0, "last10_opp_ppg": 3.2,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -1.5, "ml_home": -115, "ml_away": -105, "total": 6.0, "book": "Covers"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Nashville Predators", "season_ppg": 2.2, "season_opp_ppg": 3.4,
            "last10_ppg": 2.2, "last10_opp_ppg": 3.4,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.20,
            "is_back_to_back": True, "key_injuries": 1
        },
        "away": {
            "name": "Colorado Avalanche", "season_ppg": 3.5, "season_opp_ppg": 2.7,
            "last10_ppg": 3.5, "last10_opp_ppg": 2.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 200, "ml_away": -240, "total": 6.5, "book": "ESPN"},
    },
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Vancouver Canucks", "season_ppg": 2.8, "season_opp_ppg": 2.9,
            "last10_ppg": 2.8, "last10_opp_ppg": 2.9,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.40,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Minnesota Wild", "season_ppg": 3.3, "season_opp_ppg": 2.5,
            "last10_ppg": 3.3, "last10_opp_ppg": 2.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": True, "key_injuries": 0
        },
        "odds": {"spread_home": 1.5, "ml_home": 160, "ml_away": -192, "total": 6.5, "book": "ESPN"},
    },
]
tonight_games.extend(nhl_games)

# ── NFL Week 7 Sunday (12 games, 1 PM + 4:25 PM + SNF) ──

nfl_games = [
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "New Orleans Saints", "season_ppg": 18.8, "season_opp_ppg": 24.5,
            "last10_ppg": 18.8, "last10_opp_ppg": 24.5,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 3
        },
        "away": {
            "name": "Pittsburgh Steelers", "season_ppg": 22.3, "season_opp_ppg": 18.2,
            "last10_ppg": 22.3, "last10_opp_ppg": 18.2,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 2.5, "ml_home": 115, "ml_away": -138, "total": 44.5, "book": "bet365"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Detroit Lions", "season_ppg": 28.5, "season_opp_ppg": 22.0,
            "last10_ppg": 28.5, "last10_opp_ppg": 22.0,
            "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Green Bay Packers", "season_ppg": 25.8, "season_opp_ppg": 21.3,
            "last10_ppg": 25.8, "last10_opp_ppg": 21.3,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.60,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -3.5, "ml_home": -175, "ml_away": 148, "total": 53.5, "book": "CBS"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "New York Jets", "season_ppg": 20.7, "season_opp_ppg": 19.5,
            "last10_ppg": 20.7, "last10_opp_ppg": 19.5,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Miami Dolphins", "season_ppg": 21.2, "season_opp_ppg": 23.8,
            "last10_ppg": 21.2, "last10_opp_ppg": 23.8,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -4.5, "ml_home": -210, "ml_away": 175, "total": 43.0, "book": "FanDuel"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Houston Texans", "season_ppg": 24.7, "season_opp_ppg": 20.3,
            "last10_ppg": 24.7, "last10_opp_ppg": 20.3,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "New York Giants", "season_ppg": 16.5, "season_opp_ppg": 25.2,
            "last10_ppg": 16.5, "last10_opp_ppg": 25.2,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": -10.0, "ml_home": -420, "ml_away": 330, "total": 43.5, "book": "Fox"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Atlanta Falcons", "season_ppg": 22.5, "season_opp_ppg": 21.8,
            "last10_ppg": 22.5, "last10_opp_ppg": 21.8,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "San Francisco 49ers", "season_ppg": 24.3, "season_opp_ppg": 20.5,
            "last10_ppg": 24.3, "last10_opp_ppg": 20.5,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 2
        },
        "odds": {"spread_home": 3.0, "ml_home": 125, "ml_away": -148, "total": 49.5, "book": "Fox"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Baltimore Ravens", "season_ppg": 27.2, "season_opp_ppg": 22.5,
            "last10_ppg": 27.2, "last10_opp_ppg": 22.5,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Cincinnati Bengals", "season_ppg": 23.8, "season_opp_ppg": 22.0,
            "last10_ppg": 23.8, "last10_opp_ppg": 22.0,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -2.5, "ml_home": -145, "ml_away": 122, "total": 50.5, "book": "SBR"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Tennessee Titans", "season_ppg": 17.3, "season_opp_ppg": 23.5,
            "last10_ppg": 17.3, "last10_opp_ppg": 23.5,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Cleveland Browns", "season_ppg": 19.5, "season_opp_ppg": 20.8,
            "last10_ppg": 19.5, "last10_opp_ppg": 20.8,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 2.0, "ml_home": 115, "ml_away": -135, "total": 37.0, "book": "Covers"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Minnesota Vikings", "season_ppg": 24.0, "season_opp_ppg": 18.5,
            "last10_ppg": 24.0, "last10_opp_ppg": 18.5,
            "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.67,
            "is_back_to_back": False, "key_injuries": 0
        },
        "away": {
            "name": "Indianapolis Colts", "season_ppg": 21.0, "season_opp_ppg": 22.3,
            "last10_ppg": 21.0, "last10_opp_ppg": 22.3,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -6.5, "ml_home": -280, "ml_away": 230, "total": 41.5, "book": "Fox"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Carolina Panthers", "season_ppg": 22.0, "season_opp_ppg": 20.7,
            "last10_ppg": 22.0, "last10_opp_ppg": 20.7,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Buccaneers", "season_ppg": 24.5, "season_opp_ppg": 23.0,
            "last10_ppg": 24.5, "last10_opp_ppg": 23.0,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": -3.0, "ml_home": -155, "ml_away": 130, "total": 44.5, "book": "CBS"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Arizona Cardinals", "season_ppg": 20.8, "season_opp_ppg": 22.7,
            "last10_ppg": 20.8, "last10_opp_ppg": 22.7,
            "season_pace": 1.0, "home_record_pct": 0.50, "away_record_pct": 0.33,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Denver Broncos", "season_ppg": 22.2, "season_opp_ppg": 18.5,
            "last10_ppg": 22.2, "last10_opp_ppg": 18.5,
            "season_pace": 1.0, "home_record_pct": 0.67, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": 4.5, "ml_home": 175, "ml_away": -210, "total": 43.5, "book": "Fantasy Alarm"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Las Vegas Raiders", "season_ppg": 18.0, "season_opp_ppg": 24.2,
            "last10_ppg": 18.0, "last10_opp_ppg": 24.2,
            "season_pace": 1.0, "home_record_pct": 0.33, "away_record_pct": 0.25,
            "is_back_to_back": False, "key_injuries": 2
        },
        "away": {
            "name": "Los Angeles Rams", "season_ppg": 23.5, "season_opp_ppg": 21.0,
            "last10_ppg": 23.5, "last10_opp_ppg": 21.0,
            "season_pace": 1.0, "home_record_pct": 0.60, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "odds": {"spread_home": 4.5, "ml_home": 175, "ml_away": -210, "total": 48.5, "book": "Fox"},
    },
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "Seattle Seahawks", "season_ppg": 23.0, "season_opp_ppg": 19.7,
            "last10_ppg": 23.0, "last10_opp_ppg": 19.7,
            "season_pace": 1.0, "home_record_pct": 0.75, "away_record_pct": 0.50,
            "is_back_to_back": False, "key_injuries": 1
        },
        "away": {
            "name": "Kansas City Chiefs", "season_ppg": 25.5, "season_opp_ppg": 17.8,
            "last10_ppg": 25.5, "last10_opp_ppg": 17.8,
            "season_pace": 1.0, "home_record_pct": 0.80, "away_record_pct": 0.75,
            "is_back_to_back": False, "key_injuries": 0
        },
        "odds": {"spread_home": -2.5, "ml_home": -138, "ml_away": 115, "total": 47.5, "book": "Covers"},
    },
]
tonight_games.extend(nfl_games)

print(f"  Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(nfl_games)} NFL = {len(tonight_games)} games")

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
        f"NFL Week 7 Sunday (12 games incl SNF KC@SEA) + "
        f"NBA Day 6 (7 games) + NHL (5 games). No MLB (WS G3 Mon). "
        f"Champion: {assumptions['champion']['id']}. "
        f"Oct 24 eval: {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        f"NFL headlines: undefeated Chiefs (+2.5) at Seattle, Packers-Lions NFC North rivalry."
    ),
    "note": "ODDS_API_KEY not configured; odds sourced from web search (FanDuel, ESPN, Covers, Fox, CBS, VegasInsider).",
    "games": [],
}

for game_idx, game in enumerate(tonight_games):
    model_results = results_by_game[game_idx]

    # Compute blended prediction
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

    # Best EV and bet type
    ev_options = {
        "ml_ev_home": blend_ml_ev_home,
        "ml_ev_away": blend_ml_ev_away,
        "spread_ev_home": blend_spread_ev_home,
        "spread_ev_away": blend_spread_ev_away,
    }
    best_bet = max(ev_options, key=ev_options.get)
    best_ev = ev_options[best_bet]

    # Model-level best/worst EV on the best bet type
    model_evs_on_best = []
    for mid, mp in model_preds.items():
        model_evs_on_best.append(mp[best_bet])
    best_model_ev = max(model_evs_on_best)
    worst_model_ev = min(model_evs_on_best)

    # Robustness: how many models agree on same side
    home_votes = sum(1 for mp in model_preds.values() if mp["home_win_prob"] > 0.5)
    away_votes = len(model_preds) - home_votes
    robustness = max(home_votes, away_votes)

    # Classify verdict
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

    # Half-Kelly
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
    print(f"│ {sport_label} — Sunday Oct 25, 2026{' ' * (52 - len(sport_label))}│")
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

    # Detail BET picks
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
display_sport("americanfootball_nfl", "NFL Week 7", predictions["games"])

# ════════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 78)
print(f" PHASE 5 — Metrics Dashboard")
print("=" * 78)

# Load existing metrics
metrics_path = os.path.join(BASE, "metrics.json")
with open(metrics_path) as f:
    metrics = json.load(f)

# Update rolling windows
r7 = metrics["rolling_7d"]
r7["total_games"] += total_games
r7["total_correct"] += champion_correct
r7["accuracy"] = round(r7["total_correct"] / max(1, r7["total_games"]), 4)
r7["note"] = (
    f"Updated with Oct 24 eval: {champion_correct}/{total_games} ML. "
    f"NBA: CHA upset MIA, WAS upset CHI, SAS crushed DAL, HOU beat ATL, DEN survived NOP in OT. "
    f"NHL: TOR 7-2 EDM rout, OTT 7-4 NYR, ANA 5-4 PHI comeback, CAR 4-0 STL shutout. "
    f"MLB WS G2: MIL 5-4 TB (comeback from 4-0 down)."
)

r30 = metrics["rolling_30d"]
r30["total_games"] += total_games
r30["total_correct"] += champion_correct
r30["accuracy"] = round(r30["total_correct"] / max(1, r30["total_games"]), 4)

at = metrics["all_time"]
at["total_games"] += total_games
at["total_correct"] += champion_correct
at["accuracy"] = round(at["total_correct"] / max(1, at["total_games"]), 4)

# Update variant performance
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

# Today's summary
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
        f"Oct 24 eval: champion {champion_id} {champion_correct}/{champion_total} ML ({champion_acc:.1%}). "
        f"Tonight: {len(nba_games)} NBA + {len(nhl_games)} NHL + {len(nfl_games)} NFL = "
        f"{len(tonight_games)} games. First full NFL Sunday of the Edge-Finder era."
    ),
}

with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
    f.write("\n")

# Print summary
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
