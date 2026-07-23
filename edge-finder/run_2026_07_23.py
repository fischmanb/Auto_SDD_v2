#!/usr/bin/env python3
"""
Edge-Finder daily runner for 2026-07-23.
Phase 1: Eval July 20 predictions (15 MLB games).
Phase 2-5: Simulate tonight's 5 MLB games, produce blended predictions.
Thursday getaway-day slate — all games are simulation candidates (≤5 games).
"""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from sim import run_batch

BASE = os.path.dirname(__file__)
TODAY = "2026-07-23"
EVAL_DATE = "2026-07-20"

# ════════════════════════════════════════════════════════════════════════
# PHASE 1 — EVALUATE JULY 20 PREDICTIONS
# ════════════════════════════════════════════════════════════════════════

print("=" * 78)
print(" PHASE 1 — Evaluating 2026-07-20 predictions")
print("=" * 78)

with open(os.path.join(BASE, "assumptions.json")) as f:
    assumptions = json.load(f)

with open(os.path.join(BASE, "predictions", f"{EVAL_DATE}.json")) as f:
    past_preds = json.load(f)

# Actual results from July 20, 2026 (sourced via ESPN, MLB.com, web search)
actual_results = {
    "Minnesota Twins @ Cleveland Guardians": {"winner": "home", "home_score": 13, "away_score": 4},
    "Pittsburgh Pirates @ New York Yankees": {"winner": "home", "home_score": 8, "away_score": 5},
    "Tampa Bay Rays @ Toronto Blue Jays": {"winner": "away", "home_score": 1, "away_score": 7},
    "Baltimore Orioles @ Boston Red Sox": {"winner": "home", "home_score": 6, "away_score": 5},
    "Los Angeles Dodgers @ Philadelphia Phillies": {"winner": "home", "home_score": 10, "away_score": 7},
    "San Diego Padres @ Atlanta Braves": {"winner": "home", "home_score": 3, "away_score": 2},
    "San Francisco Giants @ Kansas City Royals": {"winner": "home", "home_score": 4, "away_score": 3},
    "New York Mets @ Milwaukee Brewers": {"winner": "home", "home_score": 8, "away_score": 3},
    "Detroit Tigers @ Chicago Cubs": {"winner": "away", "home_score": 6, "away_score": 8},
    "Chicago White Sox @ Texas Rangers": {"winner": "away", "home_score": 3, "away_score": 10},
    "Miami Marlins @ Houston Astros": {"winner": "home", "home_score": 8, "away_score": 5},
    "Washington Nationals @ Colorado Rockies": {"winner": "away", "home_score": 3, "away_score": 7},
    "Oakland Athletics @ Arizona Diamondbacks": {"winner": "away", "home_score": 2, "away_score": 5},
    "Cincinnati Reds @ Seattle Mariners": {"winner": "home", "home_score": 8, "away_score": 0},
    "St. Louis Cardinals @ Los Angeles Angels": {"winner": "home", "home_score": 3, "away_score": 2},
}

champion = assumptions["champion"]
challengers = assumptions["challengers"]
all_models = [champion] + challengers
champ_id = champion["id"]
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

# Append to results.tsv
with open(os.path.join(BASE, "results.tsv"), "a") as f:
    for line in tsv_lines:
        f.write(line + "\n")

print(f"\n  Scored {len(tsv_lines)} model-game results, appended to results.tsv")

# Print per-model accuracy
print("\n  Model accuracy on July 20 games:")
for mid in model_ids:
    s = model_scores[mid]
    pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
    tag = " (CHAMPION)" if mid == champ_id else ""
    print(f"    {mid}: {s['correct']}/{s['total']} = {pct:.1f}%{tag}")

# ── Step 1.4: Update challenger weights ─────────────────────────────
print("\n  Updating challenger weights...")
champ_correct_set = set()
for pred in past_preds["predictions"]:
    game_key = pred["game"]
    if game_key not in actual_results:
        continue
    actual = actual_results[game_key]
    mr = pred["model_results"][champ_id]
    champ_predicted = "home" if mr["home_win_prob"] > 0.5 else "away"
    if champ_predicted == actual["winner"]:
        champ_correct_set.add(game_key)

for c in challengers:
    cid = c["id"]
    outperform = 0
    underperform = 0
    for pred in past_preds["predictions"]:
        game_key = pred["game"]
        if game_key not in actual_results:
            continue
        actual = actual_results[game_key]
        mr = pred["model_results"].get(cid)
        if mr is None:
            continue
        challenger_predicted = "home" if mr["home_win_prob"] > 0.5 else "away"
        challenger_right = challenger_predicted == actual["winner"]
        champ_right = game_key in champ_correct_set

        if challenger_right and not champ_right:
            outperform += 1
        elif champ_right and not challenger_right:
            underperform += 1

    total_divergent = outperform + underperform
    old_weight = c["weight"]
    if total_divergent > 0:
        if outperform / total_divergent >= 0.6:
            c["weight"] = min(1.0, c["weight"] + 0.1)
        elif underperform / total_divergent >= 0.6:
            c["weight"] = max(0.1, c["weight"] - 0.1)

    print(f"    {cid}: outperform={outperform}, underperform={underperform}, "
          f"weight {old_weight:.1f} -> {c['weight']:.1f}")

# ── Step 1.4b: Update lifetime stats ─────────────────────────────────
for m in all_models:
    mid = m["id"]
    s = model_scores[mid]
    m["lifetime_games"] = m.get("lifetime_games", 0) + s["total"]
    m["lifetime_correct"] = m.get("lifetime_correct", 0) + s["correct"]
    acc = s["correct"] / s["total"] if s["total"] > 0 else 0
    m["rolling_10d_accuracy"] = round(acc, 4)

# ── Step 1.5: Promotion check ─────────────────────────────────────────
champ_acc = model_scores[champ_id]["correct"] / model_scores[champ_id]["total"]
best_challenger = None
best_challenger_acc = 0
for c in challengers:
    cid = c["id"]
    acc = model_scores[cid]["correct"] / model_scores[cid]["total"]
    if acc > best_challenger_acc:
        best_challenger_acc = acc
        best_challenger = c

if best_challenger and best_challenger_acc - champ_acc >= 0.05:
    print(f"\n  PROMOTION: {best_challenger['id']} ({best_challenger_acc:.1%}) replaces "
          f"{champ_id} ({champ_acc:.1%})")
    old_champ = assumptions["champion"].copy()
    old_champ["weight"] = 0.7
    assumptions["champion"] = best_challenger.copy()
    assumptions["champion"]["weight"] = 1.0
    assumptions["champion"]["promoted_on"] = TODAY
    for i, c in enumerate(assumptions["challengers"]):
        if c["id"] == best_challenger["id"]:
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
    days_alive = (date(2026, 7, 23) - date(int(born[:4]), int(born[5:7]), int(born[8:10]))).days
    if c["weight"] <= 0.15 and days_alive > 5:
        retirements.append(c)
        print(f"  RETIRE: {c['id']} (weight={c['weight']}, age={days_alive}d)")

if not retirements:
    print("  No retirements triggered.")

with open(os.path.join(BASE, "assumptions.json"), "w") as f:
    json.dump(assumptions, f, indent=2)
print("\n  assumptions.json updated.")


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2-5 — TONIGHT'S PREDICTIONS (July 23, 2026)
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

# ── Tonight's games with odds sourced via web search ──────────────────
# Thursday July 23, 2026 — MLB only (NBA/NHL/NFL off-season)
# 5-game getaway-day slate. All games are simulation candidates (≤5 threshold).
# Odds sourced from BetMGM, DraftKings, FanDuel, Covers, CBS Sports, ESPN.
# Team stats estimated from standings (~July 22), recent series scores, and known records.

games_raw = [
    # 1. SD Padres @ ATL Braves — 12:15 PM ET
    # ATL 59-42, SD ~50-51. ATL heavy home favorite (Chris Sale likely).
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Atlanta Braves",
            "season_ppg": 4.9,
            "season_opp_ppg": 4.0,
            "last10_ppg": 5.2,
            "last10_opp_ppg": 3.8,
            "season_pace": 1.0,
            "home_record_pct": 0.610,
            "away_record_pct": 0.560,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "San Diego Padres",
            "season_ppg": 4.5,
            "season_opp_ppg": 4.3,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 4.4,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -240,
            "ml_away": 201,
            "total": 8.0,
            "book": "fanduel"
        }
    },

    # 2. MIN Twins @ CLE Guardians — 1:10 PM ET
    # CLE 54-49, MIN ~49-52. CLE moderate home fav. Series finale.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Cleveland Guardians",
            "season_ppg": 4.2,
            "season_opp_ppg": 3.9,
            "last10_ppg": 5.0,
            "last10_opp_ppg": 3.6,
            "season_pace": 1.0,
            "home_record_pct": 0.560,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Minnesota Twins",
            "season_ppg": 4.2,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.8,
            "last10_opp_ppg": 4.5,
            "season_pace": 1.0,
            "home_record_pct": 0.510,
            "away_record_pct": 0.460,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -144,
            "ml_away": 119,
            "total": 7.5,
            "book": "draftkings"
        }
    },

    # 3. TB Rays @ TOR Blue Jays — 3:07 PM ET
    # TB 59-42 (1st AL East), TOR ~46-54. Near pick'em. TB swept Mon-Wed.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Toronto Blue Jays",
            "season_ppg": 3.9,
            "season_opp_ppg": 4.3,
            "last10_ppg": 3.2,
            "last10_opp_ppg": 5.0,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 2
        },
        "away": {
            "name": "Tampa Bay Rays",
            "season_ppg": 4.6,
            "season_opp_ppg": 3.7,
            "last10_ppg": 5.4,
            "last10_opp_ppg": 3.3,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.570,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": 1.5,
            "ml_home": -112,
            "ml_away": -109,
            "total": 8.5,
            "book": "draftkings"
        }
    },

    # 4. ARI Diamondbacks @ STL Cardinals — 5:15 PM ET
    # ARI ~50-52, STL ~47-54. STL slight home fav. ARI hot bats recently.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "St. Louis Cardinals",
            "season_ppg": 4.1,
            "season_opp_ppg": 4.5,
            "last10_ppg": 3.7,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.500,
            "away_record_pct": 0.430,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "away": {
            "name": "Arizona Diamondbacks",
            "season_ppg": 4.6,
            "season_opp_ppg": 4.3,
            "last10_ppg": 5.1,
            "last10_opp_ppg": 4.0,
            "season_pace": 1.0,
            "home_record_pct": 0.520,
            "away_record_pct": 0.470,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -125,
            "ml_away": 105,
            "total": 8.5,
            "book": "draftkings"
        }
    },

    # 5. KC Royals @ DET Tigers — 6:40 PM ET
    # DET ~56-45, KC ~43-59. DET heavy home fav. Series opener.
    {
        "sport": "baseball_mlb",
        "home": {
            "name": "Detroit Tigers",
            "season_ppg": 4.4,
            "season_opp_ppg": 3.7,
            "last10_ppg": 4.8,
            "last10_opp_ppg": 3.5,
            "season_pace": 1.0,
            "home_record_pct": 0.600,
            "away_record_pct": 0.510,
            "is_back_to_back": False,
            "key_injuries": 0
        },
        "away": {
            "name": "Kansas City Royals",
            "season_ppg": 3.8,
            "season_opp_ppg": 4.6,
            "last10_ppg": 3.5,
            "last10_opp_ppg": 4.8,
            "season_pace": 1.0,
            "home_record_pct": 0.460,
            "away_record_pct": 0.380,
            "is_back_to_back": False,
            "key_injuries": 1
        },
        "odds": {
            "spread_home": -1.5,
            "ml_home": -224,
            "ml_away": 182,
            "total": 8.5,
            "book": "draftkings"
        }
    },
]

# ── Build simulation batch ────────────────────────────────────────────
print(f"\n  Building sim batch for {len(games_raw)} games × {len(all_models)} models...")

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

print(f"  Running {len(batch)} simulations...")
results = run_batch(batch)
print(f"  Simulations complete.")

# ── Organize results by game ──────────────────────────────────────────
game_results = {}
for i, game in enumerate(games_raw):
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key] = {
        "game": game,
        "model_outputs": {},
    }

for idx, res in enumerate(results):
    game_idx = idx // len(all_models)
    game = games_raw[game_idx]
    game_key = f"{game['away']['name']} @ {game['home']['name']}"
    game_results[game_key]["model_outputs"][res["model_id"]] = res

# ── Compute blended predictions ───────────────────────────────────────
predictions_out = []

for game_key, gdata in game_results.items():
    game = gdata["game"]
    outputs = gdata["model_outputs"]

    # Compute weighted blend
    total_weight = 0
    blend_wp = 0
    blend_margin = 0
    best_ev = -999
    worst_ev = 999
    agree_home = 0
    agree_away = 0

    model_details = {}
    evs = []

    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champ_id else model["weight"]
        out = outputs[mid]

        total_weight += w
        blend_wp += w * out["home_win_prob"]
        blend_margin += w * out["expected_margin"]

        # Find best EV for this model
        model_best_ev = max(
            out["spread_ev_home"], out["spread_ev_away"],
            out["ml_ev_home"], out["ml_ev_away"]
        )
        evs.append(model_best_ev)
        best_ev = max(best_ev, model_best_ev)
        worst_ev = min(worst_ev, model_best_ev)

        if out["home_win_prob"] > 0.5:
            agree_home += 1
        else:
            agree_away += 1

        model_details[mid] = {
            "home_win_prob": out["home_win_prob"],
            "expected_margin": out["expected_margin"],
            "spread_ev_home": out["spread_ev_home"],
            "spread_ev_away": out["spread_ev_away"],
            "ml_ev_home": out["ml_ev_home"],
            "ml_ev_away": out["ml_ev_away"],
        }

    blend_home_wp = round(blend_wp / total_weight, 4)
    blend_away_wp = round(1 - blend_home_wp, 4)
    blend_margin_val = round(blend_margin / total_weight, 2)

    # Determine blend's best bet type
    blend_spread_home = 0
    blend_spread_away = 0
    blend_ml_home = 0
    blend_ml_away = 0
    for model in all_models:
        mid = model["id"]
        w = 1.0 if mid == champ_id else model["weight"]
        out = outputs[mid]
        blend_spread_home += w * out["spread_ev_home"]
        blend_spread_away += w * out["spread_ev_away"]
        blend_ml_home += w * out["ml_ev_home"]
        blend_ml_away += w * out["ml_ev_away"]

    blend_spread_home /= total_weight
    blend_spread_away /= total_weight
    blend_ml_home /= total_weight
    blend_ml_away /= total_weight

    blend_evs = {
        "spread_home": blend_spread_home,
        "spread_away": blend_spread_away,
        "ml_home": blend_ml_home,
        "ml_away": blend_ml_away,
    }
    best_bet_type = max(blend_evs, key=blend_evs.get)
    best_blend_ev = round(blend_evs[best_bet_type], 4)

    robustness = max(agree_home, agree_away)
    rob_str = f"{robustness}/6"

    # Classify
    any_flips = any(ev < 0 for ev in evs)
    if best_blend_ev > 0.03 and robustness >= 4 and worst_ev > 0:
        verdict = "BET"
    elif best_blend_ev > 0.015 and robustness < 4:
        verdict = "LEAN"
    elif best_blend_ev > 0.015 and robustness >= 4 and not any_flips:
        verdict = "BET"
    else:
        verdict = "NO BET"

    # If EV is very low or any model flips, downgrade
    if any_flips and verdict == "BET":
        verdict = "LEAN"
    if best_blend_ev < 0.015:
        verdict = "NO BET"

    # Side
    if "home" in best_bet_type:
        side = "HOME"
        side_team = game["home"]["name"]
    else:
        side = "AWAY"
        side_team = game["away"]["name"]

    bet_market = "SPREAD" if "spread" in best_bet_type else "ML"

    # Kelly criterion
    if best_blend_ev > 0:
        kelly = round(min(0.05, best_blend_ev / 2), 4)
    else:
        kelly = 0

    pred = {
        "game": game_key,
        "sport": game["sport"],
        "home_team": game["home"]["name"],
        "away_team": game["away"]["name"],
        "odds": game["odds"],
        "blend_home_wp": blend_home_wp,
        "blend_away_wp": blend_away_wp,
        "blend_margin": blend_margin_val,
        "best_bet_type": best_bet_type,
        "best_blend_ev": best_blend_ev,
        "best_model_ev": round(best_ev, 4),
        "worst_model_ev": round(worst_ev, 4),
        "robustness": rob_str,
        "agree_count": robustness,
        "verdict": verdict,
        "side": side,
        "side_team": side_team,
        "bet_market": bet_market,
        "kelly": kelly,
        "model_results": model_details,
    }
    predictions_out.append(pred)

# ── Save predictions ──────────────────────────────────────────────────
pred_file = os.path.join(BASE, "predictions", f"{TODAY}.json")
pred_data = {
    "date": TODAY,
    "predictions": predictions_out,
    "metadata": {
        "sports_checked": ["baseball_mlb"],
        "sports_skipped": [
            "basketball_nba (off-season)",
            "icehockey_nhl (off-season)",
            "americanfootball_nfl (off-season)",
        ],
        "total_games": len(predictions_out),
        "total_bets": sum(1 for p in predictions_out if p["verdict"] == "BET"),
        "total_leans": sum(1 for p in predictions_out if p["verdict"] == "LEAN"),
        "data_sources": [
            "web search (ESPN, MLB.com, FanDuel, DraftKings, BetMGM, Covers, CBS Sports)"
        ],
        "note": "ODDS_API_KEY not configured; odds sourced from web search. Thursday getaway-day slate (5 games).",
    },
}
with open(pred_file, "w") as f:
    json.dump(pred_data, f, indent=2)
print(f"\n  Predictions saved to {pred_file}")

# ── Display results ───────────────────────────────────────────────────
print(f"\n{'=' * 78}")
print(f" RESULTS — MLB Thursday Jul 23, 2026")
print(f"{'=' * 78}")
print()

header = (
    f"{'Game':<32} {'Spread':>6} {'Blend':>6} {'Best':>6} {'Worst':>6} "
    f"{'Rob.':>5} {'Verdict':<14}"
)
print(f"┌{'─' * 85}┐")
print(f"│ MLB — Thursday Jul 23, 2026{' ' * 57}│")
print(f"├{'─' * 85}┤")
print(f"│ {header} │")
print(f"├{'─' * 85}┤")

for p in predictions_out:
    home_short = p["home_team"].split()[-1][:4]
    away_short = p["away_team"].split()[-1][:4]
    spread = p["odds"]["spread_home"]
    spread_str = f"{spread:+.1f}"

    if p["side"] == "HOME":
        game_str = f"{home_short} {spread_str} vs {away_short}"
    else:
        game_str = f"{away_short} {-spread:+.1f} vs {home_short}"

    blend_ev = f"{p['best_blend_ev']:+.1%}"
    best_ev = f"{p['best_model_ev']:+.1%}"
    worst_ev = f"{p['worst_model_ev']:+.1%}"
    rob = p["robustness"]

    if p["verdict"] == "BET":
        verdict_str = f"✅ BET {p['side']}"
    elif p["verdict"] == "LEAN":
        verdict_str = f"⚠️  LEAN {p['side']}"
    else:
        verdict_str = f"❌ NO BET"

    line = f"│ {game_str:<32} {spread_str:>6} {blend_ev:>6} {best_ev:>6} {worst_ev:>6} {rob:>5} {verdict_str:<14} │"
    print(line)

print(f"└{'─' * 85}┘")
print()

# Show details for BET games
for p in predictions_out:
    if p["verdict"] == "BET":
        print(f"  ✅ {p['game']}")
        print(f"     Side: {p['side']} ({p['side_team']}) | Market: {p['bet_market']}")
        print(f"     Blend EV: {p['best_blend_ev']:+.1%} | Kelly: {p['kelly']:.1%} of bankroll")
        print(f"     Best book: {p['odds']['book']}")
        agreeing = []
        disagreeing = []
        for mid, mr in p["model_results"].items():
            best_model_ev = max(mr["spread_ev_home"], mr["spread_ev_away"],
                                mr["ml_ev_home"], mr["ml_ev_away"])
            if (p["side"] == "HOME" and mr["home_win_prob"] > 0.5) or \
               (p["side"] == "AWAY" and mr["home_win_prob"] <= 0.5):
                agreeing.append(f"{mid}(EV={best_model_ev:+.1%})")
            else:
                disagreeing.append(f"{mid}(EV={best_model_ev:+.1%})")
        print(f"     Agree: {', '.join(agreeing)}")
        if disagreeing:
            print(f"     Disagree: {', '.join(disagreeing)}")
        print()

# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — METRICS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

print(f"{'=' * 78}")
print(" PHASE 5 — Metrics Dashboard")
print(f"{'=' * 78}")

# Compute updated metrics
eval_correct = model_scores[champ_id]["correct"]
eval_total = model_scores[champ_id]["total"]

# Read existing metrics
with open(os.path.join(BASE, "metrics.json")) as f:
    metrics = json.load(f)

# Update rolling 7d (replace with today's eval, since last was Jul 18)
old_7d = metrics["rolling_7d"]
metrics["rolling_7d"] = {
    "accuracy": round(eval_correct / eval_total, 4) if eval_total > 0 else 0,
    "ev_realized": round(eval_correct / eval_total, 4) if eval_total > 0 else 0,
    "total_games": eval_total,
    "total_correct": eval_correct,
}

# Update all-time
at = metrics["all_time"]
at["total_games"] = champion.get("lifetime_games", at["total_games"])
at["total_correct"] = champion.get("lifetime_correct", at["total_correct"])
at["accuracy"] = round(at["total_correct"] / at["total_games"], 4) if at["total_games"] > 0 else 0

# Count recommended bets from today's predictions
bets_today = sum(1 for p in predictions_out if p["verdict"] == "BET")
leans_today = sum(1 for p in predictions_out if p["verdict"] == "LEAN")

# Bet record: from Jul 20 eval, count how many recommended bets won
bet_wins = 0
bet_total = 0
for pred in past_preds["predictions"]:
    if pred["verdict"] in ("BET", "LEAN"):
        bet_total += 1
        game_key = pred["game"]
        if game_key not in actual_results:
            continue
        actual = actual_results[game_key]
        margin = actual["home_score"] - actual["away_score"]
        spread = pred["odds"]["spread_home"]
        bet_type = pred["best_bet_type"]
        if bet_type == "spread_home":
            if (margin + spread) > 0:
                bet_wins += 1
        elif bet_type == "spread_away":
            if (-margin - spread) > 0:
                bet_wins += 1
        elif bet_type == "ml_home":
            if actual["winner"] == "home":
                bet_wins += 1
        else:
            if actual["winner"] == "away":
                bet_wins += 1

at["total_bets_recommended"] = at.get("total_bets_recommended", 0) + bet_total
at["total_bets_won"] = at.get("total_bets_won", 0) + bet_wins

# Update rolling 30d
r30 = metrics["rolling_30d"]
r30["total_games"] = at["total_games"]
r30["total_correct"] = at["total_correct"]
r30["accuracy"] = at["accuracy"]

# Update variant performance
vp = metrics["variant_performance"]
for m in all_models:
    mid = m["id"]
    vp[mid] = {
        "lifetime_games": m.get("lifetime_games", 0),
        "lifetime_correct": m.get("lifetime_correct", 0),
        "weight": 1.0 if mid == champ_id else m["weight"],
        "role": "champion" if mid == champ_id else "challenger",
    }

# Update today's summary
metrics["today_summary"] = {
    "date": TODAY,
    "games_analyzed": len(predictions_out),
    "bets_recommended": bets_today,
    "leans": leans_today,
    "sports": ["baseball_mlb"],
    "notes": (
        f"MLB Thursday getaway slate (5 games). "
        f"Eval Jul 20: {eval_correct}/{eval_total} correct ({eval_correct/eval_total*100:.0f}%). "
        f"Jul 20 bets: {bet_wins}/{bet_total} won. "
        f"CLE 13-4 rout of MIN, CHW 10-3 upset of TEX, SEA 8-0 shutout of CIN."
    ),
}

metrics["last_updated"] = TODAY

with open(os.path.join(BASE, "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)

# Print summary
champ = assumptions["champion"]
print(f"\n📊 Edge-Finder Metrics")
print(f"━━━━━━━━━━━━━━━━━━━━")
print(f"Champion: {champ['id']} (promoted {champ.get('promoted_on', 'N/A')})")
print(f"7-day:  {metrics['rolling_7d']['accuracy']:.0%} accuracy | "
      f"{metrics['rolling_7d']['total_games']} games")
print(f"All-time: {at['accuracy']:.1%} accuracy | "
      f"{at['total_games']} games | "
      f"Bets: {at.get('total_bets_won', 0)}/{at.get('total_bets_recommended', 0)} won")
print()

weights_str = ", ".join(
    f"{c['id'].split('-v')[0]}={c['weight']:.1f}" for c in challengers
)
print(f"Challenger weights: {weights_str}")

graveyard = assumptions.get("graveyard", [])
if graveyard:
    gy_str = ", ".join(
        f"{g['id']} (died {g['died']}, {g['lifetime_accuracy']:.0%} accuracy)"
        for g in graveyard
    )
    print(f"Graveyard: {gy_str}")

print(f"\nEval Jul 20: {eval_correct}/{eval_total} = {eval_correct/eval_total*100:.0f}% "
      f"(bets: {bet_wins}/{bet_total} won)")
print()
print("⚠️  DISCLAIMER: For entertainment and analysis purposes only.")
print("   Past performance does not guarantee future results.")
print()
