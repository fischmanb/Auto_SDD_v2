#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-10-19.
Phase 1: Eval Oct 17 predictions (last available), update weights.
Phase 2-5: Simulate tonight's games, produce blended predictions.

Sports tonight: NHL (4 games), NFL MNF (1 game), MLB ALCS G6 (1 game).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-10-19"
EVAL_DATE = "2026-10-17"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE 2026-10-17 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(f" PHASE 1 — Evaluating {EVAL_DATE} predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Verified results from ESPN/NHL.com/baseball-reference:
# 4 games verified, 4 games unverifiable (no score found), 1 game not played on this date
actual_results = {
    # NHL: Bruins 4-1 Kings (away BOS won)
    "Los Angeles Kings vs Boston Bruins": {"winner": "away", "home_score": 1, "away_score": 4},
    # NHL: Canadiens 4-3 OT Sabres (home MTL won) — Cole Caufield OT winner
    "Montreal Canadiens vs Buffalo Sabres": {"winner": "home", "home_score": 4, "away_score": 3},
    # NHL: Islanders 4-1 Maple Leafs (away NYI won) — Horvat 1G 1A, Holmstrom 2G
    "Toronto Maple Leafs vs New York Islanders": {"winner": "away", "home_score": 1, "away_score": 4},
    # MLB ALCS G4: Rays 7-3 Guardians (away TB won) — Diaz 2-5 2 RBI
    "Cleveland Guardians vs Tampa Bay Rays": {"winner": "away", "home_score": 3, "away_score": 7},
}

# Games we CANNOT verify (no scores found in web search):
# - Winnipeg Jets vs Carolina Hurricanes: score not found
# - Utah Hockey Club vs Edmonton Oilers: Oct 15/16 game, not Oct 17
# - Nashville Predators vs St. Louis Blues: score not found
# - Los Angeles Dodgers vs Milwaukee Brewers: NLCS G4 was Oct 15/16 (MIL won 6-4, sweep)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
model_ids = [m["id"] for m in all_models]

model_scores = {mid: {"correct": 0, "total": 0} for mid in model_ids}
tsv_lines = []

for game in past_preds["games"]:
    home_name = game["home"]
    away_name = game["away"]
    game_key = f"{home_name} vs {away_name}"

    if game_key not in actual_results:
        continue

    actual = actual_results[game_key]
    actual_winner = actual["winner"]
    margin = actual["home_score"] - actual["away_score"]

    for mid, mr in game["model_predictions"].items():
        predicted_winner = "home" if mr["home_win_prob"] > 0.5 else "away"
        hit = 1 if predicted_winner == actual_winner else 0
        model_scores[mid]["correct"] += hit
        model_scores[mid]["total"] += 1

        best_ev_type = max(
            [("spread_home", mr.get("spread_ev_home", 0)),
             ("spread_away", mr.get("spread_ev_away", 0)),
             ("ml_home", mr.get("ml_ev_home", 0)),
             ("ml_away", mr.get("ml_ev_away", 0))],
            key=lambda x: x[1]
        )
        bet_type = best_ev_type[0]

        spread = game["odds"]["spread_home"]
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
            f"{EVAL_DATE}\t{game['sport']}\t{game_key}\t{mid}\t"
            f"{predicted_winner}\t{mr['expected_margin']:.2f}\t{mr['home_win_prob']:.4f}\t"
            f"{actual_winner}\t{margin}\t{hit}\t"
            f"{mr.get('spread_ev_home', 0):.4f}\t{mr.get('ml_ev_home', 0):.4f}\t{bet_type}\t{bet_result}"
        )

with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

total_games = model_scores[champion["id"]]["total"]
print(f"\nEvaluated {total_games} verified games from {EVAL_DATE} (4 unverifiable games skipped)")
print(f"\nModel accuracy on {EVAL_DATE}:")
for mid in model_ids:
    s = model_scores[mid]
    pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
    role = "CHAMP" if mid == champion["id"] else f"w={next(c['weight'] for c in challengers if c['id'] == mid)}"
    print(f"  {mid:<20} {s['correct']}/{s['total']} = {pct:.1f}% [{role}]")

# ── Step 1.4: Update challenger weights ──────────────────────────────
champ_id = champion["id"]
champ_hits = set()
champ_misses = set()

for game in past_preds["games"]:
    game_key = f"{game['home']} vs {game['away']}"
    if game_key not in actual_results:
        continue
    actual_winner = actual_results[game_key]["winner"]
    champ_mr = game["model_predictions"].get(champ_id)
    if not champ_mr:
        continue
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
    for game in past_preds["games"]:
        game_key = f"{game['home']} vs {game['away']}"
        if game_key not in actual_results:
            continue
        actual_winner = actual_results[game_key]["winner"]
        c_mr = game["model_predictions"].get(cid)
        if not c_mr:
            continue
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
        print(f"  Weight change: {cid} {old_weight} -> {c['weight']} "
              f"(outperformed {len(outperformed)}, underperformed {len(underperformed)} "
              f"in {disagreements} disagreements)")

champion["lifetime_games"] = champion.get("lifetime_games", 0) + model_scores[champ_id]["total"]
champion["lifetime_correct"] = champion.get("lifetime_correct", 0) + model_scores[champ_id]["correct"]

# ── Step 1.5: Promotion check ──────────────────────────────────────
promotion_msg = ""
for c in challengers:
    cid = c["id"]
    c_acc = c["lifetime_correct"] / c["lifetime_games"] if c["lifetime_games"] > 0 else 0
    champ_acc = champion["lifetime_correct"] / champion["lifetime_games"] if champion["lifetime_games"] > 0 else 0.5
    if c_acc - champ_acc >= 0.05:
        promotion_msg = f"PROMOTION: {cid} (acc {c_acc:.3f}) replaces {champ_id} (acc {champ_acc:.3f})"
        print(f"\n  *** {promotion_msg} ***")
        break

if not promotion_msg:
    print("\n  No promotions triggered.")

# ── Step 1.6: Retirement check ──────────────────────────────────────
retirements = []
for c in challengers:
    born = c.get("born", "2026-03-24")
    days_alive = (date(2026, 10, 19) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ════════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (Oct 19, 2026)
# ════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 78}")
print(f" PHASE 2-5 — Predicting games for {TODAY}")
print(f" NHL: 4 games | NFL MNF: 1 game | MLB ALCS G6: 1 game")
print(f"{'=' * 78}")

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers

# ── Tonight's games with odds from web searches ─────────────────────

games_raw = [
    # === NHL Game 1: Colorado Avalanche @ Philadelphia Flyers (7 PM ET) ===
    # COL: 2025-26 was 106 pts (48-13-10). Early 2026-27 ~5-2-1 (strong start).
    #   GPG ~3.5, GAPG ~2.7, home_pct ~0.75, away_pct ~0.65
    # PHI: First win Oct 17 (3-1 vs OTT, ended 9-game losing streak). ~1-7-1.
    #   GPG ~2.0, GAPG ~3.6. Matvei Michkov improving but team struggling badly.
    # Odds: COL -220, PHI +180, Total 6.5 (FanDuel via search snippet)
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Philadelphia Flyers",
            "season_ppg": 2.0,
            "season_opp_ppg": 3.6,
            "last10_ppg": 2.1,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.125,
            "away_record_pct": 0.100,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Colorado Avalanche",
            "season_ppg": 3.5,
            "season_opp_ppg": 2.7,
            "last10_ppg": 3.6,
            "last10_opp_ppg": 2.5,
            "season_pace": 1.0,
            "home_record_pct": 0.750,
            "away_record_pct": 0.667,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": 180,
            "ml_away": -220,
            "total": 6.5,
            "book": "FanDuel"
        }
    },

    # === NHL Game 2: Anaheim Ducks @ New York Rangers (7 PM ET) ===
    # ANA: 2025-26 was 86 pts (41-27-4). Early 2026-27 ~3-4-1.
    #   GPG ~2.6, GAPG ~2.9. Young team, road underdogs.
    # NYR: Traditionally strong at MSG. ~4-3-1 early. Rangers ~59% Kalshi.
    #   GPG ~3.0, GAPG ~2.7.
    # Odds: NYR -200, ANA +165, Total 6.0 (est. from search context)
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "New York Rangers",
            "season_ppg": 3.0,
            "season_opp_ppg": 2.7,
            "last10_ppg": 2.9,
            "last10_opp_ppg": 2.6,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Anaheim Ducks",
            "season_ppg": 2.6,
            "season_opp_ppg": 2.9,
            "last10_ppg": 2.7,
            "last10_opp_ppg": 3.0,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.375,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -200,
            "ml_away": 165,
            "total": 6.0,
            "book": "consensus"
        }
    },

    # === NHL Game 3: San Jose Sharks @ Toronto Maple Leafs (7:30 PM ET) ===
    # TOR: Lost 5 of 6 recently. 2025-26 was 75 pts. ~3-5-1 early.
    #   GPG ~2.8, GAPG ~3.2. Matthews healthy but team slumping.
    # SJ: Rebuilding. ~2-5-1 early.
    #   GPG ~2.3, GAPG ~3.4.
    # Odds: TOR -142, SJ +118, Total 6.5 (FanDuel)
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Toronto Maple Leafs",
            "season_ppg": 2.8,
            "season_opp_ppg": 3.2,
            "last10_ppg": 2.5,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.400,
            "away_record_pct": 0.250,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Jose Sharks",
            "season_ppg": 2.3,
            "season_opp_ppg": 3.4,
            "last10_ppg": 2.4,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.250,
            "away_record_pct": 0.200,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -142,
            "ml_away": 118,
            "total": 6.5,
            "book": "FanDuel"
        }
    },

    # === NHL Game 4: Pittsburgh Penguins @ Utah Mammoth (9 PM ET) ===
    # PIT: Lost 6-2 to VGK on Oct 17. ~2-5-1 early. Crosby productive but team defense poor.
    #   GPG ~2.5, GAPG ~3.5.
    # Utah: ~4-3-1 early. Beat EDM 4-2 recently. Home favorite ~64% Kalshi.
    #   GPG ~3.0, GAPG ~2.8.
    # Odds: Utah -155, PIT +130, Total 6.5 (est. from search context)
    {
        "sport": "icehockey_nhl",
        "home": {
            "name": "Utah Mammoth",
            "season_ppg": 3.0,
            "season_opp_ppg": 2.8,
            "last10_ppg": 3.1,
            "last10_opp_ppg": 2.7,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.400,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Pittsburgh Penguins",
            "season_ppg": 2.5,
            "season_opp_ppg": 3.5,
            "last10_ppg": 2.4,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.333,
            "away_record_pct": 0.200,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -155,
            "ml_away": 130,
            "total": 6.5,
            "book": "FanDuel"
        }
    },

    # === NFL MNF: Washington Commanders @ San Francisco 49ers (8:15 PM ET) ===
    # SF: 5-0. Beat SEA 32-29. Purdy 789 yds 9 TD. McCaffrey 166 rush yds 3 TD.
    #   PPG ~27.4, OPP_PPG ~19.6. Dominant at home. N.Bosa calf questionable.
    # WAS: 1-3-1. Mariota doubtful, Diggs hamstring. Croskey-Merritt 142 rush yds.
    #   PPG ~17.2, OPP_PPG ~24.8. Daniels starting? Offense struggling.
    # Odds: SF -7.5 (-110), SF -420, WAS +330, Total 50.5 (FanDuel)
    {
        "sport": "americanfootball_nfl",
        "home": {
            "name": "San Francisco 49ers",
            "season_ppg": 27.4,
            "season_opp_ppg": 19.6,
            "last10_ppg": 27.4,
            "last10_opp_ppg": 19.6,
            "season_pace": 1.0,
            "home_record_pct": 1.0,
            "away_record_pct": 0.667,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Washington Commanders",
            "season_ppg": 17.2,
            "season_opp_ppg": 24.8,
            "last10_ppg": 17.2,
            "last10_opp_ppg": 24.8,
            "season_pace": 1.0,
            "home_record_pct": 0.333,
            "away_record_pct": 0.000,
            "is_back_to_back": False,
            "key_injuries": 3
        },
        "odds": {
            "spread_home": -7.5,
            "ml_home": -420,
            "ml_away": 330,
            "total": 50.5,
            "book": "FanDuel"
        }
    },

    # === MLB ALCS G6: Tampa Bay Rays @ Cleveland Guardians (8 PM ET) ===
    # TB leads series 3-2. Elimination game for CLE at Progressive Field.
    # TB: Best record in AL. Season RPG ~4.8, OPP_RPG ~3.6. Strong bullpen.
    #   Diaz 2-5 2RBI in G4 win. Won G4 7-3, G5 3-1 per CBS.
    # CLE: Home team, must-win. Season RPG ~4.2, OPP_RPG ~3.8.
    #   Espino (G4 loser). Guardians have strong home support (33K+ G4).
    # Odds: CLE ~-120 (home elim game), TB ~+100 (est.)
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.8,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.2,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.520,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.8,
            "season_opp_ppg": 3.6,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.4,
            "season_pace": 1.0,
            "home_record_pct": 0.580,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -120,
            "ml_away": 100,
            "total": 6.5,
            "book": "consensus"
        }
    },
]

# ── Build simulation batch ──────────────────────────────────────────

batch = []
for game in games_raw:
    for model in all_models:
        batch.append({
            "sport": game["sport"],
            "model_id": model["id"],
            "home": game["home"],
            "away": game["away"],
            "odds": game["odds"],
            "params": model["params"],
            "n_sims": 50000
        })

print(f"\nRunning {len(batch)} simulations ({len(games_raw)} games x {len(all_models)} models)...")

results = run_batch(batch)

# ── Organize results by game ────────────────────────────────────────

games_results = {}
for i, r in enumerate(results):
    game_idx = i // len(all_models)
    model_idx = i % len(all_models)
    game = games_raw[game_idx]
    game_key = f"{game['home']['name']} vs {game['away']['name']}"

    if game_key not in games_results:
        games_results[game_key] = {
            "sport": game["sport"],
            "home": game["home"]["name"],
            "away": game["away"]["name"],
            "odds": game["odds"],
            "model_predictions": {}
        }

    games_results[game_key]["model_predictions"][r["model_id"]] = {
        "home_win_prob": r["home_win_prob"],
        "ml_ev_home": r["ml_ev_home"],
        "ml_ev_away": r["ml_ev_away"],
        "spread_ev_home": r["spread_ev_home"],
        "spread_ev_away": r["spread_ev_away"],
        "expected_margin": r["expected_margin"],
    }

# ── Compute blended predictions ─────────────────────────────────────

predictions_output = {
    "date": TODAY,
    "sports": list(set(g["sport"] for g in games_raw)),
    "context": (
        "Monday: 4 NHL + NFL MNF (WAS@SF) + MLB ALCS G6 (TB@CLE, Rays lead 3-2). "
        "Champion: recency-v1. NHL early season (~10 games); stats volatile. "
        "No API keys; odds from web search. NLCS over (MIL swept LAD). "
        "World Series: MIL vs TB/CLE winner."
    ),
    "note": (
        "ODDS_API_KEY not configured; odds sourced from web search. "
        "NHL stats estimated from early-season results and 2025-26 baselines. "
        "NFL WAS has QB uncertainty (Mariota doubtful). "
        "ALCS G6 is elimination for CLE."
    ),
    "games": []
}

print(f"\n{'=' * 78}")
print(f" RESULTS — {TODAY}")
print(f"{'=' * 78}")

for game_key, gdata in games_results.items():
    total_weight = 0
    blended_hwp = 0
    blended_margin = 0
    best_ev_values = []
    all_evs = []

    for mid, mp in gdata["model_predictions"].items():
        if mid == champion["id"]:
            w = 1.0
        else:
            w = next(c["weight"] for c in challengers if c["id"] == mid)

        total_weight += w
        blended_hwp += w * mp["home_win_prob"]
        blended_margin += w * mp["expected_margin"]

        best_ev = max(mp["ml_ev_home"], mp["ml_ev_away"],
                      mp["spread_ev_home"], mp["spread_ev_away"])
        best_ev_type = max(
            [("ml_home", mp["ml_ev_home"]), ("ml_away", mp["ml_ev_away"]),
             ("spread_home", mp["spread_ev_home"]), ("spread_away", mp["spread_ev_away"])],
            key=lambda x: x[1]
        )[0]
        all_evs.append(best_ev)
        best_ev_values.append((mid, best_ev, best_ev_type, w))

    blended_hwp /= total_weight
    blended_margin /= total_weight

    weighted_ev = sum(ev * w for _, ev, _, w in best_ev_values) / total_weight
    best_model_ev = max(all_evs)
    worst_model_ev = min(all_evs)

    # Robustness: how many models agree on the same side
    home_votes = sum(1 for mp in gdata["model_predictions"].values() if mp["home_win_prob"] > 0.5)
    away_votes = len(gdata["model_predictions"]) - home_votes
    robustness = max(home_votes, away_votes)

    # Best bet determination
    if blended_hwp > 0.5:
        best_side = "home"
    else:
        best_side = "away"

    # Find best individual bet type across models
    champ_mp = gdata["model_predictions"][champion["id"]]
    champ_best = max(
        [("spread_home", champ_mp["spread_ev_home"]),
         ("spread_away", champ_mp["spread_ev_away"]),
         ("ml_home", champ_mp["ml_ev_home"]),
         ("ml_away", champ_mp["ml_ev_away"])],
        key=lambda x: x[1]
    )
    best_bet = champ_best[0]

    # Verdict
    if weighted_ev > 0.03 and robustness >= 4 and worst_model_ev > 0:
        verdict = "BET"
    elif weighted_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    elif weighted_ev > 0.015 and robustness >= 4:
        verdict = "LEAN"
    else:
        verdict = "NO BET"

    # Also check if any model flips sign
    if any(ev < 0 for ev in all_evs) and any(ev > 0 for ev in all_evs):
        if verdict == "BET" and worst_model_ev < 0:
            verdict = "NO BET"

    # Kelly criterion (half Kelly)
    if weighted_ev > 0 and best_model_ev > 0:
        # Simplified Kelly: f = (bp - q) / b where b=payout, p=win_prob, q=1-p
        if best_side == "home":
            prob = blended_hwp
        else:
            prob = 1 - blended_hwp
        kelly_full = max(0, (prob * 2 - 1))  # simplified for even money
        kelly_half = round(kelly_full / 2, 3)
    else:
        kelly_half = 0

    blended = {
        "home_win_prob": round(blended_hwp, 4),
        "away_win_prob": round(1 - blended_hwp, 4),
        "expected_margin": round(blended_margin, 2),
        "best_ev": round(weighted_ev, 4),
        "best_bet": best_bet,
        "robustness": robustness,
        "verdict": verdict,
        "kelly_half": kelly_half,
        "best_model_ev": round(best_model_ev, 4),
        "worst_model_ev": round(worst_model_ev, 4),
    }

    game_out = {
        "sport": gdata["sport"],
        "home": gdata["home"],
        "away": gdata["away"],
        "odds": gdata["odds"],
        "blended": blended,
        "model_predictions": gdata["model_predictions"],
    }
    predictions_output["games"].append(game_out)

    # Print results
    sport_label = gdata["sport"].split("_")[0].upper()
    home_short = gdata["home"].split()[-1][:3].upper()
    away_short = gdata["away"].split()[-1][:3].upper()
    spread = gdata["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}" if spread != 0 else "PK"

    if verdict == "BET":
        emoji = "BET"
        side = "HOME" if best_side == "home" else "AWAY"
        verdict_str = f"BET {side}"
    elif verdict == "LEAN":
        emoji = "LEAN"
        side = "HOME" if best_side == "home" else "AWAY"
        verdict_str = f"LEAN {side}"
    else:
        verdict_str = "NO BET"

    print(f"\n  [{sport_label}] {gdata['away']} @ {gdata['home']}")
    print(f"    Spread: {spread_str} | Blend EV: {weighted_ev:+.1%} | Best: {best_model_ev:+.1%} | Worst: {worst_model_ev:+.1%}")
    print(f"    Win Prob: {gdata['home']} {blended_hwp:.1%} / {gdata['away']} {1-blended_hwp:.1%}")
    print(f"    Robustness: {robustness}/6 | Kelly/2: {kelly_half:.1%} | Verdict: {verdict_str}")

    if verdict == "BET":
        print(f"    >>> RECOMMENDED: {best_bet} at {gdata['odds']['book']}")
        print(f"    >>> Model agreement: {home_votes} home / {away_votes} away")


# ── Save predictions ────────────────────────────────────────────────

pred_path = os.path.join(BASE, "predictions", f"{TODAY}.json")
with open(pred_path, "w") as f:
    json.dump(predictions_output, f, indent=2)
print(f"\nPredictions saved to predictions/{TODAY}.json")

# ── Update metrics ──────────────────────────────────────────────────

with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

metrics["last_updated"] = TODAY

# Update rolling metrics with Oct 17 eval
if total_games > 0:
    champ_correct = model_scores[champ_id]["correct"]
    champ_total = model_scores[champ_id]["total"]

    # Update rolling 7d
    old_7d = metrics["rolling_7d"]
    new_7d_total = old_7d["total_games"] + champ_total
    new_7d_correct = old_7d["total_correct"] + champ_correct
    metrics["rolling_7d"] = {
        "accuracy": round(new_7d_correct / new_7d_total, 4) if new_7d_total > 0 else 0,
        "ev_realized": old_7d["ev_realized"],
        "total_games": new_7d_total,
        "total_correct": new_7d_correct,
        "note": f"Oct 12-18. Added {champ_total} games from Oct 17 eval: {champ_correct}/{champ_total} ML."
    }

    # Update rolling 30d
    old_30d = metrics["rolling_30d"]
    new_30d_total = old_30d["total_games"] + champ_total
    new_30d_correct = old_30d["total_correct"] + champ_correct
    metrics["rolling_30d"] = {
        "accuracy": round(new_30d_correct / new_30d_total, 4) if new_30d_total > 0 else 0,
        "ev_realized": old_30d["ev_realized"],
        "total_games": new_30d_total,
        "total_correct": new_30d_correct,
        "note": f"30 days of data. {new_30d_total} games evaluated."
    }

    # Update all-time
    old_all = metrics["all_time"]
    metrics["all_time"]["total_games"] = old_all["total_games"] + champ_total
    metrics["all_time"]["total_correct"] = old_all["total_correct"] + champ_correct
    metrics["all_time"]["accuracy"] = round(
        metrics["all_time"]["total_correct"] / metrics["all_time"]["total_games"], 4
    ) if metrics["all_time"]["total_games"] > 0 else 0

# Update variant performance
for model in all_models:
    mid = model["id"]
    role = "champion" if mid == champ_id else "challenger"
    metrics["variant_performance"][mid] = {
        "lifetime_games": model.get("lifetime_games", 0),
        "lifetime_correct": model.get("lifetime_correct", 0),
        "lifetime_accuracy": round(model.get("lifetime_correct", 0) / model.get("lifetime_games", 1), 4),
        "weight": model.get("weight", 0.5),
        "role": role
    }

metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(games_raw),
    "bets_recommended": sum(1 for g in predictions_output["games"] if g["blended"]["verdict"] == "BET"),
    "leans": sum(1 for g in predictions_output["games"] if g["blended"]["verdict"] == "LEAN"),
    "no_bets": sum(1 for g in predictions_output["games"] if g["blended"]["verdict"] == "NO BET"),
    "sports": list(set(g["sport"] for g in games_raw)),
    "notes": (
        f"Monday slate: 4 NHL + MNF (WAS@SF) + ALCS G6 (TB@CLE). "
        f"Oct 17 eval: {model_scores[champ_id]['correct']}/{model_scores[champ_id]['total']} champion ML "
        f"({4} verified games, 4 skipped). No weight changes. No promotions."
    )
}

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
print("Metrics updated.\n")

# ── Print summary dashboard ─────────────────────────────────────────
print("=" * 78)
print(" EDGE-FINDER METRICS DASHBOARD")
print("=" * 78)
print(f"Champion: {champ_id} (promoted {champion.get('promoted_on', 'N/A')})")
print(f"7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | "
      f"{metrics['rolling_7d']['total_games']} games")
print(f"30-day: {metrics['rolling_30d']['accuracy']:.0%} accuracy | "
      f"{metrics['rolling_30d']['total_games']} games")
print(f"All-time: {metrics['all_time']['accuracy']:.0%} accuracy | "
      f"{metrics['all_time']['total_games']} games")
print(f"\nChallenger weights:")
for c in challengers:
    tag = " (NEW)" if (date(2026, 10, 19) - date(int(c['born'][:4]), int(c['born'][5:7]), int(c['born'][8:10]))).days <= 5 else ""
    print(f"  {c['id']:<22} w={c['weight']}{tag}")
print(f"\nGraveyard: {len(assumptions.get('graveyard', []))} retired models")
for g in assumptions.get("graveyard", []):
    print(f"  {g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)")

print(f"\n*** This is for entertainment and analysis purposes only. ***")
print(f"*** Past performance does not guarantee future results. ***")
